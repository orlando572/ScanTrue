"""Verify the frozen v4 partition IDs and known leakage exclusions."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/processed/mbert_bilstm_step2_20261008_v1"
SRC = ROOT / "modelo bilstm"
SPLITS = ("entrenamiento", "validacion", "prueba", "externa")
policy = json.loads((OUT / "policy_v4.json").read_text(encoding="utf-8"))
with (OUT / "decisions_primary_v4.csv").open(encoding="utf-8-sig", newline="") as stream:
    decisions = list(csv.DictReader(stream))
by_id = {row["id"]: row for row in decisions}
assert len(by_id) == len(decisions) == 4021
results = {}
for split in SPLITS:
    path = OUT / f"{split}_primary_v4_ids.txt"
    file_ids = path.read_text(encoding="utf-8").splitlines()
    expected = sorted(row["id"] for row in decisions if row["split"] == split
                      and row["decision"] == "retain_primary")
    assert file_ids == expected
    assert hashlib.sha256(path.read_bytes()).hexdigest() == policy["splits"][split]["ids_sha256"]
    with (SRC / f"{split}.csv").open(encoding="utf-8-sig", newline="") as stream:
        source_ids = {row["id"] for row in csv.DictReader(stream)}
    assert {row["id"] for row in decisions if row["split"] == split} == source_ids
    results[split] = {"included": len(file_ids), "excluded": len(source_ids) - len(file_ids)}
with (OUT / "near_body_candidates.csv").open(encoding="utf-8-sig", newline="") as stream:
    near = list(csv.DictReader(stream))
remaining_near = [pair for pair in near if by_id[pair["id_a"]]["decision"] == "retain_primary"
                  and by_id[pair["id_b"]]["decision"] == "retain_primary"]
assert not remaining_near
with (OUT / "old_mbert_matches.csv").open(encoding="utf-8-sig", newline="") as stream:
    old = list(csv.DictReader(stream))
exposed = {row["id_new"] for row in old if row["old_partition"] in ("es_train", "es_validation")}
for split in ("prueba", "externa"):
    kept = [row for row in decisions if row["split"] == split and row["decision"] == "retain_primary"]
    results[split]["exposed_to_old_mbert_train_or_validation"] = sum(row["id"] in exposed for row in kept)
    results[split]["no_known_old_exposure"] = sum(row["id"] not in exposed for row in kept)
    results[split]["no_known_old_exposure_by_source"] = dict(Counter(row["dataset"] for row in kept
                                                                   if row["id"] not in exposed))
train = [row for row in decisions if row["split"] == "entrenamiento" and row["decision"] == "retain_primary"]
results["ablation_without_usmsc_train_count"] = sum(row["dataset"] != "usmsc_edds_residual" for row in train)
assert all(row["domain"] not in {"eldizque.com", "elruinaversal.com", "lavozpopular.com",
                                      "elmundotoday.com", "haynoticia.es", "twitter.com", "facebook.com",
                                      "m.facebook.com"} for row in decisions if row["decision"] == "retain_primary")
report = {"status": "pass", "known_cross_split_near_body_pairs_remaining": len(remaining_near),
          "splits": results, "limits": "Exact/lexical checks do not prove semantic independence."}
(OUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
