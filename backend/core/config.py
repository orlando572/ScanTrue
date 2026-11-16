"""Configuración local; las credenciales se leen sin guardarlas en Git."""

from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True)
class LlmSettings:
    """Servidor del LLM con API tipo OpenAI (llama-server). Sin LLM_BASE_URL no hay LLM."""

    base_url: str
    model: str
    api_key: str | None
    timeout: float

    @classmethod
    def from_environment(cls) -> "LlmSettings | None":
        load_dotenv(ENV_FILE, override=False)
        base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            return None
        raw_timeout = os.getenv("LLM_TIMEOUT", "").strip() or "120"
        try:
            timeout = float(raw_timeout)
        except ValueError:
            raise ValueError("LLM_TIMEOUT debe ser un número de segundos.") from None
        if not 0 < timeout <= 3600:
            raise ValueError("LLM_TIMEOUT debe estar entre 0 y 3600 segundos.")
        return cls(
            base_url=base_url,
            model=os.getenv("LLM_MODEL", "").strip() or "qwen",
            api_key=os.getenv("LLM_API_KEY", "").strip() or None,
            timeout=timeout,
        )


@dataclass(frozen=True)
class VerificationSettings:
    """Cola de verificación web (incremento 2). Apagada salvo VERIFICATION_ENABLED=true."""

    enabled: bool
    max_attempts: int
    # Fecha de corte (D9): el barrido solo encola análisis posteriores. Sin ella no hay barrido.
    since: datetime | None
    # Tiempo máximo de un caso; al agotarse, las afirmaciones que faltan quedan «insuficiente».
    case_seconds: float = 300.0

    @classmethod
    def from_environment(cls) -> "VerificationSettings":
        load_dotenv(ENV_FILE, override=False)
        enabled = os.getenv("VERIFICATION_ENABLED", "").strip().lower() in {"1", "true", "yes", "si", "sí"}
        raw_attempts = os.getenv("VERIFICATION_MAX_ATTEMPTS", "").strip() or "3"
        try:
            max_attempts = int(raw_attempts)
        except ValueError:
            raise ValueError("VERIFICATION_MAX_ATTEMPTS debe ser un número entero.") from None
        if not 1 <= max_attempts <= 10:
            raise ValueError("VERIFICATION_MAX_ATTEMPTS debe estar entre 1 y 10.")
        raw_since = os.getenv("VERIFICATION_DESDE", "").strip()
        since = None
        if raw_since:
            try:
                since = datetime.fromisoformat(raw_since)
            except ValueError:
                raise ValueError(
                    "VERIFICATION_DESDE debe ser una fecha ISO 8601, por ejemplo 2026-11-15T09:00:00-05:00."
                ) from None
            if since.tzinfo is None:
                raise ValueError("VERIFICATION_DESDE debe incluir la zona horaria.")
        case_seconds = _bounded_number("VERIFICATION_CASE_SECONDS", cls.case_seconds, 30, 1800, float)
        return cls(enabled=enabled, max_attempts=max_attempts, since=since, case_seconds=case_seconds)


SEARCH_PROVIDERS = ("brave", "tavily")


@dataclass(frozen=True)
class SearchSettings:
    """Proveedor de búsqueda web (D3). Sin SEARCH_PROVIDER y SEARCH_API_KEY no hay búsqueda."""

    provider: str
    api_key: str
    timeout: float

    @classmethod
    def from_environment(cls) -> "SearchSettings | None":
        load_dotenv(ENV_FILE, override=False)
        provider = os.getenv("SEARCH_PROVIDER", "").strip().lower()
        api_key = os.getenv("SEARCH_API_KEY", "").strip()
        if not provider or not api_key:
            return None
        if provider not in SEARCH_PROVIDERS:
            raise ValueError(f"SEARCH_PROVIDER debe ser uno de: {', '.join(SEARCH_PROVIDERS)}.")
        raw_timeout = os.getenv("SEARCH_TIMEOUT", "").strip() or "15"
        try:
            timeout = float(raw_timeout)
        except ValueError:
            raise ValueError("SEARCH_TIMEOUT debe ser un número de segundos.") from None
        if not 0 < timeout <= 120:
            raise ValueError("SEARCH_TIMEOUT debe estar entre 0 y 120 segundos.")
        return cls(provider=provider, api_key=api_key, timeout=timeout)


@dataclass(frozen=True)
class FactCheckSettings:
    """Fuente previa: Google Fact Check Tools (docs/llm/FUENTE_PREVIA.md). Sin FACTCHECK_API_KEY no se usa."""

    api_key: str
    timeout: float

    @classmethod
    def from_environment(cls) -> "FactCheckSettings | None":
        load_dotenv(ENV_FILE, override=False)
        api_key = os.getenv("FACTCHECK_API_KEY", "").strip()
        if not api_key:
            return None
        raw_timeout = os.getenv("FACTCHECK_TIMEOUT", "").strip() or "10"
        try:
            timeout = float(raw_timeout)
        except ValueError:
            raise ValueError("FACTCHECK_TIMEOUT debe ser un número de segundos.") from None
        if not 0 < timeout <= 120:
            raise ValueError("FACTCHECK_TIMEOUT debe estar entre 0 y 120 segundos.")
        return cls(api_key=api_key, timeout=timeout)


def _bounded_number(name: str, default: float, low: float, high: float, kind=int):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = kind(raw)
    except ValueError:
        raise ValueError(f"{name} debe ser un número.") from None
    if not low <= value <= high:
        raise ValueError(f"{name} debe estar entre {low:g} y {high:g}.")
    return value


@dataclass(frozen=True)
class EvidenceLimits:
    """Límites de la búsqueda de evidencia por afirmación (docs/llm/PLAN_INCREMENTO_2.md, 4.6).

    Al agotarse el tiempo o los cupos, la afirmación se juzga con la evidencia reunida hasta ese
    momento: nunca se queda colgada.
    """

    queries_per_claim: int = 1
    results_per_query: int = 5
    pages_per_claim: int = 4
    # De esas páginas, las que como máximo salen de la fuente previa (el resto, de la búsqueda web).
    previous_pages: int = 2
    per_domain: int = 2
    passages_per_claim: int = 6
    passages_per_page: int = 3
    page_bytes: int = 1_500_000
    page_seconds: float = 15.0
    claim_seconds: float = 120.0
    max_redirects: int = 3

    @classmethod
    def from_environment(cls) -> "EvidenceLimits":
        load_dotenv(ENV_FILE, override=False)
        defaults = cls()
        return cls(
            queries_per_claim=_bounded_number("VERIFICATION_MAX_QUERIES", defaults.queries_per_claim, 1, 2),
            pages_per_claim=_bounded_number("VERIFICATION_MAX_PAGES", defaults.pages_per_claim, 1, 10),
            page_bytes=_bounded_number("VERIFICATION_PAGE_BYTES", defaults.page_bytes, 50_000, 10_000_000),
            page_seconds=_bounded_number("VERIFICATION_PAGE_SECONDS", defaults.page_seconds, 1, 120, float),
            claim_seconds=_bounded_number("VERIFICATION_CLAIM_SECONDS", defaults.claim_seconds, 10, 900, float),
        )


def web_origins() -> list[str]:
    """Orígenes de la web (web/) que pueden llamar a la API desde el navegador."""
    load_dotenv(ENV_FILE, override=False)
    value = os.getenv("WEB_ORIGINS", "http://127.0.0.1:5174,http://localhost:5174")
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
