"""Cola de verificación (Fase 2): configuración, trabajador, encolado y migración 008.

Sin Supabase, llama-server ni pesos. Uso:
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m unittest backend.tests.test_verification_queue
"""

import asyncio
import os
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.dependencies import history_repository, identity_service
from backend.api.routes import router as analysis_router
from backend.core.config import VerificationSettings
from backend.schemas.analysis import AnalysisResponse, AppliedWeights, UnifiedResult
from backend.services.analysis import AnalysisOutcome
from backend.services.llm_client import LlmUnavailable
from backend.services.verification.worker import (
    PLACEHOLDER_MODEL,
    RESERVATION_SECONDS,
    RETRY_WAITS,
    VerificationWorker,
    enqueue_new_analysis,
    placeholder_process,
)

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = VerificationSettings(enabled=True, max_attempts=3, since=None)


class FakeRepository:
    """Registra las llamadas y devuelve lo que cada prueba configure."""

    def __init__(self, claimed=None, copied=False, saved=True):
        self.claimed = claimed
        self.copied = copied
        self.saved = saved
        self.calls: list[tuple] = []
        self.fail_with: Exception | None = None
        self.complete_error: Exception | None = None

    def enqueue_verification(self, analysis_id):
        self.calls.append(("enqueue", analysis_id))
        if self.fail_with:
            raise self.fail_with
        return True

    def enqueue_pending_verifications(self, since, limit=100):
        self.calls.append(("sweep", since))
        return 2

    def claim_verification(self, max_attempts, reservation_seconds):
        self.calls.append(("claim", max_attempts, reservation_seconds))
        return self.claimed

    def copy_verification(self, analysis_id):
        self.calls.append(("copy", analysis_id))
        return self.copied

    def complete_verification(self, analysis_id, **fields):
        self.calls.append(("complete", analysis_id, fields))
        if self.complete_error:
            raise self.complete_error
        return self.saved

    def fail_verification(self, analysis_id, error, *, max_attempts, waits):
        self.calls.append(("fail", analysis_id, error, max_attempts, waits))
        if self.fail_with:
            raise self.fail_with
        return "pendiente"

    def names(self):
        return [call[0] for call in self.calls]


class SettingsTests(unittest.TestCase):
    def env(self, **values):
        base = {"VERIFICATION_ENABLED": "", "VERIFICATION_DESDE": "", "VERIFICATION_MAX_ATTEMPTS": ""}
        return mock.patch.dict(os.environ, {**base, **values})

    def test_apagada_por_defecto(self):
        with self.env():
            result = VerificationSettings.from_environment()
        self.assertEqual((result.enabled, result.max_attempts, result.since), (False, 3, None))

    def test_valores_que_encienden(self):
        for value in ("true", "TRUE", "1", "yes", "sí"):
            with self.subTest(value=value), self.env(VERIFICATION_ENABLED=value):
                self.assertTrue(VerificationSettings.from_environment().enabled)
        for value in ("false", "0", "no", "quizá"):
            with self.subTest(value=value), self.env(VERIFICATION_ENABLED=value):
                self.assertFalse(VerificationSettings.from_environment().enabled)

    def test_fecha_de_corte_exige_zona_horaria(self):
        with self.env(VERIFICATION_DESDE="2026-11-15T09:00:00-05:00"):
            since = VerificationSettings.from_environment().since
        self.assertEqual(since, datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc))
        for value in ("2026-11-15T09:00:00", "ayer", "15/11/2026"):
            with self.subTest(value=value), self.env(VERIFICATION_DESDE=value):
                with self.assertRaises(ValueError):
                    VerificationSettings.from_environment()

    def test_intentos(self):
        with self.env(VERIFICATION_MAX_ATTEMPTS="5"):
            self.assertEqual(VerificationSettings.from_environment().max_attempts, 5)
        for value in ("0", "11", "tres"):
            with self.subTest(value=value), self.env(VERIFICATION_MAX_ATTEMPTS=value):
                with self.assertRaises(ValueError):
                    VerificationSettings.from_environment()


