"""Conjuntos combinados (Administración → Datasets): comun_v1 + versiones del panel.

Un conjunto combinado suma a comun_v1 las noticias revisadas de una o varias versiones del panel,
sin cambiar nada de comun_v1:

- `fragmentos_desarrollo.csv` y los `ablacion_*.csv` se copian byte a byte (mismo SHA-256 y mismos
  pliegues F1–F3; la prueba congelada no se copia).
- Lo del panel va en `extra_panel.csv` (pliegue «panel»), que los scripts suman al entrenamiento como
  un brazo más (`datos_comunes/comun.py`, BRAZOS["panel"]): entra en el entrenamiento de F1–F3 y del
  modelo final, pero nunca en la validación. Así la validación por fuente, las predicciones fuera de
  pliegue y la calibración siguen siendo las de comun_v1.
- La prueba de las versiones va en `fragmentos_prueba.csv`: evalúa el modelo final (`metricas.json`).

Sin comun_v1, el conjunto es la unión de las versiones con el formato de una versión del panel
(`fragmentos_desarrollo.csv` repartido en F1–F3 por grupo y clase).

Balanceo (opcional, «50_50»): solo de lo añadido del panel, después de juntar y quitar duplicados,
retirando noticias enteras (grupos completos, sorteo fijo) de la clase que sobra. No se duplica nada
ni se toca la prueba. El entrenamiento ya iguala el peso total de las dos clases (pesos de clase).
"""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import logging
from pathlib import Path
import secrets
import shutil

from datos_comunes import estandar
from datos_comunes.cruces import IndiceComun
from datos_comunes.grupos import fingerprint

from backend.services.training import FOLDS, _slug, assign_folds

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SETS_DIR = ROOT / "datasets" / "conjuntos"
COMUN_V1 = ROOT / "datasets" / "comun_v1"
DEVELOPMENT = "fragmentos_desarrollo.csv"
EXTRA = "extra_panel.csv"
TEST = "fragmentos_prueba.csv"
PANEL_TRAINING = "fragmentos_entrenamiento.csv"
# Lo que se copia de comun_v1 (nunca la prueba congelada).
COMUN_FILES = (DEVELOPMENT, "ablacion_satira.csv", "ablacion_usmsc.csv", "ablacion_politica.csv")
BALANCES = ("ninguno", "50_50")
MANIFEST_VERSION = "conjunto_combinado_v1"
COLUMNS = list(estandar.COLUMNAS_BASE)


class CombinedSetError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PanelSource:
    """Una versión del panel con sus CSV del estándar (`standard_csvs`)."""
    id: str
    nombre: str
    fecha: str | None
    files: dict[str, bytes]


@dataclass
class CombinedBuild:
    training: list[dict]
    test: list[dict]
    summary: dict = field(default_factory=dict)


def _rows(data: bytes | None) -> list[dict]:
    if not data:
        return []
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def _csv(rows: list[dict], fold: str | None = None) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in sorted(rows, key=lambda r: (r["grupo"], r["id_fragmento"])):
        writer.writerow({**row, "pliegue": fold} if fold else row)
    return buffer.getvalue().encode("utf-8")


def _news(rows: list[dict]) -> dict[str, int]:
    """Noticias por clase (una noticia cuenta una vez aunque tenga varios fragmentos)."""
    labels = {row["id_articulo"]: int(row["etiqueta_falsa"]) for row in rows}
    counts = Counter(labels.values())
    return {"reales": counts.get(0, 0), "falsas": counts.get(1, 0)}


def _counts(rows: list[dict]) -> dict:
    return {**_news(rows), "fragmentos": len(rows)}


def _order(group: str) -> str:
    return sha256(group.encode("utf-8")).hexdigest()


# ── Unir ────────────────────────────────────────────────────────────


def merge_versions(sources: list[PanelSource]) -> tuple[list[dict], list[dict], dict]:
    """Une las versiones sin repetir fragmentos.

    - Por `id_fragmento`, manda la versión más reciente (por si se corrigió la etiqueta).
    - Una noticia o un grupo que esté en la prueba de alguna versión va a prueba: si no, el modelo
      se evaluaría con algo que vio al entrenar.
    """
    latest: dict[str, tuple[str, dict]] = {}
    test_articles: set[str] = set()  # en la prueba de alguna versión, aunque no sea la más reciente
    test_groups: set[str] = set()
    for source in sorted(sources, key=lambda s: (s.fecha or "", s.id)):
        for partition, name in (("entrenamiento", PANEL_TRAINING), ("prueba", TEST)):
            for row in _rows(source.files.get(name)):
                latest[row["id_fragmento"]] = (partition, row)
                if partition == "prueba":
                    test_articles.add(row["id_articulo"])
                    test_groups.add(row["grupo"])
    training, test, moved = [], [], 0
    for partition, row in latest.values():
        if partition == "prueba":
            test.append(row)
        elif row["id_articulo"] in test_articles or row["grupo"] in test_groups:
            test.append(row)
            moved += 1
        else:
            training.append(row)
    return training, test, {"fragmentos_movidos_a_prueba": moved}


