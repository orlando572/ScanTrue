"""Audita si rechazar noticias breves cambia errores y cobertura; no entrena."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from entrenar_baseline import metrics, tokenize
from probar_externo import load_model, predict_texts


ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "datasets/unificado_total/depurado/prueba_fuentes_reservadas.csv"
OUTPUT = ROOT / "datasets/evaluaciones_min_tokens/reporte.json"
MODELS = {
    "mejor_anterior_fasttext_cc_s44": ROOT / "datasets/modelos_preentrenados/noticias_192/fasttext_cc_s44/mejor_modelo.pt",
    "unificado_128": ROOT / "datasets/modelos_bilstm/unificado_depurado/mejor_modelo.pt",
    "grande_balanceado_aleatorio300": ROOT / "datasets/modelos_balanceados/grande_aleatorio300_s42/mejor_modelo.pt",
    "grande_balanceado_fasttext_cc300": ROOT / "datasets/modelos_balanceados/grande_fasttext_cc300_s42/mejor_modelo.pt",
    "pequeno_mejorado_fasttext_cc300": ROOT / "datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt",
}
MINIMA = (0, 10, 20, 30, 50, 100, 128, 192, 384)


def build() -> dict:
    with TEST.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    lengths = [len(tokenize(row["texto"])) for row in rows]
    result = {"prueba": str(TEST), "total": len(rows), "modelos": {},
              "nota": "Es rechazo de entradas breves, no mejora causal del modelo; la prueba ya se consultó antes."}
    for name, path in MODELS.items():
        model, vocab, max_len, device = load_model(path, "cpu")
        probabilities = predict_texts(model, vocab, max_len, device,
                                      [row["texto"] for row in rows], batch_size=64)
        predictions = [0 if value >= 0.5 else 1 for value in probabilities]
        by_minimum = {}
        for minimum in MINIMA:
            indices = [i for i, length in enumerate(lengths) if length >= minimum]
            actual = [int(rows[i]["etiqueta_binaria"]) for i in indices]
            predicted = [predictions[i] for i in indices]
            if not indices:
                continue
            result_metrics = metrics(actual, predicted)
            matrix = result_metrics["matriz_confusion_orden_0_falsa_1_real"]
            false_positives = matrix[1][0]  # Real clasificada como falsa.
            by_minimum[str(minimum)] = {
                "n_evaluadas": len(indices), "rechazadas": len(rows) - len(indices),
                "cobertura": len(indices) / len(rows),
                "falsos_positivos": false_positives,
                "tasa_falsos_positivos": false_positives / sum(matrix[1]) if sum(matrix[1]) else 0.0,
                "metricas": result_metrics,
            }
        result["modelos"][name] = {"max_len": max_len, "umbrales": by_minimum}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    report = build()
    for name, model in report["modelos"].items():
        print(name)
        for minimum, item in model["umbrales"].items():
            print(minimum, item["n_evaluadas"], item["falsos_positivos"],
                  round(item["tasa_falsos_positivos"], 3),
                  round(item["metricas"]["f1_macro"], 3))
