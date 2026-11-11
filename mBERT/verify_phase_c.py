"""Independent integrity check of the frozen Phase C manifests."""

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "datasets" / "processed" / "phase_b_20261007_v1" / "normalized_all.jsonl.gz"
OUT = ROOT / "datasets" / "processed" / "phase_c_seed42_v1"
manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == manifest["source_sha256"]
with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
    records = {row["id"]: row for row in map(json.loads, handle)}
with (OUT / "decisions.csv").open(encoding="utf-8-sig", newline="") as handle:
    decisions = list(csv.DictReader(handle))
assert len(decisions) == len(records)
assert len({decision["id"] for decision in decisions}) == len(records)
assert {decision["id"] for decision in decisions} == set(records)
assert dict(sorted(Counter(decision["partition"] for decision in decisions).items())) == manifest["partitions"]

by_partition = defaultdict(set)
by_component = defaultdict(set)
for decision in decisions:
    record = records[decision["id"]]
    assert int(decision["label"]) == record["etiqueta_binaria"]
    assert decision["dataset"] == record["dataset"]
    assert decision["source_split"] == record["split_origen"]
    by_partition[decision["partition"]].add(decision["id"])
    if decision["partition"] not in {"excluded", "es_test_quarantine"}:
        by_component[decision["component_id"]].add(decision["partition"])
assert all(len(partitions) == 1 for partitions in by_component.values())

for partition, ids in by_partition.items():
    if partition == "excluded":
        continue
    stored = (OUT / f"{partition}_ids.txt").read_text(encoding="utf-8").splitlines()
    assert len(stored) == len(set(stored)) == len(ids)
    assert set(stored) == ids

assert all(records[key]["dataset"] == "spanish_v2" for key in by_partition["es_test_main"])
assert all(records[key]["dataset"] == "spanish_v1" for key in by_partition["es_train"] | by_partition["es_validation"])
assert all(records[key]["dataset"] == "isot" for key in by_partition["en_train"] | by_partition["en_validation"])
assert all(records[key]["dataset"] == "perez_rosas_2018" for key in by_partition["en_test_perez_rosas"])
assert all(records[key]["dataset"] == "polyglot_v2" and records[key]["idioma_original"] == "es"
           for key in by_partition["es_test_polyglot_stress"])

summary = {
    "verified": True,
    "source_sha256": manifest["source_sha256"],
    "records_accounted_for": len(decisions),
    "partition_counts": manifest["partitions"],
    "active_components_spanning_partitions": sum(len(parts) > 1 for parts in by_component.values()),
    "test_main_support": manifest["by_partition_label"]["es_test_main"],
}
with (OUT / "verification.json").open("x", encoding="utf-8") as handle:
    json.dump(summary, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps(summary, ensure_ascii=False))
