"""Pruebas de entrenar_comun.py con un conjunto sintético diminuto en CPU.

Uso: bilstm/.venv/bin/python -m unittest bilstm/test_entrenar_comun.py
"""

import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from entrenar_comun import (  # noqa: E402
    BiLSTMComun, entrenar, parse_args, perdida_ponderada, pesos_de_clase,
)

COLUMNAS = ["id_fragmento", "id_articulo", "grupo", "fuente", "dominio", "texto",
            "etiqueta_falsa", "peso", "tokens_bilstm", "pliegue"]


def conjunto_sintetico(carpeta: Path) -> Path:
    rng = np.random.default_rng(0)
    filas = []
    for fuente, pliegue in (("v1", "F1"), ("fakedes", "F2"), ("polyglot", "F3")):
        for i in range(40):
            falsa = i % 2
            palabras = ["bulo" if falsa else "informe"] * 5 + [f"w{rng.integers(50)}" for _ in range(20)]
            for n in range(2):
                filas.append({"id_fragmento": f"{fuente}{i}#{n}", "id_articulo": f"{fuente}{i}",
                              "grupo": f"g{fuente}{i}", "fuente": fuente, "dominio": "",
                              "texto": " ".join(palabras), "etiqueta_falsa": falsa, "peso": 0.5,
                              "tokens_bilstm": 25, "pliegue": pliegue})
    conjunto = carpeta / "comun"
    conjunto.mkdir()
    archivos = {"fragmentos_desarrollo.csv": pd.DataFrame(filas, columns=COLUMNAS)}
    for brazo in ("satira", "usmsc", "politica"):
        archivos[f"ablacion_{brazo}.csv"] = pd.DataFrame(
            [{"id_fragmento": f"{brazo}{i}#0", "id_articulo": f"{brazo}{i}", "grupo": f"a{brazo}{i}",
              "fuente": "v1" if brazo == "satira" else brazo, "dominio": "", "texto": "bulo extra texto",
              "etiqueta_falsa": 1, "peso": 1.0, "tokens_bilstm": 3, "pliegue": "ablacion"} for i in range(5)],
            columns=COLUMNAS)
    manifest = {"archivos": {}}
    for nombre, frame in archivos.items():
        frame.to_csv(conjunto / nombre, index=False)
        manifest["archivos"][nombre] = {"sha256": hashlib.sha256((conjunto / nombre).read_bytes()).hexdigest()}
    (conjunto / "manifest.json").write_text(json.dumps(manifest))
    with gzip.open(carpeta / "vec.gz", "wt", encoding="utf-8") as stream:
        stream.write("2 300\n")
        stream.write("bulo " + " ".join(["0.1"] * 300) + "\n")
        stream.write("informe " + " ".join(["-0.1"] * 300) + "\n")
    return conjunto


class ModeloTests(unittest.TestCase):
    def test_pooling_ignora_relleno(self):
        torch.manual_seed(0)
        for pooling in ("final", "maxmedia", "atencion"):
            modelo = BiLSTMComun(20, 8, 4, 0.0, pooling).eval()
            ids = torch.tensor([[3, 4, 5, 0, 0]])
            solo = modelo(ids[:, :3], torch.tensor([3]))
            con_relleno = modelo(ids, torch.tensor([3]))
            self.assertEqual(con_relleno.shape, (1, 2))
            self.assertTrue(torch.allclose(solo, con_relleno, atol=1e-6), pooling)

    def test_perdida_ponderada_y_pesos_de_clase(self):
        frame = pd.DataFrame({"peso": [1.0, 1.0, 1.0, 0.5], "etiqueta_falsa": [0, 0, 0, 1]})
        w = pesos_de_clase(frame)
        self.assertAlmostEqual(float(w[0] * 3), float(w[1] * 0.5), places=5)
        logits = torch.tensor([[2.0, 0.0], [0.0, 2.0]])
        etiquetas = torch.tensor([0, 1])
        a = perdida_ponderada(logits, etiquetas, torch.tensor([1.0, 0.0]), torch.ones(2))
        b = torch.nn.functional.cross_entropy(logits[:1], etiquetas[:1])
        self.assertAlmostEqual(float(a), float(b), places=6)


class EntrenamientoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.conjunto = conjunto_sintetico(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, *extra, pliegue="F1", nombre="r"):
        args = parse_args(["--pliegue", pliegue, "--configuracion", "T", "--salida", str(self.dir / nombre),
                           "--conjunto", str(self.conjunto), "--dispositivo", "cpu",
                           "--vectores", str(self.dir / "vec.gz"), "--cache", str(self.dir / "cache.npz"),
                           "--epocas", "3", "--paciencia", "2", *extra])
        return entrenar(args)

    def test_predicciones_formato_comun_y_etiqueta(self):
        self.correr("--brazo", "satira", "--pooling", "maxmedia", "--congelar-embeddings", "1",
                    "--lr-embeddings", "0.1")
        pred = pd.read_csv(self.dir / "r/predicciones.csv")
        self.assertEqual(list(pred.columns), ["id_fragmento", "modelo", "configuracion", "semilla", "pliegue",
                                              "logit_real", "logit_falsa", "prob_falsa"])
        self.assertTrue(pred.id_fragmento.str.startswith("v1").all())
        self.assertEqual(len(pred), 80)
        z = pred.logit_falsa - pred.logit_real
        self.assertTrue(np.allclose(pred.prob_falsa, 1 / (1 + np.exp(-z))))
        config = json.loads((self.dir / "r/config.json").read_text())
        self.assertEqual(config["etiquetas"], {"real": 0, "falsa": 1})
        # El brazo de sátira (fuente v1) no entra al entrenar F1.
        self.assertEqual(config["filas"]["entrenamiento"] + config["filas"]["validacion_interna"], 160)
        self.assertIn("sha256_script", config)

    def test_brazo_entra_en_otros_pliegues(self):
        self.correr("--brazo", "usmsc", pliegue="F2", nombre="u")
        config = json.loads((self.dir / "u/config.json").read_text())
        self.assertEqual(config["filas"]["entrenamiento"] + config["filas"]["validacion_interna"], 165)

    def test_modelo_final_epocas_fijas(self):
        resultado = self.correr("--epocas-fijas", "2", pliegue="todo", nombre="t")
        self.assertEqual(resultado["mejor_epoca"], 2)
        self.assertFalse((self.dir / "t/predicciones.csv").exists())
        self.assertTrue((self.dir / "t/modelo.pt").exists())

    def test_no_sobrescribe(self):
        self.correr()
        with self.assertRaises(FileExistsError):
            self.correr()


if __name__ == "__main__":
    unittest.main()