class WorkerTests(unittest.TestCase):
    def worker(self, repository, **kwargs):
        kwargs.setdefault("process", placeholder_process)
        return VerificationWorker(repository, SETTINGS, **kwargs)

    def test_sin_casos_no_hace_nada_mas(self):
        repo = FakeRepository(claimed=None)
        self.assertFalse(self.worker(repo).process_one())
        self.assertEqual(repo.names(), ["claim"])
        self.assertEqual(repo.calls[0][1:], (3, RESERVATION_SECONDS))

    def test_caso_normal_completa_con_el_resultado_de_prueba(self):
        analysis_id = uuid4()
        repo = FakeRepository(claimed=analysis_id)
        self.assertTrue(self.worker(repo).process_one())
        self.assertEqual(repo.names(), ["claim", "copy", "complete"])
        _, completed_id, fields = repo.calls[2]
        self.assertEqual(completed_id, analysis_id)
        self.assertEqual(fields["conclusion"], "evidencia_insuficiente")
        self.assertEqual(fields["model"], PLACEHOLDER_MODEL)
        self.assertIn("no es una verificación real", fields["summary"])
        self.assertEqual((fields["claims"], fields["sources"]), ([], []))

    def test_texto_ya_verificado_se_copia_y_no_se_procesa(self):
        calls = []
        repo = FakeRepository(claimed=uuid4(), copied=True)
        worker = self.worker(repo, process=lambda analysis_id: calls.append(analysis_id))
        self.assertTrue(worker.process_one())
        self.assertEqual(repo.names(), ["claim", "copy"])
        self.assertEqual(calls, [])

    def test_falla_inesperada_vuelve_a_la_cola_con_las_esperas(self):
        def boom(analysis_id):
            raise RuntimeError("algo salió mal")

        analysis_id = uuid4()
        repo = FakeRepository(claimed=analysis_id)
        with self.assertLogs("backend.services.verification.worker", level="WARNING"):
            self.assertTrue(self.worker(repo, process=boom).process_one())
        self.assertEqual(repo.names(), ["claim", "copy", "fail"])
        self.assertEqual(repo.calls[2][1:], (analysis_id, "error_interno", 3, RETRY_WAITS))

    def test_el_codigo_del_error_se_guarda(self):
        def llm_caido(analysis_id):
            raise LlmUnavailable("no responde")

        repo = FakeRepository(claimed=uuid4())
        with self.assertLogs("backend.services.verification.worker", level="WARNING"):
            self.worker(repo, process=llm_caido).process_one()
        self.assertEqual(repo.calls[2][2], "llm_no_disponible")

    def test_si_no_se_puede_registrar_la_falla_no_se_propaga(self):
        repo = FakeRepository(claimed=uuid4())
        repo.complete_error = RuntimeError("Supabase caído")
        repo.fail_with = RuntimeError("Supabase caído")
        with self.assertLogs("backend.services.verification.worker", level="WARNING"):
            self.assertTrue(self.worker(repo).process_one())  # la reserva vencerá sola

    def test_caso_borrado_mientras_se_procesaba(self):
        repo = FakeRepository(claimed=uuid4(), saved=False)
        with self.assertLogs("backend.services.verification.worker", level="WARNING"):
            self.assertTrue(self.worker(repo).process_one())
        self.assertEqual(repo.names(), ["claim", "copy", "complete"])

    def test_resultado_de_prueba_cumple_la_restriccion_de_la_tabla(self):
        outcome = placeholder_process(uuid4())
        self.assertIn(outcome.conclusion,
                      ("respaldada", "contradicha", "fuera_de_contexto", "evidencia_insuficiente"))
        self.assertLessEqual(len(outcome.summary), 4000)

    def test_barrido_solo_con_fecha_de_corte(self):
        repo = FakeRepository()
        self.assertEqual(self.worker(repo).sweep(), 0)
        self.assertEqual(repo.calls, [])
        since = datetime(2026, 11, 15, tzinfo=timezone.utc)
        repo = FakeRepository()
        worker = VerificationWorker(repo, VerificationSettings(True, 3, since), process=placeholder_process)
        self.assertEqual(worker.sweep(), 2)
        self.assertEqual(repo.calls, [("sweep", since)])

    def test_el_bucle_barre_y_reclama_hasta_cancelarse(self):
        repo = FakeRepository(claimed=None)
        since = datetime.now(timezone.utc) - timedelta(days=1)
        worker = VerificationWorker(repo, VerificationSettings(True, 3, since), process=placeholder_process)

        async def cancel(_seconds):
            raise asyncio.CancelledError

        async def run():
            with mock.patch("backend.services.verification.worker.asyncio.sleep", cancel):
                await worker.run()

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(run())
        self.assertEqual(repo.names(), ["sweep", "claim"])


class EnqueueTests(unittest.TestCase):
    def test_apagada_no_encola(self):
        repo = FakeRepository()
        for settings in (None, VerificationSettings(False, 3, None)):
            self.assertFalse(enqueue_new_analysis(repo, settings, uuid4()))
        self.assertEqual(repo.calls, [])

    def test_encendida_encola(self):
        repo = FakeRepository()
        analysis_id = uuid4()
        self.assertTrue(enqueue_new_analysis(repo, SETTINGS, analysis_id))
        self.assertEqual(repo.calls, [("enqueue", analysis_id)])

    def test_si_falla_no_lanza(self):
        repo = FakeRepository()
        repo.fail_with = RuntimeError("Supabase caído")
        with self.assertLogs("backend.services.verification.worker", level="WARNING"):
            self.assertFalse(enqueue_new_analysis(repo, SETTINGS, uuid4()))


