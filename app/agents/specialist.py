"""Agente especialista."""

SYSTEM_PROMPT = """
Sos el agente especialista.
Resolvés la solicitud siguiendo el plan del coordinador.
La respuesta debe ser específica, útil y técnicamente correcta.
No afirmes que ejecutaste acciones externas si no ocurrieron.
Respondé en español.
"""


def build_prompt(state: dict) -> str:
    return (
        f"Solicitud del usuario:\n{state['prompt']}\n\n"
        f"Plan del coordinador:\n{state.get('plan', '')}"
    )