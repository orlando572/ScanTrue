"""Verificación del registro de un análisis perteneciente al solicitante."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.dependencies import bearer_token, history_repository, identity_service
from backend.blockchain.client import BlockchainUnavailable, RegistryClient
from backend.repositories.supabase import SupabaseRepository
from backend.schemas.blockchain import VerificationResponse
from backend.services.identity import IdentityService

router = APIRouter()


@router.get("/analisis/{analysis_id}/verificacion", response_model=VerificationResponse)
def verify_analysis(
    analysis_id: UUID,
    request: Request,
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
    repository: SupabaseRepository = Depends(history_repository),
) -> VerificationResponse:
    user = identity.verify_user(token)
    record = repository.get_analysis(token, UUID(user.id), analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado.")
    client: RegistryClient | None = getattr(
        request.app.state, "blockchain_client", None
    )
    if client is None:
        return VerificationResponse(
            estado_blockchain=record.estado_blockchain,
            hash_transaccion=record.hash_transaccion,
            verificado=None,
            detalle="blockchain_no_configurada",
        )
    try:
        client.check_ready()
        if not record.hash_transaccion:
            detail = (
                "registro_pendiente"
                if record.estado_blockchain == "pendiente"
                else "registro_no_enviado"
            )
            verified = None
        else:
            verified = client.verify(record, record.hash_transaccion)
            detail = (
                "registro_coincide"
                if verified is True
                else "registro_no_coincide" if verified is False else "sin_confirmar"
            )
    except BlockchainUnavailable as error:
        verified = None
        detail = str(error)
    except Exception:
        verified = None
        detail = "anvil_no_disponible"
    return VerificationResponse(
        estado_blockchain=record.estado_blockchain,
        hash_transaccion=record.hash_transaccion,
        verificado=verified,
        detalle=detail,
    )
