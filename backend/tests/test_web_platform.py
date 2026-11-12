"""Web pública, panel, datasets y versiones de modelos, sin Supabase ni pesos.

Uso: PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m unittest backend.tests.test_web_platform
"""

from datetime import date, datetime, timezone
import json
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.admin_routes import router as admin_router
from backend.api.dependencies import identity_service, service_repository
from backend.api.public_routes import router as public_router
from backend.repositories.filters import (
    AnalysisFilters, clean_domain, clean_query, filter_params, public_url,
)
from backend.repositories.supabase import SupabaseRepository, web_select
from backend.schemas.admin import AdminCaseDetail, AdminCasePage
from backend.schemas.analysis import AnalysisRequest
from backend.schemas.public import PublicAnalysis, PublicAnalysisDetail, PublicAnalysisPage
from backend.services.analysis import clean_fragments
from backend.services.datasets import build_dataset, export_csv
from backend.services.model_versions import ModelVersionError, ModelVersionManager

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
ROW = {
    "id": str(uuid4()),
    "fecha": NOW.isoformat(),
    "usuario_id": str(uuid4()),
    "url": "https://usuario:clave@www.noticias.example.com/politica/nota?token=secreto#parte",
    "texto": "Primer fragmento de prueba. Segundo fragmento de prueba.",
    "texto_original": "Primer fragmento de prueba. Segundo fragmento de prueba. Y algo más.",
    "fragmentos": ["Primer fragmento de prueba.", "Segundo fragmento de prueba. Y algo más."],
    "texto_recortado": True,
    "hash_texto": "a" * 64,
    "resultado_unificado": {
        "probabilidad_falsa": 0.73, "modelos_utilizados": ["bilstm", "mbert"],
        "pesos_aplicados": {"bilstm": 0.2, "mbert": 0.8},
    },
    "comparacion": "discrepan",
    "estado_blockchain": "confirmado",
    "hash_transaccion": None,
    "oculto": False,
    "resultados_modelo": [
        {"modelo": "bilstm", "version": "B", "clase": "real", "probabilidad_falsa": 0.4,
         "tokens_leidos": 8, "texto_modelo": "Primer fragmento de prueba."},
        {"modelo": "mbert", "version": "M", "clase": "falsa", "probabilidad_falsa": 0.8,
         "tokens_leidos": 12, "texto_modelo": "Primer fragmento de prueba. Segundo"},
    ],
    "verificaciones_web": None,
    "revisiones": {"decision": "corregido", "etiqueta_final": "real", "nota": "n",
                   "evidencia": ["https://fuente.example"], "grupo_evento": None,
                   "fecha": NOW.isoformat()},
}


