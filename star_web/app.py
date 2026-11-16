"""Web local y API estelar. Iniciar con start.ps1."""
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, StrictFloat, StrictInt

from core import BANDS, FEATURES, SDSS_URL, SQL, parse_objects, validate_features

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
load_dotenv(REPO / '.env', override=False)
log = logging.getLogger('star_web')
_source_lock = threading.Lock()
_model_lock = threading.Lock()
_source_cache = None
_source_time = 0
_model_cache = None
_model_time = 0


def fetch_objects(refresh=False):
    global _source_cache, _source_time
    if not refresh and _source_cache is not None and time.monotonic()-_source_time < 3600:
        return _source_cache
    if not _source_lock.acquire(blocking=False):
        raise HTTPException(503, 'Ya hay una consulta a SDSS en curso. Esperá y volvé a cargar.')
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        ca = Path(os.getenv('STAR_SDSS_CA_BUNDLE', str(REPO / 'airflow/config/sdss-ca-bundle.pem')))
        with requests.Session() as session:
            session.mount('https://', HTTPAdapter(max_retries=Retry(
                total=2, backoff_factor=1, status_forcelist=[429, 502, 503, 504])))
            response = session.get(SDSS_URL, params={'cmd':SQL, 'format':'csv'},
                                   timeout=(15, 180), verify=str(ca) if ca.is_file() else True)
            response.raise_for_status()
        data = parse_objects(response.text)
        data['fetched_at'] = datetime.now(timezone.utc).isoformat()
        data['query'] = SQL
        _source_cache, _source_time = data, time.monotonic()
        return data
    except HTTPException:
        raise
    except Exception:
        log.exception('Falló la consulta SDSS')
        raise HTTPException(502, 'No se pudo consultar SDSS. Revisá la conexión y reintentá.') from None
    finally:
        _source_lock.release()


def load_champion():
    global _model_cache, _model_time
    with _model_lock:
        if _model_cache is not None and time.monotonic()-_model_time < 60:
            return _model_cache
        import mlflow
        import mlflow.sklearn
        if mlflow.__version__ != '3.16.1':
            raise RuntimeError('Se requiere MLflow 3.16.1. Usar start.ps1 o requirements.txt.')
        os.environ.setdefault('AWS_ACCESS_KEY_ID', os.getenv('MINIO_ACCESS_KEY', 'minio'))
        os.environ.setdefault('AWS_SECRET_ACCESS_KEY', os.getenv('MINIO_SECRET_ACCESS_KEY', 'minio123'))
        os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
        os.environ['MLFLOW_S3_ENDPOINT_URL'] = os.getenv('STAR_S3_ENDPOINT', 'http://127.0.0.1:9000')
        os.environ.setdefault('MLFLOW_HTTP_REQUEST_TIMEOUT', '30')
        os.environ.setdefault('MLFLOW_HTTP_REQUEST_MAX_RETRIES', '2')
        mlflow.set_tracking_uri(os.getenv('STAR_MLFLOW_URI', 'http://127.0.0.1:5001'))
        name = 'star_type_model_prod'
        version = mlflow.MlflowClient().get_model_version_by_alias(name, 'champion').version
        model = mlflow.sklearn.load_model(f'models:/{name}/{version}')
        if list(getattr(model, 'feature_names_in_', [])) != FEATURES:
            raise RuntimeError('El champion no tiene el esquema D2 de nueve columnas esperado.')
        _model_cache = (model, str(version))
        _model_time = time.monotonic()
        return _model_cache


def predict_features(features):
    try:
        import pandas as pd
        model, version = load_champion()
        frame = pd.DataFrame([features], columns=FEATURES)
        label = str(model.predict(frame)[0])
        if label not in {'STAR', 'GALAXY', 'QSO'}:
            raise RuntimeError('El modelo devolvió una clase inesperada.')
        return {'prediction':label, 'model_name':'star_type_model_prod',
                'model_version':version, 'alias':'champion'}
    except Exception:
        log.exception('Falló la predicción estelar')
        raise HTTPException(503, 'No se pudo predecir. Comprobá que MLflow y MinIO estén disponibles '
                            'y que exista star_type_model_prod@champion.') from None


class PredictInput(BaseModel):
    features: dict[str, StrictFloat | StrictInt]


def create_app(source=None, predictor=None):
    api = FastAPI(title='Clasificación estelar', version='1.0')
    source = source or fetch_objects
    predictor = predictor or predict_features

    @api.get('/', include_in_schema=False)
    def index():
        return FileResponse(ROOT / 'index.html', headers={
            'Cache-Control': 'no-store, no-cache, must-revalidate',
            'Pragma': 'no-cache', 'Expires': '0',
        })

    @api.get('/api/objects')
    def objects(refresh: bool = False):
        return source(refresh)

    @api.post('/api/predict')
    def predict(body: PredictInput):
        try:
            features = validate_features(body.features)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return predictor(features)

    return api


app = create_app()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('STAR_WEB_PORT', '8801')))
