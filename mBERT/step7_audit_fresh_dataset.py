"""Pre-score integrity and leakage audit for a user-supplied final Spanish news set.

Does not load or run any model. Manual semantic/event review remains mandatory.
"""
import argparse
import csv
import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUT_PARENT = ROOT / "mBERT/final_test_step7/audits"
OLD = ROOT / "datasets/processed/phase_b_20261007_v1/normalized_all.jsonl.gz"
BILSTM = ROOT / "modelo bilstm"
SPLITS = ("entrenamiento", "validacion", "prueba", "externa")
FIELDS = ("id", "title", "body", "label", "source", "url", "published_date", "topic",
          "event_id", "evidence_url", "rights_basis", "reviewed_by", "review_status")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def norm(text):
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def norm_url(url):
    if not url:
        return ""
    parsed = urlsplit(url.strip())
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold().removeprefix("www."),
                       parsed.path.rstrip("/"), "", ""))


def known_history():
    history = {"text": defaultdict(list), "title": defaultdict(list), "url": defaultdict(list)}
    with gzip.open(OLD, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("idioma_original") not in ("es", "spanish", "español") and row.get("dataset") in ("isot", "perez_rosas_2018"):
                continue
            ref = "old:" + str(row["id"])
            for key, value in (("text", row.get("texto_modelo") or row.get("cuerpo")),
                               ("title", row.get("titular")), ("url", row.get("url"))):
                keyvalue = norm_url(value) if key == "url" else norm(value)
                if keyvalue:
                    history[key][keyvalue].append(ref)
    for split in SPLITS:
        with (BILSTM / f"{split}.csv").open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                ref = f"bilstm:{split}:{row['id']}"
                for key, value in (("text", row["texto"]), ("title", row["titulo"]), ("url", row["url"])):
                    keyvalue = norm_url(value) if key == "url" else norm(value)
                    if keyvalue:
                        history[key][keyvalue].append(ref)
    return history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="CSV nuevo con columnas de plantilla_noticias.csv")
    args = parser.parse_args()
    candidate = args.csv_path.resolve(strict=True)
    assert candidate.suffix.casefold() == ".csv"
    with candidate.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == list(FIELDS), f"Required columns and order: {FIELDS}"
        rows = list(reader)
    assert rows, "The CSV is empty"
    seen = set()
    seen_text = set()
    seen_url = set()
    issues = []
    labels = Counter()
    media = defaultdict(set)
    topics = set()
    lengths = Counter()
    dates = []
    for i, row in enumerate(rows, start=2):
        for field in FIELDS:
            if not (row.get(field) or "").strip():
                issues.append({"line": i, "id": row.get("id"), "kind": "empty_required_field", "field": field})
        ident = row.get("id", "")
        if ident in seen:
            issues.append({"line": i, "id": ident, "kind": "duplicate_id"})
        seen.add(ident)
        content_key = norm(row.get("title", "") + " " + row.get("body", ""))
        if content_key in seen_text:
            issues.append({"line": i, "id": ident, "kind": "duplicate_candidate_text"})
        seen_text.add(content_key)
        url_key = norm_url(row.get("url", ""))
        if url_key in seen_url:
            issues.append({"line": i, "id": ident, "kind": "duplicate_candidate_url"})
        seen_url.add(url_key)
        if row.get("label") not in ("0", "1"):
            issues.append({"line": i, "id": ident, "kind": "invalid_label"})
        else:
            labels[row["label"]] += 1
            media[row["label"]].add(norm(row.get("source")))
        if row.get("review_status") != "approved":
            issues.append({"line": i, "id": ident, "kind": "not_approved"})
        try:
            dates.append(date.fromisoformat(row.get("published_date", "")))
        except ValueError:
            issues.append({"line": i, "id": ident, "kind": "invalid_date"})
        if not urlsplit(row.get("url", "")).netloc:
            issues.append({"line": i, "id": ident, "kind": "invalid_url"})
        if not urlsplit(row.get("evidence_url", "")).netloc:
            issues.append({"line": i, "id": ident, "kind": "invalid_evidence_url"})
        topics.add(norm(row.get("topic")))
        words = len(row.get("body", "").split())
        lengths["lt200" if words < 200 else "200_499" if words < 500 else "ge500"] += 1
        if words < 80:
            issues.append({"line": i, "id": ident, "kind": "body_under_80_words", "words": words})
    history = known_history()
    collisions = []
    for row in rows:
        combined = (row["title"] + " " + row["body"]).strip()
        values = {"text": [norm(combined), norm(row["body"])],
                  "title": [norm(row["title"])], "url": [norm_url(row["url"])]}
        for kind, candidates in values.items():
            for value in set(candidates):
                if value in history[kind]:
                    collisions.append({"id": row["id"], "kind": kind,
                                       "historical_refs": history[kind][value][:20],
                                       "historical_match_count": len(history[kind][value])})
    gate = {"at_least_100_per_class": all(labels[str(i)] >= 100 for i in (0, 1)),
            "at_least_3_media_per_class": all(len(media[str(i)]) >= 3 for i in (0, 1)),
            "at_least_4_topics": len(topics - {""}) >= 4,
            "all_3_length_bands": all(lengths[k] > 0 for k in ("lt200", "200_499", "ge500")),
            "no_schema_or_quality_issues": not issues,
            "no_exact_historical_collisions": not collisions,
            "manual_event_review_completed": False}
    result = {"status": "not_ready_for_scoring_manual_event_review_required",
              "candidate_path": str(candidate), "candidate_sha256": sha(candidate),
              "history_sha256": {"phase_b": sha(OLD), **{split: sha(BILSTM / f"{split}.csv") for split in SPLITS}},
              "rows": len(rows), "labels_0_REAL_1_FALSA": dict(labels),
              "media_by_class": {k: len(v) for k, v in media.items()},
              "topics": len(topics - {""}), "length_bands": dict(lengths),
              "date_min": str(min(dates)) if dates else None, "date_max": str(max(dates)) if dates else None,
              "issues": issues, "exact_collisions": collisions, "gates": gate,
              "limits": "Exact text/title/URL checks do not establish event independence or label correctness. Human review and a frozen event decision file are mandatory before model scoring."}
    OUT_PARENT.mkdir(parents=True, exist_ok=True)
    out = OUT_PARENT / (candidate.stem + "_" + uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    (out / "pre_score_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"audit": str(out / "pre_score_audit.json"), "rows": len(rows),
                      "issues": len(issues), "exact_collisions": len(collisions),
                      "ready_for_scoring": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
