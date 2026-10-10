"""Supplementary cross-split title-similarity queue for human event review."""
import csv
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from step2_audit_bilstm import ROOT, SPLITS, SRC, OUT, norm

rows = []
for split in SPLITS:
    with (SRC / f"{split}.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if len(norm(row["titulo"])) >= 25:
                rows.append({**row, "split": split})
vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), dtype=np.float32)
matrix = vectorizer.fit_transform(norm(row["titulo"]) for row in rows)
hits = []
for start in range(0, len(rows), 100):
    sim = (matrix[start:start + 100] @ matrix.T).tocsr()
    for offset in range(sim.shape[0]):
        i = start + offset
        for j, score in zip(sim.indices[sim.indptr[offset]:sim.indptr[offset + 1]],
                            sim.data[sim.indptr[offset]:sim.indptr[offset + 1]]):
            if j <= i or score < .65 or rows[i]["split"] == rows[j]["split"]:
                continue
            a, b = rows[i], rows[j]
            hits.append({"score": round(float(score), 4), "split_a": a["split"], "id_a": a["id"],
                         "label_a": a["etiqueta"], "title_a": a["titulo"],
                         "split_b": b["split"], "id_b": b["id"],
                         "label_b": b["etiqueta"], "title_b": b["titulo"]})
hits.sort(key=lambda x: -x["score"])
with (OUT / "near_title_candidates_065.csv").open("x", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(hits[0]) if hits else
                            ["score", "split_a", "id_a", "label_a", "title_a",
                             "split_b", "id_b", "label_b", "title_b"])
    writer.writeheader()
    writer.writerows(hits)
print(f"candidates={len(hits)} conflicts={sum(r['label_a'] != r['label_b'] for r in hits)}")
