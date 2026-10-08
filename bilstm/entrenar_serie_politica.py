"""Entrena variantes fastText con 0, 25 y 50 % de política y tres semillas.

Requiere GPU CUDA. Conserva los checkpoints existentes y rechaza salidas parciales.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
TRAINER = ROOT / "bilstm/preentrenados/entrenar.py"
EMBEDDINGS = ROOT / "datasets/embeddings_preentrenados/cc.es.300.vec.gz"
INPUTS = ROOT / "datasets/experimentos_balanceados"
OUTPUTS = ROOT / "datasets/modelos_balanceados/serie_politica"
JOBS = (
    ("pequeno_mejorado", 43), ("pequeno_mejorado", 44),
    ("pequeno_politica_25", 42), ("pequeno_politica_25", 43),
    ("pequeno_politica_25", 44),
    ("grande_balanceado", 43), ("grande_balanceado", 44),
)


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no disponible; la serie requiere GPU")
    if not EMBEDDINGS.is_file():
        raise FileNotFoundError(EMBEDDINGS)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    for variant, seed in JOBS:
        output = OUTPUTS / f"{variant}_fasttext_cc300_s{seed}"
        if output.exists():
            if (output / "mejor_modelo.pt").exists() and (output / "resultados.json").exists():
                print(f"Ya completo: {output}", flush=True)
                continue
            raise FileExistsError(f"Salida parcial; revisar antes de continuar: {output}")
        command = [sys.executable, str(TRAINER), "--input", str(INPUTS / variant),
                   "--output", str(output), "--embeddings", str(EMBEDDINGS),
                   "--source", "fasttext_cc", "--device", "cuda",
                   "--epochs", "20", "--patience", "4", "--max-len", "192",
                   "--batch-size", "32", "--seed", str(seed)]
        print(f"\nENTRENANDO {variant} semilla {seed}", flush=True)
        subprocess.run(command, check=True, cwd=ROOT)
    print("SERIE COMPLETA", flush=True)


if __name__ == "__main__":
    main()
