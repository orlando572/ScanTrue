"""Carga e inferencia del BiLSTM de producción (B6) según su contrato de inferencia."""

from __future__ import annotations

from pathlib import Path

import torch

from bilstm.modelo import BiLSTM, tokenize
from backend.models.contrato import BILSTM_CONTRACT, ModelContract, calibrated_probability


def resolve_device(device_name: str = "auto") -> torch.device:
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible; usa --device cpu")
    return torch.device(device_name)


def load_model(
    contract: ModelContract, device_name: str = "auto"
) -> tuple[BiLSTM, dict[str, int], int, torch.device]:
    """Carga una sola vez el checkpoint del contrato (verificando su SHA-256)."""
    path = contract.checkpoint
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el checkpoint BiLSTM: {path}")
    contract.verify(path)
    device = resolve_device(device_name)
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    if config.get("etiquetas") != contract.data["etiquetas"]:
        raise ValueError("El orden de clases del checkpoint BiLSTM no coincide con su contrato")
    if int(config["max_len"]) != contract.max_tokens:
        raise ValueError("La longitud del checkpoint BiLSTM no coincide con su contrato")
    if config.get("pooling", "final") != contract.data.get("pooling", "final"):
        raise ValueError("El pooling del checkpoint BiLSTM no coincide con su contrato")
    model = BiLSTM(
        len(checkpoint["vocab"]),
        config["embedding_dim"],
        config["hidden_dim"],
        config["dropout"],
        config.get("pooling", "final"),
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    return model, checkpoint["vocab"], contract.max_tokens, device


def predict_logits(
    model: BiLSTM,
    vocab: dict[str, int],
    max_len: int,
    device: torch.device,
    texts: list[str],
    batch_size: int = 32,
) -> list[float]:
    """Devuelve logit_falsa − logit_real por texto; replica la tokenización del entrenamiento."""
    margins: list[float] = []
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
            logits = model(padded.to(device), lengths).float()
            # Contrato: salida 0 = real, salida 1 = falsa.
            margins.extend((logits[:, 1] - logits[:, 0]).cpu().tolist())
    return margins


class BilstmPredictor:
    """Modelo listo para recibir textos sin recargar el checkpoint por petición."""

    def __init__(
        self,
        contract_path: Path = BILSTM_CONTRACT,
        device_name: str = "auto",
    ) -> None:
        self.contract = ModelContract.load(contract_path, "bilstm")
        self.model, self.vocab, self.max_len, self.device = load_model(
            self.contract, device_name
        )
        self.version = self.contract.version

    def predict(self, text: str) -> dict[str, str | float | int]:
        words = tokenize(text)
        margin = predict_logits(
            self.model, self.vocab, self.max_len, self.device, [text]
        )[0]
        probability_fake = calibrated_probability(margin, self.contract.temperature)
        return {
            "modelo": "bilstm",
            "version": self.version,
            "clase": "falsa" if probability_fake >= self.contract.threshold else "real",
            "probabilidad_falsa": probability_fake,
            "tokens_leidos": min(len(words), self.max_len),
        }

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Expone el tokenizador exacto del entrenamiento para validar entradas."""
        return tokenize(text)
