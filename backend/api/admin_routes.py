"""Panel de administración: resumen, casos y revisión, datasets y versiones de modelos."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from backend.api.dependencies import admin_user, service_repository
from backend.repositories.filters import MAX_QUERY_LENGTH, AnalysisFilters
from backend.repositories.supabase import SupabaseDataError, SupabaseRepository
from backend.schemas.admin import (
    ActivationEntry,
    ActivationRequest,
    AdminCaseDetail,
    AdminCasePage,
    AdminIdentity,
    AdminSummary,
    DatasetCreate,
    DatasetDetail,
    DatasetSummary,
    DatasetVersion,
    DeploymentInfo,
    DeploymentModel,
    ModelsResponse,
    Review,
    ReviewRequest,
    VisibilityUpdate,
)
from backend.services.datasets import build_dataset, export_csv
from backend.services.model_versions import MODELS, ModelVersionError, ModelVersionManager


router = APIRouter(prefix="/admin", dependencies=[Depends(admin_user)])

NOT_FOUND = "Análisis no encontrado."


@router.get("/yo", response_model=AdminIdentity)
def who_am_i(user=Depends(admin_user)) -> AdminIdentity:
    return AdminIdentity(usuario_id=user.id, correo=user.email, rol="admin")


@router.get("/resumen", response_model=AdminSummary)
def summary(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminSummary:
    data = repository.admin_summary()
    versions = getattr(request.app.state, "model_versions", None)
    return data.model_copy(
        update={"despliegue_activo": getattr(versions, "current_version", None)}
    )


# ── Casos y revisión ────────────────────────────────────────────────


@router.get("/casos", response_model=AdminCasePage)
def list_cases(
    q: str | None = Query(default=None, max_length=MAX_QUERY_LENGTH * 2),
    nivel: int | None = Query(default=None, ge=1, le=5),
    comparacion: Literal["coinciden", "discrepan", "no_disponible"] | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    dominio: str | None = Query(default=None, max_length=253),
    visibilidad: Literal["todos", "visibles", "ocultos"] = "todos",
    revision: Literal[
        "todos", "pendiente", "revisado", "aprobado", "corregido", "descartado"
    ] = "todos",
    orden: Literal["prioridad", "recientes", "antiguos", "mas_falsa", "menos_falsa"] = "prioridad",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminCasePage:
    filters = AnalysisFilters(
        q=q, nivel=nivel, comparacion=comparacion, desde=desde, hasta=hasta, dominio=dominio,
        oculto={"todos": None, "visibles": False, "ocultos": True}[visibilidad],
        revision=None if revision == "todos" else revision,
        orden=orden,
    )
    return repository.list_admin_cases(filters, limit, offset)


def _case(repository: SupabaseRepository, analysis_id: UUID) -> AdminCaseDetail:
    record = repository.get_admin_case(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return record


@router.get("/casos/{analysis_id}", response_model=AdminCaseDetail)
def get_case(
    analysis_id: UUID,
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminCaseDetail:
    return _case(repository, analysis_id)


@router.patch("/casos/{analysis_id}", response_model=AdminCaseDetail)
def update_visibility(
    analysis_id: UUID,
    payload: VisibilityUpdate,
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminCaseDetail:
    if not repository.set_hidden(analysis_id, payload.oculto):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return _case(repository, analysis_id)


@router.put("/casos/{analysis_id}/revision", response_model=AdminCaseDetail)
def review_case(
    analysis_id: UUID,
    payload: ReviewRequest,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminCaseDetail:
    """Aprueba la etiqueta del modelo, la corrige o descarta el caso."""
    case = _case(repository, analysis_id)
    if payload.decision == "descartado":
        label = None
    elif payload.decision == "aprobado":
        label = case.etiqueta_modelo
        if label is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "codigo": "sin_resultado_que_aprobar",
                    "mensaje": "Este caso no tiene resultado unificado; corrígelo o descártalo.",
                },
            )
    else:
        label = payload.etiqueta_final
    evidence = [item.strip() for item in payload.evidencia if item.strip()]
    repository.save_review(
        analysis_id,
        UUID(str(user.id)),
        Review(
            decision=payload.decision,
            etiqueta_final=label,
            nota=(payload.nota or "").strip() or None,
            evidencia=evidence,
            grupo_evento=" ".join((payload.grupo_evento or "").split()) or None,
        ),
    )
    return _case(repository, analysis_id)


@router.delete("/casos/{analysis_id}/revision", response_model=AdminCaseDetail)
def clear_review(
    analysis_id: UUID,
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminCaseDetail:
    """Devuelve el caso a «pendiente de revisión»."""
    repository.delete_review(analysis_id)
    return _case(repository, analysis_id)


# ── Versiones de dataset ────────────────────────────────────────────


@router.get("/datasets", response_model=list[DatasetVersion])
def list_datasets(
    repository: SupabaseRepository = Depends(service_repository),
) -> list[DatasetVersion]:
    return repository.list_dataset_versions()


@router.get("/datasets/vista-previa", response_model=DatasetSummary)
def preview_dataset(
    fraccion_prueba: float = Query(default=0.2, ge=0.05, le=0.5),
    repository: SupabaseRepository = Depends(service_repository),
) -> DatasetSummary:
    """Qué entraría hoy en una versión nueva, sin guardarla."""
    return build_dataset(repository.reviewed_cases(), fraccion_prueba).summary


@router.post("/datasets", response_model=DatasetVersion, status_code=201)
def create_dataset(
    payload: DatasetCreate,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> DatasetVersion:
    build = build_dataset(repository.reviewed_cases(), payload.fraccion_prueba)
    if not build.items:
        raise HTTPException(
            status_code=409,
            detail={
                "codigo": "sin_casos_aprobados",
                "mensaje": "Todavía no hay casos aprobados o corregidos para una versión.",
            },
        )
    name = " ".join(payload.nombre.split())
    try:
        version_id = repository.create_dataset_version(
            name,
            (payload.descripcion or "").strip() or None,
            UUID(str(user.id)),
            build.summary.model_dump(),
            [item.model_dump(mode="json", exclude={"id"}) for item in build.items],
        )
    except SupabaseDataError as error:
        if error.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail={
                    "codigo": "nombre_repetido",
                    "mensaje": "Ya existe una versión con ese nombre.",
                },
            ) from error
        raise
    version = repository.get_dataset_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Versión no encontrada.")
    return version


def _dataset(repository: SupabaseRepository, version_id: UUID) -> DatasetVersion:
    version = repository.get_dataset_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Versión no encontrada.")
    return version


@router.get("/datasets/{version_id}", response_model=DatasetDetail)
def get_dataset(
    version_id: UUID,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: SupabaseRepository = Depends(service_repository),
) -> DatasetDetail:
    version = _dataset(repository, version_id)
    items, total = repository.dataset_items(version_id, limit, offset)
    return DatasetDetail(**version.model_dump(), elementos=items, total=total)


@router.get("/datasets/{version_id}/exportar")
def export_dataset(
    version_id: UUID,
    repository: SupabaseRepository = Depends(service_repository),
) -> Response:
    version = _dataset(repository, version_id)
    items, _ = repository.dataset_items(version_id)
    filename = "".join(
        character if character.isascii() and (character.isalnum() or character in "-_.") else "_"
        for character in version.nombre
    ).strip("_") or "dataset"
    return Response(
        content=export_csv(items),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="scantrue_{filename}.csv"'},
    )


@router.delete("/datasets/{version_id}")
def delete_dataset(
    version_id: UUID,
    repository: SupabaseRepository = Depends(service_repository),
) -> dict[str, bool]:
    if not repository.delete_dataset_version(version_id):
        raise HTTPException(status_code=404, detail="Versión no encontrada.")
    return {"eliminado": True}


# ── Versiones de modelos ────────────────────────────────────────────


def _versions(request: Request) -> ModelVersionManager:
    manager = getattr(request.app.state, "model_versions", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "versiones_no_disponibles",
                "mensaje": "El gestor de versiones de modelos no está disponible.",
            },
        )
    return manager


def _models(manager: ModelVersionManager, repository: SupabaseRepository) -> ModelsResponse:
    try:
        usage = repository.model_version_usage()
    except SupabaseDataError:
        usage = {}
    versions = []
    for deployment in manager.deployments():
        combination = deployment.load_combination()
        versions.append(
            DeploymentInfo(
                version=deployment.version,
                nombre=deployment.name,
                fecha=deployment.date,
                notas=deployment.notes,
                activable=deployment.activable,
                activa=deployment.version == manager.current_version,
                pesos=combination.weights if combination else None,
                temperaturas=combination.temperatures if combination else None,
                modelos=[
                    DeploymentModel(
                        modelo=name,
                        version=deployment.model_versions.get(name),
                        casos=usage.get((name, deployment.model_versions.get(name)), 0),
                        metricas=deployment.load_metrics(name),
                    )
                    for name in MODELS
                ],
            )
        )
    return ModelsResponse(
        activa=manager.current_version,
        anterior=manager.previous_version(),
        versiones=versions,
        historial=[ActivationEntry(**entry) for entry in manager.history()],
    )


def _change(action) -> None:
    try:
        action()
    except ModelVersionError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"codigo": error.code, "mensaje": str(error)},
        ) from error


@router.get("/modelos", response_model=ModelsResponse)
def list_models(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    return _models(_versions(request), repository)


@router.post("/modelos/activar", response_model=ModelsResponse)
def activate_model_version(
    payload: ActivationRequest,
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    """Carga y comprueba la versión; solo si responde bien sustituye a la activa."""
    manager = _versions(request)
    _change(lambda: manager.activate(payload.version, user.email))
    return _models(manager, repository)


@router.post("/modelos/revertir", response_model=ModelsResponse)
def revert_model_version(
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    manager = _versions(request)
    _change(lambda: manager.revert(user.email))
    return _models(manager, repository)
