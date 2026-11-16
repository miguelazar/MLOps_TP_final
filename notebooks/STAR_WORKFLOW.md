# Clasificación estelar D2

## Archivos y uso

1. Airflow: ejecutar `process_etl_star_data`, DAG manual en `airflow/dags/etl_star_data.py`.
   Consulta hasta 1000 objetos aleatorios con `ORDER BY NEWID()` mediante la API SQL oficial. Guarda la respuesta validada en
   `s3://data/raw/star/starset.csv`, y una copia por hash en `raw/star/snapshots/`.
   La ingesta se registra como run independiente en `star type`.
2. Abrir `notebooks/experiment_star_mlflow.ipynb` desde Windows.
   Seleccionar un kernel con las dependencias de `requirements_star.txt`.
   El cliente se fija en MLflow 3.16.1, igual que el servidor actual; al cambiar
   versiones en el kernel, reiniciarlo antes de ejecutar la notebook.
   La notebook usa `localhost:5001` para MLflow y `localhost:9000` para MinIO.
3. Ejecutar en orden. El registro crea o recupera la versión candidata.
   La celda separada de comparación mueve `champion` solo si mejora el F1 weighted.
   Como alternativa, ejecutar las seis etapas del DAG `train_star_model`,
   que usa el mismo paquete compartido `airflow/dags/star_training`.

Después del build inicial indicado en `STAR_SETUP.md`, los cambios de DAG no requieren reconstruir imágenes: se montan desde el repositorio y la
notebook se ejecuta localmente. El DAG usa requests, boto3 y MLflow ya instalados
en Airflow; no crea virtualenvs ni descarga paquetes por tarea.

### HTTPS y antivirus de este equipo

La inspección HTTPS de Avast utiliza una CA que Windows acepta pero Linux no
conocía. Se exportó únicamente su certificado público después de validar la
cadena SDSS con Windows y se dejó en `airflow/config/sdss-ca-bundle.pem`.
El bundle incluye además las CAs estándar, para funcionar con y sin inspección.
El auxiliar lo usa solo para la consulta SDSS; mantiene la validación TLS.
El archivo es local y está excluido mediante `.gitignore`.
En otro equipo sin inspección no hace falta este archivo. Para otro almacén
validado, definir `STAR_SDSS_CA_BUNDLE` en el entorno de Airflow.

## Preparación y búsqueda

- D2: `u,g,r,i,z,u-g,g-r,r-i,i-z`, objetivo multiclase `class`.
- No se usa redshift ni coordenadas como predictores.
- Duplicados por objid: conservar primero. Bandas <= -9000, no numéricas,
  nulas o infinitas: eliminar fila. Clases válidas: GALAXY, QSO, STAR.
- Partición 80/20 estratificada, semilla 42. CV estratificada de 5 folds.
- StandardScaler dentro de Pipeline; se ajusta de nuevo en cada fold.
- Optuna: 250 trials por defecto; SVM lineal/poly/rbf, árbol, Random Forest y KNN.
  Se maximiza F1 ponderado. Se registran también F1 macro y matriz de confusión.
- Un solo proceso para limitar consumo; `STAR_N_TRIALS` permite pruebas cortas.
- El modelo guardado recibe las nueve variables D2 sin normalizar y contiene el
  scaler. Para inferencia desde bandas se calculan primero los cuatro colores.
- `objid` se conserva como texto; se guarda el hash del CSV y los IDs del split.
- Nunca se sobrescriben los datos raw al normalizar. Medias y escalas se guardan
  como artefactos JSON por run, evitando conflictos de parámetros al reintentar.

## Registro y reejecuciones

Cada ejecución de la notebook crea un run padre nuevo, 250 runs hijos y una
versión nueva si se ejecuta el registro. El nombre del modelo puede existir.
La búsqueda y el entrenamiento/guardado están en celdas separadas: ante un fallo
de red durante el guardado se reintenta esa celda, sin repetir Optuna.
El alias champion se mueve a la versión recién seleccionada, sin borrar anteriores.
Se comprueba la recarga del artefacto y sus predicciones antes de publicar el alias.
Los modelos y experimentos de Heart Disease no se modifican. Su FastAPI continúa
siendo exclusiva para Heart Disease en el puerto 8800. La web y API estelar se ejecutan por separado en `star_web`, puerto 8801; seguir `../STAR_SETUP.md`.

Las nuevas ingestas toman TOP 1000 aleatorio con `ORDER BY NEWID()`; no hay
balanceo de clases ni garantía de representatividad de todo SDSS. Los snapshots
anteriores se conservan. Para cambiar la muestra hay que repetir la ingesta.
La promoción compara automáticamente ambos modelos en el mismo test,
y solo una mejora estricta del F1 weighted mueve el alias champion.

Para reproducir inferencia usar las versiones registradas en
`environment/versions.json`; en particular el mismo scikit-learn del entrenamiento.

## Verificación

`python -m unittest discover -s tests -p test_star_workflow.py`

Las pruebas cubren CSV SDSS inválido/vacío, precisión de objid, limpieza D2,
colores y aislamiento del scaler dentro de CV.

## Referencias

- Preparación D2: `tp-clasificacion-estelar_final.ipynb (referencia académica; no se necesita para ejecutar esta notebook)`.
- Patrón Optuna/MLflow: `notebooks/experiment_mlflow.ipynb`.
- API oficial: https://skyserver.sdss.org/dr17/Support/Api#search-services
- Consulta SQL: https://skyserver.sdss.org/dr17/SearchTools/sql
