"""Ingesta manual SDSS DR17 -> MinIO y tracking en MLflow."""
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag
from airflow.providers.standard.decorators.python import python_task as task
from star_sdss_source import SQL, SDSS_ENDPOINT, fetch_csv


@dag(
    dag_id='process_etl_star_data',
    description='Consulta SDSS DR17 y guarda starset.csv; experimento star type',
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=None, catchup=False, max_active_runs=1,
    default_args={'owner': 'rmb', 'retries': 2, 'retry_delay': timedelta(minutes=2)},
    tags=['ETL', 'SDSS', 'star type'],
    doc_md='''Descarga hasta 1000 objetos aleatorios con ORDER BY NEWID() en cada consulta.
Guarda `s3://data/raw/star/starset.csv` y una copia por hash para trazabilidad.
Registra la ingesta en MLflow `star type`. La preparación D2 y el entrenamiento
se ejecutan con `train_star_model` o desde `notebooks/experiment_star_mlflow.ipynb`.
No modifica el dataset ni los modelos de Heart Disease.''',
)
def process_etl_star_data():
    @task(execution_timeout=timedelta(minutes=15))
    def fetch_and_store_starset():
        import hashlib
        import os
        import boto3
        import mlflow
        from airflow.operators.python import get_current_context

        payload, rows = fetch_csv()
        sha = hashlib.sha256(payload).hexdigest()
        bucket, key = 'data', 'raw/star/starset.csv'
        snapshot = f'raw/star/snapshots/{sha}.csv'
        s3 = boto3.client('s3', endpoint_url=os.getenv('AWS_ENDPOINT_URL_S3', 'http://s3:9000'))
        # El bucket data lo crea el servicio create_s3_buckets del Compose.
        for destination in [snapshot, key]:
            s3.put_object(Bucket=bucket, Key=destination, Body=payload,
                          ContentType='text/csv', Metadata={'sha256': sha})
        mlflow.set_tracking_uri('http://mlflow:5000')
        mlflow.set_experiment('star type')
        context = get_current_context()
        with mlflow.start_run(run_name=f"ingest_star_{context['run_id']}") as run:
            mlflow.set_tags({'stage': 'ingestion', 'source': 'SDSS DR17',
                             'airflow.run_id': context['run_id'], 'dataset.sha256': sha})
            mlflow.log_params({'dataset_uri': f's3://{bucket}/{key}',
                               'snapshot_uri': f's3://{bucket}/{snapshot}',
                               'source_url': SDSS_ENDPOINT, 'query_limit': 1000,
                               'sampling_method': 'random_order_by_newid'})
            mlflow.log_metric('raw_rows', rows)
            mlflow.log_text(SQL, 'source/query.sql')
            mlflow.log_text(payload.decode('utf-8'), 'source/starset.csv')
            return {'run_id': run.info.run_id, 'rows': rows, 'sha256': sha,
                    'dataset_uri': f's3://{bucket}/{key}'}

    fetch_and_store_starset()


dag = process_etl_star_data()
