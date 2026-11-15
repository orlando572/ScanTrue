"""Paso 5 de la verificación: conclusión del caso y resumen (incremento 2, D4).

La conclusión la decide una regla **determinista**, no el LLM, para que sea explicable y medible. El
LLM solo redacta el resumen, y si falla o escribe algo no válido se usa un resumen armado con una
plantilla, de modo que un caso nunca se queda sin resumen por culpa del modelo.

Versión `conclusion-v1` (docs/llm/PLAN_INCREMENTO_2.md, 4.5). Dos cosas se afinan en la Fase 7, con
la evaluación, y por ahora son lo más simple:

- «Afirmación central»: todas las afirmaciones extraídas cuentan por igual (son pocas, máximo 5).
- `fuera_de_contexto`: el caso lo es si ninguna afirmación está contradicha, alguna está
  `fuera_de_contexto` y todas las demás tienen evidencia (`apoyada` o `fuera_de_contexto`).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from backend.schemas.verification import CaseSummary
from backend.services.llm_client import LlmClient, LlmInvalidResponse
from backend.services.verification.prompts import SUMMARY_PROMPT_VERSION, summary_messages

CONCLUSION_VERSION = "conclusion-v1"
SUMMARY_MAX_TOKENS = 300
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
# El sistema no sabe cuán fiable es una fuente: el resumen no debe afirmarlo.
_RELIABILITY = re.compile(r"confiabl|fiables?|fidedign|veraz|verosímil|independiente", re.IGNORECASE)

CONCLUSION_LABELS = {
    "respaldada": "Respaldada por fuentes",
    "contradicha": "Contradicha por fuentes",
    "fuera_de_contexto": "Fuera de contexto",
    "evidencia_insuficiente": "Evidencia insuficiente",
}
VERDICT_LABELS = {
    "apoyada": "respaldada por fuentes",
    "contradicha": "contradicha por fuentes",
    "fuera_de_contexto": "confirmada, pero en otro contexto",
    "insuficiente": "sin evidencia suficiente",
}
# Para la plantilla del resumen, cuando son varias afirmaciones («3 respaldadas por fuentes»).
VERDICT_PLURALS = {
    "apoyada": "respaldadas por fuentes",
    "contradicha": "contradichas por fuentes",
    "fuera_de_contexto": "confirmadas, pero en otro contexto",
    "insuficiente": "sin evidencia suficiente",
}


@dataclass(frozen=True)
class ClaimResult:
    """El resultado de verificar una afirmación; `fuentes` son diccionarios listos para guardar."""

    texto: str
    veredicto: str
    fuentes: list[dict] = field(default_factory=list)
    origen: str = "busqueda"  # «busqueda» o «base_anterior»
    motivo: str | None = None


def effective_verdict(result: ClaimResult) -> str:
    """Un veredicto con evidencia (`apoyada`, `contradicha`, `fuera_de_contexto`) exige al menos una fuente."""
    if result.veredicto != "insuficiente" and not result.fuentes:
        return "insuficiente"
    return result.veredicto


def conclude(results: Sequence[ClaimResult]) -> str:
    """Conclusión del caso según la tabla de 4.5; sin afirmaciones, `evidencia_insuficiente`."""
    verdicts = [effective_verdict(r) for r in results]
    if not verdicts:
        return "evidencia_insuficiente"
    if "contradicha" in verdicts:
        return "contradicha"
    if all(v == "apoyada" for v in verdicts):
        return "respaldada"
    if "fuera_de_contexto" in verdicts and all(v in ("apoyada", "fuera_de_contexto") for v in verdicts):
        return "fuera_de_contexto"
    return "evidencia_insuficiente"


def template_summary(conclusion: str, results: Sequence[ClaimResult], rejected: int = 0) -> str:
    """Resumen sin LLM: cuántas afirmaciones se comprobaron y con qué resultado."""
    if not results:
        if rejected:
            return (
                "Se encontraron afirmaciones en el texto, pero ninguna se pudo contrastar con él de forma fiable, "
                "así que no se verificó ninguna con fuentes externas."
            )
        return "No se encontraron afirmaciones concretas que se puedan comprobar con fuentes externas en este texto."
    counts = {key: 0 for key in VERDICT_LABELS}
    for result in results:
        counts[effective_verdict(result)] += 1
    parts = [f"{n} {VERDICT_LABELS[key] if n == 1 else VERDICT_PLURALS[key]}" for key, n in counts.items() if n]
    noun = "afirmación" if len(results) == 1 else "afirmaciones"
    return (
        f"Se comprobaron {len(results)} {noun} del texto con fuentes externas: {', '.join(parts)}. "
        f"Conclusión: {CONCLUSION_LABELS[conclusion].lower()}."
    )


def _usable(summary: str) -> bool:
    return 40 <= len(summary) <= 600 and not _URL.search(summary) and not _RELIABILITY.search(summary)


def summarize(client: LlmClient, conclusion: str, results: Sequence[ClaimResult]) -> tuple[str, bool]:
    """(resumen, lo escribió el LLM). Si la respuesta no sirve, el de la plantilla.

    Una falla del servidor (`LlmUnavailable`) sí se propaga: si el LLM está caído, el caso se reintenta.
    """
    rows = [(r.texto, VERDICT_LABELS[effective_verdict(r)]) for r in results]
    try:
        output = client.complete_json(
            summary_messages(CONCLUSION_LABELS[conclusion], rows), CaseSummary, max_tokens=SUMMARY_MAX_TOKENS
        )
    except LlmInvalidResponse:
        return template_summary(conclusion, results), False
    text = " ".join(output.resumen.split())
    if not _usable(text):
        return template_summary(conclusion, results), False
    return text, True


__all__ = ["CONCLUSION_VERSION", "SUMMARY_PROMPT_VERSION", "ClaimResult", "conclude", "summarize", "template_summary"]
