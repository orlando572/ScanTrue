"""Calibración del panel: candidatos, vista previa, versión calibrada nueva y rutas.

Uso: PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m unittest backend.tests.test_calibration
"""

import json
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd

from backend.api.admin_routes import router as admin_router
from backend.api.dependencies import identity_service, service_repository
from backend.models.contrato import COMBINATION_FILE, ModelContract
from backend.services.calibration import CalibrationError, CalibrationManager
from backend.services.model_registry import ModelCatalog, calibration_for
from backend.tests.test_model_registry import write_model

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "backend" / ".local"


def write_oof(path: Path, tipo: str, scale: float, seed: int = 42, labels: bool = True, n: int = 90) -> None:
    """Predicciones fuera de pliegue sintéticas: z ∝ etiqueta con ruido, tres fuentes F1–F3."""
    rng = np.random.default_rng(seed + (0 if tipo == "bilstm" else 1))
    rows = []
    for fold, source in (("F1", "v1"), ("F2", "fakedes"), ("F3", "polyglot")):
        for i in range(n):
            y = i % 2
            z = scale * ((2 * y - 1) + rng.normal(0, 1.2))
            row = {"id_fragmento": f"{source}{i}#0", "modelo": tipo, "configuracion": "X", "semilla": seed,
                   "pliegue": fold, "logit_real": 0.0, "logit_falsa": z, "prob_falsa": 1 / (1 + np.exp(-z))}
            if labels:
                row.update(id_articulo=f"{source}{i}", fuente=source, etiqueta_falsa=y)
            rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)


