"""Descriptive analysis of frozen Phase F predictions; no model changes."""

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

from phase_d_data import ROOT, load_rows


HERE = Path(__file__).resolve().parent
OUT = HERE / "evaluations" / "phase_f_20261007_v1"
PLAN = json.loads((HERE / "phase_f_plan_20261007_v1.json").read_text(encoding="utf-8"))
SOURCE = ROOT / "datasets" / "processed" / "phase_b_20261007_v1" / "normalized_all.jsonl.gz"
parts = {p: load_rows(p) for p in ["es_train", *PLAN["partitions"]]}
ids = {r["id"] for rows in parts.values() for r in rows}
meta = {}
with gzip.open(SOURCE, "rt", encoding="utf-8") as f:
    for line in f:
        row = json.loads(line)
        if row["id"] in ids:
            meta[row["id"]] = row
assert ids <= meta.keys()

audit = list(csv.DictReader((OUT / "selected_audit.csv").open(encoding="utf-8", newline="")))
train_sources = {(meta[r["id"]].get("fuente") or "").strip().casefold() for r in parts["es_train"]}
train_sources.discard("")
groups = defaultdict(list)
errors = []
for r in audit:
    m = meta[r["id"]]
    date = str(m.get("fecha_publicacion") or m.get("fecha_publicacion_original") or "")
    year = date[:4] if len(date) >= 4 and date[:4].isdigit() else "sin fecha"
    source = str(m.get("fuente") or "").strip()
    known = "conocida" if source.casefold() in train_sources else "nueva/sin fuente"
    words = int(r["word_count"])
    length = "<200" if words < 200 else "200-499" if words < 500 else "500-999" if words < 1000 else ">=1000"
    r.update({"period": year, "source_status": known, "length_bin": length,
              "text_type": m.get("tipo_texto") or "sin tipo"})
    for category, value in [("dataset", r["dataset"]), ("fuente", source or "sin fuente"),
                            ("tema", r["topic"]), ("periodo", year), ("longitud_palabras", length),
                            ("tipo_texto", r["text_type"]), ("fuente_entrenamiento", known),
                            ("entrada", r["input_mode"])]:
        groups[(r["partition"], category, value)].append(r)
    if r["partition"] == "es_test_main" and r["true"] != r["predicted"]:
        errors.append({"id": r["id"], "fuente": source, "tema": r["topic"],
                       "anio": year, "palabras": words, "real": r["true"],
                       "predicho": r["predicted"], "prob_falsa": r["prob_fake"],
                       "tipo": "FP" if r["true"] == "0" else "FN"})

with (OUT / "subgroups.csv").open("x", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["partition", "category", "value", "n", "real", "fake", "fp", "fn",
                     "fake_precision", "fake_recall", "fake_f1", "accuracy"])
    for (part, category, value), rows in sorted(groups.items()):
        real = sum(r["true"] == "0" for r in rows)
        fake = len(rows) - real
        tp = sum(r["true"] == "1" and r["predicted"] == "1" for r in rows)
        fp = sum(r["true"] == "0" and r["predicted"] == "1" for r in rows)
        fn = sum(r["true"] == "1" and r["predicted"] == "0" for r in rows)
        tn = real - fp
        p = tp / (tp + fp) if tp + fp else 0
        rec = tp / fake if fake else 0
        f1 = 2 * p * rec / (p + rec) if p + rec else 0
        writer.writerow([part, category, value, len(rows), real, fake, fp, fn,
                         p, rec, f1, (tp + tn) / len(rows)])

errors.sort(key=lambda r: float(r["prob_falsa"]), reverse=True)
with (OUT / "main_errors.csv").open("x", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(errors[0]))
    writer.writeheader()
    writer.writerows(errors)

with (OUT / "source_overlap.json").open("x", encoding="utf-8") as f:
    json.dump({"train_distinct_sources": len(train_sources),
               "test_main_known_source_count": sum(r["partition"] == "es_test_main" and r["source_status"] == "conocida" for r in audit),
               "test_main_new_source_count": sum(r["partition"] == "es_test_main" and r["source_status"] != "conocida" for r in audit),
               "note": "Exact casefolded source-name overlap only; source aliases are possible."}, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("DONE", len(groups), "subgroups", len(errors), "main-test errors")
