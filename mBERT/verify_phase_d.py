"""Check Phase D files, frozen IDs and all configured token lengths."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from phase_d_data import DATA, ROOT, VALID_LENGTHS, load_manifest, load_rows, make_tokenized_dataset


manifest = load_manifest()
C = ROOT / "datasets" / "processed" / "phase_c_seed42_v1"
assert hashlib.sha256((C / "manifest.json").read_bytes()).hexdigest() == manifest["source_phase_c_manifest_sha256"]
with (C / "decisions.csv").open(encoding="utf-8-sig", newline="") as handle:
    decisions = list(csv.DictReader(handle))
expected = {partition: {row["id"] for row in decisions if row["partition"] == partition}
            for partition in manifest["partition_counts"]}
for partition in manifest["partition_counts"]:
    rows = load_rows(partition)
    assert {row["id"] for row in rows} == expected[partition]
    assert len(rows) == len(expected[partition])
    assert Counter(str(row["label"]) for row in rows) == Counter(
        str(int(row["label"])) for row in decisions if row["partition"] == partition
    )
    assert sum(row["input_mode"] == "body_only" for row in rows) == manifest["body_only_counts"][partition]

token_shapes = {}
for length in VALID_LENGTHS:
    dataset, collator = make_tokenized_dataset("es_train", length)
    assert len(dataset) == manifest["partition_counts"]["es_train"]
    assert max(len(row["input_ids"]) for row in dataset) <= length
    batch = collator([dataset[0], dataset[1]])
    assert batch["input_ids"].shape[0] == 2
    assert batch["input_ids"].shape[1] <= length
    token_shapes[str(length)] = list(batch["input_ids"].shape)

result = {"verified": True, "partitions": manifest["partition_counts"],
          "token_lengths": list(VALID_LENGTHS), "sample_batch_shapes": token_shapes,
          "test_predictions_or_metrics_computed": False}
with (DATA / "verification.json").open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps(result, ensure_ascii=False))
