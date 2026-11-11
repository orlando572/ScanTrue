"""Configuración local; las credenciales se leen sin guardarlas en Git."""

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv


logger = logging.getLogger(__name__)
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class AnalysisSettings:
    """Los pesos y temperaturas salen de datasets/combinacion_produccion/combinacion.json."""

    combination_file: Path

    @classmethod
    def from_environment(cls) -> "AnalysisSettings":
        load_dotenv(ENV_FILE, override=False)
        if os.getenv("ANALYSIS_MBERT_WEIGHT"):
            logger.warning(
                "ANALYSIS_MBERT_WEIGHT ya no se usa: los pesos vienen de la calibración conjunta."
            )
        from backend.models.contrato import COMBINATION_FILE

        return cls(combination_file=COMBINATION_FILE)


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    publishable_key: str
    secret_key: str | None

    @classmethod
    def from_environment(cls) -> "SupabaseSettings | None":
        load_dotenv(ENV_FILE, override=False)
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        if not url or not publishable_key:
            return None
        secret_key = os.getenv("SUPABASE_SECRET_KEY", "").strip() or None
        return cls(url, publishable_key, secret_key)


@dataclass(frozen=True)
class BlockchainSettings:
    rpc_url: str
    chain_id: int
    private_key: str
    contract_address: str
    contract_abi: list[dict]
    deployment_block: int
    deployment_block_hash: str

    @classmethod
    def from_environment(cls) -> "BlockchainSettings | None":
        load_dotenv(ENV_FILE, override=False)
        private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY", "").strip()
        deployment = ENV_FILE.parent / ".local/contract.json"
        if not private_key or not deployment.is_file():
            return None
        data = json.loads(deployment.read_text(encoding="utf-8"))
        chain_id = int(os.getenv("BLOCKCHAIN_CHAIN_ID", "31337"))
        if int(data["chain_id"]) != chain_id:
            raise ValueError("El despliegue local pertenece a otra cadena.")
        return cls(
            rpc_url=os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545").strip(),
            chain_id=chain_id,
            private_key=private_key,
            contract_address=data["address"],
            contract_abi=data["abi"],
            deployment_block=int(data["deployment_block"]),
            deployment_block_hash=data["deployment_block_hash"],
        )
