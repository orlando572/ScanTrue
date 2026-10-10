"""Check BiLSTM Polyglot records against the downloaded v2 source spreadsheets."""
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "modelo bilstm"
OUT = ROOT / "datasets/processed/mbert_bilstm_step2_20261008_v1"
SPLITS = ("entrenamiento", "validacion", "prueba", "externa")


def norm(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value or "").casefold()).strip()

raw = defaultdict(list)
for filename, label in (("Fake.xlsx", "0"), ("Real.xlsx", "1")):
    workbook = openpyxl.load_workbook(ROOT / "datasets/raw/PolyglotFakeFacts_v2" / filename,
                                       read_only=True, data_only=True)
    for row in workbook.active.iter_rows(min_row=2, values_only=True):
        if not row[6]:
            continue
        raw[norm(str(row[6]))].append({"label": label, "language": norm(str(row[2] if label == "0" else row[4])),
                                      "url": norm(str(row[3] if label == "0" else row[2]))})

summary = Counter()
languages = Counter()
flags = []
for split in SPLITS:
    with (SRC / f"{split}.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["dataset"] != "polyglotfakefacts_v2":
                continue
            summary["rows"] += 1
            candidates = raw.get(norm(row["titulo"]), [])
            if not candidates:
                summary["no_exact_title_match"] += 1
                flags.append({"split": split, "id": row["id"], "issue": "no_exact_title_match"})
                continue
            summary["title_match"] += 1
            same_label = [x for x in candidates if x["label"] == row["etiqueta"]]
            if not same_label:
                summary["label_mismatch"] += 1
                flags.append({"split": split, "id": row["id"], "issue": "label_mismatch"})
                continue
            summary["label_match"] += 1
            original = next((x for x in same_label if x["url"] == norm(row["url"])), same_label[0])
            languages[original["language"]] += 1
            if original["url"] != norm(row["url"]):
                summary["url_changed_from_source"] += 1
                flags.append({"split": split, "id": row["id"], "issue": "url_changed_from_source"})

result = {"summary": dict(summary), "original_language_field": dict(languages),
          "method": "Exact NFC+casefold+whitespace title match to original v2 Fake.xlsx/Real.xlsx; URL and label checked."}
(OUT / "polyglot_provenance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with (OUT / "polyglot_provenance_flags.csv").open("x", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["split", "id", "issue"])
    writer.writeheader()
    writer.writerows(flags)
print(json.dumps(result, ensure_ascii=False))
