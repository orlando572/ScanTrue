"""Cliente del servidor LLM: esquema forzado, errores diferenciados y configuración.

No necesita llama-server, Supabase ni pesos: usa `httpx.MockTransport` y un servidor HTTP
local mínimo. Uso:
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m unittest backend.tests.test_llm_client
"""

import json
import os
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import httpx

from backend.core.config import LlmSettings
from backend.schemas.verification import MAX_CLAIMS, ClaimExtraction
from backend.services.llm_client import LlmClient, LlmInvalidResponse, LlmUnavailable

CLAVE = "clave-de-prueba-no-real"
TEXTO = "El alcalde dijo que invertirá 3 millones de soles en Ñuñoa."
MENSAJES = [
    {"role": "system", "content": "Extrae afirmaciones verificables."},
    {"role": "user", "content": TEXTO},
]
RESPUESTA_OK = {"afirmaciones": [
    {"id": 1, "texto": "El alcalde anunció una inversión de 3 millones de soles."},
]}


def settings(base_url="http://llm.test/v1", api_key=CLAVE, timeout=5.0) -> LlmSettings:
    return LlmSettings(base_url=base_url, model="qwen-prueba", api_key=api_key, timeout=timeout)


def completion(content, finish="stop") -> dict:
    return {"choices": [{"index": 0, "finish_reason": finish,
                         "message": {"role": "assistant", "content": content}}]}


def client_with(handler, **kwargs) -> tuple[LlmClient, list]:
    sleeps: list[float] = []
    client = LlmClient(
        settings(**{k: kwargs.pop(k) for k in ("base_url", "api_key", "timeout") if k in kwargs}),
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        **kwargs,
    )
    return client, sleeps


