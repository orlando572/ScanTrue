"""Combinación calibrada, contratos y recorte por modelo, sin cargar pesos.

Uso: PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m unittest backend.tests.test_analysis_combination
"""

import json
from math import exp, log
from pathlib import Path
import tempfile
import unittest

from backend.models.contrato import (
    BILSTM_CONTRACT, COMBINATION_FILE, MBERT_CONTRACT, Combination, ModelContract,
    calibrated_probability, logit, sigmoid,
)
from backend.schemas.analysis import AnalysisRequest
from backend.services.analysis import AnalysisService, InvalidAnalysisInput


def combination(**changes) -> Combination:
    values = {
        "version": "prueba", "weights": {"bilstm": 0.2, "mbert": 0.8},
        "temperatures": {"bilstm": 8.0, "mbert": 2.0},
        "model_versions": {"bilstm": "B", "mbert": "M"}, "threshold": 0.5,
    }
    values.update(changes)
    return Combination(**values)


class FakeBilstm:
    max_len = 192

    def __init__(self, probability: float = 0.7) -> None:
        self.probability = probability
        self.seen: list[str] = []

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return text.split()

    def predict(self, text: str) -> dict:
        self.seen.append(text)
        return {"modelo": "bilstm", "version": "B", "clase": "falsa" if self.probability >= 0.5 else "real",
                "probabilidad_falsa": self.probability, "tokens_leidos": min(self.max_len, len(text.split()))}


class FakeMbertPolicy:
    """Recorta a las primeras `limit` palabras, como si cada palabra fuera una subpalabra."""

    def __init__(self, limit: int) -> None:
        self.limit = limit

    def prepare(self, text: str):
        words = text.split()
        return " ".join(words[: self.limit]), len(words) > self.limit, min(len(words), self.limit)


class FakeMbert(FakeBilstm):
    def predict(self, text: str) -> dict:
        result = super().predict(text)
        return {**result, "modelo": "mbert", "version": "M"}


class CombinationTests(unittest.TestCase):
    def test_formula_de_logits(self):
        p, weights = combination().combine({"bilstm": 0.6, "mbert": 0.9})
        self.assertAlmostEqual(p, sigmoid(0.2 * logit(0.6) + 0.8 * logit(0.9)))
        self.assertEqual(weights, {"bilstm": 0.2, "mbert": 0.8})

    def test_un_solo_modelo_usa_su_probabilidad(self):
        self.assertEqual(combination().combine({"mbert": 0.33}), (0.33, {"mbert": 1.0}))
        with self.assertRaises(ValueError):
            combination().combine({})

    def test_temperatura(self):
        self.assertAlmostEqual(calibrated_probability(4.0, 2.0), 1 / (1 + exp(-2.0)))
        self.assertAlmostEqual(logit(sigmoid(1.3)), 1.3)
        self.assertAlmostEqual(log(0.5 / 0.5), logit(0.5))

    def test_combinacion_rechaza_pesos_invalidos(self):
        datos = json.loads(COMBINATION_FILE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "c.json"
            for cambio in ({"pesos": {"bilstm": 0.5, "mbert": 0.6}}, {"pesos": {"bilstm": -0.1, "mbert": 1.1}},
                           {"metodo": "otro"}, {"regla_discrepancia": 0.4}):
                ruta.write_text(json.dumps({**datos, **cambio}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    Combination.load(ruta)


class ProductionFilesTests(unittest.TestCase):
    """Los contratos y la combinación que se versionan deben ser coherentes entre sí."""

    def test_contratos_y_combinacion_coinciden(self):
        c = Combination.load()
        self.assertEqual(c.weights, {"bilstm": 0.2, "mbert": 0.8})
        for ruta, nombre in ((BILSTM_CONTRACT, "bilstm"), (MBERT_CONTRACT, "mbert")):
            contrato = ModelContract.load(ruta, nombre)
            c.check(contrato)
            self.assertTrue(contrato.checkpoint.exists(), contrato.checkpoint)
        self.assertEqual(ModelContract.load(MBERT_CONTRACT, "mbert").max_tokens, 256)
        self.assertEqual(ModelContract.load(BILSTM_CONTRACT, "bilstm").max_tokens, 192)

    def test_temperatura_distinta_se_rechaza(self):
        contrato = ModelContract.load(BILSTM_CONTRACT, "bilstm")
        otra = combination(model_versions={"bilstm": contrato.version, "mbert": "M"},
                           temperatures={"bilstm": contrato.temperature + 1, "mbert": 2.0})
        with self.assertRaises(ValueError):
            otra.check(contrato)

    def test_contrato_de_otro_modelo_se_rechaza(self):
        with self.assertRaises(ValueError):
            ModelContract.load(BILSTM_CONTRACT, "mbert")


class AnalysisServiceTests(unittest.TestCase):
    def test_unificado_y_pesos_aplicados(self):
        service = AnalysisService(FakeBilstm(0.6), mbert_predictor=FakeMbert(0.9),
                                  mbert_text_policy=FakeMbertPolicy(150), combination=combination())
        response = service.analyze(AnalysisRequest(texto=" ".join(["palabra"] * 120))).response
        unified = response.resultado_unificado
        self.assertAlmostEqual(unified.probabilidad_falsa, sigmoid(0.2 * logit(0.6) + 0.8 * logit(0.9)))
        self.assertEqual(unified.pesos_aplicados.model_dump(), {"bilstm": 0.2, "mbert": 0.8})
        self.assertEqual(unified.version_combinacion, "prueba")
        self.assertEqual(unified.version_regla, "media_ponderada_v1")

    def test_cada_modelo_recibe_el_prefijo_mas_largo(self):
        bilstm, mbert = FakeBilstm(), FakeMbert()
        bilstm.max_len = 150
        service = AnalysisService(bilstm, mbert_predictor=mbert, mbert_text_policy=FakeMbertPolicy(120),
                                  combination=combination())
        texto = " ".join(f"p{i}" for i in range(300))
        outcome = service.analyze(AnalysisRequest(texto=texto))
        self.assertEqual(len(outcome.text.split()), 150)  # BiLSTM lee más que mBERT aquí
        self.assertTrue(outcome.truncated)
        self.assertEqual(bilstm.seen, mbert.seen)

    def test_sin_mbert_usa_solo_bilstm(self):
        service = AnalysisService(FakeBilstm(0.3), combination=combination())
        response = service.analyze(AnalysisRequest(texto=" ".join(["palabra"] * 120))).response
        self.assertEqual(response.resultado_unificado.probabilidad_falsa, 0.3)
        self.assertEqual(response.resultados["mbert"].estado, "no_disponible")

    def test_texto_corto(self):
        service = AnalysisService(FakeBilstm(), combination=combination())
        with self.assertRaises(InvalidAnalysisInput):
            service.analyze(AnalysisRequest(texto="pocas palabras"))

    def test_combinacion_por_defecto_es_la_de_produccion(self):
        self.assertEqual(AnalysisService(FakeBilstm()).combination, Combination.load())


if __name__ == "__main__":
    unittest.main()
