"""Entrenamientos lanzados desde el panel (Administración → Entrenamiento).

Reentrena un BiLSTM o un BETO/mBERT desde cero con la receta del modelo desplegado de su tipo
y el conjunto que se elija: `datasets/comun_v1/`, una versión del panel de datasets o un conjunto
combinado (`datasets/conjuntos/`, ver backend/services/combined_sets.py). Lanza
`bilstm/entrenar.py reentrenar` o `mBERT/entrenar.py reentrenar` en otro proceso y sigue su
progreso leyendo su registro.

Reglas:
- Un solo entrenamiento a la vez (la GPU es una).
- No despliega, no borra y no sobrescribe modelos: el resultado es una carpeta nueva en
  `datasets/entrenamientos/<tipo>/<versión>/`, que Modelos detecta sola («Pendiente de calibrar»).
  El script escribe en una carpeta oculta y solo la renombra al terminar.
- El estado vive en `backend/.local/entrenamientos/<id>/` (fuera de Git) y se calcula al leerlo:
  sobrevive a un reinicio de la API, porque el proceso de entrenamiento sigue por su cuenta.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Callable
import unicodedata

from backend.models.contrato import resolve

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
JOBS_DIR = ROOT / "backend" / ".local" / "entrenamientos"
OUTPUT_DIR = ROOT / "datasets" / "entrenamientos"
COMUN_V1 = ROOT / "datasets" / "comun_v1"
SCRIPTS = {"bilstm": ROOT / "bilstm" / "entrenar.py", "mbert": ROOT / "mBERT" / "entrenar.py"}
PRODUCTION_RECIPES = {
    "bilstm": ROOT / "datasets" / "bilstm_produccion" / "modelo" / "config.json",
    "mbert": ROOT / "datasets" / "mbert_produccion" / "modelo" / "config.json",
}
FASTTEXT_CACHE = ROOT / "datasets" / "comun_v1_corridas" / "cache_fasttext_cc300.npz"
DEPS = ROOT / "backend" / ".deps"
TRAINING_FILE = "fragmentos_desarrollo.csv"
TEST_FILE = "fragmentos_prueba.csv"
LOG_TAIL_BYTES = 256 * 1024
CANCEL_GRACE_SECONDS = 15
# Fracción del total que se da por hecha al entrar en cada fase (la barra del panel).
PHASE_PROGRESS = {"preparando": 0.02, "descargando_base": 0.04, "entrenando": 0.06,
                  "evaluando": 0.92, "guardando": 0.97, "terminado": 1.0}


class TrainingError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


# ── Recetas ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Recipe:
    tipo: str
    path: Path
    data: dict
    origen: str  # desplegado | produccion
    modelo: str | None = None  # id del modelo del que sale la receta

    def summary(self) -> dict:
        data = self.data
        return {
            "configuracion": data.get("configuracion"),
            "origen": self.origen,
            "modelo": self.modelo,
            "ruta": _relative(self.path),
            "epocas": data.get("epocas_fijas"),
            "brazo": list(data.get("brazo") or []),
            "max_tokens": data.get("max_tokens") or data.get("max_length"),
            "modelo_base": (data.get("modelo") if self.tipo == "mbert" else None),
            "parametros": {key: data.get(key) for key in (
                ("pooling", "hidden_dim", "dropout", "lr", "weight_decay", "lote")
                if self.tipo == "bilstm" else
                ("lr", "weight_decay", "calentamiento", "lote_efectivo", "microlote")
            ) if data.get(key) is not None},
        }


def _relative(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _read_recipe(path: Path, tipo: str) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("configuracion") or not data.get("epocas_fijas"):
        return None
    if tipo == "bilstm" and data.get("modelo", "bilstm") != "bilstm":
        return None
    if tipo == "mbert" and data.get("modelo") in (None, "bilstm"):
        return None
    return data


def recipe_next_to(contract_path: Path, tipo: str) -> Path | None:
    """`config.json` de la corrida que dejó el checkpoint de un contrato."""
    try:
        contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
        seeds = contract.get("semillas") or []
        route = contract["checkpoints"][f"s{seeds[0]}"]["ruta"]
        checkpoint = resolve(route, Path(contract_path).parent)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    # BiLSTM: …/modelo.pt; BETO: …/best_model/ → el config.json está en la carpeta de la corrida.
    folder = checkpoint.parent
    candidate = folder / "config.json"
    return candidate if candidate.is_file() else None


# ── Fuentes ─────────────────────────────────────────────────────────


def _rows_by_label(data: bytes) -> dict[int, int]:
    counts: dict[int, int] = {0: 0, 1: 0}
    for row in csv.DictReader(io.StringIO(data.decode("utf-8"))):
        counts[int(row["etiqueta_falsa"])] += 1
    return counts


def _is_standard(manifest: dict) -> bool:
    return "fragmentos_entrenamiento.csv" in (manifest.get("archivos") or {})


FOLDS = ("F1", "F2", "F3")


def assign_folds(training: bytes) -> tuple[bytes, bool]:
    """Reparte los grupos de entrenamiento en F1–F3 (columna `pliegue`), por clase y con un sorteo
    fijo que sale de la clave del grupo: los mismos datos dan siempre los mismos pliegues. Devuelve
    el CSV y si cada pliegue tiene las dos clases (si no, no se puede preparar la calibración)."""
    reader = csv.DictReader(io.StringIO(training.decode("utf-8")))
    rows = list(reader)
    labels: dict[str, list[int]] = {}
    for row in rows:
        labels.setdefault(row["grupo"], []).append(int(row["etiqueta_falsa"]))
    by_class: dict[int, list[str]] = {0: [], 1: []}
    for group, values in labels.items():
        by_class[max(set(values), key=values.count)].append(group)
    fold_of: dict[str, str] = {}
    for groups in by_class.values():
        ordered = sorted(groups, key=lambda group: sha256(group.encode("utf-8")).hexdigest())
        for index, group in enumerate(ordered):
            fold_of[group] = FOLDS[index % len(FOLDS)]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "pliegue": fold_of[row["grupo"]]})
    enough = all(len(groups) >= len(FOLDS) for groups in by_class.values())
    return buffer.getvalue().encode("utf-8"), enough


def write_panel_set(folder: Path, files: dict[str, bytes], version: dict) -> dict:
    """Escribe una versión del panel con el formato de comun_v1 en `folder`.

    La partición de entrenamiento pasa a ser `fragmentos_desarrollo.csv` (lo que leen
    `datos_comunes/comun.py` y los scripts), repartida en pliegues F1–F3 por grupo, y la de
    prueba, `fragmentos_prueba.csv`."""
    training = files.get("fragmentos_entrenamiento.csv", b"")
    test = files.get("fragmentos_prueba.csv", b"")
    counts = _rows_by_label(training) if training else {0: 0, 1: 0}
    if not counts[0] and not counts[1]:
        raise TrainingError("sin_entrenamiento", "La versión no tiene fragmentos de entrenamiento.", 422)
    if not counts[0] or not counts[1]:
        raise TrainingError("una_sola_clase",
                            "El entrenamiento de la versión solo tiene una clase (falsa o real).", 422)
    folder.mkdir(parents=True, exist_ok=True)
    original = sha256(training).hexdigest()
    training, foldable = assign_folds(training)
    outputs = {TRAINING_FILE: training}
    if test.count(b"\n") > 1:
        outputs[TEST_FILE] = test
    manifest = {
        "version": "panel_estandar_v1",
        "nombre": version.get("nombre"),
        "id": str(version.get("id")),
        "origen": "panel",
        "sha256_entrenamiento_panel": original,
        "pliegues": "F1–F3 por grupo y clase (sorteo fijo por la clave del grupo)",
        "archivos": {},
    }
    for name, data in outputs.items():
        (folder / name).write_bytes(data)
        manifest["archivos"][name] = {"sha256": sha256(data).hexdigest(), "filas": data.count(b"\n") - 1}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    return {"entrenamiento": counts[0] + counts[1], "reales": counts[0], "falsas": counts[1],
            "prueba": manifest["archivos"].get(TEST_FILE, {}).get("filas", 0), "plegable": foldable}


def _slug(value: str, limit: int = 32) -> str:
    plain = unicodedata.normalize("NFKD", value.lower())
    text = "".join(c if c.isascii() and c.isalnum() else "" if unicodedata.combining(c) else "-"
                   for c in plain)
    return "-".join(part for part in text.split("-") if part)[:limit].strip("-") or "dataset"


# ── Progreso ────────────────────────────────────────────────────────


def _tail(path: Path, size: int = LOG_TAIL_BYTES) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            length = stream.tell()
            stream.seek(max(0, length - size))
            return stream.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def parse_log(text: str) -> dict:
    """Fase, época, lote y pérdidas a partir de las líneas JSON del registro."""
    info: dict = {"fase": None, "epoca": None, "epocas": None, "lote": None, "lotes": None,
                  "perdidas": [], "modelo_base": None, "corrida": None, "corridas": None, "nombre": None}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        if "progreso" in data:
            info["fase"] = data["progreso"]
            if "corrida" in data and data["corrida"] != info["corrida"]:
                info["perdidas"] = []  # cada corrida (pliegue o final) tiene sus propias épocas
            for key in ("epoca", "epocas", "lote", "lotes", "modelo_base", "corrida", "corridas", "nombre"):
                if key in data:
                    info[key] = data[key]
        elif "epoca" in data and "perdida" in data:
            losses = [item for item in info["perdidas"] if item["epoca"] != data["epoca"]]
            info["perdidas"] = [*losses, {"epoca": int(data["epoca"]), "perdida": float(data["perdida"])}]
    return info


def overall_progress(info: dict) -> float:
    phase = info.get("fase")
    if phase != "entrenando":
        return PHASE_PROGRESS.get(phase, 0.0)
    epochs = info.get("epocas") or 0
    epoch, batch, batches = info.get("epoca") or 0, info.get("lote") or 0, info.get("lotes") or 0
    if not epochs or not epoch:
        return PHASE_PROGRESS["entrenando"]
    done = (epoch - 1 + (batch / batches if batches else 0)) / epochs
    runs, run = info.get("corridas") or 1, info.get("corrida") or 1
    done = (run - 1 + min(1.0, done)) / runs
    start, end = PHASE_PROGRESS["entrenando"], PHASE_PROGRESS["evaluando"]
    return round(start + (end - start) * min(1.0, max(0.0, done)), 4)


def _pid_running(pid: int | None, marker: str) -> bool:
    """El proceso sigue vivo y es el nuestro (no un pid reutilizado ni un zombi)."""
    if not pid:
        return False
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.parent.exists():
        try:
            return marker in cmdline.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return False
    try:  # sin /proc (no Linux): solo se puede comprobar que el pid existe
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return None


# ── Gestor ──────────────────────────────────────────────────────────


class TrainingManager:
    def __init__(
        self,
        jobs_dir: Path = JOBS_DIR,
        output_dir: Path = OUTPUT_DIR,
        comun_dir: Path = COMUN_V1,
        python: str | None = None,
        launcher: Callable | None = None,
        cuda: Callable[[], bool] | None = None,
        sets=None,
    ) -> None:
        self.jobs_dir = Path(jobs_dir)
        self._sets = sets  # CombinedSetManager (conjuntos combinados); se crea al usarlo
        self.output_dir = Path(output_dir)
        self.comun_dir = Path(comun_dir)
        venv = ROOT / "bilstm" / ".venv" / "bin" / "python"
        self.python = python or os.environ.get("ENTRENAMIENTO_PYTHON") or (
            str(venv) if venv.exists() else sys.executable)
        self.launcher = launcher or self._popen
        self._cuda = cuda
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen] = {}

    # ── Opciones ────────────────────────────────────────────────────

    def cuda_available(self) -> bool:
        if self._cuda is not None:
            return self._cuda()
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def recipe(self, tipo: str, deployed=None) -> Recipe:
        """Receta del modelo desplegado de ese tipo; si no la hay, la del de producción."""
        if deployed is not None and getattr(deployed, "contrato", None) is not None:
            path = recipe_next_to(deployed.contrato, tipo)
            data = _read_recipe(path, tipo) if path else None
            if data:
                return Recipe(tipo, path, data, "desplegado", deployed.id)
        path = PRODUCTION_RECIPES[tipo]
        data = _read_recipe(path, tipo)
        if not data:
            raise TrainingError("sin_receta", f"No se encontró la receta de {tipo} ({_relative(path)}).", 503)
        return Recipe(tipo, path, data, "produccion", None)

    def comun_source(self) -> dict | None:
        try:
            manifest = json.loads((self.comun_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        files = manifest.get("archivos") or {}
        return {
            "tipo": "comun_v1",
            "version": manifest.get("version"),
            "nombre": f"Conjunto común ({manifest.get('version') or 'comun_v1'})",
            "fragmentos": (files.get(TRAINING_FILE) or {}).get("filas"),
            "brazos": sorted(name[len("ablacion_"):-4] for name in files if name.startswith("ablacion_")),
            "con_prueba": False,
        }

    @property
    def sets(self):
        if self._sets is None:
            from backend.services.combined_sets import CombinedSetManager  # evita el import circular

            self._sets = CombinedSetManager()
        return self._sets

    def set_sources(self) -> list[dict]:
        """Conjuntos combinados de Datasets (comun_v1 + versiones del panel)."""
        sources = []
        for item in self.sets.list():
            summary = item.get("resumen") or {}
            total = summary.get("total_entrenamiento") or {}
            test = summary.get("prueba") or {}
            sources.append({
                "tipo": "conjunto",
                "version": item["version"],
                "nombre": item["nombre"],
                "fecha": item.get("fecha"),
                "fragmentos": total.get("fragmentos"),
                "fragmentos_prueba": test.get("fragmentos"),
                "incluye_comun": item["incluye_comun"],
                "balanceo": item.get("balanceo"),
                "apta": item["apto"],
                "motivo": item["motivo"],
                "con_prueba": bool(test.get("fragmentos")),
                "plegable": summary.get("plegable", True),
            })
        return sources

    @staticmethod
    def panel_sources(versions: list) -> list[dict]:
        sources = []
        for version in versions:
            manifest = version.manifiesto or {}
            standard = _is_standard(manifest)
            counts = (version.resumen.fragmentos_por_particion or {}) if version.resumen else {}
            sources.append({
                "tipo": "panel",
                "version_id": str(version.id),
                "nombre": version.nombre,
                "fecha": version.fecha.isoformat() if version.fecha else None,
                "fragmentos": counts.get("entrenamiento"),
                "fragmentos_prueba": counts.get("prueba"),
                "noticias": version.resumen.casos if version.resumen else None,
                "apta": standard,
                "motivo": None if standard else
                "Se creó antes del estándar de fragmentos: crea una versión nueva.",
                "con_prueba": bool(counts.get("prueba")),
            })
        return sources

    # ── Trabajos ────────────────────────────────────────────────────

    def _job_dir(self, job_id: str) -> Path:
        if not job_id or any(c not in "0123456789abcdefghijklmnopqrstuvwxyz-" for c in job_id):
            raise TrainingError("entrenamiento_no_encontrado", "Entrenamiento no encontrado.", 404)
        return self.jobs_dir / job_id

    def _read(self, job_id: str) -> dict | None:
        try:
            return json.loads((self._job_dir(job_id) / "estado.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, job: dict) -> None:
        folder = self._job_dir(job["id"])
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / "estado.tmp"
        temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(folder / "estado.json")

    def _output(self, job: dict) -> Path:
        return self.output_dir / job["tipo"] / job["version"]

    def _alive(self, job: dict) -> bool:
        process = self._processes.get(job["id"])
        if process is not None:
            if process.poll() is None:
                return True
            self._processes.pop(job["id"], None)  # recoge el proceso (sin zombis)
            return False
        return _pid_running(job.get("pid"), job["version"])

    def status(self, job: dict, log_lines: int = 0) -> dict:
        folder = self._job_dir(job["id"])
        log = folder / "registro.log"
        text = _tail(log)
        info = parse_log(text)
        output = self._output(job)
        contract = output / "contrato.json"
        alive = self._alive(job)  # también recoge el proceso si ya terminó
        if contract.is_file():
            state, end = "completado", _iso_mtime(contract)
        elif job.get("cancelado"):  # aunque el proceso tarde unos segundos en salir
            state, end = "cancelado", job.get("fin") or _iso_mtime(log)
        elif alive:
            state, end = "en_curso", None
        else:
            state, end = "fallido", job.get("fin") or _iso_mtime(log)
        progress = 1.0 if state == "completado" else overall_progress(info)
        lines = [line for line in text.splitlines() if line.strip()]
        error = None
        if state == "fallido":
            error = next((line for line in reversed(lines)
                          if not line.startswith("{") and ("Error" in line or "error" in line)),
                         lines[-1] if lines else "El proceso terminó sin dejar registro.")
        metrics = None
        if state == "completado" and (output / "metricas.json").is_file():
            try:
                metrics = json.loads((output / "metricas.json").read_text(encoding="utf-8"))
            except ValueError:
                metrics = None
        return {
            **{key: job.get(key) for key in (
                "id", "tipo", "fuente", "receta", "epocas", "semilla", "dispositivo", "version",
                "inicio", "por", "datos")},
            "pliegues": bool(job.get("pliegues")),
            "salida": _relative(output),
            "estado": state,
            "fase": "terminado" if state == "completado" else info["fase"],
            "progreso": progress,
            "epoca": info["epoca"],
            "epocas_corrida": info["epocas"],
            "lote": info["lote"],
            "lotes": info["lotes"],
            "corrida": info["corrida"],
            "corridas": info["corridas"],
            "corrida_nombre": info["nombre"],
            "perdidas": info["perdidas"],
            "fin": end,
            "error": error,
            "metricas": metrics,
            "registro": lines[-log_lines:] if log_lines else [],
        }

    def jobs(self) -> list[dict]:
        if not self.jobs_dir.is_dir():
            return []
        found = []
        for folder in sorted(self.jobs_dir.iterdir(), reverse=True):
            if folder.is_dir() and not folder.name.startswith("."):
                job = self._read(folder.name)
                if job:
                    found.append(job)
        return found

    def overview(self, limit: int = 30) -> dict:
        items = [self.status(job) for job in self.jobs()[:limit]]
        active = next((item for item in items if item["estado"] == "en_curso"), None)
        return {"activo": active, "entrenamientos": items}

    def get(self, job_id: str, log_lines: int = 60) -> dict:
        job = self._read(job_id)
        if job is None:
            raise TrainingError("entrenamiento_no_encontrado", "Entrenamiento no encontrado.", 404)
        return self.status(job, log_lines)

    def active(self) -> dict | None:
        return next((job for job in self.jobs() if self._alive(job)), None)

    # ── Lanzar y cancelar ───────────────────────────────────────────

    def command(self, job: dict, conjunto: Path, cache: Path | None) -> list[str]:
        command = [
            self.python, "-u", str(SCRIPTS[job["tipo"]]), "reentrenar",
            "--receta", str(ROOT / job["receta"]["ruta"]),
            "--conjunto", str(conjunto),
            "--salida", str(self._output(job)),
            "--version", job["version"],
            "--epocas", str(job["epocas"]),
            "--semilla", str(job["semilla"]),
            "--dispositivo", job["dispositivo"],
            "--progreso",
        ]
        if job["tipo"] == "bilstm" and cache is not None:
            command += ["--cache", str(cache)]
        if job.get("pliegues"):
            command.append("--pliegues")
        return command

    def environment(self, tipo: str) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        env.update(PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
        if tipo == "mbert":  # transformers vive en backend/.deps, como para la API
            env["PYTHONPATH"] = str(DEPS)
        return env

    def _popen(self, command: list[str], log: Path, env: dict[str, str]) -> subprocess.Popen:
        with log.open("ab") as stream:
            return subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)

    def start(self, tipo: str, source: dict, recipe: Recipe, epochs: int | None, seed: int,
              actor: str | None, panel_loader: Callable[[str], tuple[dict, dict[str, bytes]]] | None = None,
              device: str | None = None, folds: bool = False) -> dict:
        """Prepara el conjunto y lanza el entrenamiento. `panel_loader(version_id)` devuelve la
        versión del panel (dict) y sus CSV del estándar. `device`: «cuda» (GPU), «cpu» o None
        (la GPU si hay CUDA; si no, el procesador)."""
        if tipo not in SCRIPTS:
            raise TrainingError("tipo_desconocido", "Tipo de modelo desconocido.", 422)
        if device not in (None, "cuda", "cpu"):
            raise TrainingError("dispositivo_desconocido", "Elige GPU o procesador.", 422)
        cuda = self.cuda_available()
        if device == "cuda" and not cuda:
            raise TrainingError("sin_gpu", "No hay GPU con CUDA disponible: entrena con el procesador.", 422)
        device = device or ("cuda" if cuda else "cpu")
        with self._lock:
            running = self.active()
            if running is not None:
                raise TrainingError("entrenamiento_en_curso",
                                    "Ya hay un entrenamiento en curso: espera a que termine o cancélalo.",
                                    409)
            stamp = datetime.now(timezone.utc)
            job_id = f"{stamp:%Y%m%d-%H%M%S-%f}-{secrets.token_hex(2)}"
            folder = self._job_dir(job_id)
            folder.mkdir(parents=True)
            try:
                job = self._prepare(job_id, folder, tipo, source, recipe, epochs, seed, actor, stamp,
                                    panel_loader, device, folds)
            except BaseException:
                shutil.rmtree(folder, ignore_errors=True)
                raise
            conjunto = Path(job.pop("_conjunto"))
            cache = job.pop("_cache")
            command = self.command(job, conjunto, cache)
            job["comando"] = [_relative(Path(part)) if os.sep in part and Path(part).is_absolute()
                              else part for part in command]
            self._write(job)
            log = folder / "registro.log"
            log.write_text(f"$ {' '.join(command)}\n", encoding="utf-8")
            try:
                process = self.launcher(command, log, self.environment(tipo))
            except OSError as error:
                job["fin"] = _now()
                self._write(job)
                raise TrainingError("no_se_pudo_lanzar", f"No se pudo lanzar el entrenamiento: {error}",
                                    500) from error
            job["pid"] = process.pid
            self._processes[job_id] = process
            self._write(job)
            logger.info("Entrenamiento %s lanzado (%s, pid %s)", job_id, tipo, process.pid)
            return self.status(job)

    def _prepare(self, job_id, folder, tipo, source, recipe, epochs, seed, actor, stamp, panel_loader,
                 device, folds):
        configuration = str(recipe.data["configuracion"])
        epochs = int(epochs or recipe.data.get("epocas_fijas") or 0)
        if epochs < 1:
            raise TrainingError("sin_epocas", "La receta no fija las épocas: indícalas.", 422)
        token = job_id.rsplit("-", 1)[-1]
        if source.get("tipo") == "comun_v1":
            info = self.comun_source()
            if info is None:
                raise TrainingError("sin_comun_v1", "No está datasets/comun_v1 en este equipo.", 409)
            conjunto, cache = self.comun_dir, FASTTEXT_CACHE
            prefix = info["version"] or "comun_v1"
            fuente = {"tipo": "comun_v1", "nombre": info["nombre"], "version": info["version"]}
            datos = {"entrenamiento": info["fragmentos"], "prueba": 0, "brazos": info["brazos"]}
        elif source.get("tipo") == "panel":
            if panel_loader is None:
                raise TrainingError("sin_panel", "Las versiones del panel no están disponibles.", 503)
            version, files = panel_loader(str(source.get("version_id")))
            conjunto, cache = folder / "conjunto", folder / "cache_fasttext.npz"
            datos = write_panel_set(conjunto, files, version)
            datos["brazos"] = []
            if folds and not datos["plegable"]:
                raise TrainingError(
                    "muy_pequena_para_calibrar",
                    "La versión es demasiado pequeña para preparar la calibración: hacen falta al menos "
                    "3 grupos de noticias falsas y 3 de reales.", 422)
            prefix = f"panel-{_slug(version.get('nombre') or 'dataset')}"
            fuente = {"tipo": "panel", "nombre": version.get("nombre"), "version_id": str(version.get("id"))}
        elif source.get("tipo") == "conjunto":
            from backend.services.combined_sets import CombinedSetError

            try:
                info = self.sets.get(str(source.get("version") or ""))
                conjunto = self.sets.path(info["version"])
            except CombinedSetError as error:
                raise TrainingError(error.code, str(error), error.status_code) from error
            summary = info.get("resumen") or {}
            if folds and not summary.get("plegable", True):
                raise TrainingError(
                    "muy_pequena_para_calibrar",
                    "El conjunto es demasiado pequeño para preparar la calibración: hacen falta al menos "
                    "3 grupos de noticias falsas y 3 de reales.", 422)
            # Caché fastText propia: la de comun_v1 no tiene las palabras del panel.
            cache = folder / "cache_fasttext.npz"
            total, test = summary.get("total_entrenamiento") or {}, summary.get("prueba") or {}
            datos = {"entrenamiento": total.get("fragmentos"), "prueba": test.get("fragmentos") or 0,
                     "reales": total.get("reales"), "falsas": total.get("falsas"),
                     "panel": (summary.get("panel_despues") or {}).get("fragmentos"),
                     "balanceo": summary.get("balanceo"), "incluye_comun": info["incluye_comun"]}
            prefix = f"conjunto-{_slug(info.get('nombre') or info['version'])}"
            fuente = {"tipo": "conjunto", "nombre": info.get("nombre"), "version": info["version"]}
        else:
            raise TrainingError("fuente_desconocida", "Elige comun_v1, una versión del panel o un conjunto.", 422)
        version_name = f"{prefix}_{configuration}_{stamp:%Y%m%d}_{token}"
        job = {
            "id": job_id, "tipo": tipo, "fuente": fuente,
            "receta": recipe.summary(),
            "epocas": epochs, "semilla": int(seed),
            "dispositivo": device,
            "pliegues": bool(folds),
            "version": version_name,
            "inicio": stamp.isoformat(), "por": actor, "cancelado": False, "pid": None, "fin": None,
            "datos": datos,
            "_conjunto": str(conjunto), "_cache": str(cache) if cache else None,
        }
        if self._output(job).exists() or (self._output(job).parent / f".{version_name}.parcial").exists():
            raise TrainingError("version_repetida", "Ya existe un modelo con esa versión.", 409)
        return job

    def cancel(self, job_id: str) -> dict:
        job = self._read(job_id)
        if job is None:
            raise TrainingError("entrenamiento_no_encontrado", "Entrenamiento no encontrado.", 404)
        if not self._alive(job):
            raise TrainingError("no_en_curso", "Ese entrenamiento ya no está en curso.", 409)
        job["cancelado"] = True
        job["fin"] = _now()
        self._write(job)
        pid = job.get("pid")
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, TypeError):
            pass
        threading.Thread(target=self._finish_cancel, args=(job,), daemon=True).start()
        return self.status(job)

    def _finish_cancel(self, job: dict) -> None:
        """Si el proceso no sale solo, se fuerza; después se borra su carpeta parcial (nunca un
        modelo terminado: si llegó a terminar, su contrato existe y la carpeta queda)."""
        deadline = time.monotonic() + CANCEL_GRACE_SECONDS
        while time.monotonic() < deadline and self._alive(job):
            time.sleep(0.5)
        if self._alive(job):
            try:
                os.killpg(os.getpgid(job["pid"]), signal.SIGKILL)
            except (OSError, TypeError):
                pass
            time.sleep(0.5)
            self._alive(job)
        partial = self._output(job).parent / f".{job['version']}.parcial"
        if partial.is_dir():
            shutil.rmtree(partial, ignore_errors=True)
