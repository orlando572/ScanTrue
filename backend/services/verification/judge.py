"""Paso 4 de la verificación: juicio de una afirmación con los pasajes recuperados.

El LLM propone un veredicto, los números de los pasajes en que se basa y una cita literal. El
backend **comprueba** antes de aceptarlo (docs/llm/PLAN_INCREMENTO_2.md, 4.5):

(a) los pasajes citados existen entre los entregados;
(b) la cita aparece textualmente en alguno de ellos;
(c) la URL es una de las recuperadas: el modelo no escribe ninguna, el enlace de cada fuente lo
    pone el backend a partir de la página que descargó, así que no puede inventar un enlace.

Además (d), añadida tras medir (las notas de la Fase 4): una afirmación solo queda `apoyada`
si todos sus nombres propios y cifras aparecen en los pasajes citados. Evita el error más grave,
dar por apoyada una afirmación con un pasaje que habla de otra persona o de otra cifra.

Si una comprobación falla, el veredicto pasa a `insuficiente` y se anota el motivo. Sin pasajes no
se llama al LLM: no hay evidencia, la afirmación queda `insuficiente`.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from backend.schemas.verification import ClaimJudgment
from backend.services.verification.claims import unsupported_names, unsupported_numbers
from backend.services.llm_client import LlmClient
from backend.services.verification.passages import Passage
from backend.services.verification.prompts import judge_messages

JUDGE_MAX_TOKENS = 400
MIN_QUOTE_CHARS = 20
_ELLIPSIS = re.compile(r"\s*(?:\.{3}|…)\s*")
_QUOTES = str.maketrans({"“": None, "”": None, "«": None, "»": None, '"': None, "‘": None, "’": None, "'": None, "–": "-", "—": "-", " ": " "})


@dataclass(frozen=True)
class Judgment:
    veredicto: str
    pasajes: list[int] = field(default_factory=list)  # los citados, ya comprobados
    cita: str = ""
    motivo: str | None = None  # por qué es «insuficiente», si el modelo no lo dijo por sí mismo


def _normalize(text: str) -> str:
    """Mayúsculas, comillas y espacios no cuentan (el modelo suele soltar las « » del pasaje); las palabras y las tildes sí."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(_QUOTES).casefold().split())


def quote_is_literal(quote: str, passage: str) -> bool:
    """La cita está en el pasaje. Cada tramo separado por «…» debe estar tal cual en el pasaje, en orden de aparición."""
    haystack = _normalize(passage)
    fragments = [f for f in (_normalize(part) for part in _ELLIPSIS.split(quote)) if f]
    if not fragments or sum(len(f) for f in fragments) < MIN_QUOTE_CHARS:
        return False
    position = 0
    for fragment in fragments:
        found = haystack.find(fragment, position)
        if found < 0:
            return False
        # El siguiente tramo puede empezar donde empezó este (el modelo a veces repite una frase).
        position = found
    return True


def check_judgment(output: ClaimJudgment, passages: Sequence[Passage], claim: str | None = None) -> Judgment:
    """Aplica las comprobaciones (a), (b) y, si se da la afirmación, (d) al veredicto del modelo."""
    if output.veredicto == "insuficiente":
        return Judgment("insuficiente")
    by_id = {p.id: p for p in passages}
    cited = list(dict.fromkeys(output.pasajes))
    if not cited:
        return Judgment("insuficiente", motivo="sin_pasajes_citados")
    if any(number not in by_id for number in cited):
        return Judgment("insuficiente", motivo="pasaje_inexistente")
    if not any(quote_is_literal(output.cita, by_id[number].texto) for number in cited):
        return Judgment("insuficiente", motivo="cita_no_literal")
    if output.veredicto == "apoyada" and claim is not None:
        source = " ".join(by_id[number].texto for number in cited)
        if unsupported_names(claim, source) or unsupported_numbers(claim, source):
            return Judgment("insuficiente", motivo="apoyo_incompleto")
    return Judgment(output.veredicto, pasajes=cited, cita=" ".join(output.cita.split()))


def judge_claim(client: LlmClient, claim: str, passages: Sequence[Passage]) -> Judgment:
    """Veredicto comprobado de `claim`. Propaga `LlmUnavailable` y `LlmInvalidResponse` sin tocarlas."""
    if not passages:
        return Judgment("insuficiente", motivo="sin_evidencia")
    output = client.complete_json(
        judge_messages(claim, [(p.id, p.texto) for p in passages]), ClaimJudgment, max_tokens=JUDGE_MAX_TOKENS
    )
    return check_judgment(output, passages, claim)
