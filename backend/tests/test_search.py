"""Proveedores de búsqueda web (Brave y Tavily) y la fuente previa (Google Fact Check Tools) con transporte simulado: sin internet ni claves.

Uso:
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m unittest backend.tests.test_search
"""

import json
import unittest

import httpx

from backend.core.config import FactCheckSettings, SearchSettings
from backend.services.verification.search import (
    BraveSearch,
    FactCheckSearch,
    SearchError,
    TavilySearch,
    build_factcheck_provider,
    build_search_provider,
    clean_query,
    domain_of,
    is_excluded,
)

KEY = "clave-secreta-de-prueba-123"
BRAVE_BODY = {"web": {"results": [
    {"title": " Abren el puente ", "url": "https://www.diario.test/nota/1", "description": "El puente  abrió."},
    {"title": "Peligro", "url": "javascript:alert(1)", "description": "no es http"},
    {"title": "Otro", "url": "http://otro.test/b?x=1", "description": "Segundo resultado"},
    "no es un objeto",
]}}
TAVILY_BODY = {"results": [
    {"title": "Abren el puente", "url": "https://www.diario.test/nota/1", "content": "El puente abrió.", "score": 0.9},
    {"title": "Sin url", "content": "nada"},
    {"title": "Otro", "url": "http://otro.test/b", "content": "Segundo resultado", "score": 0.5},
]}


def provider(cls, *responses, retries=1):
    requests: list[httpx.Request] = []
    queue = list(responses)

    def handler(request):
        requests.append(request)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    return cls(KEY, 5.0, retries=retries, transport=httpx.MockTransport(handler), sleep=lambda _s: None), requests


def json_response(body, status=200):
    return httpx.Response(status, json=body)


class HelperTests(unittest.TestCase):
    def test_dominio(self):
        self.assertEqual(domain_of("https://WWW.Diario.test/a?b=1"), "diario.test")
        self.assertEqual(domain_of("http://sub.diario.test./a"), "sub.diario.test")
        self.assertEqual(domain_of("no es url"), "")

    def test_exclusion_incluye_subdominios_pero_no_dominios_parecidos(self):
        excluded = ["maldita.es", "WWW.newtral.es"]
        self.assertTrue(is_excluded("maldita.es", excluded))
        self.assertTrue(is_excluded("www2.maldita.es", excluded))
        self.assertTrue(is_excluded("newtral.es", excluded))
        self.assertFalse(is_excluded("nomaldita.es", excluded))
        self.assertFalse(is_excluded("maldita.es.falso.com", excluded))
        self.assertFalse(is_excluded("diario.test", []))

    def test_la_consulta_no_lleva_direcciones_ni_correos_ni_controles(self):
        text = clean_query("el alcalde http://secreto.test/x?u=1 escribió a ana@correo.test \x00 sobre www.otro.test el puente")
        self.assertEqual(text, "el alcalde escribió a sobre el puente")
        self.assertEqual(len(clean_query("palabra " * 200)), 300)


class BraveTests(unittest.TestCase):
    def test_pide_con_la_clave_en_la_cabecera_y_lee_los_resultados(self):
        brave, requests = provider(BraveSearch, json_response(BRAVE_BODY))
        results = brave.search("puente nuevo ciudad", max_results=5)
        request = requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.headers["x-subscription-token"], KEY)
        self.assertEqual(request.url.params["q"], "puente nuevo ciudad")
        self.assertEqual(request.url.params["search_lang"], "es")
        self.assertEqual(request.url.params["count"], "5")
        self.assertNotIn(KEY, str(request.url))
        self.assertEqual([r.url for r in results], ["https://www.diario.test/nota/1", "http://otro.test/b?x=1"])
        self.assertEqual((results[0].titulo, results[0].dominio, results[0].fragmento, results[0].posicion),
                         ("Abren el puente", "diario.test", "El puente abrió.", 1))

    def test_excluye_dominios_con_site(self):
        brave, requests = provider(BraveSearch, json_response(BRAVE_BODY))
        brave.search("puente", exclude_domains=["maldita.es", " newtral.es "])
        self.assertEqual(requests[0].url.params["q"], "puente -site:maldita.es -site:newtral.es")

    def test_limita_la_cantidad(self):
        brave, requests = provider(BraveSearch, json_response(BRAVE_BODY))
        self.assertEqual(len(brave.search("puente", max_results=1)), 1)
        brave.search("puente", max_results=99)
        self.assertEqual(requests[1].url.params["count"], "20")

    def test_respuesta_sin_resultados(self):
        brave, _ = provider(BraveSearch, json_response({"query": {}}))
        self.assertEqual(brave.search("puente"), [])

    def test_consulta_vacia_no_llama(self):
        brave, requests = provider(BraveSearch, json_response(BRAVE_BODY))
        self.assertEqual(brave.search("  http://solo.una.url  "), [])
        self.assertEqual(requests, [])


