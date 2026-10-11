"""Tokenización e inferencia del checkpoint mBERT seleccionado."""

from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath

import torch


ROOT = Path(__file__).resolve().parents[2]
MBERT_ROOT = ROOT / "mBERT"
SELECTION = MBERT_ROOT / "selection/bilstm_step5_20261008_v1/selection.json"


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class MbertTokenizer:
    """Aplica el contrato congelado sin descargar artefactos remotos."""

    def __init__(self) -> None:
        from transformers import AutoTokenizer

        decision = json.loads(SELECTION.read_text(encoding="utf-8"))
        if decision["status"] != "frozen_for_step6":
            raise ValueError("La selección mBERT no está congelada")
        contract = decision["inference_contract"]
        if contract["label2id"] != {"REAL": 0, "FALSA": 1} or contract["max_length"] != 512:
            raise ValueError("El contrato mBERT no coincide con el esperado")
        run_name = PureWindowsPath(decision["selected_run"]["path"]).name
        self.model_dir = (MBERT_ROOT / "runs" / run_name / "best_model").resolve()
        if not self.model_dir.is_relative_to((MBERT_ROOT / "runs").resolve()):
            raise ValueError("La ruta del checkpoint mBERT no es válida")
        self.tokenizer_dir = MBERT_ROOT / "assets/tokenizer_mbert_cased"
        self.checkpoint = self.model_dir / "model.safetensors"
        self.expected_model_sha256 = decision["selected_run"]["model_sha256"]
        tokenizer_file = self.tokenizer_dir / "tokenizer.json"
        if file_sha256(tokenizer_file) != contract["tokenizer_json_sha256"]:
            raise ValueError("El tokenizador mBERT no coincide con la selección")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.tokenizer_dir,
            local_files_only=True,
            use_fast=True,
            # Es un tokenizador BERT; aplicar el arreglo Mistral cambiaría sus IDs.
            fix_mistral_regex=False,
        )
        if not self.tokenizer.is_fast:
            raise ValueError("Se necesita el tokenizador rápido para conservar el texto original")
        run = decision["selected_run"]
        self.version = f"mBERT_BiLSTM_{run['arm']}_len{run['length']}_seed{run['seed']}"
        self.max_len = contract["max_length"]
        self.fake_threshold = contract["fake_probability_threshold"]

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
    """Carga el modelo una vez y devuelve P(FALSA), que ocupa la clase 1."""

    def __init__(self, text_policy: MbertTokenizer) -> None:
        from transformers import AutoModelForSequenceClassification

        if file_sha256(text_policy.checkpoint) != text_policy.expected_model_sha256:
            raise ValueError("El checkpoint mBERT no coincide con la selección")
        config = json.loads((text_policy.model_dir / "config.json").read_text(encoding="utf-8"))
        if config["id2label"] != {"0": "REAL", "1": "FALSA"} or config["label2id"] != {"REAL": 0, "FALSA": 1}:
            raise ValueError("El orden de clases del checkpoint mBERT no es válido")
        self.text_policy = text_policy
        self.version = text_policy.version
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            text_policy.model_dir, local_files_only=True, use_safetensors=True
        ).to(self.device).eval()

    def predict(self, text: str) -> dict[str, str | float | int]:
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
                logits = self.model(**encoded).logits
            probability_fake = float(logits.float().softmax(dim=-1)[0, 1].item())
        return {
            "modelo": "mbert",
            "version": self.version,
            "clase": "falsa" if probability_fake >= self.text_policy.fake_threshold else "real",
            "probabilidad_falsa": probability_fake,
            "tokens_leidos": tokens_read,
        }
