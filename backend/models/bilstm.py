"""Carga e inferencia del BiLSTM elegido para el backend de ScanTrue."""

from __future__ import annotations

from pathlib import Path

import torch

from bilstm.entrenar_baseline import BiLSTM, tokenize


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT = (
    ROOT
    / "datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt"
)


def resolve_device(device_name: str = "auto") -> torch.device:
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible; usa --device cpu")
    return torch.device(device_name)


def load_model(
    path: Path = DEFAULT_CHECKPOINT, device_name: str = "auto"
) -> tuple[BiLSTM, dict[str, int], int, torch.device]:
    """Carga una sola vez el checkpoint y devuelve modelo, vocabulario y límites."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el checkpoint BiLSTM: {path}")
    device = resolve_device(device_name)
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    model = BiLSTM(
        len(checkpoint["vocab"]),
        config["embedding_dim"],
        config["hidden_dim"],
        config["dropout"],
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    return model, checkpoint["vocab"], config["max_len"], device


def predict_texts(
    model: BiLSTM,
    vocab: dict[str, int],
    max_len: int,
    device: torch.device,
    texts: list[str],
    batch_size: int = 32,
) -> list[float]:
    """Devuelve P(falsa) por texto; replica la tokenización del entrenamiento."""
    probabilities: list[float] = []
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            sequences = []
            for value in texts[start : start + batch_size]:
                words = tokenize(value)[:max_len]
                sequences.append([vocab.get(word, 1) for word in words] or [1])
            lengths = torch.tensor([len(sequence) for sequence in sequences])
            padded = torch.zeros(
                (len(sequences), int(lengths.max())), dtype=torch.long
            )
            for index, sequence in enumerate(sequences):
                padded[index, : len(sequence)] = torch.tensor(sequence)
            scores = model(padded.to(device), lengths).softmax(dim=1)
            probabilities.extend(scores[:, 0].cpu().tolist())
    return probabilities


class BilstmPredictor:
    """Modelo listo para recibir textos sin recargar el checkpoint por petición."""

    def __init__(
        self,
        checkpoint: Path = DEFAULT_CHECKPOINT,
        device_name: str = "auto",
    ) -> None:
        self.checkpoint = Path(checkpoint)
        self.model, self.vocab, self.max_len, self.device = load_model(
            self.checkpoint, device_name
        )
        self.version = self.checkpoint.parent.name

    def predict(self, text: str) -> dict[str, str | float | int]:
        words = tokenize(text)
        probability_fake = predict_texts(
            self.model, self.vocab, self.max_len, self.device, [text]
        )[0]
        return {
            "modelo": "bilstm",
            "version": self.version,
            "clase": "falsa" if probability_fake >= 0.5 else "real",
            "probabilidad_falsa": probability_fake,
            "tokens_leidos": min(len(words), self.max_len),
        }

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Expone el tokenizador exacto del entrenamiento para validar entradas."""
        return tokenize(text)
