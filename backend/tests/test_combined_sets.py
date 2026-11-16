"""Conjuntos combinados: comun_v1 (sin cambios) + versiones del panel, con balanceo 50/50 opcional.

Uso: PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m unittest backend.tests.test_combined_sets
"""

import csv
from hashlib import sha256
import io
import json
import logging
from pathlib import Path
import tempfile
import unittest

from datos_comunes.cruces import IndiceComun

from backend.services.combined_sets import (
    EXTRA, CombinedSetError, CombinedSetManager, PanelSource, balance, build, cross_with_comun,
    merge_versions, read_comun,
)
from backend.services.training import TrainingError, TrainingManager

COLUMNS = ("id_fragmento", "id_articulo", "grupo", "fuente", "dominio", "texto",
           "etiqueta_falsa", "peso", "tokens_bilstm", "pliegue")
WORDS = ("el gobierno regional anunció nuevas medidas para mejorar el transporte público durante "
         "la temporada de lluvias y pidió a los vecinos tomar precauciones en las zonas más afectadas "
         "por los deslizamientos de tierra registrados esta semana en la provincia").split()


def text(seed: int, change: int = 0) -> str:
    """Texto largo y distinto por `seed`; `change` palabras cambiadas da un casi duplicado."""
    words = [f"{word}{seed}" for word in WORDS]
    for position in range(change):
        words[position] = f"otra{position}"
    return " ".join(words)


def row(article: str, label: int, group: str | None = None, fold: str = "panel", body: str | None = None,
        part: int = 0) -> dict:
    return {"id_fragmento": f"{article}#{part}", "id_articulo": article, "grupo": group or f"g_{article}",
            "fuente": "panel", "dominio": "", "texto": body or text(int(sha256(article.encode()).hexdigest(), 16) % 10_000),
            "etiqueta_falsa": label, "peso": "1.000000", "tokens_bilstm": 120, "pliegue": fold}


