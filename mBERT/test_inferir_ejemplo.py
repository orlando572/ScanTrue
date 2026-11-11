"""Pruebas de contrato para la entrada y una prueba local de inferencia."""

import math
import unittest

from inferir_ejemplo import MAX_LENGTH, inferir, validar_entrada


class TestEntrada(unittest.TestCase):
    def test_rechaza_cuerpo_vacio(self):
        with self.assertRaises(ValueError):
            validar_entrada({"titulo": "Titular", "cuerpo": "   "})

    def test_acepta_cuerpo_sin_titular(self):
        self.assertEqual(validar_entrada({"cuerpo": " Texto "}), ("", "Texto"))

    def test_inferencia_devuelve_probabilidades_validas(self):
        entrada = {"titulo": "Noticia de prueba", "cuerpo": "Este texto comprueba la inferencia local."}
        salida = inferir(entrada)
        probabilidades = salida["probabilidades"]
        self.assertEqual(set(probabilidades), {"REAL", "FALSA"})
        self.assertTrue(all(math.isfinite(v) and 0 <= v <= 1 for v in probabilidades.values()))
        self.assertAlmostEqual(sum(probabilidades.values()), 1.0, places=5)
        self.assertEqual(salida["prediccion"], "FALSA" if probabilidades["FALSA"] >= 0.5 else "REAL")
        self.assertLessEqual(salida["tokens"], MAX_LENGTH)


if __name__ == "__main__":
    unittest.main()
