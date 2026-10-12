"""Audit single-sequence mBERT token lengths on training and validation only."""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/processed/mbert_bilstm_step3_20261008_v1"
TOKENIZER = ROOT / "mBERT/assets/tokenizer_mbert_cased"
LENGTHS = (128, 192, 256, 512)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_split(manifest, split):
    path = DATA / f"{split}.jsonl.gz"
    assert sha(path) == manifest["partitions"][split]["output_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == manifest["partitions"][split]["rows"]
    return rows


def summarize(lengths):
    ordered = sorted(lengths)
    n = len(ordered)
    return {"n": n, "median": median(ordered), "p90": ordered[min(n - 1, int(.9 * n))],
            "p95": ordered[min(n - 1, int(.95 * n))], "max": ordered[-1],
            "truncated": {str(limit): sum(x > limit for x in ordered) for limit in LENGTHS},
            "truncated_pct": {str(limit): round(100 * sum(x > limit for x in ordered) / n, 2) for limit in LENGTHS}}


def main():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert sha(TOKENIZER / "tokenizer.json") == manifest["tokenizer_json_sha256"]
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True, use_fast=True)
    assert tokenizer.cls_token_id is not None and tokenizer.sep_token_id is not None
    report = {"data_manifest_sha256": sha(DATA / "manifest.json"),
              "tokenizer_json_sha256": sha(TOKENIZER / "tokenizer.json"),
              "lengths": list(LENGTHS), "input_mode": "single_text", "splits": {},
              "decoded_examples": [], "inference_contract": {
                  "normalization": "Exact processed text; no extra strip, lowercasing, or title concatenation",
                  "call": "tokenizer(text, truncation=True, max_length=L)",
                  "existing_E1_inferir_ejemplo_py": "Uses title/body pair and is NOT compatible with new model; new inference command needed at step 6"}}
    for split in ("entrenamiento", "validacion"):
        rows = load_split(manifest, split)
        groups = defaultdict(list)
        examples_seen = set()
        for row in rows:
            ids = tokenizer(row["text"], add_special_tokens=True, truncation=False)["input_ids"]
            assert ids[0] == tokenizer.cls_token_id and ids[-1] == tokenizer.sep_token_id
            assert ids.count(tokenizer.sep_token_id) == 1
            n = len(ids)
            groups["all"].append(n)
            groups[f"label_{row['label']}"].append(n)
            groups[f"dataset_{row['dataset']}_label_{row['label']}"].append(n)
            key = (row["dataset"], row["label"])
            if key not in examples_seen:
                examples_seen.add(key)
                preview_ids = tokenizer(row["text"], truncation=True, max_length=192)["input_ids"]
                report["decoded_examples"].append({"split": split, "id": row["id"], "dataset": row["dataset"],
                    "label": row["label"], "full_tokens": n,
                    "decoded_192_prefix": tokenizer.decode(preview_ids, skip_special_tokens=False)[:500],
                    "title_at_start": row["text"].startswith(row["title_audit_only"]) if row["title_audit_only"] else None})
        report["splits"][split] = {k: summarize(v) for k, v in groups.items()}
    output = DATA / "token_audit.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({split: report["splits"][split]["all"] for split in report["splits"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
