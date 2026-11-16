"""Modelos desplegados: catálogo, un modelo por tipo, pesos y vuelta atrás.

Hay dos tipos (huecos): `bilstm` y `mbert` (BETO o mBERT). En cada uno hay como mucho un
modelo desplegado y al menos uno de los dos debe estarlo. El panel elige, retira y pondera
los modelos; nada de esto entrena ni modifica lo que deja el entrenamiento.

El catálogo junta:

- Manifiestos versionados en `backend/modelos/<tipo>/*.json`: los modelos del repositorio
  (contrato y métricas) y los archivados de octubre, que solo sirven para comparar.
- Los `contrato.json` que encuentra, solo leyendo, bajo `datasets/` (o `MODELOS_BUSCAR_EN`):
  cada entrenamiento nuevo aparece solo. Mientras su temperatura sea provisional queda
  «pendiente de calibrar» y no se puede desplegar.
- Los ZIP importados desde el panel, que se guardan en `datasets/modelos/<tipo>/<versión>/`.

Lo desplegado, los pesos y el historial se guardan en `backend/.local/modelos_desplegados.json`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import threading
from typing import Callable
import uuid
import zipfile

from backend.models.contrato import (
    COMBINATION_FILE, ROOT, Combination, ModelContract, UnsupportedBaseModel, cached_sha256,
    resolve,
)
from backend.schemas.metrics import MetricsResponse

logger = logging.getLogger(__name__)

BACKEND = Path(__file__).resolve().parents[1]
MANIFESTS_DIR = BACKEND / "modelos"
STATE_FILE = BACKEND / ".local" / "modelos_desplegados.json"
IMPORTS_DIR = ROOT / "datasets" / "modelos"
TYPES = ("bilstm", "mbert")
TYPE_NAMES = {"bilstm": "BiLSTM", "mbert": "BETO / mBERT"}
BASE_NAMES = {"beto": "BETO", "mbert": "mBERT"}
HISTORY_LIMIT = 50
# Carpetas de datasets/ que no tienen modelos (o son copias de seguridad) y no se recorren.
SKIP_DIRS = {".venv", "node_modules", "embeddings", "fuentes", "unificado", "comun_v1",
             "modelos_base", "archivo_octubre", "__pycache__"}
MAX_ZIP_BYTES = 2 * 1024 ** 3
MAX_UNZIPPED_BYTES = 4 * 1024 ** 3
# Texto neutro de más de 100 palabras para comprobar los modelos antes de darlos por buenos.
SMOKE_TEXT = " ".join(
    ["El municipio informó este lunes que las obras de la avenida principal "
     "continuarán durante la semana y pidió a los vecinos usar rutas alternas."] * 8
)


class ModelVersionError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


# ── Catálogo ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelEntry:
    id: str
    tipo: str
    version: str
    nombre: str
    fecha: str | None
    origen: str  # repositorio | entrenamiento | importado
    ruta: str | None  # carpeta del contrato, relativa a la raíz si se puede
    estado: str  # disponible | pendiente_calibrar | no_admitido | no_valido | archivado
    motivo: str | None = None
    contrato: Path | None = None
    metricas: Path | None = None
    temperatura: float | None = None
    max_tokens: int | None = None
    sha256: str | None = None
    predeterminado: bool = False
    notas: str | None = None

    @property
    def deployable(self) -> bool:
        return self.estado == "disponible"

    def load_metrics(self) -> MetricsResponse | None:
        if self.metricas is None or not self.metricas.is_file():
            return None
        try:
            return MetricsResponse.model_validate_json(self.metricas.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Métricas no válidas en %s", self.metricas)
            return None


def _relative(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _date_from_version(version: str, contract: Path | None) -> str | None:
    match = re.search(r"(20\d{2})(\d{2})(\d{2})(?!\d)", version)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    if contract is not None and contract.exists():
        return datetime.fromtimestamp(contract.stat().st_mtime, timezone.utc).date().isoformat()
    return None


def _model_name(tipo: str, data: dict) -> str:
    """«BiLSTM B6», «BETO M3b», «mBERT M1»… según el contrato."""
    if tipo == "mbert":
        base = BASE_NAMES.get((data.get("modelo_base") or {}).get("clave"), "BETO / mBERT")
    else:
        base = "BiLSTM"
    choice = data.get("eleccion") or {}
    config = choice.get("ganador_elegido") or choice.get("ganador_regla")
    if not config:  # «comun_v1_B0_20261107» → «B0»
        match = re.search(r"_([A-Za-z]+\d+[a-z]*)_\d{8}$", str(data.get("version", "")))
        config = match.group(1) if match else None
    return f"{base} {config}" if config else base


def inspect_contract(path: Path) -> dict | None:
    """Lee un contrato sin cargar pesos: tipo, versión, estado y motivo.

    Devuelve None si el archivo no es un contrato de BiLSTM o BETO/mBERT.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tipo": None, "version": path.parent.name, "estado": "no_valido",
                "motivo": "El contrato no es un JSON válido.", "data": {}}
    if not isinstance(data, dict) or data.get("modelo") not in TYPES:
        return None
    tipo = data["modelo"]
    info = {"tipo": tipo, "version": str(data.get("version") or path.parent.name),
            "data": data, "estado": "disponible", "motivo": None, "sha256": None,
            "temperatura": None, "max_tokens": None}
    try:
        contract = ModelContract.load(path, tipo, allow_provisional=True)
    except UnsupportedBaseModel as error:
        return {**info, "estado": "no_admitido", "motivo": str(error)}
    except (KeyError, TypeError, ValueError) as error:
        return {**info, "estado": "no_valido", "motivo": f"Contrato no válido: {error}"}
    info.update(sha256=contract.checkpoint_sha256, temperatura=contract.temperature,
                max_tokens=contract.max_tokens)
    problem = _check_files(contract)
    if problem:
        return {**info, "estado": "no_valido", "motivo": problem}
    if contract.provisional:
        return {**info, "estado": "pendiente_calibrar",
                "motivo": "Su temperatura aún es provisional: falta la calibración conjunta "
                          "(datos_comunes/calibrar_conjunto.py --actualizar-contratos)."}
    return info


