"""Aplica la regla de decisión fijada (plan común §6) entre dos configuraciones del BiLSTM.

Uso: bilstm/.venv/bin/python bilstm/decidir_comun.py CANDIDATA REFERENCIA [--brazo]

Regla: se adopta si la media de F1 macro de artículo (media de pliegues, media de semillas)
sube al menos 0,02 y la tasa de falsas alarmas de artículo no sube más de 2 puntos.
Con --brazo, además debe mejorar F1 macro de artículo en al menos dos de los tres pliegues.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORRIDAS = ROOT / "datasets/comun_v1_corridas"


def cargar(nombre: str) -> dict:
    """Busca la evaluación de una configuración del BiLSTM o de una referencia."""
    for ruta in (CORRIDAS / "bilstm" / nombre / "evaluacion/metricas.json",
                 CORRIDAS / "referencias/evaluacion/metricas.json"):
        if ruta.exists():
            datos = json.loads(ruta.read_text("utf-8"))["configuraciones"]
            for clave, valor in datos.items():
                if clave.split("/", 1)[1] == nombre or clave.split("/", 1)[0] == nombre:
                    return valor
    raise FileNotFoundError(nombre)


def fila(nombre: str, r: dict) -> dict:
    s = r["seleccion"]
    return {"nombre": nombre, "f1": s["f1_macro_articulo_media"], "desv": s["f1_macro_articulo_desv_semillas"],
            "fa": s["falsas_alarmas_articulo_media"],
            "pliegues": {p: v["articulo_f1_macro"]["media"] for p, v in r["por_pliegue"].items()},
            "auc": {p: v["articulo_auc_roc"]["media"] for p, v in r["por_pliegue"].items()}}


def decidir(candidata: dict, referencia: dict, brazo: bool) -> dict:
    sube = candidata["f1"] - referencia["f1"]
    alarmas = candidata["fa"] - referencia["fa"]
    mejoras = sum(candidata["pliegues"][p] > referencia["pliegues"][p] for p in ("F1", "F2", "F3"))
    adopta = sube >= 0.02 and alarmas <= 0.02 and (not brazo or mejoras >= 2)
    return {"delta_f1": sube, "delta_falsas_alarmas": alarmas, "pliegues_que_mejoran": mejoras,
            "adopta": adopta}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidata")
    parser.add_argument("referencia")
    parser.add_argument("--brazo", action="store_true")
    args = parser.parse_args()
    c, r = fila(args.candidata, cargar(args.candidata)), fila(args.referencia, cargar(args.referencia))
    d = decidir(c, r, args.brazo)
    print(json.dumps({"candidata": c, "referencia": r, "decision": d}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
