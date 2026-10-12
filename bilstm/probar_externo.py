"""Predice una noticia o evalúa un CSV externo con un BiLSTM guardado.

Las probabilidades son salidas del clasificador, no certeza factual.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
import torch

from entrenar_baseline import BiLSTM, metrics, tokenize


ROOT = Path(__file__).resolve().parents[1]


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def load_model(path: Path, device_name: str) -> tuple[BiLSTM, dict[str, int], int, torch.device]:
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible; usa --device cpu")
    device = torch.device(device_name)
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    model = BiLSTM(len(checkpoint["vocab"]), config["embedding_dim"],
                   config["hidden_dim"], config["dropout"])
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    return model, checkpoint["vocab"], config["max_len"], device


def predict_texts(model: BiLSTM, vocab: dict[str, int], max_len: int,
                  device: torch.device, texts: list[str], batch_size: int = 32) -> list[float]:
    probabilities = []
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            sequences = []
            for value in texts[start:start + batch_size]:
                words = tokenize(value)[:max_len]
                sequences.append([vocab.get(word, 1) for word in words] or [1])
            lengths = torch.tensor([len(sequence) for sequence in sequences])
            padded = torch.zeros((len(sequences), int(lengths.max())), dtype=torch.long)
            for index, sequence in enumerate(sequences):
                padded[index, :len(sequence)] = torch.tensor(sequence)
            scores = model(padded.to(device), lengths).softmax(dim=1)
            probabilities.extend(scores[:, 0].cpu().tolist())
    return probabilities


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
                        default=ROOT / "datasets/modelos_bilstm/sin_politica/mejor_modelo.pt")
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
