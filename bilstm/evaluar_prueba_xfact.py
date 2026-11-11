"""Evalúa los nueve BiLSTM ya fijados en afirmaciones españolas X-FACT."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean, pstdev

from entrenar_baseline import metrics
from probar_externo import load_model, predict_texts


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "datasets/pruebas_externas/x_fact"
POLITICS = ROOT / "datasets/experimentos_balanceados/serie_politica/comparacion.json"
OUTPUT = BASE / "evaluacion_modelos.json"


def score(actual: list[int], predicted: list[int]) -> dict:
    result = metrics(actual, predicted)
    matrix = result["matriz_confusion_orden_0_falsa_1_real"]
    result["falsos_positivos"] = matrix[1][0]
    result["tasa_falsos_positivos"] = matrix[1][0] / sum(matrix[1])
    return result


def evaluate() -> dict:
    if OUTPUT.exists():
        raise FileExistsError(f"La evaluación externa ya existe: {OUTPUT}")
    prep = json.loads((BASE / "preparacion.json").read_text(encoding="utf-8"))
    import hashlib
    if hashlib.sha256((BASE / "evaluacion_es_estricta.csv").read_bytes()).hexdigest() != prep["sha256_evaluacion"]:
        raise ValueError("La prueba preparada cambió desde la auditoría")
    with (BASE / "evaluacion_es_estricta.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    series = json.loads(POLITICS.read_text(encoding="utf-8"))
    result = {"prueba": str(BASE / "evaluacion_es_estricta.csv"),
              "sha256": prep["sha256_evaluacion"], "n": len(rows),
              "tarea": "afirmaciones breves verificadas de Chequeado, Argentina",
              "umbral_fijo": 0.5, "dispositivo": "cuda", "modelos": {}, "resumen": {}}
    actual = [int(row["etiqueta"]) for row in rows]
    for variant, data in series["variantes"].items():
        models = []
        for record in data["modelos"]:
            model, vocab, max_len, device = load_model(Path(record["checkpoint"]), "cuda")
            if max_len != 192:
                raise ValueError(f"Longitud inesperada: {record['checkpoint']}")
            probabilities = predict_texts(model, vocab, max_len, device,
                                          [row["texto"] for row in rows], batch_size=64)
            predicted = [0 if probability >= 0.5 else 1 for probability in probabilities]
            by_partition = {}
            for partition in sorted({row["particion_origen"] for row in rows}):
                indices = [index for index, row in enumerate(rows)
                           if row["particion_origen"] == partition]
                by_partition[partition] = score([actual[index] for index in indices],
                                                [predicted[index] for index in indices])
            measured = {"semilla": record["semilla"], "checkpoint": record["checkpoint"],
                        "metricas": score(actual, predicted),
                        "por_particion": by_partition}
            models.append(measured)
            print(variant, record["semilla"],
                  f"F1={measured['metricas']['f1_macro']:.3f}",
                  f"FP={measured['metricas']['falsos_positivos']}", flush=True)
        result["modelos"][variant] = models
        result["resumen"][variant] = {
            key: {"media": mean(item["metricas"][key] for item in models),
                  "desviacion_poblacional": pstdev(item["metricas"][key] for item in models)}
            for key in ("f1_macro", "f1_falsa", "precision_falsa", "recall_falsa",
                        "falsos_positivos", "tasa_falsos_positivos")}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    evaluate()
