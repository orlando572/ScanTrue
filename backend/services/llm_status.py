"""¿Responde el servidor del LLM? Una consulta ligera, con caché, para `/salud` y el panel.

`/salud` la usa la extensión con frecuencia, así que la comprobación nunca puede frenarla: espera
poco (`timeout`), recuerda el último resultado unos segundos (`ttl`) y, si falla, responde «no
disponible» sin lanzar. No manda texto de ningún análisis ni registra la clave de API.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from backend.core.config import LlmSettings

DEFAULT_TTL = 15.0
DEFAULT_TIMEOUT = 1.5


@dataclass(frozen=True)
class LlmAvailability:
    configurado: bool
    disponible: bool


class LlmProbe:
    def __init__(
        self,
        settings: LlmSettings | None,
        *,
        ttl: float = DEFAULT_TTL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._checked_at: float | None = None
        self._available = False
        self._client = None
        if settings is not None:
            headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
            self._client = httpx.Client(
                base_url=settings.base_url, headers=headers, transport=transport,
                timeout=httpx.Timeout(timeout), trust_env=False,
            )

    def status(self) -> LlmAvailability:
        if self._client is None:
            return LlmAvailability(configurado=False, disponible=False)
        with self._lock:
            now = self._clock()
            if self._checked_at is None or now - self._checked_at >= self._ttl:
                self._available = self._ping()
                self._checked_at = now
            return LlmAvailability(configurado=True, disponible=self._available)

    def _ping(self) -> bool:
        try:
            return self._client.get("models").is_success
        except httpx.HTTPError:
            return False
