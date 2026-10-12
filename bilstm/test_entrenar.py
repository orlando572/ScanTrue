import tempfile
import unittest
from pathlib import Path

import pandas as pd

from entrenar import load_splits


class TrainingSplitTests(unittest.TestCase):
    def test_validation_only_does_not_read_test_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for split in ("entrenamiento", "validacion"):
                pd.DataFrame([
                    {"texto": "noticia falsa", "etiqueta": "0", "dataset": "ejemplo",
                     "grupo_duplicados": f"{split}-0"},
                    {"texto": "noticia real", "etiqueta": "1", "dataset": "ejemplo",
                     "grupo_duplicados": f"{split}-1"},
                ]).to_csv(root / f"{split}.csv", index=False)
            frames, hashes = load_splits(root, include_test=False)
            self.assertEqual(set(frames), {"entrenamiento", "validacion"})
            self.assertEqual(set(hashes), {"entrenamiento", "validacion"})
            with self.assertRaises(FileNotFoundError):
                load_splits(root, include_test=True)


if __name__ == "__main__":
    unittest.main()
