"""Final step-2 policy: exclude Hay Noticia after its own fiction disclaimer."""
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


with (OUT / "decisions_primary_v3.csv").open(encoding="utf-8-sig", newline="") as stream:
    decisions = list(csv.DictReader(stream))
changed = []
for row in decisions:
    if row["domain"] == "haynoticia.es":
        assert row["decision"] == "retain_primary"
        row["decision"] = "exclude_primary"
        row["reasons"] = "source_declares_fiction_humor"
        changed.append(row["id"])
assert len(changed) == 38
with (OUT / "decisions_primary_v4.csv").open("x", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(decisions[0]))
    writer.writeheader()
    writer.writerows(decisions)
summary = {"status": "frozen_for_step3_not_training", "policy": {
    "inherits": "policy_v3.json", "additional_exclusion_domain": "haynoticia.es",
    "basis": "https://haynoticia.es/ (Aviso legal: site de humor; content is fiction)",
    "changed_rows": len(changed), "previous_policy_sha256": sha(OUT / "policy_v3.json"),
    "do_not_modify_original_csv": True,
}, "splits": {}}
for split in SPLITS:
    included = [r for r in decisions if r["split"] == split and r["decision"] == "retain_primary"]
    excluded = [r for r in decisions if r["split"] == split and r["decision"] == "exclude_primary"]
    path = OUT / f"{split}_primary_v4_ids.txt"
    path.write_text("\n".join(sorted(r["id"] for r in included)) + "\n", encoding="utf-8")
    summary["splits"][split] = {
        "included": len(included), "excluded": len(excluded),
        "included_labels_bilstm": dict(Counter(r["label_bilstm"] for r in included)),
        "excluded_by_reason": dict(Counter(reason for r in excluded
                                           for reason in r["reasons"].split(";") if reason)),
        "ids_sha256": sha(path),
    }
summary["decisions_sha256"] = sha(OUT / "decisions_primary_v4.csv")
summary["code_sha256"] = sha(Path(__file__))
(OUT / "policy_v4.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary["splits"], ensure_ascii=False))
