"""Entrenamiento principal del BiLSTM para noticias falsas en español.

Ejemplo: python bilstm/entrenar.py
Por defecto usa la variante sin política y requiere una GPU CUDA.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader

from entrenar_baseline import BiLSTM, NewsDataset, build_vocab, collate, metrics, predict


ROOT = Path(__file__).resolve().parents[1]


def load_splits(folder: Path, include_test: bool = True) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames, hashes = {}, {}
    splits = ("entrenamiento", "validacion", "prueba") if include_test else ("entrenamiento", "validacion")
    for split in splits:
        path = folder / f"{split}.csv"
        hashes[split] = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        required = {"texto", "etiqueta", "dataset", "grupo_duplicados"}
        if not required.issubset(frame.columns):
            raise ValueError(f"Faltan columnas en {path}: {sorted(required - set(frame.columns))}")
        if frame.empty or frame.texto.str.strip().eq("").any():
            raise ValueError(f"Hay textos vacíos o no hay datos en {path}")
        if set(frame.etiqueta) != {"0", "1"}:
            raise ValueError(f"Se requieren ambas etiquetas 0 y 1 en {path}")
        if frame.grupo_duplicados.eq("").any():
            raise ValueError(f"Faltan grupos de duplicados en {path}")
        frames[split] = frame
    for first, second in (("entrenamiento", "validacion"),
                          ("entrenamiento", "prueba"), ("validacion", "prueba")):
        if first not in frames or second not in frames:
            continue
        if set(frames[first].grupo_duplicados) & set(frames[second].grupo_duplicados):
            raise ValueError(f"Hay textos repetidos entre {first} y {second}")
    return frames, hashes


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def train(args: argparse.Namespace) -> dict:
    if args.epochs < 1 or args.patience < 1 or args.batch_size < 1:
        raise ValueError("epochs, patience y batch-size deben ser positivos")
    if args.max_len < 1 or args.vocab_size < 3 or args.embedding_dim < 1 or args.hidden_dim < 1:
        raise ValueError("Dimensiones y longitud de secuencia inválidas")
    if args.lr <= 0 or args.weight_decay < 0 or args.min_delta < 0 or not 0 <= args.dropout < 1:
        raise ValueError("Hiperparámetros fuera de rango")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible. Revisa PyTorch y el controlador NVIDIA")
    if args.output.exists() and any(args.output.iterdir()) and not args.overwrite:
        raise FileExistsError(f"La salida ya contiene archivos: {args.output}. Usa --overwrite o cambia --output")

    frames, hashes = load_splits(args.input, include_test=not args.validation_only)
    set_seed(args.seed)
    device = torch.device(args.device)
    vocab = build_vocab(frames["entrenamiento"].texto, max_size=args.vocab_size)
    datasets = {name: NewsDataset(frame, vocab, args.max_len) for name, frame in frames.items()}
    loaders = {
        name: DataLoader(dataset, batch_size=args.batch_size,
                         shuffle=(name == "entrenamiento"), collate_fn=collate,
                         generator=torch.Generator().manual_seed(args.seed))
        for name, dataset in datasets.items()
    }
    model = BiLSTM(len(vocab), args.embedding_dim, args.hidden_dim, args.dropout).to(device)
    counts = Counter(datasets["entrenamiento"].labels)
    weights = torch.tensor([len(datasets["entrenamiento"]) / (2 * counts[i]) for i in (0, 1)],
                           dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5,
                                                           patience=2)
    args.output.mkdir(parents=True, exist_ok=True)
    config = {
        "input": str(args.input.resolve()), "input_sha256": hashes,
        "output": str(args.output.resolve()), "device": args.device,
        "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
        "seed": args.seed, "epochs_max": args.epochs, "patience": args.patience,
        "min_delta": args.min_delta, "batch_size": args.batch_size,
        "max_len": args.max_len, "vocab_size": len(vocab),
        "embedding_dim": args.embedding_dim, "hidden_dim": args.hidden_dim,
        "dropout": args.dropout, "lr": args.lr, "weight_decay": args.weight_decay,
        "labels": {"0": "falsa", "1": "real"},
        "validation_only": args.validation_only,
        "rows": {name: len(frame) for name, frame in frames.items()},
    }
    (args.output / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2),
                                              encoding="utf-8")

    best_f1, best_epoch, stale = -1.0, 0, 0
    history = []
    best_path = args.output / "mejor_modelo.pt"
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for ids, lengths, labels, _ in loaders["entrenamiento"]:
            optimizer.zero_grad(set_to_none=True)
            logits = model(ids.to(device), lengths)
            loss = criterion(logits, labels.to(device))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item() * len(labels)
        actual, predicted, _ = predict(model, loaders["validacion"], device)
        validation = metrics(actual, predicted)
        scheduler.step(validation["f1_macro"])
        row = {"epoch": epoch, "train_loss": total_loss / len(datasets["entrenamiento"]),
               "lr": optimizer.param_groups[0]["lr"], "validation": validation}
        history.append(row)
        (args.output / "historial.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Época {epoch}/{args.epochs} | pérdida {row['train_loss']:.4f} | "
              f"F1 macro validación {validation['f1_macro']:.4f} | "
              f"F1 falsa {validation['f1_falsa']:.4f}", flush=True)
        if validation["f1_macro"] > best_f1 + args.min_delta:
            best_f1, best_epoch, stale = validation["f1_macro"], epoch, 0
            checkpoint = {"state_dict": {key: value.detach().cpu().clone()
                                         for key, value in model.state_dict().items()},
                          "vocab": vocab,
                          "config": {"max_len": args.max_len,
                                     "embedding_dim": args.embedding_dim,
                                     "hidden_dim": args.hidden_dim,
                                     "dropout": args.dropout,
                                     "labels": {0: "falsa", 1: "real"}},
                          "best_epoch": best_epoch}
            torch.save(checkpoint, best_path)
        else:
            stale += 1
            if stale >= args.patience:
                print(f"Parada temprana tras {stale} épocas sin mejora", flush=True)
                break

    checkpoint = torch.load(best_path, map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    result = {"best_epoch": best_epoch, "epochs_ran": len(history),
              "validation_best": history[best_epoch - 1]["validation"]}
    if not args.validation_only:
        actual, predicted, sources = predict(model, loaders["prueba"], device)
        by_source = {}
        for source in sorted(set(sources)):
            indices = [i for i, value in enumerate(sources) if value == source]
            by_source[source] = metrics([actual[i] for i in indices],
                                        [predicted[i] for i in indices])
        result.update(test=metrics(actual, predicted), test_by_source=by_source)
    (args.output / "resultados.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("sin_politica", "politica_25"),
                        default="sin_politica")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--min-delta", type=float, default=0.001)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-len", type=int, default=192)
    parser.add_argument("--vocab-size", type=int, default=30000)
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--validation-only", action="store_true",
                        help="No leer ni evaluar la partición de prueba")
    args = parser.parse_args()
    if args.input is None:
        args.input = ROOT / "datasets/experimentos_bilstm" / args.variant
    if args.output is None:
        args.output = ROOT / "datasets/modelos_bilstm" / args.variant
    return args


if __name__ == "__main__":
    train(parse_args())
