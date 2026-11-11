"""Crea un corpus único de textos españoles sin confundir tareas ni duplicar fuentes.

Uso: bilstm/.venv/bin/python bilstm/unificar_todos.py
Los originales y los modelos no se modifican.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from preparar_datasets import direct_rows, nondirect_rows


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"
SCHEMA = ("id", "texto", "titulo", "etiqueta_binaria", "grupo_uso", "tipo_tarea",
          "etiqueta_original", "tema", "idioma_declarado", "dataset_principal",
          "datasets_origen", "archivos_origen", "particiones_origen", "url",
          "fecha", "fuente", "huella_texto", "n_registros_origen", "motivo")
PRIORITY = {
    "noticia_binaria": 0, "afirmacion_falsa": 1, "usmsc_binario_derivado": 2,
    "satira": 3, "articulo_verificacion": 4, "fiabilidad": 5,
    "fragmento_fiabilidad": 6, "evidencia": 7,
}


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def fingerprint(value: object) -> str:
    """Ignora formato, acentos, puntuación y espacios; conserva letras y cifras."""
    plain = unicodedata.normalize("NFKD", normalize(value).casefold())
    return "".join(character for character in plain if character.isalnum())


def digest(value: object) -> str:
    return hashlib.sha256(fingerprint(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def verify_aliases(root: Path) -> dict:
    """Comprueba copias exactas y la versión reformateada antes de unir fuentes."""
    aliases = {}
    pairs = [
        ("jpposadas_train", "MIS DATASETS/jpposadas:FakeNewsCorpusSpanish-master/train.xlsx",
         "servir_directamente/spanish_fake_news_corpus_v1/train.xlsx"),
        ("jpposadas_development", "MIS DATASETS/jpposadas:FakeNewsCorpusSpanish-master/development.xlsx",
         "servir_directamente/spanish_fake_news_corpus_v1/development.xlsx"),
        ("jpposadas_test", "MIS DATASETS/jpposadas:FakeNewsCorpusSpanish-master/test.xlsx",
         "no_directamente/fakedes_iberlef_2021/test.xlsx"),
        ("gabrielhuav_usmsc", "MIS DATASETS/gabrielhuav:Unified-and-Balanced-Spanish-Fake-News-Corpus/gabrielhuav_Unified_Spanish_Misinformation_and_Satire_Corpus_USMSC.csv",
         "no_directamente/usmsc/usmsc.csv"),
        ("nagorebravo_factores", "MIS DATASETS/nagorebravo:FactOReS/dev.json",
         "no_directamente/factores/dev.json"),
    ]
    for name, left, right in pairs:
        left_hash, right_hash = sha256_file(root / left), sha256_file(root / right)
        if left_hash != right_hash:
            raise ValueError(f"La copia {name} ya no coincide con el original conocido")
        aliases[name] = {"copia": left, "origen": right, "sha256": left_hash}
    xlsx_dir = root / "MIS DATASETS/jpposadas:FakeNewsCorpusSpanish-master"
    csv_dir = root / "MIS DATASETS/sayalaruano:FakeNewsCorpusSpanish"
    for split in ("train", "development", "test"):
        original = pd.read_excel(xlsx_dir / f"{split}.xlsx", dtype=str, keep_default_na=False)
        copy = pd.read_csv(csv_dir / f"{split}.csv", dtype=str, keep_default_na=False)
        if list(original.columns) != list(copy.columns) or len(original) != len(copy):
            raise ValueError(f"La copia CSV de {split} cambió de estructura")
        for column in original.columns:
            if split == "test" and column == "CATEGORY":
                same = original[column].map({"False": "0", "True": "1"}).equals(copy[column])
            else:
                same = original[column].equals(copy[column])
            if not same:
                raise ValueError(f"La copia CSV de {split} difiere en {column}")
        aliases[f"sayalaruano_{split}"] = {
            "copia": str((csv_dir / f"{split}.csv").relative_to(root)),
            "equivalente": str((xlsx_dir / f"{split}.xlsx").relative_to(root)),
            "filas": len(copy),
        }
    fixed = pd.read_csv(root / "MIS DATASETS/Edds:spanish-fake-news-fixed/fakenews_fixed.csv",
                        sep=";", dtype=str, keep_default_na=False)
    original = pd.read_csv(root / "no_directamente/usmsc/usmsc.csv",
                           sep=";", dtype=str, keep_default_na=False)
    if len(fixed) != len(original) or not fixed.label.equals(original.label):
        raise ValueError("La versión Edds no conserva filas y etiquetas de USMSC")
    aliases["edds_usmsc"] = {
        "filas": len(fixed), "textos_identicos_misma_fila": int(fixed.text.eq(original.text).sum()),
        "etiquetas_identicas": True,
        "sha256": sha256_file(root / "MIS DATASETS/Edds:spanish-fake-news-fixed/fakenews_fixed.csv"),
    }
    return aliases


def lineage_fingerprints(root: Path) -> tuple[dict[str, set[str]], dict]:
    """Identifica textos derivados aunque USMSC haya descartado el titular."""
    sources: dict[str, set[str]] = {}
    political = pd.read_csv(root / "servir_directamente/spanish_political_fake_news/D57000_complete.csv",
                            sep=";", dtype=str, keep_default_na=False)
    sources["spanish_political_fake_news"] = set(map(fingerprint, political.Descripcion))
    v1_dir = root / "servir_directamente/spanish_fake_news_corpus_v1"
    sources["spanish_fake_news_corpus_v1"] = set().union(*(
        set(map(fingerprint, pd.read_excel(v1_dir / name, dtype=str, keep_default_na=False).Text))
        for name in ("train.xlsx", "development.xlsx")))
    fakedes = pd.read_excel(root / "no_directamente/fakedes_iberlef_2021/test.xlsx",
                            dtype=str, keep_default_na=False)
    sources["fakedes_iberlef_2021"] = set(map(fingerprint, fakedes.TEXT))
    acosta_dir = root / "servir_directamente/spanish_fake_and_real_news_acosta"
    sources["spanish_fake_and_real_news_acosta"] = set().union(*(
        set(map(fingerprint, pd.read_csv(acosta_dir / name, dtype=str, keep_default_na=False).texto))
        for name in ("spanishFakeNews.csv", "testSpanishFakeNews.csv")))
    zenodo = pd.read_csv(root / "no_directamente/spanish_fake_news_dataset_zenodo/esp_fake_news.csv",
                          dtype=str, keep_default_na=False)
    sources["spanish_fake_news_dataset_zenodo"] = set(map(fingerprint, zenodo["Fake statement"]))
    return sources, {name: len(values) for name, values in sources.items()}


def entry_from_prepared(row: dict) -> dict:
    source = row["dataset"]
    if row["tipo_tarea"] in ("noticia", "titulo_y_descripcion", "noticia_sobre_fallecimiento"):
        task = "noticia_binaria"
    elif source == "spanish_fake_news_dataset_zenodo":
        task = "afirmacion_falsa"
    elif source == "fakecovid":
        task = "articulo_verificacion"
    elif source == "run_as":
        task = "fiabilidad"
    elif source == "flares_2024":
        task = "fragmento_fiabilidad"
    else:
        raise ValueError(f"Fuente no clasificada: {source}")
    label = str(row["etiqueta"]) if row["etiqueta"] in (0, 1) else ""
    if task == "afirmacion_falsa":
        label = "0"  # La fuente contiene afirmaciones falsas, no artículos binarios.
    return {
        "texto": normalize(row["texto"]), "titulo": normalize(row["titulo"]),
        "label": label, "task": task, "raw_label": normalize(row["etiqueta_original"]),
        "dataset": source, "file": normalize(row["archivo"]),
        "split": normalize(row["particion"]), "url": normalize(row["url"]),
        "date": normalize(row["fecha"]), "publisher": normalize(row["fuente"]),
        "topic": "", "source_id": normalize(row["id_original"]),
        "quality": "corto" if len(normalize(row["texto"])) < 30 else "",
    }


def collect_entries(root: Path, lineage: dict[str, set[str]]) -> tuple[list[dict], dict, list[dict]]:
    direct = direct_rows(root)
    nondirect = nondirect_rows(root)
    entries = [entry_from_prepared(row) for row in direct + nondirect
               if row["dataset"] not in ("usmsc", "factores")]
    input_counts = Counter(entry["dataset"] for entry in entries)
    fixed_path = root / "MIS DATASETS/Edds:spanish-fake-news-fixed/fakenews_fixed.csv"
    fixed = pd.read_csv(fixed_path, sep=";", dtype=str, keep_default_na=False)
    derived = Counter()
    for index, row in fixed.iterrows():
        text = normalize(row["text"])
        mark = fingerprint(text)
        matched = next((name for name, values in lineage.items() if mark in values), "")
        if matched:
            derived[matched] += 1
            continue
        label = str(row["label"])
        task = "satira" if label == "2" else "usmsc_binario_derivado"
        entries.append({"texto": text, "titulo": "", "label": label if label != "2" else "",
                        "task": task, "raw_label": label, "dataset": "usmsc_edds",
                        "file": str(fixed_path), "split": "sin_particion", "url": "",
                        "date": "", "publisher": "", "topic": "", "source_id": str(index + 2),
                        "quality": ""})
        input_counts["usmsc_edds_nuevos"] += 1
    # FactOReS contiene varias relaciones de evidencia para cada afirmación.
    # La tabla maestra conserva una afirmación única y la tabla auxiliar, cada par.
    fact_path = root / "MIS DATASETS/nagorebravo:FactOReS/dev.json"
    fact_rows = json.loads(fact_path.read_text(encoding="utf-8"))
    evidence = []
    for record in fact_rows:
        evidence.append({"claim_id": record["claim_id"], "claim": normalize(record["claim"]),
                         "question": normalize(record["question"]),
                         "evidence": normalize(record["summarized_text"]),
                         "relevance": record["relevance"], "stance": record["STANCE"],
                         "label": record["label"]})
    by_claim = defaultdict(list)
    for row in evidence:
        by_claim[(row["claim_id"], fingerprint(row["claim"]))].append(row)
    for (claim_id, _), rows in by_claim.items():
        entries.append({"texto": rows[0]["claim"], "titulo": "", "label": "",
                        "task": "evidencia", "raw_label": ",".join(sorted({r["label"] for r in rows})),
                        "dataset": "factores", "file": str(fact_path), "split": "desarrollo",
                        "url": "", "date": "", "publisher": "", "topic": "",
                        "source_id": str(claim_id), "quality": ""})
    input_counts["factores_afirmaciones"] = len(by_claim)
    input_counts["factores_relaciones"] = len(evidence)
    return entries, {"entradas": dict(input_counts), "usmsc_derivados_retirados": dict(derived)}, evidence


def choose_primary(group: list[dict]) -> dict:
    return min(group, key=lambda row: (PRIORITY[row["task"]], -len(row["texto"]),
                                       row["dataset"], row["source_id"]))


def merge_entries(entries: list[dict]) -> tuple[list[dict], dict]:
    grouped = defaultdict(list)
    empty = 0
    for row in entries:
        mark = fingerprint(row["texto"])
        if not mark:
            empty += 1
            continue
        grouped[mark].append(row)
    output = []
    report = Counter()
    for mark, group in grouped.items():
        primary = choose_primary(group)
        labels = {row["label"] for row in group if row["label"] in ("0", "1")}
        tasks = {row["task"] for row in group}
        if len(labels) > 1:
            usage, label, reason = "conflicto", "", "etiquetas_binarias_contradictorias"
            report["grupos_con_conflicto"] += 1
        elif "noticia_binaria" in tasks and labels and len(primary["texto"]) >= 30:
            usage, label, reason = "noticia_binaria", next(iter(labels)), ""
        elif "usmsc_binario_derivado" in tasks and labels:
            usage, label, reason = "binario_derivado", next(iter(labels)), "sin_titulo_ni_fuente"
        elif "afirmacion_falsa" in tasks and labels:
            usage, label, reason = "afirmacion_falsa", next(iter(labels)), "solo_clase_falsa"
        else:
            usage, label = "no_binario", ""
            reason = "texto_corto" if len(primary["texto"]) < 30 else "tarea_distinta"
        tags = sorted({row["raw_label"] for row in group if row["raw_label"]})
        datasets = sorted({row["dataset"] for row in group})
        files = sorted({row["file"] for row in group})
        splits = sorted({row["split"] for row in group if row["split"]})
        topics = sorted({row["topic"] for row in group if row["topic"]})
        title = next((row["titulo"] for row in sorted(group, key=lambda r: PRIORITY[r["task"]])
                      if row["titulo"]), "")
        url = next((row["url"] for row in group if row["url"]), "")
        date = next((row["date"] for row in group if row["date"]), "")
        publisher = next((row["publisher"] for row in group if row["publisher"]), "")
        row = {
            "id": hashlib.sha256(mark.encode("utf-8")).hexdigest(),
            "texto": primary["texto"], "titulo": title, "etiqueta_binaria": label,
            "grupo_uso": usage, "tipo_tarea": ",".join(sorted(tasks)),
            "etiqueta_original": json.dumps(tags, ensure_ascii=False),
            "tema": ",".join(topics), "idioma_declarado": "es",
            "dataset_principal": primary["dataset"],
            "datasets_origen": json.dumps(datasets, ensure_ascii=False),
            "archivos_origen": json.dumps(files, ensure_ascii=False),
            "particiones_origen": json.dumps(splits, ensure_ascii=False),
            "url": url, "fecha": date, "fuente": publisher,
            "huella_texto": hashlib.sha256(mark.encode("utf-8")).hexdigest(),
            "n_registros_origen": len(group), "motivo": reason,
        }
        output.append(row)
        report["duplicados_por_contenido"] += len(group) - 1
    report["textos_vacios"] = empty
    # Una misma URL puede traer versiones con saltos, sustituciones de números
    # o párrafos añadidos. Solo se unen si el contenido y la etiqueta concuerdan.
    by_url = defaultdict(list)
    for row in output:
        if row["url"] and row["grupo_uso"] == "noticia_binaria":
            by_url[row["url"].strip().casefold().rstrip("/")].append(row)
    removed = set()
    for group in by_url.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda row: (-len(row["texto"]), row["id"]))
        keep = group[0]
        for other in group[1:]:
            if (other["etiqueta_binaria"] != keep["etiqueta_binaria"] or
                    difflib.SequenceMatcher(None, keep["texto"], other["texto"],
                                            autojunk=False).ratio() < 0.8):
                report["url_compartida_sin_unir"] += 1
                continue
            for field in ("datasets_origen", "archivos_origen", "particiones_origen"):
                keep[field] = json.dumps(sorted(set(json.loads(keep[field])) |
                                             set(json.loads(other[field]))), ensure_ascii=False)
            keep["n_registros_origen"] += other["n_registros_origen"]
            if not keep["titulo"]:
                keep["titulo"] = other["titulo"]
            removed.add(other["id"])
            report["duplicados_por_url"] += 1
    output = [row for row in output if row["id"] not in removed]
    output.sort(key=lambda row: (row["grupo_uso"], row["id"]))
    return output, dict(report)


def write_csv(path: Path, rows: list[dict], columns: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def flares_annotations(root: Path) -> list[dict]:
    """Conserva las anotaciones originales, incluidas las de fragmentos repetidos."""
    annotations = []
    for path in sorted((root / "no_directamente/flares_2024").glob("*.json")):
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                annotations.append({
                    "archivo": str(path), "linea": line_number,
                    "id_original": record.get("Id", ""),
                    "texto": normalize(record.get("Text", "")),
                    "etiqueta_fiabilidad": record.get("Reliability_Label", ""),
                    "etiqueta_5w1h": record.get("5W1H_Label", ""),
                    "fragmento": record.get("Tag_Text", ""),
                    "inicio": record.get("Tag_Start", ""),
                    "fin": record.get("Tag_End", ""),
                    "anotaciones": json.dumps(record.get("Tags", []), ensure_ascii=False),
                })
    return annotations


def build(root: Path, output: Path) -> dict:
    aliases = verify_aliases(root)
    lineage, lineage_sizes = lineage_fingerprints(root)
    entries, input_report, evidence = collect_entries(root, lineage)
    merged, dedup = merge_entries(entries)
    if len({row["huella_texto"] for row in merged}) != len(merged):
        raise AssertionError("Quedaron textos duplicados")
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "todos_los_textos_unicos.csv", merged, SCHEMA)
    binary = [row for row in merged if row["grupo_uso"] == "noticia_binaria"]
    write_csv(output / "noticias_binarias.csv", binary, SCHEMA)
    expanded = [row for row in merged if row["grupo_uso"] in
                ("noticia_binaria", "binario_derivado")]
    write_csv(output / "binarios_ampliados.csv", expanded, SCHEMA)
    write_csv(output / "factores_evidencias.csv", evidence,
              ("claim_id", "claim", "question", "evidence", "relevance", "stance", "label"))
    annotations = flares_annotations(root)
    write_csv(output / "flares_anotaciones.csv", annotations,
              ("archivo", "linea", "id_original", "texto", "etiqueta_fiabilidad",
               "etiqueta_5w1h", "fragmento", "inicio", "fin", "anotaciones"))
    report = {
        "total_textos_unicos": len(merged),
        "noticias_binarias": len(binary),
        "binarios_ampliados": len(expanded),
        "por_grupo_uso": dict(Counter(row["grupo_uso"] for row in merged)),
        "por_dataset_principal": dict(Counter(row["dataset_principal"] for row in merged)),
        "etiquetas_noticias_binarias": dict(Counter(row["etiqueta_binaria"] for row in binary)),
        "etiquetas_binarios_ampliados": dict(Counter(row["etiqueta_binaria"] for row in expanded)),
        "con_titular_noticias_binarias": sum(bool(row["titulo"]) for row in binary),
        "flares_anotaciones": len(annotations),
        "origenes_unicos": input_report, "deduplicacion": dedup,
        "huellas_linaje": lineage_sizes, "copias_verificadas": aliases,
        "faltante": "MM-COVID: enlace público de datos no disponible; no se inventaron filas",
        "notas": [
            "Todos los textos son únicos por huella alfanumérica normalizada; las paráfrasis no se eliminan automáticamente.",
            f"FactOReS tiene {input_report['entradas']['factores_afirmaciones']} identificadores de afirmación, "
            f"{sum('factores' in json.loads(row['datasets_origen']) for row in merged)} textos únicos en la tabla maestra "
            f"y {len(evidence)} relaciones en factores_evidencias.csv.",
            f"FLARES se cuenta por fragmento textual único; sus {len(annotations)} anotaciones se conservan aparte, no como noticias.",
            "Las fuentes de prueba anteriores están presentes: se necesita una nueva evaluación externa antes de entrenar con todo.",
            "Las etiquetas de fiabilidad, sátira y artículos de verificación no se convierten a falsa/real.",
        ],
    }
    (output / "reporte.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATASETS)
    parser.add_argument("--output", type=Path, default=DATASETS / "unificado_total")
    args = parser.parse_args()
    report = build(args.input, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
