"""Freeze a strict article-focused filter without changing any original CSV."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "modelo bilstm"
OUT = ROOT / "datasets/processed/mbert_bilstm_step2_20261008_v1"
SPLITS = ("entrenamiento", "validacion", "prueba", "externa")
SATIRE = {"eldizque.com", "elruinaversal.com", "lavozpopular.com", "elmundotoday.com"}
SOCIAL = {"twitter.com", "x.com", "facebook.com", "m.facebook.com", "www.facebook.com", "whatsapp.com"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


decisions = []
rows = []
for split in SPLITS:
    with (SRC / f"{split}.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            domain = (urlsplit(row["url"]).hostname or "").casefold().removeprefix("www.")
            reasons = []
            if domain in SATIRE:
                reasons.append("confirmed_satire_source")
            if domain in SOCIAL or domain in {"m.facebook.com"}:
                reasons.append("direct_social_post_url")
            decision = "exclude_primary" if reasons else "retain_primary"
            item = {"split": split, "id": row["id"], "label_bilstm": row["etiqueta"],
                    "dataset": row["dataset"], "domain": domain, "decision": decision,
                    "reasons": ";".join(reasons)}
            decisions.append(item)
            rows.append(row | {"split": split, "decision": decision})

with (OUT / "decisions_primary_v2.csv").open("x", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(decisions[0]))
    writer.writeheader()
    writer.writerows(decisions)

summary = {"policy": {
    "exclude_confirmed_satire_domains": sorted(SATIRE),
    "exclude_direct_social_post_hosts": sorted(SOCIAL),
    "retain_short_usmsc_for_main_but_require_no_usmsc_ablation": True,
    "retain_haynoticia_pending_content_review": True,
    "no_label_rewriting": True,
    "source_csv_sha256": {split: sha(SRC / f"{split}.csv") for split in SPLITS},
}, "splits": {}}
for split in SPLITS:
    kept = [r for r in rows if r["split"] == split and r["decision"] == "retain_primary"]
    excluded = [r for r in rows if r["split"] == split and r["decision"] == "exclude_primary"]
    path = OUT / f"{split}_primary_v2_ids.txt"
    path.write_text("\n".join(sorted(r["id"] for r in kept)) + "\n", encoding="utf-8")
    summary["splits"][split] = {
        "original": len(kept) + len(excluded), "retained": len(kept), "excluded": len(excluded),
        "retained_labels_bilstm": dict(Counter(r["etiqueta"] for r in kept)),
        "excluded_reasons": dict(Counter(reason for r in decisions if r["split"] == split
                                         for reason in r["reasons"].split(";") if reason)),
        "ids_sha256": sha(path),
    }
summary["decisions_sha256"] = sha(OUT / "decisions_primary_v2.csv")
summary["code_sha256"] = sha(Path(__file__))
(OUT / "policy_v2.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary["splits"], ensure_ascii=False))
