"""Contratos de datos del endpoint de análisis."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(description="Texto de la noticia que se analizará")
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
    # Se mantiene «media_ponderada_v1» porque la base de datos solo acepta ese valor
    # (migraciones 004 y 005). Desde la calibración conjunta, la media es de logits
    # calibrados; la combinación exacta la identifica `version_combinacion`.
    version_regla: Literal["media_ponderada_v1"] = "media_ponderada_v1"
    version_combinacion: str | None = None


class AnalysisResponse(BaseModel):
    resultados: dict[str, ModelResult]
    resultado_unificado: UnifiedResult
    comparacion: Literal["coinciden", "discrepan", "no_disponible"]
    nota: str
