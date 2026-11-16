"""Compatibilidad: las implementaciones viven en el paquete compartido star_training."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'airflow/dags'))
from star_training.features import (BANDS,COLORS,D2_FEATURES,CLASSES,prepare_d2,make_pipeline)

__all__=['BANDS','COLORS','D2_FEATURES','CLASSES','prepare_d2','make_pipeline']
