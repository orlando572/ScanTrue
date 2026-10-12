"""Prepare immutable, label-normalized BiLSTM partitions for mBERT step 3."""
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "modelo bilstm"
STEP1 = ROOT / "datasets/processed/mbert_bilstm_step1_20261008_v1"
STEP2 = ROOT / "datasets/processed/mbert_bilstm_step2_20261008_v1"
OUT = ROOT / "datasets/processed/mbert_bilstm_step3_20261008_v1"
SPLITS = ("entrenamiento", "validacion", "prueba", "externa")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_gzip_jsonl(path, rows):
    with path.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                zipped.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def main():
    step1 = json.loads((STEP1 / "manifest.json").read_text(encoding="utf-8"))
    step2 = json.loads((STEP2 / "policy_v4.json").read_text(encoding="utf-8"))
    assert step1["gate_step1"] == "pass" and step2["status"] == "frozen_for_step3_not_training"
    assert sha(STEP2 / "decisions_primary_v4.csv") == step2["decisions_sha256"]
    OUT.mkdir(parents=True, exist_ok=False)
    manifest = {
        "phase": "new_mbert_bilstm_step3", "created_local_date": "2026-10-08",
        "status": "prepared_no_mbert_training", "label2id": {"REAL": 0, "FALSA": 1},
        "id2label": {"0": "REAL", "1": "FALSA"},
        "label_rule": "1 - int(etiqueta_bilstm)",
        "input_policy": "Single sequence: tokenizer(text, truncation=True, max_length=L); text is exact CSV texto and already includes title when present. No metadata as input.",
        "tokenizer_revision": step1["assets"]["tokenizer_origin"]["revision"],
        "tokenizer_json_sha256": step1["assets"]["tokenizer_json"]["sha256"],
        "step1_manifest_sha256": sha(STEP1 / "manifest.json"),
        "step2_policy_v4_sha256": sha(STEP2 / "policy_v4.json"),
        "step2_decisions_sha256": sha(STEP2 / "decisions_primary_v4.csv"),
        "code_sha256": sha(Path(__file__)),
        "partitions": {},
    }
    seen_ids = set()
    for split in SPLITS:
        source_path = SOURCE / f"{split}.csv"
        assert sha(source_path) == step1["partitions"][split]["sha256"]
        ids_path = STEP2 / f"{split}_primary_v4_ids.txt"
        assert sha(ids_path) == step2["splits"][split]["ids_sha256"]
        include_ids = set(ids_path.read_text(encoding="utf-8").splitlines())
        processed = []
        with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
            for source in csv.DictReader(stream):
                if source["id"] not in include_ids:
                    continue
                assert source["id"] not in seen_ids
                assert source["etiqueta"] in ("0", "1") and source["texto"].strip()
                seen_ids.add(source["id"])
                processed.append({
                    "id": source["id"], "partition": split,
                    "label": 1 - int(source["etiqueta"]), "language": "es",
                    "dataset": source["dataset"], "text": source["texto"],
                    "title_audit_only": source["titulo"], "url_audit_only": source["url"],
                    "group_audit_only": source["grupo_duplicados"],
                    "origin_audit_only": source["origen"], "task_type_audit_only": source["tipo_tarea"],
                    "input_mode": "single_text",
                })
        assert len(processed) == len(include_ids) == step2["splits"][split]["included"]
        label_count = Counter(row["label"] for row in processed)
        expected = {1 - int(k): v for k, v in step2["splits"][split]["included_labels_bilstm"].items()}
        assert dict(label_count) == expected
        out_path = OUT / f"{split}.jsonl.gz"
        stable_gzip_jsonl(out_path, processed)
        manifest["partitions"][split] = {
            "source_csv": str(source_path), "source_csv_sha256": sha(source_path),
            "included_ids_sha256": sha(ids_path), "output_path": str(out_path),
            "output_sha256": sha(out_path), "rows": len(processed),
            "labels_mbert": {str(k): label_count[k] for k in (0, 1)},
            "datasets": dict(Counter(row["dataset"] for row in processed)),
        }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({s: {"rows": v["rows"], "labels_mbert": v["labels_mbert"]}
                      for s, v in manifest["partitions"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
