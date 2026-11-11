"""Build model-ready partition files and audit mBERT lengths, without training."""

import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from transformers import AutoTokenizer


ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "datasets" / "processed" / "phase_c_seed42_v1"
B = ROOT / "datasets" / "processed" / "phase_b_20261007_v1" / "normalized_all.jsonl.gz"
OUT = ROOT / "datasets" / "processed" / "phase_d_mbert_20261007_v1"
TOKENIZER = ROOT / "mBERT" / "assets" / "tokenizer_mbert_cased"
PARTITIONS = ("es_train", "es_validation", "es_test_main", "es_test_polyglot_stress",
              "en_train", "en_validation", "en_test_perez_rosas")
AUDIT_PARTITIONS = ("es_train", "es_validation", "en_train", "en_validation")
LENGTHS = (128, 192, 256, 512)
REUTERS = re.compile(r"^[A-Z][A-Z\s,.'\-]{2,80}\s+\(Reuters\)\s*[-–]\s*", re.I)

if OUT.exists():
    raise FileExistsError(f"No overwrite: {OUT}")
manifest_c = json.loads((C / "manifest.json").read_text(encoding="utf-8"))
assert hashlib.sha256(B.read_bytes()).hexdigest() == manifest_c["source_sha256"]
with (C / "decisions.csv").open(encoding="utf-8-sig", newline="") as handle:
    partition_for = {row["id"]: row["partition"] for row in csv.DictReader(handle)}
tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True, use_fast=True)
assert tokenizer.model_max_length == 512
assert tokenizer.sep_token == "[SEP]"
origin = json.loads((TOKENIZER / "origin.json").read_text(encoding="utf-8"))

prepared = {name: [] for name in PARTITIONS}
reuters_removed = Counter()
with gzip.open(B, "rt", encoding="utf-8") as handle:
    for record in map(json.loads, handle):
        partition = partition_for[record["id"]]
        if partition not in prepared:
            continue
        title, body = record["titular"], record["cuerpo"]
        if record["dataset"] == "isot":
            body, removed = REUTERS.subn("", body, count=1)
            reuters_removed[partition] += removed
        prepared[partition].append({
            "id": record["id"], "partition": partition, "label": record["etiqueta_binaria"],
            "language": record["idioma_original"], "dataset": record["dataset"],
            "title": title, "body": body, "input_mode": "pair" if title else "body_only",
        })

for partition in PARTITIONS:
    assert len(prepared[partition]) == manifest_c["partitions"][partition]
    assert all(row["body"] for row in prepared[partition])

OUT.mkdir(parents=True, exist_ok=False)
file_hashes = {}
for partition in PARTITIONS:
    path = OUT / f"{partition}.jsonl.gz"
    with gzip.open(path, "xt", encoding="utf-8") as handle:
        for row in prepared[partition]:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    file_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

# Exact token counts on training and validation only. The pair call in future
# runs uses title as the first sequence and body as the second; `only_second`
# preserves the entire title while truncating the body.
length_report = {}
for partition in AUDIT_PARTITIONS:
    rows = prepared[partition]
    counts = []
    title_counts = []
    for start in range(0, len(rows), 128):
        batch = rows[start:start + 128]
        title_ids = tokenizer([row["title"] for row in batch], add_special_tokens=False,
                              padding=False, truncation=False)["input_ids"]
        body_ids = tokenizer([row["body"] for row in batch], add_special_tokens=False,
                             padding=False, truncation=False)["input_ids"]
        for title, body in zip(title_ids, body_ids):
            title_counts.append(len(title))
            counts.append(len(title) + len(body) + 3)
    ordered = sorted(counts)
    assert len(counts) == len(rows)
    assert max(title_counts) + 3 <= min(LENGTHS), (partition, max(title_counts))
    length_report[partition] = {
        "count": len(rows), "min": ordered[0], "median": ordered[len(ordered) // 2],
        "p90": ordered[int(0.9 * (len(ordered) - 1))],
        "p99": ordered[int(0.99 * (len(ordered) - 1))], "max": ordered[-1],
        "title_max_tokens": max(title_counts),
        "truncated_count": {str(limit): sum(size > limit for size in counts) for limit in LENGTHS},
        "truncated_pct": {str(limit): round(100 * sum(size > limit for size in counts) / len(counts), 2)
                          for limit in LENGTHS},
    }

manifest = {
    "phase": "D", "version": "mbert_20261007_v1",
    "source_phase_c_manifest_sha256": hashlib.sha256((C / "manifest.json").read_bytes()).hexdigest(),
    "source_phase_b_sha256": manifest_c["source_sha256"],
    "tokenizer_repo": origin["repo"], "tokenizer_revision": origin["revision"],
    "tokenizer_local_path": str(TOKENIZER),
    "tokenizer_files_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in TOKENIZER.iterdir() if path.is_file()},
    "file_hashes": file_hashes,
    "partition_counts": {name: len(prepared[name]) for name in PARTITIONS},
    "reuters_datelines_removed": dict(reuters_removed),
    "input_policy": "When title exists: tokenizer(title, body, truncation='only_second', max_length=L); [CLS] title [SEP] body [SEP]. Without title: tokenizer(body, truncation=True, max_length=L). Dynamic padding in batch.",
    "title_only_ablation": "Use only records with a title, keeping identical IDs for title-only and title+body comparisons; three titleless main-test rows are excluded from that paired ablation only.",
    "body_only_counts": {name: sum(row["input_mode"] == "body_only" for row in prepared[name]) for name in PARTITIONS},
    "length_audit_scope": list(AUDIT_PARTITIONS),
    "lengths": length_report,
    "test_access_policy": "Test records prepared but no test labels, lengths or model metrics inspected for configuration selection in Phase D.",
}
with (OUT / "manifest.json").open("x", encoding="utf-8") as handle:
    json.dump(manifest, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps({"output": str(OUT), "counts": manifest["partition_counts"],
                  "lengths": length_report}, ensure_ascii=False))
