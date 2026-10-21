from typing import Any

from langgraph.types import Command


def approval_command(approved: bool) -> Command:
    if not isinstance(approved, bool):
        raise ValueError(
            "La decisión de aprobación debe ser booleana."
        )

    return Command(
        resume={"approved": approved}
    )


def is_interrupted(graph_result: dict[str, Any]) -> bool:
    return bool(graph_result.get("__interrupt__"))


def get_pending_approval(
    graph: Any,
    task_id: str,
) -> dict[str, Any] | None:
    snapshot = graph.get_state(
        {"configurable": {"thread_id": task_id}}
    )

    for task in getattr(snapshot, "tasks", ()):
        for interruption in getattr(task, "interrupts", ()):
            value = getattr(interruption, "value", None)

            if isinstance(value, dict):
                return value

    return None