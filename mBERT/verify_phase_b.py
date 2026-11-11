"""Read-only consistency checks for the versioned Phase B output."""

import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "datasets" / "processed" / "phase_b_20261007_v1"
rows = []
with gzip.open(OUT / "normalized_all.jsonl.gz", "rt", encoding="utf-8") as source:
    for line in source:
        rows.append(json.loads(line))

ids = [row["id"] for row in rows]
assert len(ids) == len(set(ids)), "Duplicate record IDs"
assert all(row["etiqueta_binaria"] in (0, 1) for row in rows)
assert all(row["idioma_original"] in ("es", "en") for row in rows)
assert all(row["texto_modelo"] for row in rows)
assert all(row["hash_texto_exacto"] for row in rows)
assert all(row["archivo_origen"] and row["fila_origen"] for row in rows)

report = json.loads((OUT / "quality_report.json").read_text(encoding="utf-8"))
assert len(rows) == report["total_records"]
assert dict(Counter(row["dataset"] for row in rows)) == report["source_counts"]
assert dict(Counter(flag for row in rows for flag in row["flags_revision"])) == report["flags"]

groups = defaultdict(list)
urls = defaultdict(list)
for row in rows:
    groups[row["hash_texto_exacto"]].append(row)
    if row["url_normalizada"]:
        urls[row["url_normalizada"]].append(row)
assert all(row["tamano_grupo_texto_exacto"] == len(groups[row["hash_texto_exacto"]]) for row in rows)
assert all(row["tamano_grupo_url"] == len(urls[row["url_normalizada"]]) for row in rows if row["url_normalizada"])

cross_label = [group for group in groups.values() if len({row["etiqueta_binaria"] for row in group}) > 1]
cross_dataset = [group for group in groups.values() if len({row["dataset"] for row in group}) > 1]
cross_original_split = [group for group in groups.values() if
    len({(row["dataset"], row["split_origen"]) for row in group}) > 1]
url_cross_label = [group for group in urls.values() if len({row["etiqueta_binaria"] for row in group}) > 1]

with (OUT / "near_title_candidates.csv").open(encoding="utf-8", newline="") as source:
    candidates = list(csv.DictReader(source))
assert len(candidates) == report["near_title_candidate_pairs"]
id_map = {row["id"]: row for row in rows}
assert all(pair["id_1"] in id_map and pair["id_2"] in id_map for pair in candidates)
near_cross_label = [pair for pair in candidates if pair["misma_etiqueta"] == "False"]
near_cross_split = [pair for pair in candidates if
    (pair["dataset_1"], pair["split_1"]) != (pair["dataset_2"], pair["split_2"])]

word_stats = {}
for dataset in sorted({row["dataset"] for row in rows}):
    lengths = sorted(len(row["texto_modelo"].split()) for row in rows if row["dataset"] == dataset)
    word_stats[dataset] = {
        "min": lengths[0], "median": median(lengths),
        "p90": lengths[int(0.9 * (len(lengths) - 1))],
        "p99": lengths[int(0.99 * (len(lengths) - 1))], "max": lengths[-1],
    }

summary = {
    "checked_records": len(rows), "unique_ids": len(set(ids)),
    "exact_cross_label_groups": len(cross_label),
    "exact_cross_label_examples": [
        [{"id": row["id"], "dataset": row["dataset"], "split": row["split_origen"],
          "label": row["etiqueta_binaria"], "title": row["titular"][:100]} for row in group[:5]]
        for group in cross_label[:15]
    ],
    "exact_cross_dataset_groups": len(cross_dataset),
    "exact_cross_original_split_groups": len(cross_original_split),
    "spanish_v1_train_development_duplicate_groups": sum(
        {("spanish_v1", "train"), ("spanish_v1", "development")}.issubset(
            {(row["dataset"], row["split_origen"]) for row in group}
        ) for group in groups.values()
    ),
    "spanish_v1_v2_duplicate_groups": sum(
        {"spanish_v1", "spanish_v2"}.issubset({row["dataset"] for row in group})
        for group in groups.values()
    ),
    "url_cross_label_groups": len(url_cross_label),
    "near_cross_label_pairs": len(near_cross_label),
    "near_cross_original_split_pairs": len(near_cross_split),
    "near_spanish_v1_v2_pairs": sum(
        {pair["dataset_1"], pair["dataset_2"]} == {"spanish_v1", "spanish_v2"}
        for pair in candidates
    ),
    "word_lengths": word_stats,
    "source_label_counts": {
        corpus: dict(Counter(str(row["etiqueta_binaria"]) for row in rows if row["dataset"] == corpus))
        for corpus in sorted({row["dataset"] for row in rows})
    },
}
target = OUT / "verification_report.json"
with target.open("x", encoding="utf-8") as handle:
    json.dump(summary, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
