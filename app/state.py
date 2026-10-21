from typing import Any, NotRequired, TypedDict


class TaskState(TypedDict):
    task_id: str
    prompt: str
    status: str

    result: NotRequired[str]
    plan: NotRequired[str]
    specialist_result: NotRequired[str]
    error: NotRequired[str]

    requires_approval: NotRequired[bool]
    criticality_reason: NotRequired[str | None]
    approval: NotRequired[str]

    agent_usage: NotRequired[dict[str, dict[str, int]]]

    input_tokens: NotRequired[int]
    output_tokens: NotRequired[int]
    cost_usd: NotRequired[float]
    duration_seconds: NotRequired[float]
    metadata: NotRequired[dict[str, Any]]