"""Web pública: resultados de todos los análisis, sin sesión y sin datos de usuario."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.blockchain_routes import verification_for
from backend.api.dependencies import service_repository
from backend.repositories.filters import MAX_QUERY_LENGTH, AnalysisFilters
from backend.repositories.supabase import SupabaseRepository
from backend.schemas.blockchain import VerificationResponse
from backend.schemas.public import PublicAnalysisDetail, PublicAnalysisPage, PublicSummary


router = APIRouter(prefix="/publico")

Comparison = Literal["coinciden", "discrepan", "no_disponible"]
Verification = Literal[
    "sin_verificar", "respaldada", "contradicha", "fuera_de_contexto", "evidencia_insuficiente"
]
PublicOrder = Literal["recientes", "antiguos", "mas_falsa", "menos_falsa"]


@router.get("/analisis", response_model=PublicAnalysisPage)
def list_public_analysis(
    q: str | None = Query(default=None, max_length=MAX_QUERY_LENGTH * 2),
    nivel: int | None = Query(default=None, ge=1, le=5),
    comparacion: Comparison | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    dominio: str | None = Query(default=None, max_length=253),
    verificacion: Verification | None = None,
    orden: PublicOrder = "recientes",
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    repository: SupabaseRepository = Depends(service_repository),
) -> PublicAnalysisPage:
    filters = AnalysisFilters(
        q=q, nivel=nivel, comparacion=comparacion, desde=desde, hasta=hasta,
        dominio=dominio, verificacion=verificacion, orden=orden,
    )
    return repository.list_public_analysis(filters, limit, offset)


@router.get("/resumen", response_model=PublicSummary)
def public_summary(
    repository: SupabaseRepository = Depends(service_repository),
) -> PublicSummary:
    return repository.public_summary()


@router.get("/analisis/{analysis_id}", response_model=PublicAnalysisDetail)
def get_public_analysis(
    analysis_id: UUID,
    repository: SupabaseRepository = Depends(service_repository),
) -> PublicAnalysisDetail:
    record = repository.get_public_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    return record


@router.get("/analisis/{analysis_id}/verificacion", response_model=VerificationResponse)
def verify_public_analysis(
    analysis_id: UUID,
    request: Request,
    repository: SupabaseRepository = Depends(service_repository),
) -> VerificationResponse:
    """Comprueba en la cadena el registro de un análisis visible en la web."""
    if repository.get_public_analysis(analysis_id) is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    record = repository.get_blockchain_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    return verification_for(record, getattr(request.app.state, "blockchain_client", None))
