"""Run one isolated mBERT fine-tuning experiment; never overwrites a run.

Validation is used for checkpoint selection. No test partition is loaded.
"""

import argparse
import hashlib
import json
import math
import random
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset, disable_progress_bar
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score,
                             precision_score, recall_score)
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          DataCollatorWithPadding, Trainer, TrainerCallback,
                          TrainingArguments, set_seed)

from phase_d_data import DATA, ROOT, VALID_LENGTHS, load_manifest, load_rows


MODEL = ROOT / "mBERT" / "assets" / "model_mbert_cased"
RUNS = ROOT / "mBERT" / "runs"


def metrics(eval_prediction):
    logits, labels = eval_prediction
    preds = np.asarray(logits).argmax(axis=-1)
    return {
        "fake_f1": float(f1_score(labels, preds, pos_label=1, zero_division=0)),
        "fake_precision": float(precision_score(labels, preds, pos_label=1, zero_division=0)),
        "fake_recall": float(recall_score(labels, preds, pos_label=1, zero_division=0)),
        "macro_f1": float(f1_score(labels, preds, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(labels, preds)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, preds)),
    }


class JsonLog(TrainerCallback):
    def __init__(self, path):
        self.path = path

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"step": state.global_step, "epoch": state.epoch,
                                         **logs}, ensure_ascii=False) + "\n")


