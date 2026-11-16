"""Contratos del panel de administración: casos, revisión, datasets, modelos y entrenamiento."""

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


class ExcludedCase(BaseModel):
    analisis_id: UUID
    motivo: str


class CaseStandardPreview(BaseModel):
    """Cómo entraría un caso al dataset si se aprueba o corrige."""

    entra: bool
    motivo: str | None = Field(default=None, description="Por qué quedaría fuera.")
    fragmentos: list[int] = Field(default_factory=list, description="Palabras de cada fragmento.")
    tokens: int = 0
    tokens_limpios: int = Field(default=0, description="Palabras tras la limpieza, antes del tope.")
    recortes: list[str] = Field(default_factory=list)
    cruce_comun: Literal["congelada", "desarrollo"] | None = None
    comprobado_comun: bool = False


class DatasetSummary(BaseModel):
    """Qué entra en una versión y qué se separó o quedó fuera."""

    candidatos: int = 0
    casos: int = Field(default=0, description="Noticias que entran (cada una da 1 o más fragmentos).")
    fragmentos: int = Field(default=0, description="Filas del dataset: fragmentos de 100–200 tokens.")
    duplicados_retirados: int = 0
    conflictos_retirados: int = 0
    excluidas: dict[str, int] = Field(
        default_factory=dict,
        description="Noticias fuera: no_espanol, sin_fin_de_oracion, menos_de_100_tokens, "
                    "oraciones_demasiado_largas, cruce_prueba_congelada.")
    recortes: dict[str, int] = Field(
        default_factory=dict,
        description="Noticias recortadas: tope_noticia, inicio_incompleto, final_incompleto, "
                    "oraciones_sueltas.")
    excluidas_casos: list[ExcludedCase] = Field(
        default_factory=list,
        description="Hasta 100 noticias que quedan fuera, con su motivo (también conflictos).")
    filas_cambiadas_por_patron: dict[str, int] = Field(default_factory=dict)
    grupos: int = 0
    grupos_con_varios: int = 0
    uniones_casi_duplicado: int = Field(
        default=0, description="Grupos unidos por casi duplicado (tejas de 5 palabras).")
    cruces_comun: dict = Field(
        default_factory=dict,
        description="Cruces con comun_v1: retirados por estar en su prueba congelada y "
                    "enviados a entrenamiento por estar en su desarrollo.")
    por_etiqueta: dict[str, int] = Field(default_factory=dict)
    por_particion: dict[str, int] = Field(default_factory=dict)
    por_decision: dict[str, int] = Field(default_factory=dict)
    por_particion_etiqueta: dict[str, dict[str, int]] = Field(default_factory=dict)
    fragmentos_por_particion: dict[str, int] = Field(default_factory=dict)
    fragmentos_por_noticia: dict[int, int] = Field(default_factory=dict)
    tokens_noticia: dict[str, float] = Field(default_factory=dict)
    tokens_fragmento: dict[str, float] = Field(default_factory=dict)
    estandar: dict = Field(default_factory=dict, description="Parámetros del estándar de fila.")
    fraccion_prueba: float = 0.2


class DatasetVersion(BaseModel):
    id: UUID
    nombre: str
    descripcion: str | None = None
    fecha: datetime
    resumen: DatasetSummary
    manifiesto: dict = Field(
        default_factory=dict,
        description="Archivos con su SHA-256, parámetros del estándar y código que la construyó.")


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
    # Columnas del estándar (datos_comunes/estandar.py). Las versiones creadas antes de la
    # migración 008 las tienen en `procedencia.fragmento`; las anteriores al estándar, vacías.
    id_fragmento: str | None = None
    fuente: str | None = None
    peso: float | None = None
    tokens_bilstm: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _fragment_from_origin(cls, data):
        if isinstance(data, dict):
            fragment = (data.get("procedencia") or {}).get("fragmento") or {}
            for name in ("id_fragmento", "peso", "tokens_bilstm"):
                if data.get(name) is None and fragment.get(name) is not None:
                    data = {**data, name: fragment[name]}
            if data.get("fuente") is None and fragment:
                data = {**data, "fuente": (data.get("procedencia") or {}).get("fuente")}
        return data


class DatasetDetail(DatasetVersion):
    elementos: list[DatasetItem]
    total: int | None


# ── Modelos desplegados ─────────────────────────────────────────────

ModelType = Literal["bilstm", "mbert"]


class ModelEntryInfo(BaseModel):
    id: str = Field(description="Identificador en el catálogo: la versión del contrato (más el SHA si se repite).")
    tipo: ModelType
    version: str
    nombre: str
    fecha: str | None = None
    origen: Literal["repositorio", "entrenamiento", "importado", "calibracion"]
    ruta: str | None = Field(default=None, description="Carpeta del contrato, relativa a la raíz del repositorio.")
    estado: Literal["disponible", "pendiente_calibrar", "no_admitido", "no_valido", "archivado"]
    motivo: str | None = None
    notas: str | None = None
    temperatura: float | None = None
    max_tokens: int | None = None
    desplegado: bool = False
    cargado: bool = Field(default=False, description="Desplegado y cargado en memoria ahora mismo.")
    casos: int = Field(default=0, description="Análisis guardados con esta versión.")
    metricas: MetricsResponse | None = None


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bilstm: float = Field(ge=0, le=1)
    mbert: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def sum_one(self):
        if abs(self.bilstm + self.mbert - 1) > 1e-6:
            raise ValueError("Los pesos deben sumar 1")
        return self


