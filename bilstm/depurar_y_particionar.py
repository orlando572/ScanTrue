"""Depura noticias binarias y crea particiones nuevas sin textos relacionados cruzados.

Uso: bilstm/.venv/bin/python bilstm/depurar_y_particionar.py
No modifica el corpus unificado original ni entrena modelos.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from unificar_todos import ROOT, SCHEMA, fingerprint, write_csv


SOURCE = ROOT / "datasets/unificado_total/noticias_binarias.csv"
OUTPUT = ROOT / "datasets/unificado_total/depurado"
RESERVED_SOURCES = {"fakedes_iberlef_2021", "falledesinfo_es"}
EXTRA_COLUMNS = ("particion_nueva", "grupo_particion")


def quality_reason(row: dict) -> str:
    text = row["texto"].strip()
    if not text or row["etiqueta_binaria"] not in ("0", "1"):
        return "texto_o_etiqueta_invalida"
    if len(text.split()) < 5:
        return "menos_de_cinco_palabras"
    if "proyecto de laligaproyecto de laliga" in text.casefold():
        return "texto_repetido_de_pagina"
    if (text.casefold().startswith("discurso íntegro de ") and
            text.casefold().endswith("estimados conciudadanos y conciudadanas,")):
        return "discurso_incompleto"
    if row["dataset_principal"] == "spanish_fake_and_real_news_acosta":
        return "acosta_fuente_con_satira_en_clase_fake"
    if "el mundo today" in text.casefold():
        return "satira_explicita"
    return ""


class UnionFind:
    def __init__(self, count: int):
        self.parent = list(range(count))
        self.rank = [0] * count

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left == right:
            return
        if self.rank[left] < self.rank[right]:
            left, right = right, left
        self.parent[right] = left
        if self.rank[left] == self.rank[right]:
            self.rank[left] += 1


def related_keys(row: dict) -> list[str]:
    """Vincula copias con titular diferente, cuerpo igual o titular repetido."""
    text, title = row["texto"], row["titulo"].strip()
    keys = ["texto:" + fingerprint(text)]
    if title and len(title.split()) >= 6:
        keys.append("titular:" + fingerprint(title))
    if title and text.casefold().startswith(title.casefold()):
        body = text[len(title):].strip()
        if len(body) >= 100:
            keys.append("cuerpo:" + fingerprint(body))
    if row["url"]:
        keys.append("url:" + row["url"].strip().casefold().rstrip("/"))
    return keys


def group_related(rows: list[dict]) -> tuple[list[str], dict]:
    union = UnionFind(len(rows))
    first_seen = {}
    key_counts = Counter()
    for index, row in enumerate(rows):
        for key in related_keys(row):
            key_counts[key.split(":", 1)[0]] += 1
            previous = first_seen.setdefault(key, index)
            if previous != index:
                union.union(previous, index)
    groups = defaultdict(list)
    for index in range(len(rows)):
        groups[union.find(index)].append(index)
    identifiers = [""] * len(rows)
    for members in groups.values():
        group_id = hashlib.sha256("|".join(sorted(rows[i]["id"] for i in members))
                                  .encode("utf-8")).hexdigest()
        for index in members:
            identifiers[index] = group_id
    return identifiers, {"grupos": len(groups),
                         "grupos_con_varias_filas": sum(len(g) > 1 for g in groups.values()),
                         "filas_en_grupos_multiples": sum(len(g) for g in groups.values() if len(g) > 1),
                         "claves_calculadas": dict(key_counts),
                         "grupo_maximo": max(map(len, groups.values()), default=0)}


def new_partitions(rows: list[dict], group_ids: list[str]) -> list[str]:
    reserved_groups = {group_ids[i] for i, row in enumerate(rows)
                       if RESERVED_SOURCES.intersection(json.loads(row["datasets_origen"]))}
    assigned = ["prueba_fuentes_reservadas" if group in reserved_groups else ""
                for group in group_ids]
    eligible = [i for i, value in enumerate(assigned) if not value]
    labels = np.array([int(rows[i]["etiqueta_binaria"]) for i in eligible])
    groups = np.array([group_ids[i] for i in eligible])
    if len(set(groups)) < 10 or len(set(labels)) != 2:
        raise ValueError("No hay suficientes grupos y ambas etiquetas para dividir")
    splitter = StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=42)
    fold_indices = [test for _, test in splitter.split(np.zeros(len(eligible)), labels, groups)]
    fraction = float(labels.mean())
    target = len(eligible) / 10
    ranked = sorted(range(10), key=lambda fold: (
        abs(len(fold_indices[fold]) - target) / target +
        abs(float(labels[fold_indices[fold]].mean()) - fraction), fold))
    test_fold, validation_fold = ranked[:2]
    for fold, indices in enumerate(fold_indices):
        name = "prueba_interna" if fold == test_fold else (
            "validacion" if fold == validation_fold else "entrenamiento")
        for relative in indices:
            assigned[eligible[int(relative)]] = name
    if len(set(assigned)) != 4:
        raise AssertionError("Falta una partición")
    by_group = defaultdict(set)
    for group, split in zip(group_ids, assigned):
        by_group[group].add(split)
    if any(len(splits) != 1 for splits in by_group.values()):
        raise AssertionError("Un grupo relacionado cruzó particiones")
    return assigned


def build(source: Path, output: Path) -> dict:
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = set(SCHEMA)
    if not rows or not expected.issubset(rows[0]):
        raise ValueError("El archivo de entrada no tiene el esquema esperado")
    kept, excluded = [], []
    for row in rows:
        reason = quality_reason(row)
        if reason:
            excluded.append({**row, "motivo_exclusion": reason})
        else:
            kept.append(row)
    if len({row["huella_texto"] for row in kept}) != len(kept):
        raise AssertionError("Persisten textos duplicados")
    group_ids, grouping = group_related(kept)
    assigned = new_partitions(kept, group_ids)
    for row, group_id, split in zip(kept, group_ids, assigned):
        row.update(particion_nueva=split, grupo_particion=group_id)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "noticias_depuradas.csv", kept, SCHEMA + EXTRA_COLUMNS)
    for split in ("entrenamiento", "validacion", "prueba_interna", "prueba_fuentes_reservadas"):
        write_csv(output / f"{split}.csv", [r for r in kept if r["particion_nueva"] == split],
                  SCHEMA + EXTRA_COLUMNS)
    write_csv(output / "excluidos.csv", excluded, SCHEMA + ("motivo_exclusion",))
    counts = Counter(row["particion_nueva"] for row in kept)
    by_split_label = {split: dict(Counter(r["etiqueta_binaria"] for r in kept
                                        if r["particion_nueva"] == split)) for split in counts}
    by_split_source = {split: dict(Counter(r["dataset_principal"] for r in kept
                                         if r["particion_nueva"] == split)) for split in counts}
    report = {
        "entrada": len(rows), "conservadas": len(kept), "excluidas": len(excluded),
        "motivos_exclusion": dict(Counter(r["motivo_exclusion"] for r in excluded)),
        "particiones": dict(counts), "etiquetas_por_particion": by_split_label,
        "fuentes_por_particion": by_split_source, "agrupacion": grouping,
        "fuentes_reservadas": sorted(RESERVED_SOURCES),
        "semilla": 42,
        "advertencias": [
            "La limpieza es conservadora; puede quedar sátira o contenido defectuoso sin marcador explícito.",
            "La prueba de fuentes reservadas queda fuera de este entrenamiento, pero no es inédita respecto a modelos anteriores.",
            "El conjunto político sigue dominando; informar métricas por fuente y revisar manualmente etiquetas.",
        ],
    }
    (output / "reporte_limpieza.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
