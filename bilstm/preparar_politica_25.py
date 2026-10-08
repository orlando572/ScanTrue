"""Añade política hasta el 25 % a la variante pequeña, sin tocar datos previos."""

from __future__ import annotations

import json
from collections import Counter

from preparar_balanceados import (DIRECT, OUTPUT, read_csv, sample_political,
                                  validate_splits, write)


NAME = "pequeno_politica_25"


def build() -> dict:
    source = OUTPUT / "pequeno_mejorado"
    destination = OUTPUT / NAME
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"La salida ya existe; no se sobrescribe: {destination}")
    base = {split: read_csv(source / f"{split}.csv") for split in
            ("entrenamiento", "validacion", "prueba", "externa")}
    candidates = [row for row in read_csv(DIRECT / "entrenamiento.csv")
                  if row["dataset_principal"] == "spanish_political_fake_news"]
    # p / (n + p) = 0.25; por tanto, p = n / 3.
    target = len(base["entrenamiento"]) // 3
    political = sample_political(candidates, target)
    splits = {**base, "entrenamiento": base["entrenamiento"] + political}
    validate_splits(splits)
    destination.mkdir(parents=True)
    for split, rows in splits.items():
        write(destination / f"{split}.csv", rows)
    report = {
        "filas": {split: len(rows) for split, rows in splits.items()},
        "fuentes": {split: dict(Counter(row["dataset"] for row in rows))
                    for split, rows in splits.items()},
        "etiquetas": {split: dict(Counter(row["etiqueta"] for row in rows))
                      for split, rows in splits.items()},
        "politica_porcentaje_entrenamiento": 100 * len(political) / len(splits["entrenamiento"]),
        "politicas_seleccionadas": len(political),
        "semilla_seleccion_politica": 42,
        "nota": "Validación, prueba y fuente reservada son las mismas que en pequeno_mejorado.",
    }
    (destination / "reporte.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
