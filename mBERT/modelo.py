"""Modelos base de mBERT (03_PLAN_MBERT.md §3.2): registro, descarga fijada y carga local.

Cada modelo base vive en `datasets/modelos_base/<clave>/` (fuera de Git) con un `origen.json` que
registra el repositorio de Hugging Face, la revisión exacta y el SHA-256 de cada archivo. La carga
es siempre local (`local_files_only=True`) y comprueba esos SHA-256 antes de usar el modelo.

Uso:
  mBERT/.venv/Scripts/python.exe mBERT/modelo.py descargar beto
  mBERT/.venv/Scripts/python.exe mBERT/modelo.py verificar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASES = ROOT / "datasets/modelos_base"
ETIQUETAS = {"real": 0, "falsa": 1}
ID2LABEL = {v: k for k, v in ETIQUETAS.items()}

# Revisión fijada el 10 nov 2026 (la vigente en el Hub ese día). `sha256_pesos` se rellena al
# descargar y desde entonces la carga exige ese valor.
MODELOS: dict[str, dict] = {
    "mbert": {
        "hub_id": "google-bert/bert-base-multilingual-cased",
        "revision": "3f076fdb1ab68d5b2880cb87a0886f315b8146f8",
        "sha256_pesos": "876f584f15ebf14887dec17539c114bb99a032e96b9e72507a51c41e205337fc",
        "parametros_m": 178,
    },
    "beto": {
        "hub_id": "dccuchile/bert-base-spanish-wwm-cased",
        "revision": "c4d86612f51b4f46759c8390d1798c2febe71b93",
        "sha256_pesos": None,
        "parametros_m": 110,
    },
    "roberta_bne": {
        # MarIA. El repositorio oficial está retirado y ya no contiene los pesos (comprobado el
        # 10 nov 2026); BSC-LT/roberta-base-bne no existe. Pendiente de decisión.
        "hub_id": "PlanTL-GOB-ES/roberta-base-bne",
        "revision": "90aa6e695a9a092187bbe57fbd298b9af09dc31b",
        "sha256_pesos": None,
        "parametros_m": 125,
        "no_disponible": "El repositorio oficial de MarIA está retirado y no tiene pesos.",
    },
    "xlmr": {
        "hub_id": "FacebookAI/xlm-roberta-base",
        "revision": "e73636d4f797dec63c3081bb6ed5c7b0bb3f2089",
        "sha256_pesos": None,
        "parametros_m": 278,
    },
}
# Orden de preferencia cuando dos modelos empatan (plan §7): el más pequeño y rápido primero.
PREFERENCIA = ("beto", "roberta_bne", "mbert", "xlmr")

PESOS = "model.safetensors"
ARCHIVOS_TOKENIZADOR = ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt",
                        "vocab.json", "merges.txt", "sentencepiece.bpe.model")


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for bloque in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(bloque)
    return hasher.hexdigest()


def carpeta(clave: str) -> Path:
    if clave not in MODELOS:
        raise ValueError(f"Modelo base desconocido: {clave}")
    return BASES / clave


def origen(ruta: Path) -> dict:
    archivo = ruta / "origen.json"
    if not archivo.exists():
        raise FileNotFoundError(f"Falta {archivo}: descarga el modelo con `modelo.py descargar`")
    return json.loads(archivo.read_text("utf-8"))


def verificar(clave: str) -> dict:
    """Comprueba revisión y SHA-256 de todos los archivos registrados. Devuelve `origen.json`."""
    ruta = carpeta(clave)
    info = origen(ruta)
    esperado = MODELOS[clave]
    if info["hub_id"] != esperado["hub_id"] or info["revision"] != esperado["revision"]:
        raise ValueError(f"{clave}: origen.json no coincide con la revisión fijada en modelo.py")
    for nombre, valor in info["archivos"].items():
        if sha256(ruta / nombre) != valor:
            raise ValueError(f"{clave}: SHA-256 de {nombre} no coincide con origen.json")
    if esperado["sha256_pesos"] and info["archivos"].get(PESOS) != esperado["sha256_pesos"]:
        raise ValueError(f"{clave}: los pesos no son los fijados en modelo.py")
    return info


def descargar(clave: str) -> dict:
    """Descarga config, pesos y tokenizador de la revisión fijada. Si el repositorio solo trae
    `pytorch_model.bin`, lo convierte a safetensors y registra los dos SHA-256."""
    from huggingface_hub import HfApi, hf_hub_download

    esperado = MODELOS[clave]
    if esperado.get("no_disponible"):
        raise RuntimeError(f"{clave}: {esperado['no_disponible']}")
    ruta = carpeta(clave)
    ruta.mkdir(parents=True, exist_ok=True)
    disponibles = {s.rfilename for s in HfApi().model_info(esperado["hub_id"], revision=esperado["revision"]).siblings}
    queridos = ["config.json", *[a for a in ARCHIVOS_TOKENIZADOR if a in disponibles]]
    queridos.append(PESOS if PESOS in disponibles else "pytorch_model.bin")
    for nombre in queridos:
        if not (ruta / nombre).exists():
            hf_hub_download(esperado["hub_id"], nombre, revision=esperado["revision"], local_dir=ruta)
    archivos = {n: sha256(ruta / n) for n in queridos}
    convertido = None
    if PESOS not in disponibles:
        import torch
        from safetensors.torch import save_file

        estado = torch.load(ruta / "pytorch_model.bin", map_location="cpu", weights_only=True)
        save_file({k: v.contiguous() for k, v in estado.items()}, str(ruta / PESOS), metadata={"format": "pt"})
        archivos[PESOS] = sha256(ruta / PESOS)
        convertido = "pytorch_model.bin convertido a model.safetensors en local"
    if esperado["sha256_pesos"] and archivos[PESOS] != esperado["sha256_pesos"]:
        raise ValueError(f"{clave}: los pesos descargados no coinciden con los fijados")
    info = {"hub_id": esperado["hub_id"], "revision": esperado["revision"], "archivos": archivos,
            "conversion": convertido}
    (ruta / "origen.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), "utf-8")
    return info


def resumen(clave: str | None, ruta: Path) -> dict:
    """Datos del modelo base que se guardan en config.json y en el contrato."""
    if clave is None:  # modelo local de pruebas
        return {"clave": None, "ruta": str(ruta), "sha256_pesos": sha256(ruta / PESOS)}
    info = verificar(clave)
    return {"clave": clave, "hub_id": info["hub_id"], "revision": info["revision"],
            "sha256": info["archivos"][PESOS],
            "sha256_tokenizer_json": info["archivos"].get("tokenizer.json")}


def cargar_tokenizador(ruta: Path):
    from transformers import AutoTokenizer

    # fix_mistral_regex solo afecta a tokenizadores con la expresión de Mistral; con BERT cambiaría
    # los IDs (plan §3.2), así que nunca se activa.
    tokenizador = AutoTokenizer.from_pretrained(ruta, local_files_only=True, use_fast=True,
                                                fix_mistral_regex=False)
    if not tokenizador.is_fast:
        raise ValueError("Se necesita el tokenizador rápido")
    return tokenizador


def cargar_modelo(ruta: Path):
    """Modelo base con una cabeza de clasificación nueva; salida 1 = «falsa»."""
    from transformers import AutoModelForSequenceClassification

    return AutoModelForSequenceClassification.from_pretrained(
        ruta, num_labels=2, id2label=ID2LABEL, label2id=ETIQUETAS, local_files_only=True, use_safetensors=True)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("descargar").add_argument("claves", nargs="+", choices=tuple(MODELOS))
    sub.add_parser("verificar").add_argument("claves", nargs="*", choices=tuple(MODELOS))
    args = parser.parse_args(argv)
    for clave in args.claves or [c for c in MODELOS if (carpeta(c) / "origen.json").exists()]:
        info = descargar(clave) if args.comando == "descargar" else verificar(clave)
        print(clave, json.dumps({"revision": info["revision"], "pesos": info["archivos"][PESOS]}))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
