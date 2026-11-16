"""Calibración desde el panel (Administración → Calibración).

Calibra una pareja BiLSTM + BETO/mBERT con las predicciones fuera de pliegue de cada modelo,
con el mismo motor que `datos_comunes/calibrar_conjunto.py` (`calibrar_predicciones`). Con la
pareja B6 + M3b, peso 0,20 y temperaturas ajustadas da exactamente la calibración de producción.

Editable: la pareja, el peso del BiLSTM y las temperaturas (ajustadas o a mano). La semilla no:
es la del entrenamiento de cada modelo (`semillas[0]` de su contrato).

Guardar no toca ningún contrato existente ni lo desplegado: crea `datasets/calibraciones/<versión>/`
con `combinacion.json`, el informe y un contrato calibrado por modelo que apunta a los mismos
pesos (sin copiarlos). Modelos los muestra como «Disponible» y se despliegan desde allí.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
import logging
import math
from pathlib import Path
import secrets
import shutil
import threading

import pandas as pd

from backend.models.contrato import ModelContract, resolve
from backend.services.model_registry import (
    CALIBRATIONS_DIR, COMBINATION_FILE, TYPES, ModelCatalog, ModelEntry, calibration_for,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
COMUN_V1 = ROOT / "datasets" / "comun_v1"
OOF = "predicciones_fuera_de_pliegue.csv"
LABEL_COLUMNS = {"id_articulo", "fuente", "etiqueta_falsa"}
WEIGHT_STEP = 0.05


class CalibrationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _engine():
    from datos_comunes import calibrar_conjunto

    return calibrar_conjunto


@lru_cache(maxsize=1)
def _comun() -> tuple[pd.DataFrame, str] | None:
    """Desarrollo de comun_v1 y su SHA-256 (para unir las predicciones que no traen etiquetas)."""
    try:
        from datos_comunes.comun import leer, manifiesto

        return (leer("fragmentos_desarrollo.csv", COMUN_V1),
                manifiesto(COMUN_V1)["archivos"]["fragmentos_desarrollo.csv"]["sha256"])
    except Exception:
        logger.exception("No se pudo leer comun_v1 para calibrar")
        return None


def _comun_sha() -> str | None:
    try:
        manifest = json.loads((COMUN_V1 / "manifest.json").read_text(encoding="utf-8"))
        return manifest["archivos"]["fragmentos_desarrollo.csv"]["sha256"]
    except (OSError, ValueError, KeyError):
        return None


_seeds_cache: dict[tuple[str, int, int], tuple[set[int], bool]] = {}


def _seeds_and_labels(path: Path) -> tuple[set[int], bool]:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _seeds_cache:
        columns = set(pd.read_csv(path, nrows=0).columns)
        seeds = set(pd.read_csv(path, usecols=["semilla"]).semilla.astype(int).unique().tolist())
        _seeds_cache[key] = (seeds, LABEL_COLUMNS <= columns)
    return _seeds_cache[key]


def oof_path(contract_path: Path, data: dict) -> Path | None:
    """Dónde están las predicciones fuera de pliegue de un modelo.

    1. El campo `predicciones_fuera_de_pliegue` del contrato (los reentrenados con pliegues y los
       calibrados desde el panel).
    2. Junto al contrato de `origen` (B6 y M3b de producción: su carpeta final de comun_v1_corridas).
    3. Junto al propio contrato.
    """
    folder = Path(contract_path).parent
    candidates = []
    if data.get("predicciones_fuera_de_pliegue"):
        try:
            candidates.append(resolve(data["predicciones_fuera_de_pliegue"], folder))
        except ValueError:
            pass
    if data.get("origen"):
        # Desde la raíz: buscarlo junto al contrato daría el propio contrato («…/contrato.json»).
        try:
            candidates.append(resolve(data["origen"]).parent / OOF)
        except ValueError:
            pass
    candidates.append(folder / OOF)
    return next((path for path in candidates if path.is_file()), None)


class CalibrationManager:
    def __init__(self, catalog: ModelCatalog, output_dir: Path = CALIBRATIONS_DIR,
                 comun: callable = _comun, comun_sha: callable = _comun_sha) -> None:
        self.catalog = catalog
        self.output_dir = Path(output_dir)
        self._comun = comun
        self._comun_sha = comun_sha
        self._lock = threading.Lock()

    # ── Candidatos ──────────────────────────────────────────────────

    def _contract(self, entry: ModelEntry) -> dict:
        return json.loads(entry.contrato.read_text(encoding="utf-8"))

    def candidate(self, entry: ModelEntry) -> dict:
        """Si un modelo se puede calibrar y, si no, por qué."""
        info = {"id": entry.id, "tipo": entry.tipo, "version": entry.version, "nombre": entry.nombre,
                "estado": entry.estado, "origen": entry.origen, "fecha": entry.fecha,
                "temperatura": entry.temperatura, "apto": False, "motivo": None, "semilla": None,
                "conjunto": None, "predicciones": None}
        if entry.contrato is None or entry.estado not in ("disponible", "pendiente_calibrar"):
            return {**info, "motivo": "Sin contrato válido (archivado, no válido o no admitido)."}
        try:
            data = self._contract(entry)
            seed = int((data.get("semillas") or [None])[0])
        except (OSError, ValueError, TypeError):
            return {**info, "motivo": "El contrato no indica su semilla."}
        info["semilla"] = seed
        info["conjunto"] = data.get("sha256_conjunto")
        path = oof_path(entry.contrato, data)
        if path is None:
            return {**info, "motivo": "No tiene predicciones fuera de pliegue: reentrénalo con "
                                      "«Preparar para calibrar»."}
        info["predicciones"] = _relative(path)
        try:
            seeds, labels = _seeds_and_labels(path)
        except Exception:
            return {**info, "motivo": f"No se pudieron leer sus predicciones ({_relative(path)})."}
        if seed not in seeds:
            return {**info, "motivo": f"Sus predicciones no tienen la semilla {seed} de su entrenamiento."}
        if not labels and data.get("sha256_conjunto") != self._comun_sha():
            return {**info, "motivo": "Sus predicciones no traen etiquetas y su conjunto no está en este equipo."}
        return {**info, "apto": True}

    def candidates(self) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {tipo: [] for tipo in TYPES}
        for entry in self.catalog.entries():
            if entry.estado == "archivado":
                continue
            groups[entry.tipo].append(self.candidate(entry))
        return groups

    def _entry(self, tipo: str, model_id: str) -> ModelEntry:
        entry = self.catalog.get(tipo, model_id)
        if entry is None:
            raise CalibrationError("modelo_no_encontrado", f"No existe el modelo {model_id}.", 404)
        info = self.candidate(entry)
        if not info["apto"]:
            raise CalibrationError("modelo_no_calibrable", f"{entry.nombre} ({entry.id}): {info['motivo']}", 422)
        return entry

    # ── Calibrar ────────────────────────────────────────────────────

    def _run(self, bilstm_id: str, mbert_id: str, weight: float, temperatures: dict | None,
             motivo: str, version: str | None) -> tuple[dict, dict[str, ModelEntry], dict[str, dict]]:
        if not 0.0 <= weight <= 1.0 or not math.isfinite(weight):
            raise CalibrationError("peso_no_valido", "El peso del BiLSTM debe estar entre 0 y 1.", 422)
        entries = {"bilstm": self._entry("bilstm", bilstm_id), "mbert": self._entry("mbert", mbert_id)}
        contracts = {tipo: self._contract(entry) for tipo, entry in entries.items()}
        paths = {tipo: oof_path(entries[tipo].contrato, contracts[tipo]) for tipo in TYPES}
        comun = None
        if any(contract.get("sha256_conjunto") == self._comun_sha() for contract in contracts.values()):
            comun = self._comun()
        try:
            result = _engine().calibrar_predicciones(
                paths["bilstm"], paths["mbert"], contracts["bilstm"], contracts["mbert"], round(weight, 4),
                motivo, temperatures, version, desarrollo=comun[0] if comun else None)
        except (ValueError, PermissionError) as error:
            raise CalibrationError("no_se_pudo_calibrar", str(error), 422) from error
        return result, entries, contracts

    def reference(self) -> dict | None:
        """Calibración de producción (`datasets/combinacion_produccion/combinacion.json`)."""
        try:
            return json.loads(COMBINATION_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def preview(self, bilstm_id: str, mbert_id: str, weight: float, temperatures: dict | None) -> dict:
        result, entries, _ = self._run(bilstm_id, mbert_id, weight, temperatures, "", None)
        result.pop("_predicciones", None)
        return self._present(result, entries)

    def _present(self, result: dict, entries: dict[str, ModelEntry]) -> dict:
        combination = result["combinacion"]
        reference = self.reference() or {}
        same = (combination["temperaturas"] == reference.get("temperaturas")
                and combination["pesos"] == reference.get("pesos"))
        adjusted = combination.get("temperaturas_ajustadas") or combination["temperaturas"]
        return {
            "combinacion": combination,
            "modelos": {tipo: {"id": entry.id, "nombre": entry.nombre, "version": entry.version}
                        for tipo, entry in entries.items()},
            "temperaturas": {
                tipo: {"ajustada": adjusted[tipo], "usada": combination["temperaturas"][tipo],
                       "manual": tipo in (combination.get("temperaturas_manuales") or [])}
                for tipo in TYPES},
            "igual_a_produccion": same,
            "conjunto_comun": result.get("conjunto_comun", True),
            "resultado": {key: value for key, value in result.items()
                          if key not in ("combinacion", "_predicciones")},
        }

    def save(self, bilstm_id: str, mbert_id: str, weight: float, temperatures: dict | None, motivo: str,
             actor: str | None) -> dict:
        motivo = " ".join((motivo or "").split())
        reference = self.reference() or {}
        default_weight = (reference.get("pesos") or {}).get("bilstm", 0.2)
        manual = any(value is not None for value in (temperatures or {}).values())
        if (abs(weight - default_weight) > 1e-9 or manual) and not motivo:
            raise CalibrationError("falta_motivo", "Explica el motivo: el peso o las temperaturas no son los "
                                                   "de la calibración vigente.", 422)
        if not motivo:
            motivo = reference.get("motivo_pesos") or "Calibración desde el panel con los valores por defecto."
        with self._lock:
            stamp = datetime.now(timezone.utc)
            token = secrets.token_hex(2)
            comun_sha = self._comun_sha()
            prefix = "panel"
            contracts_preview = {
                "bilstm": self._contract(self._entry("bilstm", bilstm_id)),
                "mbert": self._contract(self._entry("mbert", mbert_id)),
            }
            if contracts_preview["bilstm"].get("sha256_conjunto") == comun_sha:
                prefix = json.loads((Path(COMUN_V1) / "manifest.json").read_text(encoding="utf-8"))["version"]
            version = f"{prefix}_conjunta_{stamp:%Y%m%d}_{token}"
            result, entries, contracts = self._run(bilstm_id, mbert_id, weight, temperatures, motivo, version)
            final = self.output_dir / version
            partial = self.output_dir / f".{version}.parcial"
            if final.exists():
                raise CalibrationError("version_repetida", "Ya existe una calibración con esa versión.", 409)
            shutil.rmtree(partial, ignore_errors=True)
            partial.mkdir(parents=True)
            try:
                combination = result["combinacion"]
                variants = {}
                for tipo, entry in entries.items():
                    variants[tipo] = self._write_variant(partial, final, tipo, entry, contracts[tipo],
                                                         combination, version, stamp, token)
                combination["contratos"] = {tipo: variant["version"] for tipo, variant in variants.items()}
                combination["origen"] = "panel"
                combination["modelos_origen"] = {tipo: {"id": entry.id, "version": entry.version}
                                                 for tipo, entry in entries.items()}
                combination["fecha"] = stamp.isoformat()
                combination["por"] = actor
                predictions = result.pop("_predicciones", None)
                (partial / "combinacion.json").write_text(
                    json.dumps(combination, ensure_ascii=False, indent=2) + "\n", "utf-8")
                (partial / "metricas.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
                if result.get("conjunto_comun", True) and "validacion_por_fuente" in result:
                    (partial / "RESUMEN.md").write_text(_engine().resumen_md(result), "utf-8")
                if predictions is not None:
                    predictions.to_csv(partial / "predicciones_combinadas_fuera_de_pliegue.csv", index=False)
                partial.rename(final)
            except BaseException:
                shutil.rmtree(partial, ignore_errors=True)
                raise
        logger.info("Calibración %s guardada (%s + %s)", version, bilstm_id, mbert_id)
        return self.get(version)

    def _write_variant(self, partial: Path, final: Path, tipo: str, entry: ModelEntry, data: dict,
                       combination: dict, version: str, stamp: datetime, token: str) -> dict:
        """Contrato calibrado: el de origen con la temperatura nueva y las rutas desde la raíz, para
        que use los mismos pesos sin copiarlos."""
        contract = ModelContract.load(entry.contrato, tipo, allow_provisional=True)
        seed = int(data["semillas"][0])
        variant = json.loads(json.dumps(data))
        variant["version"] = f"{entry.version}_cal_{stamp:%Y%m%d}_{token}"
        variant["temperatura"] = combination["temperaturas"][tipo]
        variant["temperatura_provisional"] = False
        variant["nota_temperatura"] = (f"Calibración {version} desde el panel (Administración → Calibración), "
                                       "con las predicciones fuera de pliegue del modelo.")
        variant["calibracion"] = f"{_relative(final)}/combinacion.json"
        variant["calibrado_desde"] = {"id": entry.id, "version": entry.version,
                                      "contrato": _relative(entry.contrato)}
        variant["checkpoints"][f"s{seed}"]["ruta"] = _relative(contract.checkpoint)
        if tipo == "mbert" and variant.get("tokenizador"):
            variant["tokenizador"]["ruta"] = _relative(contract.resolve(variant["tokenizador"]["ruta"]))
        variant["predicciones_fuera_de_pliegue"] = _relative(oof_path(entry.contrato, data))
        if variant.get("procedencia"):
            source = entry.contrato.parent / variant["procedencia"]
            variant["procedencia"] = _relative(source) if source.is_file() else None
        folder = partial / tipo
        folder.mkdir()
        (folder / "contrato.json").write_text(json.dumps(variant, ensure_ascii=False, indent=2) + "\n", "utf-8")
        metrics = entry.load_metrics()
        if metrics is not None:  # las métricas del modelo no cambian: el umbral 0,5 no depende de T
            payload = metrics.model_dump(mode="json")
            payload["version"] = variant["version"]
            (folder / "metricas.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        return variant

    # ── Listar ──────────────────────────────────────────────────────

    def _summary(self, combination: dict, folder: Path | None, origin: str) -> dict:
        return {
            "version": combination.get("version"),
            "origen": origin,
            "fecha": combination.get("fecha"),
            "por": combination.get("por"),
            "temperaturas": combination.get("temperaturas"),
            "temperaturas_ajustadas": combination.get("temperaturas_ajustadas"),
            "temperaturas_manuales": combination.get("temperaturas_manuales") or [],
            "pesos": combination.get("pesos"),
            "motivo": combination.get("motivo_pesos"),
            "contratos": combination.get("contratos"),
            "modelos_origen": combination.get("modelos_origen"),
            "ruta": _relative(folder) if folder else _relative(COMBINATION_FILE.parent),
        }

    def overview(self) -> dict:
        reference = self.reference()
        saved = []
        if self.output_dir.is_dir():
            for folder in sorted(self.output_dir.iterdir(), reverse=True):
                path = folder / "combinacion.json"
                if folder.name.startswith(".") or not path.is_file():
                    continue
                try:
                    saved.append(self._summary(json.loads(path.read_text(encoding="utf-8")), folder, "panel"))
                except ValueError:
                    continue
        saved.sort(key=lambda item: item.get("fecha") or "", reverse=True)
        return {"produccion": self._summary(reference, None, "produccion") if reference else None,
                "calibraciones": saved}

    def get(self, version: str) -> dict:
        if not version or "/" in version or version.startswith("."):
            raise CalibrationError("calibracion_no_encontrada", "Calibración no encontrada.", 404)
        reference = self.reference() or {}
        if version == reference.get("version"):
            folder, origin = ROOT / "datasets" / "comun_v1_corridas" / "calibracion", "produccion"
            combination = reference
        else:
            folder, origin = self.output_dir / version, "panel"
            try:
                combination = json.loads((folder / "combinacion.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise CalibrationError("calibracion_no_encontrada", "Calibración no encontrada.", 404) from error
        try:
            result = json.loads((folder / "metricas.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result = {}
        result.pop("combinacion", None)
        return {**self._summary(combination, folder if origin == "panel" else None, origin),
                "resultado": result}

    def current(self, deployed: dict[str, str]) -> dict | None:
        """Calibración de la pareja desplegada ({tipo: versión}), si la hay."""
        combination = calibration_for(deployed)
        if combination is None:
            return None
        return {"version": combination.version, "temperaturas": combination.temperatures,
                "pesos": combination.weights, "contratos": combination.model_versions}
