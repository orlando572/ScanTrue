"""Creación y renovación de sesiones de Supabase Auth."""

from fastapi import APIRouter, Depends, Header

from backend.api.dependencies import bearer_token, identity_service
from backend.schemas.identity import (
    Credentials,
    LoginResponse,
    RefreshRequest,
    RegistrationResponse,
    SessionResponse,
)
from backend.services.identity import IdentityService


router = APIRouter()


@router.post("/invitados", response_model=SessionResponse)
def create_guest(
    identity: IdentityService = Depends(identity_service),
) -> SessionResponse:
    return identity.create_guest()


@router.post("/cuentas", response_model=RegistrationResponse)
def register(
    credentials: Credentials,
    guest_token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
) -> RegistrationResponse:
    return identity.register(guest_token, credentials)


@router.post("/sesiones", response_model=LoginResponse)
def login(
    credentials: Credentials,
    guest_token: str | None = Header(default=None, alias="X-Guest-Token"),
    identity: IdentityService = Depends(identity_service),
) -> LoginResponse:
    return identity.login(credentials, guest_token)


@router.post("/sesiones/renovar", response_model=SessionResponse)
def refresh(
    payload: RefreshRequest,
    identity: IdentityService = Depends(identity_service),
) -> SessionResponse:
    return identity.refresh(payload.refresh_token.get_secret_value())


@router.post("/sesiones/cerrar")
def close_session(
    token: str = Depends(bearer_token),
    identity: IdentityService = Depends(identity_service),
) -> dict[str, bool]:
    identity.close_session(token)
    return {"cerrada": True}
