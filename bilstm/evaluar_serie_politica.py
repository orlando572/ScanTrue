"""Compara 0, 25 y 50 % de política con tres semillas y pruebas comunes."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean, pstdev

from entrenar_baseline import metrics
from probar_externo import load_model, predict_texts


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/experimentos_balanceados"
MODELS = ROOT / "datasets/modelos_balanceados"
OUTPUT = DATA / "serie_politica"
VARIANTS = {
    "pequeno_mejorado": (0, "pequeno_mejorado_fasttext_cc300_s42"),
    "pequeno_politica_25": (25, None),
    "grande_balanceado": (50, "grande_fasttext_cc300_s42"),
}


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def score(actual: list[int], predicted: list[int]) -> dict:
    result = metrics(actual, predicted)
    confusion = result["matriz_confusion_orden_0_falsa_1_real"]
    real = confusion[1][0] + confusion[1][1]
    result["falsos_positivos"] = confusion[1][0]
    result["reales"] = real
    result["tasa_falsos_positivos"] = confusion[1][0] / real if real else None
    return result


def evaluate(checkpoint: Path, rows: list[dict[str, str]]) -> dict:
    model, vocab, max_len, device = load_model(checkpoint, "cuda")
    probabilities = predict_texts(model, vocab, max_len, device,
                                  [row["texto"] for row in rows], batch_size=64)
    actual = [int(row["etiqueta"]) for row in rows]
    predicted = [0 if probability >= 0.5 else 1 for probability in probabilities]
    by_source = {}
    for source in sorted({row["dataset"] for row in rows}):
        indices = [index for index, row in enumerate(rows) if row["dataset"] == source]
        by_source[source] = score([actual[index] for index in indices],
                                  [predicted[index] for index in indices])
    return {"max_len": max_len, "metricas": score(actual, predicted),
            "por_fuente": by_source}


def aggregate(models: list[dict], test: str) -> dict:
    keys = ("f1_macro", "f1_falsa", "precision_falsa", "recall_falsa",
            "falsos_positivos", "tasa_falsos_positivos")
    def stats(items: list[dict]) -> dict:
        return {key: {"media": mean(item[key] for item in items),
                      "desviacion_poblacional": pstdev(item[key] for item in items)}
                for key in keys if all(item[key] is not None for item in items)}
    all_scores = [item["pruebas"][test]["metricas"] for item in models]
    sources = sorted(models[0]["pruebas"][test]["por_fuente"])
    return {"global": stats(all_scores), "por_fuente": {
        source: stats([item["pruebas"][test]["por_fuente"][source]
                       for item in models]) for source in sources}}


def build() -> dict:
    tests = {
        "prueba_interna": read(DATA / "pequeno_mejorado/prueba.csv"),
        "fuentes_reservadas_exploratoria": read(DATA / "pequeno_mejorado/externa.csv"),
    }
    report = {"configuracion": {"embeddings": "fastText CC español 300d",
                               "max_len": 192, "device": "cuda", "semillas": [42, 43, 44],
                               "criterio_checkpoint": "F1 macro de validación común"},
              "advertencia": "Las fuentes reservadas ya se consultaron en rondas previas; no son una prueba nueva ni confirman superioridad para despliegue.",
              "pruebas": {name: {"n": len(rows), "fuentes": sorted({row["dataset"] for row in rows})}
                          for name, rows in tests.items()},
              "variantes": {}}
    for variant, (politics_percent, old_s42) in VARIANTS.items():
        models = []
        for seed in (42, 43, 44):
            folder = (MODELS / old_s42 if seed == 42 and old_s42 else
                      MODELS / "serie_politica" / f"{variant}_fasttext_cc300_s{seed}")
            config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
            result = json.loads((folder / "resultados.json").read_text(encoding="utf-8"))
            if (config["device"] != "cuda" or config["max_len"] != 192 or
                    config["embedding_dim"] != 300 or config["seed"] != seed or
                    config["embedding_source"] != "fasttext_cc"):
                raise ValueError(f"Configuración incompatible: {folder}")
            checks = {name: evaluate(folder / "mejor_modelo.pt", rows)
                      for name, rows in tests.items()}
            record = {"semilla": seed, "checkpoint": str(folder / "mejor_modelo.pt"),
                      "mejor_epoca": result["best_epoch"],
                      "validacion": result["validation_best"], "pruebas": checks}
            models.append(record)
            print(variant, seed, *(f"{name}: F1={value['metricas']['f1_macro']:.3f}, "
                                   f"FP={value['metricas']['falsos_positivos']}"
                                   for name, value in checks.items()), flush=True)
        report["variantes"][variant] = {
            "politica_porcentaje_entrenamiento": politics_percent,
            "n_entrenamiento": len(read(DATA / variant / "entrenamiento.csv")),
            "modelos": models,
            "resumen": {name: aggregate(models, name) for name in tests},
        }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "comparacion.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    build()