class FilterTests(unittest.TestCase):
    def test_busqueda_sin_caracteres_de_control_de_postgrest(self):
        self.assertEqual(clean_query('  vacuna, (5g)* "x" %_ '), "vacuna 5g x")
        self.assertIsNone(clean_query("*,()"))
        params = dict(filter_params(AnalysisFilters(q="vacuna")))
        self.assertEqual(params["or"], '(texto.ilike."*vacuna*",url.ilike."*vacuna*")')

    def test_nivel_usa_los_cortes_del_redondeo(self):
        params = filter_params(AnalysisFilters(nivel=3))
        self.assertIn(("probabilidad_unificada", "gte.0.405"), params)
        self.assertIn(("probabilidad_unificada", "lt.0.605"), params)
        self.assertEqual(
            [value for key, value in filter_params(AnalysisFilters(nivel=5))
             if key == "probabilidad_unificada"], ["gte.0.805"])

    def test_fechas_son_dias_completos_de_peru(self):
        params = filter_params(AnalysisFilters(desde=date(2026, 11, 1), hasta=date(2026, 11, 1)))
        self.assertIn(("fecha", "gte.2026-11-01T00:00:00-05:00"), params)
        self.assertIn(("fecha", "lt.2026-11-02T00:00:00-05:00"), params)

    def test_dominio_revision_verificacion_y_orden(self):
        self.assertEqual(clean_domain(" WWW.Diario.PE "), "diario.pe")
        self.assertIsNone(clean_domain("diario.pe,or(x)"))
        params = filter_params(AnalysisFilters(
            dominio="diario.pe,x", revision="pendiente", verificacion="contradicha",
            orden="prioridad", oculto=False))
        self.assertIn(("dominio", "eq.-"), params)
        self.assertIn(("revisiones", "is.null"), params)
        self.assertIn(("verificaciones_web.conclusion", "eq.contradicha"), params)
        self.assertIn(("oculto", "is.false"), params)
        self.assertEqual(params[-1], ("order", "discrepa.desc,fecha.desc,id.desc"))

    def test_un_filtro_sobre_tabla_hija_exige_la_fila(self):
        self.assertIn("verificaciones_web(", web_select())
        self.assertIn("verificaciones_web!inner(",
                      web_select(AnalysisFilters(verificacion="respaldada")))
        self.assertNotIn("revisiones", web_select(AnalysisFilters(revision="aprobado")))
        self.assertIn("revisiones!inner(",
                      web_select(AnalysisFilters(revision="revisado"), admin=True))
        self.assertIn("revisiones(", web_select(AnalysisFilters(revision="pendiente"), admin=True))

    def test_url_publica_sin_credenciales_ni_consulta(self):
        self.assertEqual(public_url(ROW["url"]),
                         ("noticias.example.com", "https://www.noticias.example.com/politica/nota"))
        self.assertEqual(public_url("javascript:alert(1)"), (None, None))
        self.assertEqual(public_url("http://[mal"), (None, None))


class RecordTests(unittest.TestCase):
    def test_la_lista_no_expone_usuario_ni_texto_por_modelo(self):
        record = PublicAnalysis(**SupabaseRepository._web_fields(dict(ROW), detail=False))
        data = record.model_dump_json()
        self.assertNotIn(ROW["usuario_id"], data)
        self.assertNotIn("secreto", data)
        self.assertEqual(record.fragmentos, ROW["fragmentos"])
        self.assertEqual(record.palabras, 8)
        self.assertTrue(record.texto_recortado)
        self.assertEqual(record.probabilidad_falsa, 0.73)
        self.assertIsNone(record.resultados["mbert"].texto_modelo)
        self.assertIsNone(record.verificacion_web)

    def test_el_detalle_trae_el_texto_de_cada_modelo(self):
        record = PublicAnalysisDetail(**SupabaseRepository._web_fields(dict(ROW), detail=True))
        self.assertEqual(record.resultados["bilstm"].texto_modelo, "Primer fragmento de prueba.")
        self.assertEqual(record.texto_original, ROW["texto_original"])

    def test_registro_antiguo_cuenta_como_un_fragmento_abreviado(self):
        row = {**ROW, "fragmentos": None, "texto_original": None, "texto": "palabra " * 400}
        record = PublicAnalysis(**SupabaseRepository._web_fields(row, detail=False))
        self.assertEqual(record.fragmentos_total, 1)
        self.assertLessEqual(len(record.fragmentos[0]), 700)
        self.assertTrue(record.fragmentos[0].endswith("…"))

    def test_verificacion_web_y_revision(self):
        row = {**ROW, "verificaciones_web": [{"estado": "completada", "conclusion": "contradicha"}]}
        record = PublicAnalysis(**SupabaseRepository._web_fields(row, detail=False))
        self.assertEqual(record.verificacion_web.conclusion, "contradicha")
        extra = SupabaseRepository._admin_fields(row)
        self.assertEqual(extra["etiqueta_modelo"], "falsa")
        self.assertEqual(extra["revision"].etiqueta_final, "real")

    def test_fragmentos_solo_si_forman_el_texto(self):
        self.assertEqual(clean_fragments(["Uno  dos", " tres "], "Uno dos tres"), ["Uno dos", "tres"])
        self.assertIsNone(clean_fragments(["Uno dos", "tres"], "Uno dos editado"))
        self.assertIsNone(clean_fragments(None, "x"))
        self.assertEqual(AnalysisRequest(texto="x", fragmentos=["x"]).fragmentos, ["x"])


