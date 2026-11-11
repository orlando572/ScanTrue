"""Etapa final del plan del BiLSTM (02_PLAN_BILSTM.md §4–§5, puntos 1–4).

Uso: bilstm/.venv/bin/python bilstm/final_comun.py [--ganador B6 --motivo "…"]
Con --ganador se elige a mano una configuración del registro en lugar del ganador de la regla;
el motivo queda anotado en el contrato y en el resumen.

1. Lee la configuración ganadora de `decisiones.json`.
2. Compara el ganador con la referencia TF-IDF (bootstrap pareado por artículo).
3. Entrena el modelo final con todo el desarrollo, 3 semillas, con la mediana de las épocas
   elegidas en los pliegues.
4. Decide si promediar semillas (ganancia fuera de pliegue ≥ 0,01) y ajusta la temperatura T
   con las predicciones fuera de pliegue. T queda **provisional** hasta calibrar junto con mBERT.
5. Guarda predicciones fuera de pliegue, tabla de niveles y `contrato.json`.
No abre la prueba congelada.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "datos_comunes"))
from comun import manifiesto, sha256  # noqa: E402
from evaluar_comun import (  # noqa: E402
    ajustar_temperatura, bootstrap_pareado, cargar_predicciones, evaluar_configuracion, metricas,
    por_articulo, softmax_falsa, tabla_niveles,
)

CORRIDAS = ROOT / "datasets/comun_v1_corridas"
FINAL = CORRIDAS / "bilstm/final"
PYTHON = ROOT / "bilstm/.venv/bin/python"
SEMILLAS = (42, 43, 44)


def argumentos(config: dict) -> list[str]:
    salida = []
    for clave, valor in config.items():
        if clave == "brazo":
            if valor:
                salida += ["--brazo", *valor]
        else:
            salida += [f"--{clave}", str(valor)]
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ganador", help="ID del registro (p. ej. B6) que sustituye al ganador de la regla")
    parser.add_argument("--motivo", default="", help="Motivo de la elección manual (obligatorio con --ganador)")
    args = parser.parse_args()
    decisiones = json.loads((CORRIDAS / "bilstm/decisiones.json").read_text("utf-8"))
    ganador, config = decisiones["ganador"], decisiones["config_ganadora"]
    eleccion = {"ganador_regla": ganador, "manual": False}
    if args.ganador and args.ganador != ganador:
        if not args.motivo:
            raise SystemExit("--ganador necesita --motivo")
        fila = next(r for r in decisiones["registro"] if r["id"] == args.ganador)
        ganador, config = args.ganador, fila["config"]
        eleccion.update(manual=True, ganador_elegido=ganador, motivo=args.motivo)
    carpeta = CORRIDAS / "bilstm" / ganador
    rutas = [carpeta / f"{p}_s{s}/predicciones.csv" for s in SEMILLAS for p in ("F1", "F2", "F3")]
    epocas = [json.loads((r.parent / "resultados.json").read_text())["mejor_epoca"] for r in rutas]
    epocas_final = int(np.median(epocas))

    # Predicciones fuera de pliegue del ganador (todas las semillas) y su media de logits.
    oof = cargar_predicciones(rutas)
    media = (oof.groupby(["id_fragmento", "id_articulo", "fuente", "etiqueta_falsa", "pliegue"], as_index=False)
             [["logit_real", "logit_falsa"]].mean())
    media["p"] = softmax_falsa(media.logit_real, media.logit_falsa)
    media["semilla"] = 0
    individual = evaluar_configuracion(oof, bootstrap=False)["seleccion"]["f1_macro_articulo_media"]
    promediada = evaluar_configuracion(media, bootstrap=False)["seleccion"]["f1_macro_articulo_media"]
    promediar = promediada - individual >= 0.01

    # Comparación con TF-IDF (§4): misma métrica y bootstrap pareado por artículo.
    tfidf = cargar_predicciones([CORRIDAS / "referencias/ref_tfidf_char35/predicciones.csv"])
    base = media if promediar else oof[oof.semilla == 42]
    tfidf_sel = evaluar_configuracion(tfidf, bootstrap=False)["seleccion"]["f1_macro_articulo_media"]
    comparacion = {"bilstm_seleccion": promediada if promediar else individual,
                   "tfidf_seleccion": tfidf_sel,
                   "diferencia_seleccion": (promediada if promediar else individual) - tfidf_sel,
                   "bootstrap_pareado_fuera_de_pliegue": bootstrap_pareado(base, tfidf)}

    # Temperatura con las predicciones fuera de pliegue (fragmento), sin tocar el umbral.
    calibrar = base
    temperatura = ajustar_temperatura(calibrar.logit_real, calibrar.logit_falsa, calibrar.etiqueta_falsa)
    p_cal = softmax_falsa(calibrar.logit_real, calibrar.logit_falsa, temperatura)
    p_sin = softmax_falsa(calibrar.logit_real, calibrar.logit_falsa)
    arts_cal = por_articulo(calibrar.assign(p=p_cal))
    calibracion = {
        "temperatura": temperatura, "fragmentos": int(len(calibrar)),
        "sin_calibrar": metricas(calibrar.etiqueta_falsa, p_sin),
        "calibrado": metricas(calibrar.etiqueta_falsa, p_cal),
        "calibrado_articulo": metricas(arts_cal.y, arts_cal.p),
        "niveles_sin_calibrar": tabla_niveles(p_sin, calibrar.etiqueta_falsa),
        "niveles_calibrados": tabla_niveles(p_cal, calibrar.etiqueta_falsa),
        "niveles_calibrados_por_fuente": {
            f: tabla_niveles(p_cal[calibrar.fuente.to_numpy() == f],
                             calibrar.etiqueta_falsa.to_numpy()[calibrar.fuente.to_numpy() == f])
            for f in sorted(calibrar.fuente.unique())},
    }

    # Modelo final con todo el desarrollo.
    FINAL.mkdir(parents=True, exist_ok=True)
    semillas_final = SEMILLAS if promediar else (42,)
    for semilla in semillas_final:
        salida = FINAL / f"todo_s{semilla}"
        if not (salida / "modelo.pt").exists():
            subprocess.run([str(PYTHON), str(ROOT / "bilstm/entrenar_comun.py"), "--pliegue", "todo",
                            "--semilla", str(semilla), "--configuracion", ganador, "--salida", str(salida),
                            "--epocas-fijas", str(epocas_final), *argumentos(config)], check=True,
                           stdout=(FINAL / f"todo_s{semilla}.log").open("w"), stderr=subprocess.STDOUT)

    # Entregables.
    oof.drop(columns=["p", "pliegue_dato"]).to_csv(FINAL / "predicciones_fuera_de_pliegue.csv", index=False)
    media.drop(columns=["p", "semilla"]).assign(modelo="bilstm", configuracion=f"{ganador}_media_semillas") \
        .to_csv(FINAL / "predicciones_fuera_de_pliegue_media_semillas.csv", index=False)
    fecha = dt.date.today().strftime("%Y%m%d")
    contrato = {
        "modelo": "bilstm", "version": f"{manifiesto()['version']}_{ganador}_{fecha}", "eleccion": eleccion,
        "etiquetas": {"real": 0, "falsa": 1},
        "max_tokens": int(config.get("max-tokens", 192)),
        "pooling": config.get("pooling", "final"), "hidden_dim": int(config.get("hidden-dim", 64)),
        "temperatura": round(temperatura, 4), "temperatura_provisional": True,
        "nota_temperatura": "Ajustada solo con las predicciones fuera de pliegue del BiLSTM; se recalibra "
                            "junto con mBERT (01_PLAN_COMUN.md §5) antes de usarla en el backend.",
        "umbral_falsa": 0.5,
        "semillas": list(semillas_final), "promediar_logits_semillas": promediar,
        "epocas": epocas_final,
        "checkpoints": {f"s{s}": {"ruta": str((FINAL / f"todo_s{s}/modelo.pt").relative_to(ROOT)),
                                  "sha256": sha256(FINAL / f"todo_s{s}/modelo.pt")} for s in semillas_final},
        "sha256_conjunto": manifiesto()["archivos"]["fragmentos_desarrollo.csv"]["sha256"],
    }
    (FINAL / "contrato.json").write_text(json.dumps(contrato, ensure_ascii=False, indent=2), "utf-8")
    resumen = {"ganador": ganador, "eleccion": eleccion, "config": config, "epocas_por_corrida": epocas, "epocas_final": epocas_final,
               "seleccion_semilla_individual_media": individual, "seleccion_media_logits": promediada,
               "promediar_semillas": promediar, "comparacion_tfidf": comparacion, "calibracion": calibracion}
    (FINAL / "resumen_final.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({k: resumen[k] for k in ("ganador", "epocas_final", "seleccion_semilla_individual_media",
                                               "seleccion_media_logits", "promediar_semillas")}, indent=2))
    print(json.dumps(comparacion, indent=2), "\nT =", temperatura)


if __name__ == "__main__":
    main()
