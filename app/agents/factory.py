"""Factory de agentes trazables para LangGraph."""

from collections.abc import Callable
from typing import Any

from langsmith import traceable

from app.observability import record_llm_usage

State = dict[str, Any]
PromptBuilder = Callable[[State], str]


def make_agent_node(
    *,
    name: str,
    system_prompt: str,
    prompt_builder: PromptBuilder,
    output_field: str,
    client: Any,
    model: str,
    max_tokens: int = 500,
) -> Callable[[State], dict[str, Any]]:
    """Crea un nodo de agente con métricas acumuladas."""

    @traceable(
        name=name,
        run_type="llm",
        metadata={
            "ls_provider": "groq",
            "ls_model_name": model,
        },
    )
    def run_agent(state: State) -> dict[str, Any]:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": prompt_builder(state),
                },
            ],
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        usage = response.usage

        input_tokens = int(
            usage.prompt_tokens if usage else 0
        )
        output_tokens = int(
            usage.completion_tokens if usage else 0
        )

        # Registra uso y costo en la traza activa de LangSmith.
        # El costo persistido por la API es una estimación local.
        cost = record_llm_usage(
            input_tokens,
            output_tokens,
        )

        previous_input = int(state.get("input_tokens", 0))
        previous_output = int(state.get("output_tokens", 0))
        previous_cost = float(state.get("cost_usd", 0.0))

        usage_by_agent = dict(state.get("agent_usage", {}))
        usage_by_agent[name] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        return {
            output_field: content,
            "input_tokens": previous_input + input_tokens,
            "output_tokens": previous_output + output_tokens,
            "cost_usd": previous_cost + cost,
            "agent_usage": usage_by_agent,
        }

    return run_agent