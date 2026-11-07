"""Ejecuta B0–B8 del plan del BiLSTM en orden y aplica la regla de decisión fijada.

Uso: bilstm/.venv/bin/python bilstm/plan_comun.py
Cada experimento cambia una sola cosa respecto al ganador vigente. Las corridas ya hechas
se reutilizan. Escribe `datasets/comun_v1_corridas/bilstm/decisiones.json`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from decidir_comun import CORRIDAS, cargar, decidir, fila

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "bilstm/.venv/bin/python"
REGISTRO = CORRIDAS / "bilstm/decisiones.json"

# (id, descripción, cambio sobre los argumentos del ganador, es brazo)
EXPERIMENTOS = [
    ("B1", "Pooling max + media", {"pooling": "maxmedia"}, False),
    ("B2", "Pooling con atención aditiva", {"pooling": "atencion"}, False),
    ("B3", "Embeddings congelados 3 épocas, después lr × 0,1",
     {"congelar-embeddings": "3", "lr-embeddings": "0.1"}, False),
    ("B4", "Tamaño oculto 128", {"hidden-dim": "128"}, False),
    ("B5", "Brazo +satira", {"brazo+": "satira"}, True),
    ("B6", "Brazo +usmsc", {"brazo+": "usmsc"}, True),
    ("B7", "Brazo +politica", {"brazo+": "politica"}, True),
    ("B8", "Máximo de 320 tokens", {"max-tokens": "320"}, False),
]


def argumentos(config: dict) -> list[str]:
    salida = []
    for clave, valor in config.items():
        if clave == "brazo":
            if valor:
                salida += ["--brazo", *valor]
        else:
            salida += [f"--{clave}", str(valor)]
    return salida


def aplicar(config: dict, cambio: dict) -> dict:
    nuevo = {k: (list(v) if isinstance(v, list) else v) for k, v in config.items()}
    for clave, valor in cambio.items():
        if clave == "brazo+":
            nuevo["brazo"] = nuevo.get("brazo", []) + [valor]
        else:
            nuevo[clave] = valor
    return nuevo


def correr(nombre: str, config: dict) -> None:
    with (CORRIDAS / "bilstm" / f"{nombre}.log").open("a") as log:
        subprocess.run([str(PYTHON), str(ROOT / "bilstm/serie_comun.py"), nombre, "--", *argumentos(config)],
                       check=True, stdout=log, stderr=subprocess.STDOUT)


def main() -> None:
    ganador, config = "B0", {"brazo": []}
    correr("B0", config)
    registro = [{"id": "B0", "descripcion": "Receta actual con comun_v1", "config": config,
                 "metricas": fila("B0", cargar("B0")), "decision": "línea base", "ganador_despues": "B0"}]
    b1_adoptado = False
    for ident, descripcion, cambio, brazo in EXPERIMENTOS:
        if ident == "B2" and not b1_adoptado:
            registro.append({"id": ident, "descripcion": descripcion, "decision": "no se ejecuta: B1 no se adoptó",
                             "ganador_despues": ganador})
            continue
        candidata = aplicar(config, cambio)
        correr(ident, candidata)
        c, r = fila(ident, cargar(ident)), fila(ganador, cargar(ganador))
        d = decidir(c, r, brazo)
        entrada = {"id": ident, "descripcion": descripcion, "config": candidata, "frente_a": ganador,
                   "metricas": c, "regla": d, "decision": "adoptado" if d["adopta"] else "rechazado"}
        if d["adopta"]:
            ganador, config = ident, candidata
            if ident == "B1":
                b1_adoptado = True
        entrada["ganador_despues"] = ganador
        registro.append(entrada)
        REGISTRO.write_text(json.dumps({"ganador": ganador, "config_ganadora": config,
                                        "registro": registro}, ensure_ascii=False, indent=2), "utf-8")
        print(ident, entrada["decision"], f"F1 {c['f1']:.3f} vs {r['f1']:.3f}", flush=True)
    REGISTRO.write_text(json.dumps({"ganador": ganador, "config_ganadora": config, "registro": registro},
                                   ensure_ascii=False, indent=2), "utf-8")
    print("Ganador:", ganador, config)


if __name__ == "__main__":
    main()