def _check_files(contract: ModelContract) -> str | None:
    """Que estén los archivos del contrato y sus SHA-256 coincidan (sin cargarlos)."""
    try:
        if contract.model == "bilstm":
            weights = contract.checkpoint
        else:
            weights = contract.checkpoint / "model.safetensors"
            if not (contract.checkpoint / "config.json").is_file():
                return f"Falta config.json en {_relative(contract.checkpoint)}"
            tokenizer = contract.data.get("tokenizador") or {}
            tokenizer_file = contract.resolve(tokenizer["ruta"]) / "tokenizer.json"
            if not tokenizer_file.is_file():
                return f"Falta el tokenizador: {_relative(tokenizer_file)}"
            if cached_sha256(tokenizer_file) != tokenizer.get("sha256_tokenizer_json"):
                return "El tokenizador no coincide con el SHA-256 del contrato"
        if not weights.is_file():
            return f"Faltan los pesos: {_relative(weights)}"
        if cached_sha256(weights) != contract.checkpoint_sha256:
            return f"Los pesos de {_relative(weights)} no coinciden con el SHA-256 del contrato"
    except (KeyError, OSError, ValueError) as error:
        return f"No se pudieron comprobar los archivos: {error}"
    return None


def scan_dir_from_environment() -> Path:
    """Carpeta donde buscar entrenamientos: `MODELOS_BUSCAR_EN` (también en backend/.env) o
    `datasets/`. Se lee al crear el catálogo, no al importar, para que cuente backend/.env."""
    from backend.core.config import ENV_FILE
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=False)
    value = os.environ.get("MODELOS_BUSCAR_EN", "").strip()
    return (ROOT / value).resolve() if value else ROOT / "datasets"


