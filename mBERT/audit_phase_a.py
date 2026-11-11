"""Read-only inventory of the original Phase A archives and workbooks.

Run with a Python that has openpyxl installed. This script never extracts,
normalizes, or modifies the source files. Output is an exclusive-create JSON.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "datasets" / "raw"
OUT = ROOT / "datasets" / "audit" / "phase_a_inventory_20261007_v2.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_fingerprint(value: object) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "").casefold()).strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def audit_sheet(source: str, workbook) -> tuple[dict, set[str]]:
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    headers = [str(x or "").strip() for x in next(rows)]
    index = {name.casefold(): i for i, name in enumerate(headers) if name}

    def cell(row: tuple, *names: str) -> object:
        for name in names:
            pos = index.get(name.casefold())
            if pos is not None and pos < len(row):
                return row[pos]
        return None

    labels: Counter = Counter()
    languages: Counter = Counter()
    missing_title = missing_body = missing_both = 0
    fingerprints: set[str] = set()
    row_count = 0
    for row in rows:
        if not any(value is not None for value in row):
            continue
        row_count += 1
        label = cell(row, "category", "label")
        language = cell(row, "language")
        title = cell(row, "headline", "news headline")
        body = cell(row, "text", "news original text")
        labels[str(label).strip() if label is not None else "<empty>"] += 1
        if "language" in index:
            languages[str(language).strip() if language is not None else "<empty>"] += 1
        no_title = not str(title or "").strip()
        no_body = not str(body or "").strip()
        missing_title += no_title
        missing_body += no_body
        missing_both += no_title and no_body
        fingerprint = text_fingerprint(body or title)
        if fingerprint:
            fingerprints.add(fingerprint)

    return (
        {
            "source": source,
            "rows": row_count,
            "headers": headers,
            "labels": dict(labels),
            "languages": dict(languages),
            "missing_title": missing_title,
            "missing_body": missing_body,
            "missing_both": missing_both,
            "unique_exact_text": len(fingerprints),
        },
        fingerprints,
    )


def main() -> None:
    result: dict = {"files": {}, "sheets": {}, "overlaps_exact_text": {}}
    fingerprints: dict[str, set[str]] = {}

    spanish_zip = next((RAW / "FakeNewsCorpusSpanish").glob("*.zip"))
    isot_zip = next((RAW / "ISOT").glob("*.zip"))
    perez_zip = next((RAW / "PerezRosas2018").glob("*.zip"))
    for path in (spanish_zip, isot_zip, perez_zip):
        result["files"][str(path.relative_to(ROOT))] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    with zipfile.ZipFile(spanish_zip) as archive:
        for member in archive.namelist():
            if member.endswith(".xlsx"):
                workbook = openpyxl.load_workbook(
                    io.BytesIO(archive.read(member)), read_only=True, data_only=True
                )
                name = "Spanish/" + Path(member).name
                result["sheets"][name], fingerprints[name] = audit_sheet(name, workbook)
                workbook.close()

    with zipfile.ZipFile(isot_zip) as archive:
        for member in ("True.csv", "Fake.csv"):
            with io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                count = missing_title = missing_body = missing_both = 0
                unique: set[str] = set()
                for row in reader:
                    count += 1
                    title, body = row.get("title", ""), row.get("text", "")
                    no_title, no_body = not title.strip(), not body.strip()
                    missing_title += no_title
                    missing_body += no_body
                    missing_both += no_title and no_body
                    fingerprint = text_fingerprint(body or title)
                    if fingerprint:
                        unique.add(fingerprint)
                name = "ISOT/" + member
                result["sheets"][name] = {
                    "source": name,
                    "rows": count,
                    "headers": reader.fieldnames,
                    "labels": {"REAL" if member == "True.csv" else "FAKE": count},
                    "missing_title": missing_title,
                    "missing_body": missing_body,
                    "missing_both": missing_both,
                    "unique_exact_text": len(unique),
                }
                fingerprints[name] = unique

    with zipfile.ZipFile(perez_zip) as archive:
        groups: Counter = Counter()
        for member in archive.namelist():
            if member.endswith(".txt"):
                parts = Path(member).parts
                if len(parts) > 2:
                    groups["/".join(parts[1:3])] += 1
        result["sheets"]["PerezRosas2018/txt"] = {
            "files_txt": sum(groups.values()),
            "groups": dict(groups),
        }

    poly_dir = RAW / "PolyglotFakeFacts_v2"
    for path in sorted(poly_dir.glob("*.xlsx")):
        result["files"][str(path.relative_to(ROOT))] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        name = "Polyglot/" + path.name
        result["sheets"][name], fingerprints[name] = audit_sheet(name, workbook)
        workbook.close()

    comparisons = [
        ("Spanish/train.xlsx", "Spanish/development.xlsx"),
        ("Spanish/train.xlsx", "Spanish/test.xlsx"),
        ("Spanish/development.xlsx", "Spanish/test.xlsx"),
        ("ISOT/True.csv", "ISOT/Fake.csv"),
        ("Polyglot/20.xlsx", "Polyglot/80.xlsx"),
        ("Polyglot/Fake.xlsx", "Polyglot/Real.xlsx"),
        ("Polyglot/20.xlsx", "Polyglot/Fake.xlsx"),
        ("Polyglot/20.xlsx", "Polyglot/Real.xlsx"),
        ("Polyglot/80.xlsx", "Polyglot/Fake.xlsx"),
        ("Polyglot/80.xlsx", "Polyglot/Real.xlsx"),
        ("Spanish/train.xlsx", "Polyglot/Fake.xlsx"),
        ("Spanish/train.xlsx", "Polyglot/Real.xlsx"),
        ("Spanish/test.xlsx", "Polyglot/Fake.xlsx"),
        ("Spanish/test.xlsx", "Polyglot/Real.xlsx"),
    ]
    for left, right in comparisons:
        result["overlaps_exact_text"][f"{left} <> {right}"] = len(
            fingerprints[left] & fingerprints[right]
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(OUT)


if __name__ == "__main__":
    sys.exit(main())
