import gzip
import tempfile
import unittest
from pathlib import Path

import torch

from preentrenados.entrenar import load_vectors


class VectorLoadingTests(unittest.TestCase):
    def test_loads_only_matching_vectors_and_preserves_padding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mini.vec.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write("3 3\n")
                stream.write("hola 1 2 3\n")
                stream.write("irrelevante 4 5 6\n")
                stream.write("mundo 7 8 9\n")
            model = torch.nn.Module()
            model.embedding = torch.nn.Embedding(4, 3, padding_idx=0)
            report = load_vectors(path, {"<pad>": 0, "<unk>": 1,
                                         "hola": 2, "mundo": 3}, model)
            self.assertEqual(report["vectores_encontrados"], 2)
            self.assertEqual(model.embedding.weight[2].tolist(), [1, 2, 3])
            self.assertEqual(model.embedding.weight[3].tolist(), [7, 8, 9])
            self.assertEqual(model.embedding.weight[0].tolist(), [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
