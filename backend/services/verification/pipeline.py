"""Verificación de una afirmación contra la web (incremento 2, pasos 3 y 4 del plan).

    consultas (LLM) ─► búsqueda ─► páginas elegidas ─► descarga ─► pasajes ─► juicio (LLM + comprobaciones)

Devuelve el veredicto con las fuentes **citadas**: el enlace de cada una es el de una página que el
backend descargó. La conclusión del caso, el resumen y el trabajador son de la Fase 5.

Si la búsqueda falla (`SearchError`) o el LLM falla (`LlmError`), la falla se propaga: el trabajador
decide si reintenta. Las fallas de páginas sueltas no frenan la afirmación: se cuentan y se sigue.
"""

import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from backend.core.config import EvidenceLimits
from backend.schemas.verification import SearchQueries
from backend.services.llm_client import LlmClient
from backend.services.verification.fetch import FetchedPage, FetchError, PageFetcher
from backend.services.verification.judge import Judgment, judge_claim, quote_is_literal
from backend.services.verification.passages import Passage, select_passages
from backend.services.verification.prompts import JUDGE_PROMPT_VERSION, QUERY_PROMPT_VERSION, query_messages
from backend.services.verification.search import (
    SearchError,
    SearchProvider,
    SearchResult,
    clean_query,
    domain_of,
    is_excluded,
)

logger = logging.getLogger(__name__)

QUERY_MAX_TOKENS = 300
# Sitios que en la medición con Tavily nunca entregaron texto (redes y video, todo con JavaScript) y
# ocupaban hasta 1 de cada 4 páginas elegidas: no se descargan (docs/llm/BUSQUEDA_Y_JUICIO.md).
NO_TEXT_DOMAINS = (
    "facebook.com", "youtube.com", "youtu.be", "tiktok.com", "instagram.com", "x.com", "twitter.com",
    "linkedin.com", "dailymotion.com", "pinterest.com", "t.me",
)
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$)", re.IGNORECASE)


@dataclass(frozen=True)
class Source:
    """Una fuente citada. `extracto` es la cita literal; `url` es de una página descargada."""

    titulo: str
    url: str
    dominio: str
    extracto: str
    consultada_en: datetime


@dataclass(frozen=True)
class ClaimVerification:
    texto: str
    veredicto: str
    fuentes: list[Source]
    cita: str
    motivo: str | None
    consultas: list[str]
    resultados: int  # resultados de búsqueda recibidos
    paginas: int  # páginas descargadas con texto
    paginas_fallidas: dict[str, int] = field(default_factory=dict)  # código de FetchError -> cuántas
    pasajes: int = 0
    segundos: float = 0.0
    version_prompts: str = f"{QUERY_PROMPT_VERSION}+{JUDGE_PROMPT_VERSION}"


def _canonical(url: str) -> str:
    """Para no descargar dos veces lo mismo: sin fragmento, sin parámetros de seguimiento, sin «/» final."""
    base, _, query = url.partition("#")[0].partition("?")
    kept = [p for p in query.split("&") if p and not _TRACKING.match(p.split("=", 1)[0])]
    return base.rstrip("/").lower() + ("?" + "&".join(kept) if kept else "")


def select_results(
    results: Sequence[SearchResult], limits: EvidenceLimits, exclude_domains: Sequence[str] = ()
) -> list[SearchResult]:
    """Los resultados a descargar: sin dominios excluidos ni repetidos, con tope por dominio y en total."""
    chosen: list[SearchResult] = []
    seen: set[str] = set()
    per_domain: Counter = Counter()
    for result in results:
        key = _canonical(result.url)
        if key in seen or is_excluded(result.dominio, exclude_domains) or is_excluded(result.dominio, NO_TEXT_DOMAINS):
            continue
        if per_domain[result.dominio] >= limits.per_domain:
            continue
        seen.add(key)
        per_domain[result.dominio] += 1
        chosen.append(result)
        if len(chosen) >= limits.pages_per_claim:
            break
    return chosen


def propose_queries(client: LlmClient, claim: str, limits: EvidenceLimits) -> list[str]:
    """Las consultas que propone el LLM, limpias (sin direcciones web) y sin repetir."""
    output = client.complete_json(query_messages(claim), SearchQueries, max_tokens=QUERY_MAX_TOKENS)
    queries: list[str] = []
    for raw in output.consultas:
        text = clean_query(raw)
        if text and text.lower() not in {q.lower() for q in queries}:
            queries.append(text)
    return queries[: limits.queries_per_claim]


def verify_claim(
    claim: str,
    *,
    llm: LlmClient,
    search: SearchProvider,
    fetcher: PageFetcher,
    limits: EvidenceLimits | None = None,
    exclude_domains: Sequence[str] = (),
    clock: Callable[[], float] = time.monotonic,
) -> ClaimVerification:
    limits = limits or EvidenceLimits()
    started = clock()
    deadline = started + limits.claim_seconds
    queries = propose_queries(llm, claim, limits)

    results: list[SearchResult] = []
    failures: list[SearchError] = []
    for query in queries:
        if clock() > deadline:
            break
        try:
            results.extend(search.search(query, max_results=limits.results_per_query, exclude_domains=exclude_domains))
        except SearchError as error:
            failures.append(error)
    if failures and not results:
        raise failures[0]

    pages: list[FetchedPage] = []
    failed: Counter = Counter()
    for result in select_results(results, limits, exclude_domains):
        if clock() > deadline:
            break
        try:
            page = fetcher.fetch(result.url)
        except FetchError as error:
            failed[error.code] += 1
            continue
        # La redirección pudo llevar a un dominio excluido: se vuelve a comprobar con el destino.
        if is_excluded(domain_of(page.url), exclude_domains) or not page.texto:
            failed["sin_texto_util" if not page.texto else "dominio_excluido"] += 1
            continue
        pages.append(page)

    passages = select_passages(claim, pages, limits)
    judgment = judge_claim(llm, claim, passages)
    return ClaimVerification(
        texto=claim,
        veredicto=judgment.veredicto,
        fuentes=_cited_sources(judgment, passages, pages),
        cita=judgment.cita,
        motivo="sin_resultados" if not results else judgment.motivo,
        consultas=queries,
        resultados=len(results),
        paginas=len(pages),
        paginas_fallidas=dict(failed),
        pasajes=len(passages),
        segundos=round(clock() - started, 2),
    )


def _cited_sources(judgment: Judgment, passages: Sequence[Passage], pages: Sequence[FetchedPage]) -> list[Source]:
    """Una fuente por página cuyo pasaje citado contiene la cita literal; solo URL descargadas."""
    by_id = {p.id: p for p in passages}
    sources: dict[int, Source] = {}
    for number in judgment.pasajes:
        passage = by_id.get(number)
        if passage is None or passage.fuente in sources or not quote_is_literal(judgment.cita, passage.texto):
            continue
        page = pages[passage.fuente]
        sources[passage.fuente] = Source(
            titulo=page.titulo or domain_of(page.url),
            url=page.url,
            dominio=domain_of(page.url),
            extracto=judgment.cita,
            consultada_en=page.consultada_en,
        )
    return list(sources.values())
