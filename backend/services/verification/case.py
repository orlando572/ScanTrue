"""Verificación de un caso completo (incremento 2, Fase 5): del texto del análisis al resultado.

    texto ─► afirmaciones (LLM) ─► por cada una: base de verificaciones anteriores ─► o búsqueda y juicio
          ─► conclusión (regla, D4) ─► resumen (LLM, con plantilla de respaldo) ─► resultado a guardar

Las fallas del LLM (`LlmError`) y de la búsqueda (`SearchError`) se propagan: el trabajador decide
si reintenta. Como cada afirmación ya verificada se guarda en la base, un reintento retoma casi todo
sin repetir búsquedas. Si se acaba el tiempo del caso, las afirmaciones que faltan quedan
`insuficiente` y el caso termina con lo que haya (nunca queda colgado).
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

from backend.core.config import EvidenceLimits, LlmSettings, SearchSettings, VerificationSettings
from backend.services.llm_client import LlmClient
from backend.services.verification.claims import ExtractionResult, extract_claims
from backend.services.verification.conclusion import (
    CONCLUSION_VERSION,
    ClaimResult,
    conclude,
    effective_verdict,
    summarize,
    template_summary,
)
from backend.services.verification.fetch import PageFetcher
from backend.services.verification.known_claims import KnownClaimsRepository, find_known_claim, save_known_claim
from backend.services.verification.pipeline import ClaimVerification, Source, verify_claim
from backend.services.verification.prompts import (
    EXTRACTION_PROMPT_VERSION,
    JUDGE_PROMPT_VERSION,
    QUERY_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
)
from backend.services.verification.search import SearchProvider, build_search_provider
from backend.services.verification.worker import VerificationOutcome

logger = logging.getLogger(__name__)

PROMPT_VERSIONS = "+".join(
    (EXTRACTION_PROMPT_VERSION, QUERY_PROMPT_VERSION, JUDGE_PROMPT_VERSION, SUMMARY_PROMPT_VERSION, CONCLUSION_VERSION)
)
EXPIRED = "tiempo_agotado"


class AnalysisNotFound(RuntimeError):
    """El análisis ya no existe (por ejemplo, su dueño lo borró mientras esperaba en la cola)."""

    code = "analisis_no_encontrado"


class CaseRepository(KnownClaimsRepository, Protocol):
    def analysis_text(self, analysis_id: UUID) -> str | None: ...


def source_dict(source: Source) -> dict:
    return {
        "titulo": source.titulo,
        "url": source.url,
        "dominio": source.dominio,
        "extracto": source.extracto,
        "consultada_en": source.consultada_en.isoformat(),
    }


def build_outcome(
    conclusion: str, summary: str, results: Sequence[ClaimResult], model: str | None
) -> VerificationOutcome:
    """Arma los jsonb del plan (4.3): afirmaciones con `fuente_ids` y fuentes numeradas sin repetir la URL."""
    sources: list[dict] = []
    ids_by_url: dict[str, int] = {}
    claims: list[dict] = []
    for number, result in enumerate(results, start=1):
        source_ids: list[int] = []
        for source in result.fuentes:
            url = source.get("url")
            if not isinstance(url, str):
                continue
            if url not in ids_by_url:
                ids_by_url[url] = len(sources) + 1
                sources.append({"id": ids_by_url[url], **{k: v for k, v in source.items() if k != "id"}})
            if ids_by_url[url] not in source_ids:
                source_ids.append(ids_by_url[url])
        claims.append({
            "id": number,
            "texto": result.texto,
            "veredicto": effective_verdict(result),
            "fuente_ids": source_ids,
            "origen": result.origen,
        })
    return VerificationOutcome(
        conclusion=conclusion, summary=summary, claims=claims, sources=sources, model=model, prompt_version=PROMPT_VERSIONS
    )


class CaseVerifier:
    """Procesa un análisis de principio a fin. Es el `process` del trabajador de la cola."""

    def __init__(
        self,
        repository: CaseRepository,
        llm: LlmClient,
        search: SearchProvider,
        fetcher: PageFetcher,
        *,
        limits: EvidenceLimits | None = None,
        case_seconds: float = 300.0,
        exclude_domains: Sequence[str] = (),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.repository = repository
        self.llm = llm
        self.search = search
        self.fetcher = fetcher
        self.limits = limits or EvidenceLimits()
        self.case_seconds = case_seconds
        self.exclude_domains = exclude_domains
        self._clock = clock

    def __call__(self, analysis_id: UUID) -> VerificationOutcome:
        return self.verify(analysis_id)

    def verify(self, analysis_id: UUID) -> VerificationOutcome:
        started = self._clock()
        text = self.repository.analysis_text(analysis_id)
        if not text:
            raise AnalysisNotFound(f"El análisis {analysis_id} no existe o no tiene texto.")
        extraction = extract_claims(self.llm, text)
        if extraction.ordenes_descartadas:
            logger.warning(
                "Caso %s: se quitaron %d frases del texto que parecían órdenes al modelo",
                analysis_id, extraction.ordenes_descartadas,
            )
        results = [self._verify_claim(claim.texto, analysis_id, started) for claim in extraction.afirmaciones]
        conclusion = conclude(results)
        summary = self._summary(conclusion, results, extraction)
        outcome = build_outcome(conclusion, summary, results, self.llm.settings.model)
        logger.info(
            "Caso %s: %d afirmaciones (%d rechazadas), conclusión %s, %.1f s",
            analysis_id, len(results), len(extraction.rechazadas), conclusion, self._clock() - started,
        )
        return outcome

    def _verify_claim(self, claim: str, analysis_id: UUID, case_started: float) -> ClaimResult:
        known = find_known_claim(self.repository, claim)
        if known is not None:
            return ClaimResult(claim, known.veredicto, [dict(s) for s in known.fuentes if isinstance(s, dict)], "base_anterior")
        remaining = self.case_seconds - (self._clock() - case_started)
        if remaining <= 0:
            return ClaimResult(claim, "insuficiente", motivo=EXPIRED)
        limits = replace(self.limits, claim_seconds=min(self.limits.claim_seconds, remaining))
        verification = verify_claim(
            claim, llm=self.llm, search=self.search, fetcher=self.fetcher, limits=limits,
            exclude_domains=self.exclude_domains, clock=self._clock,
        )
        sources = [source_dict(source) for source in verification.fuentes]
        self._remember(verification, sources, analysis_id)
        return ClaimResult(claim, verification.veredicto, sources, "busqueda", verification.motivo)

    def _remember(self, verification: ClaimVerification, sources: list[dict], analysis_id: UUID) -> None:
        """Guarda la afirmación en la base para reutilizarla; un fallo aquí no afecta al caso."""
        if verification.incompleta:
            return  # el resultado no es definitivo: no se propaga a otros casos
        try:
            save_known_claim(
                self.repository, verification.texto, verification.veredicto, sources,
                model=self.llm.settings.model, prompt_version=PROMPT_VERSIONS, analysis_id=analysis_id,
            )
        except Exception:
            logger.warning("No se pudo guardar la afirmación verificada", exc_info=True)

    def _summary(self, conclusion: str, results: Sequence[ClaimResult], extraction: ExtractionResult) -> str:
        if not results:
            return template_summary(conclusion, results, rejected=len(extraction.rechazadas))
        summary, _written = summarize(self.llm, conclusion, results)
        return summary


def build_case_verifier(repository: CaseRepository, verification: VerificationSettings) -> CaseVerifier | None:
    """El verificador con la configuración del entorno, o None (con el motivo en el registro) si falta algo."""
    try:
        llm_settings = LlmSettings.from_environment()
        search_settings = SearchSettings.from_environment()
        limits = EvidenceLimits.from_environment()
    except ValueError:
        logger.exception("La configuración de la verificación (LLM, búsqueda o límites) no es válida")
        return None
    if llm_settings is None:
        logger.error("VERIFICATION_ENABLED requiere LLM_BASE_URL; la cola no arranca")
        return None
    if search_settings is None:
        logger.error("VERIFICATION_ENABLED requiere SEARCH_PROVIDER y SEARCH_API_KEY; la cola no arranca")
        return None
    return CaseVerifier(
        repository, LlmClient(llm_settings), build_search_provider(search_settings), PageFetcher(limits),
        limits=limits, case_seconds=verification.case_seconds,
    )
