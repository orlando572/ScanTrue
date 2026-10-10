"""Freeze and audit BiLSTM CSV inputs for a new mBERT experiment (step 1 only)."""

import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "modelo bilstm"
OUT = ROOT / "datasets" / "processed" / "mbert_bilstm_step1_20261008_v1"
PREVIOUS = ROOT / "datasets" / "audits" / "bilstm_data_20261008_v1" / "new_artifacts_audit.json"
PARTITIONS = ("entrenamiento", "validacion", "prueba", "externa")
REQUIRED = {"texto", "etiqueta", "dataset", "grupo_duplicados", "id", "titulo", "url", "tipo_tarea", "tokens", "origen"}
SEED = 42


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = list(reader)
    return columns, rows


def asset_entry(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def main():
    # Exclusive directory creation makes it impossible to overwrite this snapshot.
    OUT.mkdir(parents=True, exist_ok=False)
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    partitions = {}
    sampled_groups = defaultdict(list)
    all_ok = True
    for name in PARTITIONS:
        path = SOURCE / f"{name}.csv"
        columns, rows = read_csv(path)
        digest = sha256(path)
        labels = Counter(row["etiqueta"] for row in rows)
        sources = Counter(row["dataset"] for row in rows)
        source_labels = defaultdict(Counter)
        for row in rows:
            source_labels[row["dataset"]][row["etiqueta"]] += 1
            if name == "entrenamiento":
                sampled_groups[(row["dataset"], row["etiqueta"])].append(row)
        empty_text = sum(not row["texto"].strip() for row in rows)
        empty_label = sum(not row["etiqueta"].strip() for row in rows)
        replacement_text = sum("\ufffd" in row["texto"] for row in rows)
        replacement_title = sum("\ufffd" in row["titulo"] for row in rows)
        missing_title = sum(not row["titulo"].strip() for row in rows)
        missing_url = sum(not row["url"].strip() for row in rows)
        hash_ok = digest == previous["hashes"][name]
        schema_ok = set(columns) == REQUIRED
        label_ok = set(labels) == {"0", "1"}
        ok = hash_ok and schema_ok and label_ok and not empty_text and not empty_label
        all_ok &= ok
        partitions[name] = {
            "path": str(path), "sha256": digest, "matches_prior_audit": hash_ok,
            "columns": columns, "schema_ok": schema_ok, "rows": len(rows),
            "labels_bilstm": dict(sorted(labels.items())), "sources": dict(sorted(sources.items())),
            "source_by_label_bilstm": {k: dict(sorted(v.items())) for k, v in sorted(source_labels.items())},
            "empty_text": empty_text, "empty_label": empty_label, "valid_binary_labels": label_ok,
            "rows_with_replacement_char_in_text": replacement_text,
            "rows_with_replacement_char_in_title": replacement_title,
            "missing_title": missing_title, "missing_url": missing_url,
            "step1_gate_ok": ok,
        }

    model_origin = json.loads((ROOT / "mBERT" / "assets" / "model_mbert_cased" / "origin.json").read_text(encoding="utf-8"))
    tokenizer_origin = json.loads((ROOT / "mBERT" / "assets" / "tokenizer_mbert_cased" / "origin.json").read_text(encoding="utf-8"))
    if model_origin["revision"] != tokenizer_origin["revision"]:
        all_ok = False
    assets = {
        "model_origin": model_origin, "tokenizer_origin": tokenizer_origin,
        "model_weights": asset_entry(ROOT / "mBERT" / "assets" / "model_mbert_cased" / "model.safetensors"),
        "tokenizer_json": asset_entry(ROOT / "mBERT" / "assets" / "tokenizer_mbert_cased" / "tokenizer.json"),
        "tokenizer_vocab": asset_entry(ROOT / "mBERT" / "assets" / "tokenizer_mbert_cased" / "vocab.txt"),
        "matched_revision": model_origin["revision"] == tokenizer_origin["revision"],
    }
    manifest = {
        "snapshot_date_local": "2026-10-08", "step": 1, "status": "inputs_frozen_no_training",
        "input_policy": "read_originals_verify_sha256_before_every_following_step",
        "source_label_mapping": {"0": "FALSA", "1": "REAL"},
        "target_label_mapping": {"0": "REAL", "1": "FALSA"},
        "conversion": "label_mbert = 1 - int(etiqueta_bilstm)",
        "planned_seed_set": [42, 43, 44], "sample_review_seed": SEED,
        "partitions": partitions, "assets": assets,
        "audit_reference": {"path": str(PREVIOUS), "sha256": sha256(PREVIOUS)},
        "code": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "comparison_protocol": {
            "reference_model": "E1_len256_seed44_20261007-202946_bda20c1f",
            "common_label_order": ["REAL", "FALSA"],
            "selection_only_validation": True,
            "retrospective_partitions": ["prueba", "externa"],
            "report_all_rows_and_common_unexposed_subset_separately": True,
            "final_unseen_test": "pending; no final generalization claim until it exists",
        },
        "gate_step1": "pass" if all_ok else "fail",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    review = []
    for (source, label), rows in sorted(sampled_groups.items()):
        for row in random.Random(SEED).sample(rows, min(3, len(rows))):
            review.append({
                "id": row["id"], "dataset": source, "etiqueta_bilstm": label,
                "titulo": row["titulo"], "url": row["url"],
                "texto_inicio_600": row["texto"][:600],
                "replacement_character": "\ufffd" in row["texto"],
                "revision": "pendiente_verificacion_externa",
                "decision": "conservar_provisionalmente",
            })
    with (OUT / "muestra_revision_entrenamiento.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(review[0]))
        writer.writeheader()
        writer.writerows(review)
    print(json.dumps({"output": str(OUT), "gate": manifest["gate_step1"],
                      "sample_rows": len(review), "replacement_by_partition": {
                          k: v["rows_with_replacement_char_in_text"] for k, v in partitions.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
