import unicodedata


CRITICAL_RULES = {
    "operacion_destructiva": (
        "eliminar registros",
        "borrar registros",
        "eliminar datos",
        "borrar datos",
        "eliminar cuenta",
        "borrar cuenta",
        "drop table",
        "truncate table",
        "destruir datos",
    ),
    "operacion_financiera": (
        "transferir fondos",
        "transferencia bancaria",
        "realizar un pago",
        "ejecutar un pago",
        "emitir un reembolso",
        "modificar saldos",
    ),
    "seguridad_y_permisos": (
        "revocar acceso",
        "otorgar permisos",
        "modificar permisos",
        "desactivar firewall",
        "desactivar seguridad",
        "cambiar contrasena",
        "restablecer contrasena",
        "modificar credenciales",
    ),
    "datos_sensibles": (
        "exponer datos personales",
        "publicar datos personales",
        "exportar datos sensibles",
        "modificar datos medicos",
        "modificar datos financieros",
    ),
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())

    without_accents = "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )

    return " ".join(without_accents.split())


def classify_criticality(
    prompt: str,
) -> tuple[bool, str | None]:
    """Aplica reglas explícitas y auditables para identificar riesgos."""

    normalized_prompt = normalize_text(prompt)

    for rule_name, phrases in CRITICAL_RULES.items():
        for phrase in phrases:
            if normalize_text(phrase) in normalized_prompt:
                return True, rule_name

    return False, None