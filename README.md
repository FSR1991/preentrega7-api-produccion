Pre-entrega 7 — API de producción y monitoreo activo

API REST construida con Python 3.12+, FastAPI, Redis, LangGraph, Groq y LangSmith. El proyecto expone un sistema de procesamiento de tareas en segundo plano, persistencia de estados, checkpoints del grafo, aprobación humana (HITL) y observabilidad de las ejecuciones.

1. Arquitectura

La solución se organiza en los siguientes componentes:

- FastAPI ("app/main.py"): expone los endpoints para crear tareas, consultar su estado y enviar decisiones de aprobación.
- Redis ("app/redis_store.py", "app/task_store.py"): almacena los estados y resultados de los trabajos y proporciona la cola de tareas.
- Worker ("app/worker.py"): consume la cola, ejecuta o reanuda los trabajos y registra los estados finales, incluidos los fallos.
- LangGraph ("app/graph.py", "app/state.py"): define el estado compartido, el flujo de agentes y el punto de interrupción para aprobación humana. Redis se utiliza también como almacenamiento de checkpoints.
- Agentes ("app/agents/"): coordinador, especialista y revisor, con responsabilidades diferenciadas dentro del flujo.
- Clasificación de criticidad ("app/criticality.py"): identifica solicitudes críticas mediante reglas explícitas.
- Observabilidad ("app/observability.py"): registra el uso de tokens y permite observar las ejecuciones en LangSmith.

2. Requisitos

- Python 3.12 o superior compatible con las dependencias del proyecto.
- Redis accesible mediante una URL de conexión.
- Una clave de API de Groq.
- Una cuenta y una clave de API de LangSmith para enviar y consultar trazas.

El proyecto utiliza un modelo remoto; no necesita descargar ni ejecutar un modelo de lenguaje local.

3. Instalación en Windows

Cloná el repositorio y entrá en su carpeta:

git clone <URL_PUBLICA_DEL_REPOSITORIO>
cd preentrega7-api-produccion

Creá y activá el entorno virtual:

py -3.12 -m venv .venv
.venv\Scripts\activate

Actualizá "pip" e instalá las dependencias:

python -m pip install --upgrade pip
pip install -r requirements.txt

Copiá el archivo de ejemplo de variables de entorno:

copy .env.example .env

Editá ".env" con los valores correspondientes. No publiques ni compartas ese archivo.

4. Configuración

Las variables utilizadas por la aplicación son:

Variable| Uso
"GROQ_API_KEY"| Clave de acceso al proveedor Groq.
"GROQ_MODEL"| Modelo utilizado. Por defecto: "openai/gpt-oss-120b".
"REDIS_URL"| URL de conexión con Redis.
"LANGSMITH_TRACING"| Activa la instrumentación de LangSmith cuando está habilitada.
"LANGSMITH_API_KEY"| Clave para consultar y enviar trazas a LangSmith.
"LANGSMITH_PROJECT"| Nombre del proyecto de trazas.
"GROQ_INPUT_PRICE_PER_MILLION"| Tarifa configurada para estimar el costo local de tokens de entrada.
"GROQ_OUTPUT_PRICE_PER_MILLION"| Tarifa configurada para estimar el costo local de tokens de salida.

Para mantener las trazas agrupadas correctamente, configurá "LANGSMITH_PROJECT" con el mismo nombre del proyecto usado en el dashboard, por ejemplo "preentrega7-api-produccion-v2".

Las tarifas locales se expresan en dólares por millón de tokens. El campo "cost_usd" persistido por la aplicación representa una estimación basada en esa configuración. Las métricas de costo del dashboard deben interpretarse según los datos de uso y los precios que LangSmith tenga asociados al modelo.

5. Ejecución

Redis debe estar accesible antes de iniciar la API y el worker. En esta implementación, la conexión se configura mediante "REDIS_URL".

Abrí dos terminales en la raíz del proyecto y activá el entorno virtual en ambas.

Terminal 1 — Worker

python -m app.worker

Terminal 2 — API

python -m uvicorn app.main:app --reload

La API queda disponible localmente en "http://127.0.0.1:8000".

La documentación interactiva de FastAPI puede consultarse en:

- Swagger UI: "http://127.0.0.1:8000/docs"
- OpenAPI: "http://127.0.0.1:8000/openapi.json"

6. Endpoints

"GET /health"

Comprueba la disponibilidad de la API y la conexión con Redis.

"POST /tasks"

Crea y encola un trabajo. Devuelve HTTP 202 y un identificador "job_id" sin esperar a que termine el procesamiento.

Ejemplo de solicitud:

{
  "prompt": "Analizá esta solicitud y prepará una respuesta breve."
}

Ejemplo ilustrativo de respuesta:

{
  "job_id": "<id-generado>",
  "status": "PENDING"
}

La respuesta exacta puede incluir información adicional sobre la clasificación de criticidad.

"GET /tasks/{task_id}"

Consulta el estado, el resultado y las métricas disponibles de una tarea. Si el identificador no existe, la API responde con HTTP 404.

"POST /tasks/{task_id}/approve"

Registra una decisión humana para un trabajo que está esperando aprobación.

Solicitud de aprobación:

{
  "approved": true
}

