"""Etapas de entrenamiento independientes de Airflow.

Los datos permanecen en memoria solo durante cada tarea; los adaptadores del DAG
persisten referencias y checkpoints en S3. Ninguna función se ejecuta al importar.
"""
from dataclasses import dataclass
import hashlib
import io
import json
import math
from importlib.metadata import version

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, classification_report)
from sklearn.model_selection import StratifiedKFold, train_test_split, cross_val_score

from .features import BANDS, CLASSES, D2_FEATURES, make_pipeline, prepare_d2

MODEL_NAME = 'star_type_model_prod'
EXPERIMENT_NAME = 'star type'


@dataclass
class PreparedData:
    frame: pd.DataFrame
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    train_objids: list
    test_objids: list
    sha256: str
    seed: int


def prepare_data(raw_bytes, seed=42):
    frame = prepare_d2(pd.read_csv(io.BytesIO(raw_bytes), dtype={'objid':'string'}))
    if set(frame['class'].unique()) != set(CLASSES):
        raise ValueError(f'Se requieren las tres clases: {CLASSES}')
    train, test = train_test_split(frame.index, test_size=.2, random_state=seed,
                                   stratify=frame['class'])
    if frame.loc[train, 'class'].value_counts().min() < 5:
        raise ValueError('Cada clase requiere al menos 5 ejemplos de entrenamiento para CV=5')
    return PreparedData(frame, frame.loc[train,D2_FEATURES].copy(),
                        frame.loc[test,D2_FEATURES].copy(),
                        frame.loc[train,'class'].astype(str),frame.loc[test,'class'].astype(str),
                        frame.loc[train,'objid'].astype(str).tolist(),
                        frame.loc[test,'objid'].astype(str).tolist(),
                        hashlib.sha256(raw_bytes).hexdigest(),int(seed))


def read_snapshot(s3, snapshot):
    raw = s3.get_object(Bucket=snapshot['bucket'], Key=snapshot['key'])['Body'].read()
    if hashlib.sha256(raw).hexdigest() != snapshot['sha256']:
        raise ValueError('SHA-256 del snapshot no coincide; no se entrena con datos modificados')
    return raw


def configure_tracking(tracking_uri, s3_endpoint):
    import os
    import mlflow
    if version('mlflow') != '3.16.1' or version('scikit-learn') != '1.7.2':
        raise RuntimeError('Se requieren MLflow 3.16.1 y scikit-learn 1.7.2')
    os.environ['MLFLOW_S3_ENDPOINT_URL'] = s3_endpoint
    os.environ['AWS_ENDPOINT_URL_S3'] = s3_endpoint
    mlflow.set_tracking_uri(tracking_uri)
    return mlflow.MlflowClient()


def create_training_run(snapshot, n_trials=250, seed=42, execution_id=None):
    import mlflow
    experiment = mlflow.set_experiment(EXPERIMENT_NAME)
    tags = {'stage':'training','feature_set':'D2','dataset.sha256':snapshot['sha256'],
            'ingestion_run_id':snapshot.get('ingestion_run_id') or 'not_found',
            'optimizer':'optuna','target':'class'}
    if execution_id:
        tags['airflow.run_id'] = execution_id
    run = mlflow.MlflowClient().create_run(experiment.experiment_id, tags=tags,
                                          run_name='best_star_d2_'+(execution_id or snapshot['sha256'][:12]))
    return run.info.run_id


