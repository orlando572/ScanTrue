"""Inferencia local con el candidato E1 congelado de fase F.

Uso: python inferir_ejemplo.py --titulo "..." --cuerpo "..."
     python inferir_ejemplo.py --titulo "..." --archivo-cuerpo noticia.txt
     python inferir_ejemplo.py --entrada ejemplo_entrada.json
"""

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE / "runs" / "E1_len256_seed44_20261007-202946_bda20c1f" / "best_model"
TOKENIZER_DIR = HERE / "assets" / "tokenizer_mbert_cased"
MAX_LENGTH = 256
THRESHOLD = 0.5


def validar_entrada(obj):
    if not isinstance(obj, dict):
        raise ValueError("La entrada debe ser un objeto JSON")
    titulo = obj.get("titulo", "")
    cuerpo = obj.get("cuerpo")
    if not isinstance(titulo, str) or not isinstance(cuerpo, str) or not cuerpo.strip():
        raise ValueError("'titulo' debe ser texto y 'cuerpo' debe contener texto")
    return titulo.strip(), cuerpo.strip()


def inferir(obj):
    titulo, cuerpo = validar_entrada(obj)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_DIR, local_files_only=True)
    if titulo:
        inputs = tokenizer(titulo, cuerpo, truncation="only_second", max_length=MAX_LENGTH, return_tensors="pt")
    else:
        inputs = tokenizer(cuerpo, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, local_files_only=True).to(device).eval()
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.inference_mode():
        if device == "cuda" and torch.cuda.is_bf16_supported():
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(**inputs).logits
        else:
            logits = model(**inputs).logits
    prob = logits.float().softmax(dim=-1)[0].cpu().tolist()
    return {
        "prediccion": "FALSA" if prob[1] >= THRESHOLD else "REAL",
        "probabilidades": {"REAL": prob[0], "FALSA": prob[1]},
        "umbral": THRESHOLD,
        "tokens": int(inputs["input_ids"].shape[1]),
        "dispositivo": device,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clasifica una noticia con el checkpoint mBERT experimental")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--entrada", type=Path, help="Archivo JSON con titulo y cuerpo")
    source.add_argument("--cuerpo", help="Cuerpo de la noticia escrito en el comando")
    source.add_argument("--archivo-cuerpo", type=Path, help="Archivo UTF-8 con el cuerpo completo")
    parser.add_argument("--titulo", default="", help="Titular de la noticia")
    args = parser.parse_args()
    if args.entrada:
        if args.titulo:
            parser.error("--titulo no se combina con --entrada; inclúyelo en el JSON")
        entrada = json.loads(args.entrada.read_text(encoding="utf-8"))
    else:
        cuerpo = args.cuerpo if args.cuerpo is not None else args.archivo_cuerpo.read_text(encoding="utf-8")
        entrada = {"titulo": args.titulo, "cuerpo": cuerpo}
    print(json.dumps(inferir(entrada), ensure_ascii=False, indent=2))
