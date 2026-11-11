"""Arquitectura y tokenizador del BiLSTM de ScanTrue.

Lo usan el entrenamiento (`bilstm/entrenar.py`), el conjunto común
(`datos_comunes/construir_comun.py`) y el backend (`backend/models/bilstm.py`).
Cambiar algo aquí cambia cómo se leen los checkpoints existentes: hazlo con cuidado.

- `tokenize`: palabras `\\b\\w+\\b` en minúsculas (casefold), igual que en todos los modelos BiLSTM.
- `construir_vocabulario`: `<pad>`=0, `<unk>`=1 y las palabras más frecuentes del entrenamiento.
- `BiLSTM`: embedding → BiLSTM de 1 capa → pooling → dropout → lineal de 2 salidas.
  Con `pooling="final"` (por defecto) tiene la misma estructura que el modelo de producción,
  así que carga tanto el checkpoint de producción como los del conjunto común.
  El orden de las salidas lo fija cada checkpoint:
  producción usa 0 = falsa, 1 = real; el conjunto común usa 0 = real, 1 = falsa.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)
POOLINGS = ("final", "maxmedia", "atencion")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def construir_vocabulario(textos: Iterable[str], max_size: int = 30000) -> dict[str, int]:
    """Vocabulario ordenado por frecuencia (empates por orden alfabético)."""
    cuentas: Counter[str] = Counter()
    for texto in textos:
        cuentas.update(tokenize(texto))
    vocab = {"<pad>": 0, "<unk>": 1}
    for palabra, _ in sorted(cuentas.items(), key=lambda item: (-item[1], item[0]))[:max_size - 2]:
        vocab[palabra] = len(vocab)
    return vocab


class BiLSTM(nn.Module):
    """Embedding → BiLSTM 1 capa → pooling → dropout → lineal(2).

    pooling:
    - `final`: concatena el último estado de cada dirección (receta usada en producción y en B6).
    - `maxmedia`: concatena el máximo y la media de todas las salidas.
    - `atencion`: suma ponderada de las salidas con atención aditiva.
    """

    def __init__(self, vocab_size: int, embedding_dim: int = 300, hidden_dim: int = 64,
                 dropout: float = 0.3, pooling: str = "final"):
        super().__init__()
        if pooling not in POOLINGS:
            raise ValueError(f"pooling desconocido: {pooling}")
        self.pooling = pooling
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        if pooling == "atencion":
            self.atencion = nn.Sequential(nn.Linear(2 * hidden_dim, hidden_dim), nn.Tanh(),
                                          nn.Linear(hidden_dim, 1, bias=False))
        self.classifier = nn.Linear(hidden_dim * (4 if pooling == "maxmedia" else 2), 2)

    def forward(self, ids: torch.Tensor, largos: torch.Tensor) -> torch.Tensor:
        empaquetado = pack_padded_sequence(self.embedding(ids), largos.cpu(), batch_first=True,
                                           enforce_sorted=False)
        salidas, (oculto, _) = self.lstm(empaquetado)
        if self.pooling == "final":
            representacion = torch.cat((oculto[-2], oculto[-1]), dim=1)
        else:
            h, _ = pad_packed_sequence(salidas, batch_first=True)
            mascara = (torch.arange(h.size(1), device=h.device)[None, :]
                       < largos.to(h.device)[:, None])
            if self.pooling == "maxmedia":
                maximo = h.masked_fill(~mascara[..., None], float("-inf")).max(dim=1).values
                media = (h * mascara[..., None]).sum(1) / mascara.sum(1, keepdim=True)
                representacion = torch.cat((maximo, media), dim=1)
            else:
                puntaje = self.atencion(h).squeeze(-1).masked_fill(~mascara, float("-inf"))
                alfa = torch.softmax(puntaje, dim=1)
                representacion = (alfa[..., None] * h).sum(1)
        return self.classifier(self.dropout(representacion))