def encode_dataset(rows, tokenizer, length):
    def encode(row):
        if row["input_mode"] == "pair":
            output = tokenizer(row["title"], row["body"], truncation="only_second", max_length=length)
        else:
            output = tokenizer(row["body"], truncation=True, max_length=length)
        output["labels"] = row["label"]
        return output

    return Dataset.from_list(rows).map(encode, remove_columns=list(rows[0]),
                                       desc=f"encode {len(rows)} len={length}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", choices=("E1", "E2", "E3", "E4"), required=True)
    parser.add_argument("--length", type=int, choices=VALID_LENGTHS, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--max-steps", type=int, default=-1,
                        help="Diagnostic cap; -1 means full configured epochs")
    parser.add_argument("--english-cap", type=int, default=0,
                        help="E2 pilot only: deterministic English subset size; 0 uses all data")
    parser.add_argument("--spanish-share", type=float, default=0.2,
                        help="E3 only: target Spanish share, downsampling English without replacement")
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--parent-model", type=Path, help="Best E2 model directory, required for E4")
    args = parser.parse_args()
    if args.experiment == "E4" and not args.parent_model:
        parser.error("E4 requires --parent-model")
    if args.experiment != "E4" and args.parent_model:
        parser.error("--parent-model only applies to E4")
    if args.english_cap and args.experiment != "E2":
        parser.error("--english-cap only applies to E2")
    if not 0 < args.spanish_share < 1:
        parser.error("--spanish-share must be between 0 and 1")
    if args.experiment != "E3" and args.spanish_share != 0.2:
        parser.error("--spanish-share only applies to E3")
    if not MODEL.joinpath("model.safetensors").exists():
        raise FileNotFoundError("Download the pinned mBERT safetensors checkpoint first")
    if args.parent_model and not args.parent_model.joinpath("model.safetensors").exists():
        raise FileNotFoundError(f"E4 parent model missing: {args.parent_model}")

    set_seed(args.seed)
    torch.set_num_threads(4)
    disable_progress_bar()
    run_name = (f"{args.experiment}_len{args.length}_seed{args.seed}_"
                f"{datetime.now():%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:8]}")
    out = RUNS / run_name
    out.mkdir(parents=True, exist_ok=False)
    start = time.time()
    try:
        data_manifest = load_manifest()
        train_names = {"E1": ("es_train",), "E2": ("en_train",),
                       "E3": ("es_train", "en_train"), "E4": ("es_train",)}[args.experiment]
        validation_name = "en_validation" if args.experiment == "E2" else "es_validation"
        train = [row for partition in train_names for row in load_rows(partition)]
        if args.experiment == "E2" and args.english_cap:
            if args.english_cap > len(train):
                parser.error("--english-cap exceeds en_train size")
            train = random.Random(args.seed).sample(train, args.english_cap)
        if args.experiment == "E3":
            spanish = [row for row in train if row["language"] == "es"]
            english = [row for row in train if row["language"] == "en"]
            target_english = round(len(spanish) * (1 - args.spanish_share) / args.spanish_share)
            english = random.Random(args.seed).sample(english, min(len(english), target_english))
            train = spanish + english
            random.Random(args.seed + 1).shuffle(train)
        validation = load_rows(validation_name)
        assert not ({row["id"] for row in train} & {row["id"] for row in validation})
        tokenizer = AutoTokenizer.from_pretrained(data_manifest["tokenizer_local_path"], local_files_only=True)
        train_ds = encode_dataset(train, tokenizer, args.length)
        val_ds = encode_dataset(validation, tokenizer, args.length)
        model_source = args.parent_model if args.parent_model else MODEL
        model = AutoModelForSequenceClassification.from_pretrained(
            model_source, num_labels=2,
            id2label={0: "REAL", 1: "FALSA"}, label2id={"REAL": 0, "FALSA": 1},
            local_files_only=True,
        )
        train_batch = 2 if args.length == 512 else 4
        accumulation = 8 if args.length == 512 else 4
        total_steps = math.ceil(math.ceil(len(train) / train_batch) / accumulation * args.epochs)
        args_hf = TrainingArguments(
            output_dir=str(out / "checkpoints"),
            per_device_train_batch_size=train_batch,
            per_device_eval_batch_size=4 if args.length == 512 else 8,
            gradient_accumulation_steps=accumulation,
            num_train_epochs=args.epochs,
            max_steps=args.max_steps,
            learning_rate=args.learning_rate,
            optim="adamw_torch",
            weight_decay=0.01,
            warmup_steps=max(1, round(total_steps * 0.10)),
            eval_strategy="epoch", save_strategy="epoch",
            load_best_model_at_end=False,
            metric_for_best_model="fake_f1", greater_is_better=True,
            bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
            fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
            logging_strategy="steps", logging_steps=25,
            report_to="none", seed=args.seed, data_seed=args.seed,
            save_total_limit=None, dataloader_num_workers=0,
            gradient_checkpointing=args.length == 512,
            skip_memory_metrics=True,
            disable_tqdm=True,
        )
        config = {
            "experiment": args.experiment, "length": args.length, "seed": args.seed,
            "epochs": args.epochs, "learning_rate": args.learning_rate,
            "max_steps": args.max_steps,
            "english_cap": args.english_cap,
            "spanish_share": args.spanish_share,
            "train_partitions": train_names, "validation_partition": validation_name,
            "train_count": len(train), "validation_count": len(validation),
            "mix_policy": (f"E3: all {sum(row['language'] == 'es' for row in train)} Spanish + "
                           f"{sum(row['language'] == 'en' for row in train)} sampled English, no replacement")
                          if args.experiment == "E3" else None,
            "model_source": str(model_source),
            "parent_model": str(args.parent_model) if args.parent_model else None,
            "base_model_revision": json.loads((MODEL / "origin.json").read_text(encoding="utf-8"))["revision"],
            "data_manifest_sha256": hashlib.sha256((DATA / "manifest.json").read_bytes()).hexdigest(),
            "training_args": args_hf.to_dict(),
            "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
        with (out / "config.json").open("x", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        with (out / "data_manifest.json").open("x", encoding="utf-8") as handle:
            json.dump({"train_ids_sha256": hashlib.sha256("\n".join(row["id"] for row in train).encode()).hexdigest(),
                       "validation_ids_sha256": hashlib.sha256("\n".join(row["id"] for row in validation).encode()).hexdigest(),
                       "phase_d_manifest_sha256": config["data_manifest_sha256"]}, handle, indent=2)
            handle.write("\n")
        trainer = Trainer(model=model, args=args_hf, train_dataset=train_ds,
                          eval_dataset=val_ds, data_collator=DataCollatorWithPadding(tokenizer),
                          processing_class=tokenizer, compute_metrics=metrics,
                          callbacks=[JsonLog(out / "train_log.jsonl")])
        train_result = trainer.train()
        evaluations = [entry for entry in trainer.state.log_history if "eval_fake_f1" in entry]
        if not evaluations:
            raise RuntimeError("No validation epoch was recorded")
        chosen = max(evaluations, key=lambda entry: (entry["eval_fake_f1"], -entry["step"]))
        best_checkpoint = out / "checkpoints" / f"checkpoint-{chosen['step']}"
        if not best_checkpoint.joinpath("model.safetensors").exists():
            raise FileNotFoundError(best_checkpoint / "model.safetensors")
        # Trainer's in-place best-model reload in this installed version does
        # not remap saved LayerNorm gamma/beta keys. from_pretrained does.
        best_model = AutoModelForSequenceClassification.from_pretrained(
            best_checkpoint, local_files_only=True
        )
        best_model.save_pretrained(str(out / "best_model"), safe_serialization=True)
        tokenizer.save_pretrained(str(out / "best_model"))
        eval_trainer = Trainer(model=best_model, args=args_hf, eval_dataset=val_ds,
                               data_collator=DataCollatorWithPadding(tokenizer),
                               processing_class=tokenizer, compute_metrics=metrics)
        val_metrics = eval_trainer.evaluate()
        if abs(val_metrics["eval_fake_f1"] - chosen["eval_fake_f1"]) > 1e-6:
            raise RuntimeError("Reloaded best checkpoint changed validation F1")
        with (out / "metrics_validation.json").open("x", encoding="utf-8") as handle:
            json.dump({"train": train_result.metrics, "validation": val_metrics,
                       "best_checkpoint": str(best_checkpoint),
                       "best_metric": chosen["eval_fake_f1"],
                       "wall_seconds": round(time.time() - start, 2),
                       "cuda_peak_gb": round(torch.cuda.max_memory_allocated() / 2**30, 3) if torch.cuda.is_available() else None},
                      handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        print(json.dumps({"run": str(out), "best_f1": chosen["eval_fake_f1"],
                          "seconds": round(time.time() - start, 2)}), flush=True)
    except Exception:
        with (out / "error.txt").open("x", encoding="utf-8") as handle:
            traceback.print_exc(file=handle)
        raise


if __name__ == "__main__":
    sys.exit(main())
