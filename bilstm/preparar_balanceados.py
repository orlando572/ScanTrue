"""Prepara dos experimentos nuevos con fuentes equilibradas y sin duplicar filas.

Uso: bilstm/.venv/bin/python bilstm/preparar_balanceados.py
No modifica los conjuntos ni checkpoints anteriores.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from entrenar_baseline import tokenize
from unificar_todos import fingerprint


ROOT = Path(__file__).resolve().parents[1]
DIRECT = ROOT / "datasets/unificado_total/depurado"
EXPANDED = ROOT / "datasets/unificado_total/binarios_ampliados.csv"
OUTPUT = ROOT / "datasets/experimentos_balanceados"
SEED = 42
COLUMNS = ("texto", "etiqueta", "dataset", "grupo_duplicados", "id", "titulo",
           "url", "tipo_tarea", "tokens", "origen")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def direct_record(row: dict) -> dict:
    return {"texto": row["texto"], "etiqueta": row["etiqueta_binaria"],
            "dataset": row["dataset_principal"], "grupo_duplicados": row["grupo_particion"],
            "id": row["id"], "titulo": row["titulo"], "url": row["url"],
            "tipo_tarea": row["tipo_tarea"], "tokens": len(tokenize(row["texto"])),
            "origen": "depurado_directo"}


def derived_records(direct_rows: list[dict]) -> tuple[list[dict], dict]:
    known = {fingerprint(row["texto"]) for row in direct_rows}
    output = []
    rejected = Counter()
    for row in read_csv(EXPANDED):
        if row["grupo_uso"] != "binario_derivado" or row["dataset_principal"] != "usmsc_edds":
            continue
        mark = fingerprint(row["texto"])
        if mark in known:
            rejected["duplicado_de_directo"] += 1
            continue
        tokens = len(tokenize(row["texto"]))
        if tokens < 10:
            rejected["menos_de_diez_tokens"] += 1
            continue
        if row["etiqueta_binaria"] not in ("0", "1"):
            rejected["etiqueta_invalida"] += 1
            continue
        known.add(mark)
        output.append({"texto": row["texto"], "etiqueta": row["etiqueta_binaria"],
                       "dataset": "usmsc_edds_residual", "grupo_duplicados": row["id"],
                       "id": row["id"], "titulo": row["titulo"], "url": row["url"],
                       "tipo_tarea": "binario_derivado", "tokens": tokens,
                       "origen": "usmsc_edds_nuevo"})
    return output, dict(rejected)


def sample_political(rows: list[dict], target: int) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["grupo_particion"]].append(row)
    keys = sorted(groups)
    random.Random(SEED).shuffle(keys)
    selected = []
    for key in keys:
        if len(selected) + len(groups[key]) > target:
            continue
        selected.extend(direct_record(row) for row in groups[key])
        if len(selected) == target:
            break
    if len(selected) < target - 8:
        raise AssertionError("No se pudo completar la muestra política")
    return selected


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def validate_splits(splits: dict[str, list[dict]]) -> None:
    ids, groups = set(), {}
    for split, rows in splits.items():
        if not rows or {row["etiqueta"] for row in rows} != {"0", "1"}:
            raise ValueError(f"La partición {split} está vacía o carece de una clase")
        for row in rows:
            if row["id"] in ids:
                raise AssertionError(f"Registro duplicado entre particiones: {row['id']}")
            if row["grupo_duplicados"] in groups and groups[row["grupo_duplicados"]] != split:
                raise AssertionError("Grupo relacionado cruzó particiones")
            ids.add(row["id"])
            groups[row["grupo_duplicados"]] = split


def build() -> dict:
    raw = {split: read_csv(DIRECT / f"{split}.csv") for split in
           ("entrenamiento", "validacion", "prueba_interna", "prueba_fuentes_reservadas")}
    all_direct = [row for rows in raw.values() for row in rows]
    derived, rejected = derived_records(all_direct)
    nonpolitical = {split: [direct_record(row) for row in raw[split]
                            if row["dataset_principal"] != "spanish_political_fake_news"]
                    for split in raw}
    small = {
        "entrenamiento": nonpolitical["entrenamiento"] + derived,
        "validacion": nonpolitical["validacion"],
        "prueba": nonpolitical["prueba_interna"],
        "externa": nonpolitical["prueba_fuentes_reservadas"],
    }
    political = sample_political(
        [row for row in raw["entrenamiento"]
         if row["dataset_principal"] == "spanish_political_fake_news"],
        len(small["entrenamiento"]))
    large = {**small, "entrenamiento": small["entrenamiento"] + political}
    reports = {}
    for name, splits in (("pequeno_mejorado", small), ("grande_balanceado", large)):
        validate_splits(splits)
        directory = OUTPUT / name
        if directory.exists() and any(directory.iterdir()):
            raise FileExistsError(f"La salida ya existe; no se sobrescribe: {directory}")
        directory.mkdir(parents=True)
        for split, rows in splits.items():
            write(directory / f"{split}.csv", rows)
        report = {
            "semilla": SEED, "filas": {split: len(rows) for split, rows in splits.items()},
            "fuentes": {split: dict(Counter(row["dataset"] for row in rows))
                        for split, rows in splits.items()},
            "etiquetas": {split: dict(Counter(row["etiqueta"] for row in rows))
                          for split, rows in splits.items()},
            "tokens_mediana_entrenamiento": sorted(row["tokens"] for row in splits["entrenamiento"])[
                len(splits["entrenamiento"]) // 2],
            "derivados_descartados": rejected,
            "nota": "USMSC residual carece de titular y fuente editorial verificables; se identifica en cada fila.",
        }
        (directory / "reporte.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        reports[name] = report
    return reports


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
