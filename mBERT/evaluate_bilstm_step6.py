"""Frozen paired evaluation: old E1 vs selected new model and sibling seeds."""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import torch
from sklearn.metrics import (accuracy_score, average_precision_score,
                             balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, f1_score,
                             precision_recall_fscore_support)
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "mBERT"
DATA = ROOT / "datasets/processed/mbert_bilstm_step3_20261008_v1"
STEP2 = ROOT / "datasets/processed/mbert_bilstm_step2_20261008_v1"
SELECTION = HERE / "selection/bilstm_step5_20261008_v1/selection.json"
OUT = HERE / "evaluations/bilstm_step6_20261008_v1"
PARTS = ("prueba", "externa")
THRESHOLD = .5


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(manifest, part):
    path = DATA / f"{part}.jsonl.gz"
    assert sha(path) == manifest["partitions"][part]["output_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == manifest["partitions"][part]["rows"]
    assert Counter(r["label"] for r in rows) == {int(k): v for k, v in manifest["partitions"][part]["labels_mbert"].items()}
    assert len({r["id"] for r in rows}) == len(rows)
    return rows


def old_input(row):
    title = row["title_audit_only"]
    text = row["text"]
    if not title:
        return text, None, "body_only"
    if text.startswith(title):
        body = text[len(title):].strip()
        assert body
        return title, body, "title_removed_from_text_for_pair"
    return title, text, "title_not_in_text_pair"


def predict(model_dir, tokenizer, rows, length, mode):
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True).cuda().eval()
    assert model.config.id2label == {0: "REAL", 1: "FALSA"}
    probabilities = []
    token_counts = []
    batch_size = 4 if length == 512 else 8
    for start in range(0, len(rows), batch_size):
        batch_rows = rows[start:start + batch_size]
        if mode == "single_text":
            encoded = tokenizer([r["text"] for r in batch_rows], truncation=True,
                                max_length=length, padding=True, return_tensors="pt")
        else:
            inputs = [old_input(r) for r in batch_rows]
            # Mixed title/body and body-only rows require per-row encoding.
            items = [tokenizer(a, b, truncation="only_second" if b is not None else True,
                               max_length=length) for a, b, _ in inputs]
            encoded = tokenizer.pad(items, padding=True, return_tensors="pt")
        mask = encoded["attention_mask"]
        token_counts.extend(int(x) for x in mask.sum(dim=1).tolist())
        encoded = {k: v.cuda() for k, v in encoded.items()}
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            logits = model(**encoded).logits
        probabilities.extend(logits.float().softmax(dim=-1)[:, 1].cpu().tolist())
    del model
    torch.cuda.empty_cache()
    assert len(probabilities) == len(token_counts) == len(rows)
    return probabilities, token_counts


