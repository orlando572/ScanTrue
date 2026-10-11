"""Análisis autenticado y estado de los servicios."""

from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.dependencies import bearer_token, history_repository, identity_service
from backend.repositories.supabase import SupabaseRepository
from backend.schemas.analysis import AnalysisRequest
from backend.schemas.history import CreatedAnalysis
from backend.services.analysis import (
    AnalysisService,
    InvalidAnalysisInput,
    ModelUnavailableError,
)
from backend.services.identity import IdentityService

router = APIRouter()


@router.get("/salud")
def health(request: Request) -> dict:
    service = getattr(request.app.state, "analysis_service", None)
    identity = getattr(request.app.state, "identity_service", None)
    blockchain = getattr(request.app.state, "blockchain_client", None)
    available = service is not None
    chain_available = False
    if blockchain is not None:
        try:
            blockchain.check_ready()
            chain_available = True
        except Exception:
            pass
    return {
        "estado": (
            "ok"
            if available and identity is not None and identity.settings.secret_key
            and chain_available
            else "degradado"
        ),
        "modelos": {
            "bilstm": available,
            "mbert": available and service.mbert_predictor is not None,
        },
        "supabase_configurado": identity is not None,
        "transferencia_configurada": bool(
            identity and identity.settings.secret_key
        ),
        "blockchain": {"configurada": blockchain is not None, "conectada": chain_available},
    }


@router.post("/analisis", response_model=CreatedAnalysis)
def analyze(
    payload: AnalysisRequest,
    request: Request,
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
    repository: SupabaseRepository = Depends(history_repository),
) -> CreatedAnalysis:
    service: AnalysisService | None = getattr(
        request.app.state, "analysis_service", None
    )
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "modelo_no_disponible",
                "mensaje": "No hay modelos disponibles para analizar el texto.",
                "reintentar": True,
            },
        )
    user = identity.verify_user(token)
    try:
        outcome = service.analyze(payload)
    except InvalidAnalysisInput as error:
        raise HTTPException(
            status_code=422,
            detail={
                "codigo": error.code,
                "mensaje": str(error),
                "como_corregir": error.suggestion,
            },
        ) from error
    except ModelUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "fallo_inferencia",
                "mensaje": str(error),
                "reintentar": True,
            },
        ) from error
    analysis_id = repository.create_analysis(
        user_id=UUID(user.id),
        title=(payload.titulo or "").strip() or None,
        url=(payload.url or "").strip() or None,
        text=outcome.text,
        text_hash=sha256(outcome.text.encode("utf-8")).hexdigest(),
        response=outcome.response,
    )
    return CreatedAnalysis(
        **outcome.response.model_dump(), id=analysis_id,
        texto_recortado=outcome.truncated,
    )
