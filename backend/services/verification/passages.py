"""Selección de pasajes (incremento 2, paso 3 del plan): de las páginas descargadas, los trozos
más cercanos a la afirmación para que el LLM los juzgue.

Es una puntuación léxica (BM25) sobre palabras sin tildes ni palabras vacías, con más peso para las
cifras y los nombres propios de la afirmación, que son lo que hay que encontrar en la fuente. No usa
ningún modelo: es determinista, rápida y no consume GPU. Un pasaje solo entra si comparte con la
afirmación al menos `MIN_SHARED_TERMS` palabras distintas y si no parece una orden dirigida al modelo
(`untrusted.py`).
"""

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from backend.core.config import EvidenceLimits
from backend.services.verification.claims import CAPITALIZED, NUMBER, WORD, fold, number_key
from backend.services.verification.fetch import FetchedPage
from backend.services.verification.prompts import one_line
from backend.services.verification.untrusted import looks_like_instruction

MAX_WORDS = 80
MIN_WORDS = 8
MIN_SHARED_TERMS = 2
K1 = 1.2
B = 0.75
SPECIAL_WEIGHT = 2.0
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"“«\d])")

STOPWORDS = frozenset(
    """a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque bajo cada como con contra
    cual cuales cuando de del desde donde dos durante el ella ellas ello ellos en entre era eran es esa esas
    ese eso esos esta estaba estan estar este esto estos fue fueron ha habia han hasta hay la las le les lo los
    mas me mi mis mucho muy nada ni no nos nuestro o os otra otras otro otros para pero poco por porque que
    quien quienes se sea segun ser si sido sin sobre solo son su sus tambien tan tanto te tiene tienen todo
    todos tras tres tu tus un una unas uno unos usted y ya yo""".split()
)


@dataclass(frozen=True)
class Passage:
    id: int  # el número con que el LLM lo ve y lo cita
    fuente: int  # posición de la página en la lista recibida
    texto: str
    puntaje: float


def _terms(text: str) -> list[str]:
    return [w for w in WORD.findall(fold(text)) if len(w) >= 2 and w not in STOPWORDS]


def split_passages(text: str) -> list[str]:
    """Párrafos; los largos se parten por oraciones en trozos de hasta MAX_WORDS palabras."""
    passages = []
    for paragraph in text.split("\n"):
        if len(paragraph.split()) < MIN_WORDS:
            continue
        current: list[str] = []
        count = 0
        for sentence in SENTENCE_END.split(paragraph):
            words = len(sentence.split())
            if current and count + words > MAX_WORDS:
                passages.append(" ".join(current))
                current, count = [], 0
            current.append(sentence)
            count += words
        if current:
            passages.append(" ".join(current))
    return [p for p in passages if len(p.split()) >= MIN_WORDS]


def _special_terms(claim: str) -> set[str]:
    numbers = {number_key(n) for n in NUMBER.findall(claim)}
    names = {part for name in CAPITALIZED.findall(claim) for part in _terms(name)}
    return numbers | names


def select_passages(claim: str, pages: Sequence[FetchedPage], limits: EvidenceLimits) -> list[Passage]:
    """Hasta `passages_per_claim` pasajes, a lo sumo `passages_per_page` por página, el mejor primero."""
    candidates: list[tuple[int, str, Counter]] = []
    for source, page in enumerate(pages):
        for text in split_passages(page.texto):
            if looks_like_instruction(text):
                continue  # una orden dirigida al modelo no es evidencia: ni se puntúa ni se muestra
            candidates.append((source, text, Counter(_terms(text) + [number_key(n) for n in NUMBER.findall(text)])))
    claim_terms = set(_terms(claim)) | {number_key(n) for n in NUMBER.findall(claim)}
    if not candidates or not claim_terms:
        return []
    special = _special_terms(claim)
    total = len(candidates)
    average = sum(sum(c.values()) for _, _, c in candidates) / total
    document_frequency = {t: sum(1 for _, _, c in candidates if t in c) for t in claim_terms}

    scored = []
    for source, text, counts in candidates:
        shared = [t for t in claim_terms if t in counts]
        if len(shared) < min(MIN_SHARED_TERMS, len(claim_terms)):
            continue
        length = sum(counts.values())
        score = 0.0
        for term in shared:
            idf = math.log(1 + (total - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            frequency = counts[term]
            score += (SPECIAL_WEIGHT if term in special else 1.0) * idf * (
                frequency * (K1 + 1) / (frequency + K1 * (1 - B + B * length / average))
            )
        scored.append((score, source, text))

    chosen: list[Passage] = []
    per_page: Counter = Counter()
    for score, source, text in sorted(scored, key=lambda item: -item[0]):
        if per_page[source] >= limits.passages_per_page:
            continue
        per_page[source] += 1
        chosen.append(Passage(id=len(chosen) + 1, fuente=source, texto=one_line(text), puntaje=round(score, 3)))
        if len(chosen) >= limits.passages_per_claim:
            break
    return chosen