def cross_with_comun(training: list[dict], comun_rows: list[dict], index: IndiceComun | None) -> tuple[list[dict], dict]:
    """Quita lo que ya está en comun_v1 y une los casi duplicados a su grupo.

    - Mismo texto que una fila de comun_v1 (su desarrollo o un brazo) → se retira.
    - Casi duplicado de una fila del desarrollo → toma su `grupo`: así nunca se entrena con ella en
      el pliegue donde valida su gemela.
    - Cruce con la prueba congelada (no debería pasar: las versiones ya lo excluyen) → se retira.
    """
    exact = {fingerprint(row["texto"]) for row in comun_rows}
    kept, stats = [], Counter()
    for row in training:
        if fingerprint(row["texto"]) in exact:
            stats["duplicado_comun"] += 1
            continue
        found = index.cruces(row["texto"]) if index is not None else []
        if any(item.congelada for item in found):
            stats["cruce_prueba_congelada"] += 1
            continue
        twins = sorted(item.grupo for item in found if item.archivo == DEVELOPMENT)
        if twins:
            row = {**row, "grupo": twins[0]}
            stats["casi_duplicado_unido"] += 1
        kept.append(row)
    return kept, {"duplicado_comun": stats["duplicado_comun"],
                  "cruce_prueba_congelada": stats["cruce_prueba_congelada"],
                  "casi_duplicado_unido": stats["casi_duplicado_unido"]}


def balance(training: list[dict]) -> tuple[list[dict], int]:
    """50/50 por noticias: retira grupos completos de la clase mayor, en un orden fijo que sale de la
    clave del grupo, mientras no deje a esa clase por debajo de la otra. Devuelve las filas que quedan
    y cuántas noticias se retiraron."""
    group_news: dict[str, set[str]] = {}
    group_labels: dict[str, list[int]] = {}
    for row in training:
        group_news.setdefault(row["grupo"], set()).add(row["id_articulo"])
        group_labels.setdefault(row["grupo"], []).append(int(row["etiqueta_falsa"]))
    group_label = {group: Counter(labels).most_common(1)[0][0] for group, labels in group_labels.items()}
    news = _news(training)
    count = {0: news["reales"], 1: news["falsas"]}
    if not count[0] or not count[1]:
        missing = "falsas" if not count[1] else "reales"
        raise CombinedSetError("una_sola_clase_para_equilibrar",
                               f"No se puede equilibrar 50/50: lo añadido del panel no tiene noticias {missing}.",
                               422)
    major = 0 if count[0] > count[1] else 1
    minor = 1 - major
    removed: set[str] = set()
    for group in sorted((g for g, label in group_label.items() if label == major), key=_order):
        size = len(group_news[group])
        if count[major] - size >= count[minor]:
            removed.add(group)
            count[major] -= size
        if count[major] == count[minor]:
            break
    kept = [row for row in training if row["grupo"] not in removed]
    return kept, sum(len(group_news[group]) for group in removed)


