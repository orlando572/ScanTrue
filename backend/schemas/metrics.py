"""Contrato público de las evaluaciones de modelos."""

from typing import Literal

from pydantic import BaseModel, Field


class ModelEvaluation(BaseModel):
    conjunto: str
    n: int = Field(gt=0)
    matriz_confusion: tuple[tuple[int, int], tuple[int, int]] = Field(
        description="Filas: etiqueta real; columnas: predicción. El orden lo indica orden_clases."
    )
    exactitud: float = Field(ge=0, le=1)
    precision_falsa: float = Field(ge=0, le=1)
    recall_falsa: float = Field(ge=0, le=1)
    f1_falsa: float = Field(ge=0, le=1)
    f1_macro: float = Field(ge=0, le=1)
    fuente: str


class MetricsResponse(BaseModel):
    modelo: Literal["bilstm", "mbert"]
    version: str
    orden_clases: tuple[Literal["falsa"], Literal["real"]]
    evaluaciones: list[ModelEvaluation]
    limitaciones: list[str]
