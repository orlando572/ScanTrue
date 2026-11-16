"""Convierte los casos revisados en una versión de dataset (incremento 3).

Reglas de calidad:
- Solo entran casos aprobados o corregidos por el administrador.
- Copias exactas (misma huella de texto): queda una; si sus etiquetas se contradicen,
  se retiran todas.
- Copias de la misma página, casos del mismo evento y casi duplicados (tejas de 5
  palabras, la regla de comun_v1) forman un grupo, y cada grupo va entero a entrenamiento
  o a prueba: nada relacionado cruza entre particiones.
- Cruce con comun_v1: una noticia que ya está en su prueba congelada se retira (si no,
  la evaluación final dejaría de ser limpia); una que está en su desarrollo va siempre a
  entrenamiento, para que la prueba del panel no repita lo que los modelos ya vieron.
- La prueba se elige por clase (falsa/real), ordenando los grupos por un sorteo fijo que
  sale de su clave: los mismos casos dan siempre la misma partición. La validación
  interna no se guarda: la separa `datos_comunes/comun.py` al entrenar, como en comun_v1.
- Cada noticia pasa por el estándar de `datos_comunes/estandar.py` (el de comun_v1):
  limpieza, solo español, tope de 400 tokens y fragmentos de 100–200 tokens hechos de
  oraciones completas, con peso 1/n. Cada elemento de la versión es un fragmento.
"""

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import io
import json
import logging
from pathlib import Path
import zipfile
from statistics import mean, median

from backend.repositories.filters import public_url
from backend.schemas.admin import CaseStandardPreview, DatasetItem, DatasetSummary
from datos_comunes import estandar
from datos_comunes.cruces import IndiceComun, parecidas, tejas
from datos_comunes.grupos import UnionFind, fingerprint

FUENTE = "panel"
ROOT = Path(__file__).resolve().parents[2]
COMUN_V1 = ROOT / "datasets" / "comun_v1"
ESTANDAR_VERSION = "panel_estandar_v1"
# Archivos de la exportación para entrenar, como en comun_v1: el pliegue dice de qué lado está.
STANDARD_FILES = {"entrenamiento": ("fragmentos_entrenamiento.csv", "panel"),
                  "prueba": ("fragmentos_prueba.csv", "prueba_panel")}
# Código que decide qué entra y cómo: su SHA-256 va al manifiesto de cada versión.
CODE_FILES = ("datos_comunes/estandar.py", "datos_comunes/limpieza.py",
              "datos_comunes/cruces.py", "datos_comunes/grupos.py",
              "backend/services/datasets.py")
# Noticias fuera que se listan en el resumen (el resto solo se cuenta).
MAX_LISTED = 100
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def comun_index() -> IndiceComun | None:
    """Índice de comun_v1 (se carga una vez); None si la carpeta no está."""
    try:
        return IndiceComun.cargar(COMUN_V1)
    except Exception:
        logger.exception("No se pudo leer comun_v1 para buscar cruces")
        return None

EXPORT_COLUMNS = (
    "id", "particion", "etiqueta", "texto", "grupo", "decision", "dominio", "url",
    "fecha_analisis", "p_unificada", "p_bilstm", "p_mbert", "version_bilstm",
    "version_mbert", "comparacion", "nota", "evidencia", "hash_texto",
    "id_fragmento", "peso", "tokens_bilstm",
)


@dataclass(frozen=True)
class DatasetBuild:
    items: list[DatasetItem]
    summary: DatasetSummary


