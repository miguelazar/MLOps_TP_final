# Clasificación estelar: instalación y ejecución desde un clon nuevo

Esta guía corresponde al flujo **SDSS → MinIO → notebook/Optuna → MLflow → web**
de `MLOps_TP_final`. Los comandos están escritos para **Windows y PowerShell** y
se ejecutan desde la raíz del repositorio, en la carpeta donde se haya clonado o
extraído. No requieren la ruta del autor, Anaconda ni el repositorio original.

El clon contiene código y configuración. Cada usuario genera sus datos,
experimentos y modelo `champion`; no recibe los volúmenes Docker de otro equipo.
Compose levanta la infraestructura. La notebook y la web se ejecutan por separado
en Windows, siguiendo los pasos 3 y 4.

## 1. Requisitos y arranque

- Docker Desktop iniciado, usando contenedores Linux y Docker Compose moderno
  (`docker compose`, versión 2.14 o posterior).
- Python de 64 bits, versión 3.11, 3.12 o 3.13; se recomienda 3.12.
- VS Code con las extensiones Python/Jupyter, o JupyterLab para abrir la notebook.
- Acceso a Docker Hub, PyPI y `skyserver.sdss.org`.
- Al menos 4 GB disponibles para Docker; es preferible asignar 8 GB si el equipo
  lo permite. Airflow, el build y el entrenamiento pueden tardar varios minutos.
  Véanse los [requisitos de Airflow 3.0.2](https://airflow.apache.org/docs/apache-airflow/3.0.2/howto/docker-compose/index.html).

Comprobar Docker y Python:

```powershell
docker version
docker compose version
python --version
```

`docker version` debe mostrar **Client y Server**. Si `python` no apunta a una
versión compatible, usar el lanzador de Windows `py -3.12` en los comandos de
creación de entornos que siguen.

Preparar la configuración sin sobrescribir una existente y levantar servicios:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose --profile airflow --profile mlflow config --quiet
docker compose --profile airflow --profile mlflow up -d --build
docker compose --profile airflow --profile mlflow ps -a
```

Este repositorio también conserva un `.env` del ejemplo. Revisarlo antes del primer
arranque; `.env.example` documenta los valores para este flujo. Conservar los
nombres de buckets `data` y `mlflow`: el DAG y la notebook usan `data` de forma
explícita. La guía asume los puertos y las credenciales predeterminados.

Esperar que los servicios persistentes estén `healthy`, incluido `airflow-worker`.
`health: starting` durante el arranque no significa que hayan fallado.
`airflow-init` y `create_s3_buckets` son tareas de inicialización: es normal que
terminen como `Exited (0)`. Además, confirmar en MinIO que existen ambos buckets;
el código de salida del inicializador por sí solo no confirma su creación.

| Servicio | Dirección desde Windows | Acceso predeterminado |
|---|---|---|
| Airflow | [http://localhost:8080](http://localhost:8080) | `airflow` / `airflow` |
| MLflow | [http://localhost:5001](http://localhost:5001) | Sin login en esta configuración local |
| MinIO, consola | [http://localhost:9001](http://localhost:9001) | `minio` / `minio123` |
| MinIO, API S3 | `http://localhost:9000` | Las mismas credenciales MinIO |
| Web estelar, después del paso 4 | [http://localhost:8801](http://localhost:8801) | Sin login local |

Los valores son para desarrollo local. Si se cambian credenciales o puertos,
actualizar también los clientes. Las credenciales de Airflow se crean en la
inicialización; editar `.env` no cambia automáticamente usuarios ya existentes.

Dentro de Docker se usan `http://mlflow:5000` y `http://s3:9000`; desde Windows se
usan los puertos publicados de la tabla. `localhost` dentro de un contenedor
designa ese mismo contenedor.

Si otro clon usa los contenedores `postgres`, `minio`, `mlflow` o
`airflow-apiserver`, detenerlo desde su propia carpeta antes de arrancar este.
Cambiar solo el nombre de la carpeta no evita los conflictos de nombres y puertos.
El perfil `all` incluye además la API del ejemplo Heart Disease en 8800, que no
interviene en el flujo estelar. Usar los perfiles indicados arriba.

## 2. Obtener los datos con el DAG

En Airflow, iniciar sesión, buscar **`process_etl_star_data`**, habilitarlo y usar
**Trigger DAG**. Esperar el estado **Success** de su tarea `fetch_and_store_starset`.
El DAG es manual: no se ejecuta automáticamente al levantar Compose.

El archivo `airflow/dags/etl_star_data.py` aparece en Airflow porque Compose monta
la carpeta `airflow/dags`. No es necesario copiarlo desde la interfaz. Si no aparece:

```powershell
docker compose --profile airflow --profile mlflow exec airflow-scheduler airflow dags list-import-errors
docker compose --profile airflow --profile mlflow logs --tail 100 airflow-dag-processor
```

El DAG consulta SDSS DR17 mediante la API SQL, une `PhotoObj` y `SpecObj`, filtra
`scienceprimary = 1` y toma hasta 1000 filas ordenadas por `objid`. Guarda:

- CSV original validado: `s3://data/raw/star/starset.csv`.
- Copia identificada por hash: `s3://data/raw/star/snapshots/<sha256>.csv`.
- Experimento **`star type`** en MLflow y un run de ingesta con el hash y la consulta.

Confirmar esos resultados en MinIO y MLflow antes de entrenar. El ID numérico del
experimento puede variar entre equipos: el código lo busca por su nombre.
El DAG realiza la ingesta; la búsqueda y el entrenamiento se ejecutan en la notebook.

## 3. Preparar el kernel y ejecutar la notebook

Crear un entorno aislado, usando un Python compatible:

```powershell
python -m venv .venv-star
.\.venv-star\Scripts\python.exe -m pip install -r .\notebook_example\requirements_star.txt
.\.venv-star\Scripts\python.exe -m ipykernel install --user --name mlops-star --display-name "Python (MLOps star)"
```

Si se usa el lanzador de Windows, el primer comando puede ser
`py -3.12 -m venv .venv-star`. No hace falta activar el entorno.
El [registro del kernel](https://ipython.readthedocs.io/en/stable/install/kernel_install.html)
permite seleccionarlo desde un Jupyter instalado en otro entorno.

En VS Code, abrir `notebook_example/experiment_star_mlflow.ipynb` y seleccionar
**Python (MLOps star)** o el intérprete `.venv-star/Scripts/python.exe` como kernel.
Para usar JupyterLab si no se tiene instalado:

```powershell
.\.venv-star\Scripts\python.exe -m pip install jupyterlab
.\.venv-star\Scripts\python.exe -m jupyterlab
```

Seleccionar ese kernel al abrir la notebook. Iniciar Jupyter desde la raíz del
repo o desde `notebook_example`, ubicaciones que admite la importación del auxiliar.
Después de instalar o cambiar paquetes, reiniciar el kernel y ejecutar las celdas
en orden. Se requieren **MLflow 3.16.1 y scikit-learn 1.7.2**, como especifican los
archivos de dependencias de notebook y web.

### Configuración de la notebook

Con los valores predeterminados no hace falta editar nada. La notebook **no carga
el `.env` automáticamente**: usa sus valores predeterminados y las variables del
proceso de Jupyter. La web sí carga `.env`.

Si se cambiaron puertos o credenciales, agregar antes de la celda de configuración
una celda como la siguiente, con los valores correspondientes:

```python
import os
os.environ["STAR_MLFLOW_URI"] = "http://127.0.0.1:5001"
os.environ["STAR_S3_ENDPOINT"] = "http://127.0.0.1:9000"
os.environ["AWS_ACCESS_KEY_ID"] = "minio"
os.environ["AWS_SECRET_ACCESS_KEY"] = "minio123"
```

Las variables AWS ya definidas en el proceso prevalecen sobre los valores por
defecto de la notebook. Usar las credenciales de este MinIO; no guardar credenciales
personales en la notebook que se publique.

### Entrenamiento y publicación

La notebook limpia los datos y construye nueve entradas:
`u, g, r, i, z, u-g, g-r, r-i, i-z`. No usa `redshift`, coordenadas ni `objid` como
predictores. Separa 80/20 de forma estratificada y prueba 250 combinaciones con
Optuna, validación cruzada de cinco folds y F1 ponderado. Cada Pipeline ajusta el
scaler dentro del fold; los datos raw no se sobrescriben.

Luego guarda el Pipeline, evalúa sobre test, verifica que el modelo recargado
prediga lo mismo y registra una versión de **`star_type_model_prod`**, asignándole
el alias **`champion`**. Ejecutar también la última celda de inferencia para
confirmar que el alias puede cargarse.

Para una prueba breve de instalación, antes de la celda de configuración:

```python
os.environ["STAR_N_TRIALS"] = "5"
```

Esa prueba también publica su modelo si se ejecuta la celda de registro. Para la
búsqueda completa, quitar esa variable y ejecutar una nueva búsqueda con 250 trials.
Cada búsqueda crea un run padre nuevo; cada registro crea una versión nueva. El
alias se mueve al modelo recién registrado sin comparar automáticamente con el
champion anterior. La muestra TOP 1000 no es aleatoria: sus métricas no describen
por sí solas todo SDSS.

Si falla **solo la recarga** `mlflow.sklearn.load_model(model_uri)` por conexión,
comprobar MinIO y reintentar esa misma celda, manteniendo el kernel. Si falla el
guardado, reintentar la celda de entrenamiento/guardado. No hace falta repetir
Optuna mientras `study`, los datos y el run padre sigan en memoria. Si se reinicia
el kernel, esas variables se pierden. Repetir la celda de registro puede crear
otra versión; comprobar MLflow antes de reintentarlo.

## 4. Iniciar la web y predecir

Con MLflow, MinIO y `star_type_model_prod@champion` disponibles, ejecutar:

```powershell
.\iniciar-web.ps1
```

El script detecta un Python compatible, crea `.venv-star-web`, instala sus propias
dependencias y arranca la web en [http://localhost:8801](http://localhost:8801).
No requiere Anaconda ni activa el entorno de la notebook. Mantener esa terminal
abierta; **Ctrl+C** detiene la web.

Si Windows no permite ejecutar `.ps1`, no es necesario cambiar su política:

```powershell
python -m venv .venv-star-web
.\.venv-star-web\Scripts\python.exe -m pip install -r .\star_web\requirements.txt
.\.venv-star-web\Scripts\python.exe .\star_web\app.py
```

Para usar otro puerto, establecer antes de iniciar:

```powershell
$env:STAR_WEB_PORT = "8802"
```

La web consulta hasta 10000 objetos de SDSS. Cargar la lista, seleccionar un
`objid` y pulsar **Predecir tipo de objeto**. Envía bandas y colores sin escalar a
`POST /api/predict`; el Pipeline aplica el scaler. Después de predecir, compara
el resultado con la clase SDSS, oculta previamente en la pantalla.
La etiqueta visible es **Modelo de predicción**. La referencia SDSS viaja en los
datos de la página para esa comparación; no es un dato secreto.

La documentación de esta API está en [http://localhost:8801/docs](http://localhost:8801/docs).
La API de 8800 pertenece al ejemplo Heart Disease. La consulta web se cachea una
hora y el modelo un minuto; una actualización de `champion` puede tardar ese
minuto en reflejarse. Los objetos de la web pueden incluir datos de entrenamiento;
la comparación visual no es una evaluación independiente del modelo.

## 5. Certificados: solo si la red los requiere

En una conexión normal no hay pasos adicionales. Si aparece
`CERTIFICATE_VERIFY_FAILED`, un antivirus o proxy podría inspeccionar HTTPS.
No desactivar la validación TLS ni usar `--trusted-host` para resolverlo.

### Build de Docker

Desde PowerShell, ejecutar una vez en ese equipo:

```powershell
.\preparar-ca.ps1
docker compose --profile airflow --profile mlflow up -d --build
```

El script valida con Windows las cadenas de PyPI, sus descargas y SDSS; exporta
solo CAs públicas a `airflow/config/pip-ca-bundle.pem` y crea un
`docker-compose.override.yaml` local que Compose carga automáticamente. La CA se
entrega a pip como secreto temporal de BuildKit; no se copia a las imágenes.
En los siguientes arranques se usa el mismo Compose, sin repetir el script salvo
que cambie o venza la CA. No compartir el bundle ni el override entre equipos.

Si el script encuentra un override propio, lo conserva y se detiene. Si Windows
no valida la cadena, solicitar al administrador un bundle válido. Para usar un
bundle que ya proporciona la organización, la alternativa explícita es:

```powershell
$env:STAR_PIP_CA_BUNDLE = 'C:/certificados/ca-validada.pem'
docker compose -f docker-compose.yaml -f docker-compose.ca.yaml --profile airflow --profile mlflow up -d --build
```

Con esta alternativa conservar ambos `-f` en futuras construcciones. Usar solo
`-f docker-compose.yaml` omite el override automático. Véanse las referencias de
[combinación de archivos Compose](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/)
y [secretos de build](https://docs.docker.com/build/building/secrets/).

### Consultas SDSS y pip de Windows

El secreto del build **no configura HTTPS en tiempo de ejecución**. Si también
falla SDSS y se generó el bundle validado con el script anterior:

```powershell
if (-not (Test-Path .\airflow\config\sdss-ca-bundle.pem)) {
    Copy-Item .\airflow\config\pip-ca-bundle.pem .\airflow\config\sdss-ca-bundle.pem
}
```

El DAG y la web detectan ese archivo por defecto. La carpeta `airflow/config` está
montada en los contenedores; reintentar la tarea fallida o la consulta web. Si ya
hay un bundle propio para SDSS, conservarlo y validar cuál corresponde antes de
reemplazarlo. La notebook descarga desde MinIO local y no consulta SDSS directamente.

Si falla pip al instalar el entorno Windows, establecer en esa terminal antes de
repetir la instalación:

```powershell
$env:PIP_CERT = (Resolve-Path .\airflow\config\pip-ca-bundle.pem).Path
```

Estos archivos son locales, públicos y están excluidos de Git. No contienen claves
privadas ni modifican el almacén de confianza del sistema. Si la política impide
ejecutar el exportador, usar un bundle validado entregado por el administrador.

## 6. Diagnóstico, parada y próximos arranques

Para revisar servicios y sus últimos logs:

```powershell
docker compose --profile airflow --profile mlflow ps -a
docker compose --profile airflow --profile mlflow logs --tail 100 airflow-worker airflow-scheduler airflow-apiserver mlflow s3
```

Una descarga de artefactos fallida no implica que se haya perdido el modelo:
comprobar primero MLflow y MinIO. Para verificar HTTP desde PowerShell:

```powershell
Invoke-WebRequest http://localhost:5001/health -UseBasicParsing
Invoke-WebRequest http://localhost:9000/minio/health/live -UseBasicParsing
```

Si falta el bucket `data`, revisar los logs de `create_s3_buckets`; con MinIO
disponible, volver a ejecutar el inicializador y confirmar los buckets en la consola:

```powershell
docker compose --profile airflow --profile mlflow run --rm create_s3_buckets
```

Para detener los servicios conservando los datos:

```powershell
docker compose --profile airflow --profile mlflow down
```

No agregar `-v`: elimina los volúmenes con bases y artefactos. Los experimentos,
versiones y metadatos están en PostgreSQL; los CSV y archivos de modelos, en MinIO.
Se necesitan ambos para recuperar el flujo. Cerrar la web aparte con Ctrl+C.
Para volver a arrancar, ejecutar el mismo `up -d --build`; no es necesario repetir
el DAG ni el entrenamiento si los datos y el champion siguen guardados.

## 7. Archivos que deben estar publicados en el repositorio

Antes de compartir el enlace de clonación, comprobar `git status --short` y que
el commit publicado incluya los siguientes componentes, además del Compose y los
Dockerfiles actualizados:

| Componente | Ubicación |
|---|---|
| Guía principal y configuración de ejemplo | `STAR_SETUP.md`, `.env.example` |
| DAG y consulta SDSS | `airflow/dags/etl_star_data.py`, `airflow/dags/star_sdss_source.py` |
| Notebook, auxiliares y dependencias | `notebook_example/experiment_star_mlflow.ipynb`, `star_workflow.py`, `requirements_star.txt`, `STAR_WORKFLOW.md` en esa misma carpeta |
| Web y su lanzador | `star_web/`, `iniciar-web.ps1` |
| Configuración opcional de CA | `preparar-ca.ps1`, `docker-compose.ca.yaml`, `.gitignore` actualizado |
| Pruebas | `tests/test_star_workflow.py`, `tests/test_star_web.py` |

Los archivos marcados `??` aún no están incluidos en un commit. Una edición local
no estará disponible para otras personas hasta que se publique. No incluir los
entornos `.venv-star*`, certificados locales, el override generado, volúmenes ni
credenciales personales. El `.env` del ejemplo ya está versionado: revisar que sus
valores publicados sigan siendo únicamente los de desarrollo.

### Verificación opcional para colaboradores

Con el entorno de notebook preparado, instalar también las dependencias de web
y `httpx` en un entorno de comprobación compatible y ejecutar:

```powershell
.\.venv-star\Scripts\python.exe -m pip install -r .\star_web\requirements.txt httpx
.\.venv-star\Scripts\python.exe -m unittest discover -s tests -p 'test_star*.py'
docker compose --profile airflow --profile mlflow config --quiet
```

Las pruebas no disparan el DAG ni entrenan el champion. La validación completa de
un despliegue nuevo requiere, además, completar los pasos 2, 3 y 4 con sus propios
datos y confirmar una predicción en la web.
