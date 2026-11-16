"""Fase 6: estado de la cola, reintento, pausa, filtros del panel y `llm` en /salud. Sin Supabase ni LLM.

Uso:
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m unittest backend.tests.test_verification_admin
"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.admin_routes import router as admin_router
from backend.api.dependencies import identity_service, service_repository
from backend.api.public_routes import router as public_router
from backend.api.routes import router as analysis_router
from backend.core.config import LlmSettings, VerificationSettings
from backend.repositories.filters import AnalysisFilters, filter_params
from backend.repositories.supabase import SupabaseRepository, web_select
from backend.schemas.admin import AdminCase, AdminCaseDetail
from backend.schemas.public import PublicAnalysis
from backend.services.llm_status import LlmProbe
from backend.services.verification.worker import VerificationWorker, placeholder_process
from backend.tests.test_web_platform import ROW

NOW = datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc)
TRACKING = {
    "intentos": 3, "ultimo_error": "llm_no_disponible", "proximo_intento": NOW.isoformat(),
    "copiada_de": None, "iniciado_en": "2026-11-15T15:59:00+00:00", "terminado_en": None,
    "version_prompts": "extraccion-v1+consultas-v1",
}
VERIFICATION = {
    "estado": "fallida", "conclusion": None, "resumen": None, "afirmaciones": [], "fuentes": [],
    "modelo_llm": None, "actualizado_en": NOW.isoformat(), **TRACKING,
}


class FilterTests(unittest.TestCase):
    def test_el_panel_filtra_por_estado_de_la_cola(self):
        for state in ("pendiente", "en_proceso", "fallida"):
            params = filter_params(AnalysisFilters(verificacion=state))
            self.assertIn(("verificaciones_web.estado", f"eq.{state}"), params)
            self.assertIn("verificaciones_web!inner(", web_select(AnalysisFilters(verificacion=state), admin=True))

    def test_las_conclusiones_y_sin_verificar_siguen_igual(self):
        self.assertIn(("verificaciones_web.conclusion", "eq.contradicha"), filter_params(AnalysisFilters(verificacion="contradicha")))
        self.assertIn(("verificaciones_web", "is.null"), filter_params(AnalysisFilters(verificacion="sin_verificar")))
        self.assertNotIn("!inner", web_select(AnalysisFilters(verificacion="sin_verificar")))

    def test_solo_el_panel_pide_intentos_y_causas(self):
        self.assertNotIn("ultimo_error", web_select())
        self.assertIn("ultimo_error", web_select(admin=True))
        self.assertIn("intentos", web_select(admin=True))


class RecordTests(unittest.TestCase):
    row = {**ROW, "verificaciones_web": VERIFICATION}

    def test_la_web_publica_no_recibe_intentos_ni_causas(self):
        record = PublicAnalysis(**SupabaseRepository._web_fields(dict(self.row), detail=False))
        self.assertEqual(record.verificacion_web.estado, "fallida")
        dumped = record.model_dump_json()
        for name in ("ultimo_error", "intentos", "proximo_intento", "version_prompts", "llm_no_disponible"):
            self.assertNotIn(name, dumped)

    def test_el_panel_recibe_el_seguimiento(self):
        row = dict(self.row)
        case = AdminCase(**SupabaseRepository._web_fields(row, detail=False), **SupabaseRepository._admin_fields(row))
        self.assertEqual(case.seguimiento_verificacion.intentos, 3)
        self.assertEqual(case.seguimiento_verificacion.ultimo_error, "llm_no_disponible")
        self.assertIsNone(case.seguimiento_verificacion.terminado_en)

    def test_sin_verificacion_no_hay_seguimiento(self):
        row = {**ROW, "verificaciones_web": None}
        self.assertIsNone(SupabaseRepository._admin_fields(row)["seguimiento_verificacion"])
        # Una fila sin columnas de seguimiento (consulta pública) tampoco rompe el contrato del panel.
        bare = {"estado": "completada", "conclusion": "respaldada"}
        fields = SupabaseRepository._admin_fields({**ROW, "verificaciones_web": bare})
        self.assertEqual(fields["seguimiento_verificacion"].intentos, 0)


class RepositoryTests(unittest.TestCase):
    """Peticiones a PostgREST simuladas: se comprueba qué se pide y cómo se interpreta."""

    def repository(self, responder):
        repo = SupabaseRepository(SimpleNamespace(url="https://x.test", publishable_key="p", secret_key="s"))
        repo.requests = []

        def request(method, path, **kwargs):
            repo.requests.append((method, path, kwargs))
            return responder(method, path, kwargs)

        def page(path, params):
            repo.requests.append(("PAGE", path, {"params": params}))
            state = dict(params)["estado"].removeprefix("eq.")
            return [], {"pendiente": 2, "en_proceso": 1, "fallida": 4, "completada": 9}[state]

        repo._request = request
        repo._request_page = page
        return repo

    def test_cuenta_por_estado_y_promedia_la_duracion(self):
        rows = [
            {"iniciado_en": "2026-11-15T10:00:00+00:00", "terminado_en": "2026-11-15T10:00:30+00:00"},
            {"iniciado_en": "2026-11-15T11:00:00+00:00", "terminado_en": "2026-11-15T11:00:40+00:00"},
            {"iniciado_en": "2026-11-15T12:00:00+00:00", "terminado_en": "2026-11-15T11:59:00+00:00"},  # negativa: se ignora
        ]
        repo = self.repository(lambda method, path, kwargs: rows)
        stats = repo.verification_stats()
        self.assertEqual({k: stats[k] for k in ("pendiente", "en_proceso", "fallida", "completada")},
                         {"pendiente": 2, "en_proceso": 1, "fallida": 4, "completada": 9})
        self.assertEqual(stats["duracion_media_segundos"], 35.0)
        # Las cinco consultas corren a la vez (hilos): la de las duraciones es la única GET, pero no necesariamente la última.
        (duraciones,) = [request for request in repo.requests if request[0] == "GET"]
        params = dict(duraciones[2]["params"])
        self.assertEqual(params["copiada_de"], "is.null")  # las copias no cuentan
        self.assertEqual(params["estado"], "eq.completada")

    def test_sin_casos_completados_no_hay_duracion(self):
        self.assertIsNone(self.repository(lambda *args: []).verification_stats()["duracion_media_segundos"])

    def test_reintentar_una_fallida_la_devuelve_a_la_cola_desde_cero(self):
        def responder(method, path, kwargs):
            if method == "GET":
                return [{"estado": "fallida"}]
            return [{"analisis_id": "x"}]

        repo = self.repository(responder)
        self.assertEqual(repo.retry_verification(uuid4()), "reintentada")
        method, path, kwargs = repo.requests[-1]
        self.assertEqual((method, path), ("PATCH", "verificaciones_web"))
        self.assertEqual(kwargs["params"]["estado"], "eq.fallida")  # solo si sigue fallida
        body = kwargs["body"]
        self.assertEqual((body["estado"], body["intentos"], body["ultimo_error"]), ("pendiente", 0, None))
        self.assertIn("proximo_intento", body)

    def test_reintentar_una_pendiente_solo_adelanta_la_espera(self):
        repo = self.repository(lambda method, path, kwargs: [{"estado": "pendiente"}] if method == "GET" else [{"analisis_id": "x"}])
        self.assertEqual(repo.retry_verification(uuid4()), "reintentada")
        body = repo.requests[-1][2]["body"]
        self.assertEqual(set(body), {"proximo_intento", "actualizado_en"})  # no reinicia los intentos

    def test_no_se_toca_lo_que_esta_en_proceso_ni_lo_completado(self):
        for state in ("en_proceso", "completada"):
            repo = self.repository(lambda method, path, kwargs, state=state: [{"estado": state}])
            self.assertEqual(repo.retry_verification(uuid4()), state)
            self.assertTrue(all(request[0] != "PATCH" for request in repo.requests))

    def test_sin_fila_no_hay_nada_que_reintentar(self):
        repo = self.repository(lambda *args: [])
        self.assertEqual(repo.retry_verification(uuid4()), "sin_verificacion")

    def test_si_el_trabajador_la_reservo_justo_antes_no_se_pisa(self):
        repo = self.repository(lambda method, path, kwargs: [{"estado": "fallida"}] if method == "GET" else [])
        self.assertEqual(repo.retry_verification(uuid4()), "en_proceso")


class FakeAdminRepository:
    def __init__(self):
        self.outcome = "reintentada"
        self.stats = {"pendiente": 3, "en_proceso": 1, "fallida": 2, "completada": 10, "duracion_media_segundos": 33.5}
        self.retried = []

    def verification_stats(self):
        return self.stats

    def retry_verification(self, analysis_id):
        self.retried.append(analysis_id)
        return self.outcome

    def get_admin_case(self, analysis_id):
        row = {**ROW, "id": str(analysis_id), "revisiones": None, "verificaciones_web": {**VERIFICATION, "estado": "pendiente"}}
        return AdminCaseDetail(**SupabaseRepository._web_fields(row, detail=True), **SupabaseRepository._admin_fields(row))

    def list_admin_cases(self, filters, limit, offset):
        self.filters = filters
        from backend.schemas.admin import AdminCasePage
        return AdminCasePage(elementos=[], total=0)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeAdminRepository()
        self.app = FastAPI()
        self.app.include_router(public_router)
        self.app.include_router(admin_router)
        self.app.dependency_overrides[service_repository] = lambda: self.repository
        self.app.dependency_overrides[identity_service] = lambda: SimpleNamespace(
            verify_user=lambda token: SimpleNamespace(id=str(uuid4()), email="a@x.test", app_metadata={"role": "admin"}))
        self.app.state.verification_worker = None
        self.app.state.llm_probe = LlmProbe(None)
        self.client = TestClient(self.app)
        self.auth = {"Authorization": "Bearer t"}

    def worker(self):
        return VerificationWorker(SimpleNamespace(), VerificationSettings(True, 3, None), process=placeholder_process)

    def test_exige_sesion_de_administrador(self):
        for method, path in (("get", "/admin/verificacion"), ("post", "/admin/verificacion/pausar"),
                             ("post", "/admin/verificacion/reanudar"),
                             ("post", f"/admin/casos/{uuid4()}/verificacion/reintentar")):
            self.assertEqual(getattr(self.client, method)(path).status_code, 401, path)

    def test_estado_de_la_cola_con_el_trabajador_apagado(self):
        data = self.client.get("/admin/verificacion", headers=self.auth).json()
        self.assertEqual((data["pendientes"], data["en_proceso"], data["fallidas"], data["completadas"]), (3, 1, 2, 10))
        self.assertEqual(data["duracion_media_segundos"], 33.5)
        self.assertEqual((data["habilitada"], data["en_pausa"]), (False, False))
        self.assertEqual(data["llm"], {"configurado": False, "disponible": False})

    def test_pausar_y_reanudar_el_trabajador(self):
        worker = self.worker()
        self.app.state.verification_worker = worker
        paused = self.client.post("/admin/verificacion/pausar", headers=self.auth).json()
        self.assertEqual((paused["habilitada"], paused["en_pausa"]), (True, True))
        self.assertTrue(worker.paused)
        resumed = self.client.post("/admin/verificacion/reanudar", headers=self.auth).json()
        self.assertEqual(resumed["en_pausa"], False)
        self.assertFalse(worker.paused)
        self.assertEqual(self.client.get("/admin/verificacion", headers=self.auth).json()["habilitada"], True)

    def test_sin_trabajador_pausar_dice_por_que_no(self):
        for action in ("pausar", "reanudar"):
            response = self.client.post(f"/admin/verificacion/{action}", headers=self.auth)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"]["codigo"], "verificacion_apagada")

    def test_reintentar_devuelve_el_caso_actualizado(self):
        case = uuid4()
        response = self.client.post(f"/admin/casos/{case}/verificacion/reintentar", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verificacion_web"]["estado"], "pendiente")
        self.assertEqual(self.repository.retried, [case])

    def test_reintentar_lo_que_no_se_puede(self):
        self.repository.outcome = "sin_verificacion"
        missing = self.client.post(f"/admin/casos/{uuid4()}/verificacion/reintentar", headers=self.auth)
        self.assertEqual((missing.status_code, missing.json()["detail"]["codigo"]), (404, "sin_verificacion"))
        for state in ("completada", "en_proceso"):
            self.repository.outcome = state
            response = self.client.post(f"/admin/casos/{uuid4()}/verificacion/reintentar", headers=self.auth)
            self.assertEqual((response.status_code, response.json()["detail"]["codigo"]), (409, "no_se_puede_reintentar"))
            self.assertIn(state, response.json()["detail"]["mensaje"])

    def test_el_panel_filtra_por_verificacion_y_la_web_publica_no_ve_los_estados(self):
        for value in ("fallida", "pendiente", "en_proceso", "sin_verificar", "contradicha"):
            self.assertEqual(self.client.get(f"/admin/casos?verificacion={value}", headers=self.auth).status_code, 200)
            self.assertEqual(self.repository.filters.verificacion, value)
        self.assertEqual(self.client.get("/admin/casos?verificacion=inventada", headers=self.auth).status_code, 422)
        self.assertEqual(self.client.get("/publico/analisis?verificacion=fallida").status_code, 422)


class LlmProbeTests(unittest.TestCase):
    def probe(self, handler, **kwargs):
        settings = LlmSettings("http://llm.test/v1", "qwen", "clave-de-prueba", 5.0)
        return LlmProbe(settings, transport=httpx.MockTransport(handler), **kwargs)

    def test_sin_llm_configurado(self):
        status = LlmProbe(None).status()
        self.assertEqual((status.configurado, status.disponible), (False, False))

    def test_responde_y_manda_la_clave(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"data": []})

        status = self.probe(handler).status()
        self.assertEqual((status.configurado, status.disponible), (True, True))
        self.assertEqual(str(seen[0].url), "http://llm.test/v1/models")
        self.assertEqual(seen[0].headers["authorization"], "Bearer clave-de-prueba")

    def test_caido_o_con_error_no_esta_disponible_y_no_lanza(self):
        for handler in (lambda r: httpx.Response(503), lambda r: httpx.Response(401),
                        lambda r: (_ for _ in ()).throw(httpx.ConnectError("no conecta")),
                        lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("lento"))):
            status = self.probe(handler).status()
            self.assertEqual((status.configurado, status.disponible), (True, False))

    def test_recuerda_el_resultado_unos_segundos(self):
        calls = []
        now = [0.0]

        def handler(request):
            calls.append(1)
            return httpx.Response(200 if len(calls) == 1 else 503)

        probe = self.probe(handler, ttl=15, clock=lambda: now[0])
        self.assertTrue(probe.status().disponible)
        now[0] = 14
        self.assertTrue(probe.status().disponible)
        self.assertEqual(len(calls), 1)  # no volvió a preguntar
        now[0] = 16
        self.assertFalse(probe.status().disponible)
        self.assertEqual(len(calls), 2)


class HealthTests(unittest.TestCase):
    def client(self, probe):
        app = FastAPI()
        app.include_router(analysis_router)
        app.state.analysis_service = SimpleNamespace(mbert_predictor=object())
        app.state.identity_service = SimpleNamespace(settings=SimpleNamespace(secret_key="s"))
        app.state.blockchain_client = SimpleNamespace(check_ready=lambda: None)
        app.state.llm_probe = probe
        return TestClient(app)

    def test_llm_en_salud_sin_cambiar_el_estado_general(self):
        up = self.client(LlmProbe(LlmSettings("http://llm.test/v1", "qwen", None, 5.0), transport=httpx.MockTransport(lambda r: httpx.Response(200))))
        down = self.client(LlmProbe(LlmSettings("http://llm.test/v1", "qwen", None, 5.0), transport=httpx.MockTransport(lambda r: httpx.Response(503))))
        none = self.client(LlmProbe(None))
        for client, expected in ((up, (True, True)), (down, (True, False)), (none, (False, False))):
            data = client.get("/salud").json()
            self.assertEqual((data["llm"]["configurado"], data["llm"]["disponible"]), expected)
            self.assertEqual(data["estado"], "ok")  # un LLM caído no degrada el análisis rápido
            self.assertEqual(data["modelos"], {"bilstm": True, "mbert": True})

    def test_sin_sonda_el_campo_existe(self):
        app = FastAPI()
        app.include_router(analysis_router)
        data = TestClient(app).get("/salud").json()
        self.assertEqual(data["llm"], {"configurado": False, "disponible": False})
        self.assertEqual(data["estado"], "degradado")


if __name__ == "__main__":
    unittest.main()
