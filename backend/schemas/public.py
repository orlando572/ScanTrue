"""Contrato de la web pública: resultados sin datos de usuario."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.analysis import UnifiedResult


class WebVerification(BaseModel):
    """Tercer criterio (incremento 2). Mientras no exista, el campo llega como null."""

    estado: Literal["pendiente", "en_proceso", "completada", "fallida"]
    conclusion: Literal[
        "respaldada", "contradicha", "fuera_de_contexto", "evidencia_insuficiente"
    ] | None = None
    resumen: str | None = None
    afirmaciones: list = Field(default_factory=list)
    fuentes: list = Field(default_factory=list)
    modelo_llm: str | None = None
    actualizado_en: datetime | None = None


class PublicModelOutput(BaseModel):
    modelo: str
    estado: Literal["ok"] = "ok"
    version: str | None = None
    clase: Literal["falsa", "real"]
    probabilidad_falsa: float = Field(ge=0, le=1)
    tokens_leidos: int | None = None
    # Solo en el detalle: el prefijo del texto que leyó este modelo.
    texto_modelo: str | None = None


class PublicAnalysis(BaseModel):
    id: UUID
    fecha: datetime
    dominio: str | None
    url: str | None = Field(description="Dirección de la página sin consulta ni fragmento.")
    fragmentos: list[str] = Field(description="Fragmentos marcados; en la lista van abreviados.")
    fragmentos_total: int = Field(ge=0)
    palabras: int = Field(ge=0, description="Palabras del texto analizado.")
    texto_recortado: bool = False
    probabilidad_falsa: float | None = Field(default=None, ge=0, le=1)
    comparacion: Literal["coinciden", "discrepan", "no_disponible"]
    estado_blockchain: Literal["no_iniciado", "pendiente", "confirmado", "fallido"]
    hash_transaccion: str | None = None
    resultados: dict[str, PublicModelOutput]
    resultado_unificado: UnifiedResult | None = None
    verificacion_web: WebVerification | None = None


class PublicAnalysisDetail(PublicAnalysis):
    hash_texto: str
    texto: str | None = Field(description="Texto que recibieron los modelos (ya recortado).")
    texto_original: str | None = Field(description="Fragmento original completo, si se guardó.")


class PublicAnalysisPage(BaseModel):
    elementos: list[PublicAnalysis]
    total: int | None = Field(default=None, description="Total con los filtros aplicados.")


class DomainCount(BaseModel):
    dominio: str
    n: int


class PublicSummary(BaseModel):
    total: int = 0
    ultimas_24h: int = 0
    ultimos_7_dias: int = 0
    niveles: list[int] = Field(default_factory=lambda: [0] * 5)
    comparacion: dict[str, int] = Field(default_factory=dict)
    dominios: list[DomainCount] = Field(default_factory=list)
    verificaciones_web: int = 0
