"""Caso de uso de análisis de texto con los modelos disponibles."""

import logging
from dataclasses import dataclass
from itertools import islice
from math import isfinite
from typing import Protocol

from bilstm.entrenar_baseline import TOKEN_PATTERN
from backend.models.bilstm import BilstmPredictor
from backend.models.mbert import MbertTokenizer
from backend.services.text_cleaning import clean_news_text
from backend.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    AppliedWeights,
    ModelResult,
    UnifiedResult,
)

MIN_INPUT_TOKENS = 100
logger = logging.getLogger(__name__)


class InvalidAnalysisInput(ValueError):
    def __init__(self, code: str, message: str, suggestion: str) -> None:
        super().__init__(message)
        self.code = code
        self.suggestion = suggestion


class ModelUnavailableError(RuntimeError):
    """Ningún modelo produjo una predicción; se puede volver a intentar."""


class Predictor(Protocol):
    def predict(self, text: str) -> dict[str, str | float | int]: ...


@dataclass(frozen=True)
class AnalysisOutcome:
    response: AnalysisResponse
    text: str
    truncated: bool


class AnalysisService:
    def __init__(
        self,
        predictor: BilstmPredictor,
        mbert_predictor: Predictor | None = None,
        mbert_text_policy: MbertTokenizer | None = None,
        mbert_weight: float = 0.7,
    ) -> None:
        if not isfinite(mbert_weight) or not 0 <= mbert_weight <= 1:
            raise ValueError("ANALYSIS_MBERT_WEIGHT debe estar entre 0 y 1.")
        if mbert_predictor is not None and mbert_text_policy is None:
            raise ValueError("mBERT requiere su tokenizador para validar la entrada")
        self.predictor = predictor
        self.mbert_predictor = mbert_predictor
        self.mbert_text_policy = mbert_text_policy
        self.mbert_weight = mbert_weight

    def _bilstm_prefix(self, text: str) -> tuple[str, bool]:
        matches = list(islice(TOKEN_PATTERN.finditer(text), self.predictor.max_len + 1))
        truncated = len(matches) > self.predictor.max_len
        if truncated:
            text = text[: matches[self.predictor.max_len - 1].end()].rstrip()
        return text, truncated

    def analyze(self, payload: AnalysisRequest) -> AnalysisOutcome:
        text = clean_news_text(payload.texto)
        if not text:
            raise InvalidAnalysisInput(
                "texto_vacio",
                "El texto de la noticia está vacío.",
                "Envía el cuerpo de la noticia en el campo 'texto'.",
            )

        model_input = text
        mbert_predictor = self.mbert_predictor
        mbert_prepare_failed = False
        if self.mbert_text_policy is not None:
            try:
                model_input, truncated, mbert_token_count = self.mbert_text_policy.prepare(
                    model_input
                )
            except Exception:
                logger.exception("Falló la tokenización mBERT")
                model_input, truncated = self._bilstm_prefix(model_input)
                mbert_token_count = None
                mbert_predictor = None
                mbert_prepare_failed = True
        else:
            model_input, truncated = self._bilstm_prefix(model_input)
            mbert_token_count = None
        token_count = len(self.predictor.tokenize(model_input))
        if token_count == 0:
            raise InvalidAnalysisInput(
                "texto_ilegible",
                "El texto no contiene palabras que el modelo pueda leer.",
                "Envía texto con palabras; no solo símbolos o espacios.",
            )
        if token_count < MIN_INPUT_TOKENS:
            raise InvalidAnalysisInput(
                "texto_insuficiente",
                f"El texto debe tener al menos {MIN_INPUT_TOKENS} tokens; recibí {token_count}.",
                f"Añade contexto hasta llegar a {MIN_INPUT_TOKENS} palabras tokenizables.",
            )
        if mbert_predictor is not None and mbert_token_count is not None and mbert_token_count < MIN_INPUT_TOKENS:
            raise InvalidAnalysisInput(
                "texto_insuficiente_mbert",
                f"mBERT debe recibir al menos {MIN_INPUT_TOKENS} tokens; recibió {mbert_token_count}.",
                "Añade contexto al texto para ambos modelos.",
            )
        results: dict[str, ModelResult] = {}
        for name, predictor in (
            ("bilstm", self.predictor),
            ("mbert", mbert_predictor),
        ):
            if name == "mbert" and mbert_prepare_failed:
                results[name] = ModelResult(
                    modelo=name,
                    estado="fallo",
                    error="Falló la preparación de mBERT; puedes volver a intentarlo.",
                )
                continue
            if predictor is None:
                results[name] = ModelResult(
                    modelo=name,
                    estado="no_disponible",
                    error="mBERT no está disponible en este inicio del backend.",
                )
                continue
            try:
                prediction = predictor.predict(model_input)
                model_result = ModelResult(
                    **{**prediction, "modelo": name, "estado": "ok"}
                )
                if (
                    not model_result.version
                    or model_result.clase is None
                    or model_result.probabilidad_falsa is None
                    or model_result.tokens_leidos is None
                    or model_result.tokens_leidos <= 0
                ):
                    raise ValueError("Predicción incompleta")
                results[name] = model_result
            except Exception:
                logger.exception("Falló la inferencia del modelo %s", name)
                results[name] = ModelResult(
                    modelo=name,
                    estado="fallo",
                    error=f"Falló la inferencia {name}; puedes volver a intentarlo.",
                )

        successful = [
            result for result in results.values()
            if result.estado == "ok" and result.probabilidad_falsa is not None
        ]
        if not successful:
            raise ModelUnavailableError(
                "Ningún modelo produjo una predicción; puedes volver a intentar el análisis."
            )
        comparison = "no_disponible"
        if len(successful) == 2:
            comparison = (
                "coinciden"
                if successful[0].clase == successful[1].clase
                else "discrepan"
            )
        if len(successful) == 1:
            weights = AppliedWeights(
                bilstm=1.0 if successful[0].modelo == "bilstm" else 0.0,
                mbert=1.0 if successful[0].modelo == "mbert" else 0.0,
            )
        else:
            weights = AppliedWeights(
                bilstm=1.0 - self.mbert_weight,
                mbert=self.mbert_weight,
            )
        probability = sum(
            result.probabilidad_falsa * getattr(weights, result.modelo)
            for result in successful
        )
        probability = min(1.0, max(0.0, probability))
        response = AnalysisResponse(
            resultados=results,
            resultado_unificado=UnifiedResult(
                probabilidad_falsa=probability,
                modelos_utilizados=[result.modelo for result in successful],
                pesos_aplicados=weights,
            ),
            comparacion=comparison,
            nota="Las probabilidades son salidas experimentales de clasificadores; no verifican hechos.",
        )
        return AnalysisOutcome(
            response=response, text=model_input, truncated=truncated,
        )
