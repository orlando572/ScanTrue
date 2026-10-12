"""Contratos de sesiones de invitados y cuentas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class Credentials(BaseModel):
    correo: str = Field(min_length=3, max_length=320)
    contrasena: SecretStr = Field(min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: SecretStr


class SessionResponse(BaseModel):
    usuario_id: UUID
    anonimo: bool
    access_token: str
    refresh_token: str
    expires_in: int


class RegistrationResponse(BaseModel):
    estado: Literal["activa", "pendiente_confirmacion"]
    sesion: SessionResponse | None = None
    registros_incorporados: int = 0


class LoginResponse(BaseModel):
    sesion: SessionResponse
    registros_incorporados: int
