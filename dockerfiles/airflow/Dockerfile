FROM apache/airflow:3.0.2
COPY requirements.txt /requirements.txt

USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
         git \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt /requirements.txt

RUN --mount=type=secret,id=pip_ca,mode=0444,required=false \
    set -eu; \
    if [ -s /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --upgrade pip; \
    pip install --no-cache-dir apache-airflow[virtualenv]==3.0.2 -r /requirements.txt
