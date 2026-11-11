"""Referencias obligatorias del plan común §4.4, con el mismo protocolo que los modelos.

1. Solo longitud: regresión logística sobre el número de tokens del fragmento.
2. TF-IDF de caracteres 3–5 + regresión logística, con los mismos pesos por muestra.

Uso: bilstm/.venv/bin/python datos_comunes/referencias.py --salida datasets/comun_v1_corridas/referencias
Entrena con el entrenamiento de cada pliegue y predice la fuente que queda fuera.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import PLIEGUES, leer, particiones  # noqa: E402


def pesos_balanceados(frame: pd.DataFrame) -> np.ndarray:
    """peso por artículo/fuente × factor que iguala el peso total de las dos clases."""
    peso = frame.peso.to_numpy(float)
    y = frame.etiqueta_falsa.to_numpy(int)
    total = peso.sum()
    factor = {c: total / (2 * peso[y == c].sum()) for c in (0, 1)}
    return peso * np.vectorize(factor.get)(y)


def longitud(entreno: pd.DataFrame, prueba: pd.DataFrame) -> np.ndarray:
    def x(f):
        return np.log(f.tokens_bilstm.to_numpy(float))[:, None]
    modelo = LogisticRegression(max_iter=1000)
    modelo.fit(x(entreno), entreno.etiqueta_falsa, sample_weight=pesos_balanceados(entreno))
    return modelo.decision_function(x(prueba))


def tfidf(entreno: pd.DataFrame, prueba: pd.DataFrame) -> np.ndarray:
    vector = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True,
                             max_features=300000)
    xe = vector.fit_transform(entreno.texto)
    modelo = LogisticRegression(max_iter=2000, C=1.0)
    modelo.fit(xe, entreno.etiqueta_falsa, sample_weight=pesos_balanceados(entreno))
    return modelo.decision_function(vector.transform(prueba.texto))


REFERENCIAS = {"ref_longitud": longitud, "ref_tfidf_char35": tfidf}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    desarrollo = leer("fragmentos_desarrollo.csv")
    for nombre, funcion in REFERENCIAS.items():
        filas = []
        for pliegue in PLIEGUES:
            p = particiones(pliegue, desarrollo=desarrollo)
            z = funcion(p["entrenamiento"], p["validacion"])
            filas.append(pd.DataFrame({
                "id_fragmento": p["validacion"].id_fragmento, "modelo": nombre,
                "configuracion": "base", "semilla": 42, "pliegue": pliegue,
                "logit_real": 0.0, "logit_falsa": z, "prob_falsa": 1 / (1 + np.exp(-z))}))
        destino = args.salida / nombre
        destino.mkdir(parents=True, exist_ok=True)
        pd.concat(filas).to_csv(destino / "predicciones.csv", index=False)
        print(nombre, "->", destino / "predicciones.csv")


if __name__ == "__main__":
    main()
