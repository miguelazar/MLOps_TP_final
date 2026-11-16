"""Persistencia de etapas del DAG. Solo referencias JSON viajan por XCom."""
import hashlib
import json
import os
import re


def runtime():
    import boto3
    from .workflow import configure_tracking
    endpoint=os.getenv('AWS_ENDPOINT_URL_S3','http://s3:9000')
    client=configure_tracking(os.getenv('STAR_MLFLOW_URI','http://mlflow:5000'),endpoint)
    return boto3.client('s3',endpoint_url=endpoint),client


def read_json(s3, key):
    from botocore.exceptions import ClientError
    try:
        return json.loads(s3.get_object(Bucket='data',Key=key)['Body'].read())
    except ClientError as exc:
        if exc.response['Error']['Code'] in {'NoSuchKey','404','NotFound'}:
            return None
        raise


def write_json(s3, key, value):
    s3.put_object(Bucket='data',Key=key,Body=json.dumps(value,allow_nan=False).encode(),
                  ContentType='application/json')


def resolve_snapshot(execution_id, config):
    import mlflow
    from .workflow import EXPERIMENT_NAME,read_snapshot
    s3,client=runtime()
    prefix='training/star/'+hashlib.sha256(execution_id.encode()).hexdigest()
    key=prefix+'/snapshot.json'
    cached=read_json(s3,key)
    if cached is not None:
        if cached['config'] != config:
            raise ValueError('La ejecución ya tiene otros parámetros; crear una ejecución nueva')
        read_snapshot(s3,cached['snapshot'])
        return cached
    sha=config['snapshot_sha256']
    ingestion_run_id=None
    if not sha:
        experiment=client.get_experiment_by_name(EXPERIMENT_NAME)
        if experiment is None:
            raise ValueError('Ejecutar primero process_etl_star_data: falta el experimento star type')
        runs=mlflow.search_runs(experiment_ids=[experiment.experiment_id],
                               filter_string="tags.stage = 'ingestion' AND attributes.status = 'FINISHED'",
                               order_by=['attributes.start_time DESC'],max_results=1)
        if runs.empty:
            raise ValueError('No hay ingestas exitosas; ejecutar process_etl_star_data')
        sha=runs.iloc[0]['tags.dataset.sha256']
        ingestion_run_id=runs.iloc[0]['run_id']
    if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{64}',sha):
        raise ValueError('snapshot_sha256 debe contener un SHA-256 hexadecimal válido')
    snapshot={'bucket':'data','key':f'raw/star/snapshots/{sha}.csv',
              'sha256':sha,'ingestion_run_id':ingestion_run_id}
    read_snapshot(s3,snapshot)
    result={'prefix':prefix,'snapshot':snapshot,'config':config}
    write_json(s3,key,result)
    return result


def prepared(reference, s3):
    from .workflow import prepare_data,read_snapshot
    return prepare_data(read_snapshot(s3,reference['snapshot']),seed=reference['config']['seed'])


def stage(reference, name, compute):
    s3,client=runtime()
    key=f"{reference['prefix']}/{name}.json"
    cached=read_json(s3,key)
    if cached is not None:
        return cached
    result=compute(s3,client)
    write_json(s3,key,result)
    return result


def search_stage(reference):
    from .workflow import create_training_run,search_hyperparameters
    def compute(s3,client):
        data=prepared(reference,s3)
        key=reference['prefix']+'/parent_run.json'
        parent=read_json(s3,key)
        if parent is None:
            parent={'run_id':create_training_run(reference['snapshot'],reference['config']['n_trials'],
                                                 reference['config']['seed'],reference['prefix'])}
            write_json(s3,key,parent)
        return search_hyperparameters(data,reference['snapshot'],
                                       n_trials=reference['config']['n_trials'],run_id=parent['run_id'])
    return stage(reference,'search',compute)


def train_stage(reference, search):
    from .workflow import train_and_log_model
    return stage(reference,'trained',lambda s3,client:train_and_log_model(prepared(reference,s3),search))


def evaluation_stage(reference, trained):
    from .workflow import evaluate_candidate
    return stage(reference,'evaluated',lambda s3,client:evaluate_candidate(prepared(reference,s3),trained))


def registration_stage(reference, evaluated):
    from .workflow import register_candidate
    return stage(reference,'registered',lambda s3,client:register_candidate(evaluated))


def promotion_stage(reference, candidate):
    from .workflow import compare_and_promote
    return stage(reference,'promotion',lambda s3,client:compare_and_promote(
        prepared(reference,s3),candidate,min_delta=reference['config']['min_delta'],client=client))
