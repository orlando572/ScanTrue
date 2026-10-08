"""Entrena un BiLSTM independiente inicializado con vectores fastText en español."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bilstm"))
from entrenar import load_splits, set_seed  # noqa: E402
from entrenar_baseline import (  # noqa: E402
    BiLSTM, NewsDataset, build_vocab, collate, metrics, predict,
)


def load_vectors(path: Path, vocab: dict[str, int], model: BiLSTM) -> dict:
    """Busca solo las palabras del entrenamiento, sin cargar el archivo entero en RAM."""
    opener = gzip.open if path.suffix == ".gz" else open
    dimension = model.embedding.embedding_dim
    wanted = set(vocab) - {"<pad>", "<unk>"}
    found: set[str] = set()
    malformed = 0
    with opener(path, "rt", encoding="utf-8", errors="replace") as stream:
        header = stream.readline().strip().split()
        if len(header) != 2 or not all(part.isdecimal() for part in header):
            raise ValueError("El archivo de vectores necesita cabecera 'palabras dimensiones'")
        if int(header[1]) != dimension:
            raise ValueError(f"Vectores de {header[1]} dimensiones; modelo de {dimension}")
        with torch.no_grad():
            for line in stream:
                word, separator, values = line.partition(" ")
                if not separator or word not in wanted or word in found:
                    continue
                vector = np.fromstring(values, sep=" ", dtype=np.float32)
                if vector.size != dimension or not np.isfinite(vector).all():
                    malformed += 1
                    continue
                model.embedding.weight[vocab[word]].copy_(torch.from_numpy(vector))
                found.add(word)
                if len(found) == len(wanted):
                    break
    return {"vocabulario": len(wanted), "vectores_encontrados": len(found),
            "cobertura": len(found) / len(wanted) if wanted else 0.0,
            "lineas_invalidas_relevantes": malformed,
            "sin_vector": len(wanted) - len(found)}


def train(args: argparse.Namespace) -> dict:
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"La salida ya contiene archivos: {args.output}")
    if not args.embeddings.is_file():
        raise FileNotFoundError(args.embeddings)
    if args.epochs < 1 or args.patience < 1 or args.max_len < 1:
        raise ValueError("epochs, patience y max-len deben ser positivos")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible")

    frames, hashes = load_splits(args.input, include_test=False)
    set_seed(args.seed)
    vocab = build_vocab(frames["entrenamiento"].texto, max_size=args.vocab_size)
    model = BiLSTM(len(vocab), 300, args.hidden_dim, args.dropout)
    coverage = load_vectors(args.embeddings, vocab, model)
    print(f"Cobertura de vectores: {coverage['vectores_encontrados']}/"
          f"{coverage['vocabulario']} ({coverage['cobertura']:.1%})", flush=True)
    if coverage["cobertura"] < args.min_coverage:
        raise ValueError("Cobertura inferior al mínimo solicitado")
    device = torch.device(args.device)
    model.to(device)
    data = {name: NewsDataset(frame, vocab, args.max_len) for name, frame in frames.items()}
    loaders = {
        name: DataLoader(dataset, batch_size=args.batch_size,
                         shuffle=(name == "entrenamiento"), collate_fn=collate,
                         generator=torch.Generator().manual_seed(args.seed))
        for name, dataset in data.items()
    }
    counts = Counter(data["entrenamiento"].labels)
    weights = torch.tensor([len(data["entrenamiento"]) / (2 * counts[i]) for i in (0, 1)],
                           dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max",
                                                           factor=0.5, patience=2)
    args.output.mkdir(parents=True, exist_ok=True)
    config = {
        "input": str(args.input.resolve()), "input_sha256": hashes,
        "embeddings": str(args.embeddings.resolve()), "embedding_source": args.source,
        "embedding_file_size": args.embeddings.stat().st_size,
        "coverage": coverage, "output": str(args.output.resolve()),
        "device": args.device, "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda, "seed": args.seed,
        "epochs_max": args.epochs, "patience": args.patience,
        "batch_size": args.batch_size, "max_len": args.max_len,
        "vocab_size": len(vocab), "embedding_dim": 300,
        "hidden_dim": args.hidden_dim, "dropout": args.dropout,
        "lr": args.lr, "weight_decay": args.weight_decay,
        "labels": {"0": "falsa", "1": "real"},
        "validation_only": True,
        "rows": {name: len(frame) for name, frame in frames.items()},
    }
    (args.output / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    best_f1, best_epoch, stale = -math.inf, 0, 0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for ids, lengths, labels, _ in loaders["entrenamiento"]:
            optimizer.zero_grad(set_to_none=True)
            scores = model(ids.to(device), lengths)
            loss = criterion(scores, labels.to(device))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item() * len(labels)
        actual, predicted, _ = predict(model, loaders["validacion"], device)
        validation = metrics(actual, predicted)
        scheduler.step(validation["f1_macro"])
        history.append({"epoch": epoch,
                        "train_loss": total_loss / len(data["entrenamiento"]),
                        "validation": validation})
        (args.output / "historial.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Época {epoch}: F1 macro {validation['f1_macro']:.4f}, "
              f"F1 falsa {validation['f1_falsa']:.4f}", flush=True)
        if validation["f1_macro"] > best_f1 + args.min_delta:
            best_f1, best_epoch, stale = validation["f1_macro"], epoch, 0
            checkpoint = {
                "state_dict": {key: value.detach().cpu().clone()
                               for key, value in model.state_dict().items()},
                "vocab": vocab,
                "config": {"max_len": args.max_len, "embedding_dim": 300,
                           "hidden_dim": args.hidden_dim, "dropout": args.dropout,
                           "labels": {0: "falsa", 1: "real"}},
                "best_epoch": best_epoch,
            }
            torch.save(checkpoint, args.output / "mejor_modelo.pt")
        else:
            stale += 1
            if stale >= args.patience:
                print("Parada temprana", flush=True)
                break
    result = {"best_epoch": best_epoch, "epochs_ran": len(history),
              "validation_best": history[best_epoch - 1]["validation"],
              "coverage": coverage}
    (args.output / "resultados.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--source", choices=("fasttext_cc", "fasttext_wiki"), required=True)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--min-delta", type=float, default=0.001)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-len", type=int, default=64)
    parser.add_argument("--vocab-size", type=int, default=30000)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-coverage", type=float, default=0.5)
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
