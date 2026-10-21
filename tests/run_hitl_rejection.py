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
    expected: str,
) -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        response = await client.get(f"/tasks/{job_id}")
        response.raise_for_status()

        task = response.json()
        current = task.get("status")

        if current == expected:
            return task

        if current in {"FAILED", "DONE", "REJECTED"}:
            raise RuntimeError(
                f"Estado inesperado: {current}; "
                f"se esperaba {expected}. Detalle: {task}"
            )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"La tarea no alcanzó el estado {expected}."
    )


async def main() -> int:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=30.0,
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()

        if health.json().get("redis") != "connected":
            raise RuntimeError("Redis no está conectado.")

        response = await client.post(
            "/tasks",
            json={
                "prompt": (
                    "Solicito eliminar registros de prueba para "
            "verificar el rechazo de una tarea crítica."
                ),
            },
        )
        response.raise_for_status()

        job_id = response.json()["job_id"]
        print(f"Tarea creada: {job_id}")

        await wait_for_status(
            client,
            job_id,
            "WAITING_APPROVAL",
        )
        print("Pausa HITL confirmada.")

        response = await client.post(
            f"/tasks/{job_id}/approve",
            json={"approved": False},
        )
        response.raise_for_status()
        print("Rechazo aceptado.")

        task = await wait_for_status(
            client,
            job_id,
            "REJECTED",
        )

        print("PRUEBA DE RECHAZO SUPERADA")
        print(json.dumps({
            "job_id": job_id,
            "status": task["status"],
            "approval": task.get("approval"),
        }, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        print(
            f"Falló la prueba: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)