class RequestTests(unittest.TestCase):
    def test_envia_esquema_clave_y_cuerpo_utf8(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=completion(json.dumps(RESPUESTA_OK)))

        client, _ = client_with(handler)
        result = client.complete_json(MENSAJES, ClaimExtraction, max_tokens=300)
        self.assertEqual(result.afirmaciones[0].id, 1)

        request = seen[0]
        self.assertEqual(request.url.path, "/v1/chat/completions")
        self.assertEqual(request.headers["authorization"], f"Bearer {CLAVE}")
        self.assertIn("utf-8", request.headers["content-type"])
        raw = request.content.decode("utf-8")  # no debe fallar con tildes ni eñes
        self.assertIn("Ñuñoa", raw)
        body = json.loads(raw)
        self.assertEqual(body["model"], "qwen-prueba")
        self.assertEqual(body["max_tokens"], 300)
        self.assertIs(body["stream"], False)
        self.assertEqual(body["temperature"], 0.0)
        fmt = body["response_format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["json_schema"]["name"], "ClaimExtraction")
        self.assertEqual(fmt["json_schema"]["schema"]["properties"]["afirmaciones"]["maxItems"], MAX_CLAIMS)

    def test_sin_clave_no_envia_authorization(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=completion(json.dumps({"afirmaciones": []})))

        client, _ = client_with(handler, api_key=None)
        self.assertEqual(client.complete_json(MENSAJES, ClaimExtraction).afirmaciones, [])
        self.assertNotIn("authorization", seen[0].headers)


class InvalidResponseTests(unittest.TestCase):
    def assert_invalid(self, response: httpx.Response, secreto: str | None = None):
        client, _ = client_with(lambda request: response)
        with self.assertRaises(LlmInvalidResponse) as caught:
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(caught.exception.code, "salida_invalida")
        if secreto:  # el contenido recibido nunca va en el mensaje
            self.assertNotIn(secreto, str(caught.exception))

    def test_contenido_que_no_es_json(self):
        self.assert_invalid(httpx.Response(200, json=completion("esto no es json SECRETO")), "SECRETO")

    def test_json_que_no_cumple_el_esquema(self):
        demasiadas = {"afirmaciones": [
            {"id": 1, "texto": "Una afirmación suficientemente larga."}] * (MAX_CLAIMS + 1)}
        sobrante = {"afirmaciones": [], "extra": "SECRETO"}
        corta = {"afirmaciones": [{"id": 1, "texto": "corta"}]}
        for content in (demasiadas, sobrante, corta, {"otra_cosa": []}, []):
            with self.subTest(content=str(content)[:40]):
                self.assert_invalid(httpx.Response(200, json=completion(json.dumps(content))), "SECRETO")

    def test_respuesta_vacia_o_cortada(self):
        self.assert_invalid(httpx.Response(200, json=completion("   ")))
        self.assert_invalid(httpx.Response(200, json=completion(None)))
        cortada = httpx.Response(200, json=completion('{"afirmaciones": [', finish="length"))
        self.assert_invalid(cortada)

    def test_cuerpo_sin_el_formato_esperado(self):
        self.assert_invalid(httpx.Response(200, json={"choices": []}))
        self.assert_invalid(httpx.Response(200, json={"error": "algo"}))
        self.assert_invalid(httpx.Response(200, text="<html>no es json</html>"))


class UnavailableTests(unittest.TestCase):
    def test_clave_rechazada_no_se_reintenta(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})

        client, sleeps = client_with(handler)
        with self.assertRaises(LlmUnavailable) as caught:
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(caught.exception.code, "no_autorizado")
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])
        self.assertNotIn(CLAVE, str(caught.exception))

    def test_servidor_cargando_se_reintenta_y_se_recupera(self):
        answers = [httpx.Response(503, json={"error": {"message": "Loading model"}}),
                   httpx.Response(200, json=completion(json.dumps(RESPUESTA_OK)))]
        client, sleeps = client_with(lambda request: answers.pop(0))
        self.assertEqual(len(client.complete_json(MENSAJES, ClaimExtraction).afirmaciones), 1)
        self.assertEqual(len(sleeps), 1)

    def test_si_sigue_caido_falla_tras_los_reintentos(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(503)

        client, sleeps = client_with(handler, retries=2)
        with self.assertRaises(LlmUnavailable) as caught:
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(caught.exception.code, "llm_no_disponible")
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps), 2)

    def test_solicitud_rechazada_no_se_reintenta(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(400, json={"error": {"message": "mala solicitud"}})

        client, _ = client_with(handler)
        with self.assertRaises(LlmUnavailable):
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(len(calls), 1)

    def test_error_de_red_es_llm_caido(self):
        def handler(request):
            raise httpx.ConnectError("sin conexión")

        client, sleeps = client_with(handler, retries=1)
        with self.assertRaises(LlmUnavailable) as caught:
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(caught.exception.code, "llm_no_disponible")
        self.assertEqual(len(sleeps), 1)


class ServidorSimulado(BaseHTTPRequestHandler):
    """Servidor HTTP real y mínimo: comprueba el recorrido por la red, no solo el transporte falso."""

    recibido: list = []
    demora = 0.0
    respuesta = completion(json.dumps(RESPUESTA_OK))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        type(self).recibido.append((self.path, dict(self.headers), self.rfile.read(length)))
        if self.headers.get("Authorization") != f"Bearer {CLAVE}":
            self._send(401, {"error": {"message": "Invalid API Key"}})
            return
        time.sleep(type(self).demora)
        self._send(200, type(self).respuesta)

    def _send(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # el cliente ya se había ido por el tiempo máximo

    def log_message(self, *args):
        pass


class NetworkTests(unittest.TestCase):
    def setUp(self):
        ServidorSimulado.recibido = []
        ServidorSimulado.demora = 0.0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ServidorSimulado)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/v1"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_recorrido_completo_con_clave_y_tildes(self):
        client = LlmClient(settings(base_url=self.base))
        result = client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(result.afirmaciones[0].texto, RESPUESTA_OK["afirmaciones"][0]["texto"])
        path, _, body = ServidorSimulado.recibido[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertIn("Ñuñoa", body.decode("utf-8"))

    def test_clave_equivocada_es_no_autorizado(self):
        client = LlmClient(settings(base_url=self.base, api_key="otra"))
        with self.assertRaises(LlmUnavailable) as caught:
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(caught.exception.code, "no_autorizado")

    def test_tiempo_agotado_no_se_reintenta(self):
        ServidorSimulado.demora = 1.0
        client = LlmClient(settings(base_url=self.base, timeout=0.2), sleep=lambda s: None)
        with self.assertRaises(LlmUnavailable) as caught:
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(caught.exception.code, "tiempo_agotado")
        self.assertEqual(len(ServidorSimulado.recibido), 1)

    def test_servidor_apagado(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]  # puerto libre: nadie escucha
        client = LlmClient(settings(base_url=f"http://127.0.0.1:{port}/v1"), retries=1,
                           sleep=lambda s: None)
        with self.assertRaises(LlmUnavailable) as caught:
            client.complete_json(MENSAJES, ClaimExtraction)
        self.assertEqual(caught.exception.code, "llm_no_disponible")


class SettingsTests(unittest.TestCase):
    def env(self, **values):
        base = {"LLM_BASE_URL": "", "LLM_MODEL": "", "LLM_TIMEOUT": "", "LLM_API_KEY": ""}
        return mock.patch.dict(os.environ, {**base, **values})

    def test_sin_url_no_hay_llm(self):
        with self.env():
            self.assertIsNone(LlmSettings.from_environment())

    def test_lee_url_modelo_clave_y_tiempo(self):
        with self.env(LLM_BASE_URL=" http://192.168.1.5:8080/v1/ ", LLM_MODEL="qwen3",
                      LLM_API_KEY=CLAVE, LLM_TIMEOUT="45"):
            result = LlmSettings.from_environment()
        self.assertEqual(result, LlmSettings("http://192.168.1.5:8080/v1", "qwen3", CLAVE, 45.0))

    def test_valores_por_defecto(self):
        with self.env(LLM_BASE_URL="http://127.0.0.1:8080/v1"):
            result = LlmSettings.from_environment()
        self.assertIsNone(result.api_key)
        self.assertEqual(result.timeout, 120.0)
        self.assertTrue(result.model)

    def test_tiempo_invalido(self):
        for value in ("mucho", "0", "-3", "99999"):
            with self.subTest(value=value), self.env(LLM_BASE_URL="http://x/v1", LLM_TIMEOUT=value):
                with self.assertRaises(ValueError):
                    LlmSettings.from_environment()


if __name__ == "__main__":
    unittest.main()
