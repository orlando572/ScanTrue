"""Convierte los casos revisados en una versión de dataset (incremento 3).

Reglas de calidad:
- Solo entran casos aprobados o corregidos por el administrador.
- Copias exactas (misma huella de texto): queda una; si sus etiquetas se contradicen,
  se retiran todas.
- Copias de la misma página y casos del mismo evento forman un grupo, y cada grupo va
  entero a entrenamiento o a prueba: nada relacionado cruza entre particiones.
- La partición sale de la clave del grupo, así que un grupo cae en el mismo lado en
  todas las versiones.
"""

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from hashlib import sha256
import io

from backend.repositories.filters import public_url
from backend.schemas.admin import DatasetItem, DatasetSummary
from datos_comunes.grupos import UnionFind, fingerprint

EXPORT_COLUMNS = (
    "id", "particion", "etiqueta", "texto", "grupo", "decision", "dominio", "url",
    "fecha_analisis", "p_unificada", "p_bilstm", "p_mbert", "version_bilstm",
    "version_mbert", "comparacion", "nota", "evidencia", "hash_texto",
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
    domain, url = public_url(analysis.get("url"))
    outputs = {item["modelo"]: item for item in analysis.get("resultados_modelo") or []}
    unified = analysis.get("resultado_unificado") or {}
    return {
        "analisis_id": analysis["id"],
        "texto": text,
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


def _partition(group: str, test_fraction: float) -> str:
    bucket = int(sha256(group.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "prueba" if bucket < test_fraction else "entrenamiento"


def build_dataset(rows: list[dict], test_fraction: float = 0.2) -> DatasetBuild:
    candidates = [item for item in (_candidate(row) for row in rows) if item]

    # 1. Copias exactas: se conserva la revisión más reciente (las filas llegan por fecha).
    by_print: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        by_print[item["huella"]].append(item)
    kept: list[dict] = []
    duplicates = conflicts = 0
    for copies in by_print.values():
        if len({item["etiqueta"] for item in copies}) > 1:
            conflicts += len(copies)
            continue
        duplicates += len(copies) - 1
        kept.append(copies[-1])

    # 2. Grupos: misma página o mismo evento marcado por el administrador.
    union = UnionFind(len(kept))
    seen: dict[str, int] = {}
    for index, item in enumerate(kept):
        keys = [f"texto:{item['huella']}"]
        if item["url"]:
            keys.append(f"url:{item['url'].casefold().rstrip('/')}")
        if item["evento"]:
            keys.append(f"evento:{item['evento']}")
        for key in keys:
            if key in seen:
                union.union(index, seen[key])
            else:
                seen[key] = index
    members: dict[int, list[int]] = defaultdict(list)
    for index in range(len(kept)):
        members[union.find(index)].append(index)

    # 3. Cada grupo completo va a una sola partición.
    items: list[DatasetItem] = []
    for indexes in members.values():
        group = "g_" + sha256(
            "|".join(sorted(kept[index]["huella"] for index in indexes)).encode("utf-8")
        ).hexdigest()[:12]
        # La clave de reparto es la huella más pequeña: estable aunque el grupo crezca.
        partition = _partition(min(kept[index]["huella"] for index in indexes), test_fraction)
        for index in indexes:
            item = kept[index]
            items.append(
                DatasetItem(
                    analisis_id=item["analisis_id"],
                    texto=item["texto"],
                    hash_texto=item["hash_texto"],
                    etiqueta=item["etiqueta"],
                    particion=partition,
                    grupo=group,
                    url=item["url"],
                    dominio=item["dominio"],
                    decision=item["decision"],
                    procedencia=item["procedencia"],
                    evidencia=item["evidencia"],
                )
            )
    items.sort(key=lambda item: (item.particion, item.grupo, item.hash_texto))

    by_partition_label: dict[str, dict[str, int]] = {
        "entrenamiento": {"falsa": 0, "real": 0}, "prueba": {"falsa": 0, "real": 0},
    }
    for item in items:
        by_partition_label[item.particion][item.etiqueta] += 1
    summary = DatasetSummary(
        candidatos=len(candidates),
        casos=len(items),
        duplicados_retirados=duplicates,
        conflictos_retirados=conflicts,
        grupos=len(members),
        grupos_con_varios=sum(1 for indexes in members.values() if len(indexes) > 1),
        por_etiqueta=dict(Counter(item.etiqueta for item in items)),
        por_particion=dict(Counter(item.particion for item in items)),
        por_decision=dict(Counter(item.decision for item in items)),
        por_particion_etiqueta=by_partition_label,
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
        })
    return buffer.getvalue()
