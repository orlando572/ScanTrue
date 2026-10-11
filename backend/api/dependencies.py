"""Dependencias HTTP para sesiones y almacenamiento."""

from fastapi import Header, HTTPException, Request

from backend.repositories.supabase import SupabaseRepository
from backend.services.identity import IdentityService


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail={
                "codigo": "sesion_requerida",
                "mensaje": "Envía una sesión en Authorization: Bearer <token>.",
            },
        )
    return token.strip()


def identity_service(request: Request) -> IdentityService:
    service = getattr(request.app.state, "identity_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "supabase_no_configurado",
                "mensaje": "Configura SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY.",
                "reintentar": False,
            },
        )
    return service


def history_repository(request: Request) -> SupabaseRepository:
    identity = identity_service(request)
    return identity.repository