class TavilyTests(unittest.TestCase):
    def test_pide_con_la_clave_en_la_cabecera_y_lee_los_resultados(self):
        tavily, requests = provider(TavilySearch, json_response(TAVILY_BODY))
        results = tavily.search("puente nuevo ciudad", max_results=3, exclude_domains=["maldita.es"])
        request = requests[0]
        body = json.loads(request.content)
        self.assertEqual((request.method, str(request.url)), ("POST", "https://api.tavily.com/search"))
        self.assertEqual(request.headers["authorization"], f"Bearer {KEY}")
        self.assertNotIn(KEY, request.content.decode())
        self.assertEqual(body["query"], "puente nuevo ciudad")
        self.assertEqual((body["search_depth"], body["max_results"], body["exclude_domains"]), ("basic", 3, ["maldita.es"]))
        self.assertFalse(body["include_answer"])
        self.assertFalse(body["include_raw_content"])
        self.assertEqual([r.url for r in results], ["https://www.diario.test/nota/1", "http://otro.test/b"])
        self.assertEqual(results[0].fragmento, "El puente abrió.")

    def test_sin_exclusiones_no_manda_la_lista(self):
        tavily, requests = provider(TavilySearch, json_response(TAVILY_BODY))
        tavily.search("puente")
        self.assertNotIn("exclude_domains", json.loads(requests[0].content))


FACTCHECK_BODY = {"claims": [
    {"text": "El puente abrió en 2020", "claimant": "Alguien", "claimDate": "2026-01-01T00:00:00Z", "claimReview": [
        {"publisher": {"name": "Medio", "site": "verifica.test"}, "url": "https://www.verifica.test/puente", "title": " El  puente ",
         "reviewDate": "2026-02-01T00:00:00Z", "textualRating": "Falso", "languageCode": "es"},
        {"publisher": {"name": "Otro", "site": "maldita.es"}, "url": "https://maldita.es/puente", "title": "Puente", "textualRating": "Engañoso"},
    ]},
    {"text": "Otra afirmación", "claimReview": [
        {"url": "https://www.verifica.test/puente", "title": "repetida"},
        {"url": "ftp://x.test/a", "title": "no es http"},
        {"url": "https://tercero.test/p"},
        "no es un objeto",
    ]},
    "no es un objeto",
]}


class FactCheckTests(unittest.TestCase):
    def test_pide_en_espanol_con_la_clave_en_la_cabecera_y_lee_las_verificaciones(self):
        search, requests = provider(FactCheckSearch, json_response(FACTCHECK_BODY))
        results = search.search("puente nuevo ciudad", max_results=3)
        request = requests[0]
        self.assertEqual((request.method, request.url.path), ("GET", "/v1alpha1/claims:search"))
        self.assertEqual(request.url.host, "factchecktools.googleapis.com")
        self.assertEqual(dict(request.url.params), {"query": "puente nuevo ciudad", "languageCode": "es", "pageSize": "3"})
        self.assertEqual(request.headers["x-goog-api-key"], KEY)
        self.assertNotIn(KEY, str(request.url))  # la clave nunca va en la dirección
        self.assertEqual([r.url for r in results], ["https://www.verifica.test/puente", "https://maldita.es/puente", "https://tercero.test/p"])
        self.assertEqual((results[0].titulo, results[0].fragmento, results[0].dominio), ("El puente", "El puente abrió en 2020", "verifica.test"))
        self.assertEqual(results[2].titulo, "Otra afirmación")  # sin título de la revisión, el de la afirmación revisada

    def test_la_calificacion_de_la_api_no_pasa_a_los_resultados(self):
        search, _ = provider(FactCheckSearch, json_response(FACTCHECK_BODY))
        for result in search.search("puente"):
            self.assertNotIn("Falso", f"{result.titulo} {result.fragmento}")
            self.assertNotIn("Engañoso", f"{result.titulo} {result.fragmento}")

    def test_excluye_dominios_no_repite_y_respeta_el_tope(self):
        search, _ = provider(FactCheckSearch, json_response(FACTCHECK_BODY))
        urls = [r.url for r in search.search("puente", exclude_domains=["maldita.es"])]
        self.assertEqual(urls, ["https://www.verifica.test/puente", "https://tercero.test/p"])
        self.assertEqual(len(search.search("puente", max_results=1)), 1)

    def test_sin_verificaciones_o_sin_consulta_no_hay_resultados(self):
        search, _ = provider(FactCheckSearch, json_response({}))
        self.assertEqual(search.search("puente"), [])
        search, requests = provider(FactCheckSearch, json_response(FACTCHECK_BODY))
        self.assertEqual(search.search("  http://solo.una.url  "), [])
        self.assertEqual(requests, [])

    def test_los_errores_se_reportan_sin_la_clave(self):
        for status, code in ((403, "busqueda_no_autorizada"), (429, "busqueda_cupo_agotado"), (400, "busqueda_fallida")):
            search, requests = provider(FactCheckSearch, httpx.Response(status))
            with self.assertRaises(SearchError) as caught:
                search.search("puente")
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn(KEY, str(caught.exception))
            self.assertEqual(len(requests), 1)

    def test_configuracion_desde_el_entorno(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"FACTCHECK_API_KEY": KEY, "FACTCHECK_TIMEOUT": ""}), mock.patch("backend.core.config.load_dotenv"):
            settings = FactCheckSettings.from_environment()
        self.assertEqual((settings.api_key, settings.timeout), (KEY, 10.0))
        self.assertIsInstance(build_factcheck_provider(settings), FactCheckSearch)
        with mock.patch.dict(os.environ, {"FACTCHECK_API_KEY": ""}), mock.patch("backend.core.config.load_dotenv"):
            self.assertIsNone(FactCheckSettings.from_environment())
        for bad in ("0", "x", "500"):
            with mock.patch.dict(os.environ, {"FACTCHECK_API_KEY": KEY, "FACTCHECK_TIMEOUT": bad}), mock.patch("backend.core.config.load_dotenv"):
                with self.assertRaises(ValueError):
                    FactCheckSettings.from_environment()


