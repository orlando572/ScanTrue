"""Punto de entrada y composición de la API local de ScanTrue."""

from contextlib import asynccontextmanager, suppress
import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.api.history_routes import router as history_router
from backend.api.blockchain_routes import router as blockchain_router
from backend.api.identity_routes import router as identity_router
from backend.api.metrics_routes import router as metrics_router
from backend.api.routes import router as analysis_router
from backend.blockchain.client import RegistryClient
from backend.blockchain.worker import BlockchainWorker
from backend.core.config import AnalysisSettings, BlockchainSettings, SupabaseSettings
from backend.models.bilstm import BilstmPredictor
from backend.models.mbert import MbertPredictor, MbertTokenizer
from backend.repositories.supabase import SupabaseDataError, SupabaseRepository
from backend.services.analysis import AnalysisService
from backend.services.identity import (
    AuthOperationError,
    IdentityService,
    InvalidSessionError,
    SupabaseAuthUnavailable,
)

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
    # Cada modelo se carga una vez y puede degradarse de forma independiente.
    try:
        analysis_settings = AnalysisSettings.from_environment()
        bilstm_predictor = BilstmPredictor()
        try:
            mbert_text_policy = MbertTokenizer()
        except Exception:
            logger.exception("No se pudo cargar el tokenizador mBERT")
            mbert_text_policy = None
        try:
            mbert_predictor = (
                MbertPredictor(mbert_text_policy) if mbert_text_policy else None
            )
        except Exception:
            logger.exception("No se pudo cargar el checkpoint mBERT")
            mbert_predictor = None
        app.state.analysis_service = AnalysisService(
            bilstm_predictor,
            mbert_predictor=mbert_predictor,
            mbert_text_policy=mbert_text_policy,
            mbert_weight=analysis_settings.mbert_weight,
        )
    except Exception:
        logger.exception("No se pudo iniciar el servicio de análisis")
        app.state.analysis_service = None
    try:
        yield
    finally:
        if worker_task:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task


app = FastAPI(
    title="ScanTrue API",
    description="API local para clasificar textos con los modelos disponibles.",
    version="0.7.0",
    lifespan=lifespan,
)
app.include_router(analysis_router)
app.include_router(identity_router)
app.include_router(history_router)
app.include_router(metrics_router)
app.include_router(blockchain_router)


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
