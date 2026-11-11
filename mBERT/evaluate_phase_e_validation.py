"""Evaluate a fixed checkpoint on Spanish validation in a new directory.

This is diagnostic for transfer. It never opens a reserved test partition.
"""

import argparse
import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import (accuracy_score, average_precision_score,
                             balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification

from phase_d_data import ROOT, load_rows, make_tokenized_dataset


parser = argparse.ArgumentParser()
parser.add_argument("--run", type=Path, required=True)
args = parser.parse_args()
run = args.run.resolve()
config = json.loads((run / "config.json").read_text(encoding="utf-8"))
length = config["length"]
model_path = run / "best_model"
if not model_path.joinpath("model.safetensors").exists():
    raise FileNotFoundError(model_path / "model.safetensors")
rows = load_rows("es_validation")
dataset, collator = make_tokenized_dataset("es_validation", length)
loader = DataLoader(dataset, batch_size=8 if length < 512 else 4, collate_fn=collator)
model = AutoModelForSequenceClassification.from_pretrained(model_path, local_files_only=True).cuda().eval()
scores = []
with torch.no_grad():
    for batch in loader:
        batch = {key: value.cuda() for key, value in batch.items() if key != "labels"}
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits = model(**batch).logits
        scores.extend(logits.float().softmax(dim=-1)[:, 1].cpu().numpy().tolist())
y = np.array([row["label"] for row in rows])
pred = (np.array(scores) >= 0.5).astype(int)
metrics = {
    "source_run": str(run), "model_sha256": hashlib.sha256((model_path / "model.safetensors").read_bytes()).hexdigest(),
    "partition": "es_validation", "n": len(rows), "length": length, "threshold": 0.5,
    "fake_f1": float(f1_score(y, pred, pos_label=1)),
    "fake_precision": float(precision_score(y, pred, pos_label=1, zero_division=0)),
    "fake_recall": float(recall_score(y, pred, pos_label=1, zero_division=0)),
    "macro_f1": float(f1_score(y, pred, average="macro")),
    "accuracy": float(accuracy_score(y, pred)),
    "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
    "average_precision_fake": float(average_precision_score(y, scores)),
    "confusion_matrix_real_fake": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
}
out = ROOT / "mBERT" / "evaluations" / f"{run.name}_esval_{datetime.now():%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:8]}"
out.mkdir(parents=True, exist_ok=False)
with (out / "metrics.json").open("x", encoding="utf-8") as handle:
    json.dump(metrics, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps({"output": str(out), "fake_f1": metrics["fake_f1"]}))
