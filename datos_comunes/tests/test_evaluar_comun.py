"""Pruebas del evaluador común.

Uso: bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluar_comun import (  # noqa: E402
    ajustar_temperatura, bootstrap_pareado, ece, evaluar_configuracion, metricas, softmax_falsa,
    tabla_niveles,
)


class MetricasTests(unittest.TestCase):
    def test_matriz_y_falsas_alarmas(self):
        m = metricas([0, 0, 0, 1, 1], [0.9, 0.1, 0.2, 0.8, 0.3])
        self.assertEqual(m["matriz_confusion_real_falsa"], [[2, 1], [1, 1]])
        self.assertAlmostEqual(m["tasa_falsas_alarmas"], 1 / 3)
        self.assertAlmostEqual(m["precision_falsa"], 0.5)
        self.assertAlmostEqual(m["recall_falsa"], 0.5)

    def test_ece_perfecto_y_malo(self):
        y = np.array([0, 1] * 50)
        self.assertAlmostEqual(ece(y, np.full(100, 0.5)), 0.0)
        self.assertAlmostEqual(ece(np.ones(10), np.full(10, 0.95)), 0.05)

    def test_temperatura_recupera_escala(self):
        rng = np.random.default_rng(0)
        z = rng.normal(0, 2, 20000)
        y = (rng.random(20000) < 1 / (1 + np.exp(-z))).astype(int)
        t = ajustar_temperatura(np.zeros_like(z), z * 3, y)
        self.assertAlmostEqual(t, 3.0, delta=0.15)
        self.assertTrue(np.allclose(softmax_falsa([0.0], [2.0], 2.0), 1 / (1 + np.exp(-1))))

    def test_niveles_igual_que_la_extension(self):
        # Math.round: 0,204 → 20 % «Muy probablemente verdadero»; 0,205 → 21 % «Probablemente verdadero».
        filas = tabla_niveles([0.204, 0.205, 0.4049, 0.405, 0.8, 0.805, 1.0], [0, 0, 0, 0, 1, 1, 1])
        self.assertEqual([f["fragmentos"] for f in filas], [1, 2, 1, 1, 2])

    def test_niveles(self):
        filas = tabla_niveles([0.1, 0.1, 0.9, 0.9, 0.5], [0, 1, 1, 1, 0])
        self.assertEqual([f["fragmentos"] for f in filas], [2, 0, 1, 0, 2])
        self.assertAlmostEqual(filas[0]["pct_falsas"], 0.5)
        self.assertFalse(filas[0]["dentro_objetivo"])
        self.assertTrue(filas[4]["dentro_objetivo"])

    def test_seleccion_media_de_pliegues(self):
        filas = []
        for semilla in (42, 43):
            for pliegue in ("F1", "F2", "F3"):
                for i in range(20):
                    y = i % 2
                    p = (0.9 if y else 0.1) if pliegue != "F3" else 0.6
                    filas.append({"id_fragmento": f"{pliegue}{i}#0", "id_articulo": f"{pliegue}{i}",
                                  "fuente": pliegue, "etiqueta_falsa": y, "semilla": semilla,
                                  "pliegue": pliegue, "p": p})
        r = evaluar_configuracion(pd.DataFrame(filas), bootstrap=False)
        # F1 y F2 perfectos; F3 todo «falsa» => F1 macro 1/3.
        self.assertAlmostEqual(r["seleccion"]["f1_macro_articulo_media"], (1 + 1 + 1 / 3) / 3)
        self.assertTrue(r["seleccion"]["completo"])

    def test_bootstrap_pareado(self):
        a = pd.DataFrame({"id_articulo": list("abcd"), "etiqueta_falsa": [0, 1, 0, 1], "fuente": "x",
                          "p": [0.1, 0.9, 0.2, 0.8]})
        b = a.assign(p=[0.9, 0.1, 0.8, 0.2])
        r = bootstrap_pareado(a, b, repeticiones=200)
        self.assertAlmostEqual(r["diferencia"], 1.0)


if __name__ == "__main__":
    unittest.main()
