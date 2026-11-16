"""Punto de entrada y composición de la API local de ScanTrue."""

from contextlib import asynccontextmanager, suppress
import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.admin_routes import router as admin_router
from backend.api.history_routes import router as history_router
from backend.api.blockchain_routes import router as blockchain_router
from backend.api.identity_routes import router as identity_router
from backend.api.metrics_routes import router as metrics_router
from backend.api.public_routes import router as public_router
from backend.api.routes import router as analysis_router
from backend.blockchain.client import RegistryClient
from backend.blockchain.worker import BlockchainWorker
from backend.core.config import (
    AnalysisSettings,
    BlockchainSettings,
    LlmSettings,
    SupabaseSettings,
    VerificationSettings,
    web_origins,
)
from backend.repositories.supabase import SupabaseDataError, SupabaseRepository
from backend.services.identity import (
    AuthOperationError,
    IdentityService,
    InvalidSessionError,
    SupabaseAuthUnavailable,
)
from backend.services.llm_status import LlmProbe
from backend.services.model_registry import ModelDeploymentManager
from backend.services.training import TrainingManager
from backend.services.verification.case import build_case_verifier
from backend.services.verification.worker import VerificationWorker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = SupabaseSettings.from_environment()
    repository = SupabaseRepository(settings) if settings else None
    app.state.identity_service = (
        IdentityService(settings, repository) if settings and repository else None
    )
    try:
        blockchain_settings = BlockchainSettings.from_environment()
        app.state.blockchain_client = (
            RegistryClient(blockchain_settings) if blockchain_settings else None
        )
    except Exception:
        logger.exception("La configuración de blockchain no es válida")
        app.state.blockchain_client = None
    worker_task = None
    if repository and settings.secret_key and app.state.blockchain_client:
        worker_task = asyncio.create_task(
            BlockchainWorker(repository, app.state.blockchain_client).run()
        )
    # Estado del LLM para /salud y el panel (incremento 2); sin LLM_BASE_URL queda «no configurado».
    try:
        app.state.llm_probe = LlmProbe(LlmSettings.from_environment())
    except ValueError:
        logger.exception("La configuración del LLM no es válida")
        app.state.llm_probe = LlmProbe(None)
    # Cola de verificación web (incremento 2): apagada salvo VERIFICATION_ENABLED=true.
    try:
        verification_settings = VerificationSettings.from_environment()
    except ValueError:
        logger.exception("La configuración de la verificación no es válida; queda apagada")
        verification_settings = None
    app.state.verification_settings = verification_settings
    verification_task = None
    app.state.verification_worker = None
    if verification_settings and verification_settings.enabled:
        if repository and settings.secret_key:
            verifier = build_case_verifier(repository, verification_settings)
            if verifier is not None:
                worker = VerificationWorker(repository, verification_settings, process=verifier)
                app.state.verification_worker = worker  # el panel (Fase 6) lo pausa y reanuda
                verification_task = asyncio.create_task(worker.run())
        else:
            logger.error("VERIFICATION_ENABLED requiere SUPABASE_SECRET_KEY; la cola no arranca")
    # Los modelos desplegados (uno por tipo, backend/services/model_registry.py) se cargan
    # una vez; si uno falla, el servicio sigue con el otro. El panel los cambia sin reiniciar.
    def swap_service(service) -> None:
        app.state.analysis_service = service

    versions = ModelDeploymentManager(on_swap=swap_service)
    app.state.model_versions = versions
    # Entrenamientos del panel: lanzan un proceso aparte y nunca tocan lo desplegado.
    app.state.training = TrainingManager()
    try:
        AnalysisSettings.from_environment()
        app.state.analysis_service = await asyncio.to_thread(versions.start)
        if app.state.analysis_service is None:
            logger.error("No se pudo iniciar el servicio de análisis")
    except Exception:
        logger.exception("No se pudo iniciar el servicio de análisis")
        app.state.analysis_service = None
    try:
        yield
    finally:
        for task in (worker_task, verification_task):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


app = FastAPI(
    title="ScanTrue API",
    description="API local para clasificar textos con los modelos disponibles.",
    version="0.8.0",
    lifespan=lifespan,
)
app.include_router(analysis_router)
app.include_router(identity_router)
app.include_router(history_router)
app.include_router(metrics_router)
app.include_router(blockchain_router)
app.include_router(public_router)
app.include_router(admin_router)
# La web (web/) llama a la API desde el navegador; la extensión usa sus permisos de host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=web_origins(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(InvalidSessionError)
async def invalid_session_handler(_request: Request, error: InvalidSessionError):
    return JSONResponse(
        status_code=401,
        content={"detail": {"codigo": "sesion_invalida", "mensaje": str(error)}},
    )


@app.exception_handler(AuthOperationError)
async def auth_operation_handler(_request: Request, error: AuthOperationError):
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"codigo": error.code, "mensaje": str(error)}},
    )


@app.exception_handler(SupabaseAuthUnavailable)
async def auth_unavailable_handler(_request: Request, error: SupabaseAuthUnavailable):
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "codigo": "supabase_auth_no_disponible",
                "mensaje": str(error),
                "reintentar": True,
            }
        },
    )


@app.exception_handler(SupabaseDataError)
async def supabase_data_handler(_request: Request, error: SupabaseDataError):
    status = (
        401
        if error.status_code == 401
        else 502 if error.status_code is not None and error.status_code < 500 else 503
    )
    return JSONResponse(
        status_code=status,
        content={
            "detail": {
                "codigo": (
                    "sesion_invalida"
                    if status == 401
                    else "supabase_rechazo_operacion" if status == 502 else "supabase_no_disponible"
                ),
                "mensaje": "No se pudo completar la operación de historial.",
                "reintentar": status == 503,
            }
        },
    )
