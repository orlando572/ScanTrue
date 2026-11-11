"""Pruebas del texto que se analiza y se guarda."""

import unittest
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError

from backend.api.routes import analyze as analyze_route
from backend.repositories.supabase import SELECT_HISTORY_BASE, SupabaseRepository
from backend.schemas.analysis import AnalysisRequest
from backend.services.analysis import AnalysisService, InvalidAnalysisInput
from backend.services.text_cleaning import clean_news_text
from bilstm.modelo import tokenize


class FakePredictor:
    max_len = 192

    def __init__(self, name):
        self.name = name
        self.received = []

    tokenize = staticmethod(tokenize)

    def predict(self, text):
        self.received.append(text)
        return {
            "version": "prueba", "clase": "real", "probabilidad_falsa": 0.2,
            "tokens_leidos": min(len(tokenize(text)), self.max_len),
        }


class FakeMbertPolicy:
    def prepare(self, text):
        return text, False, len(tokenize(text)) + 2


class TextCleaningTests(unittest.TestCase):
    def test_news_example_preserves_content_and_removes_formatting(self):
        raw = (
            'PNP captura a alias “Leo”\n\n'
            '##### Durante operativo se incautaron 22 granadas.\n\n'
            '**10/10/2026 20:37&#x20;**&#x45;n concordancia con la estrategia\n\n'
            '&#x20;impulsada por el Ministerio del Interior, la PNP logró la captura.'
        )
        expected = (
            'PNP captura a alias “Leo” Durante operativo se incautaron 22 granadas. '
            '10/10/2026 20:37 En concordancia con la estrategia impulsada por '
            'el Ministerio del Interior, la PNP logró la captura.'
        )
        self.assertEqual(clean_news_text(raw), expected)
        self.assertEqual(clean_news_text(expected), expected)

    def test_unicode_entities_emphasis_and_legitimate_symbols(self):
        raw = '\ufeff  **Noticia**\u00a0 __importante__ &nbsp; S/ 73,800; #1 y 22 * 3.  '
        expected = 'Noticia importante S/ 73,800; #1 y 22 * 3.'
        self.assertEqual(clean_news_text(raw), expected)
        self.assertEqual(clean_news_text(expected), expected)

    def test_training_placeholders_are_preserved(self):
        raw = 'El operativo incautó *NUMBER* objetos y encontró *URL* en el informe.'
        self.assertEqual(clean_news_text(raw), raw)

    def test_nested_html_entities_are_idempotent(self):
        raw = 'Un espacio: &amp;#x20; y una letra: &amp;#x45;'
        cleaned = clean_news_text(raw)
        self.assertEqual(cleaned, 'Un espacio: y una letra: E')
        self.assertEqual(clean_news_text(cleaned), cleaned)

    def test_ampersand_without_entity_is_preserved(self):
        self.assertEqual(clean_news_text('Pérez &noticias sobre R&D'),
                         'Pérez &noticias sobre R&D')

    def test_input_becomes_too_short_after_cleaning(self):
        bilstm = FakePredictor('bilstm')
        service = AnalysisService(bilstm)
        with self.assertRaises(InvalidAnalysisInput) as caught:
            service.analyze(AnalysisRequest(texto='&#x20;  ##### breve  **texto**'))
        self.assertEqual(caught.exception.code, 'texto_insuficiente')
        self.assertEqual(bilstm.received, [])

    def test_both_models_receive_selected_title_once(self):
        bilstm, mbert = FakePredictor('bilstm'), FakePredictor('mbert')
        service = AnalysisService(bilstm, mbert, FakeMbertPolicy())
        raw = '##### Título de prueba\n\n' + 'noticia con 22 datos. ' * 34
        outcome = service.analyze(AnalysisRequest(texto=raw))
        self.assertTrue(outcome.text.startswith('Título de prueba noticia con 22 datos.'))
        self.assertEqual(outcome.text.count('Título de prueba'), 1)
        self.assertEqual(bilstm.received, [outcome.text])
        self.assertEqual(mbert.received, [outcome.text])
        self.assertNotIn('&#', outcome.text)
        self.assertNotIn('  ', outcome.text)

    def test_body_without_title_and_first_line_are_preserved(self):
        bilstm = FakePredictor('bilstm')
        service = AnalysisService(bilstm)
        body = 'Primera línea del cuerpo.\n' + 'dato relevante. ' * 55
        outcome = service.analyze(AnalysisRequest(texto=body))
        self.assertEqual(outcome.text, clean_news_text(body))
        self.assertEqual(bilstm.received, [outcome.text])

    def test_separate_title_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            AnalysisRequest.model_validate({
                'texto': 'dato relevante. ' * 55,
                'titulo': 'Titular separado',
            })
        self.assertEqual(caught.exception.errors()[0]['type'], 'extra_forbidden')

    def test_route_persists_exact_model_input_and_hash(self):
        bilstm = FakePredictor('bilstm')
        service = AnalysisService(bilstm)
        captured = {}
        analysis_id = uuid4()

        class Repository:
            def create_analysis(self, **values):
                captured.update(values)
                return analysis_id

        user_id = uuid4()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            analysis_service=service,
        )))
        identity = SimpleNamespace(verify_user=lambda _token: SimpleNamespace(id=str(user_id)))
        payload = AnalysisRequest(texto='##### Titular&#x20;\n' + 'dato relevante. ' * 55)
        response = analyze_route(payload, request, 'token', identity, Repository())
        self.assertEqual(response.id, analysis_id)
        self.assertEqual(captured['text'], bilstm.received[0])
        self.assertEqual(captured['text_hash'], sha256(captured['text'].encode()).hexdigest())
        self.assertTrue(captured['text'].startswith('Titular dato relevante.'))
        self.assertNotIn('title', captured)

    def test_repository_uses_text_only_rpc_and_history_select(self):
        repository = SupabaseRepository.__new__(SupabaseRepository)
        calls = []
        repository._request = lambda *args, **kwargs: calls.append((args, kwargs)) or str(uuid4())
        service = AnalysisService(FakePredictor('bilstm'))
        outcome = service.analyze(AnalysisRequest(texto='dato relevante. ' * 55))
        repository.create_analysis(
            user_id=uuid4(), url=None, text=outcome.text,
            text_hash=sha256(outcome.text.encode()).hexdigest(), response=outcome.response,
        )
        self.assertEqual(calls[0][0], ('POST', 'rpc/crear_analisis_texto_unico'))
        self.assertNotIn('p_titulo', calls[0][1]['body'])
        self.assertNotIn('titulo', SELECT_HISTORY_BASE)


if __name__ == '__main__':
    unittest.main()
