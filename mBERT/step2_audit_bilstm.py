"""Step 2: audit cross-split leakage, old-mBERT exposure, source bias, and exclusions."""

import csv
import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


ROOT = Path(__file__).resolve().parents[1]
STEP1 = ROOT / "datasets/processed/mbert_bilstm_step1_20261008_v1"
OUT = ROOT / "datasets/processed/mbert_bilstm_step2_20261008_v1"
SRC = ROOT / "modelo bilstm"
OLD_ROWS = ROOT / "datasets/processed/phase_b_20261007_v1/normalized_all.jsonl.gz"
OLD_DECISIONS = ROOT / "datasets/processed/phase_c_seed42_v1/decisions.csv"
SPLITS = ("entrenamiento", "validacion", "prueba", "externa")
SATIRE_DOMAINS = {"eldizque.com", "elruinaversal.com", "lavozpopular.com", "elmundotoday.com"}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value or "").casefold()).strip()


def host(url):
    return (urlsplit(url or "").hostname or "").casefold().removeprefix("www.")


def body(row):
    text, title = norm(row["texto"]), norm(row["titulo"])
    return text[len(title):].strip() if title and text.startswith(title) else text


def write_csv(path, rows, fields):
    with path.open("x", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    manifest = json.loads((STEP1 / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["gate_step1"] == "pass"
    for split in SPLITS:
        assert sha(SRC / f"{split}.csv") == manifest["partitions"][split]["sha256"]
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []
    for split in SPLITS:
        with (SRC / f"{split}.csv").open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                row["split"] = split
                rows.append(row)
    assert len({row["id"] for row in rows}) == len(rows)

    # Exact cross-split keys; no raw article text is written to reports.
    key_map = defaultdict(lambda: defaultdict(set))
    for row in rows:
        vals = {"id": row["id"], "group": row["grupo_duplicados"],
                "url": norm(row["url"]), "full_text": norm(row["texto"]),
                "body": body(row), "title": norm(row["titulo"])}
        for kind, value in vals.items():
            if value:
                key_map[kind][value].add((row["split"], row["id"], row["etiqueta"]))
    exact = {}
    cross_rows = []
    for kind, entries in key_map.items():
        crossing = [(key, items) for key, items in entries.items()
                    if len({item[0] for item in items}) > 1]
        exact[kind] = {"crossing_keys": len(crossing),
                       "involved_rows": len({r[1] for _, items in crossing for r in items}),
                       "conflicting_label_keys": sum(len({r[2] for r in items}) > 1 for _, items in crossing)}
        for key, items in crossing:
            for split, row_id, label in sorted(items):
                cross_rows.append({"kind": kind, "key_sha256": hashlib.sha256(key.encode()).hexdigest(),
                                   "split": split, "id": row_id, "label_bilstm": label})
    write_csv(OUT / "exact_cross_split.csv", cross_rows,
              ["kind", "key_sha256", "split", "id", "label_bilstm"])

    # High lexical similarity in titles provides a reproducible review queue,
    # not proof that two different articles are the same event.
    titled = [row for row in rows if len(norm(row["titulo"])) >= 25]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=1,
                                 dtype=np.float32, norm="l2")
    matrix = vectorizer.fit_transform(norm(row["titulo"]) for row in titled)
    near = []
    for start in range(0, len(titled), 100):
        scores = (matrix[start:start + 100] @ matrix.T).tocsr()
        for local in range(scores.shape[0]):
            i = start + local
            for j, value in zip(scores.indices[scores.indptr[local]:scores.indptr[local + 1]],
                                scores.data[scores.indptr[local]:scores.indptr[local + 1]]):
                if j <= i or titled[i]["split"] == titled[j]["split"] or value < 0.85:
                    continue
                a, b = titled[i], titled[j]
                near.append({"split_a": a["split"], "id_a": a["id"],
                             "label_a": a["etiqueta"], "split_b": b["split"],
                             "id_b": b["id"], "label_b": b["etiqueta"],
                             "title_similarity": round(float(value), 4),
                             "same_group": a["grupo_duplicados"] == b["grupo_duplicados"],
                             "same_url": bool(a["url"]) and norm(a["url"]) == norm(b["url"])})
    near.sort(key=lambda x: -x["title_similarity"])
    write_csv(OUT / "near_title_cross_split.csv", near,
              ["split_a", "id_a", "label_a", "split_b", "id_b", "label_b",
               "title_similarity", "same_group", "same_url"])

    # Rebuild old mBERT partition identity from phase B + phase C. Only Spanish
    # partitions can match these Spanish inputs; URL is available here unlike D.
    with OLD_DECISIONS.open("r", encoding="utf-8-sig", newline="") as stream:
        old_part = {r["id"]: r["partition"] for r in csv.DictReader(stream)}
    old_keys = defaultdict(lambda: defaultdict(set))
    with gzip.open(OLD_ROWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            old = json.loads(line)
            part = old_part.get(old["id"], "")
            if not part.startswith("es_"):
                continue
            for kind, key in {"url": norm(old.get("url_normalizada", "")),
                              "title": norm(old.get("titular", "")),
                              "body": norm(old.get("cuerpo", "")),
                              "full_text": norm(old.get("texto_modelo", ""))}.items():
                if key:
                    old_keys[kind][key].add((part, old["id"], str(old["etiqueta_binaria"])))
    old_matches = []
    exposed = defaultdict(set)
    exposure_kinds = defaultdict(set)
    old_counts = defaultdict(Counter)
    for row in rows:
        keys = {"url": norm(row["url"]), "title": norm(row["titulo"]),
                "body": body(row), "full_text": norm(row["texto"])}
        matched = set()
        for kind, key in keys.items():
            if key:
                for part, old_id, old_label in old_keys[kind].get(key, ()):
                    matched.add((part, old_id, old_label, kind))
                    if part in ("es_train", "es_validation"):
                        exposed[row["id"]].add(part)
                        exposure_kinds[row["id"]].add(kind)
        for part in {m[0] for m in matched}:
            old_counts[row["split"]][part] += 1
        for part, old_id, old_label, kind in sorted(matched):
            old_matches.append({"split_new": row["split"], "id_new": row["id"],
                                "label_bilstm": row["etiqueta"], "old_partition": part,
                                "old_id": old_id, "old_label_mbert": old_label,
                                "label_agrees_after_inversion": str(1-int(row["etiqueta"])) == old_label,
                                "match_kind": kind})
    write_csv(OUT / "old_mbert_matches.csv", old_matches,
              ["split_new", "id_new", "label_bilstm", "old_partition", "old_id",
               "old_label_mbert", "label_agrees_after_inversion", "match_kind"])

    # A frozen *policy* and exact IDs for the four site-confirmed satire sources.
    exclusions = []
    for row in rows:
        domain = host(row["url"])
        if domain in SATIRE_DOMAINS:
            exclusions.append({"split": row["split"], "id": row["id"],
                               "label_bilstm": row["etiqueta"], "domain": domain,
                               "decision": "exclude_primary", "reason": "source_declares_satire"})
    write_csv(OUT / "exclusions_primary.csv", exclusions,
              ["split", "id", "label_bilstm", "domain", "decision", "reason"])
    exclude_ids = {row["id"] for row in exclusions}
    retained = {}
    for split in SPLITS:
        ids = sorted(row["id"] for row in rows if row["split"] == split and row["id"] not in exclude_ids)
        (OUT / f"{split}_retained_ids.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
        retained[split] = {"rows": len(ids), "ids_sha256": sha(OUT / f"{split}_retained_ids.txt"),
                           "labels_bilstm": dict(Counter(row["etiqueta"] for row in rows
                                                       if row["split"] == split and row["id"] not in exclude_ids))}

    by_source = defaultdict(lambda: {"n": 0, "labels": Counter(), "word_lengths": [], "char_lengths": []})
    by_domain = defaultdict(Counter)
    for row in rows:
        item = by_source[(row["split"], row["dataset"])]
        item["n"] += 1
        item["labels"][row["etiqueta"]] += 1
        item["word_lengths"].append(len(row["texto"].split()))
        item["char_lengths"].append(len(row["texto"]))
        if host(row["url"]):
            by_domain[(row["split"], host(row["url"]))][row["etiqueta"]] += 1
    sources = {f"{part}|{source}": {"rows": v["n"], "labels": dict(v["labels"]),
                                     "median_words": float(np.median(v["word_lengths"])),
                                     "median_chars": float(np.median(v["char_lengths"]))}
               for (part, source), v in sorted(by_source.items())}
    domain_bias = {split: {"with_url": sum(sum(c.values()) for (s, _), c in by_domain.items() if s == split),
                           "single_label_domains": sum(len(c) == 1 for (s, _), c in by_domain.items() if s == split),
                           "rows_single_label_domains": sum(sum(c.values()) for (s, _), c in by_domain.items()
                                                            if s == split and len(c) == 1)} for split in SPLITS}
    result = {
        "step1_manifest_sha256": sha(STEP1 / "manifest.json"),
        "step2_code_sha256": sha(Path(__file__)),
        "input_sha256": {s: sha(SRC / f"{s}.csv") for s in SPLITS},
        "exact_cross_split": exact,
        "near_title_cross_split_pairs_ge_0_85": len(near),
        "near_title_conflicting_labels": sum(x["label_a"] != x["label_b"] for x in near),
        "old_mbert_match_rows_by_new_split_and_old_partition": {s: dict(c) for s, c in old_counts.items()},
        "old_mbert_exposure_es_train_or_val": {s: {"all_rows": sum(r["split"] == s for r in rows),
                                                   "exposed_exact_title_body_url_or_full": sum(
                                                       r["split"] == s and r["id"] in exposed for r in rows),
                                                   "retained_exposed": sum(r["split"] == s and
                                                       r["id"] in exposed and r["id"] not in exclude_ids for r in rows)}
                                               for s in SPLITS},
        "old_mbert_label_disagreements_on_matches": sum(x["label_agrees_after_inversion"] is False for x in old_matches),
        "satire_excluded": {s: {"rows": sum(r["split"] == s for r in exclusions),
                                "by_domain": dict(Counter(r["domain"] for r in exclusions if r["split"] == s))}
                            for s in SPLITS},
        "retained": retained, "source_length_label": sources, "domain_bias": domain_bias,
        "near_match_method": "TF-IDF title character 3-5 gram cosine >=0.85; lexical candidates only, not event-proof",
        "old_exposure_method": "NFC+casefold+whitespace exact title/body/full/url against phase B rows assigned phase C Spanish partitions",
    }
    (OUT / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("exact_cross_split", "near_title_cross_split_pairs_ge_0_85",
                                          "old_mbert_exposure_es_train_or_val", "satire_excluded", "retained")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
