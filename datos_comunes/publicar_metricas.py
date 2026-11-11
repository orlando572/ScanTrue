"""Publica las métricas que muestra la extensión (backend/metrics/*.json) para los modelos de producción.

Uso:
  bilstm/.venv/bin/python datos_comunes/publicar_metricas.py

Usa las predicciones fuera de pliegue de la calibración conjunta
(`datasets/comun_v1_corridas/calibracion/predicciones_combinadas_fuera_de_pliegue.csv`): cada fuente la
predice un modelo que no la vio al entrenar. Las métricas son por artículo (media de sus fragmentos),
con umbral 0,5. La temperatura no cambia la clase predicha, solo la probabilidad.
Si ya se evaluó la prueba congelada (`datasets/comun_v1_corridas/prueba_congelada/`), se añade como
dos evaluaciones más: toda la prueba y solo FalleDesinfo, la única fuente que ningún modelo vio.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import PLIEGUES, ROOT  # noqa: E402
from evaluar_comun import metricas, por_articulo  # noqa: E402

CALIBRACION = ROOT / "datasets/comun_v1_corridas/calibracion"
CONGELADA = ROOT / "datasets/comun_v1_corridas/prueba_congelada/probabilidades_calibradas.csv"
SALIDA = ROOT / "backend/metrics"
ARCHIVOS = {"bilstm": "evaluaciones.json", "mbert": "mbert_evaluaciones.json"}
CONTRATOS = {"bilstm": ROOT / "datasets/bilstm_produccion/modelo/contrato.json",
             "mbert": ROOT / "datasets/mbert_produccion/modelo/contrato.json"}
NOMBRES = {"bilstm": "BiLSTM B6", "mbert": "BETO M3b"}


def evaluacion(frame: pd.DataFrame, columna: str, conjunto: str, fuente: str) -> dict:
    articulos = por_articulo(frame, columna)
    m = metricas(articulos.y, articulos.p)
    (tn, fp), (fn, tp) = m["matriz_confusion_real_falsa"]
    return {
        "conjunto": conjunto,
        "n": int(len(articulos)),
        # orden_clases = [falsa, real]: filas = etiqueta, columnas = predicción.
        "matriz_confusion": [[tp, fn], [fp, tn]],
        "exactitud": (tp + tn) / len(articulos),
        "precision_falsa": m["precision_falsa"],
        "recall_falsa": m["recall_falsa"],
        "f1_falsa": m["f1_falsa"],
        "f1_macro": m["f1_macro"],
        "fuente": fuente,
    }


def publicar(modelo: str, predicciones: pd.DataFrame, combinacion: dict,
             congelada: pd.DataFrame | None = None) -> dict:
    contrato = json.loads(CONTRATOS[modelo].read_text("utf-8"))
    columna = f"p_{modelo}"
    origen = f"datasets/comun_v1_corridas/calibracion/predicciones_combinadas_fuera_de_pliegue.csv#{columna}"
    evaluaciones = [evaluacion(predicciones, columna, "validacion_por_fuente_articulos", origen)]
    for pliegue, fuente in PLIEGUES.items():
        sub = predicciones[predicciones.pliegue == pliegue]
        evaluaciones.append(evaluacion(sub, columna, f"fuente_no_vista_{fuente}", f"{origen}&pliegue={pliegue}"))
    if congelada is not None:
        origen_c = f"datasets/comun_v1_corridas/prueba_congelada/probabilidades_calibradas.csv#{columna}"
        evaluaciones.append(evaluacion(congelada, columna, "prueba_congelada", origen_c))
        nueva = congelada[congelada.fuente == "falledesinfo"]
        evaluaciones.append(evaluacion(nueva, columna, "prueba_congelada_falledesinfo",
                                       f"{origen_c}&fuente=falledesinfo"))
    semilla = combinacion["semillas"][modelo]
    return {
        "modelo": modelo,
        "version": contrato["version"],
        "orden_clases": ["falsa", "real"],
        "evaluaciones": evaluaciones,
        "limitaciones": [
            f"{NOMBRES[modelo]}. Validación dejando una fuente fuera (v1, FakeDeS, Polyglot): cada fuente la "
            f"predice un modelo entrenado sin ella (semilla {semilla}). El modelo de producción se entrenó "
            "después con todo el desarrollo, así que estas cifras lo aproximan, no lo miden.",
            "Métricas por artículo (media de las probabilidades de sus fragmentos) con umbral 0,5. "
            + ("La prueba congelada se evaluó una sola vez con el modelo de producción (11 nov 2026). Sus artículos "
               "de v1, FakeDeS y Polyglot son de fuentes que el modelo sí vio al entrenar, por eso sus cifras son más "
               "altas que las de fuentes no vistas. FalleDesinfo es la única fuente nueva: allí no detectó ninguna "
               "de las 10 falsas (32 artículos)." if congelada is not None else
               "La prueba congelada, nunca abierta, se evaluará una sola vez y se añadirá aquí."),
            f"La probabilidad está calibrada con temperatura T = {contrato['temperatura']} y el resultado "
            f"unificado combina BETO (80 %) y BiLSTM (20 %) ({combinacion['version']}). Mide la confianza "
            "del clasificador según el estilo del texto; no verifica hechos.",
        ],
    }


def main() -> None:
    predicciones = pd.read_csv(CALIBRACION / "predicciones_combinadas_fuera_de_pliegue.csv",
                               dtype={"id_fragmento": str, "pliegue": str})
    combinacion = json.loads((ROOT / "datasets/combinacion_produccion/combinacion.json").read_text("utf-8"))
    congelada = pd.read_csv(CONGELADA, dtype={"id_fragmento": str}) if CONGELADA.exists() else None
    for modelo, archivo in ARCHIVOS.items():
        datos = publicar(modelo, predicciones, combinacion, congelada)
        (SALIDA / archivo).write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(modelo, [(e["conjunto"], e["n"], round(e["f1_macro"], 3)) for e in datos["evaluaciones"]])


if __name__ == "__main__":
    main()
