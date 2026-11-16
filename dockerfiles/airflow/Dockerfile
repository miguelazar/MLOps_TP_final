FROM apache/airflow:3.0.2

USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends git \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt /requirements.txt
RUN --mount=type=secret,id=pip_ca,mode=0444,required=false \
    set -eu; \
    if [ -s /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --upgrade pip; \
    pip install --no-cache-dir apache-airflow[virtualenv]==3.0.2 -r /requirements.txt; \
    pip check

# Entorno preinstalado: las tareas no descargan dependencias al ejecutarse.
# Su pandas/numpy no alteran los proveedores de Google/Snowflake de Airflow.
COPY requirements-training.txt /requirements-training.txt
RUN --mount=type=secret,id=pip_ca,mode=0444,required=false \
    set -eu; \
    if [ -s /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    python -m venv /home/airflow/star-venv; \
    /home/airflow/star-venv/bin/python -m pip install --upgrade pip; \
    /home/airflow/star-venv/bin/python -m pip install --no-cache-dir -r /requirements-training.txt; \
    /home/airflow/star-venv/bin/python -m pip check
