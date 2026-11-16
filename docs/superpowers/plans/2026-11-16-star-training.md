# DAG de entrenamiento estelar: diseño e implementación

Diseño aceptado por el usuario: lógica compartida por notebook y DAG; promover
automáticamente al candidato solo si mejora al champion; comparación/promoción
como tarea separada de entrenamiento, evaluación y registro.

Arquitectura: paquete `airflow/dags/star_training` importado por ambos entornos.
Pipeline: resolve_snapshot -> search_hyperparameters -> train_and_log_model ->
evaluate_candidate -> register_candidate -> compare_and_promote_champion.
Snapshot S3 por SHA fijo, XCom solo referencias, checkpoints por ejecución en S3.
Regla: F1 weighted del candidato estrictamente mayor que champion sobre idéntico
test estratificado 80/20; empate conserva; ausencia de champion permite bootstrap.
Los errores de lectura/evaluación impiden mover alias. max_active_runs=1 y
comprobación del alias antes de actualizar; MLflow no tiene CAS para escrituras
concurrentes desde otras aplicaciones.

Plan inline:
1. RED: pruebas split/hash, mejora/empate/peor/primer champion/error/carrera/retry.
2. GREEN: extraer features, implementar workflow, registro idempotente y auditoría.
3. DAG liviano con seis tareas, checkpoints y parámetros validados por Airflow.
4. Notebook delega en las mismas funciones; dependencias y guía actualizadas.
5. Pruebas locales, integración MLflow temporal, parsing real Airflow y Compose.

Restricciones: MLflow3.16.1/sklearn1.7.2, CV5,250 trials,n_jobs1; no heavy imports
al parsear DAG; no ejecutar flujo de producción ni cambiar champion durante pruebas.
