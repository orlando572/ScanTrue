"""Tokenización e inferencia del modelo transformer de producción (BETO M3b) según su contrato.

La clave interna sigue siendo «mbert» (API, contratos y extensión); el modelo base lo indica
`modelo_base` en el contrato.
"""

from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path

import torch

from backend.models.contrato import (
    MBERT_CONTRACT, ModelContract, calibrated_probability, file_sha256, resolve,
)


class MbertTokenizer:
    """Aplica el contrato de inferencia sin descargar artefactos remotos."""

    def __init__(self, contract_path: Path = MBERT_CONTRACT) -> None:
        from transformers import AutoTokenizer

        self.contract = ModelContract.load(contract_path, "mbert")
        if self.contract.data.get("entrada") != "texto_unico":
            raise ValueError("El contrato mBERT espera otra forma de entrada")
        self.model_dir = self.contract.checkpoint
        self.checkpoint = self.model_dir / "model.safetensors"
        tokenizer = self.contract.data["tokenizador"]
        self.tokenizer_dir = resolve(tokenizer["ruta"])
        if file_sha256(self.tokenizer_dir / "tokenizer.json") != tokenizer["sha256_tokenizer_json"]:
            raise ValueError("El tokenizador mBERT no coincide con su contrato")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.tokenizer_dir,
            local_files_only=True,
            use_fast=True,
            # Es un tokenizador BERT (WordPiece); el arreglo Mistral cambiaría sus IDs.
            fix_mistral_regex=False,
        )
        if not self.tokenizer.is_fast:
            raise ValueError("Se necesita el tokenizador rápido para conservar el texto original")
        self.version = self.contract.version
        self.base_model = self.contract.data.get("modelo_base", {}).get("clave", "mbert")
        self.max_len = self.contract.max_tokens
        self.fake_threshold = self.contract.threshold

    def prepare(self, text: str) -> tuple[str, bool, int]:
        """Recorta por offsets originales; el límite incluye [CLS] y [SEP]."""
        probe = self.tokenizer(
            text, truncation=True, max_length=self.max_len + 1,
            return_offsets_mapping=True,
        )
        truncated = len(probe["input_ids"]) > self.max_len
        if truncated:
            encoded = self.tokenizer(
                text, truncation=True, max_length=self.max_len,
                return_offsets_mapping=True,
            )
            ends = [end for start, end in encoded["offset_mapping"] if end > start]
            if not ends:
                raise ValueError("El tokenizador mBERT no encontró texto para recortar")
            text = text[: ends[-1]].rstrip()
        count = len(self.tokenizer(text, truncation=False)["input_ids"])
        if count > self.max_len:
            raise ValueError("El recorte mBERT excedió el límite de tokens")
        return text, truncated, count


class MbertPredictor:
    """Carga el modelo una vez y devuelve P(falsa) calibrada; «falsa» es la salida 1."""

    def __init__(self, text_policy: MbertTokenizer) -> None:
        from transformers import AutoModelForSequenceClassification

        contract = text_policy.contract
        contract.verify(text_policy.checkpoint)
        config = json.loads((text_policy.model_dir / "config.json").read_text(encoding="utf-8"))
        if config["id2label"] != {"0": "real", "1": "falsa"} or config["label2id"] != {"real": 0, "falsa": 1}:
            raise ValueError("El orden de clases del checkpoint mBERT no es válido")
        self.text_policy = text_policy
        self.contract = contract
        self.version = text_policy.version
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            text_policy.model_dir, local_files_only=True, use_safetensors=True
        ).to(self.device).eval()

    def margin(self, text: str) -> tuple[float, int]:
        """`logit_falsa − logit_real` sin calibrar y subpalabras leídas."""
        encoded = self.text_policy.tokenizer(
            text, truncation=True, max_length=self.text_policy.max_len,
            return_tensors="pt",
        )
        tokens_read = int(encoded["input_ids"].shape[1])
        encoded = {name: value.to(self.device) for name, value in encoded.items()}
        with torch.inference_mode():
            autocast = (
                torch.autocast("cuda", dtype=torch.bfloat16)
                if self.device.type == "cuda" and torch.cuda.is_bf16_supported()
                else nullcontext()
            )
            with autocast:
                logits = self.model(**encoded).logits.float()[0]
        return float((logits[1] - logits[0]).item()), tokens_read

    def predict(self, text: str) -> dict[str, str | float | int]:
        margin, tokens_read = self.margin(text)
        probability_fake = calibrated_probability(margin, self.contract.temperature)
        return {
            "modelo": "mbert",
            "version": self.version,
            "clase": "falsa" if probability_fake >= self.text_policy.fake_threshold else "real",
            "probabilidad_falsa": probability_fake,
            "tokens_leidos": tokens_read,
        }