def search_hyperparameters(data, snapshot, n_trials=250, run_id=None, callback=None):
    import mlflow
    import optuna
    if isinstance(n_trials,bool) or not isinstance(n_trials,int) or n_trials < 1:
        raise ValueError('n_trials debe ser un entero positivo')
    run_id = run_id or create_training_run(snapshot,n_trials,data.seed)
    cv = StratifiedKFold(5, shuffle=True, random_state=data.seed)

    def objective(trial):
        with mlflow.start_run(experiment_id=mlflow.active_run().info.experiment_id,
                              run_name=f'trial_{trial.number:03d}',nested=True):
            smallest_fold = len(data.X_train) - math.ceil(len(data.X_train)/5)
            pipe = make_pipeline(trial,max_neighbors=min(25,smallest_fold))
            mlflow.log_params(trial.params)
            mlflow.set_tags({'stage':'search','feature_set':'D2'})
            scores = cross_val_score(pipe,data.X_train,data.y_train,cv=cv,
                                     scoring='f1_weighted',n_jobs=1,error_score='raise')
            mlflow.log_metrics({'cv_f1_weighted':float(scores.mean()),'cv_f1_std':float(scores.std()),
                               **{f'fold_{i}_f1_weighted':float(v) for i,v in enumerate(scores,1)}})
            return float(scores.mean())

    with mlflow.start_run(run_id=run_id):
        mlflow.log_params({'n_trials':n_trials,'cv_folds':5,'seed':data.seed,'test_size':.2,
                           'scoring':'f1_weighted','dataset_uri':f"s3://{snapshot['bucket']}/{snapshot['key']}",
                           'train_rows':len(data.X_train),'test_rows':len(data.X_test)})
        mlflow.log_dict({'bands':BANDS,'features':D2_FEATURES,'classes':CLASSES,
                         'excluded':['objid','ra','dec','redshift']},'preprocessing/d2.json')
        mlflow.log_dict({'train_objid':data.train_objids,'test_objid':data.test_objids},'data/split_objids.json')
        mlflow.log_dict({p:version(p) for p in ['scikit-learn','mlflow','optuna','pandas','numpy']},
                        'environment/versions.json')
        study = optuna.create_study(direction='maximize',sampler=optuna.samplers.TPESampler(seed=data.seed))
        study.optimize(objective,n_trials=n_trials,n_jobs=1,callbacks=[callback] if callback else None)
        mlflow.log_params(study.best_params)
        mlflow.log_metric('best_cv_f1_weighted',study.best_value)
        mlflow.log_dict({'trials':json.loads(study.trials_dataframe().to_json(orient='records'))},'search/trials.json')
    return {'run_id':run_id,'best_params':study.best_params,'best_value':float(study.best_value),
            'sha256':data.sha256,'seed':data.seed,'n_trials':n_trials}


def train_and_log_model(data, search):
    import mlflow
    import mlflow.sklearn
    import optuna
    from mlflow.models import infer_signature
    client = mlflow.MlflowClient()
    if search['sha256'] != data.sha256:
        raise ValueError('La búsqueda pertenece a otro dataset')
    if search['seed'] != data.seed:
        raise ValueError('La búsqueda pertenece a otro split de datos')
    # Un reintento posterior a log_model recupera el artefacto existente.
    models = mlflow.search_logged_models(experiment_ids=[client.get_run(search['run_id']).info.experiment_id],
                                         filter_string=f"source_run_id = '{search['run_id']}'")
    if not models.empty and 'status' in models:
        models=models.loc[models['status'].astype(str).str.upper().eq('READY')]
    if not models.empty:
        model_uri = f"models:/{models['model_id'].iloc[0]}"
    else:
        model = make_pipeline(optuna.trial.FixedTrial(search['best_params']))
        model.fit(data.X_train,data.y_train)
        with mlflow.start_run(run_id=search['run_id']):
            scaler = model.named_steps['scaler']
            mlflow.log_dict({'feature_names':D2_FEATURES,'mean':scaler.mean_.tolist(),
                             'scale':scaler.scale_.tolist()},'preprocessing/scaler.json')
            info = mlflow.sklearn.log_model(model,name='model',
                       signature=infer_signature(data.X_train,model.predict(data.X_train)),
                       input_example=data.X_train.head(3),serialization_format='cloudpickle',
                       metadata={'feature_set':'D2','dataset_sha256':data.sha256})
            model_uri = info.model_uri
    client.set_tag(search['run_id'],'star.model_uri',model_uri)
    return {'run_id':search['run_id'],'model_uri':model_uri,'sha256':data.sha256,'seed':data.seed}


