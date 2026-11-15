"""Base de afirmaciones ya verificadas (incremento 2, Fase 3; ver docs/llm/BASE_AFIRMACIONES.md).

Antes de buscar en internet, cada afirmación se busca aquí. **Solo se reutiliza la coincidencia
exacta** del texto normalizado: la medición de docs/llm/BASE_AFIRMACIONES.md mostró que ningún
umbral de similitud de trigramas separa una paráfrasis (similitud mediana 0,42) de un cambio de un
solo dato como «Florida» por «Texas» o «dos» por «tres» (hasta 0,97), y reutilizar mal un
veredicto es peor que no reutilizar. La búsqueda por similitud sigue disponible (`threshold`), con
comprobaciones de cifras y negación, pero está apagada. La vigencia (30 días, o 7 si el veredicto
fue insuficiente) la aplica la base.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from backend.services.verification.claims import NUMBER, WORD, fold, number_key

VERDICTS = ("apoyada", "contradicha", "fuera_de_contexto", "insuficiente")
# Umbral de similitud de pg_trgm; None = búsqueda por similitud apagada (solo coincidencia exacta).
SIMILARITY_THRESHOLD: float | None = None
NEGATIONS = frozenset({
    "no", "nunca", "ni", "sin", "tampoco", "jamas", "ningun", "ninguno", "ninguna", "nadie", "nada",
})


def normalize_claim(text: str) -> str:
    """Minúsculas, sin tildes ni signos de puntuación y con los espacios colapsados."""
    plain = re.sub(r"[^\w\s]", " ", fold(text))
    return re.sub(r"\s+", " ", plain).strip()


def claim_hash(normalized: str) -> str:
    return sha256(normalized.encode("utf-8")).hexdigest()


def numbers_of(text: str) -> frozenset[str]:
    return frozenset(number_key(n) for n in NUMBER.findall(text))


def negations_of(text: str) -> frozenset[str]:
    return frozenset(WORD.findall(fold(text))) & NEGATIONS


def compatible(new: str, stored: str) -> bool:
    """Misma lista de cifras y mismas negaciones: sin eso, parecerse no basta."""
    return numbers_of(new) == numbers_of(stored) and negations_of(new) == negations_of(stored)


@dataclass(frozen=True)
class KnownClaim:
    id: UUID
    texto: str
    veredicto: str
    fuentes: list = field(default_factory=list)
    modelo_llm: str | None = None
    version_prompts: str | None = None
    verificado_en: datetime | None = None
    expira_en: datetime | None = None
    similitud: float = 1.0
    exacta: bool = True

    # Se muestra como tal en la verificación (`origen` de cada afirmación).
    origen = "base_anterior"


class KnownClaimsRepository(Protocol):
    def find_verified_claims(
        self, claim_hash: str, normalized: str, threshold: float | None, limit: int = 5
    ) -> list[dict]: ...
    def save_verified_claim(
        self, *, text: str, normalized: str, claim_hash: str, verdict: str, sources: list,
        model: str | None, prompt_version: str | None, analysis_id: UUID | None,
    ) -> UUID: ...


def _known(row: dict) -> KnownClaim:
    def when(value):
        return datetime.fromisoformat(value) if value else None

    return KnownClaim(
        id=UUID(row["id"]), texto=row["texto"], veredicto=row["veredicto"],
        fuentes=row.get("fuentes") or [], modelo_llm=row.get("modelo_llm"),
        version_prompts=row.get("version_prompts"), verificado_en=when(row.get("verificado_en")),
        expira_en=when(row.get("expira_en")), similitud=float(row.get("similitud", 1.0)),
        exacta=bool(row.get("exacta", True)),
    )


def find_known_claim(
    repository: KnownClaimsRepository, claim: str, *, threshold: float | None = SIMILARITY_THRESHOLD
) -> KnownClaim | None:
    """La afirmación ya verificada y vigente que corresponde a `claim`, o None.

    Con `threshold=None` solo cuenta la coincidencia exacta del texto normalizado.
    """
    normalized = normalize_claim(claim)
    if not normalized:
        return None
    for row in repository.find_verified_claims(claim_hash(normalized), normalized, threshold):
        known = _known(row)
        if known.exacta or compatible(claim, known.texto):
            return known
    return None


def save_known_claim(
    repository: KnownClaimsRepository,
    claim: str,
    verdict: str,
    sources: list,
    *,
    model: str | None,
    prompt_version: str | None,
    analysis_id: UUID | None = None,
) -> UUID:
    """Guarda una afirmación verificada; si ya estaba, se actualiza y se renueva su vigencia."""
    if verdict not in VERDICTS:
        raise ValueError(f"Veredicto no válido: {verdict!r}")
    normalized = normalize_claim(claim)
    if not normalized:
        raise ValueError("La afirmación está vacía.")
    return repository.save_verified_claim(
        text=claim, normalized=normalized, claim_hash=claim_hash(normalized), verdict=verdict,
        sources=sources, model=model, prompt_version=prompt_version, analysis_id=analysis_id,
    )