class ErrorTests(unittest.TestCase):
    def test_clave_rechazada(self):
        for cls in (BraveSearch, TavilySearch):
            for status in (401, 403):
                search, requests = provider(cls, httpx.Response(status))
                with self.assertRaises(SearchError) as caught:
                    search.search("puente")
                self.assertEqual(caught.exception.code, "busqueda_no_autorizada")
                self.assertEqual(len(requests), 1)
                self.assertNotIn(KEY, str(caught.exception))

    def test_cupo_agotado_no_se_reintenta(self):
        for cls, status in ((BraveSearch, 429), (BraveSearch, 402), (TavilySearch, 429), (TavilySearch, 432), (TavilySearch, 433)):
            search, requests = provider(cls, httpx.Response(status))
            with self.assertRaises(SearchError) as caught:
                search.search("puente")
            self.assertEqual(caught.exception.code, "busqueda_cupo_agotado", (cls.__name__, status))
            self.assertEqual(len(requests), 1)

    def test_falla_pasajera_se_reintenta_una_vez(self):
        search, requests = provider(TavilySearch, httpx.Response(503), json_response(TAVILY_BODY))
        self.assertEqual(len(search.search("puente")), 2)
        self.assertEqual(len(requests), 2)

    def test_falla_persistente(self):
        search, requests = provider(BraveSearch, httpx.Response(500))
        with self.assertRaises(SearchError) as caught:
            search.search("puente")
        self.assertEqual(caught.exception.code, "busqueda_fallida")
        self.assertEqual(len(requests), 2)

    def test_error_que_no_es_pasajero_no_se_reintenta(self):
        search, requests = provider(BraveSearch, httpx.Response(400))
        with self.assertRaises(SearchError):
            search.search("puente")
        self.assertEqual(len(requests), 1)

    def test_tiempo_agotado_y_conexion(self):
        search, requests = provider(BraveSearch, httpx.ReadTimeout("lento"))
        with self.assertRaises(SearchError):
            search.search("puente")
        self.assertEqual(len(requests), 1)
        search, requests = provider(BraveSearch, httpx.ConnectError("no conecta"))
        with self.assertRaises(SearchError):
            search.search("puente")
        self.assertEqual(len(requests), 2)

    def test_respuesta_que_no_es_json_o_no_es_objeto(self):
        for response in (httpx.Response(200, content=b"<html>"), httpx.Response(200, json=["x"])):
            search, _ = provider(TavilySearch, response)
            with self.assertRaises(SearchError):
                search.search("puente")


class FactoryTests(unittest.TestCase):
    def test_construye_el_proveedor_de_la_configuracion(self):
        self.assertIsInstance(build_search_provider(SearchSettings("brave", KEY, 5.0)), BraveSearch)
        self.assertIsInstance(build_search_provider(SearchSettings("tavily", KEY, 5.0)), TavilySearch)

    def test_configuracion_desde_el_entorno(self):
        import os
        from unittest import mock

        env = {"SEARCH_PROVIDER": "Tavily", "SEARCH_API_KEY": KEY, "SEARCH_TIMEOUT": "20"}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch("backend.core.config.load_dotenv"):
            settings = SearchSettings.from_environment()
        self.assertEqual((settings.provider, settings.api_key, settings.timeout), ("tavily", KEY, 20.0))
        with mock.patch.dict(os.environ, {"SEARCH_PROVIDER": "", "SEARCH_API_KEY": KEY}), mock.patch("backend.core.config.load_dotenv"):
            self.assertIsNone(SearchSettings.from_environment())
        for bad in ({"SEARCH_PROVIDER": "bing", "SEARCH_API_KEY": KEY}, {**env, "SEARCH_TIMEOUT": "0"}, {**env, "SEARCH_TIMEOUT": "x"}):
            with mock.patch.dict(os.environ, bad), mock.patch("backend.core.config.load_dotenv"):
                with self.assertRaises(ValueError):
                    SearchSettings.from_environment()


if __name__ == "__main__":
    unittest.main()
