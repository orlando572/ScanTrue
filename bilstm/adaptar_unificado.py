"""Adapta las particiones depuradas al esquema del entrenador BiLSTM existente.

Uso: bilstm/.venv/bin/python bilstm/adaptar_unificado.py
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "datasets/unificado_total/depurado"
OUTPUT = ROOT / "datasets/experimentos_bilstm/unificado_depurado/datos"
COLUMNS = ("texto", "etiqueta", "dataset", "grupo_duplicados", "id", "titulo", "url")


def adapt(source: Path, output: Path) -> dict[str, int]:
    output.mkdir(parents=True, exist_ok=True)
    counts = {}
    for original, target in (("entrenamiento", "entrenamiento"),
                             ("validacion", "validacion"),
                             ("prueba_interna", "prueba")):
        count = 0
        with (source / f"{original}.csv").open(encoding="utf-8", newline="") as stream, \
                (output / f"{target}.csv").open("w", encoding="utf-8", newline="") as destination:
            reader = csv.DictReader(stream)
            required = {"texto", "etiqueta_binaria", "dataset_principal", "grupo_particion", "id"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"Faltan columnas en {original}.csv")
            writer = csv.DictWriter(destination, fieldnames=COLUMNS)
            writer.writeheader()
            for row in reader:
                writer.writerow({"texto": row["texto"], "etiqueta": row["etiqueta_binaria"],
                                 "dataset": row["dataset_principal"],
                                 "grupo_duplicados": row["grupo_particion"],
                                 "id": row["id"], "titulo": row["titulo"], "url": row["url"]})
                count += 1
        counts[target] = count
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(adapt(args.input, args.output))


if __name__ == "__main__":
    main()
