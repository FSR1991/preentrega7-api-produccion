import asyncio
import json
import os
import sys
import time

import httpx

BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

TIMEOUT_SECONDS = 180
POLL_INTERVAL_SECONDS = 0.5


async def wait_for_status(
    client: httpx.AsyncClient,
    job_id: str,
    expected_status: str,
) -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        response = await client.get(f"/tasks/{job_id}")
        response.raise_for_status()
        task = response.json()
        current_status = task.get("status")

        if current_status == expected_status:
            return task

        if current_status in {"FAILED", "DONE", "REJECTED"}:
            raise RuntimeError(
                f"La tarea {job_id} terminó en {current_status}; "
                f"se esperaba {expected_status}. Detalle: {task}"
            )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"La tarea {job_id} no alcanzó el estado "
        f"{expected_status} dentro del tiempo previsto."
    )


async def main() -> int:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=30.0,
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()

        created_response = await client.post(
            "/tasks",
            json={
                "prompt": (
                    "Solicito eliminar registros de prueba."
                    "Quiero verificar la pausa obligatoria de"
                    "aprobacion antes de procesar esta solicitud."
                ),
            },
        )
        created_response.raise_for_status()

        job_id = created_response.json()["job_id"]
        print(f"Tarea creada: {job_id}")

        waiting_task = await wait_for_status(
            client,
            job_id,
            "WAITING_APPROVAL",
        )
        print(
            "Pausa HITL confirmada:",
            waiting_task["status"],
        )

        approval_response = await client.post(
            f"/tasks/{job_id}/approve",
            json={"approved": True},
        )
        approval_response.raise_for_status()
        print(
            "Aprobación aceptada:",
            json.dumps(
                approval_response.json(),
                ensure_ascii=False,
            ),
        )

        completed_task = await wait_for_status(
            client,
            job_id,
            "DONE",
        )

        print("Prueba HITL superada.")
        print(
            json.dumps(
                {
                    "job_id": job_id,
                    "status": completed_task["status"],
                    "approval": completed_task.get("approval"),
                    "input_tokens": completed_task.get("input_tokens"),
                    "output_tokens": completed_task.get("output_tokens"),
                    "cost_usd": completed_task.get("cost_usd"),
                    "duration_seconds": completed_task.get(
                        "duration_seconds"
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        print(
            f"Falló la prueba HITL: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)