def build(sources: list[PanelSource], include_comun: bool, balanceo: str,
          comun_rows: list[dict] | None = None, index: IndiceComun | None = None) -> CombinedBuild:
    """Junta las versiones (y comun_v1 si se pide) y balancea lo añadido. No escribe nada."""
    if balanceo not in BALANCES:
        raise CombinedSetError("balanceo_desconocido", "Elige «ninguno» o «50_50».", 422)
    if not sources and not include_comun:
        raise CombinedSetError("sin_fuentes", "Elige comun_v1 o al menos una versión del panel.", 422)
    if not sources:
        raise CombinedSetError("sin_versiones", "Elige al menos una versión del panel para añadir a comun_v1.", 422)
    training, test, merge_stats = merge_versions(sources)
    before = _counts(training)
    cross_stats = {}
    if include_comun:
        if comun_rows is None:
            raise CombinedSetError("sin_comun_v1", "No está datasets/comun_v1 en este equipo.", 409)
        training, cross_stats = cross_with_comun(training, comun_rows, index)
    removed_news = 0
    if balanceo == "50_50" and training:
        training, removed_news = balance(training)
    if not training:
        raise CombinedSetError("sin_entrenamiento", "No queda ninguna noticia del panel para entrenar.", 422)
    after = _counts(training)
    summary = {
        "incluye_comun": include_comun,
        "balanceo": balanceo,
        "versiones": [{"id": s.id, "nombre": s.nombre, "fecha": s.fecha} for s in sources],
        "panel_antes": before,
        "panel_despues": after,
        "retiradas": {**cross_stats, "noticias_por_balanceo": removed_news},
        **merge_stats,
        "prueba": _counts(test),
    }
    if include_comun:
        development = [row for row in comun_rows if row.get("_archivo", DEVELOPMENT) == DEVELOPMENT]
        comun = _counts(development)
        summary["comun_v1"] = comun
        summary["total_entrenamiento"] = {
            "reales": comun["reales"] + after["reales"], "falsas": comun["falsas"] + after["falsas"],
            "fragmentos": comun["fragmentos"] + after["fragmentos"]}
    else:
        summary["total_entrenamiento"] = after
        labels_per_group: dict[str, list[int]] = {}
        for row in training:
            labels_per_group.setdefault(row["grupo"], []).append(int(row["etiqueta_falsa"]))
        classes = Counter(Counter(v).most_common(1)[0][0] for v in labels_per_group.values())
        summary["plegable"] = all(classes.get(c, 0) >= len(FOLDS) for c in (0, 1))
        if not (after["reales"] and after["falsas"]):
            raise CombinedSetError("una_sola_clase", "Sin comun_v1, el conjunto necesita noticias reales y falsas.", 422)
    total = summary["total_entrenamiento"]
    news = total["reales"] + total["falsas"]
    summary["proporcion_falsas"] = round(total["falsas"] / news, 4) if news else None
    return CombinedBuild(training, test, summary)


# ── Guardar y listar ────────────────────────────────────────────────


def read_comun(comun_dir: Path = COMUN_V1) -> list[dict] | None:
    """Filas de lo que se copia de comun_v1 (desarrollo y brazos), para los cruces y los conteos."""
    if not (comun_dir / DEVELOPMENT).is_file():
        return None
    csv.field_size_limit(1 << 30)
    rows = []
    for name in COMUN_FILES:
        path = comun_dir / name
        if path.is_file():
            with path.open(encoding="utf-8", newline="") as stream:
                rows.extend({**row, "_archivo": name} for row in csv.DictReader(stream))
    return rows


