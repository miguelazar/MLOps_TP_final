"""Ingesta manual SDSS DR17 -> MinIO y tracking en MLflow."""
import logging
from datetime import datetime, timedelta, timezone

from airflow.decorators import dag
from airflow.providers.standard.decorators.branch_python import branch_task
from airflow.providers.standard.decorators.python import python_task as task
from airflow.sdk import Param
from star_sdss_source import (SQL, SDSS_ENDPOINT, count_classes, fetch_csv,
                              smallest_class_rows)

log = logging.getLogger(__name__)
MAX_DOWNLOADS = 3  # descargas en total, contando la primera


@dag(
    dag_id='process_etl_star_data',
    description='Consulta SDSS DR17 y guarda starset.csv; experimento star type',
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=None, catchup=False, max_active_runs=1,
    default_args={'owner': 'rmb', 'retries': 2, 'retry_delay': timedelta(minutes=2)},
    params={
        'min_rows_per_class': Param(
            30, type='integer', minimum=0, maximum=100000,
            description='Mínimo de filas por clase (GALAXY, QSO, STAR). Si la muestra '
                        'no lo alcanza se descarga de nuevo, hasta 3 descargas en total. '
                        'Usar 9999 para probar el camino de remuestreo'),
    },
    tags=['ETL', 'SDSS', 'star type'],
    doc_md='''Descarga hasta 1000 objetos aleatorios con ORDER BY NEWID() en cada consulta.
`revisar_clases` cuenta las filas por clase y las compara con `min_rows_per_class`.
Si alcanzan, va directo a `guardar_snapshot`. Si no, `remuestrear` descarga otra
muestra aleatoria (hasta 3 descargas en total) y conserva la que tenga más filas en
su clase más escasa. Si ninguna alcanza el mínimo, avisa en el log y guarda igual la mejor.
Guarda `s3://data/raw/star/starset.csv` y una copia por hash para trazabilidad.
Registra la ingesta en MLflow `star type`. La preparación D2 y el entrenamiento
se ejecutan con `train_star_model` o desde `notebooks/experiment_star_mlflow.ipynb`.
No modifica el dataset ni los modelos de Heart Disease.''',
)
def process_etl_star_data():
    def as_sample(payload, rows):
        # XCom no admite bytes: la muestra viaja como texto CSV (UTF-8 sin pérdida).
        return {'csv': payload.decode('utf-8'), 'rows': rows}

    @task(execution_timeout=timedelta(minutes=15))
    def descargar_muestra():
        return as_sample(*fetch_csv())

    @branch_task
    def revisar_clases(muestra, params=None):
        minimum = int(params['min_rows_per_class'])
        counts = count_classes(muestra['csv'])
        smallest = smallest_class_rows(counts)
        log.info('Filas por clase: %s; clase más escasa: %s; mínimo: %s',
                 counts, smallest, minimum)
        return 'guardar_snapshot' if smallest >= minimum else 'remuestrear'

    @task(execution_timeout=timedelta(minutes=30))
    def remuestrear(muestra, params=None):
        minimum = int(params['min_rows_per_class'])
        best = muestra
        best_counts = count_classes(muestra['csv'])
        best_smallest = smallest_class_rows(best_counts)
        for attempt in range(2, MAX_DOWNLOADS + 1):
            candidate = as_sample(*fetch_csv())
            counts = count_classes(candidate['csv'])
            smallest = smallest_class_rows(counts)
            log.info('Descarga %s de %s: filas por clase %s; clase más escasa: %s',
                     attempt, MAX_DOWNLOADS, counts, smallest)
            if smallest > best_smallest:  # en empate se conserva la anterior
                best, best_counts, best_smallest = candidate, counts, smallest
            if best_smallest >= minimum:
                break
        if best_smallest < minimum:
            log.warning('Ninguna de las muestras alcanzó el mínimo de %s filas por clase. '
                        'Se guarda la mejor igualmente. Filas por clase: %s',
                        minimum, best_counts)
        else:
            log.info('Muestra elegida con filas por clase %s', best_counts)
        return best

    # Si remuestrear fue omitida (camino directo), su resultado llega como None.
    @task(execution_timeout=timedelta(minutes=15),
          trigger_rule='none_failed_min_one_success')
    def guardar_snapshot(muestra, remuestreada=None):
        import hashlib
        import os
        import boto3
        import mlflow
        from airflow.operators.python import get_current_context

        chosen = remuestreada or muestra
        payload, rows = chosen['csv'].encode('utf-8'), chosen['rows']
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

    muestra = descargar_muestra()
    decision = revisar_clases(muestra)
    mejor = remuestrear(muestra)
    guardado = guardar_snapshot(muestra, mejor)
    decision >> [mejor, guardado]


dag = process_etl_star_data()
