"""Entrenamientos del panel: recetas, fuentes, estados y rutas, sin entrenar nada de verdad.

Uso: PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m unittest backend.tests.test_training
"""

import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.admin_routes import router as admin_router
from backend.api.dependencies import identity_service, service_repository
from backend.schemas.admin import DatasetItem, DatasetSummary, DatasetVersion
from backend.services.combined_sets import CombinedSetManager
from backend.services.datasets import standard_csvs
from backend.services.training import (
    PRODUCTION_RECIPES, ROOT, TrainingError, TrainingManager, overall_progress, parse_log,
    recipe_next_to, write_panel_set,
)

COLUMNS = ("id_fragmento", "id_articulo", "grupo", "fuente", "dominio", "texto",
           "etiqueta_falsa", "peso", "tokens_bilstm", "pliegue")


def csv_bytes(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def row(index: int, label: int, fold: str = "panel") -> dict:
    return {"id_fragmento": f"a{index}#0", "id_articulo": f"a{index}", "grupo": f"g{index}",
            "fuente": "panel", "dominio": "", "texto": "texto de prueba", "etiqueta_falsa": label,
            "peso": "1.000000", "tokens_bilstm": 120, "pliegue": fold}


class FakeProcess:
    _next = 900_000

    def __init__(self):
        FakeProcess._next += 1
        self.pid = FakeProcess._next
        self.code = None

    def poll(self):
        return self.code


class Workspace(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.comun = self.root / "comun_v1"
        self.comun.mkdir()
        (self.comun / "manifest.json").write_text(json.dumps({
            "version": "comun_v1.1",
            "archivos": {"fragmentos_desarrollo.csv": {"sha256": "x", "filas": 2878},
                         "fragmentos_prueba_congelada.csv": {"sha256": "y", "filas": 555},
                         "ablacion_usmsc.csv": {"sha256": "z", "filas": 10}},
        }))
        self.launched: list[tuple[list[str], dict]] = []
        self.processes: list[FakeProcess] = []
        self.manager = TrainingManager(
            jobs_dir=self.root / "jobs", output_dir=self.root / "datasets/entrenamientos",
            comun_dir=self.comun, python="python-de-prueba", launcher=self.launch, cuda=lambda: False,
            # Conjuntos combinados en la carpeta temporal: los del equipo no cuentan.
            sets=CombinedSetManager(self.root / "conjuntos", self.comun),
        )

    def launch(self, command, log, env):
        self.launched.append((command, env))
        process = FakeProcess()
        self.processes.append(process)
        return process

    def recipe(self, tipo="bilstm"):
        return self.manager.recipe(tipo)


class RecipeTests(Workspace):
    def test_recetas_de_produccion(self):
        if not all(path.is_file() for path in PRODUCTION_RECIPES.values()):
            self.skipTest("config.json de producción no disponibles")
        bilstm = self.recipe("bilstm").summary()
        self.assertEqual((bilstm["configuracion"], bilstm["epocas"], bilstm["brazo"]), ("B6", 4, ["usmsc"]))
        self.assertEqual(bilstm["origen"], "produccion")
        mbert = self.recipe("mbert").summary()
        self.assertEqual((mbert["configuracion"], mbert["epocas"], mbert["modelo_base"]), ("M3b", 3, "beto"))

    def test_receta_del_modelo_desplegado(self):
        folder = self.root / "modelo"
        (folder / "todo_s42").mkdir(parents=True)
        (folder / "todo_s42/modelo.pt").write_bytes(b"pesos")
        (folder / "todo_s42/config.json").write_text(json.dumps(
            {"modelo": "bilstm", "configuracion": "B9", "epocas_fijas": 7, "brazo": []}))
        (folder / "contrato.json").write_text(json.dumps(
            {"semillas": [42], "checkpoints": {"s42": {"ruta": "otra/raiz/todo_s42/modelo.pt"}}}))
        self.assertEqual(recipe_next_to(folder / "contrato.json", "bilstm"), folder / "todo_s42/config.json")
        deployed = SimpleNamespace(id="B9_x", contrato=folder / "contrato.json")
        recipe = self.manager.recipe("bilstm", deployed)
        self.assertEqual((recipe.origen, recipe.modelo, recipe.data["epocas_fijas"]), ("desplegado", "B9_x", 7))
        # Un modelo sin config.json junto a sus pesos (p. ej. importado) usa la de producción.
        (folder / "todo_s42/config.json").unlink()
        self.assertEqual(self.manager.recipe("bilstm", deployed).origen, "produccion")


class SourceTests(Workspace):
    def test_version_del_panel_con_formato_de_comun(self):
        files = {"fragmentos_entrenamiento.csv": csv_bytes([row(1, 0), row(2, 1), row(3, 1)]),
                 "fragmentos_prueba.csv": csv_bytes([row(4, 0, "prueba_panel")])}
        datos = write_panel_set(self.root / "c", files, {"id": "v1", "nombre": "Abril"})
        self.assertEqual(datos, {"entrenamiento": 3, "reales": 1, "falsas": 2, "prueba": 1, "plegable": False})
        manifest = json.loads((self.root / "c/manifest.json").read_text())
        self.assertEqual(set(manifest["archivos"]), {"fragmentos_desarrollo.csv", "fragmentos_prueba.csv"})
        data = (self.root / "c/fragmentos_desarrollo.csv").read_bytes()
        self.assertEqual(manifest["archivos"]["fragmentos_desarrollo.csv"]["sha256"], sha256(data).hexdigest())

    def test_pliegues_por_grupo_y_clase(self):
        rows = [row(i, i % 2) for i in range(12)] + [{**row(0, 0), "id_fragmento": "a0#1"}]
        datos = write_panel_set(self.root / "c", {"fragmentos_entrenamiento.csv": csv_bytes(rows)}, {"id": "v"})
        self.assertTrue(datos["plegable"])
        written = list(csv.DictReader(io.StringIO((self.root / "c/fragmentos_desarrollo.csv").read_text())))
        folds = {}
        for item in written:
            folds.setdefault(item["grupo"], set()).add(item["pliegue"])
        self.assertTrue(all(len(value) == 1 for value in folds.values()))  # un grupo, un pliegue
        for fold in ("F1", "F2", "F3"):  # cada pliegue con las dos clases
            labels = {item["etiqueta_falsa"] for item in written if item["pliegue"] == fold}
            self.assertEqual(labels, {"0", "1"}, fold)
        again = write_panel_set(self.root / "d", {"fragmentos_entrenamiento.csv": csv_bytes(rows)}, {"id": "v"})
        self.assertEqual((self.root / "c/fragmentos_desarrollo.csv").read_bytes(),
                         (self.root / "d/fragmentos_desarrollo.csv").read_bytes())
        self.assertTrue(again["plegable"])

    def test_sin_prueba_no_se_escribe(self):
        files = {"fragmentos_entrenamiento.csv": csv_bytes([row(1, 0), row(2, 1)]),
                 "fragmentos_prueba.csv": csv_bytes([])}
        write_panel_set(self.root / "c", files, {"id": "v1", "nombre": "x"})
        self.assertFalse((self.root / "c/fragmentos_prueba.csv").exists())

    def test_rechaza_vacia_o_de_una_clase(self):
        for rows, code in (([], "sin_entrenamiento"), ([row(1, 1), row(2, 1)], "una_sola_clase")):
            with self.assertRaises(TrainingError) as caught:
                write_panel_set(self.root / code, {"fragmentos_entrenamiento.csv": csv_bytes(rows)}, {})
            self.assertEqual(caught.exception.code, code)

    def test_fuentes(self):
        comun = self.manager.comun_source()
        self.assertEqual((comun["version"], comun["fragmentos"], comun["brazos"]), ("comun_v1.1", 2878, ["usmsc"]))
        summary = DatasetSummary(casos=5, fragmentos_por_particion={"entrenamiento": 8, "prueba": 2})
        now = datetime.now(timezone.utc)
        versions = [
            DatasetVersion(id=uuid4(), nombre="nueva", fecha=now, resumen=summary,
                           manifiesto={"archivos": {"fragmentos_entrenamiento.csv": {}}}),
            DatasetVersion(id=uuid4(), nombre="vieja", fecha=now, resumen=summary, manifiesto={}),
        ]
        sources = self.manager.panel_sources(versions)
        self.assertEqual([(s["nombre"], s["apta"], s["fragmentos"]) for s in sources],
                         [("nueva", True, 8), ("vieja", False, 8)])


class ProgressTests(unittest.TestCase):
    def test_registro_a_progreso(self):
        log = "\n".join([
            "$ python bilstm/entrenar.py reentrenar …",
            '{"progreso": "preparando", "segundos": 0.1}',
            '{"progreso": "entrenando", "epoca": 2, "epocas": 4, "lote": 50, "lotes": 100}',
            '{"epoca": 1, "perdida": 0.6, "embeddings_congelados": false}',
            "texto suelto que no es JSON",
        ])
        info = parse_log(log)
        self.assertEqual((info["fase"], info["epoca"], info["epocas"]), ("entrenando", 2, 4))
        self.assertEqual(info["perdidas"], [{"epoca": 1, "perdida": 0.6}])
        self.assertAlmostEqual(overall_progress(info), 0.06 + 0.86 * (1.5 / 4), places=4)
        self.assertEqual(overall_progress({"fase": "guardando"}), 0.97)
        self.assertEqual(overall_progress({"fase": None}), 0.0)


class JobTests(Workspace):
    def start(self, source=None, **extra):
        return self.manager.start("bilstm", source or {"tipo": "comun_v1"}, self.recipe(),
                                  extra.get("epochs"), 42, "admin@example.com", extra.get("loader"))

    def test_lanza_con_la_receta_y_no_admite_dos_a_la_vez(self):
        job = self.start(epochs=2)
        self.assertEqual(job["estado"], "en_curso")
        self.assertRegex(job["version"], r"^comun_v1\.1_B6_\d{8}_[0-9a-f]{4}$")
        command, env = self.launched[0]
        self.assertEqual(command[2:4], [str(ROOT / "bilstm/entrenar.py"), "reentrenar"])
        self.assertIn("--progreso", command)
        self.assertEqual(command[command.index("--epocas") + 1], "2")
        self.assertEqual(command[command.index("--dispositivo") + 1], "cpu")
        self.assertEqual(command[command.index("--conjunto") + 1], str(self.comun))
        self.assertEqual(command[command.index("--salida") + 1],
                         str(self.root / "datasets/entrenamientos/bilstm" / job["version"]))
        self.assertNotIn("PYTHONPATH", env)
        with self.assertRaises(TrainingError) as caught:
            self.start()
        self.assertEqual(caught.exception.status_code, 409)

    def test_elegir_procesador_o_gpu(self):
        with self.assertRaises(TrainingError) as caught:  # sin CUDA no se puede pedir la GPU
            self.manager.start("bilstm", {"tipo": "comun_v1"}, self.recipe(), None, 42, None, device="cuda")
        self.assertEqual(caught.exception.code, "sin_gpu")
        self.assertEqual(self.launched, [])
        self.manager._cuda = lambda: True
        job = self.manager.start("bilstm", {"tipo": "comun_v1"}, self.recipe(), None, 42, None, device="cpu")
        command, _ = self.launched[0]
        self.assertEqual((job["dispositivo"], command[command.index("--dispositivo") + 1]), ("cpu", "cpu"))
        self.processes[0].code = 0
        job = self.manager.start("bilstm", {"tipo": "comun_v1"}, self.recipe(), None, 42, None)
        self.assertEqual(job["dispositivo"], "cuda")  # por defecto, la GPU si la hay

    def test_preparar_para_calibrar(self):
        job = self.manager.start("bilstm", {"tipo": "comun_v1"}, self.recipe(), None, 42, None, folds=True)
        command, _ = self.launched[0]
        self.assertIn("--pliegues", command)
        self.assertTrue(job["pliegues"])
        folder = self.root / "jobs" / job["id"]
        with (folder / "registro.log").open("a") as log:
            log.write('{"progreso": "entrenando", "corrida": 1, "corridas": 4, "nombre": "F1", "epoca": 2, '
                      '"epocas": 20, "lote": 5, "lotes": 10}\n{"epoca": 1, "perdida": 0.5}\n')
            log.write('{"progreso": "entrenando", "corrida": 2, "corridas": 4, "nombre": "F2", "epoca": 1, '
                      '"epocas": 20, "lote": 1, "lotes": 10}\n')
        status = self.manager.get(job["id"])
        self.assertEqual((status["corrida"], status["corridas"], status["corrida_nombre"]), (2, 4, "F2"))
        self.assertEqual(status["perdidas"], [])  # las pérdidas son de la corrida en curso
        self.assertAlmostEqual(status["progreso"], 0.06 + 0.86 * ((1 + 0.005) / 4), places=3)
        self.processes[0].code = 0
        tiny = [row(1, 0), row(2, 1)]

        def loader(_):
            return {"id": "v", "nombre": "mini"}, {"fragmentos_entrenamiento.csv": csv_bytes(tiny)}

        with self.assertRaises(TrainingError) as caught:
            self.manager.start("bilstm", {"tipo": "panel", "version_id": "v"}, self.recipe(), None, 42, None,
                               loader, folds=True)
        self.assertEqual(caught.exception.code, "muy_pequena_para_calibrar")

    def test_comando_de_mbert_listo_sin_ejecutarlo(self):
        if not PRODUCTION_RECIPES["mbert"].is_file():
            self.skipTest("config.json de BETO no disponible")
        job = self.manager.start("mbert", {"tipo": "comun_v1"}, self.recipe("mbert"), None, 42, None)
        command, env = self.launched[0]
        self.assertEqual(command[2], str(ROOT / "mBERT/entrenar.py"))
        self.assertEqual(command[command.index("--epocas") + 1], "3")
        self.assertNotIn("--cache", command)
        self.assertTrue(env["PYTHONPATH"].endswith("backend/.deps"))
        self.assertRegex(job["version"], r"_M3b_")

    def test_estados(self):
        job = self.start()
        folder = self.root / "jobs" / job["id"]
        with (folder / "registro.log").open("a") as log:
            log.write('{"progreso": "entrenando", "epoca": 1, "epocas": 4, "lote": 10, "lotes": 20}\n')
        running = self.manager.get(job["id"])
        self.assertEqual((running["estado"], running["epoca"], running["lotes"]), ("en_curso", 1, 20))
        self.assertGreater(running["progreso"], 0.06)
        # Falla: el proceso sale sin contrato.
        self.processes[0].code = 1
        with (folder / "registro.log").open("a") as log:
            log.write("Traceback (most recent call last):\nRuntimeError: CUDA no está disponible\n")
        failed = self.manager.get(job["id"])
        self.assertEqual(failed["estado"], "fallido")
        self.assertIn("CUDA", failed["error"])
        # Otro entrenamiento termina bien: su contrato aparece en la salida.
        second = self.start()
        output = self.root / "datasets/entrenamientos/bilstm" / second["version"]
        output.mkdir(parents=True)
        (output / "contrato.json").write_text("{}")
        (output / "metricas.json").write_text(json.dumps({"modelo": "bilstm"}))
        self.processes[1].code = 0
        done = self.manager.get(second["id"])
        self.assertEqual((done["estado"], done["progreso"], done["fase"]), ("completado", 1.0, "terminado"))
        listing = self.manager.overview()
        self.assertIsNone(listing["activo"])
        self.assertEqual([item["estado"] for item in listing["entrenamientos"]], ["completado", "fallido"])

    def test_sobrevive_a_un_reinicio(self):
        job = self.start()
        self.processes[0].code = 0  # sin contrato y sin proceso
        fresh = TrainingManager(jobs_dir=self.root / "jobs", output_dir=self.root / "datasets/entrenamientos",
                                comun_dir=self.comun, launcher=self.launch, cuda=lambda: False)
        self.assertEqual(fresh.get(job["id"])["estado"], "fallido")

    def test_version_del_panel(self):
        items = [
            DatasetItem(analisis_id=uuid4(), texto=f"texto {i}", hash_texto=f"h{i}",
                        etiqueta="falsa" if i % 2 else "real", particion="prueba" if i == 3 else "entrenamiento",
                        grupo=f"g_{i}", decision="aprobado", id_fragmento=f"f{i}#0", peso=1.0, tokens_bilstm=120)
            for i in range(4)
        ]
        version_id = str(uuid4())

        def loader(requested):
            self.assertEqual(requested, version_id)
            return {"id": version_id, "nombre": "Revisión de noviembre"}, standard_csvs(items)

        job = self.start({"tipo": "panel", "version_id": version_id}, loader=loader)
        self.assertRegex(job["version"], r"^panel-revision-de-noviembre_B6_\d{8}_[0-9a-f]{4}$")
        self.assertEqual(job["datos"]["prueba"], 1)
        command, _ = self.launched[0]
        conjunto = Path(command[command.index("--conjunto") + 1])
        self.assertTrue((conjunto / "fragmentos_desarrollo.csv").is_file())
        self.assertTrue(command[command.index("--cache") + 1].startswith(str(self.root / "jobs")))

    def test_fallo_al_preparar_no_deja_rastro(self):
        def loader(_):
            raise TrainingError("una_sola_clase", "x", 422)

        with self.assertRaises(TrainingError):
            self.start({"tipo": "panel", "version_id": str(uuid4())}, loader=loader)
        self.assertEqual(list((self.root / "jobs").iterdir()), [])
        self.assertEqual(self.launched, [])

    def test_cancelar_detiene_el_proceso_y_borra_lo_parcial(self):
        def launch(command, log, env):
            version = command[command.index("--version") + 1]
            return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", version],
                                    start_new_session=True)

        self.manager.launcher = launch
        job = self.start()
        partial = self.root / "datasets/entrenamientos/bilstm" / f".{job['version']}.parcial"
        partial.mkdir(parents=True)
        cancelled = self.manager.cancel(job["id"])
        self.assertEqual(cancelled["estado"], "cancelado")
        deadline = time.monotonic() + 10
        while partial.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(partial.exists())
        with self.assertRaises(TrainingError) as caught:
            self.manager.cancel(job["id"])
        self.assertEqual(caught.exception.status_code, 409)


class RouteTests(Workspace):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(admin_router)
        app.state.training = self.manager

        def forbidden(*args, **kwargs):
            raise AssertionError("Entrenamiento no debe desplegar, retirar ni borrar modelos")

        app.state.model_versions = SimpleNamespace(
            selection=lambda: {"bilstm": None, "mbert": None},
            deploy=forbidden, retire=forbidden, set_weights=forbidden, revert=forbidden, delete=forbidden,
        )
        user = SimpleNamespace(id=str(uuid4()), email="admin@example.com", app_metadata={"role": "admin"})
        app.dependency_overrides[identity_service] = lambda: SimpleNamespace(verify_user=lambda token: user)
        self.legacy_id = uuid4()
        legacy = DatasetVersion(id=self.legacy_id, nombre="vieja", fecha=datetime.now(timezone.utc),
                                resumen=DatasetSummary(), manifiesto={})

        def get_version(version_id):
            return legacy if version_id == self.legacy_id else None

        app.dependency_overrides[service_repository] = lambda: SimpleNamespace(
            list_dataset_versions=lambda: [legacy],
            get_dataset_version=get_version,
            dataset_items=lambda version_id, *a: ([DatasetItem(
                texto="t", hash_texto="h", etiqueta="real", particion="entrenamiento", grupo="g",
                decision="aprobado")], 1),
        )
        self.client = TestClient(app)
        self.auth = {"Authorization": "Bearer t"}

    def test_opciones_lanzar_y_listar(self):
        self.assertEqual(self.client.get("/admin/entrenamientos/opciones").status_code, 401)
        options = self.client.get("/admin/entrenamientos/opciones", headers=self.auth).json()
        self.assertEqual([s["tipo"] for s in options["fuentes"]], ["comun_v1", "panel"])
        self.assertFalse(options["fuentes"][1]["apta"])
        self.assertFalse(options["cuda"])
        self.assertEqual(options["salida"], "datasets/entrenamientos")
        response = self.client.post("/admin/entrenamientos", headers=self.auth,
                                    json={"tipo": "bilstm", "fuente": {"tipo": "comun_v1"}, "epocas": 1})
        self.assertEqual(response.status_code, 202, response.text)
        job = response.json()
        self.assertEqual((job["estado"], job["epocas"], job["receta"]["configuracion"]), ("en_curso", 1, "B6"))
        self.assertTrue(job["pliegues"])  # «Preparar para calibrar», activo por defecto como en el panel
        listing = self.client.get("/admin/entrenamientos", headers=self.auth).json()
        self.assertEqual(listing["activo"]["id"], job["id"])
        detail = self.client.get(f"/admin/entrenamientos/{job['id']}", headers=self.auth).json()
        self.assertTrue(detail["registro"][0].startswith("$ "))
        again = self.client.post("/admin/entrenamientos", headers=self.auth,
                                 json={"tipo": "bilstm", "fuente": {"tipo": "comun_v1"}})
        self.assertEqual(again.json()["detail"]["codigo"], "entrenamiento_en_curso")

    def test_errores(self):
        legacy = self.client.post("/admin/entrenamientos", headers=self.auth, json={
            "tipo": "bilstm", "fuente": {"tipo": "panel", "version_id": str(self.legacy_id)}})
        self.assertEqual((legacy.status_code, legacy.json()["detail"]["codigo"]),
                         (409, "version_anterior_al_estandar"))
        missing = self.client.post("/admin/entrenamientos", headers=self.auth, json={
            "tipo": "bilstm", "fuente": {"tipo": "panel", "version_id": str(uuid4())}})
        self.assertEqual(missing.status_code, 404)
        no_gpu = self.client.post("/admin/entrenamientos", headers=self.auth, json={
            "tipo": "bilstm", "fuente": {"tipo": "comun_v1"}, "dispositivo": "cuda"})
        self.assertEqual((no_gpu.status_code, no_gpu.json()["detail"]["codigo"]), (422, "sin_gpu"))
        no_version = self.client.post("/admin/entrenamientos", headers=self.auth,
                                      json={"tipo": "bilstm", "fuente": {"tipo": "panel"}})
        self.assertEqual(no_version.status_code, 422)
        self.assertEqual(self.client.get("/admin/entrenamientos/no..existe", headers=self.auth).status_code, 404)
        self.assertEqual(self.launched, [])
        self.assertEqual(list((self.root / "jobs").iterdir()) if (self.root / "jobs").exists() else [], [])


if __name__ == "__main__":
    unittest.main()
