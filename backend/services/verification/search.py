"""Búsqueda web de la verificación (incremento 2, paso 3 del plan).

El backend ejecuta la búsqueda; el LLM solo propone las consultas y nunca toca internet. El código
depende únicamente de `SearchProvider`: cambiar de proveedor (D3) no rehace nada más.

A los buscadores salen solo las consultas, escritas a partir de la afirmación: nunca la URL del
usuario ni su identidad. Los registros no incluyen ni la consulta ni la clave de API.
"""

import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from backend.core.config import SearchSettings

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 300
RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
DEFAULT_RETRIES = 1


class SearchError(RuntimeError):
    """La búsqueda no entregó resultados. `code` es lo que se guarda en `ultimo_error`."""

    code = "busqueda_fallida"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


@dataclass(frozen=True)
class SearchResult:
    titulo: str
    url: str
    fragmento: str
    dominio: str
    posicion: int


class SearchProvider(Protocol):
    name: str

    def search(
        self, query: str, *, max_results: int = 5, exclude_domains: Sequence[str] = ()
    ) -> list[SearchResult]: ...


def domain_of(url: str) -> str:
    """Dominio en minúsculas y sin «www.»; vacío si la URL no tiene host."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def is_excluded(domain: str, excluded: Sequence[str]) -> bool:
    """El dominio, o cualquiera de sus subdominios, está en la lista (D7, al evaluar)."""
    for item in excluded:
        base = item.lower().strip().removeprefix("www.").rstrip(".")
        if base and (domain == base or domain.endswith("." + base)):
            return True
    return False


def clean_query(query: str) -> str:
    """Sin direcciones web, correos ni caracteres de control, y con un tope de longitud."""
    text = re.sub(r"https?://\S+|www\.\S+|\S+@\S+\.\S+", " ", query)
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    return " ".join(text.split())[:MAX_QUERY_CHARS]


class _HttpSearch:
    """Base de los proveedores: cliente HTTP, reintento de fallas pasajeras y errores uniformes."""

    name = ""

    def __init__(
        self,
        api_key: str,
        timeout: float = 15.0,
        *,
        retries: int = DEFAULT_RETRIES,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
            transport=transport,
            trust_env=False,
            headers={"Accept": "application/json"},
        )
        self._api_key = api_key
        self._retries = max(0, retries)
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def _send(self, request: httpx.Request) -> dict:
        error: SearchError | None = None
        for attempt in range(self._retries + 1):
            try:
                response = self._client.send(request)
            except httpx.TimeoutException:
                raise SearchError(f"{self.name}: la búsqueda no respondió a tiempo.") from None
            except httpx.TransportError as exc:
                error = SearchError(f"{self.name}: no se pudo conectar ({type(exc).__name__}).")
            else:
                if response.is_success:
                    try:
                        data = response.json()
                    except ValueError:
                        raise SearchError(f"{self.name}: la respuesta no es JSON.") from None
                    if not isinstance(data, dict):
                        raise SearchError(f"{self.name}: la respuesta no tiene el formato esperado.")
                    return data
                code = response.status_code
                if code in (401, 403):
                    raise SearchError(f"{self.name}: clave de API rechazada.", "busqueda_no_autorizada")
                if code in (402, 429, 432, 433):
                    raise SearchError(
                        f"{self.name}: cupo o límite de uso agotado (HTTP {code}).", "busqueda_cupo_agotado"
                    )
                error = SearchError(f"{self.name}: respondió HTTP {code}.")
                if code not in RETRYABLE_STATUS:
                    raise error
            if attempt < self._retries:
                logger.warning("Búsqueda %s no disponible; reintento %d", self.name, attempt + 1)
                self._sleep(1.0)
        assert error is not None
        raise error

    @staticmethod
    def _result(item: object, position: int, text_key: str) -> SearchResult | None:
        if not isinstance(item, dict):
            return None
        url = item.get("url")
        if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
            return None
        domain = domain_of(url)
        if not domain:
            return None
        return SearchResult(
            titulo=" ".join(str(item.get("title") or "").split()),
            url=url,
            fragmento=" ".join(str(item.get(text_key) or "").split()),
            dominio=domain,
            posicion=position,
        )


class BraveSearch(_HttpSearch):
    """Brave Search API (GET /res/v1/web/search). Excluye dominios con `-site:` en la consulta."""

    name = "brave"
    URL = "https://api.search.brave.com/res/v1/web/search"

    def search(
        self, query: str, *, max_results: int = 5, exclude_domains: Sequence[str] = ()
    ) -> list[SearchResult]:
        text = clean_query(query)
        if not text:
            return []
        exclusions = " ".join(f"-site:{d.strip()}" for d in exclude_domains if d.strip())
        request = self._client.build_request(
            "GET",
            self.URL,
            params={"q": f"{text} {exclusions}".strip(), "count": min(max(max_results, 1), 20), "search_lang": "es"},
            headers={"X-Subscription-Token": self._api_key},
        )
        data = self._send(request)
        items = (data.get("web") or {}).get("results") or []
        results = [self._result(item, n, "description") for n, item in enumerate(items, start=1)]
        return [r for r in results if r is not None][:max_results]


class TavilySearch(_HttpSearch):
    """Tavily Search API (POST /search, búsqueda básica: 1 crédito). Excluye con `exclude_domains`."""

    name = "tavily"
    URL = "https://api.tavily.com/search"

    def search(
        self, query: str, *, max_results: int = 5, exclude_domains: Sequence[str] = ()
    ) -> list[SearchResult]:
        text = clean_query(query)
        if not text:
            return []
        body: dict = {
            "query": text,
            "search_depth": "basic",
            "topic": "general",
            "max_results": min(max(max_results, 1), 20),
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        excluded = [d.strip() for d in exclude_domains if d.strip()]
        if excluded:
            body["exclude_domains"] = excluded
        request = self._client.build_request(
            "POST", self.URL, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
        )
        data = self._send(request)
        items = data.get("results") or []
        results = [self._result(item, n, "content") for n, item in enumerate(items, start=1)]
        return [r for r in results if r is not None][:max_results]


PROVIDERS: dict[str, type[_HttpSearch]] = {"brave": BraveSearch, "tavily": TavilySearch}


def build_search_provider(
    settings: SearchSettings, *, transport: httpx.BaseTransport | None = None
) -> SearchProvider:
    return PROVIDERS[settings.provider](settings.api_key, settings.timeout, transport=transport)
