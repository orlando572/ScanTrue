"""Trabajador de la cola de verificación (incremento 2).

Sigue el diseño del trabajador de blockchain: reclama un caso con `for update skip locked`,
lo procesa y guarda el resultado. En la Fase 2 el procesamiento es un resultado fijo de prueba
que solo comprueba que la cola funciona; las fases 3 a 5 lo sustituyen por la verificación real
(`process` es el punto de cambio). Mientras tanto, no enciendas VERIFICATION_ENABLED en un
entorno cuyos resultados vea el público: los casos terminarían «completada» sin verificar nada.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from backend.core.config import VerificationSettings

logger = logging.getLogger(__name__)

# La reserva debe durar más que un caso: si el proceso se cae, vence y otro retoma el caso.
RESERVATION_SECONDS = 600
# Espera tras el 1.º, 2.º y 3.º intento fallido (D11); se ajustan en la Fase 5.
RETRY_WAITS = (60, 300, 900)
SWEEP_EVERY_SECONDS = 60

PLACEHOLDER_MODEL = "prueba-fase-2"


@dataclass(frozen=True)
class VerificationOutcome:
    conclusion: str
    summary: str | None
    claims: list
    sources: list
    model: str | None
    prompt_version: str | None


class QueueRepository(Protocol):
    def enqueue_verification(self, analysis_id: UUID) -> bool: ...
    def enqueue_pending_verifications(self, since, limit: int = 100) -> int: ...
    def claim_verification(self, max_attempts: int, reservation_seconds: int) -> UUID | None: ...
    def copy_verification(self, analysis_id: UUID) -> bool: ...
    def complete_verification(
        self, analysis_id: UUID, *, conclusion: str, summary: str | None, claims: list,
        sources: list, model: str | None, prompt_version: str | None,
    ) -> bool: ...
    def fail_verification(
        self, analysis_id: UUID, error: str, *, max_attempts: int, waits: tuple[int, ...],
    ) -> str | None: ...


def placeholder_process(analysis_id: UUID) -> VerificationOutcome:
    """Resultado fijo de la Fase 2: deja claro que no es una verificación real."""
    return VerificationOutcome(
        conclusion="evidencia_insuficiente",
        summary="Resultado de prueba de la cola (Fase 2): no es una verificación real.",
        claims=[],
        sources=[],
        model=PLACEHOLDER_MODEL,
        prompt_version=PLACEHOLDER_MODEL,
    )


def enqueue_new_analysis(
    repository: QueueRepository,
    settings: VerificationSettings | None,
    analysis_id: UUID,
) -> bool:
    """Encola el análisis recién guardado. Nunca lanza: si falla, el análisis sigue válido.

    Lo que no se encole aquí lo recoge el barrido del trabajador (VERIFICATION_DESDE).
    """
    if settings is None or not settings.enabled:
        return False
    try:
        return repository.enqueue_verification(analysis_id)
    except Exception:
        logger.warning("No se pudo encolar la verificación del análisis %s", analysis_id, exc_info=True)
        return False


class VerificationWorker:
    def __init__(
        self,
        repository: QueueRepository,
        settings: VerificationSettings,
        *,
        process: Callable[[UUID], VerificationOutcome] = placeholder_process,
        reservation_seconds: int = RESERVATION_SECONDS,
        waits: tuple[int, ...] = RETRY_WAITS,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.process = process
        self.reservation_seconds = reservation_seconds
        self.waits = waits

    def process_one(self) -> bool:
        """Atiende un caso. False si no había ninguno listo."""
        analysis_id = self.repository.claim_verification(
            self.settings.max_attempts, self.reservation_seconds
        )
        if analysis_id is None:
            return False
        try:
            # Paso 0: si el mismo texto ya tiene una verificación vigente, se reutiliza.
            if self.repository.copy_verification(analysis_id):
                return True
            outcome = self.process(analysis_id)
            saved = self.repository.complete_verification(
                analysis_id,
                conclusion=outcome.conclusion,
                summary=outcome.summary,
                claims=outcome.claims,
                sources=outcome.sources,
                model=outcome.model,
                prompt_version=outcome.prompt_version,
            )
            if not saved:  # el propietario pudo borrar el análisis mientras se procesaba
                logger.warning("La verificación %s ya no estaba en proceso", analysis_id)
        except Exception as error:
            code = getattr(error, "code", None)
            code = code if isinstance(code, str) else "error_interno"
            logger.exception("Falló la verificación %s (%s)", analysis_id, code)
            self._fail(analysis_id, code)
        return True

    def _fail(self, analysis_id: UUID, code: str) -> None:
        try:
            state = self.repository.fail_verification(
                analysis_id, code, max_attempts=self.settings.max_attempts, waits=self.waits
            )
            logger.warning("Verificación %s: %s -> %s", analysis_id, code, state)
        except Exception:
            # Sin este registro la reserva vence sola y otro intento retoma el caso.
            logger.exception("No se pudo registrar la falla de la verificación %s", analysis_id)

    def sweep(self) -> int:
        """Encola los análisis sin fila posteriores a VERIFICATION_DESDE (D9)."""
        if self.settings.since is None:
            return 0
        count = self.repository.enqueue_pending_verifications(self.settings.since)
        if count:
            logger.info("El barrido encoló %d verificaciones", count)
        return count

    async def run(self) -> None:
        if self.settings.since is None:
            logger.warning("VERIFICATION_DESDE sin definir: no habrá barrido de análisis sin fila")
        last_sweep = float("-inf")
        while True:
            try:
                if time.monotonic() - last_sweep >= SWEEP_EVERY_SECONDS:
                    last_sweep = time.monotonic()
                    await asyncio.to_thread(self.sweep)
                processed = await asyncio.to_thread(self.process_one)
            except Exception:
                logger.exception("Falló la cola de verificación")
                processed = False
            await asyncio.sleep(1 if processed else 5)
