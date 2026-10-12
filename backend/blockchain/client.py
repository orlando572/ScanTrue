"""Envío y verificación del contrato local sin almacenar el texto original."""

import json
from uuid import UUID

from web3 import Web3
from web3.exceptions import TransactionNotFound

from backend.core.config import BlockchainSettings
from backend.schemas.history import HistoryRecord


class BlockchainUnavailable(RuntimeError):
    pass


def canonical_data(record: HistoryRecord) -> bytes:
    models = [
        {
            "modelo": result.modelo,
            "version": result.version,
            "clase": result.clase,
            "probabilidad_falsa": result.probabilidad_falsa,
            "tokens_leidos": result.tokens_leidos,
        }
        for _, result in sorted(record.resultados.items())
        if result.estado == "ok"
    ]
    return json.dumps(
        {"comparacion": record.comparacion, "resultados": models},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class RegistryClient:
    def __init__(self, settings: BlockchainSettings) -> None:
        self.settings = settings
        self.web3 = Web3(
            Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 3})
        )
        self.address = Web3.to_checksum_address(settings.contract_address)
        self.contract = self.web3.eth.contract(
            address=self.address, abi=settings.contract_abi
        )
        self.account = self.web3.eth.account.from_key(settings.private_key)

    def check_ready(self) -> None:
        try:
            if self.web3.eth.chain_id != self.settings.chain_id:
                raise BlockchainUnavailable("chain_id_incorrecto")
            if not self.web3.eth.get_code(self.address):
                raise BlockchainUnavailable("contrato_no_desplegado")
            if Web3.to_hex(
                self.web3.eth.get_block(self.settings.deployment_block)["hash"]
            ) != self.settings.deployment_block_hash:
                raise BlockchainUnavailable("estado_anvil_incompatible")
            if self.contract.functions.registrador().call() != self.account.address:
                raise BlockchainUnavailable("firmante_no_autorizado")
        except BlockchainUnavailable:
            raise
        except Exception as error:
            raise BlockchainUnavailable("anvil_no_disponible") from error

    def find_registration(self, analysis_id: UUID) -> str | None:
        """Recupera un envío confirmado cuyo hash no llegó a guardarse."""
        logs = self.contract.events.AnalisisRegistrado().get_logs(
            from_block=self.settings.deployment_block,
            to_block="latest",
            argument_filters={"id": analysis_id.bytes},
        )
        return Web3.to_hex(logs[0]["transactionHash"]) if logs else None

    def send(self, record: HistoryRecord) -> str:
        nonce = self.web3.eth.get_transaction_count(self.account.address, "pending")
        transaction = self.contract.functions.registrar(
            record.id.bytes,
            bytes.fromhex(record.hash_texto),
            int(record.fecha.timestamp()),
            canonical_data(record),
        ).build_transaction(
            {
                "from": self.account.address,
                "nonce": nonce,
                "chainId": self.settings.chain_id,
                "gas": 500_000,
                "gasPrice": self.web3.eth.gas_price,
            }
        )
        signed = self.account.sign_transaction(transaction)
        return Web3.to_hex(self.web3.eth.send_raw_transaction(signed.raw_transaction))

    def verify(self, record: HistoryRecord, transaction_hash: str) -> bool | None:
        """None significa que la transacción todavía no tiene recibo."""
        try:
            receipt = self.web3.eth.get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            return None
        if receipt["status"] != 1:
            return False
        events = self.contract.events.AnalisisRegistrado().process_receipt(receipt)
        if len(events) != 1:
            return False
        event = events[0]
        args = event["args"]
        return (
            Web3.to_checksum_address(event["address"]) == self.address
            and args["id"] == record.id.bytes
            and args["hashTexto"] == bytes.fromhex(record.hash_texto)
            and args["fecha"] == int(record.fecha.timestamp())
            and args["datos"] == canonical_data(record)
        )
