"""Entrena y compara dos BiLSTM con las mismas particiones de evaluación.

Uso: python bilstm/entrenar_baseline.py --variant sin_politica
El vocabulario se aprende solo de entrenamiento; la prueba se evalúa una vez.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence
from torch.utils.data import DataLoader, Dataset


SEED = 42
TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def build_vocab(texts: pd.Series, max_size: int = 30000) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(tokenize(text))
    vocab = {"<pad>": 0, "<unk>": 1}
    for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_size - 2]:
        vocab[word] = len(vocab)
    return vocab


class NewsDataset(Dataset):
    def __init__(self, frame: pd.DataFrame, vocab: dict[str, int], max_len: int):
        self.ids = []
        self.labels = frame.etiqueta.astype(int).tolist()
        self.sources = frame.dataset.tolist()
        for text in frame.texto:
            tokens = tokenize(text)[:max_len]
            self.ids.append([vocab.get(word, 1) for word in tokens] or [1])

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, index: int):
        return self.ids[index], self.labels[index], self.sources[index]


def collate(batch):
    lengths = torch.tensor([len(row[0]) for row in batch], dtype=torch.long)
    width = int(lengths.max())
    ids = torch.zeros((len(batch), width), dtype=torch.long)
    for i, (sequence, _, _) in enumerate(batch):
        ids[i, :len(sequence)] = torch.tensor(sequence, dtype=torch.long)
    labels = torch.tensor([row[1] for row in batch], dtype=torch.long)
    return ids, lengths, labels, [row[2] for row in batch]


class BiLSTM(nn.Module):
    def __init__(self, vocab_size: int, embedding_dim: int = 128,
                 hidden_dim: int = 64, dropout: float = 0.3):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, batch_first=True,
                            bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_dim * 2, 2)

    def forward(self, ids: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(ids)
        packed = pack_padded_sequence(embedded, lengths.cpu(), batch_first=True,
                                      enforce_sorted=False)
        _, (hidden, _) = self.lstm(packed)
        representation = torch.cat((hidden[-2], hidden[-1]), dim=1)
        return self.classifier(self.dropout(representation))


def predict(model: nn.Module, loader: DataLoader, device: torch.device):
    model.eval()
    actual, predicted, sources = [], [], []
    with torch.inference_mode():
        for ids, lengths, labels, batch_sources in loader:
            scores = model(ids.to(device), lengths)
            actual.extend(labels.tolist())
            predicted.extend(scores.argmax(dim=1).cpu().tolist())
            sources.extend(batch_sources)
    return actual, predicted, sources


def metrics(actual: list[int], predicted: list[int]) -> dict:
    precision, recall, f1, _ = precision_recall_fscore_support(
        actual, predicted, pos_label=0, average="binary", zero_division=0)
    return {
        "n": len(actual), "accuracy": float(accuracy_score(actual, predicted)),
        "precision_falsa": float(precision), "recall_falsa": float(recall),
        "f1_falsa": float(f1),
        "f1_macro": float(f1_score(actual, predicted, average="macro", zero_division=0)),
        "matriz_confusion_orden_0_falsa_1_real": confusion_matrix(
            actual, predicted, labels=[0, 1]).tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("sin_politica", "politica_25"), required=True)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[1]
                        / "datasets/experimentos_bilstm")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-len", type=int, default=192)
    args = parser.parse_args()
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    if torch.cuda.is_available():
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    target = args.base / args.variant
    frames = {split: pd.read_csv(target / f"{split}.csv", dtype=str, keep_default_na=False)
              for split in ("entrenamiento", "validacion", "prueba")}
    vocab = build_vocab(frames["entrenamiento"].texto)
    data = {split: NewsDataset(frame, vocab, args.max_len) for split, frame in frames.items()}
    loader = {
        split: DataLoader(dataset, batch_size=args.batch_size,
                          shuffle=(split == "entrenamiento"), collate_fn=collate,
                          generator=torch.Generator().manual_seed(SEED))
        for split, dataset in data.items()
    }
    model = BiLSTM(len(vocab)).to(device)
    labels = frames["entrenamiento"].etiqueta.astype(int).value_counts()
    weights = torch.tensor([len(frames["entrenamiento"]) / (2 * labels[i])
                            for i in (0, 1)], dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    best_f1, best_state, best_epoch, stale = -1.0, None, 0, 0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for ids, lengths, batch_labels, _ in loader["entrenamiento"]:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(ids.to(device), lengths), batch_labels.to(device))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += float(loss.item()) * len(batch_labels)
        actual, predicted, _ = predict(model, loader["validacion"], device)
        validation = metrics(actual, predicted)
        history.append({"epoch": epoch,
                        "train_loss": total_loss / len(data["entrenamiento"]),
                        "validation": validation})
        print(f"{args.variant} epoch={epoch} loss={history[-1]['train_loss']:.4f} "
              f"val_f1_falsa={validation['f1_falsa']:.4f} "
              f"val_f1_macro={validation['f1_macro']:.4f}", flush=True)
        if validation["f1_macro"] > best_f1 + 1e-6:
            best_f1 = validation["f1_macro"]
            best_state = {name: value.detach().cpu().clone()
                          for name, value in model.state_dict().items()}
            best_epoch, stale = epoch, 0
        else:
            stale += 1
            if stale >= args.patience:
                break
    if best_state is None:
        raise RuntimeError("No se entrenó el modelo")
    model.load_state_dict(best_state)
    actual, predicted, sources = predict(model, loader["prueba"], device)
    by_source = {}
    for source in sorted(set(sources)):
        indices = [i for i, value in enumerate(sources) if value == source]
        by_source[source] = metrics([actual[i] for i in indices],
                                    [predicted[i] for i in indices])
    result = {
        "variant": args.variant, "device": str(device),
        "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
        "seed": SEED, "epochs_max": args.epochs, "best_epoch": best_epoch,
        "batch_size": args.batch_size, "max_len": args.max_len,
        "vocab_size": len(vocab), "history": history,
        "test": metrics(actual, predicted), "test_by_source": by_source,
    }
    torch.save({"state_dict": best_state, "vocab": vocab,
                "config": {"max_len": args.max_len, "embedding_dim": 128,
                           "hidden_dim": 64, "dropout": 0.3,
                           "labels": {0: "falsa", 1: "real"}}}, target / "modelo.pt")
    (target / "metricas.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(json.dumps({"variant": args.variant, "device": str(device),
                      "best_epoch": best_epoch, "test": result["test"],
                      "test_by_source": by_source}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
