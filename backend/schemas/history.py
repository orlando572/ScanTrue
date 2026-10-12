"""Respuestas de creación y consulta del historial."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.schemas.analysis import AnalysisResponse, ModelResult, UnifiedResult


class CreatedAnalysis(AnalysisResponse):
    id: UUID
    estado_blockchain: Literal["pendiente"] = "pendiente"
    texto_recortado: bool = False


class HistoryBase(BaseModel):
    id: UUID
    fecha: datetime
    url: str | None
    hash_texto: str
    comparacion: Literal["coinciden", "discrepan", "no_disponible"]
    estado_blockchain: Literal["no_iniciado", "pendiente", "confirmado", "fallido"]
    hash_transaccion: str | None
    resultados: dict[str, ModelResult]
    resultado_unificado: UnifiedResult | None


class HistoryListRecord(HistoryBase):
    vista_previa: str | None


class HistoryRecord(HistoryBase):
    texto: str | None