class FakeRepository:
    def __init__(self):
        self.filters = None
        self.reviews = {}
        self.hidden = False

    def list_public_analysis(self, filters, limit, offset):
        self.filters = filters
        record = PublicAnalysis(**SupabaseRepository._web_fields(dict(ROW), detail=False))
        return PublicAnalysisPage(elementos=[record], total=1)

    def get_public_analysis(self, analysis_id):
        return None

    def list_admin_cases(self, filters, limit, offset):
        self.filters = filters
        return AdminCasePage(elementos=[], total=0)

    def get_admin_case(self, analysis_id):
        row = {**ROW, "id": str(analysis_id), "revisiones": None, "oculto": self.hidden}
        fields = SupabaseRepository._web_fields(row, detail=True)
        extra = SupabaseRepository._admin_fields(row)
        return AdminCaseDetail(**fields, **{**extra, "revision": self.reviews.get(analysis_id)})

    def set_hidden(self, analysis_id, hidden):
        self.hidden = hidden
        return True

    def save_review(self, analysis_id, reviewer_id, review):
        self.reviews[analysis_id] = review

    def delete_review(self, analysis_id):
        return self.reviews.pop(analysis_id, None) is not None

    def reviewed_cases(self):
        return []


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeRepository()
        self.role = "admin"
        user = lambda: SimpleNamespace(
            id=str(uuid4()), email="admin@example.com", app_metadata={"role": self.role})
        app = FastAPI()
        app.include_router(public_router)
        app.include_router(admin_router)
        app.dependency_overrides[service_repository] = lambda: self.repository
        app.dependency_overrides[identity_service] = lambda: SimpleNamespace(
            verify_user=lambda token: user())
        self.client = TestClient(app)
        self.auth = {"Authorization": "Bearer t"}

    def test_lista_publica_sin_sesion_y_con_filtros(self):
        response = self.client.get(
            "/publico/analisis",
            params={"q": "vacuna", "nivel": 4, "comparacion": "discrepan",
                    "desde": "2026-11-01", "orden": "mas_falsa"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertNotIn("usuario_id", response.text)
        self.assertEqual(self.repository.filters.nivel, 4)
        self.assertEqual(self.repository.filters.desde, date(2026, 11, 1))
        self.assertEqual(self.client.get("/publico/analisis?nivel=9").status_code, 422)
        self.assertEqual(self.client.get("/publico/analisis?orden=prioridad").status_code, 422)
        self.assertEqual(self.client.get(f"/publico/analisis/{uuid4()}").status_code, 404)

    def test_el_panel_exige_sesion_y_rol(self):
        self.assertEqual(self.client.get("/admin/casos").status_code, 401)
        self.role = "user"
        response = self.client.get("/admin/casos", headers=self.auth)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["codigo"], "no_es_admin")
        self.role = "admin"
        self.assertEqual(self.client.get("/admin/yo", headers=self.auth).json()["rol"], "admin")
        self.assertEqual(self.client.get("/admin/casos", headers=self.auth).status_code, 200)
        self.assertEqual(self.repository.filters.orden, "prioridad")

    def test_aprobar_corregir_descartar_y_deshacer(self):
        case = uuid4()
        url = f"/admin/casos/{case}/revision"
        approved = self.client.put(url, headers=self.auth, json={"decision": "aprobado"}).json()
        self.assertEqual(approved["revision"]["etiqueta_final"], "falsa")  # la del modelo (0,73)
        self.assertEqual(
            self.client.put(url, headers=self.auth, json={"decision": "corregido"}).status_code, 422)
        corrected = self.client.put(url, headers=self.auth, json={
            "decision": "corregido", "etiqueta_final": "real", "nota": "  desmentida  ",
            "evidencia": [" https://fuente.example ", ""], "grupo_evento": " Paro  minero "}).json()
        self.assertEqual(corrected["revision"]["etiqueta_final"], "real")
        self.assertEqual(corrected["revision"]["nota"], "desmentida")
        self.assertEqual(corrected["revision"]["evidencia"], ["https://fuente.example"])
        self.assertEqual(corrected["revision"]["grupo_evento"], "Paro minero")
        discarded = self.client.put(url, headers=self.auth, json={
            "decision": "descartado", "etiqueta_final": "real"}).json()
        self.assertIsNone(discarded["revision"]["etiqueta_final"])
        self.assertIsNone(self.client.delete(url, headers=self.auth).json()["revision"])

    def test_ocultar_y_dataset_vacio(self):
        case = uuid4()
        hidden = self.client.patch(f"/admin/casos/{case}", headers=self.auth, json={"oculto": True})
        self.assertTrue(hidden.json()["oculto"])
        self.assertEqual(self.client.get("/admin/datasets/vista-previa", headers=self.auth).json()["casos"], 0)
        created = self.client.post("/admin/datasets", headers=self.auth, json={"nombre": "v1"})
        self.assertEqual(created.status_code, 409)
        self.assertEqual(created.json()["detail"]["codigo"], "sin_casos_aprobados")


def reviewed(text, label, *, url=None, event=None, decision="aprobado"):
    return {
        "decision": decision, "etiqueta_final": label, "nota": None, "evidencia": ["https://f.example"],
        "grupo_evento": event, "fecha": NOW.isoformat(),
        "analisis": {
            "id": str(uuid4()), "fecha": NOW.isoformat(), "url": url, "texto": text,
            "texto_original": None, "hash_texto": "b" * 64, "comparacion": "coinciden",
            "resultado_unificado": {"probabilidad_falsa": 0.9},
            "resultados_modelo": [{"modelo": "bilstm", "version": "B", "probabilidad_falsa": 0.8}],
        },
    }


class DatasetTests(unittest.TestCase):
    def test_duplicados_conflictos_y_grupos(self):
        rows = [
            reviewed("El alcalde anunció la obra.", "real"),
            reviewed("EL ALCALDE anunció, la obra", "real", decision="corregido"),  # copia exacta
            reviewed("La vacuna cambia el ADN.", "falsa"),
            reviewed("La vacuna cambia el ADN", "real"),  # misma huella, etiqueta contraria
            reviewed("Paro minero: primer párrafo.", "real", url="https://d.pe/paro?x=1"),
            reviewed("Paro minero: segundo párrafo.", "real", url="https://d.pe/paro"),
            reviewed("Otro medio sobre el paro.", "real", event=" Paro  Minero "),
            reviewed("Más sobre el paro en otro sitio.", "falsa", event="paro minero"),
            reviewed("Sin etiqueta", None),
        ]
        build = build_dataset(rows, 0.2)
        summary = build.summary
        self.assertEqual(summary.candidatos, 8)
        self.assertEqual(summary.duplicados_retirados, 1)
        self.assertEqual(summary.conflictos_retirados, 2)
        self.assertEqual(summary.casos, 5)
        self.assertEqual(summary.grupos, 3)
        self.assertEqual(summary.grupos_con_varios, 2)
        self.assertEqual(summary.por_etiqueta, {"real": 4, "falsa": 1})
        # Se conserva la revisión más reciente de la copia exacta.
        kept = next(item for item in build.items if "alcalde" in item.texto.casefold())
        self.assertEqual(kept.decision, "corregido")
        # Ningún grupo cruza entre particiones.
        partitions = {}
        for item in build.items:
            partitions.setdefault(item.grupo, set()).add(item.particion)
        self.assertTrue(all(len(value) == 1 for value in partitions.values()))
        self.assertEqual(len({item.grupo for item in build.items if "paro" in item.texto.casefold()}
                             - {item.grupo for item in build.items if "párrafo" in item.texto}), 1)

    def test_la_particion_es_estable_y_respeta_la_fraccion(self):
        rows = [reviewed(f"Noticia número {index} sobre un tema distinto.", "real")
                for index in range(400)]
        first, second = build_dataset(rows, 0.2), build_dataset(list(reversed(rows)), 0.2)
        self.assertEqual({(i.texto, i.particion) for i in first.items},
                         {(i.texto, i.particion) for i in second.items})
        self.assertTrue(50 <= first.summary.por_particion["prueba"] <= 110)

    def test_csv_con_procedencia(self):
        build = build_dataset([reviewed('Texto con "comillas", y coma.', "falsa", url="https://d.pe/n")])
        lines = export_csv(build.items).splitlines()
        self.assertTrue(lines[0].startswith("id,particion,etiqueta,texto,"))
        self.assertIn('"Texto con ""comillas"", y coma."', lines[1])
        self.assertIn("d.pe", lines[1])
        self.assertIn("0.9", lines[1])


class ModelVersionTests(unittest.TestCase):
    def setUp(self):
        # Los manifiestos rotos y las cargas fallidas de estas pruebas se registran a propósito.
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.directory = root / "despliegues"
        self.directory.mkdir()
        self.state = root / "local" / "activo.json"
        base = {"contratos": {"bilstm": "datasets/a.json", "mbert": "datasets/b.json"},
                "combinacion": "datasets/c.json"}
        for name, extra in (("v1", {"fecha": "2026-01-01", "predeterminado": True}),
                            ("v2", {"fecha": "2026-02-01"}),
                            ("rota", {"fecha": "2026-03-01"})):
            (self.directory / f"{name}.json").write_text(json.dumps({"version": name, **base, **extra}))
        (self.directory / "vieja.json").write_text(json.dumps({"version": "vieja", "activable": False}))
        (self.directory / "invalida.json").write_text("{")
        self.swapped = []

    def manager(self):
        def builder(deployment, strict):
            if deployment.version == "rota":
                raise RuntimeError("no carga")
            return f"servicio-{deployment.version}"

        return ModelVersionManager(self.directory, self.state, builder=builder,
                                   check=lambda service: None, on_swap=self.swapped.append)

    def test_arranca_con_la_predeterminada_y_lista_las_validas(self):
        manager = self.manager()
        self.assertEqual([d.version for d in manager.deployments()], ["rota", "v2", "v1", "vieja"])
        self.assertEqual(manager.start(), "servicio-v1")
        self.assertEqual(manager.current_version, "v1")
        self.assertIsNone(manager.previous_version())

    def test_activar_revertir_y_persistir(self):
        manager = self.manager()
        manager.start()
        manager.activate("v2", "admin@example.com")
        self.assertEqual(self.swapped, ["servicio-v2"])
        self.assertEqual(manager.previous_version(), "v1")
        # Otro proceso arranca con la versión guardada.
        again = self.manager()
        self.assertEqual(again.start(), "servicio-v2")
        self.assertEqual(again.revert("admin@example.com"), "v1")
        self.assertEqual(again.current_version, "v1")
        history = again.history()
        self.assertEqual([(e["accion"], e["version"], e["anterior"]) for e in history],
                         [("revertir", "v1", "v2"), ("activar", "v2", "v1")])
        self.assertEqual(again.previous_version(), "v2")

    def test_una_version_que_falla_no_sustituye_a_la_activa(self):
        manager = self.manager()
        manager.start()
        for version, code in (("rota", "version_no_cargo"), ("vieja", "version_no_activable"),
                              ("nada", "version_desconocida"), ("v1", "version_ya_activa")):
            with self.assertRaises(ModelVersionError) as raised:
                manager.activate(version, None)
            self.assertEqual(raised.exception.code, code)
        self.assertEqual(manager.current_version, "v1")
        self.assertEqual(self.swapped, [])
        with self.assertRaises(ModelVersionError):
            manager.revert(None)

    def test_si_la_guardada_falla_arranca_la_predeterminada(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text(json.dumps({"activa": "rota", "historial": []}))
        manager = self.manager()
        self.assertEqual(manager.start(), "servicio-v1")
        self.assertEqual(manager.current_version, "v1")

    def test_los_manifiestos_del_repositorio_son_validos(self):
        manager = ModelVersionManager(state_file=self.state)
        default = manager.default()
        self.assertTrue(default.activable)
        self.assertTrue(all(path.is_file() for path in default.contracts.values()))
        self.assertEqual(default.load_combination().model_versions, default.model_versions)
        for deployment in manager.deployments():
            for model in ("bilstm", "mbert"):
                metrics = deployment.load_metrics(model)
                self.assertEqual(metrics.version, deployment.model_versions[model])


if __name__ == "__main__":
    unittest.main()
