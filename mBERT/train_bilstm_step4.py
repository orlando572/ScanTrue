"""One isolated mBERT run on frozen BiLSTM data. Reads train/validation only."""
import argparse
import gzip
import hashlib
import json
import math
import random
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset, disable_progress_bar
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,
                             f1_score, precision_recall_fscore_support)
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          DataCollatorWithPadding, Trainer, TrainerCallback,
                          TrainingArguments, set_seed)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/processed/mbert_bilstm_step3_20261008_v1"
MODEL = ROOT / "mBERT/assets/model_mbert_cased"
TOKENIZER = ROOT / "mBERT/assets/tokenizer_mbert_cased"
RUNS = ROOT / "mBERT/runs"
LENGTHS = (128, 192, 256, 512)
SEEDS = (42, 43, 44)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(manifest, split):
    path = DATA / f"{split}.jsonl.gz"
    assert sha(path) == manifest["partitions"][split]["output_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == manifest["partitions"][split]["rows"]
    assert Counter(r["label"] for r in rows) == {int(k): v for k, v in manifest["partitions"][split]["labels_mbert"].items()}
    return rows


def score(logits, labels):
    pred = np.asarray(logits).argmax(axis=-1)
    p, r, f, support = precision_recall_fscore_support(labels, pred, labels=[0, 1], zero_division=0)
    cm = confusion_matrix(labels, pred, labels=[0, 1])
    return {"macro_f1": float(f1_score(labels, pred, average="macro", labels=[0, 1])),
            "accuracy": float(accuracy_score(labels, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(labels, pred)),
            "false_alarm_rate_real_to_fake": float(cm[0, 1] / cm[0].sum()),
            "real_precision": float(p[0]), "real_recall": float(r[0]), "real_f1": float(f[0]),
            "fake_precision": float(p[1]), "fake_recall": float(r[1]), "fake_f1": float(f[1])}


class JsonLog(TrainerCallback):
    def __init__(self, path):
        self.path = path

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"step": state.global_step, "epoch": state.epoch, **logs}, ensure_ascii=False) + "\n")