class AnalyzeRouteTests(unittest.TestCase):
    """POST /analisis responde igual con la cola apagada, encendida o rota."""

    def setUp(self):
        self.analysis_id = uuid4()
        self.repository = FakeRepository()
        self.repository.create_analysis = lambda **kwargs: self.analysis_id
        response = AnalysisResponse(
            resultados={},
            resultado_unificado=UnifiedResult(
                probabilidad_falsa=0.5, modelos_utilizados=["bilstm"],
                pesos_aplicados=AppliedWeights(bilstm=1, mbert=0),
            ),
            comparacion="no_disponible",
            nota="prueba",
        )
        outcome = AnalysisOutcome(response=response, text="texto de prueba", truncated=False)
        app = FastAPI()
        app.include_router(analysis_router)
        app.state.analysis_service = SimpleNamespace(analyze=lambda payload: outcome)
        app.dependency_overrides[history_repository] = lambda: self.repository
        app.dependency_overrides[identity_service] = lambda: SimpleNamespace(
            verify_user=lambda token: SimpleNamespace(id=str(uuid4())))
        self.app = app
        self.client = TestClient(app)

    def post(self):
        return self.client.post("/analisis", json={"texto": "texto de prueba"},
                                headers={"Authorization": "Bearer t"})

    def test_cola_apagada_no_encola(self):
        self.app.state.verification_settings = VerificationSettings(False, 3, None)
        self.assertEqual(self.post().status_code, 200)
        self.assertNotIn("enqueue", self.repository.names())

    def test_sin_configuracion_tampoco(self):
        self.assertEqual(self.post().status_code, 200)
        self.assertNotIn("enqueue", self.repository.names())

    def test_cola_encendida_encola_el_analisis(self):
        self.app.state.verification_settings = SETTINGS
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.analysis_id))
        self.assertEqual(self.repository.calls, [("enqueue", self.analysis_id)])

    def test_si_encolar_falla_el_analisis_responde_igual(self):
        self.app.state.verification_settings = SETTINGS
        self.repository.fail_with = RuntimeError("Supabase caído")
        with self.assertLogs("backend.services.verification.worker", level="WARNING"):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.analysis_id))


class MigrationTests(unittest.TestCase):
    """La reversión 008 deshace todo lo que crea la 008 y nada más."""

    def setUp(self):
        self.up = (ROOT / "backend/db/migrations/008_verificacion_web.sql").read_text(encoding="utf-8")
        self.down = (ROOT / "backend/db/rollback/008_revertir_verificacion_web.sql").read_text(encoding="utf-8")

    def test_cada_funcion_creada_se_borra(self):
        created = re.findall(r"create function public\.(\w+)\(", self.up)
        self.assertEqual(len(created), 6)
        for name in created:
            self.assertIn(f"drop function if exists public.{name}(", self.down, name)

    def test_cada_tabla_indice_y_columna_creada_se_borra(self):
        tables = re.findall(r"create table public\.(\w+)", self.up)
        for table in tables:
            self.assertIn(f"drop table if exists public.{table}", self.down)
        # Un índice de una tabla creada por la 008 cae con la tabla; los demás se borran aparte.
        for index, table in re.findall(r"create index (\w+)\s+on public\.(\w+)", self.up):
            if table not in tables:
                self.assertIn(f"drop index if exists public.{index}", self.down)
        added = re.findall(r"add column (\w+)", self.up)
        self.assertEqual(len(added), 7)
        for column in added:
            self.assertIn(f"drop column if exists {column}", self.down)

    def test_verificaciones_web_no_gana_otra_relacion_con_analisis(self):
        # Una segunda clave foránea hacia analisis hace ambigua la incrustación de PostgREST
        # (PGRST201) y rompe las consultas de la web pública y del panel.
        block = re.search(r"alter table public\.verificaciones_web\s+(.*?);", self.up, flags=re.S).group(1)
        self.assertNotIn("references", block)
        self.assertIn("add column copiada_de uuid", block)

    def test_las_funciones_solo_las_usa_el_backend(self):
        revoked = len(re.findall(r"revoke execute on function", self.up))
        granted = len(re.findall(r"grant execute on function", self.up))
        self.assertEqual((revoked, granted), (6, 6))
        self.assertIn("from anon, authenticated", self.up)  # la tabla nueva

    def test_la_reversion_no_toca_datos_de_otros_incrementos(self):
        for table in ("analisis", "resultados_modelo", "revisiones", "datasets_version", "dataset_items"):
            self.assertNotIn(f"drop table if exists public.{table}", self.down)
        self.assertNotIn("delete from public.", self.down)


if __name__ == "__main__":
    unittest.main()
