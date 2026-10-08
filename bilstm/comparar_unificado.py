"""Compara checkpoints existentes sobre las mismas noticias de fuentes reservadas.

Uso: bilstm/.venv/bin/python bilstm/comparar_unificado.py
Lee modelos; no los modifica ni entrena. Separa modelos de noticias y titulares.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import torch

from depurar_y_particionar import related_keys
from entrenar_baseline import metrics
from probar_externo import load_model, predict_texts


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/unificado_total/depurado"
NEW_MODEL = ROOT / "datasets/modelos_bilstm/unificado_depurado/mejor_modelo.pt"
OUTPUT = ROOT / "datasets/experimentos_bilstm/unificado_depurado/comparacion.json"


def old_models() -> list[tuple[str, Path, str, Path]]:
    result = []
    candidates = [
        ROOT / "datasets/modelos_bilstm/sin_politica/mejor_modelo.pt",
        ROOT / "datasets/experimentos_bilstm/sin_politica/modelo.pt",
        ROOT / "datasets/experimentos_bilstm/politica_25/modelo.pt",
        ROOT / "datasets/modelos_titulares/sin_politica/mejor_modelo.pt",
    ]
    candidates += sorted((ROOT / "datasets/experimentos_longitud").glob("t*_s*/mejor_modelo.pt"))
    candidates += sorted((ROOT / "datasets/modelos_preentrenados/noticias_192").glob("*/mejor_modelo.pt"))
    candidates += sorted((ROOT / "datasets/modelos_preentrenados/titulares").glob("*/mejor_modelo.pt"))
    candidates += sorted((ROOT / "datasets/modelos_preentrenados/controles").glob("*/mejor_modelo.pt"))
    for path in candidates:
        if not path.exists():
            continue
        group = "titulares" if "titulares" in str(path) else "noticias"
        if "experimentos_bilstm" in str(path):
            reference = path.parent
        else:
            config = json.loads((path.parent / "config.json").read_text(encoding="utf-8"))
            reference = Path(config["input"])
        result.append((str(path.relative_to(ROOT)), path, group, reference))
    return result


def reference_keys(reference: Path) -> set[str]:
    keys = set()
    for split in ("entrenamiento", "validacion"):
        path = reference / f"{split}.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                keys.update(related_keys({"texto": row.get("texto", ""),
                                          "titulo": row.get("titulo", ""),
                                          "url": row.get("url", "")}))
    return keys


def evaluate(model_path: Path, rows: list[dict], input_field: str, device: str) -> dict:
    model, vocab, max_len, actual_device = load_model(model_path, device)
    probabilities = predict_texts(model, vocab, max_len, actual_device,
                                  [row[input_field] for row in rows], batch_size=64)
    predicted = [0 if value >= 0.5 else 1 for value in probabilities]
    actual = [int(row["etiqueta_binaria"]) for row in rows]
    by_source = {}
    for source in sorted({row["dataset_principal"] for row in rows}):
        indices = [i for i, row in enumerate(rows) if row["dataset_principal"] == source]
        by_source[source] = metrics([actual[i] for i in indices],
                                    [predicted[i] for i in indices])
    result = {"max_len": max_len, "metricas": metrics(actual, predicted),
              "por_fuente": by_source}
    del model
    if actual_device.type == "cuda":
        torch.cuda.empty_cache()
    return result


def build(output: Path, device: str, old_only: bool = False,
          new_only: bool = False) -> dict:
    if not old_only and not NEW_MODEL.exists():
        raise FileNotFoundError(f"El modelo nuevo aún no está listo: {NEW_MODEL}")
    with (DATA / "prueba_fuentes_reservadas.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    models = old_models()
    if not models:
        raise ValueError("No se encontraron checkpoints anteriores")
    references = {str(reference): reference_keys(reference)
                  for reference in dict.fromkeys(reference for _, _, _, reference in models)}
    old_keys = set().union(*references.values())
    clean = [row for row in rows if not set(related_keys(row)).intersection(old_keys)]
    with_title = [row for row in clean if row["titulo"].strip()]
    if not clean or not with_title:
        raise ValueError("No hay noticias comparables tras filtrar solapamientos")
    report = {
        "prueba_original": len(rows),
        "solapadas_con_entrenamiento_o_validacion_anterior": len(rows) - len(clean),
        "prueba_comun_noticias": len(clean), "prueba_comun_titulares": len(with_title),
        "filtro_solapamiento": "texto, titular específico, cuerpo y URL; no detecta todas las paráfrasis",
        "dispositivo": device,
        "modelos_noticias": {}, "modelos_titulares": {},
        "nota": "Los modelos de titulares reciben solo el titular y se comparan en sección separada.",
    }
    report["referencia_siempre_real"] = metrics(
        [int(row["etiqueta_binaria"]) for row in clean], [1] * len(clean))
    output.parent.mkdir(parents=True, exist_ok=True)
    if new_only:
        if not output.exists():
            raise FileNotFoundError("Primero ejecuta la comparación de modelos anteriores")
        previous = json.loads(output.read_text(encoding="utf-8"))
        if previous["prueba_comun_noticias"] != len(clean):
            raise ValueError("La prueba común cambió desde la evaluación anterior")
        report["modelos_noticias"] = previous["modelos_noticias"]
        report["modelos_titulares"] = previous["modelos_titulares"]
    if not old_only:
        report["modelos_noticias"]["nuevo_unificado_128"] = evaluate(
            NEW_MODEL, clean, "texto", device)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, path, group, _ in ([] if new_only else models):
        subset = with_title if group == "titulares" else clean
        field = "titulo" if group == "titulares" else "texto"
        report[f"modelos_{group}"][name] = evaluate(path, subset, field, device)
        print(f"{name}: F1 macro {report[f'modelos_{group}'][name]['metricas']['f1_macro']:.4f}",
              flush=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--old-only", action="store_true")
    mode.add_argument("--new-only", action="store_true")
    args = parser.parse_args()
    report = build(args.output, args.device, args.old_only, args.new_only)
    print(json.dumps({"prueba_comun_noticias": report["prueba_comun_noticias"],
                      "modelos_noticias": {name: value["metricas"]["f1_macro"] for name, value in
                                          report["modelos_noticias"].items()},
                      "modelos_titulares": {name: value["metricas"]["f1_macro"] for name, value in
                                           report["modelos_titulares"].items()}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