def encode(rows, tokenizer, length):
    data = Dataset.from_list([{"text": r["text"], "labels": r["label"]} for r in rows])
    def process(batch):
        return tokenizer(batch["text"], truncation=True, max_length=length)
    return data.map(process, batched=True, remove_columns=["text"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--length", type=int, choices=LENGTHS, required=True)
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    parser.add_argument("--arm", choices=("main", "no_usmsc"), required=True)
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; refusing unintended CPU training")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("BF16 unavailable; revise configuration before training")
    assert args.epochs == 3
    set_seed(args.seed)
    random.seed(args.seed)
    torch.set_num_threads(4)
    disable_progress_bar()
    out = RUNS / (f"BILSTM_ES_{args.arm}_len{args.length}_seed{args.seed}_"
                  f"{datetime.now():%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:8]}")
    out.mkdir(parents=True, exist_ok=False)
    start = time.time()
    try:
        manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["label2id"] == {"REAL": 0, "FALSA": 1}
        assert sha(TOKENIZER / "tokenizer.json") == manifest["tokenizer_json_sha256"]
        model_origin = json.loads((MODEL / "origin.json").read_text(encoding="utf-8"))
        assert model_origin["revision"] == manifest["tokenizer_revision"]
        train = load_rows(manifest, "entrenamiento")
        validation = load_rows(manifest, "validacion")
        if args.arm == "no_usmsc":
            train = [r for r in train if r["dataset"] != "usmsc_edds_residual"]
            assert len(train) == 1141
        assert not ({r["id"] for r in train} & {r["id"] for r in validation})
        tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True)
        train_ds = encode(train, tokenizer, args.length)
        val_ds = encode(validation, tokenizer, args.length)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL, num_labels=2, id2label={0: "REAL", 1: "FALSA"},
            label2id={"REAL": 0, "FALSA": 1}, local_files_only=True)
        batch = 2 if args.length == 512 else 4
        accumulation = 8 if args.length == 512 else 4
        total_steps = math.ceil(len(train) / (batch * accumulation)) * args.epochs
        training_args = TrainingArguments(
            output_dir=str(out / "checkpoints"),
            per_device_train_batch_size=batch,
            per_device_eval_batch_size=2 if args.length == 512 else 8,
            gradient_accumulation_steps=accumulation,
            num_train_epochs=args.epochs, learning_rate=2e-5,
            optim="adamw_torch", weight_decay=0.01,
            warmup_steps=max(1, round(total_steps * .10)),
            eval_strategy="epoch", save_strategy="epoch", save_total_limit=None,
            load_best_model_at_end=False,
            bf16=True, fp16=False, gradient_checkpointing=args.length == 512,
            logging_strategy="steps", logging_steps=25,
            report_to="none", seed=args.seed, data_seed=args.seed,
            dataloader_num_workers=0, skip_memory_metrics=True, disable_tqdm=True)
        config = {"phase": "BILSTM_step4", "arm": args.arm, "length": args.length,
                  "seed": args.seed, "epochs": args.epochs, "train_count": len(train),
                  "validation_count": len(validation), "train_labels": dict(Counter(r["label"] for r in train)),
                  "validation_labels": dict(Counter(r["label"] for r in validation)),
                  "input_mode": "single_text_exact", "model_source": str(MODEL),
                  "base_model_revision": model_origin["revision"],
                  "base_model_sha256": sha(MODEL / "model.safetensors"),
                  "tokenizer_sha256": sha(TOKENIZER / "tokenizer.json"),
                  "data_manifest_sha256": sha(DATA / "manifest.json"),
                  "code_sha256": sha(Path(__file__)), "torch": torch.__version__,
                  "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
                  "training_args": training_args.to_dict()}
        with (out / "config.json").open("x", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2, default=str)
        data_ref = {"train_original_sha256": sha(DATA / "entrenamiento.jsonl.gz"),
                    "validation_sha256": sha(DATA / "validacion.jsonl.gz"),
                    "train_ids_sha256": hashlib.sha256("\n".join(r["id"] for r in train).encode()).hexdigest(),
                    "validation_ids_sha256": hashlib.sha256("\n".join(r["id"] for r in validation).encode()).hexdigest(),
                    "test_or_external_accessed": False}
        with (out / "data_manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(data_ref, stream, ensure_ascii=False, indent=2)
        trainer = Trainer(model=model, args=training_args, train_dataset=train_ds,
                          eval_dataset=val_ds, data_collator=DataCollatorWithPadding(tokenizer),
                          processing_class=tokenizer,
                          compute_metrics=lambda p: score(p.predictions, p.label_ids),
                          callbacks=[JsonLog(out / "train_log.jsonl")])
        train_result = trainer.train()
        evaluations = [e for e in trainer.state.log_history if "eval_macro_f1" in e]
        assert len(evaluations) == args.epochs, evaluations
        chosen = max(evaluations, key=lambda e: (e["eval_macro_f1"], -e["step"]))
        checkpoint = out / "checkpoints" / f"checkpoint-{chosen['step']}"
        assert (checkpoint / "model.safetensors").exists()
        best = AutoModelForSequenceClassification.from_pretrained(checkpoint, local_files_only=True)
        best.save_pretrained(out / "best_model", safe_serialization=True)
        tokenizer.save_pretrained(out / "best_model")
        evaluator = Trainer(model=best, args=training_args, eval_dataset=val_ds,
                            data_collator=DataCollatorWithPadding(tokenizer),
                            processing_class=tokenizer,
                            compute_metrics=lambda p: score(p.predictions, p.label_ids))
        prediction = evaluator.predict(val_ds)
        pred = prediction.predictions.argmax(axis=-1)
        metric = score(prediction.predictions, prediction.label_ids)
        assert abs(metric["macro_f1"] - chosen["eval_macro_f1"]) < 1e-6
        cm = confusion_matrix(prediction.label_ids, pred, labels=[0, 1]).tolist()
        with (out / "predictions_validation.jsonl").open("x", encoding="utf-8") as stream:
            for row, label in zip(validation, pred):
                stream.write(json.dumps({"id": row["id"], "dataset": row["dataset"],
                                         "true": row["label"], "pred": int(label)}) + "\n")
        result = {"train": train_result.metrics, "validation": metric,
                  "validation_confusion_true_rows_pred_cols_REAL_FALSA": cm,
                  "validation_epoch_history": evaluations, "best_checkpoint": str(checkpoint),
                  "best_model_sha256": sha(out / "best_model/model.safetensors"),
                  "wall_seconds": round(time.time() - start, 2),
                  "cuda_peak_gb": round(torch.cuda.max_memory_allocated() / 2**30, 3)}
        with (out / "metrics_validation.json").open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, default=str)
        print(json.dumps({"run": str(out), "macro_f1": metric["macro_f1"],
                          "seconds": result["wall_seconds"], "peak_gb": result["cuda_peak_gb"]}), flush=True)
    except Exception:
        with (out / "error.txt").open("x", encoding="utf-8") as stream:
            traceback.print_exc(file=stream)
        raise


if __name__ == "__main__":
    main()
