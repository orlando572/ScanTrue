"""Pruebas de mBERT/entrenar.py y mBERT/modelo.py con un conjunto sintético y un BERT diminuto en CPU.

Uso (desde la raíz del repositorio):
  mBERT/.venv/Scripts/python.exe -m unittest discover -s mBERT/tests
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelo as bases  # noqa: E402
from entrenar import (  # noqa: E402
    aplicar, argumentos, corrida, decidir, elegir_modelo, parse_args, perdida_ponderada, pesos_de_clase,
)

COLUMNAS = ["id_fragmento", "id_articulo", "grupo", "fuente", "dominio", "texto",
            "etiqueta_falsa", "peso", "tokens_bilstm", "pliegue"]
PALABRAS = ["bulo", "informe", "extra", "texto"] + [f"w{i}" for i in range(50)]


def conjunto_sintetico(carpeta: Path) -> Path:
    rng = np.random.default_rng(0)
    filas = []
    for fuente, pliegue in (("v1", "F1"), ("fakedes", "F2"), ("polyglot", "F3")):
        for i in range(40):
            falsa = int(i % 3 == 0)  # clases desequilibradas, para probar los pesos de clase
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
    manifest = {"version": "sintetico", "archivos": {}}
    for nombre, frame in archivos.items():
        frame.to_csv(conjunto / nombre, index=False)
        manifest["archivos"][nombre] = {"sha256": hashlib.sha256((conjunto / nombre).read_bytes()).hexdigest()}
    (conjunto / "manifest.json").write_text(json.dumps(manifest))
    return conjunto


def bert_diminuto(carpeta: Path) -> Path:
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

    ruta = carpeta / "bert"
    ruta.mkdir()
    (carpeta / "vocab.txt").write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *PALABRAS]))
    tokenizador = BertTokenizerFast(vocab_file=str(carpeta / "vocab.txt"), do_lower_case=False)
    tokenizador.save_pretrained(ruta)
    torch.manual_seed(0)
    config = BertConfig(vocab_size=len(tokenizador), hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                        intermediate_size=32, max_position_embeddings=64)
    BertForSequenceClassification(config).save_pretrained(ruta, safe_serialization=True)
    return ruta


class ReglasTests(unittest.TestCase):
    def test_perdida_ponderada_y_pesos_de_clase(self):
        frame = pd.DataFrame({"peso": [1.0, 1.0, 1.0, 0.5], "etiqueta_falsa": [0, 0, 0, 1]})
        w = pesos_de_clase(frame)
        self.assertAlmostEqual(w[0] * 3, w[1] * 0.5, places=6)
        logits = torch.tensor([[2.0, 0.0], [0.0, 2.0]])
        etiquetas = torch.tensor([0, 1])
        a = perdida_ponderada(logits, etiquetas, torch.tensor([1.0, 0.0]))
        b = torch.nn.functional.cross_entropy(logits[:1], etiquetas[:1])
        self.assertAlmostEqual(float(a), float(b), places=6)

    def test_regla_de_decision(self):
        ref = {"f1": 0.50, "fa": 0.20, "pliegues": {"F1": 0.5, "F2": 0.5, "F3": 0.5}}
        sube = {"f1": 0.53, "fa": 0.21, "pliegues": {"F1": 0.6, "F2": 0.6, "F3": 0.4}}
        self.assertTrue(decidir(sube, ref, brazo=True)["adopta"])
        self.assertFalse(decidir(dict(sube, fa=0.25), ref, brazo=False)["adopta"])
        self.assertFalse(decidir(dict(sube, f1=0.515), ref, brazo=False)["adopta"])
        un_pliegue = dict(sube, pliegues={"F1": 0.7, "F2": 0.4, "F3": 0.4})
        self.assertFalse(decidir(un_pliegue, ref, brazo=True)["adopta"])

    def test_paso_1_prefiere_el_modelo_mas_pequeno(self):
        filas = {"M0": {"nombre": "M0", "f1": 0.60, "fa": 0.20}, "M1a": {"nombre": "M1a", "f1": 0.59, "fa": 0.21},
                 "M1c": {"nombre": "M1c", "f1": 0.63, "fa": 0.20}}
        modelos = {"M0": "mbert", "M1a": "beto", "M1c": "xlmr"}
        # XLM-R es el mejor, pero BETO queda a menos de 0,02 → gana BETO.
        self.assertEqual(elegir_modelo(dict(filas, M1a=dict(filas["M1a"], f1=0.615)), modelos)["ganador"], "M1a")
        # BETO queda a 0,04 de XLM-R → gana XLM-R.
        self.assertEqual(elegir_modelo(filas, modelos)["ganador"], "M1c")
        # Dentro de 0,02 pero con 3 puntos más de falsas alarmas → no cuenta como empate.
        con_alarmas = dict(filas, M1a={"nombre": "M1a", "f1": 0.62, "fa": 0.23})
        self.assertEqual(elegir_modelo(con_alarmas, modelos)["ganador"], "M1c")

    def test_configuracion_a_argumentos(self):
        config = aplicar({"modelo": "beto", "brazo": []},
                         {"brazo+": "usmsc", "max-length": "512", "gradient-checkpointing": True})
        self.assertEqual(argumentos(config), ["--modelo", "beto", "--brazo", "usmsc", "--max-length", "512",
                                              "--gradient-checkpointing"])

    def test_opciones_de_experimento(self):
        a = parse_args(["experimento", "M1a", "--modelo", "beto"])
        self.assertEqual((a.semillas, a.opciones), ([42, 43, 44], ["--modelo", "beto"]))
        b = parse_args(["experimento", "M1a", "--semillas", "42", "--modelo", "beto", "--brazo", "usmsc"])
        self.assertEqual((b.semillas, b.opciones), ([42], ["--modelo", "beto", "--brazo", "usmsc"]))
        with self.assertRaises(SystemExit):
            parse_args(["corrida", "--pliegue", "F1", "--configuracion", "x", "--salida", "x", "--desconocida"])

    def test_registro_de_modelos(self):
        self.assertEqual(set(bases.PREFERENCIA), set(bases.MODELOS))
        for clave, info in bases.MODELOS.items():
            self.assertRegex(info["revision"], r"^[0-9a-f]{40}$", clave)


class ModeloBaseTests(unittest.TestCase):
    def test_verificar_detecta_archivos_cambiados(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bases, "BASES", Path(tmp)):
            ruta = Path(tmp) / "beto"
            ruta.mkdir()
            (ruta / "model.safetensors").write_bytes(b"pesos")
            info = {"hub_id": bases.MODELOS["beto"]["hub_id"], "revision": bases.MODELOS["beto"]["revision"],
                    "archivos": {"model.safetensors": bases.sha256(ruta / "model.safetensors")}}
            (ruta / "origen.json").write_text(json.dumps(info))
            self.assertEqual(bases.verificar("beto")["archivos"], info["archivos"])
            (ruta / "model.safetensors").write_bytes(b"otros pesos")
            with self.assertRaises(ValueError):
                bases.verificar("beto")

    def test_mbert_local_coincide_con_lo_fijado(self):
        if not (bases.carpeta("mbert") / "origen.json").exists():
            self.skipTest("modelo base mbert no descargado")
        info = bases.verificar("mbert")
        self.assertEqual(info["archivos"]["model.safetensors"], bases.MODELOS["mbert"]["sha256_pesos"])


class EntrenamientoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.conjunto = conjunto_sintetico(cls.dir)
        cls.bert = bert_diminuto(cls.dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def correr(self, *extra, pliegue="F1", nombre="r"):
        args = parse_args(["corrida", "--pliegue", pliegue, "--configuracion", "T", "--salida", str(self.dir / nombre),
                           "--conjunto", str(self.conjunto), "--dispositivo", "cpu", "--ruta-modelo", str(self.bert),
                           "--max-length", "32", "--microlote", "8", "--lote-efectivo", "16", "--lr", "1e-3",
                           "--epocas", "2", *extra])
        return corrida(args)

    def test_predicciones_formato_comun_y_etiqueta(self):
        resultado = self.correr("--brazo", "satira", "--no-guardar-modelo", nombre="p")
        pred = pd.read_csv(self.dir / "p/predicciones.csv")
        self.assertEqual(list(pred.columns), ["id_fragmento", "modelo", "configuracion", "semilla", "pliegue",
                                              "logit_real", "logit_falsa", "prob_falsa"])
        self.assertTrue(pred.id_fragmento.str.startswith("v1").all())
        self.assertEqual(len(pred), 80)
        z = pred.logit_falsa - pred.logit_real
        self.assertTrue(np.allclose(pred.prob_falsa, 1 / (1 + np.exp(-z)), atol=1e-6))
        config = json.loads((self.dir / "p/config.json").read_text())
        self.assertEqual(config["etiquetas"], {"real": 0, "falsa": 1})
        self.assertEqual(config["entrada"], "texto_unico")
        # El brazo de sátira (fuente v1) no entra al entrenar F1.
        self.assertEqual(config["filas"]["entrenamiento"] + config["filas"]["validacion_interna"], 160)
        # Pesos por clase equilibrados (plan §6.2): suma de reales ≈ suma de falsas.
        suma = config["suma_pesos_por_clase"]
        self.assertAlmostEqual(suma["real"], suma["falsa"], places=6)
        self.assertIn("sha256_script", config)
        self.assertIn(resultado["mejor_epoca"], (1, 2))
        self.assertAlmostEqual(resultado["f1_recargado"], resultado["f1_macro_articulo_interna"], places=6)
        self.assertFalse((self.dir / "p/best_model").exists())

    def test_brazo_entra_en_otros_pliegues(self):
        self.correr("--brazo", "usmsc", "--no-guardar-modelo", pliegue="F2", nombre="u")
        config = json.loads((self.dir / "u/config.json").read_text())
        self.assertEqual(config["filas"]["entrenamiento"] + config["filas"]["validacion_interna"], 165)

    def test_modelo_final_epocas_fijas(self):
        resultado = self.correr("--epocas-fijas", "1", pliegue="todo", nombre="t")
        self.assertEqual(resultado["mejor_epoca"], 1)
        self.assertFalse((self.dir / "t/predicciones.csv").exists())
        guardado = json.loads((self.dir / "t/best_model/config.json").read_text())
        self.assertEqual(guardado["id2label"], {"0": "real", "1": "falsa"})
        self.assertIn("sha256_modelo", resultado)

    def test_no_sobrescribe(self):
        self.correr("--no-guardar-modelo", "--epocas", "1", nombre="s")
        with self.assertRaises(FileExistsError):
            self.correr("--no-guardar-modelo", "--epocas", "1", nombre="s")


if __name__ == "__main__":
    unittest.main()
