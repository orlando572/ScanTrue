"""Catálogo, despliegue por tipo, pesos, ZIP y rutas del panel de modelos, sin cargar pesos.

Uso: PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m unittest backend.tests.test_model_registry
"""

from hashlib import sha256
import io
import json
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.admin_routes import router as admin_router
from backend.api.dependencies import identity_service, service_repository
from backend.api.metrics_routes import router as metrics_router
from backend.models.contrato import (
    COMBINATION_FILE, MODELOS_BASE_ADMITIDOS, Combination, ModelContract, UnsupportedBaseModel,
    resolve,
)
from backend.schemas.analysis import AnalysisRequest
from backend.services.analysis import AnalysisService, InvalidAnalysisInput
from backend.services.model_registry import (
    ModelCatalog, ModelDeploymentManager, ModelVersionError, PredictorCache, default_weights,
)
from backend.tests.test_analysis_combination import (
    FakeBilstm, FakeMbert, FakeMbertPolicy, combination,
)

LABELS = {"real": 0, "falsa": 1}


def write_model(folder: Path, tipo: str, version: str, *, weights: bytes = b"pesos",
                provisional: bool = False, base: str = "beto", training_paths: bool = False,
                metrics: bool = False) -> Path:
    """Carpeta de modelo como la deja el entrenamiento: contrato.json y sus archivos."""
    folder.mkdir(parents=True, exist_ok=True)
    prefix = "datasets/comun_v1_corridas/x/final/" if training_paths else ""
    contract = {
        "modelo": tipo, "version": version, "etiquetas": LABELS, "max_tokens": 192,
        "temperatura": 1.0 if provisional else 2.5, "temperatura_provisional": provisional,
        "umbral_falsa": 0.5, "semillas": [42], "promediar_logits_semillas": False,
    }
    if tipo == "bilstm":
        (folder / "todo_s42").mkdir(exist_ok=True)
        (folder / "todo_s42" / "modelo.pt").write_bytes(weights)
        contract["checkpoints"] = {"s42": {"ruta": f"{prefix}todo_s42/modelo.pt",
                                           "sha256": sha256(weights).hexdigest()}}
    else:
        model = folder / "best_model"
        model.mkdir(exist_ok=True)
        (model / "model.safetensors").write_bytes(weights)
        (model / "config.json").write_text("{}")
        (model / "tokenizer.json").write_text("{\"t\": 1}")
        hub, revision = MODELOS_BASE_ADMITIDOS.get(base, ("otro/roberta", "abc"))
        contract.update(
            max_tokens=256, entrada="texto_unico",
            modelo_base={"clave": base, "hub_id": hub, "revision": revision},
            checkpoints={"s42": {"ruta": f"{prefix}best_model",
                                 "sha256": sha256(weights).hexdigest()}},
            tokenizador={"ruta": f"{prefix}best_model",
                         "sha256_tokenizer_json": sha256(b"{\"t\": 1}").hexdigest()},
        )
    (folder / "contrato.json").write_text(json.dumps(contract))
    if metrics:
        (folder / "metricas.json").write_text(json.dumps({
            "modelo": tipo, "version": version, "orden_clases": ["falsa", "real"],
            "evaluaciones": [], "limitaciones": []}))
    return folder


class FakeService:
    def __init__(self, selection, weights):
        self.selection = selection
        self.predictor = selection.get("bilstm")
        self.mbert_predictor = selection.get("mbert")
        self.combination = SimpleNamespace(version=f"fake {weights['bilstm']:.2f}")


