"""Normalize Phase A sources without changing originals or making data splits.

Requires openpyxl for the original Excel files. Output directory is created
exclusively, so reruns cannot overwrite an earlier preparation.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import html
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import openpyxl


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "datasets" / "raw"
OUT = ROOT / "datasets" / "processed" / "phase_b_20261007_v1"
SPANISH_ZIP = next((RAW / "FakeNewsCorpusSpanish").glob("*.zip"))
ISOT_ZIP = next((RAW / "ISOT").glob("*.zip"))
PEREZ_ZIP = next((RAW / "PerezRosas2018").glob("*.zip"))
POLYGLOT = RAW / "PolyglotFakeFacts_v2"
SOCIAL_HOSTS = ("facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "whatsapp.com")
TRACKING_KEYS = {"fbclid", "gclid", "igshid", "ref", "source"}
WORD_RE = re.compile(r"\w+", re.UNICODE)
HTML_TAG_RE = re.compile(r"<[^>]{1,300}>")
LEAK_PREFIX_RE = re.compile(r"^\s*(?:fake|false|falso|falsa|real|true|verdadero|verdadera)\s*[:\-]", re.I)
REUTERS_DATELINE = re.compile(r"^[A-Z][A-Z\s,.'\-]{2,80}\s+\(Reuters\)\s*[-–]\s*", re.I)


def clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("_x000D_", " ").replace("\x00", " ")
    text = html.unescape(text)
    text = HTML_TAG_RE.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(value: object) -> str:
    text = clean(value)
    if not text.startswith(("http://", "https://")):
        return ""
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower().removeprefix("www.")
        if not host:
            return ""
        path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
        query = urlencode([
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=False)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
        ])
        return urlunsplit(("https", host, path, query, ""))
    except ValueError:
        return ""


def iso_date(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = clean(value)
    for pattern in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return ""


def label_value(value: object) -> int | None:
    if isinstance(value, bool):
        return 0 if value else 1
    text = clean(value).casefold()
    if text in {"true", "real", "legit", "legitimate"}:
        return 0
    if text in {"false", "fake", "falso", "falsa"}:
        return 1
    return None


def non_latin_fraction(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    non_latin = sum("LATIN" not in unicodedata.name(ch, "") for ch in letters)
    return non_latin / len(letters)


def text_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text.casefold()).strip().encode("utf-8")).hexdigest()


def source_record(
    *, corpus: str, version: str, split: str, file_name: str, source_row: str,
    language: str, title: object, body: object, label: object, topic: object = None,
    source: object = None, url: object = None, published: object = None,
    license_name: str = "", type_hint: str = "article",
) -> dict:
    title_raw, body_raw = str(title or ""), str(body or "")
    title_clean, body_clean = clean(title), clean(body)
    source_clean, url_clean = clean(source), clean(url)
    normalized_url = canonical_url(url_clean)
    text_for_model = "\n\n".join(x for x in (title_clean, body_clean) if x)
    flags: list[str] = []
    if not text_for_model:
        flags.append("empty_text")
    if not title_clean:
        flags.append("missing_title")
    if not body_clean:
        flags.append("missing_body")
    if len(WORD_RE.findall(text_for_model)) < 50:
        flags.append("under_50_words")
    if non_latin_fraction(text_for_model) > 0.15:
        flags.append("non_latin_script_over_15pct")
    if LEAK_PREFIX_RE.match(title_clean) or LEAK_PREFIX_RE.match(body_clean):
        flags.append("possible_label_prefix")
    if REUTERS_DATELINE.match(body_clean):
        flags.append("reuters_dateline")
    if corpus == "spanish_v2" and source_clean.casefold() == "afpfactual":
        flags.append("afpfactual_source_review")
    host = urlsplit(normalized_url).hostname or ""
    if any(host == social or host.endswith("." + social) for social in SOCIAL_HOSTS):
        flags.append("social_url_review")
        if corpus == "spanish_v2":
            type_hint = "social_candidate"
    if corpus == "spanish_v2" and type_hint == "article":
        type_hint = "article_or_post_unverified"
    mapped = label_value(label)
    if mapped is None:
        flags.append("unmapped_label")
    identity = f"{corpus}|{version}|{file_name}|{source_row}"
    record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return {
        "id": record_id,
        "dataset": corpus,
        "version": version,
        "split_origen": split,
        "archivo_origen": file_name,
        "fila_origen": source_row,
        "idioma_original": language,
        "titulo_original": title_raw,
        "cuerpo_original": body_raw,
        "titular": title_clean,
        "cuerpo": body_clean,
        "texto_modelo": text_for_model,
        "etiqueta_original": str(label),
        "etiqueta_binaria": mapped,
        "tipo_texto": type_hint,
        "tema": clean(topic),
        "fuente": source_clean,
        "url": url_clean,
        "url_normalizada": normalized_url,
        "fecha_publicacion_original": clean(published),
        "fecha_publicacion": iso_date(published),
        "licencia_dataset": license_name,
        "flags_revision": flags,
        "hash_texto_exacto": text_hash(body_clean or title_clean) if text_for_model else "",
        "grupo_evento": "",  # Assigned only after evidence review in phase C.
    }


def workbook_rows(path_or_bytes):
    workbook = openpyxl.load_workbook(path_or_bytes, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        iterator = sheet.iter_rows(values_only=True)
        headers = [clean(x).casefold() for x in next(iterator)]
        for row_number, row in enumerate(iterator, start=2):
            if not any(value is not None for value in row):
                continue
            yield row_number, dict(zip(headers, row))
    finally:
        workbook.close()


def collect_records() -> tuple[list[dict], Counter]:
    records: list[dict] = []
    excluded = Counter()
    with zipfile.ZipFile(SPANISH_ZIP) as archive:
        for member in archive.namelist():
            name = Path(member).name
            if name not in {"train.xlsx", "development.xlsx", "test.xlsx"}:
                continue
            corpus = "spanish_v2" if name == "test.xlsx" else "spanish_v1"
            version = "2.0" if corpus == "spanish_v2" else "1.0"
            for row_number, row in workbook_rows(io.BytesIO(archive.read(member))):
                records.append(source_record(
                    corpus=corpus, version=version, split=name.removesuffix(".xlsx"),
                    file_name=name, source_row=str(row_number), language="es",
                    title=row.get("headline"), body=row.get("text"),
                    label=row.get("category"), topic=row.get("topic", row.get("topics")),
                    source=row.get("source"), url=row.get("link"),
                    license_name="CC BY 4.0",
                ))

    with zipfile.ZipFile(ISOT_ZIP) as archive:
        for member in ("True.csv", "Fake.csv"):
            label = "True" if member == "True.csv" else "Fake"
            with io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="") as handle:
                for row_number, row in enumerate(csv.DictReader(handle), start=2):
                    records.append(source_record(
                        corpus="isot", version="2023-03-09", split="source_file",
                        file_name=member, source_row=str(row_number), language="en",
                        title=row.get("title"), body=row.get("text"), label=label,
                        topic=row.get("subject"), published=row.get("date"),
                        license_name="not stated at source",
                    ))

    with zipfile.ZipFile(PEREZ_ZIP) as archive:
        for member in archive.namelist():
            if not member.endswith(".txt"):
                continue
            parts = Path(member).parts
            if len(parts) < 4:
                excluded["perez_unexpected_path"] += 1
                continue
            domain, label = parts[1], parts[2]
            raw = archive.read(member)
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                content = raw.decode("cp1252", errors="replace")
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            title = lines[0] if lines else ""
            body = "\n".join(lines[1:])
            records.append(source_record(
                corpus="perez_rosas_2018", version="2018-08-20", split=domain,
                file_name=member, source_row="1", language="en",
                title=title, body=body, label=label,
                topic=domain, license_name="GNU GPL (author download page)",
            ))

    for file_name in ("Fake.xlsx", "Real.xlsx"):
        for row_number, row in workbook_rows(POLYGLOT / file_name):
            original_language = clean(row.get("language")).casefold()
            if original_language not in {"spanish", "english"}:
                excluded["polyglot_other_original_language"] += 1
                continue
            records.append(source_record(
                corpus="polyglot_v2", version="1 (2026-02-17)", split=file_name.removesuffix(".xlsx"),
                file_name=file_name, source_row=str(row_number),
                language="es" if original_language == "spanish" else "en",
                title=row.get("news headline"), body=row.get("news original text"),
                label=row.get("label"), topic=row.get("keywords"),
                source=row.get("domain"), url=row.get("url"),
                published=row.get("news date"), license_name="CC BY 4.0",
            ))
    return records, excluded


def near_title_candidates(records: list[dict], limit: int = 20000) -> tuple[list[dict], int]:
    """High precision candidate pairs only; never merges or deletes records."""
    buckets: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    token_sets: list[set[str]] = []
    signatures: list[int] = []
    for i, row in enumerate(records):
        words = set(WORD_RE.findall(row["titular"].casefold()))
        token_sets.append(words)
        if len(words) < 5:
            signatures.append(0)
            continue
        votes = [0] * 64
        for word in words:
            value = int.from_bytes(hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest(), "big")
            for bit in range(64):
                votes[bit] += 1 if (value >> bit) & 1 else -1
        signature = sum((1 << bit) for bit, vote in enumerate(votes) if vote > 0)
        signatures.append(signature)
        for band in range(4):
            buckets[(row["idioma_original"], band, (signature >> (band * 16)) & 0xFFFF)].append(i)

    pairs: set[tuple[int, int]] = set()
    oversized = 0
    for indices in buckets.values():
        if len(indices) > 250:
            oversized += 1
            continue
        for offset, left in enumerate(indices):
            for right in indices[offset + 1:]:
                if left != right:
                    pairs.add((left, right))
    candidates: list[dict] = []
    for left, right in sorted(pairs):
        if records[left]["hash_texto_exacto"] == records[right]["hash_texto_exacto"]:
            continue
        words_left, words_right = token_sets[left], token_sets[right]
        if not words_left or not words_right:
            continue
        jaccard = len(words_left & words_right) / len(words_left | words_right)
        if jaccard < 0.80:
            continue
        title_left, title_right = records[left]["titular"], records[right]["titular"]
        ratio = SequenceMatcher(None, title_left.casefold(), title_right.casefold()).ratio()
        if ratio < 0.82:
            continue
        candidates.append({
            "id_1": records[left]["id"], "id_2": records[right]["id"],
            "dataset_1": records[left]["dataset"], "dataset_2": records[right]["dataset"],
            "split_1": records[left]["split_origen"], "split_2": records[right]["split_origen"],
            "jaccard_titulo": round(jaccard, 4), "similitud_titulo": round(ratio, 4),
            "misma_etiqueta": records[left]["etiqueta_binaria"] == records[right]["etiqueta_binaria"],
        })
        if len(candidates) >= limit:
            break
    return candidates, oversized


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"No se sobrescribe una preparación anterior: {OUT}")
    records, excluded = collect_records()
    exact_counts = Counter(row["hash_texto_exacto"] for row in records if row["hash_texto_exacto"])
    url_counts = Counter(row["url_normalizada"] for row in records if row["url_normalizada"])
    for row in records:
        row["grupo_texto_exacto"] = (
            "exact-" + row["hash_texto_exacto"][:16] if row["hash_texto_exacto"] else ""
        )
        row["tamano_grupo_texto_exacto"] = exact_counts.get(row["hash_texto_exacto"], 0)
        row["tamano_grupo_url"] = url_counts.get(row["url_normalizada"], 0)
        if row["tamano_grupo_texto_exacto"] > 1:
            row["flags_revision"].append("exact_text_duplicate")
        if row["tamano_grupo_url"] > 1:
            row["flags_revision"].append("normalized_url_duplicate")

    candidates, oversized = near_title_candidates(records)
    by_corpus = Counter(row["dataset"] for row in records)
    by_language_label = Counter(
        (row["dataset"], row["idioma_original"], str(row["etiqueta_binaria"])) for row in records
    )
    flags = Counter(flag for row in records for flag in row["flags_revision"])
    source_label = defaultdict(lambda: Counter())
    for row in records:
        if row["fuente"]:
            source_label[(row["dataset"], row["fuente"].casefold())][str(row["etiqueta_binaria"])] += 1
    single_label_sources = sorted(
        (
            {"dataset": corpus, "fuente": source, "count": sum(counts.values()), "labels": dict(counts)}
            for (corpus, source), counts in source_label.items()
            if sum(counts.values()) >= 10 and len(counts) == 1
        ),
        key=lambda item: item["count"], reverse=True,
    )

    report = {
        "total_records": len(records),
        "source_counts": dict(by_corpus),
        "language_label_counts": [
            {"dataset": corpus, "language": language, "label": label, "count": count}
            for (corpus, language, label), count in sorted(by_language_label.items())
        ],
        "excluded_before_normalization": dict(excluded),
        "flags": dict(flags),
        "exact_text_groups_over_one": sum(count > 1 for count in exact_counts.values()),
        "records_in_exact_text_groups": sum(count for count in exact_counts.values() if count > 1),
        "exact_url_groups_over_one": sum(count > 1 for count in url_counts.values()),
        "near_title_candidate_pairs": len(candidates),
        "near_title_oversized_buckets_skipped": oversized,
        "near_title_limit_reached": len(candidates) >= 20000,
        "single_label_sources_top30": single_label_sources[:30],
        "normalization_rules": [
            "Unicode NFC, HTML entity decode, HTML tag removal, whitespace collapse",
            "No lowercase/accent/punctuation deletion in model text",
            "Only original Spanish/English Polyglot rows; no translated columns",
            "Original files unchanged; no train/validation/test split created",
            "Exact duplicates flagged, not dropped; near title pairs for review only",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=False)
    with gzip.open(OUT / "normalized_all.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (OUT / "near_title_candidates.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "id_1", "id_2", "dataset_1", "dataset_2", "split_1", "split_2",
            "jaccard_titulo", "similitud_titulo", "misma_etiqueta",
        ])
        writer.writeheader()
        writer.writerows(candidates)
    with (OUT / "quality_report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": str(OUT), "records": len(records), "near_pairs": len(candidates)}))


if __name__ == "__main__":
    sys.exit(main())
