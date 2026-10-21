import logging

from langsmith import get_current_run_tree

from app.config import calculate_cost_usd

logger = logging.getLogger("preentrega7.observability")


def record_llm_usage(
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Registra tokens en LangSmith y estima el costo local."""

    local_cost_estimate = calculate_cost_usd(
        input_tokens,
        output_tokens,
    )

    run = get_current_run_tree()

    if run is None:
        logger.warning(
            "No hay una traza LangSmith activa para registrar uso."
        )
        return local_cost_estimate

    run.set(
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    )

    logger.info(
        "Tokens registrados en LangSmith: entrada=%s, salida=%s",
        input_tokens,
        output_tokens,
    )

    return local_cost_estimate