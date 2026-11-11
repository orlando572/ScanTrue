"""La prueba congelada sigue cerrada por defecto y solo se abre una vez.

Uso: bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comun import leer  # noqa: E402
from prueba_congelada import comprobar_una_vez  # noqa: E402


class PruebaCongeladaTests(unittest.TestCase):
    def test_leer_sigue_cerrado_por_defecto(self):
        with self.assertRaises(PermissionError):
            leer("fragmentos_prueba_congelada.csv")

    def test_hace_falta_la_opcion_explicita(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with self.assertRaises(SystemExit):
                comprobar_una_vez(Path(carpeta) / "nueva", abrir=False)
            comprobar_una_vez(Path(carpeta) / "nueva", abrir=True)

    def test_no_se_repite(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with self.assertRaises(SystemExit):
                comprobar_una_vez(Path(carpeta), abrir=True)


if __name__ == "__main__":
    unittest.main()
