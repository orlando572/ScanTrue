"""Evalúa una sola vez el modelo de titulares en la partición de prueba reservada."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from preparar import ROOT

import sys
sys.path.insert(0, str(ROOT / "bilstm"))
from entrenar_baseline import metrics  # noqa: E402
from probar_externo import load_model, predict_texts  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path,
                        default=ROOT / "datasets/experimentos_titulares/sin_politica/prueba.csv")
    parser.add_argument("--modelo", type=Path,
                        default=ROOT / "datasets/modelos_titulares/sin_politica/mejor_modelo.pt")
    parser.add_argument("--salida", type=Path,
                        default=ROOT / "datasets/modelos_titulares/sin_politica/evaluacion_prueba.json")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    frame = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    if frame.empty or not frame.etiqueta.isin(("0", "1")).all():
        raise ValueError("La partición de prueba debe tener etiquetas 0 y 1")
    model, vocab, max_len, device = load_model(args.modelo, args.device)
    probabilities = predict_texts(model, vocab, max_len, device, frame.texto.tolist())
    predicted = [0 if value >= 0.5 else 1 for value in probabilities]
    actual = frame.etiqueta.astype(int).tolist()
    report = {
        "modelo": str(args.modelo.resolve()), "max_len": max_len,
        "prueba": metrics(actual, predicted),
        "por_fuente": {
            source: metrics([actual[i] for i in indexes],
                            [predicted[i] for i in indexes])
            for source in sorted(frame.dataset.unique())
            for indexes in [[i for i, value in enumerate(frame.dataset) if value == source]]
        },
    }
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
