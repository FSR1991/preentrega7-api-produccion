import logging
import time
from contextlib import closing
from typing import Any

from dotenv import load_dotenv
from langgraph.checkpoint.redis import RedisSaver
from redis import Redis
from redis.exceptions import RedisError

from app.config import PROJECT_ROOT, get_redis_url
from app.graph import build_graph
from app.hitl import approval_command, is_interrupted

from app.task_store import TaskStore

load_dotenv(PROJECT_ROOT / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("preentrega7.worker")


def process_message(
    message: dict[str, Any],
    store: TaskStore,
    graph: Any,
) -> None:
    task_id = message.get("task_id")
    action = message.get("action")

    if not task_id:
        logger.error("Mensaje de cola sin task_id: %s", message)
        return

    task = store.get_task(task_id)

    if task is None:
        logger.error("No existe la tarea %s", task_id)
        return

    config = {"configurable": {"thread_id": task_id}}
    started_at = task.get("started_at", time.time())

    try:
        if action == "execute":
            if task["status"] != "PENDING":
                logger.warning(
                    "Se omite ejecución duplicada de %s: estado=%s",
                    task_id,
                    task["status"],
                )
                return

            started_at = time.time()

            store.update_task(
                task_id,
                "RUNNING",
                started_at=started_at,
            )

            result = graph.invoke(
                {
                    "task_id": task_id,
                    "prompt": task["prompt"],
                    "status": "RUNNING",
                    "requires_approval": task.get(
                        "requires_approval", False
                    ),
                    "criticality_reason": task.get(
                        "criticality_reason"
                    ),
                },
                config=config,
            )

        elif action == "resume":
            if task["status"] != "APPROVAL_QUEUED":
                logger.warning(
                    "Se omite reanudación duplicada de %s: estado=%s",
                    task_id,
                    task["status"],
                )
                return

            store.update_task(task_id, "RUNNING")

            result = graph.invoke(
                approval_command(message.get("approved") is True),
                config=config,
            )

        else:
            logger.error("Acción desconocida en cola: %s", action)
            return

        input_tokens = result.get(
            "input_tokens",
            task.get("input_tokens", 0),
        )
        output_tokens = result.get(
            "output_tokens",
            task.get("output_tokens", 0),
        )
        cost_usd = result.get(
            "cost_usd",
            task.get("cost_usd", 0.0),
        )
        final_result = result.get(
            "result",
            task.get("result", ""),
        )

        if is_interrupted(result):
            store.update_task(
                task_id,
                "WAITING_APPROVAL",
                result=final_result,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )

            logger.info(
                "Tarea %s en espera de aprobación humana",
                task_id,
            )
            return

        final_status = result.get("status", "DONE")

        if final_status not in {"DONE", "REJECTED"}:
            final_status = "DONE"

        finished_at = time.time()
        duration_seconds = round(finished_at - started_at, 6)

        store.update_task(
            task_id,
            final_status,
            result=final_result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            approval=result.get("approval", task.get("approval")),
            finished_at=finished_at,
            duration_seconds=duration_seconds,
        )

        

        logger.info(
            "Tarea %s finalizada: estado=%s, tokens=%s/%s, "
            "costo_usd=%s, duración=%s segundos",
            task_id,
            final_status,
            input_tokens,
            output_tokens,
            cost_usd,
            duration_seconds,
        )

    except Exception as exc:
        logger.exception("Falló la tarea %s", task_id)

        try:
            store.update_task(
                task_id,
                "FAILED",
                error=f"{type(exc).__name__}: {exc}",
                finished_at=time.time(),
            )
        except (RedisError, KeyError):
            logger.exception(
                "No se pudo guardar FAILED para %s",
                task_id,
            )


def run_worker() -> None:
    redis_url = get_redis_url()

    with RedisSaver.from_conn_string(redis_url) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer)

        with closing(
            Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=None,
                health_check_interval=30,
            )
        ) as client:
            client.ping()
            store = TaskStore(client)

            logger.info("Worker iniciado; esperando tareas")

            while True:
                try:
                    message = store.dequeue(timeout=5)

                    if message is not None:
                        process_message(message, store, graph)

                except RedisError:
                    logger.exception(
                        "Error de Redis; se reintentará"
                    )
                    time.sleep(2)

                except KeyboardInterrupt:
                    logger.info("Worker detenido")
                    break


if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker detenido")
    except Exception:
        logger.exception("No se pudo iniciar el worker")
        raise