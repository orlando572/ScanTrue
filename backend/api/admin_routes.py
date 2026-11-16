"""Panel de administración: resumen, casos y revisión, datasets y versiones de modelos."""

import asyncio
from datetime import date
import os
import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from backend.api.dependencies import admin_user, service_repository
from backend.repositories.filters import MAX_QUERY_LENGTH, AnalysisFilters
from backend.repositories.supabase import SupabaseDataError, SupabaseRepository
from backend.schemas.admin import (
    AdminCaseDetail,
    AdminCasePage,
    AdminIdentity,
    AdminSummary,
    CaseStandardPreview,
    DatasetCreate,
    DatasetDetail,
    DatasetSummary,
    DatasetVersion,
    DeploymentHistoryEntry,
    DeployRequest,
    ModelEntryInfo,
    ModelsResponse,
    RetireRequest,
    Review,
    ReviewRequest,
    VisibilityUpdate,
    Weights,
)
from backend.services.datasets import (
    LegacyVersionError, build_dataset, build_manifest, comun_index, export_csv,
    export_standard_zip, preview_case,
)
from backend.services.model_registry import (
    MAX_ZIP_BYTES, TYPES, ModelDeploymentManager, ModelVersionError, default_weights,
)


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
        update={"despliegue_activo": versions.summary() if versions is not None else None}
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


@router.get("/casos/{analysis_id}/estandar", response_model=CaseStandardPreview)
def get_case_standard(
    analysis_id: UUID,
    repository: SupabaseRepository = Depends(service_repository),
) -> CaseStandardPreview:
    """Cómo entraría el caso a una versión de dataset (no guarda nada)."""
    case = _case(repository, analysis_id)
    text = (case.texto_original or case.texto or "").strip()
    return preview_case(text, case.fragmentos, comun_index())


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
    return build_dataset(repository.reviewed_cases(), fraccion_prueba, comun_index()).summary


@router.post("/datasets", response_model=DatasetVersion, status_code=201)
def create_dataset(
    payload: DatasetCreate,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> DatasetVersion:
    build = build_dataset(repository.reviewed_cases(), payload.fraccion_prueba, comun_index())
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
            build_manifest(build),
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
    formato: Literal["completo", "estandar"] = Query(
        default="completo",
        description="completo: un CSV con toda la procedencia. estandar: ZIP para entrenar "
                    "con los CSV de comun_v1 y manifest.json."),
    repository: SupabaseRepository = Depends(service_repository),
) -> Response:
    version = _dataset(repository, version_id)
    items, _ = repository.dataset_items(version_id)
    filename = "".join(
        character if character.isascii() and (character.isalnum() or character in "-_.") else "_"
        for character in version.nombre
    ).strip("_") or "dataset"
    if formato == "estandar":
        try:
            content = export_standard_zip(version.model_dump(), items)
        except LegacyVersionError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "codigo": "version_anterior_al_estandar",
                    "mensaje": "Esta versión se creó antes del estándar de fragmentos: "
                               "crea una nueva para exportarla para entrenar.",
                },
            ) from error
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="scantrue_{filename}.zip"'},
        )
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


# ── Modelos desplegados ─────────────────────────────────────────────


def _versions(request: Request) -> ModelDeploymentManager:
    manager = getattr(request.app.state, "model_versions", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "versiones_no_disponibles",
                "mensaje": "El gestor de modelos no está disponible.",
            },
        )
    return manager


