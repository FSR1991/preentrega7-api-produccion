import asyncio
import json
import math
import os
import sys
import time
from typing import Any

import httpx

BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

CONCURRENT_REQUESTS = 5
MAX_WAIT_SECONDS = 240
POLL_INTERVAL_SECONDS = 0.5


def percentile_95(values: list[float]) -> float:
    if not values:
        raise ValueError("No hay mediciones para calcular el p95.")

    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


async def submit_task(
    client: httpx.AsyncClient,
    number: int,
) -> dict[str, Any]:
    started_at = time.perf_counter()

    response = await client.post(
        "/tasks",
      json={
    "prompt": (
        f"[P7-CARGA-FINAL-20261021] Prueba de concurrencia {number}. "
        "Respondé brevemente e indicá que terminó."
    ),
},
    )
    response.raise_for_status()
    payload = response.json()

    job_id = payload.get("job_id")
    if not job_id:
        raise RuntimeError(
            f"La API no devolvió job_id: {payload}"
        )

    return {
        "job_id": job_id,
        "started_at": started_at,
        "http_latency_seconds": (
            time.perf_counter() - started_at
        ),
    }


async def wait_for_completion(
    client: httpx.AsyncClient,
    submitted: dict[str, Any],
) -> dict[str, Any]:
    job_id = submitted["job_id"]
    deadline = time.monotonic() + MAX_WAIT_SECONDS

    while time.monotonic() < deadline:
        response = await client.get(f"/tasks/{job_id}")
        response.raise_for_status()
        task = response.json()

        state = task.get("status")

        if state in {"DONE", "FAILED", "REJECTED"}:
            return {
                "job_id": job_id,
                "status": state,
                "http_latency_seconds": round(
                    submitted["http_latency_seconds"],
                    6,
                ),
                "end_to_end_seconds": round(
                    time.perf_counter() - submitted["started_at"],
                    6,
                ),
                "input_tokens": task.get("input_tokens", 0),
                "output_tokens": task.get("output_tokens", 0),
                "cost_usd": task.get("cost_usd", 0.0),
                "error": task.get("error"),
            }

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return {
        "job_id": job_id,
        "status": "TIMEOUT",
        "http_latency_seconds": round(
            submitted["http_latency_seconds"],
            6,
        ),
        "end_to_end_seconds": None,
        "error": (
            f"La tarea no terminó dentro de "
            f"{MAX_WAIT_SECONDS} segundos."
        ),
    }


async def main() -> int:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=30.0,
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()

        if health.json().get("redis") != "connected":
            raise RuntimeError(
                "La API no confirma la conexión con Redis."
            )

        submitted = await asyncio.gather(
            *(
                submit_task(client, number)
                for number in range(1, CONCURRENT_REQUESTS + 1)
            )
        )

        results = await asyncio.gather(
            *(
                wait_for_completion(client, item)
                for item in submitted
            )
        )

    completed = [
        item for item in results
        if item["status"] == "DONE"
    ]

    http_latencies = [
        item["http_latency_seconds"] for item in results
    ]

    end_to_end_latencies = [
        item["end_to_end_seconds"] for item in results
        if item["end_to_end_seconds"] is not None
    ]

    summary = {
        "api_url": BASE_URL,
        "requests_sent_concurrently": CONCURRENT_REQUESTS,
        "completed": len(completed),
        "failed_or_timed_out": (
            CONCURRENT_REQUESTS - len(completed)
        ),
        "http_p95_seconds": round(
            percentile_95(http_latencies),
            6,
        ),
        "end_to_end_p95_seconds": (
            round(percentile_95(end_to_end_latencies), 6)
            if end_to_end_latencies
            else None
        ),
        "results": results,
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    return 0 if len(completed) == CONCURRENT_REQUESTS else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        print(
            f"Falló la prueba de concurrencia: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)