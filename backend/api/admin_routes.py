"""Panel de administración: resumen, casos y revisión, datasets, modelos y entrenamiento."""

import asyncio
from datetime import date
import json
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
    CalibrationRequest,
    CombinedSetCreate,
    CombinedSetPreview,
    CaseStandardPreview,
    DatasetCreate,
    DatasetDetail,
    DatasetSummary,
    DatasetVersion,
    LlmStatus,
    DeployCalibrationRequest,
    DeploymentHistoryEntry,
    DeployRequest,
    ModelEntryInfo,
    ModelsResponse,
    RetireRequest,
    Review,
    ReviewRequest,
    VerificationStatus,
    TrainingJob,
    TrainingList,
    TrainingOptions,
    TrainingRequest,
    VisibilityUpdate,
    Weights,
)
from backend.services.datasets import (
    LegacyVersionError, build_dataset, build_manifest, comun_index, export_csv,
    export_standard_zip, preview_case, standard_csvs,
)
from backend.services.model_registry import (
    MAX_ZIP_BYTES, TYPES, ModelDeploymentManager, ModelVersionError, calibration_for, default_weights,
)
from backend.services.calibration import CalibrationError, CalibrationManager
from backend.services.combined_sets import CombinedSetError, CombinedSetManager, PanelSource
from backend.services.training import OUTPUT_DIR, TrainingError, TrainingManager


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
    verificacion: Literal[
        "sin_verificar", "respaldada", "contradicha", "fuera_de_contexto", "evidencia_insuficiente",
        "pendiente", "en_proceso", "fallida",
    ] | None = None,
    orden: Literal["prioridad", "recientes", "antiguos", "mas_falsa", "menos_falsa"] = "prioridad",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminCasePage:
    filters = AnalysisFilters(
        q=q, nivel=nivel, comparacion=comparacion, desde=desde, hasta=hasta, dominio=dominio,
        oculto={"todos": None, "visibles": False, "ocultos": True}[visibilidad],
        revision=None if revision == "todos" else revision,
        verificacion=verificacion,
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


# ── Verificación web (incremento 2) ─────────────────────────────────


def _verification_status(request: Request, repository: SupabaseRepository) -> VerificationStatus:
    worker = getattr(request.app.state, "verification_worker", None)
    probe = getattr(request.app.state, "llm_probe", None)
    llm = probe.status() if probe is not None else None
    stats = repository.verification_stats()
    return VerificationStatus(
        habilitada=worker is not None,
        en_pausa=bool(worker is not None and worker.paused),
        llm=LlmStatus(
            configurado=bool(llm and llm.configurado), disponible=bool(llm and llm.disponible)
        ),
        pendientes=stats["pendiente"],
        en_proceso=stats["en_proceso"],
        fallidas=stats["fallida"],
        completadas=stats["completada"],
        duracion_media_segundos=stats["duracion_media_segundos"],
    )


def _worker(request: Request):
    worker = getattr(request.app.state, "verification_worker", None)
    if worker is None:
        raise HTTPException(
            status_code=409,
            detail={
                "codigo": "verificacion_apagada",
                "mensaje": "La verificación no está encendida en este servidor (VERIFICATION_ENABLED).",
            },
        )
    return worker


@router.get("/verificacion", response_model=VerificationStatus)
def verification_status(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> VerificationStatus:
    return _verification_status(request, repository)


@router.post("/verificacion/pausar", response_model=VerificationStatus)
def pause_verification(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> VerificationStatus:
    """El trabajador deja de reclamar casos (el que está en proceso termina); la cola se conserva."""
    _worker(request).pause()
    return _verification_status(request, repository)


@router.post("/verificacion/reanudar", response_model=VerificationStatus)
def resume_verification(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> VerificationStatus:
    _worker(request).resume()
    return _verification_status(request, repository)


@router.post("/casos/{analysis_id}/verificacion/reintentar", response_model=AdminCaseDetail)
def retry_verification(
    analysis_id: UUID,
    repository: SupabaseRepository = Depends(service_repository),
) -> AdminCaseDetail:
    """Devuelve a la cola una verificación fallida (o en espera de su turno) para intentarla ya."""
    outcome = repository.retry_verification(analysis_id)
    if outcome == "sin_verificacion":
        raise HTTPException(
            status_code=404,
            detail={"codigo": "sin_verificacion", "mensaje": "Este caso no tiene una verificación en la cola."},
        )
    if outcome != "reintentada":
        raise HTTPException(
            status_code=409,
            detail={
                "codigo": "no_se_puede_reintentar",
                "mensaje": f"Solo se reintenta una verificación fallida o en espera; esta está «{outcome}».",
            },
        )
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


# ── Conjuntos combinados ────────────────────────────────────────────
# comun_v1 (sin cambiarlo) + versiones del panel, con balanceo 50/50 opcional de lo añadido. Se
# guardan en datasets/conjuntos/ y se eligen como fuente en Entrenamiento.


def _sets(request: Request) -> CombinedSetManager:
    return _training(request).sets


def _set_error(error: CombinedSetError) -> HTTPException:
    return HTTPException(status_code=error.status_code,
                         detail={"codigo": error.code, "mensaje": str(error)})


def _panel_sources(repository: SupabaseRepository, ids: list[UUID]) -> list[PanelSource]:
    sources = []
    for version_id in dict.fromkeys(ids):  # sin repetir, en el orden elegido
        version = _dataset(repository, version_id)
        items, _ = repository.dataset_items(version.id)
        try:
            files = standard_csvs(items)
        except LegacyVersionError as error:
            raise HTTPException(status_code=409, detail={
                "codigo": "version_anterior_al_estandar",
                "mensaje": f"«{version.nombre}» se creó antes del estándar de fragmentos: crea una versión nueva.",
            }) from error
        sources.append(PanelSource(id=str(version.id), nombre=version.nombre,
                                   fecha=version.fecha.isoformat() if version.fecha else None, files=files))
    return sources


@router.get("/conjuntos")
def list_sets(request: Request) -> list[dict]:
    return _sets(request).list()


@router.post("/conjuntos/vista-previa")
def preview_set(
    payload: CombinedSetPreview,
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> dict:
    """Qué saldría del conjunto, sin guardarlo."""
    sources = _panel_sources(repository, payload.versiones)
    try:
        return _sets(request).preview(sources, payload.incluir_comun, payload.balanceo,
                                      comun_index() if payload.incluir_comun else None)
    except CombinedSetError as error:
        raise _set_error(error) from error


@router.post("/conjuntos", status_code=201)
def create_set(
    payload: CombinedSetCreate,
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> dict:
    sources = _panel_sources(repository, payload.versiones)
    try:
        return _sets(request).create(payload.nombre, payload.descripcion, sources, payload.incluir_comun,
                                     payload.balanceo, comun_index() if payload.incluir_comun else None,
                                     user.email)
    except CombinedSetError as error:
        raise _set_error(error) from error


@router.get("/conjuntos/{version}")
def get_set(version: str, request: Request) -> dict:
    try:
        return _sets(request).get(version)
    except CombinedSetError as error:
        raise _set_error(error) from error


@router.delete("/conjuntos/{version}")
def delete_set(version: str, request: Request) -> dict[str, bool]:
    """Borra el conjunto. Los modelos ya entrenados con él no cambian: guardan su procedencia."""
    try:
        _sets(request).delete(version)
    except CombinedSetError as error:
        raise _set_error(error) from error
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


def calibrated_weights(manager: ModelDeploymentManager) -> dict[str, float]:
    """Pesos de la calibración de la pareja desplegada; si no la hay, los de producción."""
    versions = {tipo: entry.version for tipo, entry in manager.selection().items() if entry is not None}
    combination = calibration_for(versions)
    return dict(combination.weights) if combination else default_weights()


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
        pesos_calibrados=Weights(**calibrated_weights(manager)),
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


@router.post("/modelos/desplegar-calibracion", response_model=ModelsResponse)
async def deploy_calibration(
    payload: DeployCalibrationRequest,
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> ModelsResponse:
    """Despliega la pareja de una calibración con sus pesos, en un solo cambio."""
    manager = _versions(request)
    await _change(lambda: manager.deploy_calibration(payload.version, user.email))
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


# ── Entrenamiento ───────────────────────────────────────────────────
# Solo entrena: el modelo nuevo aparece en Modelos («Pendiente de calibrar»). Desde aquí no se
# despliega, no se borra y no se sobrescribe ningún modelo.


def _training(request: Request) -> TrainingManager:
    manager = getattr(request.app.state, "training", None)
    if manager is None:
        manager = request.app.state.training = TrainingManager()
    return manager


def _training_error(error: TrainingError) -> HTTPException:
    return HTTPException(status_code=error.status_code,
                         detail={"codigo": error.code, "mensaje": str(error)})


def _deployed(request: Request, tipo: str):
    versions = getattr(request.app.state, "model_versions", None)
    if versions is None:
        return None
    try:
        return versions.selection().get(tipo)
    except Exception:
        return None


@router.get("/entrenamientos/opciones", response_model=TrainingOptions)
def training_options(
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> TrainingOptions:
    manager = _training(request)
    recipes, errors = {}, {}
    for tipo in TYPES:
        try:
            recipes[tipo] = manager.recipe(tipo, _deployed(request, tipo)).summary()
        except TrainingError as error:
            recipes[tipo], errors[tipo] = None, str(error)
    sources = []
    comun = manager.comun_source()
    if comun is not None:
        sources.append(comun)
    sources.extend(manager.set_sources())
    try:
        sources.extend(manager.panel_sources(repository.list_dataset_versions()))
    except SupabaseDataError:
        pass
    salida = OUTPUT_DIR.relative_to(OUTPUT_DIR.parents[1]).as_posix()
    return TrainingOptions(tipos=recipes, errores_receta=errors, fuentes=sources,
                           cuda=manager.cuda_available(), salida=salida)


@router.get("/entrenamientos", response_model=TrainingList)
def list_trainings(request: Request) -> TrainingList:
    return TrainingList(**_training(request).overview())


@router.post("/entrenamientos", response_model=TrainingJob, status_code=202)
def start_training(
    payload: TrainingRequest,
    request: Request,
    user=Depends(admin_user),
    repository: SupabaseRepository = Depends(service_repository),
) -> TrainingJob:
    manager = _training(request)

    def panel_version(version_id: str):
        version = _dataset(repository, UUID(version_id))
        items, _ = repository.dataset_items(version.id)
        try:
            files = standard_csvs(items)
        except LegacyVersionError as error:
            raise TrainingError(
                "version_anterior_al_estandar",
                "Esta versión se creó antes del estándar de fragmentos: crea una nueva para "
                "entrenar con ella.", 409) from error
        return version.model_dump(), files

    try:
        recipe = manager.recipe(payload.tipo, _deployed(request, payload.tipo))
        job = manager.start(payload.tipo, payload.fuente.model_dump(mode="json"), recipe,
                            payload.epocas, payload.semilla, user.email, panel_version,
                            payload.dispositivo, payload.pliegues)
    except TrainingError as error:
        raise _training_error(error) from error
    return TrainingJob(**job)


@router.get("/entrenamientos/{job_id}", response_model=TrainingJob)
def get_training(job_id: str, request: Request) -> TrainingJob:
    try:
        return TrainingJob(**_training(request).get(job_id))
    except TrainingError as error:
        raise _training_error(error) from error


@router.post("/entrenamientos/{job_id}/cancelar", response_model=TrainingJob)
def cancel_training(job_id: str, request: Request) -> TrainingJob:
    try:
        return TrainingJob(**_training(request).cancel(job_id))
    except TrainingError as error:
        raise _training_error(error) from error


# ── Calibración ─────────────────────────────────────────────────────
# Calibra una pareja y guarda una versión calibrada nueva (contratos que apuntan a los mismos
# pesos). No toca contratos existentes ni lo desplegado: se despliega desde Modelos.


def _calibration(request: Request) -> CalibrationManager:
    manager = getattr(request.app.state, "calibration", None)
    if manager is None:
        manager = request.app.state.calibration = CalibrationManager(_versions(request).catalog)
    return manager


def _calibration_error(error: CalibrationError) -> HTTPException:
    return HTTPException(status_code=error.status_code,
                         detail={"codigo": error.code, "mensaje": str(error)})


def _deployed_versions(request: Request) -> dict[str, str]:
    versions = getattr(request.app.state, "model_versions", None)
    if versions is None:
        return {}
    return {tipo: entry.version for tipo, entry in versions.selection().items() if entry is not None}


def _calibration_options(request: Request) -> dict:
    manager = _calibration(request)
    candidates = manager.candidates()
    versions = getattr(request.app.state, "model_versions", None)
    deployed = versions.selection() if versions is not None else {}
    defaults = {}
    for tipo in TYPES:
        entry = deployed.get(tipo)
        usable = {item["id"] for item in candidates[tipo] if item["apto"]}
        pick = entry.id if entry is not None and entry.id in usable else None
        if pick is None and entry is not None:  # una variante calibrada: su modelo de origen
            try:
                origin = (json.loads(entry.contrato.read_text("utf-8")).get("calibrado_desde") or {}).get("id")
            except (OSError, ValueError, AttributeError):
                origin = None
            pick = origin if origin in usable else None
        defaults[tipo] = pick or next(iter(sorted(usable)), None)
    reference = manager.reference() or {}
    return {
        "candidatos": candidates,
        "por_defecto": {**defaults, "peso_bilstm": (reference.get("pesos") or {}).get("bilstm", 0.2)},
        "produccion": {key: reference.get(key) for key in ("version", "temperaturas", "pesos", "motivo_pesos",
                                                           "contratos")} if reference else None,
        "vigente": manager.current(_deployed_versions(request)),
        "desplegados": _deployed_versions(request),
    }


@router.get("/calibraciones/opciones")
async def calibration_options(request: Request) -> dict:
    return await asyncio.to_thread(_calibration_options, request)


@router.post("/calibraciones/vista-previa")
async def calibration_preview(payload: CalibrationRequest, request: Request) -> dict:
    """Calcula la calibración sin guardar nada (tarda unos segundos)."""
    manager = _calibration(request)
    try:
        return await asyncio.to_thread(
            manager.preview, payload.bilstm, payload.mbert, payload.peso_bilstm,
            payload.temperaturas.model_dump())
    except CalibrationError as error:
        raise _calibration_error(error) from error


@router.post("/calibraciones", status_code=201)
async def save_calibration(
    payload: CalibrationRequest,
    request: Request,
    user=Depends(admin_user),
) -> dict:
    manager = _calibration(request)
    try:
        return await asyncio.to_thread(
            manager.save, payload.bilstm, payload.mbert, payload.peso_bilstm,
            payload.temperaturas.model_dump(), payload.motivo or "", user.email)
    except CalibrationError as error:
        raise _calibration_error(error) from error


@router.get("/calibraciones")
async def list_calibrations(request: Request) -> dict:
    data = await asyncio.to_thread(_calibration(request).overview)
    return {**data, "vigente": await asyncio.to_thread(_calibration(request).current, _deployed_versions(request))}


@router.get("/calibraciones/{version}")
async def get_calibration(version: str, request: Request) -> dict:
    try:
        return await asyncio.to_thread(_calibration(request).get, version)
    except CalibrationError as error:
        raise _calibration_error(error) from error