def metrics(rows, probs):
    y = np.array([r["label"] for r in rows], dtype=int)
    scores = np.array(probs, dtype=float)
    pred = (scores >= THRESHOLD).astype(int)
    p, r, f, support = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
    cm = confusion_matrix(y, pred, labels=[0, 1])
    return {"n": len(y), "support": {"REAL": int(support[0]), "FALSA": int(support[1])},
            "REAL": {"precision": float(p[0]), "recall": float(r[0]), "f1": float(f[0])},
            "FALSA": {"precision": float(p[1]), "recall": float(r[1]), "f1": float(f[1])},
            "macro_f1": float(f.mean()), "accuracy": float(accuracy_score(y, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "confusion_true_rows_pred_cols_REAL_FALSA": cm.tolist(),
            "fp_real_as_fake": int(cm[0, 1]), "fn_fake_as_real": int(cm[1, 0]),
            "false_alarm_rate": float(cm[0, 1] / cm[0].sum()) if cm[0].sum() else None,
            "average_precision_fake": float(average_precision_score(y, scores)) if len(set(y)) == 2 else None,
            "brier_fake": float(brier_score_loss(y, scores))}


def source_group(row):
    host = urlparse(row["url_audit_only"] or "").netloc.casefold().removeprefix("www.")
    if host:
        return host
    return "missing_url:" + row["dataset"]


def bootstrap(rows, old_probs, new_probs, draws=1000):
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[source_group(row)].append(i)
    keys = sorted(groups)
    rng = np.random.default_rng(42)
    y = np.array([r["label"] for r in rows], dtype=int)
    old_pred = np.asarray(old_probs) >= THRESHOLD
    new_pred = np.asarray(new_probs) >= THRESHOLD
    differences = []
    for _ in range(draws):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        indices = np.array([i for key in sampled for i in groups[key]], dtype=int)
        if len(set(y[indices])) < 2:
            continue
        a = f1_score(y[indices], old_pred[indices], average="macro", labels=[0, 1])
        b = f1_score(y[indices], new_pred[indices], average="macro", labels=[0, 1])
        differences.append(b - a)
    assert differences
    return {"method": "paired source-domain bootstrap of macro F1 difference, new minus E1",
            "seed": 42, "requested": draws, "valid": len(differences),
            "groups": len(keys), "point_difference": metrics(rows, new_probs)["macro_f1"] - metrics(rows, old_probs)["macro_f1"],
            "difference_percentile_95": np.quantile(differences, [.025, .975]).tolist()}


def main():
    assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    torch.set_num_threads(4)
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    assert selection["status"] == "frozen_for_step6" and selection["test_or_external_accessed"] is False
    assert selection["inference_contract"]["fake_probability_threshold"] == THRESHOLD
    assert selection["selected_group"]["arm"] == "main" and selection["selected_group"]["length"] == 512
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["label2id"] == {"REAL": 0, "FALSA": 1}
    assert sha(HERE / "assets/tokenizer_mbert_cased/tokenizer.json") == manifest["tokenizer_json_sha256"]
    old_model_dir = Path(selection["old_e1_for_step6"]["model_dir"])
    assert sha(old_model_dir / "model.safetensors") == selection["old_e1_for_step6"]["model_sha256"]
    selected_run = selection["selected_run"]
    assert sha(Path(selected_run["model_dir"]) / "model.safetensors") == selected_run["model_sha256"]
    runs = [("new_seed" + str(r["seed"]), Path(r["path"]) / "best_model")
            for r in json.loads((HERE / "PASO_4_RESUMEN.json").read_text(encoding="utf-8"))["runs"]
            if r["arm"] == "main" and r["length"] == 512]
    assert len(runs) == 3 and [name for name, _ in runs] == ["new_seed42", "new_seed43", "new_seed44"]
    for _, model_dir in runs:
        config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        assert config["id2label"] == {"0": "REAL", "1": "FALSA"}
    old_config = json.loads((old_model_dir / "config.json").read_text(encoding="utf-8"))
    assert old_config["id2label"] == {"0": "REAL", "1": "FALSA"}
    all_rows = {part: load_rows(manifest, part) for part in PARTS}
    matches_path = STEP2 / "old_mbert_matches.csv"
    with matches_path.open(encoding="utf-8-sig", newline="") as stream:
        matches = list(csv.DictReader(stream))
    exposure = {part: {r["id_new"] for r in matches if r["split_new"] == part
                       and r["old_partition"] in ("es_train", "es_validation")}
                for part in PARTS}
    verification = json.loads((STEP2 / "verification.json").read_text(encoding="utf-8"))
    assert len(exposure["prueba"] & {r["id"] for r in all_rows["prueba"]}) == verification["splits"]["prueba"]["exposed_to_old_mbert_train_or_validation"] == 64
    assert len(exposure["externa"] & {r["id"] for r in all_rows["externa"]}) == verification["splits"]["externa"]["exposed_to_old_mbert_train_or_validation"] == 6
    for part, rows in all_rows.items():
        for row in rows:
            row["known_old_exposure"] = row["id"] in exposure[part]
            row["old_input_mode"] = old_input(row)[2]
            row["word_count"] = len(row["text"].split())
            row["source_group"] = source_group(row)
    tokenizer = AutoTokenizer.from_pretrained(HERE / "assets/tokenizer_mbert_cased", local_files_only=True)
    protocol = {"selection_sha256": sha(SELECTION), "step3_manifest_sha256": sha(DATA / "manifest.json"),
                "step2_matches_sha256": sha(matches_path), "step2_verification_sha256": sha(STEP2 / "verification.json"),
                "partitions": {part: manifest["partitions"][part]["output_sha256"] for part in PARTS},
                "models": {"old_E1": {"path": str(old_model_dir), "sha256": sha(old_model_dir / "model.safetensors"), "length": 256},
                           **{name: {"path": str(path), "sha256": sha(path / "model.safetensors"), "length": 512} for name, path in runs}},
                "new_selected": "new_seed43", "tokenizer": str(HERE / "assets/tokenizer_mbert_cased"),
                "tokenizer_sha256": sha(HERE / "assets/tokenizer_mbert_cased/tokenizer.json"),
                "threshold": THRESHOLD,
                "old_input_reconstruction": "If titulo prefixes text, remove it and pass (titulo, remainder) with only_second; if title absent pass text; if title does not prefix text, pass (titulo, text).",
                "new_input": "Exact text as one sequence; no title concatenation or normalization.",
                "scope": "Retrospective paired comparison; test/external never used in selection."}
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scores = {}
    token_counts = {}
    for name, model_dir in [("old_E1", old_model_dir)] + runs:
        for part, rows in all_rows.items():
            probability, count = predict(model_dir, tokenizer, rows,
                                         256 if name == "old_E1" else 512,
                                         "old_pair" if name == "old_E1" else "single_text")
            scores[(name, part)] = probability
            token_counts[(name, part)] = count
            print(f"PREDICTED {name} {part} {len(rows)}", flush=True)
    results = []
    for name in ("old_E1", "new_seed42", "new_seed43", "new_seed44"):
        for part, rows in all_rows.items():
            for scope in ("all", "no_known_old_train_or_validation_exposure"):
                indices = [i for i, row in enumerate(rows) if scope == "all" or not row["known_old_exposure"]]
                subset = [rows[i] for i in indices]
                probabilities = [scores[(name, part)][i] for i in indices]
                results.append({"model": name, "partition": part, "scope": scope,
                                **metrics(subset, probabilities)})
    with (OUT / "results.json").open("x", encoding="utf-8") as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2)
    with gzip.open(OUT / "predictions.csv.gz", "xt", encoding="utf-8", newline="") as stream:
        columns = ["model", "partition", "id", "dataset", "true", "prob_fake", "predicted",
                   "known_old_exposure", "old_input_mode", "word_count", "token_count", "source_group"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for name in ("old_E1", "new_seed42", "new_seed43", "new_seed44"):
            for part, rows in all_rows.items():
                for i, row in enumerate(rows):
                    writer.writerow({"model": name, "partition": part, "id": row["id"],
                                     "dataset": row["dataset"], "true": row["label"],
                                     "prob_fake": scores[(name, part)][i],
                                     "predicted": int(scores[(name, part)][i] >= THRESHOLD),
                                     "known_old_exposure": row["known_old_exposure"],
                                     "old_input_mode": row["old_input_mode"], "word_count": row["word_count"],
                                     "token_count": token_counts[(name, part)][i],
                                     "source_group": row["source_group"]})
    with gzip.open(OUT / "paired_selected.csv.gz", "xt", encoding="utf-8", newline="") as stream:
        columns = ["partition", "id", "dataset", "true", "known_old_exposure", "word_count",
                   "old_prob_fake", "new_prob_fake", "old_pred", "new_pred", "disagreement"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for part, rows in all_rows.items():
            for i, row in enumerate(rows):
                old_p = scores[("old_E1", part)][i]
                new_p = scores[("new_seed43", part)][i]
                writer.writerow({"partition": part, "id": row["id"], "dataset": row["dataset"],
                                 "true": row["label"], "known_old_exposure": row["known_old_exposure"],
                                 "word_count": row["word_count"], "old_prob_fake": old_p, "new_prob_fake": new_p,
                                 "old_pred": int(old_p >= THRESHOLD), "new_pred": int(new_p >= THRESHOLD),
                                 "disagreement": int((old_p >= THRESHOLD) != (new_p >= THRESHOLD))})
    subgroup = []
    for part, rows in all_rows.items():
        for source in sorted({r["dataset"] for r in rows}):
            indices = [i for i, row in enumerate(rows) if row["dataset"] == source]
            for name in ("old_E1", "new_seed43"):
                subgroup.append({"partition": part, "dataset": source, "model": name,
                                 **metrics([rows[i] for i in indices], [scores[(name, part)][i] for i in indices])})
        for label, condition in (("lt200", lambda n: n < 200), ("200_499", lambda n: 200 <= n < 500),
                                 ("500_999", lambda n: 500 <= n < 1000), ("ge1000", lambda n: n >= 1000)):
            indices = [i for i, row in enumerate(rows) if condition(row["word_count"])]
            if not indices:
                continue
            for name in ("old_E1", "new_seed43"):
                subgroup.append({"partition": part, "word_band": label, "model": name,
                                 **metrics([rows[i] for i in indices], [scores[(name, part)][i] for i in indices])})
    with (OUT / "subgroups.json").open("x", encoding="utf-8") as stream:
        json.dump(subgroup, stream, ensure_ascii=False, indent=2)
    uncertainty = {}
    for part, rows in all_rows.items():
        for scope in ("all", "no_known_old_train_or_validation_exposure"):
            indices = [i for i, row in enumerate(rows) if scope == "all" or not row["known_old_exposure"]]
            subset = [rows[i] for i in indices]
            uncertainty[part + "/" + scope] = bootstrap(subset,
                [scores[("old_E1", part)][i] for i in indices],
                [scores[("new_seed43", part)][i] for i in indices])
    with (OUT / "paired_bootstrap.json").open("x", encoding="utf-8") as stream:
        json.dump(uncertainty, stream, ensure_ascii=False, indent=2)
    with (OUT / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"status": "complete", "results_rows": len(results),
                   "prediction_rows": 4 * sum(len(rows) for rows in all_rows.values()),
                   "paired_rows": sum(len(rows) for rows in all_rows.values()),
                   "files_sha256": {p.name: sha(p) for p in OUT.iterdir() if p.is_file() and p.name != "manifest.json"},
                   "code_sha256": sha(Path(__file__))}, stream, ensure_ascii=False, indent=2)
    print("DONE", OUT, flush=True)


if __name__ == "__main__":
    main()