Para rechazarlo:

{
  "approved": false
}

La API valida que la tarea exista y esté esperando aprobación antes de registrar la decisión. La reanudación se procesa mediante el worker y el checkpoint de LangGraph.

7. Estados de los trabajos

Los estados utilizados incluyen:

- "PENDING": trabajo creado y encolado.
- "RUNNING": trabajo en ejecución.
- "WAITING_APPROVAL": el grafo está detenido esperando una decisión humana.
- "APPROVAL_QUEUED": la decisión fue registrada y está pendiente de procesamiento.
- "DONE": trabajo completado.
- "REJECTED": solicitud crítica rechazada.
- "FAILED": fallo durante el procesamiento.

Las tareas críticas se identifican a partir de las reglas configuradas en "app/criticality.py". La aprobación humana se realiza mediante el endpoint correspondiente.

8. Pruebas

Ejecutá las pruebas automatizadas desde la raíz del repositorio:

python -m compileall -q app tests
python -m pytest -q

Para las pruebas de integración, Redis, la API y el worker deben estar funcionando.

Aprobación humana:

python -m tests.run_hitl_check

Rechazo humano:

python -m tests.run_hitl_rejection

Cinco peticiones concurrentes:

python -m tests.run_concurrency

El script envía cinco solicitudes concurrentes, consulta los estados de las tareas y presenta las latencias HTTP y de extremo a extremo, junto con los resultados y los costos locales estimados disponibles.

Comprobación de observabilidad:

python -m tests.check_observability

Esta última prueba consulta LangSmith y comprueba las trazas y los datos de uso disponibles.

9. Observabilidad y métricas

Las trazas permiten inspeccionar el flujo de los agentes, los datos de entrada y salida y el uso de tokens del modelo.

El dashboard de LangSmith creado para la entrega incluye gráficos de costo promedio por ejecución y latencia P95. Las métricas deben interpretarse con el filtro correspondiente a la corrida de prueba identificada.

En la última corrida de concurrencia registrada durante el desarrollo:

- Solicitudes concurrentes: 5.
- Tareas completadas: 5.
- Fallos o timeouts: 0.
- Latencia HTTP P95 local: aproximadamente 1,296 segundos.
- Latencia total P95 local: aproximadamente 20,416 segundos.

En el dashboard se observó una latencia P95 de aproximadamente 2,639 segundos y un costo promedio por ejecución de USD 0,00032691 para el período mostrado. La latencia de las trazas y la latencia total de los trabajos son métricas diferentes; no deben intercambiarse.

Los valores son resultados de una corrida concreta y no una garantía de rendimiento para otras cargas.

10. Evidencias

Las capturas de ejecución y observabilidad se almacenan en "screenshots/".

Archivo| Evidencia
"01-pytest-aprobado.png"| Resultado de las pruebas automatizadas.
"02-hitl-aprobacion.png"| Pausa y aprobación humana con finalización del trabajo.
"03-hitl-rechazo.png"| Rechazo humano y estado final "REJECTED".
"04-concurrencia-final-A.png"| Primera parte de la salida de la prueba de concurrencia.
"04-concurrencia-final-B.png"| Continuación de la salida de la prueba de concurrencia.
"05-langsmith-trazas-agentes.png"| Árbol de trazas de los agentes en LangSmith.
"06-langsmith-costo.png"| Métrica de costo mostrada en LangSmith.
"07-langsmith-latencia-p95.png"| Métrica de latencia P95 mostrada en LangSmith.
"08-langsmith-dashboard-A.png"| Primera parte del dashboard de observabilidad.
"08-langsmith-dashboard-B.png"| Continuación del dashboard de observabilidad.

Las capturas divididas en "A" y "B" se utilizan para conservar legibles las salidas y los gráficos que no cabían completos en una sola imagen.

11. Seguridad y reproducibilidad

- No subir ".env", claves de API ni credenciales al repositorio.
- Mantener ".env.example" sin valores secretos.
- Excluir ".venv", cachés de Python y archivos generados mediante ".gitignore".
- Instalar las dependencias a partir de "requirements.txt".
- Verificar los pasos de instalación y ejecución desde una clonación limpia antes de entregar.

12. Estructura del proyecto

preentrega7-api-produccion/
├── app/
│   ├── agents/
│   ├── criticality.py
│   ├── config.py
│   ├── graph.py
│   ├── hitl.py
│   ├── main.py
│   ├── observability.py
│   ├── redis_store.py
│   ├── state.py
│   ├── task_store.py
│   └── worker.py
├── tests/
│   ├── test_task_store.py
│   ├── test_worker_failure.py
│   ├── run_concurrency.py
│   ├── run_hitl_check.py
│   ├── run_hitl_rejection.py
│   └── check_observability.py
├── screenshots/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md

La estructura refleja los componentes principales de la aplicación. Debe contrastarse con los archivos efectivamente presentes en la versión publicada.

13. Alcance

La entrega implementa una API para encolar y consultar tareas, un worker para ejecutarlas, persistencia del estado en Redis, checkpoints de LangGraph, aprobación humana y observabilidad con LangSmith.

La validación final debe realizarse mediante las pruebas automatizadas, los scripts de integración y las evidencias incluidas en "screenshots/".