class DeploymentHistoryEntry(BaseModel):
    accion: Literal["desplegar", "desplegar_calibracion", "retirar", "pesos", "revertir"]
    tipo: ModelType | None = None
    version: str | None = None
    pesos: dict[str, float] | None = None
    anterior: dict | None = None
    fecha: datetime
    por: str | None = None


class ModelsResponse(BaseModel):
    desplegados: dict[str, str | None] = Field(description="Modelo desplegado de cada tipo (id), o null si está retirado.")
    cargados: list[ModelType] = Field(description="Tipos con su modelo cargado y respondiendo.")
    pesos: Weights
    pesos_calibrados: Weights | None = Field(default=None, description="Pesos de la combinación calibrada (combinacion.json).")
    combinacion: str | None = Field(default=None, description="Versión de combinación que usan los análisis nuevos.")
    anterior: dict | None = Field(default=None, description="Estado al que llevaría «Volver atrás».")
    modelos: dict[str, list[ModelEntryInfo]]
    historial: list[DeploymentHistoryEntry]


class DeployRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: ModelType
    id: str = Field(min_length=1, max_length=200)


class DeployCalibrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=200)


class RetireRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: ModelType


# ── Entrenamiento ───────────────────────────────────────────────────


class TrainingSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["comun_v1", "panel", "conjunto"]
    version_id: UUID | None = Field(default=None, description="Versión del panel (solo con tipo panel).")
    version: str | None = Field(default=None, max_length=200,
                                description="Conjunto combinado de Datasets (solo con tipo conjunto).")

    @model_validator(mode="after")
    def panel_needs_version(self):
        if self.tipo == "panel" and self.version_id is None:
            raise ValueError("Elige la versión del panel")
        if self.tipo == "conjunto" and not self.version:
            raise ValueError("Elige el conjunto combinado")
        return self


class CombinedSetPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incluir_comun: bool = Field(default=True, description="Sumar las noticias a comun_v1 (sin cambiarlo).")
    versiones: list[UUID] = Field(min_length=1, max_length=20, description="Versiones del panel que se añaden.")
    balanceo: Literal["ninguno", "50_50"] = Field(
        default="ninguno", description="50_50: retira noticias enteras de la clase que sobra en lo añadido.")


class CombinedSetCreate(CombinedSetPreview):
    nombre: str = Field(min_length=3, max_length=80)
    descripcion: str | None = Field(default=None, max_length=500)


class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: ModelType
    fuente: TrainingSource
    epocas: int | None = Field(default=None, ge=1, le=50, description="Por defecto, las de la receta.")
    semilla: int = Field(default=42, ge=0, le=2**31 - 1)
    dispositivo: Literal["cuda", "cpu"] | None = Field(
        default=None, description="cuda (GPU) o cpu (procesador). Por defecto, la GPU si hay CUDA.")
    pliegues: bool = Field(
        default=True, description="Preparar para calibrar (activo por defecto, como en el panel): "
                                  "entrena también F1–F3 y guarda sus predicciones fuera de pliegue.")


class TrainingRecipe(BaseModel):
    configuracion: str | None = None
    origen: Literal["desplegado", "produccion"]
    modelo: str | None = Field(default=None, description="Modelo desplegado del que sale la receta.")
    ruta: str | None = None
    epocas: int | None = None
    brazo: list[str] = Field(default_factory=list)
    max_tokens: int | None = None
    modelo_base: str | None = None
    parametros: dict = Field(default_factory=dict)


class TrainingJob(BaseModel):
    id: str
    tipo: ModelType
    fuente: dict
    receta: TrainingRecipe
    epocas: int
    semilla: int
    dispositivo: Literal["cuda", "cpu"]
    version: str = Field(description="Versión del modelo que se crea (no sobrescribe ninguno).")
    salida: str | None = None
    inicio: datetime
    fin: datetime | None = None
    por: str | None = None
    datos: dict = Field(default_factory=dict, description="Fragmentos de entrenamiento y prueba.")
    estado: Literal["en_curso", "completado", "fallido", "cancelado"]
    fase: str | None = None
    progreso: float = Field(ge=0, le=1)
    epoca: int | None = None
    epocas_corrida: int | None = Field(default=None, description="Épocas máximas de la corrida en curso.")
    lote: int | None = None
    lotes: int | None = None
    pliegues: bool = False
    corrida: int | None = None
    corridas: int | None = None
    corrida_nombre: str | None = Field(default=None, description="F1, F2, F3 o final.")
    perdidas: list[dict] = Field(default_factory=list)
    error: str | None = None
    metricas: MetricsResponse | None = None
    registro: list[str] = Field(default_factory=list, description="Últimas líneas del registro.")


class TrainingList(BaseModel):
    activo: TrainingJob | None = None
    entrenamientos: list[TrainingJob]


class TrainingOptions(BaseModel):
    tipos: dict[str, TrainingRecipe | None]
    errores_receta: dict[str, str] = Field(default_factory=dict)
    fuentes: list[dict]
    cuda: bool
    salida: str


# ── Calibración ─────────────────────────────────────────────────────


class CalibrationTemperatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bilstm: float | None = Field(default=None, gt=0, le=100, description="A mano; null = ajustada.")
    mbert: float | None = Field(default=None, gt=0, le=100, description="A mano; null = ajustada.")


class CalibrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bilstm: str = Field(min_length=1, max_length=200, description="Id del BiLSTM en el catálogo.")
    mbert: str = Field(min_length=1, max_length=200, description="Id del BETO / mBERT en el catálogo.")
    peso_bilstm: float = Field(default=0.2, ge=0, le=1)
    temperaturas: CalibrationTemperatures = Field(default_factory=CalibrationTemperatures)
    motivo: str | None = Field(default=None, max_length=2000)
