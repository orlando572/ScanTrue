"""Fit frozen, separate training-only baselines and score validation only."""
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, brier_score_loss,
                             classification_report, confusion_matrix, f1_score)
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/processed/mbert_bilstm_step3_20261008_v1"
RUNS = ROOT / "mBERT/runs"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_split(manifest, split):
    path = DATA / f"{split}.jsonl.gz"
    assert sha(path) == manifest["partitions"][split]["output_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == manifest["partitions"][split]["rows"]
    return rows


def metrics(y, pred):
    cm = confusion_matrix(y, pred, labels=[0, 1])
    return {"accuracy": accuracy_score(y, pred), "balanced_accuracy": balanced_accuracy_score(y, pred),
            "f1_macro": f1_score(y, pred, average="macro", labels=[0, 1]),
            "per_class": classification_report(y, pred, labels=[0, 1], target_names=["REAL", "FALSA"], output_dict=True, zero_division=0),
            "confusion_true_rows_pred_cols_REAL_FALSA": cm.tolist(),
            "false_alarm_rate_real_to_fake": int(cm[0, 1]) / int(cm[0].sum())}


def write_run(name, config, score, model=None):
    path = RUNS / ("BILSTM_E0_" + name + "_" + datetime.now().strftime("%Y%m%d-%H%M%S") + "_" + uuid4().hex[:8])
    path.mkdir(parents=True, exist_ok=False)
    (path / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (path / "metrics_validation.json").write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if model is not None:
        joblib.dump(model, path / "model.joblib")
        assert (path / "model.joblib").exists()
    return str(path)


def main():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    train = load_split(manifest, "entrenamiento")
    val = load_split(manifest, "validacion")
    Xtrain = [r["text"] for r in train]
    ytrain = np.array([r["label"] for r in train])
    Xval = [r["text"] for r in val]
    yval = np.array([r["label"] for r in val])
    assert set(ytrain) == set(yval) == {0, 1}
    assert not set(r["id"] for r in train).intersection(r["id"] for r in val)
    common = {"data_manifest_sha256": sha(DATA / "manifest.json"),
              "train_sha256": sha(DATA / "entrenamiento.jsonl.gz"),
              "validation_sha256": sha(DATA / "validacion.jsonl.gz"),
              "test_or_external_accessed": False, "label2id": {"REAL": 0, "FALSA": 1},
              "sklearn_version": sklearn.__version__, "decision_threshold": 0.5}
    results = {}
    majority = Counter(ytrain).most_common(1)[0][0]
    majority_pred = np.full_like(yval, majority)
    score = metrics(yval, majority_pred)
    config = {**common, "model": "train_majority", "majority_class": int(majority)}
    results["majority"] = {"path": write_run("majority", config, score), "metrics": score}
    for name, vectorizer in (("tfidf_word12", TfidfVectorizer(ngram_range=(1, 2), max_features=100000, sublinear_tf=True)),
                             ("tfidf_char35", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), max_features=100000, sublinear_tf=True))):
        model = make_pipeline(vectorizer, LogisticRegression(C=1.0, max_iter=1000, random_state=42))
        model.fit(Xtrain, ytrain)
        pred = model.predict(Xval)
        score = metrics(yval, pred)
        score["brier_fake"] = brier_score_loss(yval, model.predict_proba(Xval)[:, 1])
        config = {**common, "model": name, "C": 1.0, "max_iter": 1000, "random_state": 42,
                  "vectorizer": vectorizer.get_params()}
        # Keep config JSON simple and stable; sklearn parameters here are primitive.
        config["vectorizer"] = {k: v for k, v in config["vectorizer"].items() if isinstance(v, (str, int, float, bool, type(None), tuple))}
        results[name] = {"path": write_run(name, config, score, model), "metrics": score}
    selected = max((k for k in results if k != "majority"),
                   key=lambda k: (results[k]["metrics"]["f1_macro"], -results[k]["metrics"]["false_alarm_rate_real_to_fake"]))
    summary = {"selection_rule": "Validation macro F1, then lower real-to-fake false alarm rate; threshold 0.5",
               "selected_tfidf": selected, "results": results}
    with (DATA / "baselines_validation.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: {"f1_macro": v["metrics"]["f1_macro"], "false_alarm_rate": v["metrics"]["false_alarm_rate_real_to_fake"]} for k, v in results.items()}, ensure_ascii=False))
    print("selected:", selected)


if __name__ == "__main__":
    main()
