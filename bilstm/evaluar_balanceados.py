"""Evalúa los nuevos checkpoints balanceados en pruebas comunes sin entrenar."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from entrenar_baseline import metrics
from probar_externo import load_model, predict_texts


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "datasets/experimentos_balanceados"
OUTPUT = BASE / "comparacion.json"
MODELS = {
    "grande_aleatorio300_s42": ROOT / "datasets/modelos_balanceados/grande_aleatorio300_s42/mejor_modelo.pt",
    "grande_fasttext_cc300_s42": ROOT / "datasets/modelos_balanceados/grande_fasttext_cc300_s42/mejor_modelo.pt",
    "pequeno_mejorado_fasttext_cc300_s42": ROOT / "datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt",
    "mejor_anterior_fasttext_cc_s44": ROOT / "datasets/modelos_preentrenados/noticias_192/fasttext_cc_s44/mejor_modelo.pt",
    "unificado_128_anterior": ROOT / "datasets/modelos_bilstm/unificado_depurado/mejor_modelo.pt",
}


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def evaluate(path: Path, rows: list[dict], device_name: str) -> dict:
    model, vocab, max_len, device = load_model(path, device_name)
    probabilities = predict_texts(model, vocab, max_len, device,
                                  [row["texto"] for row in rows], batch_size=64)
    actual = [int(row["etiqueta"]) for row in rows]
    predicted = [0 if value >= 0.5 else 1 for value in probabilities]
    by_source = {}
    for source in sorted({row["dataset"] for row in rows}):
        indices = [i for i, row in enumerate(rows) if row["dataset"] == source]
        by_source[source] = metrics([actual[i] for i in indices],
                                    [predicted[i] for i in indices])
    return {"max_len": max_len, "metricas": metrics(actual, predicted),
            "por_fuente": by_source}


def build(device_name: str = "cuda") -> dict:
    tests = {
        "prueba_interna_no_politica": read(BASE / "pequeno_mejorado/prueba.csv"),
        "fuentes_reservadas": read(BASE / "pequeno_mejorado/externa.csv"),
    }
    report = {"dispositivo": device_name,
              "nota": "Prueba interna comparable solo entre los tres modelos nuevos; fuentes reservadas ya consultadas en experimentos previos.",
              "pruebas": {name: {"n": len(rows), "modelos": {}} for name, rows in tests.items()}}
    for name, path in MODELS.items():
        if not path.exists():
            raise FileNotFoundError(path)
        for test_name, rows in tests.items():
            if test_name == "prueba_interna_no_politica" and name not in (
                    "grande_aleatorio300_s42", "grande_fasttext_cc300_s42",
                    "pequeno_mejorado_fasttext_cc300_s42"):
                continue
            report["pruebas"][test_name]["modelos"][name] = evaluate(path, rows, device_name)
            print(name, test_name,
                  report["pruebas"][test_name]["modelos"][name]["metricas"]["f1_macro"],
                  flush=True)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    build()