class Workspace(unittest.TestCase):
    def setUp(self):
        # Los contratos rotos y las cargas fallidas se registran a propósito.
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.datasets = self.root / "datasets"
        self.imports = self.datasets / "modelos"
        self.manifests = self.root / "manifiestos"
        (self.manifests / "bilstm").mkdir(parents=True)
        (self.manifests / "mbert").mkdir(parents=True)
        self.state = self.root / "local" / "estado.json"
        write_model(self.datasets / "corridas/bilstm/final", "bilstm", "B1_20260101",
                    weights=b"b1", training_paths=True)
        write_model(self.datasets / "corridas/bilstm/final_b2", "bilstm", "B2_20260201",
                    weights=b"b2", metrics=True)
        write_model(self.datasets / "corridas/mbert/final", "mbert", "M1_20260101", weights=b"m1")
        for tipo, version in (("bilstm", "B1_20260101"), ("mbert", "M1_20260101")):
            (self.manifests / tipo / f"{version}.json").write_text(json.dumps({
                "tipo": tipo, "version": version, "predeterminado": True,
                "contrato": str(next(self.datasets.glob(f"corridas/{tipo}/final/contrato.json"))),
            }))
        (self.manifests / "mbert" / "viejo.json").write_text(json.dumps(
            {"tipo": "mbert", "version": "viejo", "archivado": True, "nombre": "mBERT"}))
        (self.manifests / "bilstm" / "roto.json").write_text("{")
        self.swapped = []
        self.released = []

    def catalog(self):
        # Todo dentro de la carpeta temporal: las calibraciones reales del equipo no cuentan.
        return ModelCatalog(self.manifests, self.datasets, self.imports, self.datasets / "calibraciones")

    def manager(self, fail: set[str] = frozenset()):
        def builder(selection, weights, required):
            for tipo, entry in list(selection.items()):
                if entry is not None and entry.version in fail:
                    if tipo in required:
                        raise RuntimeError("no carga")
                    selection = {**selection, tipo: None}
            if not any(selection.values()):
                raise RuntimeError("nada")
            return FakeService({t: e and e.id for t, e in selection.items()}, weights)

        return ModelDeploymentManager(
            self.catalog(), self.state, builder=builder, check=lambda service: None,
            on_swap=self.swapped.append, release=self.released.append)

    def entry(self, tipo, model_id):
        return self.catalog().get(tipo, model_id)


class CatalogTests(Workspace):
    def test_detecta_entrenamientos_sin_repetir_los_del_repositorio(self):
        entries = {(e.tipo, e.id): e for e in self.catalog().entries()}
        self.assertEqual(set(entries), {("bilstm", "B1_20260101"), ("bilstm", "B2_20260201"),
                                        ("mbert", "M1_20260101"), ("mbert", "viejo")})
        self.assertEqual(entries[("bilstm", "B1_20260101")].origen, "repositorio")
        self.assertEqual(entries[("bilstm", "B2_20260201")].origen, "entrenamiento")
        self.assertEqual(entries[("bilstm", "B2_20260201")].estado, "disponible")
        self.assertIsNotNone(entries[("bilstm", "B2_20260201")].load_metrics())
        self.assertEqual(entries[("mbert", "viejo")].estado, "archivado")
        self.assertEqual(entries[("bilstm", "B2_20260201")].fecha, "2026-02-01")
        self.assertEqual(entries[("mbert", "M1_20260101")].nombre, "BETO")
        self.assertEqual(self.catalog().defaults(), {"bilstm": "B1_20260101", "mbert": "M1_20260101"})

    def test_rutas_del_entrenamiento_se_buscan_junto_al_contrato(self):
        folder = self.datasets / "corridas/bilstm/final"
        contract = ModelContract.load(folder / "contrato.json", "bilstm")
        self.assertEqual(contract.checkpoint, (folder / "todo_s42/modelo.pt").resolve())
        with self.assertRaises(ValueError):
            resolve("../../fuera.pt")

    def test_pendiente_de_calibrar_pasa_a_disponible_solo(self):
        folder = write_model(self.datasets / "nuevo/bilstm", "bilstm", "B3_20260301",
                             weights=b"b3", provisional=True)
        self.assertEqual(self.entry("bilstm", "B3_20260301").estado, "pendiente_calibrar")
        data = json.loads((folder / "contrato.json").read_text())
        data.update(temperatura=3.1, temperatura_provisional=False)
        (folder / "contrato.json").write_text(json.dumps(data))
        self.assertEqual(self.entry("bilstm", "B3_20260301").estado, "disponible")

    def test_solo_beto_y_mbert_y_pesos_comprobados(self):
        write_model(self.datasets / "otro/roberta", "mbert", "R1_20260101", weights=b"r", base="roberta")
        write_model(self.datasets / "otro/mbert", "mbert", "MB_20260101", weights=b"mb", base="mbert")
        self.assertEqual(self.entry("mbert", "R1_20260101").estado, "no_admitido")
        self.assertEqual(self.entry("mbert", "MB_20260101").nombre, "mBERT")
        self.assertEqual(self.entry("mbert", "MB_20260101").estado, "disponible")
        broken = write_model(self.datasets / "otro/roto", "bilstm", "B9_20260101", weights=b"x")
        (broken / "todo_s42/modelo.pt").write_bytes(b"cambiado")
        self.assertEqual(self.entry("bilstm", "B9_20260101").estado, "no_valido")
        with self.assertRaises(UnsupportedBaseModel):
            ModelContract.load(self.datasets / "otro/roberta/contrato.json", "mbert")

    def test_misma_version_con_otros_pesos_son_dos_modelos(self):
        write_model(self.datasets / "repeticion", "bilstm", "B2_20260201", weights=b"otro")
        ids = sorted(e.id for e in self.catalog().entries() if e.version == "B2_20260201")
        self.assertEqual(len(ids), 2)
        self.assertIn("B2_20260201", ids)
        self.assertTrue(any(i.startswith("B2_20260201-") for i in ids))

    def test_carpeta_de_busqueda_desde_el_entorno(self):
        from unittest.mock import patch

        from backend.services.model_registry import scan_dir_from_environment
        with patch.dict("os.environ", {"MODELOS_BUSCAR_EN": str(self.datasets / "corridas")}):
            self.assertEqual(scan_dir_from_environment(), (self.datasets / "corridas").resolve())
            self.assertEqual(ModelCatalog(self.manifests, imports_dir=self.imports).scan_dir,
                             (self.datasets / "corridas").resolve())
        with patch.dict("os.environ", {"MODELOS_BUSCAR_EN": ""}):
            self.assertTrue(str(scan_dir_from_environment()).endswith("datasets"))

    def test_no_entra_en_copias_de_respaldo(self):
        write_model(self.datasets / "respaldo_v1/bilstm", "bilstm", "B7_20260101", weights=b"b7")
        self.assertIsNone(self.entry("bilstm", "B7_20260101"))