def checked_predictions(model, frame):
    if list(getattr(model,'feature_names_in_',[])) != D2_FEATURES:
        raise ValueError('El esquema del modelo no corresponde a las nueve variables D2')
    values = np.asarray(model.predict(frame))
    if values.ndim != 1 or len(values) != len(frame) or not set(values).issubset(CLASSES):
        raise ValueError('Predicciones inválidas del modelo')
    return values


def evaluate_candidate(data, trained):
    import mlflow
    import mlflow.sklearn
    if trained['sha256'] != data.sha256:
        raise ValueError('El candidato pertenece a otro dataset')
    if trained['seed'] != data.seed:
        raise ValueError('El candidato pertenece a otro split de datos')
    model = mlflow.sklearn.load_model(trained['model_uri'])
    prediction = checked_predictions(model,data.X_test)
    metrics = {'test_accuracy':float(accuracy_score(data.y_test,prediction)),
               'test_precision_weighted':float(precision_score(data.y_test,prediction,average='weighted',zero_division=0)),
               'test_recall_weighted':float(recall_score(data.y_test,prediction,average='weighted',zero_division=0)),
               'test_f1_weighted':float(f1_score(data.y_test,prediction,average='weighted',zero_division=0)),
               'test_f1_macro':float(f1_score(data.y_test,prediction,average='macro',zero_division=0))}
    with mlflow.start_run(run_id=trained['run_id']):
        mlflow.log_metrics(metrics)
        mlflow.log_dict(classification_report(data.y_test,prediction,labels=CLASSES,output_dict=True,zero_division=0),
                        'evaluation/classification_report.json')
        # Figuras útiles tanto para la ejecución headless como para la notebook.
        import matplotlib.pyplot as plt
        from sklearn.metrics import ConfusionMatrixDisplay
        fig,ax=plt.subplots(figsize=(6,5))
        ConfusionMatrixDisplay.from_predictions(data.y_test,prediction,labels=CLASSES,ax=ax,cmap='Blues')
        fig.tight_layout();mlflow.log_figure(fig,'evaluation/confusion_matrix.png');plt.close(fig)
        fig,ax=plt.subplots(figsize=(8,6))
        image=ax.imshow(data.X_train.corr(),vmin=-1,vmax=1,cmap='coolwarm')
        ax.set_xticks(range(len(D2_FEATURES)),D2_FEATURES,rotation=45)
        ax.set_yticks(range(len(D2_FEATURES)),D2_FEATURES)
        fig.colorbar(image,ax=ax);fig.tight_layout()
        mlflow.log_figure(fig,'plots/correlation_d2.png');plt.close(fig)
    return {**trained,'metrics':metrics}


def register_candidate(evaluated, name=MODEL_NAME):
    import mlflow
    client=mlflow.MlflowClient()
    tags={'feature_set':'D2','training_run_id':evaluated['run_id'],
          'dataset_sha256':evaluated['sha256'],'star.model_uri':evaluated['model_uri'],
          'split_seed':str(evaluated['seed']),
          'test_f1_weighted':str(evaluated['metrics']['test_f1_weighted'])}
    token=None
    while True:
        versions=client.search_model_versions(f"name = '{name}'",max_results=1000,page_token=token)
        for item in versions:
            if item.run_id==evaluated['run_id'] and item.tags.get('star.model_uri')==evaluated['model_uri']:
                return {**evaluated,'name':name,'version':str(item.version)}
        token=versions.token
        if not token:break
    result=mlflow.register_model(evaluated['model_uri'],name,tags=tags,await_registration_for=300)
    return {**evaluated,'name':name,'version':str(result.version)}


