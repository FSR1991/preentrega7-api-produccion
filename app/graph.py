"""Grafo multiagente con persistencia y aprobación humana."""

from typing import Any

from groq import Groq
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from langsmith import traceable

from app.agents import make_agent_node
from app.agents import planner, reviewer, specialist
from app.config import get_groq_api_key, get_groq_model
from app.state import TaskState


def build_graph(checkpointer: Any):
    client = Groq(api_key=get_groq_api_key())
    model = get_groq_model()

    coordinator = make_agent_node(
        name="coordinator_agent",
        system_prompt=planner.SYSTEM_PROMPT,
        prompt_builder=planner.build_prompt,
        output_field="plan",
        client=client,
        model=model,
        max_tokens=350,
    )

    specialist_agent = make_agent_node(
        name="specialist_agent",
        system_prompt=specialist.SYSTEM_PROMPT,
        prompt_builder=specialist.build_prompt,
        output_field="specialist_result",
        client=client,
        model=model,
        max_tokens=700,
    )

    reviewer_agent = make_agent_node(
        name="reviewer_agent",
        system_prompt=reviewer.SYSTEM_PROMPT,
        prompt_builder=reviewer.build_prompt,
        output_field="result",
        client=client,
        model=model,
        max_tokens=700,
    )

    @traceable(
        name="human_approval_gate",
        run_type="chain",
    )
    def approval_gate(state: TaskState) -> dict[str, Any]:
        decision = interrupt({
            "type": "approval_required",
            "task_id": state["task_id"],
            "reason": state.get("criticality_reason"),
            "prompt": state["prompt"],
            "message": (
                "La tarea fue clasificada como crítica. "
                "Se requiere aprobación humana antes de "
                "continuar con los agentes."
            ),
        })

        if (
            not isinstance(decision, dict)
            or not isinstance(decision.get("approved"), bool)
        ):
            raise ValueError(
                "La decisión debe incluir approved como booleano."
            )

        approved = decision["approved"]

        return {
            "approval": "approved" if approved else "rejected",
            "status": "RUNNING" if approved else "REJECTED",
        }

    def route_before_agents(state: TaskState) -> str:
        if state.get("requires_approval", False):
            return "approval_gate"
        return "coordinator_agent"

    def route_after_approval(state: TaskState) -> str:
        if state.get("approval") == "approved":
            return "coordinator_agent"
        return END

    builder = StateGraph(TaskState)

    builder.add_node("approval_gate", approval_gate)
    builder.add_node("coordinator_agent", coordinator)
    builder.add_node("specialist_agent", specialist_agent)
    builder.add_node("reviewer_agent", reviewer_agent)

    builder.add_conditional_edges(
        START,
        route_before_agents,
        {
            "approval_gate": "approval_gate",
            "coordinator_agent": "coordinator_agent",
        },
    )

    builder.add_conditional_edges(
        "approval_gate",
        route_after_approval,
        {
            "coordinator_agent": "coordinator_agent",
            END: END,
        },
    )

    builder.add_edge("coordinator_agent", "specialist_agent")
    builder.add_edge("specialist_agent", "reviewer_agent")
    builder.add_edge("reviewer_agent", END)

    return builder.compile(checkpointer=checkpointer)