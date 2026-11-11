"""Audita las predicciones de un BiLSTM ya entrenado sin cambiar sus pesos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import torch
from torch.utils.data import DataLoader

from entrenar_baseline import BiLSTM, NewsDataset, collate, metrics, tokenize


ROOT = Path(__file__).resolve().parents[1]


def audit(model_path: Path, data_path: Path, output: Path, batch_size: int = 32) -> dict:
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    model = BiLSTM(len(checkpoint["vocab"]), config["embedding_dim"],
                   config["hidden_dim"], config["dropout"])
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    frame = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    if frame.empty or not {"texto", "etiqueta", "dataset"}.issubset(frame.columns):
        raise ValueError("El CSV debe contener noticias, texto, etiqueta y dataset")
    dataset = NewsDataset(frame, checkpoint["vocab"], config["max_len"])
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, collate_fn=collate)
    predictions, probabilities = [], []
    with torch.inference_mode():
        for ids, lengths, _, _ in loader:
            scores = model(ids, lengths).softmax(dim=1)
            predictions.extend(scores.argmax(dim=1).tolist())
            probabilities.extend(scores[:, 0].tolist())
    audit_frame = frame.copy()
    audit_frame["prediccion"] = predictions
    audit_frame["prob_falsa"] = probabilities
    audit_frame["correcta"] = audit_frame.etiqueta.astype(int).eq(audit_frame.prediccion)
    audit_frame["tokens"] = audit_frame.texto.map(lambda value: len(tokenize(value)))
    audit_frame["recortada"] = audit_frame.tokens.gt(config["max_len"])
    audit_frame["confianza_prediccion"] = [p if label == 0 else 1 - p
                                          for p, label in zip(probabilities, predictions)]
    audit_frame["longitud"] = pd.cut(audit_frame.tokens, bins=[-1, 192, 384, 768, float("inf")],
                                     labels=["0-192", "193-384", "385-768", "769+"])
    actual = audit_frame.etiqueta.astype(int).tolist()
    summary = {
        "modelo": str(model_path.resolve()), "datos": str(data_path.resolve()),
        "n": len(audit_frame), "recortadas": int(audit_frame.recortada.sum()),
        "errores": int((~audit_frame.correcta).sum()),
        "metricas": metrics(actual, predictions),
        "por_longitud": {},
    }
    for group, rows in audit_frame.groupby("longitud", observed=True):
        summary["por_longitud"][str(group)] = {
            "n": len(rows), "errores": int((~rows.correcta).sum()),
            "metricas": metrics(rows.etiqueta.astype(int).tolist(), rows.prediccion.tolist()),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_frame.to_csv(output, index=False)
    summary_path = output.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("sin_politica", "politica_25"),
                        default="sin_politica")
    parser.add_argument("--split", choices=("validacion", "prueba"), default="validacion")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    model_dir = ROOT / "datasets/modelos_bilstm" / args.variant
    model_path = args.model or model_dir / "mejor_modelo.pt"
    data_path = args.data or ROOT / "datasets/experimentos_bilstm" / args.variant / f"{args.split}.csv"
    output = args.output or model_dir / f"auditoria_{args.split}.csv"
    print(json.dumps(audit(model_path, data_path, output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