class CombinedSetManager:
    def __init__(self, sets_dir: Path = SETS_DIR, comun_dir: Path = COMUN_V1) -> None:
        self.sets_dir = Path(sets_dir)
        self.comun_dir = Path(comun_dir)

    def _folder(self, version: str) -> Path:
        if not version or version.startswith(".") or "/" in version or "\\" in version:
            raise CombinedSetError("conjunto_no_encontrado", "Conjunto no encontrado.", 404)
        return self.sets_dir / version

    def _manifests(self) -> list[tuple[Path, dict]]:
        if not self.sets_dir.is_dir():
            return []
        found = []
        for folder in sorted(self.sets_dir.iterdir()):
            if folder.name.startswith(".") or not (folder / "manifest.json").is_file():
                continue
            try:
                found.append((folder, json.loads((folder / "manifest.json").read_text("utf-8"))))
            except ValueError:
                logger.warning("Manifiesto no válido en %s", folder)
        return found

    def _info(self, folder: Path, manifest: dict) -> dict:
        files = manifest.get("archivos") or {}
        missing = [name for name in files if not (folder / name).is_file()]
        return {
            "version": folder.name,
            "nombre": manifest.get("nombre"),
            "descripcion": manifest.get("descripcion"),
            "fecha": manifest.get("fecha"),
            "por": manifest.get("por"),
            "incluye_comun": bool(manifest.get("comun_v1")),
            "balanceo": manifest.get("balanceo"),
            "resumen": manifest.get("conteos") or {},
            "apto": not missing and DEVELOPMENT in files,
            "motivo": f"Faltan archivos: {', '.join(missing)}" if missing else None,
        }

    def list(self) -> list[dict]:
        items = [self._info(folder, manifest) for folder, manifest in self._manifests()]
        return sorted(items, key=lambda item: item.get("fecha") or "", reverse=True)

    def get(self, version: str) -> dict:
        folder = self._folder(version)
        try:
            manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        except (OSError, ValueError) as error:
            raise CombinedSetError("conjunto_no_encontrado", "Conjunto no encontrado.", 404) from error
        return {**self._info(folder, manifest), "manifiesto": manifest}

    def path(self, version: str) -> Path:
        """Carpeta de un conjunto apto, para entrenar."""
        info = self.get(version)
        if not info["apto"]:
            raise CombinedSetError("conjunto_no_apto", info["motivo"] or "El conjunto está incompleto.", 409)
        return self._folder(version)

    def preview(self, sources: list[PanelSource], include_comun: bool, balanceo: str,
                index: IndiceComun | None) -> dict:
        comun = read_comun(self.comun_dir) if include_comun else None
        return build(sources, include_comun, balanceo, comun, index).summary

    def create(self, nombre: str, descripcion: str | None, sources: list[PanelSource], include_comun: bool,
               balanceo: str, index: IndiceComun | None, actor: str | None) -> dict:
        nombre = " ".join((nombre or "").split())
        if not nombre:
            raise CombinedSetError("sin_nombre", "Ponle un nombre al conjunto.", 422)
        if any((manifest.get("nombre") or "").casefold() == nombre.casefold() for _, manifest in self._manifests()):
            raise CombinedSetError("nombre_repetido", "Ya existe un conjunto con ese nombre.", 409)
        comun = read_comun(self.comun_dir) if include_comun else None
        result = build(sources, include_comun, balanceo, comun, index)
        stamp = datetime.now(timezone.utc)
        version = f"{_slug(nombre)}_{stamp:%Y%m%d}_{secrets.token_hex(2)}"
        final, partial = self.sets_dir / version, self.sets_dir / f".{version}.parcial"
        if final.exists():
            raise CombinedSetError("version_repetida", "Ya existe un conjunto con esa versión.", 409)
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir(parents=True)
        try:
            manifest = self._write(partial, version, nombre, descripcion, result, include_comun, stamp, actor)
            partial.rename(final)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        logger.info("Conjunto combinado %s creado (%s)", version, manifest["conteos"].get("total_entrenamiento"))
        return self.get(version)

    def _write(self, folder: Path, version: str, nombre: str, descripcion: str | None, result: CombinedBuild,
               include_comun: bool, stamp: datetime, actor: str | None) -> dict:
        files: dict[str, dict] = {}
        comun_ref = None
        pliegues = None
        if include_comun:
            comun_manifest = json.loads((self.comun_dir / "manifest.json").read_text("utf-8"))
            for name in COMUN_FILES:
                source = self.comun_dir / name
                if not source.is_file():
                    continue
                shutil.copyfile(source, folder / name)
                digest = sha256((folder / name).read_bytes()).hexdigest()
                expected = comun_manifest["archivos"][name]["sha256"]
                if digest != expected:
                    raise CombinedSetError("comun_v1_alterado",
                                           f"{name} de comun_v1 no coincide con su manifiesto.", 409)
                files[name] = dict(comun_manifest["archivos"][name])
            outputs = {EXTRA: _csv(result.training, "panel")}
            comun_ref = {"version": comun_manifest.get("version"),
                         "sha256_manifest": sha256((self.comun_dir / "manifest.json").read_bytes()).hexdigest()}
            pliegues = comun_manifest.get("pliegues")
        else:
            development, _ = assign_folds(_csv(result.training, "panel"))
            outputs = {DEVELOPMENT: development}
            pliegues = "F1–F3 por grupo y clase (sorteo fijo por la clave del grupo)"
        if result.test:
            outputs[TEST] = _csv(result.test, "prueba_panel")
        for name, data in outputs.items():
            (folder / name).write_bytes(data)
            files[name] = {"sha256": sha256(data).hexdigest(), "filas": data.count(b"\n") - 1}
        manifest = {
            "version": MANIFEST_VERSION,
            "tipo": "combinado",
            "nombre": nombre,
            "id": version,
            "descripcion": (descripcion or "").strip() or None,
            "fecha": stamp.isoformat(),
            "por": actor,
            "comun_v1": comun_ref,
            "versiones_panel": result.summary["versiones"],
            "balanceo": result.summary["balanceo"],
            "etiqueta": {"columna": "etiqueta_falsa", "real": 0, "falsa": 1},
            "columnas": COLUMNS,
            "pliegues": pliegues,
            "archivos": files,
            "conteos": result.summary,
            "notas": [
                "comun_v1 se copia sin cambios (mismo SHA-256); la prueba congelada no se copia."
                if include_comun else "Sin comun_v1: la unión de las versiones, repartida en F1–F3.",
                f"{EXTRA}: noticias del panel que solo se suman al entrenamiento (brazo «panel»)."
                if include_comun else "",
                "El balanceo 50/50 solo retira noticias enteras de lo añadido del panel; nunca de "
                "comun_v1 ni de la prueba.",
            ],
        }
        manifest["notas"] = [note for note in manifest["notas"] if note]
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
        return manifest

    def delete(self, version: str) -> None:
        folder = self._folder(version)
        if not (folder / "manifest.json").is_file():
            raise CombinedSetError("conjunto_no_encontrado", "Conjunto no encontrado.", 404)
        shutil.rmtree(folder)
