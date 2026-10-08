import unittest

import pandas as pd

from titulares.preparar import prepare_split


class TitularPreparationTests(unittest.TestCase):
    def test_keeps_only_real_headlines_and_replaces_model_input(self):
        source = pd.DataFrame([
            {"dataset": "x", "etiqueta": "0", "titulo": "Titular falso",
             "texto": "Cuerpo largo que no debe entrar"},
            {"dataset": "x", "etiqueta": "1", "titulo": "Titular real",
             "texto": "Otro cuerpo que no debe entrar"},
            {"dataset": "x", "etiqueta": "1", "titulo": " ", "texto": "Sin titular"},
        ])
        frame, report = prepare_split(source)
        self.assertEqual(frame.texto.tolist(), ["Titular falso", "Titular real"])
        self.assertEqual(report["omitidos_sin_titulo"], 1)
        self.assertNotIn("Cuerpo largo que no debe entrar", frame.texto.tolist())


if __name__ == "__main__":
    unittest.main()