class Workspace(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        LOCAL.mkdir(parents=True, exist_ok=True)
        # Dentro del repositorio (en backend/.local, fuera de Git): los contratos calibrados citan
        # sus pesos desde la raíz, como en producción.
        self.folder = tempfile.TemporaryDirectory(dir=LOCAL)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.datasets = self.root / "datasets"
        self.output = self.datasets / "calibraciones"
        (self.root / "manifiestos/bilstm").mkdir(parents=True)
        (self.root / "manifiestos/mbert").mkdir(parents=True)
        self.b = self.model("bilstm", "B9_20261101", scale=6.0)
        self.m = self.model("mbert", "M9_20261101", scale=2.0)

    def model(self, tipo, version, scale, provisional=True, **extra):
        folder = write_model(self.datasets / "entrenamientos" / tipo / version, tipo, version,
                             weights=version.encode(), provisional=provisional, metrics=True)
        contract = json.loads((folder / "contrato.json").read_text())
        contract.update(sha256_conjunto="conjunto-x", predicciones_fuera_de_pliegue="predicciones_fuera_de_pliegue.csv",
                        eleccion={"ganador_regla": version.split("_")[0]}, **extra)
        (folder / "contrato.json").write_text(json.dumps(contract))
        write_oof(folder / "predicciones_fuera_de_pliegue.csv", tipo, scale)
        return folder

    def catalog(self):
        return ModelCatalog(self.root / "manifiestos", self.datasets, self.datasets / "modelos", self.output)

    def manager(self):
        return CalibrationManager(self.catalog(), self.output, comun=lambda: None, comun_sha=lambda: None)


class CandidateTests(Workspace):
    def test_aptos_y_motivos(self):
        no_oof = write_model(self.datasets / "entrenamientos/bilstm/B8_20261101", "bilstm", "B8_20261101",
                             weights=b"b8", provisional=True)
        other_seed = self.model("bilstm", "B7_20261101", scale=5.0)
        contract = json.loads((other_seed / "contrato.json").read_text())
        contract["semillas"] = [43]
        contract["checkpoints"] = {"s43": contract["checkpoints"]["s42"]}
        (other_seed / "contrato.json").write_text(json.dumps(contract))
        candidates = {item["id"]: item for group in self.manager().candidates().values() for item in group}
        self.assertTrue(candidates["B9_20261101"]["apto"])
        self.assertTrue(candidates["M9_20261101"]["apto"])
        self.assertIn("Preparar para calibrar", candidates["B8_20261101"]["motivo"])
        self.assertIn("semilla 43", candidates["B7_20261101"]["motivo"])
        self.assertTrue(no_oof.exists())


class PreviewAndSaveTests(Workspace):
    def test_vista_previa_ajustada_y_a_mano(self):
        manager = self.manager()
        fitted = manager.preview("B9_20261101", "M9_20261101", 0.2, None)
        self.assertTrue(fitted["conjunto_comun"])
        self.assertGreater(fitted["temperaturas"]["bilstm"]["ajustada"], 1.0)
        self.assertEqual(fitted["resultado"]["metodo_elegido"], "combinacion_bilstm_0.20")
        self.assertIn("validacion_por_fuente", fitted["resultado"])
        manual = manager.preview("B9_20261101", "M9_20261101", 0.35, {"bilstm": 3.0, "mbert": None})
        self.assertEqual(manual["temperaturas"]["bilstm"], {"ajustada": fitted["temperaturas"]["bilstm"]["ajustada"],
                                                            "usada": 3.0, "manual": True})
        self.assertFalse(manual["temperaturas"]["mbert"]["manual"])
        self.assertEqual(manual["combinacion"]["pesos"], {"bilstm": 0.35, "mbert": 0.65})
        self.assertEqual(manual["resultado"]["metodo_elegido"], "combinacion_elegida")
        self.assertFalse(manual["igual_a_produccion"])
        with self.assertRaises(CalibrationError) as caught:
            manager.preview("no-existe", "M9_20261101", 0.2, None)
        self.assertEqual(caught.exception.status_code, 404)

    def test_guardar_crea_version_calibrada_sin_tocar_los_modelos(self):
        manager = self.manager()
        before = {path: path.read_bytes() for path in self.datasets.rglob("contrato.json")}
        with self.assertRaises(CalibrationError) as caught:  # peso distinto del vigente sin motivo
            manager.save("B9_20261101", "M9_20261101", 0.3, None, "", "admin")
        self.assertEqual(caught.exception.code, "falta_motivo")
        saved = manager.save("B9_20261101", "M9_20261101", 0.3, {"mbert": 1.5}, "Prueba de pesos", "admin")
        self.assertEqual({p: p.read_bytes() for p in before}, before)  # ningún contrato existente cambió
        folder = self.output / saved["version"]
        self.assertTrue((folder / "combinacion.json").is_file() and (folder / "RESUMEN.md").is_file())
        self.assertFalse(any(path.name.endswith(".parcial") for path in self.output.iterdir()))
        combination = json.loads((folder / "combinacion.json").read_text())
        self.assertEqual(combination["temperaturas"]["mbert"], 1.5)
        self.assertEqual(combination["pesos"], {"bilstm": 0.3, "mbert": 0.7})
        for tipo, source in (("bilstm", self.b), ("mbert", self.m)):
            variant = ModelContract.load(folder / tipo / "contrato.json", tipo)  # ya no es provisional
            original = ModelContract.load(source / "contrato.json", tipo, allow_provisional=True)
            self.assertEqual(variant.checkpoint, original.checkpoint)  # mismos pesos, sin copiarlos
            self.assertEqual(variant.temperature, combination["temperaturas"][tipo])
            self.assertEqual(combination["contratos"][tipo], variant.version)
            self.assertTrue(variant.version.startswith(original.version + "_cal_"))
        entries = {entry.id: entry for entry in self.catalog().entries()}
        variant_b = entries[combination["contratos"]["bilstm"]]
        self.assertEqual((variant_b.origen, variant_b.estado), ("calibracion", "disponible"))
        self.assertEqual(entries["B9_20261101"].estado, "pendiente_calibrar")
        self.assertIsNotNone(variant_b.load_metrics())
        found = calibration_for(combination["contratos"], self.output)
        self.assertEqual((found.version, found.weights["bilstm"]), (saved["version"], 0.3))
        listing = manager.overview()
        self.assertEqual([item["version"] for item in listing["calibraciones"]], [saved["version"]])
        detail = manager.get(saved["version"])
        self.assertIn("validacion_por_fuente", detail["resultado"])
        # Una variante calibrada también se puede volver a calibrar (usa las mismas predicciones).
        self.assertTrue(manager.candidate(variant_b)["apto"])

    def test_conjuntos_distintos_calibra_cada_modelo_por_su_lado(self):
        contract = json.loads((self.m / "contrato.json").read_text())
        contract["sha256_conjunto"] = "otro-conjunto"
        (self.m / "contrato.json").write_text(json.dumps(contract))
        preview = self.manager().preview("B9_20261101", "M9_20261101", 0.2, None)
        self.assertFalse(preview["conjunto_comun"])
        self.assertIn("validacion_por_modelo", preview["resultado"])
        self.assertNotIn("validacion_por_fuente", preview["resultado"])


class ProductionTests(unittest.TestCase):
    """Con B6 + M3b, peso 0,2 y temperaturas ajustadas: la calibración de producción, idéntica."""

    def test_mismo_resultado_que_produccion(self):
        reference_file = ROOT / "datasets/comun_v1_corridas/calibracion/metricas.json"
        needed = [reference_file, ROOT / "datasets/comun_v1_corridas/bilstm/final/predicciones_fuera_de_pliegue.csv",
                  ROOT / "datasets/comun_v1_corridas/mbert/final/predicciones_fuera_de_pliegue.csv",
                  ROOT / "datasets/comun_v1/manifest.json"]
        if not all(path.is_file() for path in needed):
            self.skipTest("faltan las predicciones o la calibración de producción")
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            manager = CalibrationManager(ModelCatalog(), Path(tmp))
            preview = manager.preview("comun_v1.1_B6_20261107", "comun_v1.1_M3b_20261111", 0.2, None)
        reference = json.loads(reference_file.read_text())
        production = json.loads(COMBINATION_FILE.read_text())
        self.assertTrue(preview["igual_a_produccion"])
        self.assertEqual(preview["combinacion"]["temperaturas"], production["temperaturas"])
        self.assertEqual(preview["combinacion"]["pesos"], production["pesos"])
        for key in ("semillas_mbert", "validacion_por_fuente", "metodo_elegido", "niveles", "regla_discrepancia",
                    "comparaciones_pareadas"):
            self.assertEqual(json.loads(json.dumps(preview["resultado"][key])), reference[key], key)


class RouteTests(Workspace):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(admin_router)
        catalog = self.catalog()

        def forbidden(*args, **kwargs):
            raise AssertionError("Calibración no debe desplegar ni borrar modelos")

        app.state.model_versions = SimpleNamespace(
            catalog=catalog, selection=lambda: {"bilstm": catalog.get("bilstm", "B9_20261101"),
                                                "mbert": catalog.get("mbert", "M9_20261101")},
            deploy=forbidden, retire=forbidden, delete=forbidden, set_weights=forbidden)
        app.state.calibration = CalibrationManager(catalog, self.output, comun=lambda: None, comun_sha=lambda: None)
        user = SimpleNamespace(id=str(uuid4()), email="admin@example.com", app_metadata={"role": "admin"})
        app.dependency_overrides[identity_service] = lambda: SimpleNamespace(verify_user=lambda token: user)
        app.dependency_overrides[service_repository] = lambda: SimpleNamespace()
        self.client = TestClient(app)
        self.auth = {"Authorization": "Bearer t"}

    def test_flujo_completo(self):
        self.assertEqual(self.client.get("/admin/calibraciones/opciones").status_code, 401)
        options = self.client.get("/admin/calibraciones/opciones", headers=self.auth).json()
        self.assertEqual((options["por_defecto"]["bilstm"], options["por_defecto"]["mbert"]),
                         ("B9_20261101", "M9_20261101"))
        self.assertIsNone(options["vigente"])
        body = {"bilstm": "B9_20261101", "mbert": "M9_20261101", "peso_bilstm": 0.2}
        preview = self.client.post("/admin/calibraciones/vista-previa", headers=self.auth, json=body)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn("temperaturas", preview.json())
        saved = self.client.post("/admin/calibraciones", headers=self.auth, json=body)
        self.assertEqual(saved.status_code, 201, saved.text)
        version = saved.json()["version"]
        listing = self.client.get("/admin/calibraciones", headers=self.auth).json()
        self.assertEqual(listing["calibraciones"][0]["version"], version)
        self.assertEqual(self.client.get(f"/admin/calibraciones/{version}", headers=self.auth).status_code, 200)
        self.assertEqual(self.client.get("/admin/calibraciones/no-existe", headers=self.auth).status_code, 404)
        bad = self.client.post("/admin/calibraciones/vista-previa", headers=self.auth,
                               json={**body, "temperaturas": {"bilstm": -1}})
        self.assertEqual(bad.status_code, 422)


if __name__ == "__main__":
    unittest.main()
