"""Agente revisor de calidad."""

SYSTEM_PROMPT = """
Sos el agente revisor de calidad.
Comprobá que la propuesta responda a la solicitud original.
Corregí omisiones, contradicciones y afirmaciones no justificadas.
Entregá una respuesta final autosuficiente.
No describas tu proceso interno de revisión.
Respondé en español.
"""


def build_prompt(state: dict) -> str:
    return (
        f"Solicitud original:\n{state['prompt']}\n\n"
        f"Plan:\n{state.get('plan', '')}\n\n"
        "Propuesta del especialista:\n"
        f"{state.get('specialist_result', '')}"
    )