"""Versiones de modelos: qué conjunto está activo, activar otro y volver al anterior.

Una versión activable («despliegue») es un conjunto coherente: contrato BiLSTM,
contrato BETO y la combinación calibrada con esos dos contratos. Cada una se describe
con un manifiesto en `backend/despliegues/<version>.json`, con rutas relativas a la
raíz del repositorio. Las versiones antiguas sin contrato se listan solo para comparar
sus métricas.

La versión activa y el historial de cambios se guardan en
`backend/.local/despliegue_activo.json`, fuera de Git y sin depender de Supabase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
from typing import Callable

from backend.models.contrato import Combination, resolve
from backend.schemas.metrics import MetricsResponse

logger = logging.getLogger(__name__)

BACKEND = Path(__file__).resolve().parents[1]
DEPLOYMENTS_DIR = BACKEND / "despliegues"
STATE_FILE = BACKEND / ".local" / "despliegue_activo.json"
MODELS = ("bilstm", "mbert")
HISTORY_LIMIT = 50
# Texto neutro de más de 100 palabras para comprobar una versión antes de activarla.
SMOKE_TEXT = " ".join(
    ["El municipio informó este lunes que las obras de la avenida principal "
     "continuarán durante la semana y pidió a los vecinos usar rutas alternas."] * 8
)


class ModelVersionError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class Deployment:
    version: str
    name: str
    date: str | None
    notes: str | None
    activable: bool
    default: bool
    contracts: dict[str, Path]
    combination: Path | None
    metrics: dict[str, Path]
    model_versions: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "Deployment":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        contracts = {name: resolve(value) for name, value in (data.get("contratos") or {}).items()}
        combination = resolve(data["combinacion"]) if data.get("combinacion") else None
        activable = bool(data.get("activable", True))
        if activable and (set(contracts) != set(MODELS) or combination is None):
            raise ValueError(f"El despliegue {path.name} necesita dos contratos y una combinación")
        return cls(
            version=data["version"],
            name=data.get("nombre") or data["version"],
            date=data.get("fecha"),
            notes=data.get("notas"),
            activable=activable,
            default=bool(data.get("predeterminado", False)),
            contracts=contracts,
            combination=combination,
            metrics={name: resolve(value) for name, value in (data.get("metricas") or {}).items()},
            model_versions=dict(data.get("versiones_modelo") or {}),
        )

    def load_metrics(self, model: str) -> MetricsResponse | None:
        path = self.metrics.get(model)
        if path is None or not path.is_file():
            return None
        try:
            return MetricsResponse.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Métricas no válidas en %s", path)
            return None

    def load_combination(self) -> Combination | None:
        if self.combination is None or not self.combination.is_file():
            return None
        try:
            return Combination.load(self.combination)
        except Exception:
            logger.exception("Combinación no válida en %s", self.combination)
            return None


def build_analysis_service(deployment: Deployment, strict: bool):
    """Carga los modelos de un despliegue.

    Al arrancar (`strict=False`) BETO puede faltar y el servicio sigue con el BiLSTM,
    como siempre. Al activar una versión (`strict=True`) deben cargar los dos.
    """
    from backend.models.bilstm import BilstmPredictor
    from backend.models.mbert import MbertPredictor, MbertTokenizer
    from backend.services.analysis import AnalysisService

    combination = Combination.load(deployment.combination)
    bilstm_predictor = BilstmPredictor(deployment.contracts["bilstm"])
    combination.check(bilstm_predictor.contract)
    try:
        mbert_text_policy = MbertTokenizer(deployment.contracts["mbert"])
        combination.check(mbert_text_policy.contract)
    except Exception:
        if strict:
            raise
        logger.exception("No se pudo cargar el tokenizador mBERT")
        mbert_text_policy = None
    try:
        mbert_predictor = MbertPredictor(mbert_text_policy) if mbert_text_policy else None
    except Exception:
        if strict:
            raise
        logger.exception("No se pudo cargar el checkpoint mBERT")
        mbert_predictor = None
    return AnalysisService(
        bilstm_predictor,
        mbert_predictor=mbert_predictor,
        mbert_text_policy=mbert_text_policy,
        combination=combination,
    )


def smoke_test(service) -> None:
    """Una predicción real con los dos modelos antes de dar por buena una versión."""
    from backend.schemas.analysis import AnalysisRequest

    results = service.analyze(AnalysisRequest(texto=SMOKE_TEXT)).response.resultados
    failed = [name for name in MODELS if getattr(results.get(name), "estado", None) != "ok"]
    if failed:
        raise RuntimeError(f"La versión no respondió con: {', '.join(failed)}")


class ModelVersionManager:
    def __init__(
        self,
        directory: Path = DEPLOYMENTS_DIR,
        state_file: Path = STATE_FILE,
        builder: Callable = build_analysis_service,
        check: Callable = smoke_test,
        on_swap: Callable | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.state_file = Path(state_file)
        self.builder = builder
        self.check = check
        self.on_swap = on_swap
        self.current_version: str | None = None
        self._lock = threading.Lock()

    # ── Catálogo y estado ───────────────────────────────────────────

    def deployments(self) -> list[Deployment]:
        found = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                found.append(Deployment.load(path))
            except Exception:
                logger.exception("Manifiesto de despliegue no válido: %s", path)
        # Más recientes primero; los que no tienen fecha, al final.
        return sorted(found, key=lambda item: item.date or "", reverse=True)

    def get(self, version: str) -> Deployment | None:
        return next((item for item in self.deployments() if item.version == version), None)

    def default(self) -> Deployment | None:
        activable = [item for item in self.deployments() if item.activable]
        return next((item for item in activable if item.default), activable[0] if activable else None)

    def _state(self) -> dict:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, state: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_file)

    def history(self) -> list[dict]:
        entries = self._state().get("historial")
        return list(reversed(entries)) if isinstance(entries, list) else []

    def previous_version(self) -> str | None:
        """Última versión activable distinta de la actual que estuvo activa."""
        for entry in self.history():
            previous = entry.get("anterior")
            if entry.get("version") == self.current_version and previous \
                    and previous != self.current_version:
                target = self.get(previous)
                return previous if target and target.activable else None
        return None

    # ── Arranque ────────────────────────────────────────────────────

    def start(self):
        """Carga la versión guardada; si falla, la predeterminada. Devuelve el servicio."""
        default = self.default()
        saved = self.get(self._state().get("activa") or "")
        tried: set[str] = set()
        for deployment in (saved, default):
            if deployment is None or not deployment.activable or deployment.version in tried:
                continue
            tried.add(deployment.version)
            try:
                service = self.builder(deployment, False)
                self.current_version = deployment.version
                return service
            except Exception:
                logger.exception("No se pudo cargar el despliegue %s", deployment.version)
        self.current_version = None
        return None

    # ── Cambio de versión ───────────────────────────────────────────

    def activate(self, version: str, actor: str | None, action: str = "activar") -> str:
        if not self._lock.acquire(blocking=False):
            raise ModelVersionError(
                "activacion_en_curso", "Ya hay un cambio de versión en curso.", 409
            )
        try:
            deployment = self.get(version)
            if deployment is None:
                raise ModelVersionError("version_desconocida", "Esa versión no existe.", 404)
            if not deployment.activable:
                raise ModelVersionError(
                    "version_no_activable",
                    "Esta versión está archivada: solo sirve para comparar métricas.",
                )
            if version == self.current_version:
                raise ModelVersionError("version_ya_activa", "Esa versión ya está activa.", 409)
            try:
                service = self.builder(deployment, True)
                self.check(service)
            except Exception as error:
                logger.exception("No se pudo activar el despliegue %s", version)
                raise ModelVersionError(
                    "version_no_cargo",
                    "La versión no se pudo cargar; sigue activa la anterior.",
                    502,
                ) from error
            previous = self.current_version
            if self.on_swap is not None:
                self.on_swap(service)
            self.current_version = version
            state = self._state()
            entries = state.get("historial") if isinstance(state.get("historial"), list) else []
            entries.append({
                "version": version,
                "anterior": previous,
                "accion": action,
                "fecha": datetime.now(timezone.utc).isoformat(),
                "por": actor,
            })
            self._save({"activa": version, "historial": entries[-HISTORY_LIMIT:]})
            return version
        finally:
            self._lock.release()

    def revert(self, actor: str | None) -> str:
        previous = self.previous_version()
        if previous is None:
            raise ModelVersionError(
                "sin_version_anterior", "No hay una versión anterior a la que volver.", 409
            )
        return self.activate(previous, actor, action="revertir")

    # ── Métricas de la versión activa ───────────────────────────────

    def active_metrics(self, model: str) -> MetricsResponse | None:
        deployment = self.get(self.current_version or "") or self.default()
        return deployment.load_metrics(model) if deployment else None
