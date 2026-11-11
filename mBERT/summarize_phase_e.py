"""Verify isolated training artifacts and freeze a validation-only selection."""

import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
OUT = ROOT / "phase_e_summary_20261007_v1"
if OUT.exists():
    raise FileExistsError(f"No overwrite: {OUT}")

completed = []
incomplete = []
for run in sorted(RUNS.iterdir()):
    if not run.is_dir() or not run.name.startswith(("E1_", "E2_", "E3_", "E4_")):
        continue
    config_path, metrics_path = run / "config.json", run / "metrics_validation.json"
    if not config_path.exists() or not metrics_path.exists():
        incomplete.append({"run": run.name, "status": "interrupted_or_failed"})
        continue
    config = json.loads(config_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    best = run / "best_model" / "model.safetensors"
    checkpoint = Path(metrics["best_checkpoint"]) / "model.safetensors"
    assert best.exists() and checkpoint.exists(), run
    assert abs(metrics["best_metric"] - metrics["validation"]["eval_fake_f1"]) < 1e-6, run
    assert not (run / "metrics_test.json").exists(), run
    assert config["validation_partition"] in ("es_validation", "en_validation"), run
    assert all("test" not in part for part in config["train_partitions"]), run
    if config["experiment"] == "E2":
        assert config["validation_partition"] == "en_validation"
    else:
        assert config["validation_partition"] == "es_validation"
    completed.append({
        "run": run.name, "experiment": config["experiment"], "length": config["length"],
        "seed": config["seed"], "learning_rate": config["learning_rate"],
        "epochs": config["epochs"], "max_steps": config.get("max_steps", -1),
        "english_cap": config.get("english_cap") or 0,
        "spanish_share": config.get("spanish_share", 0.2),
        "train_count": config["train_count"], "validation_count": config["validation_count"],
        "validation": config["validation_partition"],
        "fake_f1": metrics["best_metric"],
        "fake_precision": metrics["validation"]["eval_fake_precision"],
        "fake_recall": metrics["validation"]["eval_fake_recall"],
        "macro_f1": metrics["validation"]["eval_macro_f1"],
        "best_checkpoint": metrics["best_checkpoint"],
        "cuda_peak_gb": metrics["cuda_peak_gb"],
        "wall_seconds": metrics["wall_seconds"],
    })

groups = {}
for experiment, length, rate in (("E1", 192, 2e-5), ("E1", 256, 2e-5),
                                 ("E1", 256, 3e-5), ("E3", 256, 2e-5)):
    candidates = sorted((row for row in completed if row["experiment"] == experiment
                         and row["length"] == length and row["learning_rate"] == rate
                         and row["max_steps"] == -1 and row["english_cap"] == 0
                         and row["spanish_share"] == 0.2), key=lambda row: row["seed"])
    assert [row["seed"] for row in candidates] == [42, 43, 44], (experiment, length, rate)
    scores = [row["fake_f1"] for row in candidates]
    groups[f"{experiment}_len{length}_lr{rate:g}"] = {
        "seeds": [42, 43, 44], "runs": [row["run"] for row in candidates],
        "fake_f1": scores, "mean": statistics.mean(scores), "sample_sd": statistics.stdev(scores),
    }

e1 = groups["E1_len256_lr2e-05"]
e3 = groups["E3_len256_lr2e-05"]
chosen = max((row for row in completed if row["run"] in e1["runs"]),
             key=lambda row: row["fake_f1"])
selected_model = RUNS / chosen["run"] / "best_model" / "model.safetensors"
selection = {
    "configuration": "E1 Spanish only, 256 tokens, 2e-5, 3 epochs, batch 4, accumulation 4",
    "reason": "Highest three-seed mean among repeated E1 configurations; E3 256 did not improve the mean Spanish validation F1.",
    "selected_checkpoint_run": chosen["run"], "selected_seed": chosen["seed"],
    "selected_validation_fake_f1": chosen["fake_f1"],
    "selected_model_sha256": hashlib.sha256(selected_model.read_bytes()).hexdigest(),
    "e1_mean": e1["mean"], "e3_mean": e3["mean"],
    "difference_e3_minus_e1": e3["mean"] - e1["mean"],
    "test_partitions_opened": False,
}
result = {"completed_run_count": len(completed), "incomplete_runs": incomplete,
          "groups": groups, "selection": selection}
OUT.mkdir(parents=True, exist_ok=False)
with (OUT / "runs.csv").open("x", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(completed[0]))
    writer.writeheader()
    writer.writerows(completed)
with (OUT / "summary.json").open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps({"completed": len(completed), "incomplete": len(incomplete),
                  "e1_mean": e1["mean"], "e3_mean": e3["mean"],
                  "selected": chosen["run"]}, ensure_ascii=False))
