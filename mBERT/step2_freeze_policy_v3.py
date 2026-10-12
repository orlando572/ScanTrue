"""Revise the frozen policy to remove training-side near copies of test rows."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/processed/mbert_bilstm_step2_20261008_v1"
SPLITS = ("entrenamiento", "validacion", "prueba", "externa")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


with (OUT / "near_body_candidates.csv").open(encoding="utf-8-sig", newline="") as handle:
    pairs = list(csv.DictReader(handle))
train_near = {row["id_a"] for row in pairs if row["split_a"] == "entrenamiento"}
assert len(train_near) == 38
with (OUT / "decisions_primary_v2.csv").open(encoding="utf-8-sig", newline="") as handle:
    decisions = list(csv.DictReader(handle))
for row in decisions:
    if row["split"] == "entrenamiento" and row["id"] in train_near:
        assert row["decision"] == "retain_primary"
        row["decision"] = "exclude_primary"
        row["reasons"] = ";".join(filter(None, [row["reasons"], "cross_split_near_copy"]))

with (OUT / "decisions_primary_v3.csv").open("x", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(decisions[0]))
    writer.writeheader()
    writer.writerows(decisions)
summary = {"policy": {
    "inherits": "policy_v2.json", "additional_training_exclusion": "38 near-copy IDs in near_body_candidates.csv",
    "preserve_eval_rows": True, "do_not_modify_original_csv": True,
    "candidate_method_limits": "five-word shingle overlap and prefix containment; semantic matches may remain",
    "mandatory_ablation_without_usmsc_residual": True,
    "near_body_candidates_sha256": sha(OUT / "near_body_candidates.csv"),
    "previous_policy_sha256": sha(OUT / "policy_v2.json"),
}, "splits": {}}
for split in SPLITS:
    included = [row for row in decisions if row["split"] == split and row["decision"] == "retain_primary"]
    excluded = [row for row in decisions if row["split"] == split and row["decision"] == "exclude_primary"]
    path = OUT / f"{split}_primary_v3_ids.txt"
    path.write_text("\n".join(sorted(row["id"] for row in included)) + "\n", encoding="utf-8")
    summary["splits"][split] = {
        "included": len(included), "excluded": len(excluded),
        "included_labels_bilstm": dict(Counter(row["label_bilstm"] for row in included)),
        "excluded_by_reason": dict(Counter(reason for row in excluded
                                           for reason in row["reasons"].split(";") if reason)),
        "ids_sha256": sha(path),
    }
summary["decisions_sha256"] = sha(OUT / "decisions_primary_v3.csv")
summary["code_sha256"] = sha(Path(__file__))
(OUT / "policy_v3.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary["splits"], ensure_ascii=False))
