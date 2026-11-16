"""Tabla de equivalencias: del veredicto de un medio de verificación a una de las cuatro conclusiones.

Se escribe **antes** de etiquetar (docs/llm/PLAN_INCREMENTO_2.md, 5.2) y no se cambia mirando el
resultado del sistema. Lo ambiguo no se traduce: el caso se descarta (`None`), porque una etiqueta
dudosa estropea la medición más que la falta de un caso. Si un medio usa una palabra que no está
aquí, el caso se descarta o la tabla se amplía **por escrito y antes de correr nada**.
"""

import re

from backend.services.verification.text import fold

TABLE_VERSION = "equivalencias-v1"

# Ratings sin tildes ni mayúsculas. «sin contexto» y «engañoso» son `fuera_de_contexto` por el plan.
EQUIVALENCES: dict[str, list[str]] = {
    "contradicha": [
        "falso", "falsa", "bulo", "es falso", "es falsa", "fake", "mentira", "desinformacion", "no es cierto",
        "no es verdad", "falso rotundo", "totalmente falso",
    ],
    "fuera_de_contexto": [
        "enganoso", "enganosa", "sin contexto", "descontextualizado", "descontextualizada", "fuera de contexto",
        "contexto erroneo", "falta contexto", "le falta contexto", "no es de ahora", "no es reciente",
    ],
    "evidencia_insuficiente": [
        "sin pruebas", "sin evidencia", "sin evidencias", "no hay pruebas", "no hay evidencia", "no verificable",
        "inverificable", "inchequeable", "no se puede comprobar", "no comprobable", "no se puede verificar",
        "sin confirmar", "no confirmado",
    ],
    "respaldada": ["verdadero", "verdadera", "cierto", "cierta", "verdad", "es verdad", "es cierto", "veridico"],
}
# Veredictos que no se traducen: el caso se descarta.
AMBIGUOUS = [
    "verdad a medias", "apresurado", "discutible", "exagerado", "impreciso", "parcialmente falso",
    "parcialmente cierto", "verdadero pero", "cierto pero", "mixto", "satira", "sin matices", "en parte",
    "pendiente",
]


def normalize(rating: str) -> str:
    plain = re.sub(r"[^\w\s]", " ", fold(rating or "").replace("ñ", "n"))
    return re.sub(r"\s+", " ", plain).strip()


def conclusion_for(rating: str) -> str | None:
    """La conclusión que corresponde al veredicto original, o None si es ambiguo o no está en la tabla."""
    key = normalize(rating)
    if not key or any(key == normalize(item) or key.startswith(normalize(item) + " ") for item in AMBIGUOUS):
        return None
    for conclusion, ratings in EQUIVALENCES.items():
        if key in {normalize(item) for item in ratings}:
            return conclusion
    return None


def as_json() -> dict:
    """Para guardar junto a los casos (`equivalencias.json`) y entrar en el manifiesto."""
    return {"version": TABLE_VERSION, "equivalencias": EQUIVALENCES, "ambiguos_se_descartan": AMBIGUOUS}