class DeploymentTests(Workspace):
    def test_arranca_con_los_predeterminados(self):
        manager = self.manager()
        service = manager.start()
        self.assertEqual(service.selection, {"bilstm": "B1_20260101", "mbert": "M1_20260101"})
        self.assertEqual(manager.loaded, {"bilstm", "mbert"})
        self.assertIsNone(manager.previous_state())

    def test_desplegar_sustituye_al_del_mismo_tipo_y_se_puede_volver(self):
        manager = self.manager()
        manager.start()
        manager.deploy("bilstm", "B2_20260201", "admin@example.com")
        self.assertEqual(self.swapped[-1].selection, {"bilstm": "B2_20260201", "mbert": "M1_20260101"})
        again = self.manager()  # otro arranque lee lo guardado
        self.assertEqual(again.start().selection["bilstm"], "B2_20260201")
        again.revert("admin@example.com")
        self.assertEqual(again.state.deployed["bilstm"], "B1_20260101")
        self.assertEqual([(e["accion"], e["version"]) for e in again.history()],
                         [("revertir", None), ("desplegar", "B2_20260201")])
        with self.assertRaises(ModelVersionError) as raised:
            again.deploy("bilstm", "B1_20260101", None)
        self.assertEqual(raised.exception.code, "ya_desplegado")

    def test_retirar_cualquiera_pero_no_el_ultimo(self):
        for first, second in (("bilstm", "mbert"), ("mbert", "bilstm")):
            self.state.unlink(missing_ok=True)
            manager = self.manager()
            manager.start()
            manager.retire(first, None)
            self.assertEqual(manager.loaded, {second})
            self.assertIsNone(self.swapped[-1].selection[first])
            with self.assertRaises(ModelVersionError) as raised:
                manager.retire(second, None)
            self.assertEqual(raised.exception.code, "ultimo_modelo")
            manager.deploy(first, self.catalog().defaults()[first], None)
            self.assertEqual(manager.loaded, {"bilstm", "mbert"})

    def test_lo_que_falla_no_cambia_nada(self):
        write_model(self.datasets / "x/rota", "bilstm", "rota", weights=b"rota")
        manager = self.manager(fail={"rota"})
        manager.start()
        for tipo, model_id, code in (("bilstm", "rota", "modelo_no_cargo"),
                                     ("mbert", "viejo", "modelo_archivado"),
                                     ("bilstm", "nada", "modelo_desconocido")):
            with self.assertRaises(ModelVersionError) as raised:
                manager.deploy(tipo, model_id, None)
            self.assertEqual(raised.exception.code, code)
        self.assertEqual(manager.state.deployed["bilstm"], "B1_20260101")
        self.assertEqual(self.swapped, [])
        with self.assertRaises(ModelVersionError):
            manager.revert(None)

    def test_pesos(self):
        manager = self.manager()
        manager.start()
        manager.set_weights({"bilstm": 0.3, "mbert": 0.7}, None)
        self.assertEqual(manager.state.weights, {"bilstm": 0.3, "mbert": 0.7})
        self.assertEqual(self.swapped[-1].combination.version, "fake 0.30")
        for bad in ({"bilstm": 0.5, "mbert": 0.6}, {"bilstm": -0.1, "mbert": 1.1}):
            with self.assertRaises(ModelVersionError):
                manager.set_weights(bad, None)
        manager.revert(None)
        self.assertEqual(manager.state.weights, default_weights())

    def test_estado_roto_o_modelo_borrado_arranca_igual(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text("{roto")
        self.assertEqual(self.manager().start().selection["bilstm"], "B1_20260101")
        self.state.write_text(json.dumps({"desplegados": {"bilstm": "ya_no_existe", "mbert": "M1_20260101"},
                                          "pesos": {"bilstm": 0.2, "mbert": 0.8}, "historial": []}))
        manager = self.manager()
        self.assertEqual(manager.start().selection, {"bilstm": None, "mbert": "M1_20260101"})
        self.assertEqual(manager.loaded, {"mbert"})


def model_zip(folder: Path, inside: str = "modelo/") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in folder.rglob("*"):
            if path.is_file():
                archive.write(path, inside + path.relative_to(folder).as_posix())
    return buffer.getvalue()


class ImportTests(Workspace):
    def import_bytes(self, data: bytes):
        path = self.root / f"{uuid4().hex}.zip"
        path.write_bytes(data)
        return self.catalog().import_zip(path)

    def test_importar_desplegar_y_borrar(self):
        source = write_model(self.root / "fuera/b5", "bilstm", "B5_20260501", weights=b"b5",
                             training_paths=True, metrics=True)
        entry = self.import_bytes(model_zip(source))
        self.assertEqual((entry.tipo, entry.id, entry.origen, entry.estado),
                         ("bilstm", "B5_20260501", "importado", "disponible"))
        self.assertTrue((self.imports / "bilstm/B5_20260501/contrato.json").is_file())
        with self.assertRaises(ModelVersionError) as raised:
            self.import_bytes(model_zip(source))
        self.assertEqual(raised.exception.code, "version_existente")
        manager = self.manager()
        manager.start()
        manager.deploy("bilstm", "B5_20260501", None)
        with self.assertRaises(ModelVersionError) as raised:
            manager.delete("bilstm", "B5_20260501")
        self.assertEqual(raised.exception.code, "modelo_en_uso")
        manager.deploy("bilstm", "B2_20260201", None)
        manager.deploy("bilstm", "B1_20260101", None)
        manager.delete("bilstm", "B5_20260501")
        self.assertIsNone(self.entry("bilstm", "B5_20260501"))
        write_model(self.datasets / "corridas/bilstm/final_b4", "bilstm", "B4_20260401", weights=b"b4")
        with self.assertRaises(ModelVersionError) as raised:
            manager.delete("bilstm", "B4_20260401")  # los del entrenamiento no se borran
        self.assertEqual(raised.exception.code, "no_borrable")

    def test_zip_peligroso_o_incompleto(self):
        cases = []
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../fuera/contrato.json", "{}")
        cases.append((buffer.getvalue(), "zip_no_valido"))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("solo_pesos.pt", "x")
        cases.append((buffer.getvalue(), "modelo_no_valido"))
        source = write_model(self.root / "fuera/r", "mbert", "R_20260101", weights=b"r", base="roberta")
        cases.append((model_zip(source), "modelo_no_valido"))
        cases.append((b"no es zip", "zip_no_valido"))
        for data, code in cases:
            with self.assertRaises(ModelVersionError) as raised:
                self.import_bytes(data)
            self.assertEqual(raised.exception.code, code)
        self.assertEqual([p.name for p in (self.imports / ".importando").iterdir()], [])


class AnalysisWithoutOneModelTests(unittest.TestCase):
    def test_solo_beto(self):
        mbert = FakeMbert(0.8)
        service = AnalysisService(None, mbert_predictor=mbert, mbert_text_policy=FakeMbertPolicy(150),
                                  combination=combination())
        outcome = service.analyze(AnalysisRequest(texto=" ".join(f"p{i}" for i in range(300))))
        self.assertEqual(outcome.response.resultados["bilstm"].estado, "no_disponible")
        self.assertEqual(outcome.response.resultado_unificado.probabilidad_falsa, 0.8)
        self.assertEqual(len(outcome.text.split()), 150)
        self.assertTrue(outcome.truncated)
        self.assertEqual(set(outcome.model_texts), {"mbert"})
        with self.assertRaises(InvalidAnalysisInput):
            service.analyze(AnalysisRequest(texto="pocas palabras"))

    def test_solo_bilstm_y_ninguno(self):
        response = AnalysisService(FakeBilstm(0.4), combination=combination()).analyze(
            AnalysisRequest(texto=" ".join(["palabra"] * 120))).response
        self.assertEqual(response.resultados["mbert"].estado, "no_disponible")
        self.assertEqual(response.resultado_unificado.probabilidad_falsa, 0.4)
        with self.assertRaises(ValueError):
            AnalysisService(None, combination=combination())


class CombinationForModelsTests(unittest.TestCase):
    def test_lo_predeterminado_es_la_combinacion_calibrada(self):
        calibrated = Combination.load(COMBINATION_FILE)
        contracts = {name: SimpleNamespace(version=calibrated.model_versions[name],
                                           temperature=calibrated.temperatures[name])
                     for name in ("bilstm", "mbert")}
        self.assertIs(Combination.for_models(contracts, calibrated.weights, calibrated), calibrated)
        edited = Combination.for_models(contracts, {"bilstm": 0.3, "mbert": 0.7}, calibrated)
        self.assertNotEqual(edited.version, calibrated.version)
        self.assertEqual(edited.temperatures, calibrated.temperatures)
        self.assertEqual(edited.weights, {"bilstm": 0.3, "mbert": 0.7})
        alone = Combination.for_models({"mbert": contracts["mbert"]}, calibrated.weights, calibrated)
        self.assertEqual(alone.model_versions, {"mbert": calibrated.model_versions["mbert"]})
        with self.assertRaises(ValueError):
            Combination.for_models(contracts, {"bilstm": 0.5, "mbert": 0.6}, calibrated)

    def test_catalogo_del_repositorio(self):
        catalog = ModelCatalog()
        defaults = catalog.defaults()
        calibrated = Combination.load(COMBINATION_FILE)
        self.assertEqual(defaults, calibrated.model_versions)
        self.assertEqual(default_weights(), calibrated.weights)
        for tipo, model_id in defaults.items():
            entry = catalog.get(tipo, model_id)
            self.assertEqual(entry.estado, "disponible", entry.motivo)
            self.assertEqual(entry.load_metrics().version, entry.version)
        archived = [e for e in catalog.entries() if e.estado == "archivado"]
        self.assertEqual({e.tipo for e in archived}, {"bilstm", "mbert"})
        self.assertTrue(all(e.load_metrics() for e in archived))

    def test_cache_suelta_lo_que_no_se_usa(self):
        cache = PredictorCache()
        entry = SimpleNamespace(tipo="bilstm", contrato="a", sha256="1")
        cache._loaded[cache._key(entry)] = "modelo"
        cache._loaded[("bilstm", "b:2")] = "otro"
        cache.keep({"bilstm": entry, "mbert": None})
        self.assertEqual(list(cache._loaded.values()), ["modelo"])


class RouteTests(Workspace):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(admin_router)
        self.manager_ = self.manager()
        app.state.analysis_service = self.manager_.start()
        app.state.model_versions = self.manager_
        self.manager_.on_swap = lambda service: setattr(app.state, "analysis_service", service)
        user = SimpleNamespace(id=str(uuid4()), email="admin@example.com",
                               app_metadata={"role": "admin"})
        app.dependency_overrides[identity_service] = lambda: SimpleNamespace(
            verify_user=lambda token: user)
        app.dependency_overrides[service_repository] = lambda: SimpleNamespace(
            model_version_usage=lambda: {("bilstm", "B1_20260101"): 7})
        self.client = TestClient(app)
        self.auth = {"Authorization": "Bearer t"}

    def test_listar_desplegar_retirar_pesos_y_volver(self):
        self.assertEqual(self.client.get("/admin/modelos").status_code, 401)
        data = self.client.get("/admin/modelos", headers=self.auth).json()
        self.assertEqual(data["desplegados"], {"bilstm": "B1_20260101", "mbert": "M1_20260101"})
        self.assertEqual(data["cargados"], ["bilstm", "mbert"])
        b1 = next(m for m in data["modelos"]["bilstm"] if m["id"] == "B1_20260101")
        self.assertEqual((b1["desplegado"], b1["cargado"], b1["casos"]), (True, True, 7))
        data = self.client.post("/admin/modelos/desplegar", headers=self.auth,
                                json={"tipo": "bilstm", "id": "B2_20260201"}).json()
        self.assertEqual(data["desplegados"]["bilstm"], "B2_20260201")
        self.assertEqual(data["historial"][0]["por"], "admin@example.com")
        data = self.client.post("/admin/modelos/retirar", headers=self.auth, json={"tipo": "mbert"}).json()
        self.assertEqual(data["cargados"], ["bilstm"])
        last = self.client.post("/admin/modelos/retirar", headers=self.auth, json={"tipo": "bilstm"})
        self.assertEqual((last.status_code, last.json()["detail"]["codigo"]), (409, "ultimo_modelo"))
        bad = self.client.put("/admin/modelos/pesos", headers=self.auth, json={"bilstm": 0.5, "mbert": 0.6})
        self.assertEqual(bad.status_code, 422)
        data = self.client.put("/admin/modelos/pesos", headers=self.auth,
                               json={"bilstm": 0.4, "mbert": 0.6}).json()
        self.assertEqual(data["pesos"], {"bilstm": 0.4, "mbert": 0.6})
        self.assertEqual(data["combinacion"], "fake 0.40")
        data = self.client.post("/admin/modelos/revertir", headers=self.auth).json()
        self.assertEqual(data["pesos"], {"bilstm": 0.2, "mbert": 0.8})

    def test_importar_zip_por_la_api(self):
        source = write_model(self.root / "fuera/b6", "bilstm", "B6_20260601", weights=b"b6")
        response = self.client.post("/admin/modelos/importar", headers={
            **self.auth, "Content-Type": "application/zip"}, content=model_zip(source))
        self.assertEqual(response.status_code, 200, response.text)
        ids = [m["id"] for m in response.json()["modelos"]["bilstm"]]
        self.assertIn("B6_20260601", ids)
        response = self.client.delete("/admin/modelos/bilstm/B6_20260601", headers=self.auth)
        self.assertNotIn("B6_20260601", [m["id"] for m in response.json()["modelos"]["bilstm"]])
        empty = self.client.post("/admin/modelos/importar", headers=self.auth, content=b"")
        self.assertEqual(empty.json()["detail"]["codigo"], "zip_vacio")


class PublishedMetricsTests(Workspace):
    """`GET /metricas` publica las del modelo desplegado de cada tipo, nunca las de otro."""

    def setUp(self):
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(metrics_router)
        self.manager_ = self.manager()
        self.manager_.start()
        self.app.state.model_versions = self.manager_
        self.client = TestClient(self.app)

    def metrics(self, modelo):
        response = self.client.get("/metricas", params={"modelo": modelo})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_las_del_desplegado_o_vacias_con_el_motivo(self):
        self.manager_.deploy("bilstm", "B2_20260201", None)  # trae metricas.json
        self.assertEqual(self.metrics("bilstm")["version"], "B2_20260201")
        self.manager_.deploy("bilstm", "B1_20260101", None)  # no trae métricas
        data = self.metrics("bilstm")
        self.assertEqual((data["version"], data["evaluaciones"]), ("B1_20260101", []))
        self.assertIn("no tiene métricas publicadas", data["limitaciones"][0])
        self.manager_.retire("mbert", None)
        data = self.metrics("mbert")
        self.assertEqual((data["version"], data["evaluaciones"]), ("ninguno", []))

    def test_sin_gestor_las_de_produccion(self):
        self.app.state.model_versions = None
        data = self.metrics("bilstm")
        self.assertEqual(data["version"], "comun_v1.1_B6_20261107")
        self.assertTrue(data["evaluaciones"])


if __name__ == "__main__":
    unittest.main()
