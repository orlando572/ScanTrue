"""Contratos de datos del endpoint de análisis."""

from typing import Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    texto: str = Field(description="Texto de la noticia que se analizará")
    titulo: str | None = Field(default=None, max_length=200, description="Titular opcional")
    url: str | None = Field(default=None, max_length=2048, description="URL opcional de referencia")


class ModelResult(BaseModel):
    modelo: str
    estado: Literal["ok", "no_disponible", "fallo"]
    version: str | None = None
    clase: Literal["falsa", "real"] | None = None
    probabilidad_falsa: float | None = Field(default=None, ge=0, le=1)
    tokens_leidos: int | None = Field(default=None, ge=0)
    error: str | None = None


class AppliedWeights(BaseModel):
    bilstm: float = Field(ge=0, le=1)
    mbert: float = Field(ge=0, le=1)


class UnifiedResult(BaseModel):
    probabilidad_falsa: float = Field(ge=0, le=1)
    modelos_utilizados: list[Literal["bilstm", "mbert"]]
    pesos_aplicados: AppliedWeights
    version_regla: Literal["media_ponderada_v1"] = "media_ponderada_v1"


class AnalysisResponse(BaseModel):
    resultados: dict[str, ModelResult]
    resultado_unificado: UnifiedResult
    comparacion: Literal["coinciden", "discrepan", "no_disponible"]
    nota: str
