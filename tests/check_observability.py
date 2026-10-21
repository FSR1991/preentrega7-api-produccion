import os
import sys
from datetime import datetime, timedelta, timezone

from langsmith import Client

from app.config import get_langsmith_project


AGENT_NAMES = {
    "coordinator_agent",
    "specialist_agent",
    "reviewer_agent",
}


def main() -> int:
    api_key = os.getenv("LANGSMITH_API_KEY", "").strip()

    if not api_key:
        print("ERROR: falta LANGSMITH_API_KEY en .env")
        return 1

    project = get_langsmith_project()
    client = Client(api_key=api_key)

    try:
        runs = list(
            client.list_runs(
                project_name=project,
                start_time=(
                    datetime.now(timezone.utc)
                    - timedelta(hours=24)
                ),
                limit=100,
            )
        )
    except Exception as exc:
        print(
            f"ERROR consultando LangSmith: "
            f"{type(exc).__name__}: {exc}"
        )
        return 1

    agent_runs = [
        run for run in runs
        if run.name in AGENT_NAMES
    ]

    approval_runs = [
        run for run in runs
        if run.name == "human_approval_gate"
    ]

    print(f"Proyecto: {project}")
    print(f"Trazas totales: {len(runs)}")
    print(f"Trazas de agentes: {len(agent_runs)}")
    print(f"Trazas HITL: {len(approval_runs)}")

    usage_ok = 0

    for run in agent_runs:
        extra = run.extra or {}
        metadata = extra.get("metadata", {})

        usage = (
            getattr(run, "usage_metadata", None)
            or metadata.get("usage_metadata", {})
        )

        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")

        if (
            input_tokens is not None
            and output_tokens is not None
            and total_tokens is not None
        ):
            usage_ok += 1

        print({
            "agent": run.name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "error": run.error,
        })

    if not agent_runs:
        print("ERROR: no se encontraron trazas de los agentes.")
        return 1

    if usage_ok == 0:
        print("ERROR: no se encontraron trazas con tokens registrados.")
        return 1

    if not approval_runs:
        print(
            "AVISO: todavía no se encontró una traza HITL."
        )

    print(
        f"Validación parcial: {usage_ok} trazas "
        "contienen datos de tokens."
    )
    print(
        "Falta confirmar el costo automático "
        "directamente en el dashboard."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())