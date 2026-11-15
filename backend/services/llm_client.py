"""Cliente del servidor LLM (llama-server) con API tipo OpenAI y salida JSON forzada.

Distingue dos tipos de falla, porque el trabajador de verificación las trata distinto:

- `LlmUnavailable`: el servidor no entregó una respuesta (no conecta, se agotó el tiempo,
  clave rechazada, error HTTP). Se pueden reintentar más tarde.
- `LlmInvalidResponse`: el servidor respondió, pero no con un JSON que cumpla el esquema
  (vacío, cortado por `max_tokens`, o con campos que no corresponden).

Cada excepción trae `code`, con los valores que la tabla `verificaciones_web` guarda en
`ultimo_error`: `llm_no_disponible`, `tiempo_agotado`, `no_autorizado` o `salida_invalida`.
Nunca se registra el texto enviado ni el recibido, ni la clave de API.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.core.config import LlmSettings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Estados que suelen ser pasajeros (el servidor aún carga el modelo o está saturado).
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
DEFAULT_RETRIES = 2
CONNECT_TIMEOUT = 5.0


class LlmError(RuntimeError):
    code = "llm_no_disponible"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class LlmUnavailable(LlmError):
    """El servidor no entregó una respuesta."""


class LlmInvalidResponse(LlmError):
    """El servidor respondió, pero no con un JSON válido para el esquema."""

    code = "salida_invalida"


class LlmClient:
    """Cliente síncrono: lo usa el trabajador de verificación desde un hilo."""

    def __init__(
        self,
        settings: LlmSettings,
        *,
        retries: int = DEFAULT_RETRIES,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.retries = max(0, retries)
        self._sleep = sleep
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        self._client = httpx.Client(
            base_url=settings.base_url,
            headers=headers,
            # `timeout` es lo máximo que se espera por la respuesta del modelo.
            timeout=httpx.Timeout(settings.timeout, connect=min(CONNECT_TIMEOUT, settings.timeout)),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def complete_json(
        self,
        messages: list[dict[str, str]],
        model_type: type[T],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> T:
        """Pide una respuesta que cumpla `model_type` y la devuelve ya validada.

        El esquema se envía al servidor como `response_format` para que genere solo JSON
        válido; aun así se valida aquí, porque una respuesta cortada o vacía lo incumple.
        """
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": model_type.__name__,
                    "strict": True,
                    "schema": model_type.model_json_schema(),
                },
            },
        }
        # Cuerpo en UTF-8 explícito: con otra codificación el servidor responde 400.
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._parse(self._post(body), model_type)

    def _post(self, body: bytes) -> httpx.Response:
        error: LlmUnavailable | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.post("chat/completions", content=body)
            except httpx.TimeoutException:
                # No se reintenta: repetir una espera tan larga solo retrasa el siguiente caso.
                raise LlmUnavailable(
                    f"El LLM no respondió en {self.settings.timeout:g} s.", "tiempo_agotado"
                ) from None
            except httpx.TransportError as exc:
                error = LlmUnavailable(f"No se pudo conectar con el LLM ({type(exc).__name__}).")
            else:
                if response.is_success:
                    return response
                if response.status_code in (401, 403):
                    raise LlmUnavailable(
                        "El servidor LLM rechazó la clave de API.", "no_autorizado"
                    )
                error = LlmUnavailable(f"El LLM respondió HTTP {response.status_code}.")
                if response.status_code not in RETRYABLE_STATUS:
                    raise error
            if attempt < self.retries:
                logger.warning("LLM no disponible (%s); reintento %d", error.code, attempt + 1)
                self._sleep(min(0.5 * 2**attempt, 5.0))
        assert error is not None
        raise error

    @staticmethod
    def _parse(response: httpx.Response, model_type: type[T]) -> T:
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError):
            raise LlmInvalidResponse("La respuesta del servidor no tiene el formato esperado.") from None
        if finish == "length":
            raise LlmInvalidResponse("La respuesta se cortó por el límite de tokens.")
        if not isinstance(content, str) or not content.strip():
            raise LlmInvalidResponse("La respuesta del LLM llegó vacía.")
        try:
            return model_type.model_validate_json(content)
        except ValidationError as exc:
            # Solo ubicación y tipo del error: el contenido nunca va a los registros.
            detail = "; ".join(
                f"{'.'.join(str(part) for part in item['loc']) or '(raíz)'}: {item['type']}"
                for item in exc.errors(include_input=False, include_url=False)[:5]
            )
            raise LlmInvalidResponse(f"La respuesta no cumple el esquema ({detail}).") from None
