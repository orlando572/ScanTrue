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
from dataclasses import dataclass, field, replace
from datetime import datetime

from backend.core.config import EvidenceLimits
from backend.schemas.verification import SearchQueries, ShortQuery
from backend.services.llm_client import LlmClient
from backend.services.verification.fetch import FetchedPage, FetchError, PageFetcher
from backend.services.verification.judge import Judgment, judge_claim, quote_is_literal
from backend.services.verification.passages import Passage, select_passages
from backend.services.verification.prompts import (
    JUDGE_PROMPT_VERSION,
    QUERY_PROMPT_VERSION,
    query_messages,
    short_query_messages,
)
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
SHORT_QUERY_MAX_TOKENS = 60
# Veredictos con los que la fuente previa basta y no se busca en la web. «fuera_de_contexto» no está: con este modelo es poco
# fiable y salió también cuando la verificación hallada era de otra afirmación (las notas de la fuente previa, sección 9).
PREVIOUS_STOPS = ("apoyada", "contradicha")
# Sitios que en la medición con Tavily nunca entregaron texto (redes y video, todo con JavaScript) y
# ocupaban hasta 1 de cada 4 páginas elegidas: no se descargan (las notas de la Fase 4).
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
    # Se acabó el tiempo de la afirmación antes de reunir toda la evidencia: el resultado no es definitivo.
    incompleta: bool = False
    version_prompts: str = f"{QUERY_PROMPT_VERSION}+{JUDGE_PROMPT_VERSION}"
    # De dónde salió la evidencia: «web» (solo la búsqueda web), «verificadores» (bastó la fuente previa) o
    # «verificadores+web» (se consultó la fuente previa, no bastó y el juicio final se hizo solo con la web).
    # Solo para medir y registrar.
    origen_busqueda: str = "web"
    # Las consultas cortas que se probaron en la fuente previa (distintas de `consultas`, que son las de la web).
    consultas_fuente_previa: list[str] = field(default_factory=list)


def _canonical(url: str) -> str:
    """Para no descargar dos veces lo mismo: sin fragmento, sin parámetros de seguimiento, sin «/» final."""
    base, _, query = url.partition("#")[0].partition("?")
    kept = [p for p in query.split("&") if p and not _TRACKING.match(p.split("=", 1)[0])]
    return base.rstrip("/").lower() + ("?" + "&".join(kept) if kept else "")


