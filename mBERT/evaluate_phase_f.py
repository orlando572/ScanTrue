"""One-pass evaluation of the frozen Phase F protocol; never changes checkpoints."""

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.metrics import (accuracy_score, average_precision_score,
                             balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, f1_score, precision_recall_curve,
                             precision_recall_fscore_support)
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification

from phase_d_data import ROOT, load_rows, make_tokenized_dataset


HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "phase_f_plan_20261007_v1.json"
OUT = HERE / "evaluations" / "phase_f_20261007_v1"
PLAN = json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def save_json(path, data):
    with path.open("x", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def metrics(y, scores):
    y = np.asarray(y, dtype=np.int8)
    scores = np.asarray(scores, dtype=float)
    pred = (scores >= PLAN["threshold"]).astype(np.int8)
    p, r, f, s = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
    cm = confusion_matrix(y, pred, labels=[0, 1])
    return {
        "n": int(len(y)), "support": {"real": int(s[0]), "fake": int(s[1])},
        "real_precision": float(p[0]), "real_recall": float(r[0]), "real_f1": float(f[0]),
        "fake_precision": float(p[1]), "fake_recall": float(r[1]), "fake_f1": float(f[1]),
        "macro_f1": float(np.mean(f)), "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "confusion_matrix_real_fake": cm.tolist(), "tn": int(cm[0, 0]),
        "fp": int(cm[0, 1]), "fn": int(cm[1, 0]), "tp": int(cm[1, 1]),
        "average_precision_fake": float(average_precision_score(y, scores)),
        "brier_fake": float(brier_score_loss(y, scores)), "threshold": PLAN["threshold"]
    }


def main():
    assert PLAN["selection_frozen_before_test"] and PLAN["threshold"] == 0.5
    assert not OUT.exists(), f"Existing evaluation is preserved: {OUT}"
    selected = HERE / "runs" / PLAN["selected_run"] / "best_model" / "model.safetensors"
    assert hashlib.sha256(selected.read_bytes()).hexdigest() == PLAN["selected_model_sha256"]
    OUT.mkdir(parents=True, exist_ok=False)
    save_json(OUT / "protocol.json", {**PLAN, "plan_sha256": hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()})
    torch.set_num_threads(4)
    partitions = {part: load_rows(part) for part in PLAN["partitions"]}
    for part, rows in partitions.items():
        assert len({r["id"] for r in rows}) == len(rows)
    encoded = {}
    results = []
    predictions = {}

    for exp, runs in PLAN["runs"].items():
        for run_name in runs:
            run = HERE / "runs" / run_name
            config = json.loads((run / "config.json").read_text(encoding="utf-8"))
            assert config["experiment"] == exp
            length = config["length"]
            model_file = run / "best_model" / "model.safetensors"
            model_hash = hashlib.sha256(model_file.read_bytes()).hexdigest()
            model = AutoModelForSequenceClassification.from_pretrained(run / "best_model", local_files_only=True).cuda().eval()
            for part, rows in partitions.items():
                key = (part, length)
                if key not in encoded:
                    encoded[key] = make_tokenized_dataset(part, length)
                dataset, collator = encoded[key]
                loader = DataLoader(dataset, batch_size=8, collate_fn=collator)
                scores = []
                with torch.inference_mode():
                    for batch in loader:
                        batch = {k: v.cuda() for k, v in batch.items() if k != "labels"}
                        with torch.autocast("cuda", dtype=torch.bfloat16):
                            logits = model(**batch).logits
                        scores.extend(logits.float().softmax(-1)[:, 1].cpu().tolist())
                assert len(scores) == len(rows)
                y = [row["label"] for row in rows]
                result = {"experiment": exp, "run": run_name, "partition": part,
                          "max_length": length, "seed": config["seed"], "model_sha256": model_hash,
                          **metrics(y, scores)}
                results.append(result)
                predictions[(run_name, part)] = np.asarray(scores)
                save_json(OUT / f"{run_name}__{part}.json", result)
                print(f"{run_name} {part} F1={result['fake_f1']:.4f}", flush=True)
            del model
            torch.cuda.empty_cache()

    for name in PLAN["baselines"]:
        run = HERE / "runs" / name
        obj = joblib.load(run / "model.joblib")
        for part, rows in partitions.items():
            texts = [row["title"] + "\n" + row["body"] if row["title"] else row["body"] for row in rows]
            scores = obj["classifier"].predict_proba(obj["vectorizer"].transform(texts))[:, 1]
            result = {"experiment": "E0", "run": name, "partition": part, "max_length": None,
                      **metrics([row["label"] for row in rows], scores)}
            results.append(result)
            predictions[(name, part)] = scores
            save_json(OUT / f"{name}__{part}.json", result)
            print(f"{name} {part} F1={result['fake_f1']:.4f}", flush=True)

    with (OUT / "results.csv").open("x", newline="", encoding="utf-8") as file:
        columns = ["experiment", "run", "partition", "max_length", "seed", "n", "fake_f1",
                   "fake_precision", "fake_recall", "real_f1", "macro_f1", "accuracy",
                   "balanced_accuracy", "fp", "fn", "average_precision_fake", "brier_fake"]
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # Keep row-level outputs auditable while avoiding duplication of full copyrighted article text.
    with gzip.open(OUT / "predictions.csv.gz", "xt", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["run", "partition", "id", "true", "prob_fake", "predicted"])
        for (run, part), scores in predictions.items():
            for row, score in zip(partitions[part], scores):
                writer.writerow([run, part, row["id"], row["label"], float(score), int(score >= 0.5)])

    # The retained Spanish candidate's PR curve is diagnostic only; no test threshold is adopted.
    main_rows = partitions["es_test_main"]
    main_y = np.array([row["label"] for row in main_rows])
    selected_scores = predictions[(PLAN["selected_run"], "es_test_main")]
    p, r, t = precision_recall_curve(main_y, selected_scores)
    with (OUT / "selected_pr_curve.csv").open("x", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["threshold", "precision", "recall"])
        writer.writerows(zip(list(t) + [""], p, r))

    # Attach source and topic metadata for subgroup and error audits.
    wanted = {row["id"] for rows in partitions.values() for row in rows}
    meta = {}
    source_file = ROOT / "datasets" / "processed" / "phase_b_20261007_v1" / "normalized_all.jsonl.gz"
    with gzip.open(source_file, "rt", encoding="utf-8") as file:
        for line in file:
            row = json.loads(line)
            if row["id"] in wanted:
                meta[row["id"]] = row
    assert wanted <= meta.keys()
    audit = []
    for part, rows in partitions.items():
        scores = predictions[(PLAN["selected_run"], part)]
        for row, score in zip(rows, scores):
            original = meta[row["id"]]
            audit.append({"partition": part, "id": row["id"], "dataset": row["dataset"],
                          "source": original.get("fuente") or "(sin fuente)",
                          "topic": original.get("tema") or "(sin tema)",
                          "period": original.get("fecha") or original.get("periodo") or "(sin fecha)",
                          "word_count": len((row["title"] + " " + row["body"]).split()),
                          "input_mode": row["input_mode"], "true": row["label"],
                          "prob_fake": float(score), "predicted": int(score >= 0.5)})
    with (OUT / "selected_audit.csv").open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)

    # Paired source-group bootstrap: equal resampled sources, preserving all records within each.
    groups = defaultdict(list)
    for i, row in enumerate(audit[:len(main_rows)]):
        groups[str(row["source"]).casefold()].append(i)
    group_keys = sorted(groups)
    rng = np.random.default_rng(42)
    e3_scores = predictions[(PLAN["runs"]["E3"][2], "es_test_main")]
    boot = []
    for _ in range(1000):
        sampled = rng.choice(group_keys, size=len(group_keys), replace=True)
        ids = np.array([i for g in sampled for i in groups[g]], dtype=int)
        if len(np.unique(main_y[ids])) < 2:
            continue
        a = f1_score(main_y[ids], selected_scores[ids] >= 0.5, pos_label=1, zero_division=0)
        b = f1_score(main_y[ids], e3_scores[ids] >= 0.5, pos_label=1, zero_division=0)
        boot.append((a, b, b - a))
    boot = np.asarray(boot)
    save_json(OUT / "source_bootstrap.json", {
        "method": "paired source-group bootstrap", "seed": 42, "requested_resamples": 1000,
        "valid_resamples": len(boot), "source_group_count": len(group_keys),
        "e1_f1_95pct": np.quantile(boot[:, 0], [0.025, 0.975]).tolist(),
        "e3_seed44_f1_95pct": np.quantile(boot[:, 1], [0.025, 0.975]).tolist(),
        "e3_minus_e1_95pct": np.quantile(boot[:, 2], [0.025, 0.975]).tolist()})
    save_json(OUT / "manifest.json", {"results": len(results), "predictions": sum(len(v) for v in predictions.values()),
                                      "selected_run": PLAN["selected_run"], "source_group_count": len(group_keys)})
    print(f"DONE {OUT}", flush=True)


if __name__ == "__main__":
    main()
