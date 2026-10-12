"""Conciliación periódica de registros pendientes de Supabase con Anvil."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import time

from backend.blockchain.client import BlockchainUnavailable, RegistryClient
from backend.repositories.supabase import SupabaseRepository

logger = logging.getLogger(__name__)


class BlockchainWorker:
    def __init__(self, repository: SupabaseRepository, client: RegistryClient) -> None:
        self.repository = repository
        self.client = client

    def process_one(self) -> bool:
        analysis_id = self.repository.claim_blockchain_analysis()
        if analysis_id is None:
            return False
        record = self.repository.get_blockchain_analysis(analysis_id)
        if record is None:  # El propietario pudo eliminar el análisis tras reclamarlo.
            return True
        now = datetime.now(timezone.utc)
        transaction_hash = record.hash_transaccion
        try:
            self.client.check_ready()
            found_hash = self.client.find_registration(analysis_id)
            transaction_hash = found_hash or transaction_hash
            if transaction_hash:
                verified = self.client.verify(record, transaction_hash)
                if verified is True:
                    self.repository.set_blockchain_state(
                        analysis_id,
                        state="confirmado",
                        transaction_hash=transaction_hash,
                        next_attempt=now,
                    )
                elif verified is None:
                    self.repository.set_blockchain_state(
                        analysis_id,
                        state="pendiente",
                        transaction_hash=transaction_hash,
                        next_attempt=now + timedelta(seconds=15),
                    )
                else:
                    self.repository.set_blockchain_state(
                        analysis_id,
                        state="fallido",
                        transaction_hash=transaction_hash if found_hash else None,
                        next_attempt=now + timedelta(minutes=1),
                        error="registro_no_coincide" if found_hash else "transaccion_fallida",
                    )
                return True

            transaction_hash = self.client.send(record)
            # Anvil suele entregar el recibo enseguida; confirmar en esta pasada
            # evita dejar un registro verificable en estado pendiente.
            for attempt in range(6):
                verified = self.client.verify(record, transaction_hash)
                if verified is not None:
                    break
                if attempt < 5:
                    time.sleep(1)
            if verified is True:
                self.repository.set_blockchain_state(
                    analysis_id,
                    state="confirmado",
                    transaction_hash=transaction_hash,
                    next_attempt=now,
                )
            elif verified is False:
                self.repository.set_blockchain_state(
                    analysis_id,
                    state="fallido",
                    transaction_hash=None,
                    next_attempt=now + timedelta(minutes=1),
                    error="transaccion_fallida",
                )
            else:
                self.repository.set_blockchain_state(
                    analysis_id,
                    state="pendiente",
                    transaction_hash=transaction_hash,
                    next_attempt=now + timedelta(seconds=15),
                )
        except BlockchainUnavailable as error:
            self._failed(analysis_id, transaction_hash, str(error), now)
        except Exception:
            logger.exception("No se pudo registrar el análisis %s", analysis_id)
            self._failed(analysis_id, transaction_hash, "envio_fallido", now)
        return True

    def _failed(
        self, analysis_id, transaction_hash: str | None, reason: str, now: datetime
    ) -> None:
        self.repository.set_blockchain_state(
            analysis_id,
            state="fallido",
            transaction_hash=transaction_hash,
            next_attempt=now + timedelta(minutes=1),
            error=reason,
        )

    async def run(self) -> None:
        while True:
            try:
                processed = await asyncio.to_thread(self.process_one)
            except Exception:
                logger.exception("Falló la conciliación de blockchain")
                processed = False
            await asyncio.sleep(1 if processed else 5)