def select_results(
    results: Sequence[SearchResult],
    limits: EvidenceLimits,
    exclude_domains: Sequence[str] = (),
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


def _run_queries(
    provider: SearchProvider,
    queries: Sequence[str],
    limits: EvidenceLimits,
    exclude_domains: Sequence[str],
    clock: Callable[[], float],
    deadline: float,
) -> tuple[list[SearchResult], list[SearchError], bool]:
    """Los resultados de todas las consultas en un proveedor, sus fallas y si se acabó el tiempo."""
    results: list[SearchResult] = []
    failures: list[SearchError] = []
    for query in queries:
        if clock() > deadline:
            return results, failures, True
        try:
            results.extend(provider.search(query, max_results=limits.results_per_query, exclude_domains=exclude_domains))
        except SearchError as error:
            failures.append(error)
    return results, failures, False


def _download(
    chosen: Sequence[SearchResult],
    fetcher: PageFetcher,
    exclude_domains: Sequence[str],
    clock: Callable[[], float],
    deadline: float,
    failed: Counter,
) -> tuple[list[FetchedPage], bool]:
    """Descarga los resultados elegidos; las fallas de páginas sueltas se cuentan y no frenan la afirmación."""
    pages: list[FetchedPage] = []
    for result in chosen:
        if clock() > deadline:
            return pages, True
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
    return pages, False


def propose_short_query(client: LlmClient, claim: str) -> str:
    """La consulta corta (2 o 3 palabras clave) para la fuente previa; vacía si no queda nada útil."""
    output = client.complete_json(short_query_messages(claim), ShortQuery, max_tokens=SHORT_QUERY_MAX_TOKENS)
    return clean_query(output.consulta)


def verify_claim(
    claim: str,
    *,
    llm: LlmClient,
    search: SearchProvider,
    fetcher: PageFetcher,
    limits: EvidenceLimits | None = None,
    exclude_domains: Sequence[str] = (),
    clock: Callable[[], float] = time.monotonic,
    previous_search: SearchProvider | None = None,
) -> ClaimVerification:
    """Verifica una afirmación.

    Con `previous_search` (la fuente previa) se busca primero ahí, con la
    consulta corta, y se descargan hasta `limits.previous_pages` páginas. Solo si con esa evidencia el
    juez da «apoyada» o «contradicha» (`PREVIOUS_STOPS`) no se busca en la web. Si no hay nada, o el
    juez dice «insuficiente» o «fuera_de_contexto», se busca en la web como siempre y **el juicio final
    usa solo las páginas de la web**, con el tope completo `pages_per_claim`: las de la fuente previa
    se descartan, porque si eran de otra afirmación estropeaban el veredicto de la web (9.1 del
    documento). Una página que la web también devuelve y que ya se descargó no se baja otra vez. Si la
    fuente previa falla, se sigue con la web: solo la falla de la búsqueda web hace fallar la afirmación.
    """
    limits = limits or EvidenceLimits()
    started = clock()
    deadline = started + limits.claim_seconds
    queries = propose_queries(llm, claim, limits)

    failed: Counter = Counter()
    pages: list[FetchedPage] = []
    results_count = 0
    cut = False
    origin = "web"
    previous_queries: list[str] = []

    def outcome(judgment: Judgment, passages: Sequence[Passage]) -> ClaimVerification:
        return ClaimVerification(
            texto=claim,
            veredicto=judgment.veredicto,
            fuentes=_cited_sources(judgment, passages, pages),
            cita=judgment.cita,
            motivo="sin_resultados" if not results_count else judgment.motivo,
            consultas=queries,
            resultados=results_count,
            paginas=len(pages),
            paginas_fallidas=dict(failed),
            pasajes=len(passages),
            segundos=round(clock() - started, 2),
            incompleta=cut,
            origen_busqueda=origin,
            consultas_fuente_previa=previous_queries,
        )

    if previous_search is not None:
        # La fuente previa solo acierta con pocas palabras clave; la consulta de la web (`queries`) no cambia.
        previous_queries = [q for q in [propose_short_query(llm, claim)] if q]
        previous, failures, cut = _run_queries(previous_search, previous_queries, limits, exclude_domains, clock, deadline)
        for failure in failures:
            logger.warning("La fuente previa no respondió (%s); se sigue con la búsqueda web", failure.code)
        results_count += len(previous)
        previous_limits = replace(limits, pages_per_claim=min(limits.previous_pages, limits.pages_per_claim))
        chosen = select_results(previous, previous_limits, exclude_domains)
        pages, page_cut = _download(chosen, fetcher, exclude_domains, clock, deadline, failed)
        cut = cut or page_cut
        if pages:
            origin = "verificadores+web"
            passages = select_passages(claim, pages, limits)
            if passages:
                judgment = judge_claim(llm, claim, passages)
                if judgment.veredicto in PREVIOUS_STOPS:
                    origin = "verificadores"
                    return outcome(judgment, passages)

    # La fuente previa no bastó (o no se usa): el juicio final es solo con la web. Las páginas ya descargadas de la
    # previa no entran en él, salvo que la web devuelva esa misma dirección (entonces se reutiliza, sin bajarla otra vez).
    downloaded = {_canonical(p.url): p for p in pages}
    pages = []
    results, failures, web_cut = _run_queries(search, queries, limits, exclude_domains, clock, deadline)
    if failures and not results:
        raise failures[0]
    results_count += len(results)
    chosen = select_results(results, limits, exclude_domains)
    reused = [downloaded[_canonical(r.url)] for r in chosen if _canonical(r.url) in downloaded]
    web_pages, page_cut = _download([r for r in chosen if _canonical(r.url) not in downloaded], fetcher, exclude_domains, clock, deadline, failed)
    pages = reused + web_pages
    cut = cut or web_cut or page_cut

    passages = select_passages(claim, pages, limits)
    return outcome(judge_claim(llm, claim, passages), passages)


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
