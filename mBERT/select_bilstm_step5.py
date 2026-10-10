"""Apply the frozen validation-only selection rule to step-4 mBERT runs."""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "mBERT"
DATA = ROOT / "datasets/processed/mbert_bilstm_step3_20261008_v1"
SUMMARY = HERE / "PASO_4_RESUMEN.json"
MATRIX = HERE / "PASO_4_MATRIX_STATUS.json"
TOKENIZER = HERE / "assets/tokenizer_mbert_cased"
E1 = HERE / "runs/E1_len256_seed44_20261007-202946_bda20c1f/best_model"
OUT = HERE / "selection/bilstm_step5_20261008_v1"
MARGIN = .01


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def confusion(rows):
    cm = [[0, 0], [0, 0]]
    for row in rows:
        cm[row["true"]][row["pred"]] += 1
    return cm


def class_scores(cm):
    result = {}
    for i, name in enumerate(("REAL", "FALSA")):
        tp = cm[i][i]
        actual = sum(cm[i])
        predicted = sum(cm[j][i] for j in (0, 1))
        precision = tp / predicted if predicted else 0
        recall = tp / actual if actual else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        result[name] = {"support": actual, "precision": precision, "recall": recall, "f1": f1}
    return result


def main():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    data = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert matrix["state"] == "complete" and len(summary["runs"]) == 24
    assert data["label2id"] == {"REAL": 0, "FALSA": 1}
    groups = summary["aggregate"]
    assert len(groups) == 8 and all(g["seeds"] == [42, 43, 44] for g in groups)
    top = max(g["mean_macro_f1"] for g in groups)
    near = [g for g in groups if top - g["mean_macro_f1"] < MARGIN]
    chosen_group = min(near, key=lambda g: (g["mean_false_alarm_rate"], g["length"],
                                            -g["mean_macro_f1"], g["arm"]))
    eligible = [r for r in summary["runs"] if r["arm"] == chosen_group["arm"] and r["length"] == chosen_group["length"]]
    assert len(eligible) == 3
    chosen = max(eligible, key=lambda r: (r["validation"]["macro_f1"], -r["seed"]))
    validation_path = DATA / "validacion.jsonl.gz"
    assert sha(validation_path) == data["partitions"]["validacion"]["output_sha256"]
    with gzip.open(validation_path, "rt", encoding="utf-8") as stream:
        validation = [json.loads(line) for line in stream]
    expected = {r["id"]: r for r in validation}
    assert len(expected) == len(validation) == 132
    run_path = Path(chosen["path"])
    selected_config = json.loads((run_path / "config.json").read_text(encoding="utf-8"))
    assert selected_config["input_mode"] == "single_text_exact"
    assert selected_config["length"] == chosen_group["length"]
    assert selected_config["tokenizer_sha256"] == sha(TOKENIZER / "tokenizer.json") == data["tokenizer_json_sha256"]
    assert selected_config["data_manifest_sha256"] == sha(DATA / "manifest.json")
    model_path = run_path / "best_model/model.safetensors"
    model_config = json.loads((run_path / "best_model/config.json").read_text(encoding="utf-8"))
    assert model_config["id2label"] == {"0": "REAL", "1": "FALSA"}
    assert model_config["label2id"] == {"REAL": 0, "FALSA": 1}
    run_metrics = json.loads((run_path / "metrics_validation.json").read_text(encoding="utf-8"))
    assert sha(model_path) == run_metrics["best_model_sha256"]
    with (run_path / "predictions_validation.jsonl").open(encoding="utf-8") as stream:
        predictions = [json.loads(line) for line in stream]
    assert len(predictions) == 132 and len({r["id"] for r in predictions}) == 132
    for row in predictions:
        assert row["id"] in expected
        assert row["true"] == expected[row["id"]]["label"]
        assert row["dataset"] == expected[row["id"]]["dataset"]
    cm = confusion(predictions)
    scores = class_scores(cm)
    assert cm == chosen["confusion"]
    assert abs(sum(v["f1"] for v in scores.values()) / 2 - chosen["validation"]["macro_f1"]) < 1e-12
    source_groups = defaultdict(list)
    for row in predictions:
        source_groups[row["dataset"]].append(row)
    source_metrics = {name: {"count": len(rows), "confusion_REAL_FALSA": confusion(rows),
                             "per_class": class_scores(confusion(rows))}
                      for name, rows in source_groups.items()}
    # The saved tokenizer is reserialized; verify its behavior on every validation input.
    original_tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True)
    saved_tokenizer = AutoTokenizer.from_pretrained(run_path / "best_model", local_files_only=True)
    token_differences = sum(
        original_tokenizer(row["text"], truncation=True, max_length=chosen_group["length"])["input_ids"]
        != saved_tokenizer(row["text"], truncation=True, max_length=chosen_group["length"])["input_ids"]
        for row in validation)
    assert token_differences == 0
    assert sha(E1 / "model.safetensors") == "7e6a88893c10f0d9ea89ec6b9347e00f872f140ce2752b7fa00011ccb634ff5c"
    decision = {
        "status": "frozen_for_step6", "selected_using": "validation_only",
        "rule": {"primary": "three_seed_mean_macro_f1", "tie_if_difference_strictly_less_than": MARGIN,
                 "tie_breakers": ["lower_mean_false_alarm_rate", "shorter_length"],
                 "checkpoint_within_group": "highest_validation_macro_f1_then_lower_seed"},
        "all_groups": groups, "best_mean": top,
        "near_tie_groups": [{"arm": g["arm"], "length": g["length"]} for g in near],
        "margin_to_main_256": top - next(g["mean_macro_f1"] for g in groups if g["arm"] == "main" and g["length"] == 256),
        "selected_group": chosen_group,
        "selected_run": {"path": str(run_path), "arm": chosen["arm"], "length": chosen["length"],
                         "seed": chosen["seed"], "model_dir": str(run_path / "best_model"),
                         "model_sha256": sha(model_path),
                         "config_sha256": sha(run_path / "config.json"),
                         "metrics_sha256": sha(run_path / "metrics_validation.json"),
                         "predictions_validation_sha256": sha(run_path / "predictions_validation.jsonl")},
        "other_seeds_same_group": [{"seed": r["seed"], "path": r["path"],
                                     "macro_f1": r["validation"]["macro_f1"]}
                                    for r in eligible if r["seed"] != chosen["seed"]],
        "validation": {"rows": 132, "confusion_true_rows_pred_cols_REAL_FALSA": cm,
                       "per_class": scores, "macro_f1": chosen["validation"]["macro_f1"],
                       "accuracy": chosen["validation"]["accuracy"],
                       "balanced_accuracy": chosen["validation"]["balanced_accuracy"],
                       "false_alarm_rate": chosen["validation"]["false_alarm_rate_real_to_fake"],
                       "by_source": source_metrics},
        "inference_contract": {"input": "exact text as single sequence", "title_policy": "already included in text when present; never concatenate again",
                               "tokenizer_dir": str(TOKENIZER), "tokenizer_json_sha256": sha(TOKENIZER / "tokenizer.json"),
                               "max_length": chosen_group["length"], "truncation": True,
                               "label2id": {"REAL": 0, "FALSA": 1}, "fake_probability_threshold": .5,
                               "saved_tokenizer_id_differences_on_validation": token_differences},
        "old_e1_for_step6": {"model_dir": str(E1), "model_sha256": sha(E1 / "model.safetensors"),
                             "max_length": 256, "input": "title/body pair when title exists, else body; see inferir_ejemplo.py"},
        "inputs_sha256": {"step4_summary": sha(SUMMARY), "step4_matrix": sha(MATRIX),
                          "step3_manifest": sha(DATA / "manifest.json"), "validation_gzip": sha(validation_path),
                          "selection_code": sha(Path(__file__))},
        "test_or_external_accessed": False,
    }
    OUT.mkdir(parents=True, exist_ok=False)
    with (OUT / "selection.json").open("x", encoding="utf-8") as stream:
        json.dump(decision, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"arm": chosen["arm"], "length": chosen["length"], "seed": chosen["seed"],
                      "macro_f1": chosen["validation"]["macro_f1"], "confusion": cm,
                      "margin_to_256": decision["margin_to_main_256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