def _manifest_path(value: str) -> Path:
    """Rutas de un manifiesto: relativas a la raíz (o absolutas, p. ej. en las pruebas)."""
    return Path(value) if Path(value).is_absolute() else resolve(value)


class ModelCatalog:
    def __init__(
        self,
        manifests_dir: Path = MANIFESTS_DIR,
        scan_dir: Path | None = ...,
        imports_dir: Path = IMPORTS_DIR,
    ) -> None:
        self.manifests_dir = Path(manifests_dir)
        if scan_dir is ...:
            scan_dir = scan_dir_from_environment()
        self.scan_dir = Path(scan_dir) if scan_dir else None
        self.imports_dir = Path(imports_dir)

    @staticmethod
    def _inspect(path: Path) -> dict | None:
        # Se relee cada vez: es barato (los SHA de los pesos se recuerdan mientras el
        # archivo no cambie) y así un contrato recién calibrado aparece al momento.
        return inspect_contract(path) if path.is_file() else None

    # Manifiestos del repositorio.
    def _manifest_entries(self) -> list[ModelEntry]:
        found = []
        for path in sorted(self.manifests_dir.glob("*/*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tipo = data["tipo"]
                if tipo not in TYPES or path.parent.name != tipo:
                    raise ValueError(f"Tipo no válido: {tipo}")
                metrics = _manifest_path(data["metricas"]) if data.get("metricas") else None
                version = str(data["version"])
                common = dict(
                    tipo=tipo, version=version, origen="repositorio", metricas=metrics,
                    predeterminado=bool(data.get("predeterminado")), notas=data.get("notas"),
                )
                if data.get("archivado"):
                    found.append(ModelEntry(
                        id=version, nombre=data.get("nombre") or TYPE_NAMES[tipo],
                        fecha=data.get("fecha"), ruta=None, estado="archivado",
                        motivo="Sin contrato de inferencia: solo sirve para comparar métricas.",
                        **common,
                    ))
                    continue
                contract = _manifest_path(data["contrato"])
                info = self._inspect(contract) or {
                    "estado": "no_valido", "data": {},
                    "motivo": f"No se encontró el contrato {_relative(contract)} "
                              "(¿falta `git lfs pull`?)" if not contract.is_file()
                              else "El contrato no es de un BiLSTM ni de BETO/mBERT"}
                if info.get("tipo") not in (None, tipo):
                    info = {**info, "estado": "no_valido", "motivo": "El contrato es de otro tipo"}
                if info.get("version") not in (None, version) and info["estado"] != "no_valido":
                    info = {**info, "estado": "no_valido",
                            "motivo": f"El contrato es de la versión {info['version']}"}
                found.append(ModelEntry(
                    id=version, nombre=data.get("nombre") or _model_name(tipo, info["data"]),
                    fecha=data.get("fecha") or _date_from_version(version, contract),
                    ruta=_relative(contract.parent), estado=info["estado"], motivo=info["motivo"],
                    contrato=contract, temperatura=info.get("temperatura"),
                    max_tokens=info.get("max_tokens"), sha256=info.get("sha256"), **common,
                ))
            except Exception:
                logger.exception("Manifiesto de modelo no válido: %s", path)
        return found

    # Contratos bajo datasets/ (entrenamientos e importados).
    def _contract_paths(self) -> list[Path]:
        roots = [root for root in (self.scan_dir, self.imports_dir) if root and root.is_dir()]
        seen: set[Path] = set()
        paths = []
        for root in roots:
            for current, dirs, files in os.walk(root):
                dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS
                                 and not name.startswith((".", "respaldo")))
                if "contrato.json" in files:
                    dirs[:] = []  # dentro de una carpeta de modelo no hay otros modelos
                    path = (Path(current) / "contrato.json").resolve()
                    if path not in seen:
                        seen.add(path)
                        paths.append(path)
        return paths

    def _scanned_entries(self) -> list[ModelEntry]:
        found = []
        imports = self.imports_dir.resolve()
        for path in self._contract_paths():
            info = self._inspect(path)
            if info is None or info.get("tipo") is None:
                continue
            tipo, version = info["tipo"], info["version"]
            folder = path.parent
            metrics = folder / "metricas.json"
            found.append(ModelEntry(
                id=version, tipo=tipo, version=version, nombre=_model_name(tipo, info["data"]),
                fecha=_date_from_version(version, path),
                origen="importado" if folder.is_relative_to(imports) else "entrenamiento",
                ruta=_relative(folder), estado=info["estado"], motivo=info["motivo"],
                contrato=path, metricas=metrics if metrics.is_file() else None,
                temperatura=info.get("temperatura"), max_tokens=info.get("max_tokens"),
                sha256=info.get("sha256"),
            ))
        return found

    def entries(self) -> list[ModelEntry]:
        """Todos los modelos, sin repetir el mismo (tipo, versión, pesos) y con id único."""
        result: list[ModelEntry] = []
        keys: set[tuple] = set()
        ids: set[tuple[str, str]] = set()
        for entry in self._manifest_entries() + self._scanned_entries():
            key = (entry.tipo, entry.version, entry.sha256 or entry.ruta)
            if key in keys:
                continue
            keys.add(key)
            if (entry.tipo, entry.id) in ids:
                suffix = (entry.sha256 or uuid.uuid5(uuid.NAMESPACE_URL, entry.ruta or "").hex)[:8]
                entry = replace(entry, id=f"{entry.version}-{suffix}")
            ids.add((entry.tipo, entry.id))
            result.append(entry)
        return sorted(result, key=lambda e: (e.tipo, e.fecha or "", e.id), reverse=True)

    def get(self, tipo: str, model_id: str | None) -> ModelEntry | None:
        if not model_id:
            return None
        return next((e for e in self.entries() if e.tipo == tipo and e.id == model_id), None)

    def defaults(self) -> dict[str, str | None]:
        chosen: dict[str, str | None] = {}
        for tipo in TYPES:
            candidates = [e for e in self.entries() if e.tipo == tipo and e.deployable]
            pick = next((e for e in candidates if e.predeterminado), None)
            chosen[tipo] = pick.id if pick else None
        return chosen

    # ── Importar y borrar ───────────────────────────────────────────

    def import_zip(self, zip_path: Path) -> ModelEntry:
        """Valida un ZIP con contrato.json y sus archivos y lo guarda en datasets/modelos/."""
        staging_root = self.imports_dir / ".importando"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = staging_root / uuid.uuid4().hex
        try:
            try:
                archive = zipfile.ZipFile(zip_path)
            except zipfile.BadZipFile as error:
                raise ModelVersionError("zip_no_valido", "El archivo no es un ZIP válido.") from error
            with archive:
                members = archive.infolist()
                total = 0
                for member in members:
                    name = PurePosixPath(member.filename)
                    mode = member.external_attr >> 16
                    if name.is_absolute() or ".." in name.parts or "\\" in member.filename \
                            or stat.S_ISLNK(mode):
                        raise ModelVersionError(
                            "zip_no_valido", f"Ruta no permitida en el ZIP: {member.filename}")
                    total += member.file_size
                if total > MAX_UNZIPPED_BYTES:
                    raise ModelVersionError("zip_demasiado_grande",
                                            "El ZIP descomprimido supera 4 GB.", 413)
                contracts = [m for m in members
                             if not m.is_dir() and PurePosixPath(m.filename).name == "contrato.json"]
                if len(contracts) != 1:
                    raise ModelVersionError(
                        "modelo_no_valido",
                        "El ZIP debe tener exactamente un contrato.json "
                        f"(tiene {len(contracts)}).")
                prefix = PurePosixPath(contracts[0].filename).parent
                staging.mkdir()
                for member in members:
                    name = PurePosixPath(member.filename)
                    if member.is_dir() or (prefix.parts and name.parts[:len(prefix.parts)] != prefix.parts):
                        continue
                    target = staging.joinpath(*name.parts[len(prefix.parts):])
                    if not target.resolve().is_relative_to(staging.resolve()):
                        raise ModelVersionError("zip_no_valido", "Ruta no permitida en el ZIP.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as sink:
                        shutil.copyfileobj(source, sink, 1024 * 1024)
            info = inspect_contract(staging / "contrato.json")
            if info is None or info.get("tipo") is None:
                raise ModelVersionError("modelo_no_valido",
                                        "El contrato no es de un BiLSTM ni de BETO/mBERT.")
            if info["estado"] in ("no_valido", "no_admitido"):
                raise ModelVersionError("modelo_no_valido", info["motivo"])
            tipo, version = info["tipo"], info["version"]
            if not re.fullmatch(r"[\w.\-]{1,120}", version):
                raise ModelVersionError("modelo_no_valido", f"Versión no válida: {version}")
            if any(e.tipo == tipo and e.version == version and e.sha256 == info["sha256"]
                   for e in self.entries()):
                raise ModelVersionError("version_existente", "Ese modelo ya está en el catálogo.", 409)
            destination = self.imports_dir / tipo / version
            if destination.exists():
                raise ModelVersionError(
                    "version_existente", f"Ya hay un modelo importado con la versión {version}.", 409)
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(destination)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        entry = next((e for e in self.entries()
                      if e.contrato and e.contrato.parent == destination.resolve()), None)
        if entry is None:
            raise ModelVersionError("modelo_no_valido", "El modelo importado no aparece en el catálogo.")
        return entry

    def delete_imported(self, entry: ModelEntry) -> None:
        if entry.origen != "importado" or entry.contrato is None:
            raise ModelVersionError(
                "no_borrable", "Solo se pueden borrar modelos importados desde el panel.", 409)
        folder = entry.contrato.parent.resolve()
        if not folder.is_relative_to(self.imports_dir.resolve()) or folder == self.imports_dir.resolve():
            raise ModelVersionError("no_borrable", "La carpeta no es de un modelo importado.", 409)
        shutil.rmtree(folder)


# ── Carga de modelos ────────────────────────────────────────────────


class PredictorCache:
    """Modelos cargados por (tipo, contrato): cambiar uno no recarga el otro."""

    def __init__(self) -> None:
        self._loaded: dict[tuple[str, str], object] = {}

    @staticmethod
    def _key(entry: ModelEntry) -> tuple[str, str]:
        return entry.tipo, f"{entry.contrato}:{entry.sha256}"

    def _load(self, entry: ModelEntry):
        key = self._key(entry)
        if key not in self._loaded:
            if entry.tipo == "bilstm":
                from backend.models.bilstm import BilstmPredictor

                self._loaded[key] = BilstmPredictor(entry.contrato)
            else:
                from backend.models.mbert import MbertPredictor, MbertTokenizer

                policy = MbertTokenizer(entry.contrato)
                self._loaded[key] = (policy, MbertPredictor(policy))
        return self._loaded[key]

    def build(self, selection: dict[str, ModelEntry | None], weights: dict[str, float],
              required: set[str]):
        """Servicio con los modelos elegidos. Los de `required` deben cargar; si otro falla,
        el servicio sigue sin él (como siempre ha pasado con BETO al arrancar)."""
        from backend.services.analysis import AnalysisService

        loaded: dict[str, object] = {}
        for tipo, entry in selection.items():
            if entry is None:
                continue
            try:
                loaded[tipo] = self._load(entry)
            except Exception:
                if tipo in required:
                    raise
                logger.exception("No se pudo cargar el modelo %s %s", tipo, entry.id)
        bilstm = loaded.get("bilstm")
        policy, mbert = loaded.get("mbert", (None, None))
        contracts = {}
        if bilstm is not None:
            contracts["bilstm"] = bilstm.contract
        if mbert is not None:
            contracts["mbert"] = mbert.contract
        if not contracts:
            raise RuntimeError("No se pudo cargar ningún modelo")
        try:
            calibrated = Combination.load(COMBINATION_FILE)
        except Exception:
            calibrated = None
        combination = Combination.for_models(contracts, weights, calibrated)
        return AnalysisService(bilstm, mbert_predictor=mbert, mbert_text_policy=policy,
                               combination=combination)

    def keep(self, selection: dict[str, ModelEntry | None]) -> None:
        """Suelta los modelos que ya no se usan."""
        wanted = {self._key(e) for e in selection.values() if e is not None}
        dropped = [key for key in self._loaded if key not in wanted]
        for key in dropped:
            del self._loaded[key]
        if dropped:
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass


def deployed_types(service) -> set[str]:
    if service is None:
        return set()
    return {name for name, value in (("bilstm", service.predictor),
                                     ("mbert", service.mbert_predictor)) if value is not None}


def smoke_test(service) -> None:
    """Una predicción real con los modelos cargados antes de dar por bueno un cambio."""
    from backend.schemas.analysis import AnalysisRequest

    results = service.analyze(AnalysisRequest(texto=SMOKE_TEXT)).response.resultados
    failed = [name for name in deployed_types(service)
              if getattr(results.get(name), "estado", None) != "ok"]
    if failed:
        raise RuntimeError(f"No respondió: {', '.join(failed)}")


# ── Despliegue ──────────────────────────────────────────────────────


def default_weights() -> dict[str, float]:
    try:
        return dict(Combination.load(COMBINATION_FILE).weights)
    except Exception:
        logger.exception("No se pudo leer la combinación calibrada; pesos 0,2/0,8")
        return {"bilstm": 0.2, "mbert": 0.8}


@dataclass
class DeploymentState:
    deployed: dict[str, str | None]
    weights: dict[str, float]
    history: list[dict] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {"desplegados": dict(self.deployed), "pesos": dict(self.weights)}


class ModelDeploymentManager:
    def __init__(
        self,
        catalog: ModelCatalog | None = None,
        state_file: Path = STATE_FILE,
        builder: Callable | None = None,
        check: Callable = smoke_test,
        on_swap: Callable | None = None,
        release: Callable | None = None,
    ) -> None:
        self.catalog = catalog or ModelCatalog()
        self.state_file = Path(state_file)
        if builder is None:
            cache = PredictorCache()
            builder, release = cache.build, cache.keep
        self.builder = builder
        self.release = release or (lambda selection: None)
        self.check = check
        self.on_swap = on_swap
        self.state = DeploymentState({tipo: None for tipo in TYPES}, default_weights())
        self.loaded: set[str] = set()
        self._lock = threading.Lock()

    # ── Estado ──────────────────────────────────────────────────────

    def _read_state(self) -> DeploymentState | None:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            deployed = data["desplegados"]
            weights = {name: float(data["pesos"][name]) for name in TYPES}
            if not isinstance(deployed, dict) or abs(sum(weights.values()) - 1) > 1e-6 \
                    or any(w < 0 for w in weights.values()):
                raise ValueError("estado no válido")
            history = data.get("historial")
            return DeploymentState(
                {tipo: deployed.get(tipo) or None for tipo in TYPES}, weights,
                history if isinstance(history, list) else [],
            )
        except FileNotFoundError:
            return None
        except Exception:
            logger.exception("Estado de modelos no válido en %s; se usan los predeterminados",
                             self.state_file)
            return None

    def _save(self, state: DeploymentState) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        data = {**state.snapshot(), "historial": state.history[-HISTORY_LIMIT:]}
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_file)

    def _default_state(self) -> DeploymentState:
        return DeploymentState(self.catalog.defaults(), default_weights())

    def history(self) -> list[dict]:
        return list(reversed(self.state.history))

    def previous_state(self) -> dict | None:
        """Estado anterior al último cambio, al que llevaría «volver atrás»."""
        if not self.state.history:
            return None
        previous = self.state.history[-1].get("anterior")
        return previous if isinstance(previous, dict) else None

    def selection(self, deployed: dict[str, str | None] | None = None) -> dict[str, ModelEntry | None]:
        deployed = self.state.deployed if deployed is None else deployed
        return {tipo: self.catalog.get(tipo, deployed.get(tipo)) for tipo in TYPES}

    def summary(self) -> str | None:
        """Texto corto de lo desplegado y cargado, para el resumen del panel."""
        selection = self.selection()
        parts = [f"{selection[t].nombre} ({selection[t].id})" for t in TYPES
                 if t in self.loaded and selection[t] is not None]
        return " · ".join(parts) or None

    # ── Arranque ────────────────────────────────────────────────────

    def start(self):
        """Carga lo guardado; si no carga nada, lo predeterminado. Devuelve el servicio."""
        saved = self._read_state()
        default = self._default_state()
        candidates = [saved, default] if saved else [default]
        for state in candidates:
            selection = {tipo: entry if entry and entry.deployable else None
                         for tipo, entry in self.selection(state.deployed).items()}
            for tipo, entry in selection.items():
                if state.deployed.get(tipo) and entry is None:
                    logger.error("El modelo %s %s no está disponible", tipo, state.deployed[tipo])
            if not any(selection.values()):
                continue
            try:
                service = self.builder(selection, state.weights, set())
            except Exception:
                logger.exception("No se pudieron cargar los modelos desplegados")
                continue
            self.state = DeploymentState(state.deployed, state.weights,
                                         saved.history if saved else [])
            self.loaded = deployed_types(service)
            self.release(selection)
            return service
        if saved:
            self.state = DeploymentState(saved.deployed, saved.weights, saved.history)
        self.loaded = set()
        return None

    # ── Cambios ─────────────────────────────────────────────────────

    def _apply(self, deployed: dict[str, str | None], weights: dict[str, float],
               required: set[str], entry: dict) -> None:
        if not self._lock.acquire(blocking=False):
            raise ModelVersionError("cambio_en_curso", "Ya hay un cambio de modelos en curso.", 409)
        try:
            selection = self.selection(deployed)
            for tipo in TYPES:
                if deployed.get(tipo) and selection[tipo] is None:
                    raise ModelVersionError(
                        "modelo_desconocido", f"El modelo {deployed[tipo]} ya no está en el catálogo.", 404)
            for tipo in required:
                model = selection[tipo]
                if model is not None and not model.deployable:
                    raise ModelVersionError(
                        "modelo_archivado" if model.estado == "archivado" else "modelo_no_valido",
                        model.motivo or "Ese modelo no se puede desplegar.",
                    )
            if not any(selection.values()):
                raise ModelVersionError(
                    "ultimo_modelo", "Debe quedar al menos un modelo desplegado.", 409)
            try:
                service = self.builder(selection, weights, required)
                self.check(service)
            except Exception as error:
                logger.exception("No se pudo aplicar el cambio de modelos %s", entry)
                self.release(self.selection())
                raise ModelVersionError(
                    "modelo_no_cargo",
                    "Los modelos no se pudieron cargar o no respondieron; sigue lo que había.",
                    502,
                ) from error
            if self.on_swap is not None:
                self.on_swap(service)
            previous = self.state.snapshot()
            history = self.state.history + [{
                **entry, "anterior": previous,
                "fecha": datetime.now(timezone.utc).isoformat(),
            }]
            self.state = DeploymentState(dict(deployed), dict(weights), history[-HISTORY_LIMIT:])
            self.loaded = deployed_types(service)
            self._save(self.state)
            self.release(selection)
        finally:
            self._lock.release()

    def deploy(self, tipo: str, model_id: str, actor: str | None) -> None:
        if tipo not in TYPES:
            raise ModelVersionError("tipo_desconocido", "Tipo de modelo desconocido.", 404)
        entry = self.catalog.get(tipo, model_id)
        if entry is None:
            raise ModelVersionError("modelo_desconocido", "Ese modelo no existe.", 404)
        if not entry.deployable:
            raise ModelVersionError(
                "modelo_archivado" if entry.estado == "archivado" else "modelo_no_valido",
                entry.motivo or "Ese modelo no se puede desplegar.",
            )
        if self.state.deployed.get(tipo) == model_id and tipo in self.loaded:
            raise ModelVersionError("ya_desplegado", "Ese modelo ya está desplegado.", 409)
        deployed = {**self.state.deployed, tipo: model_id}
        self._apply(deployed, self.state.weights, {tipo},
                    {"accion": "desplegar", "tipo": tipo, "version": model_id, "por": actor})

    def retire(self, tipo: str, actor: str | None) -> None:
        if tipo not in TYPES:
            raise ModelVersionError("tipo_desconocido", "Tipo de modelo desconocido.", 404)
        if not self.state.deployed.get(tipo):
            raise ModelVersionError("ya_retirado", "Ese tipo no tiene ningún modelo desplegado.", 409)
        if not (self.loaded - {tipo}):
            raise ModelVersionError(
                "ultimo_modelo", "No se puede retirar: debe quedar al menos un modelo desplegado.", 409)
        deployed = {**self.state.deployed, tipo: None}
        self._apply(deployed, self.state.weights, set(),
                    {"accion": "retirar", "tipo": tipo, "version": self.state.deployed[tipo],
                     "por": actor})

    def set_weights(self, weights: dict[str, float], actor: str | None) -> None:
        weights = {name: round(float(weights[name]), 4) for name in TYPES}
        if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1) > 1e-6:
            raise ModelVersionError("pesos_no_validos", "Los pesos deben ser ≥ 0 y sumar 1.")
        if all(abs(weights[n] - self.state.weights[n]) < 1e-9 for n in TYPES):
            raise ModelVersionError("pesos_iguales", "Esos ya son los pesos actuales.", 409)
        self._apply(self.state.deployed, weights, set(),
                    {"accion": "pesos", "tipo": None, "version": None, "pesos": weights,
                     "por": actor})

    def revert(self, actor: str | None) -> None:
        previous = self.previous_state()
        if previous is None:
            raise ModelVersionError("sin_estado_anterior", "No hay un cambio anterior que deshacer.", 409)
        deployed = {tipo: (previous.get("desplegados") or {}).get(tipo) for tipo in TYPES}
        weights = {name: float((previous.get("pesos") or {}).get(name, 0)) for name in TYPES}
        required = {tipo for tipo in TYPES
                    if deployed[tipo] and deployed[tipo] != self.state.deployed.get(tipo)}
        self._apply(deployed, weights, required,
                    {"accion": "revertir", "tipo": None, "version": None, "por": actor})

    def delete(self, tipo: str, model_id: str) -> None:
        entry = self.catalog.get(tipo, model_id)
        if entry is None:
            raise ModelVersionError("modelo_desconocido", "Ese modelo no existe.", 404)
        previous = (self.previous_state() or {}).get("desplegados") or {}
        if self.state.deployed.get(tipo) == model_id or previous.get(tipo) == model_id:
            raise ModelVersionError(
                "modelo_en_uso",
                "Está desplegado o es al que se volvería con «Volver atrás»; no se puede borrar.", 409)
        self.catalog.delete_imported(entry)

    # ── Métricas ────────────────────────────────────────────────────

    def active_metrics(self, tipo: str) -> MetricsResponse | None:
        entry = self.catalog.get(tipo, self.state.deployed.get(tipo))
        return entry.load_metrics() if entry else None
