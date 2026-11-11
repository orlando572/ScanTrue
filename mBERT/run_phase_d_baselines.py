"""E0 majority and TF-IDF baselines on frozen train/validation IDs only."""

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
                             balanced_accuracy_score, confusion_matrix,
                             f1_score, precision_score, recall_score)


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "datasets" / "processed" / "phase_d_mbert_20261007_v1"
RUNS = ROOT / "mBERT" / "runs"
DATA_MANIFEST = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
SCENARIOS = {
    "es": (["es_train"], "es_validation"),
    "en": (["en_train"], "en_validation"),
    "mixed": (["es_train", "en_train"], "es_validation"),
}


def load(partition):
    path = DATA / f"{partition}.jsonl.gz"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == DATA_MANIFEST["file_hashes"][path.name]
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return list(map(json.loads, handle))


def model_text(row):
    return row["title"] + "\n" + row["body"] if row["title"] else row["body"]


def metric_result(y_true, y_pred, positive_score=None):
    output = {
        "n": len(y_true),
        "support": {"real": int(sum(y_true == 0)), "fake": int(sum(y_true == 1))},
        "fake_precision": float(precision_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "fake_recall": float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "fake_f1": float(f1_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "confusion_matrix_real_fake": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }
    if positive_score is not None:
        output["average_precision_fake"] = float(average_precision_score(y_true, positive_score))
    return output


def run_scenario(name, train_names, validation_name):
    out = RUNS / f"E0_{name}_seed42_phaseD_v1"
    if out.exists():
        raise FileExistsError(f"An earlier baseline run exists: {out}")
    training = [row for partition in train_names for row in load(partition)]
    validation = load(validation_name)
    assert not ({row["id"] for row in training} & {row["id"] for row in validation})
    y_train = np.array([row["label"] for row in training], dtype=np.int8)
    y_val = np.array([row["label"] for row in validation], dtype=np.int8)
    majority_label = Counter(y_train).most_common(1)[0][0]
    majority_pred = np.full(len(validation), majority_label, dtype=np.int8)

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2), min_df=2, max_features=100_000,
        sublinear_tf=True, dtype=np.float32,
    )
    X_train = vectorizer.fit_transform([model_text(row) for row in training])
    X_val = vectorizer.transform([model_text(row) for row in validation])
    model = LogisticRegression(solver="liblinear", max_iter=300, random_state=42)
    model.fit(X_train, y_train)
    score = model.predict_proba(X_val)[:, list(model.classes_).index(1)]
    pred = (score >= 0.5).astype(np.int8)
    metrics = {
        "scenario": name,
        "train_partitions": train_names, "validation_partition": validation_name,
        "majority_label": int(majority_label),
        "majority": metric_result(y_val, majority_pred),
        "tfidf_logistic": metric_result(y_val, pred, score),
        "threshold": 0.5,
        "train_count": len(training), "validation_count": len(validation),
        "features": int(X_train.shape[1]),
        "data_manifest_sha256": hashlib.sha256((DATA / "manifest.json").read_bytes()).hexdigest(),
        "sklearn_version": sklearn.__version__,
    }
    out.mkdir(parents=True, exist_ok=False)
    with (out / "metrics_validation.json").open("x", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    joblib.dump({"vectorizer": vectorizer, "classifier": model}, out / "model.joblib", compress=3)
    with (out / "data_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump({"train_ids_sha256": hashlib.sha256("\n".join(row["id"] for row in training).encode()).hexdigest(),
                   "validation_ids_sha256": hashlib.sha256("\n".join(row["id"] for row in validation).encode()).hexdigest(),
                   "train_partitions": train_names, "validation_partition": validation_name,
                   "phase_d_manifest_sha256": metrics["data_manifest_sha256"]}, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"scenario": name, "path": str(out),
                      "majority_f1": metrics["majority"]["fake_f1"],
                      "tfidf_f1": metrics["tfidf_logistic"]["fake_f1"]}), flush=True)


if __name__ == "__main__":
    for name, (train_names, validation_name) in SCENARIOS.items():
        run_scenario(name, train_names, validation_name)