def compare_and_promote(data, candidate, min_delta=0.0, *, client=None, loader=None):
    """Tarea final independiente: comparar en el mismo test y mover solo si mejora.

    La comparación y su hash se escriben ANTES del cambio de alias. Un problema
    de descarga o esquema se propaga sin modificar champion. No hay CAS en MLflow:
    no ejecutar otros promotores concurrentes sobre este alias.
    """
    import mlflow
    import mlflow.sklearn
    client=client if client is not None else mlflow.MlflowClient()
    loader=loader if loader is not None else mlflow.sklearn.load_model
    if candidate['sha256'] != data.sha256:
        raise ValueError('El candidato pertenece a otro dataset')
    if candidate['seed'] != data.seed:
        raise ValueError('El candidato pertenece a otro split de datos')
    if not math.isfinite(min_delta) or not 0 <= min_delta <= 1:
        raise ValueError('min_delta debe estar entre 0 y 1')
    name,version_id=candidate['name'],str(candidate['version'])
    previous=client.get_registered_model(name).aliases.get('champion')
    if previous is not None:previous=str(previous)
    if previous==version_id:
        marker=f'{version_id}|{data.sha256}'
        if client.get_run(candidate['run_id']).data.tags.get('star.promotion_audit')==marker:
            from pathlib import Path
            audit=Path(client.download_artifacts(candidate['run_id'],'promotion/comparison.json'))
            recovered=json.loads(audit.read_text('utf-8'))
            if (recovered.get('candidate_version')!=version_id or
                    recovered.get('sha256')!=data.sha256 or not recovered.get('promoted')):
                raise ValueError('La auditoría de promoción no coincide con el candidato')
            client.set_model_version_tag(name,version_id,'promotion_result',recovered['reason'])
            client.set_tag(candidate['run_id'],'promotion_result',recovered['reason'])
            return recovered
        return {'promoted':False,'reason':'already_champion','champion_version':version_id,
                'candidate_version':version_id,'sha256':data.sha256}
    predicted=checked_predictions(loader(f'models:/{name}/{version_id}'),data.X_test)
    new_f1=float(f1_score(data.y_test,predicted,average='weighted',zero_division=0))
    old_f1=None
    if previous is not None:
        old_prediction=checked_predictions(loader(f'models:/{name}/{previous}'),data.X_test)
        old_f1=float(f1_score(data.y_test,old_prediction,average='weighted',zero_division=0))
    improve=old_f1 is None or new_f1 > old_f1+min_delta
    result={'promoted':improve,'reason':'first_champion' if old_f1 is None else ('improved' if improve else 'not_improved'),
            'candidate_version':version_id,'previous_champion_version':previous,
            'champion_version':version_id if improve else previous,
            'candidate_f1_weighted':new_f1,'champion_f1_weighted':old_f1,
            'min_delta':min_delta,'sha256':data.sha256,'seed':data.seed,'test_rows':len(data.X_test)}
    # ID de test documentado incluso si el champion proviene de otro snapshot.
    if hasattr(data,'test_objids'):
        result['test_objids_sha256']=hashlib.sha256('\n'.join(data.test_objids).encode()).hexdigest()
    client.log_dict(candidate['run_id'],result,'promotion/comparison.json')
    client.log_metric(candidate['run_id'],'promotion_candidate_f1_weighted',new_f1)
    if old_f1 is not None:client.log_metric(candidate['run_id'],'promotion_champion_f1_weighted',old_f1)
    if improve:
        current=client.get_registered_model(name).aliases.get('champion')
        if (None if current is None else str(current)) != previous:
            raise RuntimeError('El alias champion cambió durante la comparación; reintentar la tarea')
        client.set_tag(candidate['run_id'],'star.promotion_audit',f'{version_id}|{data.sha256}')
        client.set_registered_model_alias(name,'champion',version_id)
    client.set_model_version_tag(name,version_id,'promotion_result',result['reason'])
    client.set_tag(candidate['run_id'],'promotion_result',result['reason'])
    return result