def _models(request: Request, repository: SupabaseRepository) -> ModelsResponse:
    manager = _versions(request)
    try:
        usage = repository.model_version_usage()
    except SupabaseDataError:
        usage = {}
    deployed = manager.state.deployed
    groups: dict[str, list[ModelEntryInfo]] = {tipo: [] for tipo in TYPES}
    for entry in manager.catalog.entries():
        groups[entry.tipo].append(ModelEntryInfo(
            id=entry.id, tipo=entry.tipo, version=entry.version, nombre=entry.nombre,
            fecha=entry.fecha, origen=entry.origen, ruta=entry.ruta, estado=entry.estado,
            motivo=entry.motivo, notas=entry.notas, temperatura=entry.temperatura,
            max_tokens=entry.max_tokens,
            desplegado=deployed.get(entry.tipo) == entry.id,
            cargado=deployed.get(entry.tipo) == entry.id and entry.tipo in manager.loaded,
            casos=usage.get((entry.tipo, entry.version), 0),
            metricas=entry.load_metrics(),
        ))
    service = getattr(request.app.state, "analysis_service", None)
    combination = getattr(service, "combination", None)
    history = []
    for item in manager.history():
        try:
            history.append(DeploymentHistoryEntry(**item))
        except Exception:
            continue  # una entrada antigua o editada a mano no rompe el panel
    return ModelsResponse(
        desplegados=dict(deployed),
        cargados=sorted(manager.loaded),
        pesos=Weights(**manager.state.weights),
        pesos_calibrados=Weights(**default_weights()),
        combinacion=getattr(combination, "version", None),
        anterior=manager.previous_state(),
        modelos=groups,
        historial=history,
    )


async def _change(action) -> None:
    """Cargar y comprobar modelos tarda: se hace fuera del bucle de eventos."""
    try:
        await asyncio.to_thread(action)
    except ModelVersionError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"codigo": error.code, "mensaje": str(error)},
        ) from error


@router.get("/modelos", response_model=ModelsResponse)
async def list_models(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    return await asyncio.to_thread(_models, request, repository)


@router.post("/modelos/desplegar", response_model=ModelsResponse)
async def deploy_model(
    payload: DeployRequest,
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    """Carga y comprueba el modelo; solo si responde bien sustituye al de su tipo."""
    manager = _versions(request)
    await _change(lambda: manager.deploy(payload.tipo, payload.id, user.email))
    return await asyncio.to_thread(_models, request, repository)


@router.post("/modelos/retirar", response_model=ModelsResponse)
async def retire_model(
    payload: RetireRequest,
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    manager = _versions(request)
    await _change(lambda: manager.retire(payload.tipo, user.email))
    return await asyncio.to_thread(_models, request, repository)


@router.put("/modelos/pesos", response_model=ModelsResponse)
async def update_weights(
    payload: Weights,
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    manager = _versions(request)
    await _change(lambda: manager.set_weights(payload.model_dump(), user.email))
    return await asyncio.to_thread(_models, request, repository)


@router.post("/modelos/revertir", response_model=ModelsResponse)
async def revert_models(
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    manager = _versions(request)
    await _change(lambda: manager.revert(user.email))
    return await asyncio.to_thread(_models, request, repository)


@router.post("/modelos/importar", response_model=ModelsResponse)
async def import_model(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    """Recibe un ZIP (cuerpo crudo) con contrato.json, pesos y, opcional, metricas.json."""
    manager = _versions(request)
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_ZIP_BYTES:
        raise HTTPException(413, detail={"codigo": "zip_demasiado_grande",
                                         "mensaje": "El ZIP supera 2 GB."})
    staging = manager.catalog.imports_dir / ".importando"
    await asyncio.to_thread(staging.mkdir, parents=True, exist_ok=True)
    path = staging / f"{uuid.uuid4().hex}.zip"
    try:
        size = 0
        with path.open("wb") as sink:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    raise HTTPException(413, detail={"codigo": "zip_demasiado_grande",
                                                     "mensaje": "El ZIP supera 2 GB."})
                await asyncio.to_thread(sink.write, chunk)
        if size == 0:
            raise HTTPException(400, detail={"codigo": "zip_vacio",
                                             "mensaje": "No llegó ningún archivo."})
        await _change(lambda: manager.catalog.import_zip(path))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return await asyncio.to_thread(_models, request, repository)


@router.delete("/modelos/{tipo}/{model_id}", response_model=ModelsResponse)
async def delete_model(
    tipo: Literal["bilstm", "mbert"],
    model_id: str,
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    """Borra un modelo importado que no esté desplegado (los del entrenamiento no se tocan)."""
    manager = _versions(request)
    await _change(lambda: manager.delete(tipo, model_id))
    return await asyncio.to_thread(_models, request, repository)
