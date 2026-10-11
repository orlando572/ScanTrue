"""Lectura y eliminación del historial propio."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import bearer_token, history_repository, identity_service
from backend.repositories.supabase import SupabaseRepository
from backend.schemas.history import HistoryListRecord, HistoryRecord
from backend.services.identity import IdentityService


router = APIRouter()


@router.get("/analisis", response_model=list[HistoryListRecord])
def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
    repository: SupabaseRepository = Depends(history_repository),
) -> list[HistoryListRecord]:
    user = identity.verify_user(token)
    return repository.list_analysis(token, UUID(user.id), limit, offset)


@router.get("/analisis/{analysis_id}", response_model=HistoryRecord)
def get_history_item(
    analysis_id: UUID,
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
    repository: SupabaseRepository = Depends(history_repository),
) -> HistoryRecord:
    user = identity.verify_user(token)
    record = repository.get_analysis(token, UUID(user.id), analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    return record


@router.delete("/analisis/{analysis_id}")
def delete_history_item(
    analysis_id: UUID,
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
    repository: SupabaseRepository = Depends(history_repository),
) -> dict[str, bool]:
    user = identity.verify_user(token)
    if not repository.delete_analysis(token, UUID(user.id), analysis_id):
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    return {"eliminado": True}
