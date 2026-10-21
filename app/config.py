import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_INPUT_PRICE = 0.15
DEFAULT_OUTPUT_PRICE = 0.60


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Falta la variable obligatoria {name}. "
            "Configurala en el archivo .env."
        )
    return value


def get_redis_url() -> str:
    return get_required_env("REDIS_URL")


def get_groq_api_key() -> str:
    return get_required_env("GROQ_API_KEY")


def get_groq_model() -> str:
    return os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip()


def get_model_prices() -> tuple[float, float]:
    """Tarifas en USD por millón de tokens, configurables por entorno."""
    input_price = float(
        os.getenv("GROQ_INPUT_PRICE_PER_MILLION", str(DEFAULT_INPUT_PRICE))
    )
    output_price = float(
        os.getenv("GROQ_OUTPUT_PRICE_PER_MILLION", str(DEFAULT_OUTPUT_PRICE))
    )

    if input_price < 0 or output_price < 0:
        raise ValueError("Las tarifas por token no pueden ser negativas.")

    return input_price, output_price


def calculate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = get_model_prices()
    return round(
        (input_tokens * input_price + output_tokens * output_price) / 1_000_000,
        10,
    )


def get_langsmith_project() -> str:
    return os.getenv(
        "LANGSMITH_PROJECT",
        "preentrega7-api-produccion-v2",
    ).strip()