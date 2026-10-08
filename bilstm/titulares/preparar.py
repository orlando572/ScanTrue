"""Construye particiones de titulares sin alterar el corpus ni el modelo principal."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SPLITS = ("entrenamiento", "validacion", "prueba")
COLUMNS = ("dataset", "etiqueta", "texto", "titulo", "grupo_duplicados", "fuente", "url")


def normalized_title(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def prepare_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    required = {"dataset", "etiqueta", "titulo"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Faltan columnas: {sorted(required - set(frame.columns))}")
    filtered = frame[frame.titulo.map(lambda value: bool(normalized_title(value)))].copy()
    if filtered.empty or not filtered.etiqueta.isin(("0", "1")).all():
        raise ValueError("No hay titulares etiquetados válidos")
    filtered["texto"] = filtered.titulo.str.strip()
    filtered["grupo_duplicados"] = filtered.titulo.map(
        lambda value: hashlib.sha256(normalized_title(value).encode("utf-8")).hexdigest())
    if filtered.grupo_duplicados.duplicated().any():
        raise ValueError("Hay titulares repetidos dentro de una partición")
    for column in ("fuente", "url"):
        if column not in filtered:
            filtered[column] = ""
    return filtered[list(COLUMNS)], {
        "originales": len(frame), "con_titulo": len(filtered),
        "omitidos_sin_titulo": len(frame) - len(filtered),
        "etiquetas": filtered.etiqueta.value_counts().to_dict(),
        "fuentes": filtered.dataset.value_counts().to_dict(),
    }


def build(input_dir: Path, output_dir: Path) -> dict:
    prepared, report = {}, {}
    input_hashes = {}
    for split in SPLITS:
        path = input_dir / f"{split}.csv"
        input_hashes[split] = hashlib.sha256(path.read_bytes()).hexdigest()
        source = pd.read_csv(path, dtype=str, keep_default_na=False)
        prepared[split], report[split] = prepare_split(source)
        if set(prepared[split].etiqueta) != {"0", "1"}:
            raise ValueError(f"Falta una clase en {split}")
    for first, second in (("entrenamiento", "validacion"),
                          ("entrenamiento", "prueba"), ("validacion", "prueba")):
        left = set(prepared[first].grupo_duplicados)
        right = set(prepared[second].grupo_duplicados)
        if left & right:
            raise ValueError(f"Hay titulares repetidos entre {first} y {second}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for split, frame in prepared.items():
        frame.to_csv(output_dir / f"{split}.csv", index=False)
    manifest = {"input": str(input_dir.resolve()), "input_sha256": input_hashes,
                "salida": str(output_dir.resolve()), "particiones": report}
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path,
                        default=ROOT / "datasets/experimentos_bilstm/sin_politica")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "datasets/experimentos_titulares/sin_politica")
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
