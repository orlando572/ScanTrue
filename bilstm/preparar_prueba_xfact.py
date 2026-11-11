"""Prepara una prueba inédita de afirmaciones españolas de X-FACT.

Usa solo las etiquetas estrictas true/false. No reetiqueta clases intermedias.
Los modelos de este proyecto nunca se entrenaron ni seleccionaron con X-FACT.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from entrenar_baseline import tokenize
from unificar_todos import fingerprint


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "datasets/pruebas_externas/x_fact"
MASTER = ROOT / "datasets/unificado_total/todos_los_textos_unicos.csv"
PARTITIONS = ("train.all.tsv", "dev.all.tsv", "test.all.tsv")
OUTPUT = BASE / "evaluacion_es_estricta.csv"
REPORT = BASE / "preparacion.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    if OUTPUT.exists() or REPORT.exists():
        raise FileExistsError("La prueba X-FACT ya está preparada; no se sobrescribe")
    reference = pd.read_csv(MASTER, dtype=str, usecols=["texto", "titulo"],
                            keep_default_na=False)
    known = {fingerprint(value) for column in ("texto", "titulo")
             for value in reference[column] if value}
    rows = []
    counts = Counter()
    source_hashes = {}
    for name in PARTITIONS:
        path = BASE / "original" / name
        source_hashes[name] = digest(path)
        frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False,
                            quoting=csv.QUOTE_NONE)
        spanish = frame[frame.language.eq("es")]
        counts[f"{name}:es_total"] = len(spanish)
        for _, item in spanish.iterrows():
            label = item["label"].strip().casefold()
            if label not in ("true", "false"):
                counts[f"{name}:clase_intermedia"] += 1
                continue
            claim = item["claim"].strip()
            key = fingerprint(claim)
            if not key or len(tokenize(claim)) < 3:
                counts["descartadas_breves_o_vacias"] += 1
                continue
            rows.append({"texto": claim, "etiqueta": 0 if label == "false" else 1,
                         "fuente": "x_fact_chequeado_claims", "particion_origen": name,
                         "sitio": item["site"], "etiqueta_original": label,
                         "tokens": len(tokenize(claim)), "huella": key})
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["huella"], []).append(row)
    clean = []
    for key, copies in groups.items():
        if len({row["etiqueta"] for row in copies}) > 1:
            counts["descartadas_contradiccion"] += len(copies)
            continue
        counts["duplicados_internos"] += len(copies) - 1
        if key in known:
            counts["solapamiento_exacto_corpus_local"] += 1
            continue
        clean.append(copies[0])
    # Compara cada afirmación con titulares locales. Algunos titulares de
    # FakeCovid citan literalmente la afirmación con un prefijo adicional.
    reference_titles = reference["titulo"].where(
        reference["titulo"].ne(""), reference["texto"].str.slice(0, 200))
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), strip_accents="unicode",
                                 lowercase=True)
    vectors = vectorizer.fit_transform(
        pd.concat([reference_titles, pd.Series([row["texto"] for row in clean])],
                  ignore_index=True))
    similarity = cosine_similarity(vectors[len(reference):], vectors[:len(reference)],
                                   dense_output=False)
    nearest = similarity.max(axis=1).toarray().ravel()
    near_threshold = 0.70
    counts["solapamiento_titulo_similar"] = int(sum(value >= near_threshold
                                                   for value in nearest))
    clean = [row for row, value in zip(clean, nearest) if value < near_threshold]
    clean.sort(key=lambda row: (row["particion_origen"], row["huella"]))
    if not clean or len({row["etiqueta"] for row in clean}) != 2:
        raise ValueError("La prueba resultante necesita ambas clases")
    BASE.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(clean[0]))
        writer.writeheader()
        writer.writerows(clean)
    report = {
        "fuente": "https://github.com/utahnlp/x-fact/tree/main/data/x-fact",
        "licencia_repositorio": "MIT",
        "tipo_tarea": "afirmaciones verificadas; no artículos completos",
        "criterio": "language=es y label exactamente true/false; 0=false, 1=true",
        "particiones_originales": list(PARTITIONS),
        "sha256_originales": source_hashes,
        "n_referencias_locales": len(reference),
        "conteos": dict(counts),
        "umbral_similitud_titulo_excluido": near_threshold,
        "n_evaluacion": len(clean),
        "etiquetas": dict(Counter(str(row["etiqueta"]) for row in clean)),
        "por_particion": dict(Counter(row["particion_origen"] for row in clean)),
        "tokens": {"min": min(row["tokens"] for row in clean),
                   "max": max(row["tokens"] for row in clean),
                   "sobre_192": sum(row["tokens"] > 192 for row in clean)},
        "limitacion_solapamiento": "Se quitan coincidencias exactas y similitud TF-IDF >=0.70 con titulares locales; no garantiza ausencia de eventos compartidos o paráfrasis.",
        "sha256_evaluacion": digest(OUTPUT),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
