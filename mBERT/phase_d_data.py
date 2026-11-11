"""Verified Phase D dataset loader for later, isolated mBERT runs.

Importing this module performs no downloads, tokenization, or training.
"""

import gzip
import hashlib
import json
from pathlib import Path

from datasets import Dataset
from transformers import AutoTokenizer, DataCollatorWithPadding


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "datasets" / "processed" / "phase_d_mbert_20261007_v1"
VALID_LENGTHS = (128, 192, 256, 512)


def load_manifest():
    return json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))


def load_rows(partition):
    manifest = load_manifest()
    if partition not in manifest["partition_counts"]:
        raise ValueError(f"Unknown partition: {partition}")
    path = DATA / f"{partition}.jsonl.gz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["file_hashes"][path.name]:
        raise ValueError(f"Data checksum mismatch: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = list(map(json.loads, handle))
    if len(rows) != manifest["partition_counts"][partition]:
        raise ValueError(f"Count mismatch: {partition}")
    return rows


def make_tokenized_dataset(partition, max_length, title_only=False):
    if max_length not in VALID_LENGTHS:
        raise ValueError(f"max_length must be one of {VALID_LENGTHS}")
    rows = load_rows(partition)
    if title_only:
        rows = [row for row in rows if row["title"]]
    tokenizer = AutoTokenizer.from_pretrained(load_manifest()["tokenizer_local_path"],
                                               local_files_only=True)

    def encode(row):
        if title_only:
            result = tokenizer(row["title"], truncation=True, max_length=max_length)
        elif row["input_mode"] == "pair":
            result = tokenizer(row["title"], row["body"],
                               truncation="only_second", max_length=max_length)
        else:
            result = tokenizer(row["body"], truncation=True, max_length=max_length)
        result["labels"] = row["label"]
        return result

    dataset = Dataset.from_list(rows).map(encode, remove_columns=list(rows[0]),
                                          desc=f"{partition} len={max_length}")
    collator = DataCollatorWithPadding(tokenizer=tokenizer, padding=True)
    return dataset, collator
