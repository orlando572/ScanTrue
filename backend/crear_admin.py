"""Crea una cuenta de administrador de la web o asciende una existente.

El rol vive en `app_metadata.role = "admin"` de Supabase Auth, que solo se puede
cambiar con la clave secreta. La web (web/) solo deja iniciar sesión a estas cuentas.

Uso, desde la raíz del repositorio:
    PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m backend.crear_admin correo@ejemplo.com
    PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m backend.crear_admin correo@ejemplo.com --quitar

La contraseña se pide por teclado (no queda en el historial de la terminal).
"""

import argparse
from getpass import getpass
import sys

from supabase import ClientOptions, create_client

from backend.core.config import SupabaseSettings


def find_user(client, email: str):
    page = 1
    while True:
        users = client.auth.admin.list_users(page=page, per_page=200)
        for user in users:
            if (user.email or "").casefold() == email.casefold():
                return user
        if len(users) < 200:
            return None
        page += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("correo")
    parser.add_argument("--quitar", action="store_true", help="Retira el rol de administrador.")
    arguments = parser.parse_args()

    settings = SupabaseSettings.from_environment()
    if settings is None or not settings.secret_key:
        print("Faltan SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY o SUPABASE_SECRET_KEY en backend/.env.")
        return 1
    client = create_client(
        settings.url,
        settings.secret_key,
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )
    user = find_user(client, arguments.correo)

    if arguments.quitar:
        if user is None:
            print("No existe una cuenta con ese correo.")
            return 1
        metadata = {**(user.app_metadata or {}), "role": None}
        client.auth.admin.update_user_by_id(user.id, {"app_metadata": metadata})
        print(f"{arguments.correo} ya no es administrador.")
        return 0

    if user is None:
        password = getpass("Contraseña nueva (mínimo 8 caracteres): ")
        if len(password) < 8 or password != getpass("Repite la contraseña: "):
            print("Las contraseñas no coinciden o son demasiado cortas.")
            return 1
        client.auth.admin.create_user({
            "email": arguments.correo,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"role": "admin"},
        })
        print(f"Cuenta de administrador creada: {arguments.correo}")
        return 0

    if user.is_anonymous:
        print("Esa cuenta es de invitado; usa un correo registrado.")
        return 1
    metadata = {**(user.app_metadata or {}), "role": "admin"}
    client.auth.admin.update_user_by_id(user.id, {"app_metadata": metadata})
    print(f"{arguments.correo} ahora es administrador (su contraseña no cambió).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