def csv_bytes(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def source(version_id: str, training: list[dict], test: list[dict] = (), fecha: str = "2026-11-01") -> PanelSource:
    return PanelSource(version_id, f"versión {version_id}", fecha, {
        "fragmentos_entrenamiento.csv": csv_bytes(training),
        "fragmentos_prueba.csv": csv_bytes(list(test))})


class MergeTests(unittest.TestCase):
    def test_sin_repetir_y_manda_la_version_mas_reciente(self):
        old = source("a", [row("n1", 0), row("n2", 1)], fecha="2026-11-01")
        new = source("b", [row("n1", 1), row("n3", 0)], fecha="2026-11-10")
        training, test, _ = merge_versions([new, old])
        labels = {r["id_articulo"]: int(r["etiqueta_falsa"]) for r in training}
        self.assertEqual(labels, {"n1": 1, "n2": 1, "n3": 0})
        self.assertEqual(test, [])

    def test_lo_que_esta_en_alguna_prueba_va_a_prueba(self):
        first = source("a", [row("n1", 0), row("n2", 1, group="g_comun")], [row("n3", 1, fold="prueba_panel")])
        second = source("b", [row("n3", 1), row("n4", 0, group="g_comun")], [row("n1", 0, fold="prueba_panel")],
                        fecha="2026-11-02")
        training, test, stats = merge_versions([first, second])
        # n1 y n3 estuvieron en la prueba de alguna versión; n2 y n4 comparten grupo, pero ninguno
        # de los dos está en una prueba, así que siguen entrenando.
        self.assertEqual(sorted(r["id_articulo"] for r in training), ["n2", "n4"])
        self.assertEqual(sorted(r["id_articulo"] for r in test), ["n1", "n3"])
        self.assertEqual(stats["fragmentos_movidos_a_prueba"], 1)  # n3: en entrenamiento en «b»


class CrossAndBalanceTests(unittest.TestCase):
    def setUp(self):
        self.comun = [
            {**row("c1", 0, group="gc1", fold="F1", body=text(1)), "_archivo": "fragmentos_desarrollo.csv"},
            {**row("c2", 1, group="gc2", fold="F2", body=text(2)), "_archivo": "fragmentos_desarrollo.csv"},
        ]
        self.index = IndiceComun([{"archivo": r["_archivo"], "grupo": r["grupo"], "pliegue": r["pliegue"],
                                   "texto": r["texto"]} for r in self.comun])

    def test_duplicado_se_retira_y_casi_duplicado_se_une_a_su_grupo(self):
        training = [row("p1", 0, body=text(1).upper()),  # mismo texto (cambia solo el formato)
                    row("p2", 1, body=text(2, change=3)),  # casi duplicado de c2
                    row("p3", 0, body=text(3))]
        kept, stats = cross_with_comun(training, self.comun, self.index)
        self.assertEqual([r["id_articulo"] for r in kept], ["p2", "p3"])
        self.assertEqual(kept[0]["grupo"], "gc2")
        self.assertEqual((stats["duplicado_comun"], stats["casi_duplicado_unido"]), (1, 1))

    def test_50_50_retira_noticias_enteras_de_la_clase_mayor(self):
        training = [row("r1", 0), row("r2", 0), row("r3", 0, part=0), row("r3", 0, part=1), row("f1", 1)]
        kept, removed = balance(training)
        news = {r["id_articulo"]: int(r["etiqueta_falsa"]) for r in kept}
        self.assertEqual(sorted(news.values()), [0, 1])
        self.assertEqual(removed, 2)
        again, _ = balance(list(reversed(training)))  # mismo resultado sin importar el orden
        self.assertEqual({r["id_fragmento"] for r in again}, {r["id_fragmento"] for r in kept})
        with self.assertRaises(CombinedSetError) as raised:
            balance([row("r1", 0), row("r2", 0)])
        self.assertEqual(raised.exception.code, "una_sola_clase_para_equilibrar")

    def test_el_balanceo_no_toca_la_prueba_ni_comun(self):
        sources = [source("a", [row("r1", 0), row("r2", 0), row("f1", 1)], [row("t1", 0, fold="prueba_panel"),
                                                                             row("t2", 0, fold="prueba_panel")])]
        result = build(sources, True, "50_50", self.comun, self.index)
        self.assertEqual(result.summary["panel_despues"], {"reales": 1, "falsas": 1, "fragmentos": 2})
        self.assertEqual(result.summary["prueba"]["reales"], 2)
        self.assertEqual(result.summary["comun_v1"], {"reales": 1, "falsas": 1, "fragmentos": 2})
        self.assertEqual(result.summary["total_entrenamiento"]["fragmentos"], 4)


class SetsWorkspace(unittest.TestCase):
    """comun_v1 pequeño en una carpeta temporal y un gestor de conjuntos que escribe allí."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.comun_dir = self.root / "comun_v1"
        self.comun_dir.mkdir()
        files = {"fragmentos_desarrollo.csv": csv_bytes([row("c1", 0, "gc1", "F1", text(1)),
                                                         row("c2", 1, "gc2", "F2", text(2)),
                                                         row("c3", 0, "gc3", "F3", text(3))]),
                 "ablacion_usmsc.csv": csv_bytes([row("u1", 1, "gu1", "ablacion", text(4))]),
                 "fragmentos_prueba_congelada.csv": csv_bytes([row("z1", 1, "gz1", "congelada", text(5))])}
        for name, data in files.items():
            (self.comun_dir / name).write_bytes(data)
        (self.comun_dir / "manifest.json").write_text(json.dumps({
            "version": "comun_v1.1", "pliegues": {"F1": {"valida": "v1"}},
            "archivos": {name: {"sha256": sha256(data).hexdigest(), "filas": data.count(b"\n") - 1}
                         for name, data in files.items()}}))
        self.manager = CombinedSetManager(self.root / "conjuntos", self.comun_dir)
        self.index = IndiceComun.cargar(self.comun_dir)
        self.panel = source("a", [row("r1", 0, body=text(11)), row("r2", 0, body=text(12)),
                                  row("f1", 1, body=text(13))],
                            [row("t1", 1, fold="prueba_panel", body=text(14))])


class ManagerTests(SetsWorkspace):
    def test_copia_comun_sin_cambios_y_guarda_lo_del_panel_aparte(self):
        info = self.manager.create("Común + abril", None, [self.panel], True, "50_50", self.index, "admin@x")
        folder = self.root / "conjuntos" / info["version"]
        self.assertTrue(info["apto"])
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         ["ablacion_usmsc.csv", EXTRA, "fragmentos_desarrollo.csv", "fragmentos_prueba.csv",
                          "manifest.json"])  # la prueba congelada no se copia
        for name in ("fragmentos_desarrollo.csv", "ablacion_usmsc.csv"):
            self.assertEqual((folder / name).read_bytes(), (self.comun_dir / name).read_bytes())
        manifest = json.loads((folder / "manifest.json").read_text())
        for name, entry in manifest["archivos"].items():
            self.assertEqual(sha256((folder / name).read_bytes()).hexdigest(), entry["sha256"], name)
        extra = list(csv.DictReader(io.StringIO((folder / EXTRA).read_text())))
        self.assertEqual({r["pliegue"] for r in extra}, {"panel"})
        self.assertEqual(sorted(int(r["etiqueta_falsa"]) for r in extra), [0, 1])
        self.assertEqual(manifest["comun_v1"]["version"], "comun_v1.1")
        self.assertEqual([item["version"] for item in self.manager.list()], [info["version"]])
        with self.assertRaises(CombinedSetError) as raised:
            self.manager.create("común + ABRIL", None, [self.panel], True, "ninguno", self.index, None)
        self.assertEqual(raised.exception.code, "nombre_repetido")
        self.manager.delete(info["version"])
        self.assertEqual(self.manager.list(), [])
        self.assertEqual(list((self.root / "conjuntos").iterdir()), [])

    def test_sin_comun_es_la_union_repartida_en_pliegues(self):
        many = source("b", [row(f"r{i}", 0, body=text(20 + i)) for i in range(3)]
                      + [row(f"f{i}", 1, body=text(30 + i)) for i in range(3)])
        info = self.manager.create("Solo panel", None, [many], False, "ninguno", None, None)
        folder = self.root / "conjuntos" / info["version"]
        self.assertFalse((folder / EXTRA).exists())
        development = list(csv.DictReader(io.StringIO((folder / "fragmentos_desarrollo.csv").read_text())))
        self.assertEqual({r["pliegue"] for r in development}, {"F1", "F2", "F3"})
        self.assertTrue(info["resumen"]["plegable"])
        self.assertFalse(info["incluye_comun"])

    def test_errores(self):
        for args, code in ((([], True, "ninguno"), "sin_versiones"),
                           (([self.panel], True, "60_40"), "balanceo_desconocido")):
            with self.assertRaises(CombinedSetError) as raised:
                build(*args, read_comun(self.comun_dir), self.index)
            self.assertEqual(raised.exception.code, code)
        with self.assertRaises(CombinedSetError) as raised:
            self.manager.get("../fuera")
        self.assertEqual(raised.exception.status_code, 404)

    def test_entrenar_con_un_conjunto(self):
        info = self.manager.create("Común + abril", None, [self.panel], True, "ninguno", self.index, None)
        launched = []

        class Process:
            pid = 987_654

            def poll(self):
                return None

        training = TrainingManager(jobs_dir=self.root / "jobs", output_dir=self.root / "salida",
                                   comun_dir=self.comun_dir, python="python-de-prueba",
                                   launcher=lambda command, log, env: launched.append(command) or Process(),
                                   cuda=lambda: False, sets=self.manager)
        recipe = training.recipe("bilstm")
        with self.assertRaises(TrainingError) as raised:
            training.start("bilstm", {"tipo": "conjunto", "version": "no_existe"}, recipe, 1, 42, None)
        self.assertEqual(raised.exception.code, "conjunto_no_encontrado")
        sources = training.set_sources()
        self.assertEqual([(s["tipo"], s["version"], s["apta"]) for s in sources],
                         [("conjunto", info["version"], True)])
        job = training.start("bilstm", {"tipo": "conjunto", "version": info["version"]}, recipe, 1, 42, None,
                             folds=False)
        self.assertTrue(job["version"].startswith("conjunto-comun-abril_"))
        command = launched[0]
        self.assertEqual(command[command.index("--conjunto") + 1], str(self.root / "conjuntos" / info["version"]))
        cache = Path(command[command.index("--cache") + 1])
        self.assertEqual(cache.parent.parent, self.root / "jobs")  # caché propia, no la de comun_v1
        self.assertEqual(job["datos"]["prueba"], 1)


class RouteTests(SetsWorkspace):
    """Las rutas del panel con un repositorio falso (sin Supabase)."""

    def setUp(self):
        super().setUp()
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from unittest.mock import patch
        from uuid import uuid4

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.api.admin_routes import router as admin_router
        from backend.api.dependencies import identity_service, service_repository
        from backend.schemas.admin import DatasetItem, DatasetSummary, DatasetVersion

        app = FastAPI()
        app.include_router(admin_router)
        app.state.training = TrainingManager(jobs_dir=self.root / "jobs", output_dir=self.root / "salida",
                                             comun_dir=self.comun_dir, cuda=lambda: False, sets=self.manager)
        user = SimpleNamespace(id=str(uuid4()), email="admin@example.com", app_metadata={"role": "admin"})
        app.dependency_overrides[identity_service] = lambda: SimpleNamespace(verify_user=lambda token: user)
        self.version_id, self.legacy_id = uuid4(), uuid4()
        now = datetime.now(timezone.utc)
        versions = {
            self.version_id: DatasetVersion(id=self.version_id, nombre="abril", fecha=now,
                                            resumen=DatasetSummary(), manifiesto={}),
            self.legacy_id: DatasetVersion(id=self.legacy_id, nombre="vieja", fecha=now,
                                           resumen=DatasetSummary(), manifiesto={}),
        }

        def item(index, label, partition="entrenamiento"):
            article = uuid4()
            return DatasetItem(analisis_id=article, texto=text(40 + index), hash_texto=f"h{index}",
                               etiqueta=label, particion=partition, grupo=f"g{index}", decision="aprobado",
                               id_fragmento=f"{article}#0", fuente="panel", peso=1.0, tokens_bilstm=120)

        items = {self.version_id: [item(1, "real"), item(2, "real"), item(3, "falsa"), item(4, "falsa", "prueba")],
                 self.legacy_id: [DatasetItem(texto="t", hash_texto="h", etiqueta="real",
                                              particion="entrenamiento", grupo="g", decision="aprobado")]}
        app.dependency_overrides[service_repository] = lambda: SimpleNamespace(
            get_dataset_version=versions.get,
            dataset_items=lambda version_id, *a: (items[version_id], len(items[version_id])),
            list_dataset_versions=lambda: list(versions.values()),
        )
        patcher = patch("backend.api.admin_routes.comun_index", lambda: self.index)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.auth = {"Authorization": "Bearer t"}

    def test_vista_previa_crear_entrenar_y_borrar(self):
        body = {"versiones": [str(self.version_id)], "balanceo": "50_50"}
        self.assertEqual(self.client.post("/admin/conjuntos/vista-previa", json=body).status_code, 401)
        preview = self.client.post("/admin/conjuntos/vista-previa", headers=self.auth, json=body)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["panel_despues"], {"reales": 1, "falsas": 1, "fragmentos": 2})
        created = self.client.post("/admin/conjuntos", headers=self.auth, json={**body, "nombre": "Común + abril"})
        self.assertEqual(created.status_code, 201, created.text)
        version = created.json()["version"]
        self.assertEqual([item["version"] for item in self.client.get("/admin/conjuntos", headers=self.auth).json()],
                         [version])
        options = self.client.get("/admin/entrenamientos/opciones", headers=self.auth).json()
        self.assertIn(("conjunto", version), [(s["tipo"], s.get("version")) for s in options["fuentes"]])
        legacy = self.client.post("/admin/conjuntos/vista-previa", headers=self.auth,
                                  json={"versiones": [str(self.legacy_id)]})
        self.assertEqual((legacy.status_code, legacy.json()["detail"]["codigo"]),
                         (409, "version_anterior_al_estandar"))
        self.assertEqual(self.client.delete(f"/admin/conjuntos/{version}", headers=self.auth).json(),
                         {"eliminado": True})
        missing = self.client.get(f"/admin/conjuntos/{version}", headers=self.auth)
        self.assertEqual((missing.status_code, missing.json()["detail"]["codigo"]), (404, "conjunto_no_encontrado"))


if __name__ == "__main__":
    unittest.main()
