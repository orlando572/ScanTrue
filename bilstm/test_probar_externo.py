import tempfile
import unittest
from pathlib import Path

import pandas as pd

from probar_externo import evaluate_csv


class ExternalEvaluationTests(unittest.TestCase):
    def test_duplicate_training_text_is_excluded_from_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame([{"texto": "Noticia ya usada para entrenar", "titulo": "",
                           "url": "", "etiqueta": "0"}]).to_csv(root / "entrenamiento.csv", index=False)
            pd.DataFrame([{"texto": "Noticia de validación", "titulo": "",
                           "url": "", "etiqueta": "1"}]).to_csv(root / "validacion.csv", index=False)
            pd.DataFrame([{"texto": "Noticia de prueba anterior", "titulo": "",
                           "url": "", "etiqueta": "1"}]).to_csv(root / "prueba.csv", index=False)
            external = pd.DataFrame([
                {"texto": " noticia ya usada para entrenar ", "etiqueta": "0", "fuente": "A"},
                {"texto": "noticia de prueba anterior", "etiqueta": "1", "fuente": "A"},
                {"texto": "Primera noticia nueva", "etiqueta": "0", "fuente": "B"},
                {"texto": "Segunda noticia nueva", "etiqueta": "1", "fuente": "B"},
            ])
            output, report = evaluate_csv(external, [0.9, 0.1, 0.8, 0.1], root)
            self.assertEqual(report["solapadas_excluidas"], 2)
            self.assertEqual(report["n_evaluadas"], 2)
            self.assertEqual(report["metricas"]["accuracy"], 1.0)
            self.assertEqual(output.solapamiento.tolist(), ["texto", "texto", "", ""])

    def test_conflicting_external_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame([{"texto": "entrenamiento", "titulo": "", "url": ""}]).to_csv(
                root / "entrenamiento.csv", index=False)
            pd.DataFrame([{"texto": "validacion", "titulo": "", "url": ""}]).to_csv(
                root / "validacion.csv", index=False)
            external = pd.DataFrame([
                {"texto": "misma noticia externa", "etiqueta": "0"},
                {"texto": "Misma noticia externa", "etiqueta": "1"},
            ])
            with self.assertRaisesRegex(ValueError, "contradictorias"):
                evaluate_csv(external, [0.8, 0.2], root)

    def test_missing_reference_keeps_predictions_and_marks_overlap_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            external = pd.DataFrame([
                {"texto": "Noticia falsa", "etiqueta": "0"},
                {"texto": "Noticia real", "etiqueta": "1"},
            ])
            output, report = evaluate_csv(external, [0.9, 0.1], Path(directory))
            self.assertFalse(report["referencia_disponible"])
            self.assertEqual(report["n_evaluadas"], 2)
            self.assertEqual(report["metricas"]["accuracy"], 1.0)
            self.assertEqual(output.prediccion.tolist(), [0, 1])
            self.assertTrue(output.solapamiento.isna().all())


if __name__ == "__main__":
    unittest.main()
