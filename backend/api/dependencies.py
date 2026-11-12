"""Dependencias HTTP para sesiones y almacenamiento."""

from fastapi import Depends, Header, HTTPException, Request

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


def service_repository(request: Request) -> SupabaseRepository:
    """Repositorio con la clave secreta: lecturas de la web pública y del panel."""
    identity = identity_service(request)
    if not identity.settings.secret_key:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "clave_secreta_no_configurada",
                "mensaje": "Configura SUPABASE_SECRET_KEY para la web y el panel.",
                "reintentar": False,
            },
        )
    return identity.repository


def is_admin(user) -> bool:
    metadata = getattr(user, "app_metadata", None) or {}
    return metadata.get("role") == "admin"


def admin_user(
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
):
    """Solo deja pasar sesiones con app_metadata.role = 'admin' (ver crear_admin.py)."""
    user = identity.verify_user(token)
    if not is_admin(user):
        raise HTTPException(
            status_code=403,
            detail={
                "codigo": "no_es_admin",
                "mensaje": "Esta cuenta no tiene acceso de administrador.",
            },
        )
    return user