def _single(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _candidate(row: dict) -> dict | None:
    """Aplana una fila de `revisiones` con su análisis; None si no sirve como ejemplo."""
    analysis = _single(row.get("analisis")) or {}
    text = (analysis.get("texto_original") or analysis.get("texto") or "").strip()
    label = row.get("etiqueta_final")
    if not text or label not in ("falsa", "real") or not analysis.get("id"):
        return None
    marked = analysis.get("fragmentos")
    parts = [str(part) for part in marked if str(part).strip()] if isinstance(marked, list) else []
    domain, url = public_url(analysis.get("url"))
    outputs = {item["modelo"]: item for item in analysis.get("resultados_modelo") or []}
    unified = analysis.get("resultado_unificado") or {}
    return {
        "analisis_id": analysis["id"],
        "texto": text,
        # Fragmentos marcados en la página: su borde cuenta como borde de oración.
        "partes": parts or [text],
        "hash_texto": sha256(text.encode("utf-8")).hexdigest(),
        "huella": fingerprint(text),
        "etiqueta": label,
        "decision": row["decision"],
        "url": url,
        "dominio": domain,
        "evento": " ".join((row.get("grupo_evento") or "").split()).casefold() or None,
        "evidencia": [str(item) for item in row.get("evidencia") or []],
        "procedencia": {
            "fecha_analisis": analysis.get("fecha"),
            "fecha_revision": row.get("fecha"),
            "comparacion": analysis.get("comparacion"),
            "p_unificada": unified.get("probabilidad_falsa"),
            "version_combinacion": unified.get("version_combinacion"),
            "modelos": {
                name: {
                    "version": output.get("version"),
                    "probabilidad_falsa": output.get("probabilidad_falsa"),
                }
                for name, output in outputs.items()
            },
            "nota": row.get("nota"),
            "grupo_evento": row.get("grupo_evento"),
        },
    }


def _bucket(key: str) -> float:
    """Sorteo fijo en [0, 1) a partir de la clave del grupo."""
    return int(sha256(key.encode("utf-8")).hexdigest()[:8], 16) / 0x100000000


def _test_groups(groups: dict[str, dict], test_fraction: float) -> set[str]:
    """Grupos de prueba: ~`test_fraction` de las noticias de cada clase.

    Como `comun.separar_interna`: se recorren los grupos de cada clase en orden de sorteo
    y entra el que no pase la meta en más de medio grupo. Si una clase tiene al menos
    1/fracción grupos y no entró ninguno (grupos grandes), entra el primero del sorteo.
    """
    strata: dict[str, list[str]] = defaultdict(list)
    for key, info in groups.items():
        if not info["forzado"]:
            strata[info["clase"]].append(key)
    chosen: set[str] = set()
    for keys in strata.values():
        keys.sort(key=lambda key: (_bucket(groups[key]["clave"]), key))
        target = test_fraction * sum(groups[key]["n"] for key in keys)
        total = 0
        for key in keys:
            size = groups[key]["n"]
            if total + size / 2 > target:
                continue
            chosen.add(key)
            total += size
        if total == 0 and keys and len(keys) * test_fraction >= 1:
            chosen.add(keys[0])
    return chosen


def _stats(values: list[int]) -> dict[str, float]:
    if not values:
        return {}
    return {"min": min(values), "mediana": median(values), "media": round(mean(values), 1),
            "max": max(values)}


def build_dataset(
    rows: list[dict], test_fraction: float = 0.2, comun: IndiceComun | None = None,
) -> DatasetBuild:
    """`comun`: índice de comun_v1 para los cruces (None = no se comprueban)."""
    candidates = [item for item in (_candidate(row) for row in rows) if item]

    # 1. Copias exactas: se conserva la revisión más reciente (las filas llegan por fecha).
    by_print: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        by_print[item["huella"]].append(item)
    unique: list[dict] = []
    dropped: list[tuple[str, str]] = []  # (análisis, motivo) de lo que queda fuera
    duplicates = conflicts = 0
    for copies in by_print.values():
        if len({item["etiqueta"] for item in copies}) > 1:
            conflicts += len(copies)
            dropped.extend((item["analisis_id"], "conflicto_etiquetas") for item in copies)
            continue
        duplicates += len(copies) - 1
        unique.append(copies[-1])

    # 2. Estándar de fila: limpieza, idioma, tope por noticia y fragmentos de oraciones completas.
    excluded: Counter = Counter()
    cuts: Counter = Counter()
    patterns: Counter = Counter()
    kept: list[dict] = []
    for item in unique:
        news = estandar.preparar_noticia(item["partes"])
        if news.motivo:
            excluded[news.motivo] += 1
            dropped.append((item["analisis_id"], news.motivo))
            continue
        patterns.update(news.patrones)
        cuts.update(set(news.recortes))
        kept.append({**item, "noticia": news})

    # 3. Cruces con comun_v1: fuera lo que está en su prueba congelada.
    in_development = 0
    if comun is not None:
        still: list[dict] = []
        for item in kept:
            found = comun.cruces(item["texto"])
            if any(cruce.congelada for cruce in found):
                excluded["cruce_prueba_congelada"] += 1
                dropped.append((item["analisis_id"], "cruce_prueba_congelada"))
                continue
            item["comun"] = sorted({cruce.grupo for cruce in found})
            in_development += bool(found)
            still.append(item)
        kept = still

    # 4. Grupos: misma página, mismo evento, casi duplicados o mismo grupo de comun_v1.
    union = UnionFind(len(kept))
    seen: dict[str, int] = {}
    shingles = [tejas(item["texto"]) for item in kept]
    near_pairs = 0
    by_shingle: dict[int, list[int]] = defaultdict(list)
    for index, item in enumerate(kept):
        keys = [f"texto:{item['huella']}"]
        if item["url"]:
            keys.append(f"url:{item['url'].casefold().rstrip('/')}")
        if item["evento"]:
            keys.append(f"evento:{item['evento']}")
        keys.extend(f"comun:{group}" for group in item.get("comun") or [])
        for key in keys:
            if key in seen:
                union.union(index, seen[key])
            else:
                seen[key] = index
        others = {other for shingle in shingles[index] for other in by_shingle[shingle]}
        for other in sorted(others):
            if parecidas(shingles[index], shingles[other]):
                if union.find(index) != union.find(other):
                    near_pairs += 1
                union.union(index, other)
        for shingle in shingles[index]:
            by_shingle[shingle].append(index)
    members: dict[int, list[int]] = defaultdict(list)
    for index in range(len(kept)):
        members[union.find(index)].append(index)

    groups: dict[str, dict] = {}
    for indexes in members.values():
        key = "g_" + sha256(
            "|".join(sorted(kept[index]["huella"] for index in indexes)).encode("utf-8")
        ).hexdigest()[:12]
        groups[key] = {
            "indices": indexes,
            # La clave del sorteo es la huella más pequeña: estable aunque el grupo crezca.
            "clave": min(kept[index]["huella"] for index in indexes),
            "clase": Counter(kept[index]["etiqueta"] for index in indexes).most_common(1)[0][0],
            "n": len(indexes),
            "forzado": any(kept[index].get("comun") for index in indexes),
        }
    test = _test_groups(groups, test_fraction)

    # 5. Cada grupo completo (con todos sus fragmentos) va a una sola partición.
    items: list[DatasetItem] = []
    partition_of: dict[str, str] = {}
    for group, info in groups.items():
        partition = "prueba" if group in test else "entrenamiento"
        for index in info["indices"]:
            item = kept[index]
            news = item["noticia"]
            partition_of[item["analisis_id"]] = partition
            rows_std = estandar.filas_estandar(
                news, id_articulo=item["analisis_id"], grupo=group, fuente=FUENTE,
                dominio=item["dominio"] or "", etiqueta_falsa=int(item["etiqueta"] == "falsa"),
                pliegue=FUENTE,
            )
            for row in rows_std:
                fragment = {
                    "id_fragmento": row["id_fragmento"],
                    "peso": row["peso"],
                    "tokens_bilstm": row["tokens_bilstm"],
                    "fragmentos_noticia": len(rows_std),
                    "tokens_noticia": news.tokens,
                }
                items.append(
                    DatasetItem(
                        analisis_id=item["analisis_id"],
                        texto=row["texto"],
                        hash_texto=sha256(row["texto"].encode("utf-8")).hexdigest(),
                        etiqueta=item["etiqueta"],
                        particion=partition,
                        grupo=group,
                        url=item["url"],
                        dominio=item["dominio"],
                        decision=item["decision"],
                        # Hasta la migración 008, los datos del fragmento viajan en la procedencia.
                        procedencia={
                            **item["procedencia"],
                            "fuente": FUENTE,
                            "hash_noticia": item["hash_texto"],
                            "recortes": news.recortes,
                            "grupos_comun_v1": item.get("comun") or [],
                            "fragmento": fragment,
                        },
                        evidencia=item["evidencia"],
                        id_fragmento=row["id_fragmento"],
                        fuente=FUENTE,
                        peso=row["peso"],
                        tokens_bilstm=row["tokens_bilstm"],
                    )
                )
    items.sort(key=lambda item: (item.particion, item.grupo, item.id_fragmento or ""))

    # Recuentos por noticia (casos) y por fragmento.
    by_partition_label: dict[str, dict[str, int]] = {
        "entrenamiento": {"falsa": 0, "real": 0}, "prueba": {"falsa": 0, "real": 0},
    }
    for item in kept:
        by_partition_label[partition_of[item["analisis_id"]]][item["etiqueta"]] += 1
    summary = DatasetSummary(
        candidatos=len(candidates),
        casos=len(kept),
        fragmentos=len(items),
        duplicados_retirados=duplicates,
        conflictos_retirados=conflicts,
        excluidas=dict(excluded),
        excluidas_casos=[
            {"analisis_id": case, "motivo": reason} for case, reason in dropped[:MAX_LISTED]
        ],
        recortes=dict(cuts),
        filas_cambiadas_por_patron=dict(patterns),
        grupos=len(groups),
        grupos_con_varios=sum(1 for info in groups.values() if info["n"] > 1),
        uniones_casi_duplicado=near_pairs,
        cruces_comun={
            "comprobado": comun is not None,
            "fragmentos_indice": len(comun) if comun is not None else 0,
            "retirados_prueba_congelada": excluded.get("cruce_prueba_congelada", 0),
            "en_desarrollo_a_entrenamiento": in_development,
        },
        por_etiqueta=dict(Counter(item["etiqueta"] for item in kept)),
        por_particion=dict(Counter(partition_of.values())),
        por_decision=dict(Counter(item["decision"] for item in kept)),
        por_particion_etiqueta=by_partition_label,
        fragmentos_por_particion=dict(Counter(item.particion for item in items)),
        fragmentos_por_noticia=dict(sorted(Counter(
            len(item["noticia"].fragmentos) for item in kept).items())),
        tokens_noticia=_stats([item["noticia"].tokens for item in kept]),
        tokens_fragmento=_stats([item.tokens_bilstm for item in items]),
        estandar={
            "fuente": FUENTE,
            "tope_noticia": estandar.TOPE_NOTICIA,
            "min_tokens": estandar.MIN_TOKENS,
            "max_tokens_fragmento": estandar.MAX_TOKENS_FRAGMENTO,
            "columnas": list(estandar.COLUMNAS_BASE),
        },
        fraccion_prueba=test_fraction,
    )
    return DatasetBuild(items=items, summary=summary)


def export_csv(items: list[DatasetItem]) -> str:
    """CSV de una versión: una fila por caso, con su procedencia aplanada."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for item in items:
        origin = item.procedencia or {}
        models = origin.get("modelos") or {}
        writer.writerow({
            "id": item.analisis_id or "",
            "particion": item.particion,
            "etiqueta": item.etiqueta,
            "texto": item.texto,
            "grupo": item.grupo,
            "decision": item.decision,
            "dominio": item.dominio or "",
            "url": item.url or "",
            "fecha_analisis": origin.get("fecha_analisis") or "",
            "p_unificada": origin.get("p_unificada", ""),
            "p_bilstm": (models.get("bilstm") or {}).get("probabilidad_falsa", ""),
            "p_mbert": (models.get("mbert") or {}).get("probabilidad_falsa", ""),
            "version_bilstm": (models.get("bilstm") or {}).get("version", ""),
            "version_mbert": (models.get("mbert") or {}).get("version", ""),
            "comparacion": origin.get("comparacion") or "",
            "nota": origin.get("nota") or "",
            "evidencia": " | ".join(str(value) for value in item.evidencia),
            "hash_texto": item.hash_texto,
            "id_fragmento": item.id_fragmento or "",
            "peso": "" if item.peso is None else f"{item.peso:.6f}",
            "tokens_bilstm": "" if item.tokens_bilstm is None else item.tokens_bilstm,
        })
    return buffer.getvalue()


# ── Vista previa de un caso al revisarlo ────────────────────────────


def preview_case(text: str, parts: list[str], comun: IndiceComun | None) -> CaseStandardPreview:
    """Cómo entraría un caso al dataset si se aprueba: mismo estándar y cruces que una versión."""
    news = estandar.preparar_noticia(parts or [text])
    cross = None
    if comun is not None and not news.motivo:
        found = comun.cruces(text)
        if any(item.congelada for item in found):
            cross = "congelada"
        elif found:
            cross = "desarrollo"
    reason = news.motivo or ("cruce_prueba_congelada" if cross == "congelada" else None)
    return CaseStandardPreview(
        entra=reason is None,
        motivo=reason,
        fragmentos=[estandar.contar_tokens(fragment) for fragment in news.fragmentos]
        if reason is None else [],
        tokens=news.tokens if reason is None else 0,
        tokens_limpios=news.tokens_limpios,
        recortes=news.recortes,
        cruce_comun=cross,
        comprobado_comun=comun is not None,
    )


# ── Formato estándar (el de comun_v1) y manifiesto ──────────────────


class LegacyVersionError(ValueError):
    """La versión se creó antes del estándar (una fila por noticia, sin fragmentos)."""


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def standard_csvs(items: list[DatasetItem]) -> dict[str, bytes]:
    """Un CSV por partición con las columnas de comun_v1 (`datos_comunes/comun.py` los lee)."""
    if any(item.id_fragmento is None or item.peso is None or item.tokens_bilstm is None
           for item in items):
        raise LegacyVersionError("La versión es anterior al estándar de fragmentos.")
    ordered = sorted(items, key=lambda item: (item.particion, item.grupo, item.id_fragmento))
    files = {}
    for partition, (name, fold) in STANDARD_FILES.items():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=estandar.COLUMNAS_BASE, lineterminator="\n")
        writer.writeheader()
        for item in ordered:
            if item.particion != partition:
                continue
            writer.writerow({
                "id_fragmento": item.id_fragmento,
                "id_articulo": str(item.analisis_id or item.id_fragmento.split("#")[0]),
                "grupo": item.grupo,
                "fuente": item.fuente or FUENTE,
                "dominio": item.dominio or "",
                "texto": item.texto,
                "etiqueta_falsa": int(item.etiqueta == "falsa"),
                "peso": f"{item.peso:.6f}",
                "tokens_bilstm": item.tokens_bilstm,
                "pliegue": fold,
            })
        files[name] = buffer.getvalue().encode("utf-8")
    return files


def _file_hash(relative: str) -> str | None:
    path = ROOT / relative
    return _sha256_bytes(path.read_bytes()) if path.is_file() else None


def _comun_reference() -> dict | None:
    path = COMUN_V1 / "manifest.json"
    if not path.is_file():
        return None
    try:
        version = json.loads(path.read_text("utf-8")).get("version")
    except ValueError:
        version = None
    return {"version": version, "sha256_manifest": _sha256_bytes(path.read_bytes())}


def build_manifest(build: DatasetBuild) -> dict:
    """Manifiesto al estilo de comun_v1: archivos con SHA-256 y filas, reglas y código."""
    files = standard_csvs(build.items)
    summary = build.summary
    return {
        "version": ESTANDAR_VERSION,
        "etiqueta": {"columna": "etiqueta_falsa", "real": 0, "falsa": 1},
        "columnas": list(estandar.COLUMNAS_BASE),
        "pliegues": {fold: partition for partition, (_, fold) in STANDARD_FILES.items()},
        "archivos": {
            name: {"sha256": _sha256_bytes(data), "filas": data.count(b"\n") - 1}
            for name, data in files.items()
        },
        "parametros": {**summary.estandar, "fraccion_prueba": summary.fraccion_prueba,
                       "regla_casi_duplicado": "tejas de 5 palabras, >= 5 y >= 65 %"},
        "codigo": {relative: _file_hash(relative) for relative in CODE_FILES},
        "comun_v1": _comun_reference() if summary.cruces_comun.get("comprobado") else None,
        "conteos": {
            "noticias": summary.casos, "fragmentos": summary.fragmentos,
            "por_particion_etiqueta": summary.por_particion_etiqueta,
            "fragmentos_por_particion": summary.fragmentos_por_particion,
            "excluidas": summary.excluidas, "cruces_comun": summary.cruces_comun,
        },
        "notas": [
            "Validación interna: la separa datos_comunes/comun.py al entrenar (10 % de los "
            "grupos de entrenamiento), como en comun_v1.",
            "fragmentos_prueba.csv no comparte grupos con fragmentos_entrenamiento.csv ni "
            "con la prueba congelada de comun_v1.",
        ],
    }


def export_standard_zip(version: dict, items: list[DatasetItem]) -> bytes:
    """ZIP para entrenar: los CSV del estándar, la procedencia completa y manifest.json.

    Los CSV se regeneran desde la base; si su SHA-256 no coincide con el manifiesto guardado
    al crear la versión, el manifiesto exportado lo dice en `verificacion`.
    """
    files = standard_csvs(items)
    manifest = dict(version.get("manifiesto") or {})
    stored = manifest.get("archivos") or {}
    manifest["verificacion"] = {
        name: ("ok" if stored.get(name, {}).get("sha256") == _sha256_bytes(data)
               else "no_coincide" if name in stored else "sin_manifiesto")
        for name, data in files.items()
    }
    manifest["nombre"] = version.get("nombre")
    manifest["id"] = str(version.get("id"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("procedencia.csv", export_csv(items))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return buffer.getvalue()
