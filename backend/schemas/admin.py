"""Contratos del panel de administración: casos, revisión, datasets y modelos."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas.metrics import MetricsResponse
from backend.schemas.public import DomainCount, PublicAnalysis, PublicAnalysisDetail

Label = Literal["falsa", "real"]
Decision = Literal["aprobado", "corregido", "descartado"]


class AdminIdentity(BaseModel):
    usuario_id: UUID
    correo: str | None
    rol: str


# ── Casos y revisión ────────────────────────────────────────────────


class Review(BaseModel):
    decision: Decision
    etiqueta_final: Label | None = None
    nota: str | None = None
    evidencia: list[str] = Field(default_factory=list)
    grupo_evento: str | None = None
    fecha: datetime | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    etiqueta_final: Label | None = Field(
        default=None, description="Obligatoria al corregir; al aprobar se usa la del modelo."
    )
    nota: str | None = Field(default=None, max_length=2000)
    evidencia: list[str] = Field(default_factory=list, max_length=10)
    grupo_evento: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def check(self) -> "ReviewRequest":
        if self.decision == "corregido" and self.etiqueta_final is None:
            raise ValueError("Al corregir hay que indicar la etiqueta final.")
        if any(len(item) > 2048 for item in self.evidencia):
            raise ValueError("Cada evidencia admite hasta 2048 caracteres.")
        return self


class VisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oculto: bool


class AdminCase(PublicAnalysis):
    oculto: bool = False
    etiqueta_modelo: Label | None = None
    revision: Review | None = None


class AdminCaseDetail(PublicAnalysisDetail):
    oculto: bool = False
    etiqueta_modelo: Label | None = None
    revision: Review | None = None


class AdminCasePage(BaseModel):
    elementos: list[AdminCase]
    total: int | None


class DayCount(BaseModel):
    dia: str
    n: int


class AdminSummary(BaseModel):
    total: int = 0
    ocultos: int = 0
    ultimas_24h: int = 0
    ultimos_7_dias: int = 0
    probabilidad_media: float | None = None
    niveles: list[int] = Field(default_factory=lambda: [0] * 5)
    comparacion: dict[str, int] = Field(default_factory=dict)
    blockchain: dict[str, int] = Field(default_factory=dict)
    revisiones: dict[str, int] = Field(default_factory=dict)
    verificaciones_web: int = 0
    por_dia: list[DayCount] = Field(default_factory=list)
    dominios: list[DomainCount] = Field(default_factory=list)
    datasets: int = 0
    despliegue_activo: str | None = None


# ── Versiones de dataset ────────────────────────────────────────────


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = Field(default=None, max_length=500)
    fraccion_prueba: float = Field(default=0.2, ge=0.05, le=0.5)


class DatasetSummary(BaseModel):
    """Qué entra en una versión y qué se separó o quedó fuera."""

    candidatos: int = 0
    casos: int = 0
    duplicados_retirados: int = 0
    conflictos_retirados: int = 0
    grupos: int = 0
    grupos_con_varios: int = 0
    por_etiqueta: dict[str, int] = Field(default_factory=dict)
    por_particion: dict[str, int] = Field(default_factory=dict)
    por_decision: dict[str, int] = Field(default_factory=dict)
    por_particion_etiqueta: dict[str, dict[str, int]] = Field(default_factory=dict)
    fraccion_prueba: float = 0.2


class DatasetVersion(BaseModel):
    id: UUID
    nombre: str
    descripcion: str | None = None
    fecha: datetime
    resumen: DatasetSummary


class DatasetItem(BaseModel):
    id: UUID | None = None
    analisis_id: UUID | None = None
    texto: str
    hash_texto: str
    etiqueta: Label
    particion: Literal["entrenamiento", "prueba"]
    grupo: str
    url: str | None = None
    dominio: str | None = None
    decision: Literal["aprobado", "corregido"]
    procedencia: dict = Field(default_factory=dict)
    evidencia: list = Field(default_factory=list)


class DatasetDetail(DatasetVersion):
    elementos: list[DatasetItem]
    total: int | None


# ── Versiones de modelos ────────────────────────────────────────────


class DeploymentModel(BaseModel):
    modelo: Literal["bilstm", "mbert"]
    version: str | None = None
    casos: int = Field(default=0, description="Análisis guardados con esta versión.")
    metricas: MetricsResponse | None = None


class DeploymentInfo(BaseModel):
    version: str
    nombre: str
    fecha: str | None = None
    notas: str | None = None
    activable: bool
    activa: bool
    pesos: dict[str, float] | None = None
    temperaturas: dict[str, float] | None = None
    modelos: list[DeploymentModel]


class ActivationEntry(BaseModel):
    version: str
    anterior: str | None = None
    accion: Literal["activar", "revertir"]
    fecha: datetime
    por: str | None = None


class ModelsResponse(BaseModel):
    activa: str | None
    anterior: str | None = Field(description="Versión a la que volvería «revertir».")
    versiones: list[DeploymentInfo]
    historial: list[ActivationEntry]


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=160)
