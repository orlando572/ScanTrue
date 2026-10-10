"""Inferencia local con el mBERT nuevo seleccionado en el paso 5.

Ejemplos:
  python inferir_bilstm_mbert.py --texto "Titular Cuerpo de la noticia..."
  python inferir_bilstm_mbert.py --titulo "Titular" --cuerpo "Cuerpo..."
  python inferir_bilstm_mbert.py --archivo-texto noticia.txt
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path, PureWindowsPath

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "selection/bilstm_step5_20261008_v1/selection.json"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_frozen_candidate():
    decision = json.loads(SELECTION.read_text(encoding="utf-8"))
    assert decision["status"] == "frozen_for_step6"
    contract = decision["inference_contract"]
    assert contract["label2id"] == {"REAL": 0, "FALSA": 1}
    # El manifiesto histórico conserva rutas absolutas del equipo de entrenamiento.
    # Usar el nombre de la corrida permite inferir desde cualquier clon del repositorio.
    run_name = PureWindowsPath(decision["selected_run"]["path"]).name
    model_dir = (HERE / "runs" / run_name / "best_model").resolve()
    tokenizer_dir = (HERE / "assets" / "tokenizer_mbert_cased").resolve()
    assert model_dir.is_relative_to((HERE / "runs").resolve())
    assert tokenizer_dir == (HERE / "assets/tokenizer_mbert_cased").resolve()
    assert sha(model_dir / "model.safetensors") == decision["selected_run"]["model_sha256"]
    assert sha(tokenizer_dir / "tokenizer.json") == contract["tokenizer_json_sha256"]
    config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    assert config["id2label"] == {"0": "REAL", "1": "FALSA"}
    assert config["label2id"] == {"REAL": 0, "FALSA": 1}
    return decision, model_dir, tokenizer_dir


def classify(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("El texto de la noticia debe contener caracteres no vacíos")
    decision, model_dir, tokenizer_dir = load_frozen_candidate()
    contract = decision["inference_contract"]
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir, local_files_only=True)
    total_tokens = len(tokenizer.encode(text, add_special_tokens=False)) + tokenizer.num_special_tokens_to_add(pair=False)
    encoded = tokenizer(text, truncation=True, max_length=contract["max_length"], return_tensors="pt")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True).to(device).eval()
    encoded = {name: value.to(device) for name, value in encoded.items()}
    with torch.inference_mode():
        if device == "cuda" and torch.cuda.is_bf16_supported():
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(**encoded).logits
        else:
            logits = model(**encoded).logits
    probabilities = logits.float().softmax(dim=-1)[0].cpu().tolist()
    threshold = contract["fake_probability_threshold"]
    return {"prediccion": "FALSA" if probabilities[1] >= threshold else "REAL",
            "probabilidades_sin_calibrar": {"REAL": probabilities[0], "FALSA": probabilities[1]},
            "umbral": threshold, "tokens_originales": total_tokens,
            "tokens_utilizados": int(encoded["input_ids"].shape[1]),
            "longitud_maxima": contract["max_length"],
            "texto_recortado": total_tokens > contract["max_length"], "dispositivo": device,
            "modelo": (f"mBERT_BiLSTM_{decision['selected_run']['arm']}_"
                       f"len{decision['selected_run']['length']}_seed{decision['selected_run']['seed']}"),
            "nota": "Clasificación textual experimental; no verifica los hechos de la noticia."}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Prueba manual del nuevo mBERT experimental")
    parser.add_argument("--texto", help="Texto completo, con título incluido si existe")
    parser.add_argument("--archivo-texto", type=Path, help="Archivo UTF-8 con texto completo")
    parser.add_argument("--titulo", help="Título para combinar con el cuerpo en una sola secuencia")
    parser.add_argument("--cuerpo", help="Cuerpo escrito en el comando")
    parser.add_argument("--archivo-cuerpo", type=Path, help="Archivo UTF-8 con el cuerpo")
    args = parser.parse_args()
    full_modes = int(args.texto is not None) + int(args.archivo_texto is not None)
    body_modes = int(args.cuerpo is not None) + int(args.archivo_cuerpo is not None)
    if full_modes + body_modes != 1:
        parser.error("Use exactamente una opción: --texto, --archivo-texto, --cuerpo o --archivo-cuerpo")
    if full_modes and args.titulo is not None:
        parser.error("--texto y --archivo-texto ya incluyen el título; no agregue --titulo")
    if args.texto is not None:
        text = args.texto
    elif args.archivo_texto is not None:
        text = args.archivo_texto.read_text(encoding="utf-8")
    else:
        body = args.cuerpo if args.cuerpo is not None else args.archivo_cuerpo.read_text(encoding="utf-8")
        text = (args.titulo.strip() + " " + body.strip()) if args.titulo and args.titulo.strip() else body
    print(json.dumps(classify(text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
