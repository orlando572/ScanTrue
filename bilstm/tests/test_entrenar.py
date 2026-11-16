"""Pruebas de bilstm/entrenar.py y bilstm/modelo.py con un conjunto sintético diminuto en CPU.

Uso: bilstm/.venv/bin/python -m unittest discover -s bilstm/tests
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entrenar import (  # noqa: E402
    aplicar, argumentos, corrida, decidir, parse_args, perdida_ponderada, pesos_de_clase, reentrenar,
)
from modelo import BiLSTM, construir_vocabulario, tokenize  # noqa: E402

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
            modelo = BiLSTM(20, 8, 4, 0.0, pooling).eval()
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


class ModeloBasicoTests(unittest.TestCase):
    def test_tokenizador_y_vocabulario(self):
        self.assertEqual(tokenize("¡Hola, Señor! 2026"), ["hola", "señor", "2026"])
        vocab = construir_vocabulario(["b a a", "c b a"], max_size=4)
        self.assertEqual(vocab, {"<pad>": 0, "<unk>": 1, "a": 2, "b": 3})

    def test_carga_checkpoints_de_produccion_y_archivo(self):
        raiz = Path(__file__).resolve().parents[2] / "datasets/bilstm_produccion"
        rutas = [raiz / "modelo/modelo.pt", raiz / "archivo_octubre/modelo/mejor_modelo.pt"]
        if not all(ruta.exists() for ruta in rutas):
            self.skipTest("checkpoints de producción no disponibles")
        for ruta in rutas:
            ck = torch.load(ruta, map_location="cpu", weights_only=True)
            c = ck["config"]
            modelo = BiLSTM(len(ck["vocab"]), c["embedding_dim"], c["hidden_dim"], c["dropout"],
                            c.get("pooling", "final"))
            modelo.load_state_dict(ck["state_dict"])


class PlanTests(unittest.TestCase):
    def test_regla_de_decision(self):
        ref = {"f1": 0.50, "fa": 0.20, "pliegues": {"F1": 0.5, "F2": 0.5, "F3": 0.5}}
        sube = {"f1": 0.53, "fa": 0.21, "pliegues": {"F1": 0.6, "F2": 0.6, "F3": 0.4}}
        self.assertTrue(decidir(sube, ref, brazo=True)["adopta"])
        alarmas = dict(sube, fa=0.25)
        self.assertFalse(decidir(alarmas, ref, brazo=False)["adopta"])
        un_pliegue = dict(sube, pliegues={"F1": 0.7, "F2": 0.4, "F3": 0.4})
        self.assertFalse(decidir(un_pliegue, ref, brazo=True)["adopta"])

    def test_configuracion_a_argumentos(self):
        config = aplicar({"brazo": []}, {"brazo+": "usmsc", "max-tokens": "320"})
        self.assertEqual(argumentos(config), ["--brazo", "usmsc", "--max-tokens", "320"])


class EntrenamientoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.conjunto = conjunto_sintetico(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, *extra, pliegue="F1", nombre="r"):
        args = parse_args(["corrida", "--pliegue", pliegue, "--configuracion", "T", "--salida", str(self.dir / nombre),
                           "--conjunto", str(self.conjunto), "--dispositivo", "cpu",
                           "--vectores", str(self.dir / "vec.gz"), "--cache", str(self.dir / "cache.npz"),
                           "--epocas", "3", "--paciencia", "2", *extra])
        return corrida(args)

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

    def test_sin_checkpoint(self):
        self.correr("--no-guardar-modelo", nombre="s")
        self.assertTrue((self.dir / "s/predicciones.csv").exists())
        self.assertFalse((self.dir / "s/modelo.pt").exists())

    def test_no_sobrescribe(self):
        self.correr()
        with self.assertRaises(FileExistsError):
            self.correr()


def conjunto_panel(carpeta: Path, origen: Path) -> Path:
    """Como una versión del panel: desarrollo + prueba, sin brazos de ablación."""
    desarrollo = pd.read_csv(origen / "fragmentos_desarrollo.csv", keep_default_na=False)
    conjunto = carpeta / "panel"
    conjunto.mkdir()
    archivos = {"fragmentos_desarrollo.csv": desarrollo[desarrollo.fuente != "v1"].assign(pliegue="panel"),
                "fragmentos_prueba.csv": desarrollo[desarrollo.fuente == "v1"].assign(pliegue="prueba_panel")}
    manifest = {"version": "panel_estandar_v1", "nombre": "prueba", "archivos": {}}
    for nombre, frame in archivos.items():
        frame.to_csv(conjunto / nombre, index=False)
        manifest["archivos"][nombre] = {"sha256": hashlib.sha256((conjunto / nombre).read_bytes()).hexdigest()}
    (conjunto / "manifest.json").write_text(json.dumps(manifest))
    return conjunto


class ReentrenarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.conjunto = conjunto_sintetico(self.dir)
        self.receta = self.dir / "receta.json"
        self.receta.write_text(json.dumps({
            "modelo": "bilstm", "configuracion": "B6", "brazo": ["usmsc"], "pooling": "final",
            "congelar_embeddings_epocas": 0, "lr_embeddings_factor": 1.0, "max_tokens": 64,
            "hidden_dim": 8, "dropout": 0.0, "lr": 0.01, "weight_decay": 0.0, "lote": 16, "epocas_fijas": 2,
        }))

    def tearDown(self):
        self.tmp.cleanup()

    def reentrenar(self, conjunto, salida, *extra):
        args = parse_args(["reentrenar", "--receta", str(self.receta), "--conjunto", str(conjunto),
                           "--salida", str(salida), "--version", "v_prueba", "--dispositivo", "cpu",
                           "--vectores", str(self.dir / "vec.gz"), "--cache", str(self.dir / "cache.npz"),
                           *extra])
        return reentrenar(args)

    def test_comun_contrato_provisional_sin_metricas(self):
        salida = self.dir / "modelos/v_prueba"
        resultado = self.reentrenar(self.conjunto, salida)
        self.assertEqual(resultado["epocas"], 2)
        self.assertEqual(resultado["brazos_omitidos"], [])
        contrato = json.loads((salida / "contrato.json").read_text())
        self.assertTrue(contrato["temperatura_provisional"])
        self.assertEqual(contrato["semillas"], [42])
        self.assertEqual(contrato["max_tokens"], 64)
        pesos = salida / "todo_s42/modelo.pt"
        self.assertEqual(contrato["checkpoints"]["s42"]["sha256"], hashlib.sha256(pesos.read_bytes()).hexdigest())
        self.assertFalse((salida / "metricas.json").exists())
        config = json.loads((salida / "todo_s42/config.json").read_text())
        self.assertEqual(config["brazo"], ["usmsc"])
        self.assertEqual(config["configuracion"], "B6")
        self.assertFalse(any(p.name.endswith(".parcial") for p in salida.parent.iterdir()))
        procedencia = json.loads((salida / "entrenamiento.json").read_text())
        self.assertEqual(procedencia["epocas"], 2)

    def test_panel_omite_brazos_y_evalua_la_prueba(self):
        panel = conjunto_panel(self.dir, self.conjunto)
        salida = self.dir / "modelos/v_panel"
        resultado = self.reentrenar(panel, salida, "--epocas", "1", "--cache", str(self.dir / "cache_panel.npz"))
        self.assertEqual(resultado["brazos_omitidos"], ["usmsc"])
        self.assertEqual(resultado["epocas"], 1)
        metricas = json.loads((salida / "metricas.json").read_text())
        evaluacion = metricas["evaluaciones"][0]
        self.assertEqual(evaluacion["n"], 40)  # 40 noticias de la prueba (2 fragmentos cada una)
        self.assertEqual(sum(map(sum, evaluacion["matriz_confusion"])), 40)
        self.assertEqual(metricas["orden_clases"], ["falsa", "real"])

    def test_no_sobrescribe_y_limpia_lo_parcial(self):
        salida = self.dir / "modelos/v_prueba"
        salida.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.reentrenar(self.conjunto, salida)
        self.assertEqual([p.name for p in salida.parent.iterdir()], ["v_prueba"])
        # Si falla a mitad, no queda la carpeta oculta de trabajo.
        otra = self.dir / "modelos/v_falla"
        with self.assertRaises(Exception):
            self.reentrenar(self.conjunto, otra, "--vectores", str(self.dir / "no_existe.gz"),
                            "--cache", str(self.dir / "otra_cache.npz"))
        self.assertFalse(otra.exists())
        self.assertFalse((otra.parent / ".v_falla.parcial").exists())

    def test_pliegues_para_calibrar(self):
        salida = self.dir / "modelos/v_pliegues"
        self.receta.write_text(json.dumps({**json.loads(self.receta.read_text()), "epocas_max": 2, "paciencia": 1}))
        resultado = self.reentrenar(self.conjunto, salida, "--pliegues")
        self.assertEqual(resultado["pliegues"], ["F1", "F2", "F3"])
        oof = pd.read_csv(salida / "predicciones_fuera_de_pliegue.csv")
        self.assertEqual(len(oof), 240)  # todo el desarrollo, una vez
        self.assertEqual(set(oof.pliegue), {"F1", "F2", "F3"})
        for columna in ("id_articulo", "fuente", "etiqueta_falsa", "logit_real", "logit_falsa", "semilla"):
            self.assertIn(columna, oof.columns)
        contrato = json.loads((salida / "contrato.json").read_text())
        self.assertEqual(contrato["predicciones_fuera_de_pliegue"], "predicciones_fuera_de_pliegue.csv")
        self.assertTrue((salida / "pliegues/F2_s42/predicciones.csv").exists())
        self.assertFalse((salida / "pliegues/F2_s42/modelo.pt").exists())

    def test_pliegues_exige_f1_f3(self):
        panel = conjunto_panel(self.dir, self.conjunto)  # pliegue «panel»: sin repartir
        with self.assertRaises(ValueError):
            self.reentrenar(panel, self.dir / "modelos/v_x", "--pliegues", "--cache", str(self.dir / "c2.npz"))
        self.assertFalse((self.dir / "modelos/v_x").exists())

    def test_progreso_en_json(self):
        import contextlib
        import io

        salida = self.dir / "modelos/v_progreso"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.reentrenar(self.conjunto, salida, "--progreso")
        fases = [json.loads(linea)["progreso"] for linea in buffer.getvalue().splitlines()
                 if linea.startswith('{"progreso"')]
        self.assertEqual(fases[0], "preparando")
        self.assertIn("entrenando", fases)
        self.assertEqual(fases[-2:], ["guardando", "terminado"])


if __name__ == "__main__":
    unittest.main()
