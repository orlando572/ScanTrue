"""Find cross-split near-copy candidates using shared five-word shingles."""
import csv
import re
from collections import Counter, defaultdict

from step2_audit_bilstm import SRC, OUT, SPLITS, body, norm

rows = []
for split in SPLITS:
    with (SRC / f"{split}.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows.extend({**r, "split": split} for r in csv.DictReader(handle))

texts = [body(r) for r in rows]
shingles = []
index = defaultdict(list)
for i, value in enumerate(texts):
    words = re.findall(r"\w+", value[:1500], re.UNICODE)
    grams = set(zip(words, words[1:], words[2:], words[3:], words[4:]))
    shingles.append(grams)
    for gram in grams:
        index[gram].append(i)

hits = {}
for i, a in enumerate(rows):
    counts = Counter()
    for gram in shingles[i]:
        postings = index[gram]
        if len(postings) <= 20:
            counts.update(j for j in postings if j > i and rows[j]["split"] != a["split"])
    for j, shared in counts.items():
        smaller = min(len(shingles[i]), len(shingles[j]))
        score = shared / smaller if smaller else 0
        if shared < 5 or score < .65:
            continue
        b = rows[j]
        hits[(i, j)] = {"method": "5word_shingle_containment_first1500", "score": round(score, 4),
                        "shared_shingles": shared, "split_a": a["split"], "id_a": a["id"],
                        "label_a": a["etiqueta"], "source_a": a["dataset"],
                        "split_b": b["split"], "id_b": b["id"],
                        "label_b": b["etiqueta"], "source_b": b["dataset"]}

# Normalize once before checking whether a short residual occurs in a longer article.
full_norm = [norm(r["texto"]) for r in rows]
short = [i for i, r in enumerate(rows) if r["dataset"] == "usmsc_edds_residual"
         and r["split"] == "entrenamiento" and len(full_norm[i]) >= 120]
other = [j for j, r in enumerate(rows) if r["split"] != "entrenamiento"]
for i in short:
    prefix = full_norm[i][:120]
    for j in other:
        if len(full_norm[j]) < len(full_norm[i]) or prefix not in full_norm[j]:
            continue
        a, b = rows[i], rows[j]
        hits[(i, j)] = {"method": "usmsc_prefix_120_contained", "score": 1.0,
                        "shared_shingles": "", "split_a": a["split"], "id_a": a["id"],
                        "label_a": a["etiqueta"], "source_a": a["dataset"],
                        "split_b": b["split"], "id_b": b["id"],
                        "label_b": b["etiqueta"], "source_b": b["dataset"]}

hits = sorted(hits.values(), key=lambda r: (-r["score"], r["id_a"], r["id_b"]))
fields = ["method", "score", "shared_shingles", "split_a", "id_a", "label_a", "source_a",
          "split_b", "id_b", "label_b", "source_b"]
with (OUT / "near_body_candidates.csv").open("x", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(hits)
print({"pairs": len(hits), "methods": dict(Counter(r["method"] for r in hits)),
       "conflicting_labels": sum(r["label_a"] != r["label_b"] for r in hits)})
