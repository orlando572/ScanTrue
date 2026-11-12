"""Caso de uso de análisis de texto con los modelos disponibles."""

import logging
from dataclasses import dataclass, field
from itertools import islice
from typing import Protocol

from bilstm.modelo import TOKEN_PATTERN
from backend.models.bilstm import BilstmPredictor
from backend.models.contrato import Combination
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
# Límite del fragmento original que se guarda (columna analisis.texto_original).
MAX_ORIGINAL_CHARS = 20_000
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
    # Fragmento original completo (limpio) y fragmentos tal como se marcaron.
    original_text: str | None = None
    fragments: list[str] | None = None
    # Prefijo del texto que leyó cada modelo: cada uno recorta por su cuenta.
    model_texts: dict[str, str] = field(default_factory=dict)


def clean_fragments(fragments: list[str] | None, text: str) -> list[str] | None:
    """Fragmentos limpios, solo si juntos son el texto enviado (pudo editarse después)."""
    if not fragments:
        return None
    cleaned = [value for value in (clean_news_text(item) for item in fragments) if value]
    return cleaned if cleaned and " ".join(cleaned) == text else None


class AnalysisService:
    def __init__(
        self,
        predictor: BilstmPredictor,
        mbert_predictor: Predictor | None = None,
        mbert_text_policy: MbertTokenizer | None = None,
        combination: Combination | None = None,
    ) -> None:
        if mbert_predictor is not None and mbert_text_policy is None:
            raise ValueError("mBERT requiere su tokenizador para validar la entrada")
        self.predictor = predictor
        self.mbert_predictor = mbert_predictor
        self.mbert_text_policy = mbert_text_policy
        # Por defecto, la combinación versionada en datasets/combinacion_produccion/.
        self.combination = combination or Combination.load()

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

        # Cada modelo lee hasta su propio límite (BiLSTM 192 palabras, mBERT 256 subpalabras).
        # Los dos recortes son prefijos del mismo texto: se guarda y se envía el más largo y
        # cada predictor recorta dentro de él lo que le corresponde.
        model_input, truncated = self._bilstm_prefix(text)
        model_texts = {"bilstm": model_input}
        mbert_predictor = self.mbert_predictor
        mbert_prepare_failed = False
        mbert_token_count = None
        if self.mbert_text_policy is not None:
            try:
                mbert_input, mbert_truncated, mbert_token_count = self.mbert_text_policy.prepare(
                    text
                )
                model_texts["mbert"] = mbert_input
                if len(mbert_input) > len(model_input):
                    model_input = mbert_input
                truncated = truncated and mbert_truncated
            except Exception:
                logger.exception("Falló la tokenización mBERT")
                mbert_token_count = None
                mbert_predictor = None
                mbert_prepare_failed = True
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
        # Cada modelo ya devuelve su probabilidad calibrada; se combinan sus logits
        # (docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md).
        probability, used_weights = self.combination.combine(
            {result.modelo: result.probabilidad_falsa for result in successful}
        )
        weights = AppliedWeights(
            bilstm=used_weights.get("bilstm", 0.0),
            mbert=used_weights.get("mbert", 0.0),
        )
        probability = min(1.0, max(0.0, probability))
        response = AnalysisResponse(
            resultados=results,
            resultado_unificado=UnifiedResult(
                probabilidad_falsa=probability,
                modelos_utilizados=[result.modelo for result in successful],
                pesos_aplicados=weights,
                version_combinacion=self.combination.version,
            ),
            comparacion=comparison,
            nota="Las probabilidades son salidas experimentales de clasificadores; no verifican hechos.",
        )
        return AnalysisOutcome(
            response=response, text=model_input, truncated=truncated,
            original_text=text[:MAX_ORIGINAL_CHARS],
            fragments=clean_fragments(payload.fragmentos, text),
            model_texts={
                name: value for name, value in model_texts.items()
                if results[name].estado == "ok"
            },
        )
