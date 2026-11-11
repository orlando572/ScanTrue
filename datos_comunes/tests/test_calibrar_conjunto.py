"""Pruebas de la calibración conjunta con datos sintéticos.

Uso: bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibrar_conjunto import (  # noqa: E402
    cargar_fuera_de_pliegue, combinar, discrepancia, emparejar, metodos, por_fuente, sigmoide, temperatura,
)

FUENTES = {"F1": "v1", "F2": "fakedes", "F3": "polyglot"}


def desarrollo(n_por_fuente: int = 200, semilla: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    filas = []
    for pliegue, fuente in FUENTES.items():
        for i in range(n_por_fuente):
            filas.append({"id_fragmento": f"{fuente}{i}#0", "id_articulo": f"{fuente}{i}", "fuente": fuente,
                          "etiqueta_falsa": int(rng.random() < 0.5), "pliegue": pliegue})
    return pd.DataFrame(filas)


def predicciones(dev: pd.DataFrame, escala: float, ruido: float, semilla: int, modelo: str) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    z = (2 * dev.etiqueta_falsa - 1) * 1.0 + rng.normal(0, ruido, len(dev))
    z = z * escala
    return pd.DataFrame({"id_fragmento": dev.id_fragmento, "modelo": modelo, "configuracion": "X",
                         "semilla": 42, "pliegue": dev.pliegue, "logit_real": 0.0, "logit_falsa": z,
                         "prob_falsa": sigmoide(z), "columna_extra": 1})


class CombinacionTests(unittest.TestCase):
    def test_combinar_pesos_extremos_y_formula(self):
        zb, zm = np.array([4.0, -2.0]), np.array([1.0, 3.0])
        self.assertTrue(np.allclose(combinar(zb, zm, 2.0, 1.0, 0.0), sigmoide(zm)))
        self.assertTrue(np.allclose(combinar(zb, zm, 2.0, 1.0, 1.0), sigmoide(zb / 2)))
        self.assertTrue(np.allclose(combinar(zb, zm, 2.0, 1.0, 0.2), sigmoide(0.2 * zb / 2 + 0.8 * zm)))
        with self.assertRaises(ValueError):
            combinar(zb, zm, 1.0, 1.0, 1.5)

    def test_discrepancia(self):
        marca = discrepancia([0.3, 0.45, 0.9, 0.2], [0.8, 0.55, 0.95, 0.75], 0.4)
        self.assertEqual(marca.tolist(), [True, False, False, True])

    def test_temperatura_recupera_escala(self):
        rng = np.random.default_rng(1)
        z = rng.normal(0, 2, 20000)
        y = (rng.random(20000) < sigmoide(z)).astype(int)
        self.assertAlmostEqual(temperatura(z * 4, y), 4.0, delta=0.2)


class DatosTests(unittest.TestCase):
    def setUp(self):
        self.dev = desarrollo()
        self.carpeta = tempfile.TemporaryDirectory()
        self.ruta = Path(self.carpeta.name) / "pred.csv"

    def tearDown(self):
        self.carpeta.cleanup()

    def test_carga_ignora_columnas_extra_y_rechaza_congelada(self):
        pred = predicciones(self.dev, 3.0, 1.0, 0, "bilstm")
        pred.to_csv(self.ruta, index=False)
        d = cargar_fuera_de_pliegue(self.ruta, 42, self.dev)
        self.assertEqual(len(d), len(self.dev))
        self.assertTrue(np.allclose(d.z, pred.logit_falsa))
        pred.loc[0, "pliegue"] = "congelada"
        pred.to_csv(self.ruta, index=False)
        with self.assertRaises(PermissionError):
            cargar_fuera_de_pliegue(self.ruta, 42, self.dev)

    def test_carga_rechaza_fuente_equivocada(self):
        pred = predicciones(self.dev, 1.0, 1.0, 0, "bilstm")
        pred.loc[0, "pliegue"] = "F2"
        pred.to_csv(self.ruta, index=False)
        with self.assertRaises(ValueError):
            cargar_fuera_de_pliegue(self.ruta, 42, self.dev)

    def test_emparejar_exige_mismo_desarrollo(self):
        b = predicciones(self.dev, 1.0, 1.0, 0, "bilstm")
        b.to_csv(self.ruta, index=False)
        cb = cargar_fuera_de_pliegue(self.ruta, 42, self.dev)
        with self.assertRaises(ValueError):
            emparejar(cb, cb.iloc[:-1], self.dev)
        self.assertEqual(len(emparejar(cb, cb, self.dev)), len(self.dev))

    def test_por_fuente_no_usa_la_fuente_evaluada(self):
        b = predicciones(self.dev, 6.0, 2.0, 1, "bilstm")
        m = predicciones(self.dev, 1.5, 0.5, 2, "mbert")
        b.to_csv(self.ruta, index=False)
        cb = cargar_fuera_de_pliegue(self.ruta, 42, self.dev)
        m.to_csv(self.ruta, index=False)
        cm = cargar_fuera_de_pliegue(self.ruta, 42, self.dev)
        d = emparejar(cb, cm, self.dev)
        vistos = []

        def espia(tr, te):
            vistos.append((set(tr.pliegue), set(te.pliegue)))
            return np.full(len(te), 0.5)

        probs = por_fuente(d, {"espia": espia, **metodos(0.2)})
        for entreno, prueba in vistos:
            self.assertEqual(len(prueba), 1)
            self.assertFalse(entreno & prueba)
        # El modelo con menos ruido debe dominar: la combinación ordena mejor que el BiLSTM solo.
        y = d.etiqueta_falsa.to_numpy()
        auc = lambda p: np.mean([pi > pj for pi in p[y == 1][:200] for pj in p[y == 0][:200]])
        self.assertGreater(auc(probs["combinacion_bilstm_0.20"]), auc(probs["bilstm_calibrado"]))
        # La regresión con pesos no negativos nunca da probabilidades que bajen al subir un logit.
        self.assertTrue(np.all((probs["regresion_logistica_pesos_no_negativos"] >= 0)
                               & (probs["regresion_logistica_pesos_no_negativos"] <= 1)))


if __name__ == "__main__":
    unittest.main()
