"""Autenticación de Supabase y traslado verificado del historial invitado."""

import logging
from uuid import UUID

from supabase import ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthError

from backend.core.config import SupabaseSettings
from backend.repositories.supabase import SupabaseRepository
from backend.schemas.identity import (
    Credentials,
    LoginResponse,
    RegistrationResponse,
    SessionResponse,
)

logger = logging.getLogger(__name__)


class InvalidSessionError(RuntimeError):
    """El token no corresponde a una sesión vigente."""


class AuthOperationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class SupabaseAuthUnavailable(RuntimeError):
    """No fue posible comunicarse con Supabase Auth."""


class IdentityService:
    def __init__(self, settings: SupabaseSettings, repository: SupabaseRepository):
        self.settings = settings
        self.repository = repository

    def _client(self):
        # Cliente nuevo por operación: ninguna sesión se comparte entre usuarios.
        return create_client(
            self.settings.url,
            self.settings.publishable_key,
            options=ClientOptions(persist_session=False, auto_refresh_token=False),
        )

    @staticmethod
    def _session(auth_response) -> SessionResponse:
        session = auth_response.session
        if session is None:
            raise SupabaseAuthUnavailable("Supabase no devolvió una sesión.")
        return SessionResponse(
            usuario_id=session.user.id,
            anonimo=bool(session.user.is_anonymous),
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_in=session.expires_in,
        )

    def verify_user(self, token: str):
        try:
            response = self._client().auth.get_user(token)
        except AuthApiError as error:
            if 400 <= error.status < 500:
                raise InvalidSessionError("La sesión no es válida o expiró.") from error
            raise SupabaseAuthUnavailable("No se pudo verificar la sesión.") from error
        except Exception as error:
            logger.warning("Error al verificar una sesión en Supabase Auth")
            raise SupabaseAuthUnavailable("No se pudo verificar la sesión.") from error
        if response is None or response.user is None:
            raise InvalidSessionError("La sesión no es válida o expiró.")
        return response.user

    def _guest(self, token: str):
        user = self.verify_user(token)
        if not user.is_anonymous:
            raise AuthOperationError(
                "sesion_no_invitada", "La sesión de origen debe ser de invitado.", 400
            )
        return user

    def _require_transfer_key(self) -> None:
        if not self.settings.secret_key:
            raise SupabaseAuthUnavailable(
                "Falta la configuración necesaria para incorporar el historial."
            )

    def create_guest(self) -> SessionResponse:
        try:
            response = self._client().auth.sign_in_anonymously()
            return self._session(response)
        except AuthApiError as error:
            if 400 <= error.status < 500:
                raise AuthOperationError(
                    "invitados_no_disponibles",
                    "No se pudo crear un invitado. Revisa que Auth anónimo esté habilitado.",
                    503,
                ) from error
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error
        except AuthError as error:
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error

    def register(self, guest_token: str, credentials: Credentials) -> RegistrationResponse:
        guest = self._guest(guest_token)
        self._require_transfer_key()
        try:
            response = self._client().auth.sign_up(
                {
                    "email": credentials.correo,
                    "password": credentials.contrasena.get_secret_value(),
                }
            )
        except AuthApiError as error:
            if error.status == 429:
                raise AuthOperationError(
                    "registro_temporalmente_limitado",
                    "Supabase limitó temporalmente el registro; inténtalo más tarde.",
                    429,
                ) from error
            if 400 <= error.status < 500:
                raise AuthOperationError(
                    "registro_rechazado",
                    "Supabase rechazó el registro; revisa correo y contraseña.",
                    400,
                ) from error
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error
        except AuthError as error:
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error

        if response.session is None:
            return RegistrationResponse(estado="pendiente_confirmacion")
        session = self._session(response)
        account = self.verify_user(session.access_token)
        count = self.repository.transfer_guest_history(UUID(guest.id), UUID(account.id))
        return RegistrationResponse(
            estado="activa", sesion=session, registros_incorporados=count
        )

    def login(
        self, credentials: Credentials, guest_token: str | None = None
    ) -> LoginResponse:
        guest = self._guest(guest_token) if guest_token else None
        if guest is not None:
            self._require_transfer_key()
        try:
            response = self._client().auth.sign_in_with_password(
                {
                    "email": credentials.correo,
                    "password": credentials.contrasena.get_secret_value(),
                }
            )
        except AuthApiError as error:
            if 400 <= error.status < 500:
                raise AuthOperationError(
                    "credenciales_invalidas", "Correo o contraseña incorrectos.", 401
                ) from error
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error
        except AuthError as error:
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error

        session = self._session(response)
        count = 0
        if guest is not None:
            account = self.verify_user(session.access_token)
            if account.is_anonymous:
                raise AuthOperationError(
                    "cuenta_no_disponible", "La cuenta aún no está activa.", 401
                )
            count = self.repository.transfer_guest_history(UUID(guest.id), UUID(account.id))
        return LoginResponse(sesion=session, registros_incorporados=count)

    def refresh(self, refresh_token: str) -> SessionResponse:
        try:
            response = self._client().auth.refresh_session(refresh_token)
            return self._session(response)
        except AuthApiError as error:
            if 400 <= error.status < 500:
                raise InvalidSessionError("No se pudo renovar la sesión.") from error
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error
        except AuthError as error:
            raise SupabaseAuthUnavailable("Supabase Auth no está disponible.") from error

    def close_session(self, access_token: str) -> None:
        self.verify_user(access_token)
        try:
            # El alcance local revoca solo la sesión presentada en el Bearer.
            self._client().auth.admin.sign_out(access_token, "local")
        except AuthApiError as error:
            if 400 <= error.status < 500:
                raise InvalidSessionError("La sesión no es válida o expiró.") from error
            raise SupabaseAuthUnavailable("No se pudo cerrar la sesión.") from error
        except AuthError as error:
            raise SupabaseAuthUnavailable("No se pudo cerrar la sesión.") from error
        except Exception as error:
            logger.warning("Error al cerrar una sesión en Supabase Auth")
            raise SupabaseAuthUnavailable("No se pudo cerrar la sesión.") from error
