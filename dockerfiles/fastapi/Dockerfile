FROM python:3.12-slim

WORKDIR /app
COPY . .
COPY requirements.txt /requirements.txt

RUN apt-get update && apt-get install -y curl
RUN --mount=type=secret,id=pip_ca,mode=0444,required=false \
    set -eu; \
    if [ -s /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --upgrade pip; \
    pip install --no-cache-dir -r /requirements.txt

EXPOSE 8800