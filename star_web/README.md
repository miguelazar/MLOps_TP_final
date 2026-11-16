# Web mínima de clasificación estelar

Abrir `http://localhost:8801` después de iniciar la app. MLflow, MinIO y el
modelo `star_type_model_prod@champion` deben estar disponibles en el Compose existente.

Requisitos: Windows, PowerShell y Python 3.11, 3.12 o 3.13 (recomendado: 3.12).
Clonar el repositorio o extraer su ZIP y abrir PowerShell en esa carpeta. No requiere Anaconda.

Desde la raíz del repositorio:

```powershell
.\iniciar-web.ps1
```

El script detecta Python, crea `.venv-star-web` sin heredar paquetes globales e
instala todas las dependencias dentro de ese entorno, incluido el cliente S3.
Si falta `.env`, copia `.env.example`; un `.env` existente se conserva.
Puede ejecutarse desde cualquier carpeta usando la ruta al lanzador.
No cambia el Python de la notebook.
Para preparar el entorno sin iniciar la web: `.\iniciar-web.ps1 -PrepareOnly`.

Luego inicia un solo proceso en Windows, independiente de la API Heart Disease.
Cerrar con Ctrl+C. Para iniciar manualmente después de instalar:

```powershell
.\.venv-star-web\Scripts\python.exe .\star_web\app.py
```

## Alternativa sin ejecutar scripts PowerShell

Si la configuración de Windows no permite ejecutar archivos `.ps1`, desde la
raíz del repositorio se puede preparar e iniciar directamente con Python:

```powershell
python -m venv .venv-star-web
.\.venv-star-web\Scripts\python.exe -m pip install -r .\star_web\requirements.txt
.\.venv-star-web\Scripts\python.exe .\star_web\app.py
```

No es necesario activar el entorno ni modificar la política de ejecución.
`python` debe corresponder a una de las versiones compatibles indicadas arriba.

## Uso

1. Cargar objetos: consulta TOP 10000 a SDSS, con el JOIN y filtro scienceprimary
   del DAG estelar. Se mantiene `objid` como texto y se excluyen bandas inválidas.
2. Buscar por identificador y seleccionar un objeto; la clase SDSS permanece oculta. La lista está paginada.
3. Revisar bandas y colores y pulsar **Predecir tipo de objeto**.

El navegador calcula `u-g`, `g-r`, `r-i`, `i-z` y envía las nueve variables D2
sin escalar a `POST /api/predict`. La API comprueba los colores, ordena las columnas
y ejecuta el Pipeline sklearn completo cargado desde MLflow. No envía `class`,
`objid`, coordenadas ni redshift al modelo. Después de predecir se muestra la clase SDSS y si coincide con la predicción. Antes de predecir no aparece en el selector, los detalles ni la búsqueda.

Se cachea la consulta una hora; el alias del modelo se revisa cada minuto.
La versión usada se fija al cargarlo y se devuelve con la predicción.
La lista de TOP 10000 puede incluir objetos usados para entrenar; esta pantalla
explora predicciones, no calcula una métrica de evaluación independiente.

## API

- `GET /api/objects`: lista y metadatos de la consulta.
- `GET /api/objects?refresh=true`: fuerza una consulta nueva.
- `POST /api/predict`: `{ "features": { "u":20, "g":19, "r":18, "i":17, "z":16,
  "u-g":1, "g-r":1, "r-i":1, "i-z":1 } }`.
- Documentación interactiva: `http://localhost:8801/docs`.

## Configuración opcional del proceso

- `STAR_WEB_PORT`: 8801.
- `STAR_MLFLOW_URI`: `http://127.0.0.1:5001`.
- `STAR_S3_ENDPOINT`: `http://127.0.0.1:9000`.
- `STAR_SDSS_CA_BUNDLE`: bundle de CA verificado para SDSS. Por defecto usa
  `airflow/config/sdss-ca-bundle.pem` si existe; normalmente no hace falta.
  Si hay inspección HTTPS, usar una CA validada del propio equipo.

Las credenciales MinIO se leen del `.env` del repositorio, únicamente en el
servidor. Cliente MLflow 3.16.1 y scikit-learn 1.7.2, compatibles con el registro.

Pruebas: `python -m unittest discover -s tests -p test_star_web.py`.
