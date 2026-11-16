"""Convierte los casos revisados en una versión de dataset (incremento 3).

Reglas de calidad:
- Solo entran casos aprobados o corregidos por el administrador.
- Copias exactas (misma huella de texto): queda una; si sus etiquetas se contradicen,
  se retiran todas.
- Copias de la misma página y casos del mismo evento forman un grupo, y cada grupo va
  entero a entrenamiento o a prueba: nada relacionado cruza entre particiones.
- La partición sale de la clave del grupo, así que un grupo cae en el mismo lado en
  todas las versiones.
- Cada noticia pasa por el estándar de `datos_comunes/estandar.py` (el de comun_v1):
  limpieza, solo español, tope de 400 tokens y fragmentos de 100–200 tokens hechos de
  oraciones completas, con peso 1/n. Cada elemento de la versión es un fragmento.
"""

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from hashlib import sha256
import io
from statistics import mean, median

from backend.repositories.filters import public_url
from backend.schemas.admin import DatasetItem, DatasetSummary
from datos_comunes import estandar
from datos_comunes.grupos import UnionFind, fingerprint

FUENTE = "panel"

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


def _partition(group: str, test_fraction: float) -> str:
    bucket = int(sha256(group.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "prueba" if bucket < test_fraction else "entrenamiento"


def _stats(values: list[int]) -> dict[str, float]:
    if not values:
        return {}
    return {"min": min(values), "mediana": median(values), "media": round(mean(values), 1),
            "max": max(values)}


def build_dataset(rows: list[dict], test_fraction: float = 0.2) -> DatasetBuild:
    candidates = [item for item in (_candidate(row) for row in rows) if item]

    # 1. Copias exactas: se conserva la revisión más reciente (las filas llegan por fecha).
    by_print: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        by_print[item["huella"]].append(item)
    unique: list[dict] = []
    duplicates = conflicts = 0
    for copies in by_print.values():
        if len({item["etiqueta"] for item in copies}) > 1:
            conflicts += len(copies)
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
            continue
        patterns.update(news.patrones)
        cuts.update(set(news.recortes))
        kept.append({**item, "noticia": news})

    # 3. Grupos: misma página o mismo evento marcado por el administrador.
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

    # 4. Cada grupo completo (con todos sus fragmentos) va a una sola partición.
    items: list[DatasetItem] = []
    partition_of: dict[str, str] = {}
    for indexes in members.values():
        group = "g_" + sha256(
            "|".join(sorted(kept[index]["huella"] for index in indexes)).encode("utf-8")
        ).hexdigest()[:12]
        # La clave de reparto es la huella más pequeña: estable aunque el grupo crezca.
        partition = _partition(min(kept[index]["huella"] for index in indexes), test_fraction)
        for index in indexes:
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
                            "fragmento": fragment,
                        },
                        evidencia=item["evidencia"],
                        id_fragmento=row["id_fragmento"],
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
        recortes=dict(cuts),
        filas_cambiadas_por_patron=dict(patterns),
        grupos=len(members),
        grupos_con_varios=sum(1 for indexes in members.values() if len(indexes) > 1),
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
