"""Crea dos experimentos reproducibles a partir del unificado existente."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


POLITICAL = "spanish_political_fake_news"
VARIANTS = ("sin_politica", "politica_25")
SEED = 42


def choose_political(nonpolitical: pd.DataFrame, political: pd.DataFrame,
                     max_share: float = 0.25, seed: int = SEED) -> pd.DataFrame:
    """Muestrea política por clase sin superar su proporción objetivo."""
    if not 0 < max_share < 1:
        raise ValueError("max_share debe estar entre 0 y 1")
    limit = min(len(political), int(len(nonpolitical) * max_share / (1 - max_share)))
    if limit == 0:
        return political.iloc[0:0].copy()
    available = political.etiqueta.value_counts()
    target_counts = nonpolitical.etiqueta.value_counts(normalize=True)
    labels = sorted(set(nonpolitical.etiqueta) & set(political.etiqueta))
    selected = []
    remaining = limit
    for label in labels[:-1]:
        count = min(int(round(limit * target_counts[label])), int(available[label]))
        selected.append(political[political.etiqueta == label].sample(n=count, random_state=seed))
        remaining -= count
    last = labels[-1]
    selected.append(political[political.etiqueta == last].sample(
        n=min(remaining, int(available[last])), random_state=seed + 1))
    result = pd.concat(selected, ignore_index=True)
    if len(result) != limit:
        raise ValueError("No hay suficientes ejemplos políticos por clase")
    return result


def build_variants(unified: pd.DataFrame) -> dict[str, dict[str, pd.DataFrame]]:
    required = {"dataset", "particion", "etiqueta", "texto", "grupo_duplicados"}
    if not required.issubset(unified.columns):
        raise ValueError(f"Faltan columnas: {sorted(required - set(unified.columns))}")
    if unified.etiqueta.isna().any() or set(unified.etiqueta) != {"0", "1"}:
        raise ValueError("Se necesitan las etiquetas binarias 0 y 1")
    nonpolitical = unified[unified.dataset != POLITICAL]
    train = nonpolitical[nonpolitical.particion == "entrenamiento"].copy()
    validation = nonpolitical[nonpolitical.particion == "validacion"].copy()
    test = nonpolitical[nonpolitical.particion == "prueba"].copy()
    political_train = unified[(unified.dataset == POLITICAL) &
                              (unified.particion == "entrenamiento")]
    sample = choose_political(train, political_train)
    variants = {
        "sin_politica": {"entrenamiento": train, "validacion": validation, "prueba": test},
        "politica_25": {"entrenamiento": pd.concat([train, sample], ignore_index=True),
                         "validacion": validation.copy(), "prueba": test.copy()},
    }
    for name, splits in variants.items():
        if any(frame.empty for frame in splits.values()):
            raise ValueError(f"Partición vacía en {name}")
        hashes = {split: set(frame.grupo_duplicados) for split, frame in splits.items()}
        if any(hashes[a] & hashes[b] for a, b in
               (("entrenamiento", "validacion"), ("entrenamiento", "prueba"),
                ("validacion", "prueba"))):
            raise ValueError(f"Fuga de texto entre particiones de {name}")
    return variants


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1] / "datasets"
    parser.add_argument("--input", type=Path, default=root / "estandarizados/unificado.csv")
    parser.add_argument("--output", type=Path, default=root / "experimentos_bilstm")
    args = parser.parse_args()
    unified = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    variants = build_variants(unified)
    manifest = {"seed": SEED, "political_max_share": 0.25,
                "unified_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
                "variants": {}}
    for name, splits in variants.items():
        target = args.output / name
        target.mkdir(parents=True, exist_ok=True)
        manifest["variants"][name] = {}
        for split, frame in splits.items():
            frame.to_csv(target / f"{split}.csv", index=False)
            manifest["variants"][name][split] = {
                "rows": len(frame),
                "labels": frame.etiqueta.value_counts().to_dict(),
                "sources": frame.dataset.value_counts().to_dict(),
            }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest["variants"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
