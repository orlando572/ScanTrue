"""Predice una noticia o evalúa un CSV externo con un BiLSTM guardado.

Las probabilidades son salidas del clasificador, no certeza factual.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.bilstm import DEFAULT_CHECKPOINT, load_model, predict_texts
from entrenar_baseline import metrics, tokenize


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def overlap_flags(frame: pd.DataFrame, reference_dir: Path) -> list[str | None]:
    paths = [reference_dir / f"{split}.csv" for split in
             ("entrenamiento", "validacion", "prueba")]
    if not all(path.is_file() for path in paths):
        return [None] * len(frame)
    reference = pd.concat([pd.read_csv(path, dtype=str, keep_default_na=False)
                           for path in paths], ignore_index=True)
    known_texts = {normalize(value) for value in reference.texto if value}
    known_titles = {normalize(value) for value in reference.titulo
                    if len(normalize(value)) >= 25} if "titulo" in reference else set()
    known_urls = {normalize(value) for value in reference.url if value} \
        if "url" in reference else set()
    flags = []
    for _, row in frame.iterrows():
        if normalize(row["texto"]) in known_texts:
            flags.append("texto")
        elif "url" in frame and row["url"] and normalize(row["url"]) in known_urls:
            flags.append("url")
        elif "titulo" in frame and len(normalize(row["titulo"])) >= 25 \
                and normalize(row["titulo"]) in known_titles:
            flags.append("titulo")
        else:
            flags.append("")
    return flags


def evaluate_csv(frame: pd.DataFrame, probabilities: list[float],
                 reference_dir: Path) -> tuple[pd.DataFrame, dict]:
    if "texto" not in frame or frame.empty or frame.texto.str.strip().eq("").any():
        raise ValueError("El CSV necesita una columna texto sin filas vacías")
    output = frame.copy()
    output["prob_falsa"] = probabilities
    output["prediccion"] = [0 if value >= 0.5 else 1 for value in probabilities]
    output["solapamiento"] = overlap_flags(frame, reference_dir)
    reference_available = output.solapamiento.notna().all()
    output["referencia_disponible"] = reference_available
    overlapping = output.solapamiento.fillna("").ne("")
    normalized_text = output.texto.map(normalize)
    output["duplicado_externo"] = normalized_text.duplicated()
    report = {"n_total": len(output),
              "referencia_disponible": bool(reference_available),
              "solapadas_excluidas": int(overlapping.sum()),
              "duplicadas_excluidas": int(output.duplicado_externo.sum())}
    if "etiqueta" in output:
        if not output.etiqueta.isin(("0", "1")).all():
            raise ValueError("La columna etiqueta debe contener solo 0=falsa y 1=real")
        if (output.groupby(normalized_text).etiqueta.nunique() > 1).any():
            raise ValueError("Hay noticias externas idénticas con etiquetas contradictorias")
        clean = output[~overlapping & ~output.duplicado_externo]
        report["n_evaluadas"] = len(clean)
        if not clean.empty:
            report["metricas"] = metrics(clean.etiqueta.astype(int).tolist(),
                                          clean.prediccion.tolist())
            if "fuente" in clean:
                report["por_fuente"] = {
                    str(name): metrics(group.etiqueta.astype(int).tolist(),
                                       group.prediccion.tolist())
                    for name, group in clean.groupby("fuente")
                }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--texto", help="Texto de una noticia")
    source.add_argument("--archivo", type=Path, help="Archivo UTF-8 con una noticia")
    source.add_argument("--csv", type=Path, help="CSV externo con columna texto")
    parser.add_argument("--modelo", type=Path,
                        default=DEFAULT_CHECKPOINT)
    parser.add_argument("--referencia", type=Path,
                        default=ROOT / "datasets/experimentos_bilstm/sin_politica")
    parser.add_argument("--salida", type=Path, help="CSV opcional con predicciones por fila")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    model, vocab, max_len, device = load_model(args.modelo, args.device)
    if args.csv:
        frame = pd.read_csv(args.csv, dtype=str, keep_default_na=False)
        if "texto" not in frame:
            raise ValueError("El CSV necesita una columna texto")
        probabilities = predict_texts(model, vocab, max_len, device, frame.texto.tolist())
        output, report = evaluate_csv(frame, probabilities, args.referencia)
        if args.salida:
            args.salida.parent.mkdir(parents=True, exist_ok=True)
            output.to_csv(args.salida, index=False)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        value = args.texto if args.texto is not None else args.archivo.read_text(encoding="utf-8")
        if not value.strip():
            raise ValueError("El texto de la noticia está vacío")
        probability = predict_texts(model, vocab, max_len, device, [value])[0]
        frame = pd.DataFrame({"texto": [value]})
        overlap = overlap_flags(frame, args.referencia)[0]
        print(json.dumps({"prediccion": "falsa" if probability >= 0.5 else "real",
                          "prob_falsa": round(probability, 4),
                          "tokens": len(tokenize(value)),
                          "tokens_leidos": min(len(tokenize(value)), max_len),
                          "referencia_disponible": overlap is not None,
                          "solapamiento_datos_previos": overlap or None,
                          "nota": "Predicción experimental; requiere verificación de hechos"},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
