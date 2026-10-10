"""Verify all step-4 runs and write an aggregate validation-only report."""
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
MATRIX = HERE / "PASO_4_MATRIX_STATUS.json"
OUT_JSON = HERE / "PASO_4_RESUMEN.json"
OUT_MD = HERE / "PASO_4_RESULTADOS_BILSTM.md"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert matrix["state"].startswith("complete")
    grouped = defaultdict(list)
    detail = []
    for arm, length, seed in matrix["matrix"]:
        matching = [p for p in RUNS.glob(f"BILSTM_ES_{arm}_len{length}_seed{seed}_*")
                    if (p / "metrics_validation.json").exists()]
        if not matching:
            assert length == 512 and arm in matrix.get("skip_512_arms", [])
            continue
        assert len(matching) == 1, matching
        path = matching[0]
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        ref = json.loads((path / "data_manifest.json").read_text(encoding="utf-8"))
        result = json.loads((path / "metrics_validation.json").read_text(encoding="utf-8"))
        assert config["arm"] == arm and config["length"] == length and config["seed"] == seed
        assert ref["test_or_external_accessed"] is False
        assert len(result["validation_epoch_history"]) == 3
        assert len(list((path / "checkpoints").glob("checkpoint-*/model.safetensors"))) == 3
        assert sha(path / "best_model/model.safetensors") == result["best_model_sha256"]
        assert sum(1 for _ in (path / "predictions_validation.jsonl").open(encoding="utf-8")) == 132
        item = {"arm": arm, "length": length, "seed": seed, "path": str(path),
                "train_count": config["train_count"], "validation": result["validation"],
                "confusion": result["validation_confusion_true_rows_pred_cols_REAL_FALSA"],
                "best_checkpoint": result["best_checkpoint"],
                "wall_seconds": result["wall_seconds"], "cuda_peak_gb": result["cuda_peak_gb"]}
        grouped[(arm, length)].append(item)
        detail.append(item)
    aggregate = []
    for (arm, length), rows in sorted(grouped.items()):
        f1 = [r["validation"]["macro_f1"] for r in rows]
        alarms = [r["validation"]["false_alarm_rate_real_to_fake"] for r in rows]
        aggregate.append({"arm": arm, "length": length, "seeds": [r["seed"] for r in rows],
                          "mean_macro_f1": statistics.mean(f1),
                          "stdev_macro_f1": statistics.stdev(f1) if len(f1) > 1 else None,
                          "mean_false_alarm_rate": statistics.mean(alarms),
                          "mean_seconds": statistics.mean(r["wall_seconds"] for r in rows),
                          "max_cuda_peak_gb": max(r["cuda_peak_gb"] for r in rows)})
    report = {"matrix_status_sha256": sha(MATRIX), "scope": "training and validation only",
              "aggregate": aggregate, "runs": detail}
    with OUT_JSON.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    lines = ["# Paso 4: entrenamientos independientes con los datos BiLSTM", "",
             "**Estado:** ejecuciones finalizadas y verificadas. La selección de configuración corresponde al paso 5; prueba y externa no se usaron.", "",
             "Cada ejecución cargó desde cero el checkpoint base mBERT local, usó solo `text` como secuencia única y entrenó tres épocas con `2e-5`, decaimiento 0,01, calentamiento 10 %, lote efectivo 16 y BF16 en la RTX 5060 Laptop. Se guardaron los tres checkpoints, el mejor por F1 macro de validación (empate por época anterior), logs, configuración, hashes, memoria, tiempos y predicciones de validación por ID. Todos los checkpoints recargados reprodujeron la F1 seleccionada.", "",
             "| Brazo | Tokens | Semillas | F1 macro media ± DE | Falsas alarmas media | Tiempo medio | Pico asignado por PyTorch |", "|---|---:|---|---:|---:|---:|---:|"]
    for r in aggregate:
        spread = f"{r['stdev_macro_f1']:.4f}" if r["stdev_macro_f1"] is not None else "—"
        lines.append(f"| {r['arm']} | {r['length']} | {', '.join(map(str, r['seeds']))} | {r['mean_macro_f1']:.4f} ± {spread} | {r['mean_false_alarm_rate']:.3%} | {r['mean_seconds']:.0f} s | {r['max_cuda_peak_gb']:.2f} GB |")
    lines.extend(["", "El pico indicado es `torch.cuda.max_memory_allocated()`, no el uso total informado por el controlador de la GPU.", "",
                  "La ablación `no_usmsc` excluye solo los 1.647 ejemplos USMSC/Edds del entrenamiento: conserva 1.141 ejemplos; usa los mismos 132 de validación. No modifica la política de prueba. La comparación de configuraciones y la elección de un checkpoint concreto se harán en el paso 5 según el plan congelado.", "",
                  "[Resumen completo en JSON](PASO_4_RESUMEN.json) · [Estado de la matriz](PASO_4_MATRIX_STATUS.json) · [Código de una ejecución](train_bilstm_step4.py) · [Ejecutor de la matriz](run_bilstm_step4_matrix.py)", ""])
    with OUT_MD.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    print(json.dumps({"verified_runs": len(detail), "groups": len(aggregate)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
