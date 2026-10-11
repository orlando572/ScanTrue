"""Recorrido operativo de la API con Supabase y Anvil reales.

Ejecutar desde la raíz del repositorio. Usa solo análisis creados por este
recorrido y no imprime tokens, contraseñas ni claves.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
from getpass import getpass
import time
from uuid import UUID

from fastapi.testclient import TestClient

from backend.api.dependencies import history_repository
from backend.app import app
from backend.repositories.supabase import SupabaseDataError


TEXT = " ".join(
    [
        "El informe local describe una reunión pública y explica sus decisiones "
        "con fechas, fuentes, contexto y declaraciones de los participantes."
    ]
    * 7
)


def require(response, status: int, step: str):
    if response.status_code != status:
        detail = response.json().get("detail", "sin detalle")
        raise RuntimeError(f"{step}: HTTP {response.status_code}; {detail}")
    return response.json()


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def run(email: str | None, password: str | None, timeout: int) -> None:
    analysis_id: str | None = None
    owner_token: str | None = None
    with TestClient(app) as client:
        health = require(client.get("/salud"), 200, "salud")
        if not health["modelos"]["bilstm"]:
            raise RuntimeError("El checkpoint BiLSTM no está disponible")
        if not health["modelos"]["mbert"]:
            raise RuntimeError("El checkpoint mBERT no está disponible")
        if not health["transferencia_configurada"]:
            raise RuntimeError("Falta SUPABASE_SECRET_KEY")
        if not health["blockchain"]["conectada"]:
            raise RuntimeError("Anvil o el contrato no están disponibles")
        require(client.get("/openapi.json"), 200, "OpenAPI")
        if client.get("/docs").status_code != 200:
            raise RuntimeError("La documentación /docs no está disponible")
        require(client.get("/metricas"), 200, "metricas")
        require(client.get("/metricas?modelo=mbert"), 200, "metricas mBERT")
        try:
            guest_a = require(client.post("/invitados"), 200, "invitado A")
            guest_b = require(client.post("/invitados"), 200, "invitado B")
            token_a = guest_a["access_token"]
            token_b = guest_b["access_token"]
            owner_token = token_a
            if guest_a["usuario_id"] == guest_b["usuario_id"]:
                raise RuntimeError("Los invitados comparten identidad")
            require(
                client.post("/analisis", headers=headers(token_a), json={"texto": "corto"}),
                422,
                "mínimo de tokens",
            )
            started = time.monotonic()
            created = require(
                client.post(
                    "/analisis",
                    headers=headers(token_a),
                    json={"texto": TEXT, "titulo": "Informe local de prueba"},
                ),
                200,
                "crear análisis",
            )
            latency = time.monotonic() - started
            analysis_id = created["id"]
            UUID(analysis_id)
            if created["resultados"]["bilstm"]["estado"] != "ok":
                raise RuntimeError("BiLSTM no devolvió una predicción")
            if created["resultados"]["mbert"]["estado"] != "ok":
                raise RuntimeError("mBERT no devolvió una predicción")
            unified = created["resultado_unificado"]
            mbert_weight = app.state.analysis_service.mbert_weight
            expected_probability = (
                (1 - mbert_weight) * created["resultados"]["bilstm"]["probabilidad_falsa"]
                + mbert_weight * created["resultados"]["mbert"]["probabilidad_falsa"]
            )
            if (
                unified["modelos_utilizados"] != ["bilstm", "mbert"]
                or abs(unified["pesos_aplicados"]["bilstm"] - (1 - mbert_weight)) > 1e-9
                or abs(unified["pesos_aplicados"]["mbert"] - mbert_weight) > 1e-9
                or abs(unified["probabilidad_falsa"] - expected_probability) > 1e-9
            ):
                raise RuntimeError("El resultado unificado de dos modelos no coincide")
            if not 100 <= created["resultados"]["bilstm"]["tokens_leidos"] <= 192:
                raise RuntimeError("El recuento de tokens está fuera del rango esperado")
            if not 100 <= created["resultados"]["mbert"]["tokens_leidos"] <= 512:
                raise RuntimeError("El recuento mBERT está fuera del rango esperado")
            if created["texto_recortado"]:
                raise RuntimeError("El texto de prueba se recortó inesperadamente")
            if created["estado_blockchain"] != "pendiente":
                raise RuntimeError("El registro blockchain no empezó pendiente")
            own = require(client.get("/analisis", headers=headers(token_a)), 200, "historial A")
            row = next((item for item in own if item["id"] == analysis_id), None)
            if row is None:
                raise RuntimeError("El análisis no figura en el historial propio")
            if "texto" in row or not row["vista_previa"] or row["resultado_unificado"] != unified:
                raise RuntimeError("El listado expone texto o no conserva el resultado")
            detail = require(client.get(f"/analisis/{analysis_id}", headers=headers(token_a)), 200, "detalle A")
            expected_text = f"Informe local de prueba. {TEXT}"
            if (
                detail["texto"] != expected_text
                or detail["hash_texto"] != sha256(expected_text.encode("utf-8")).hexdigest()
                or detail["resultado_unificado"] != unified
            ):
                raise RuntimeError("El detalle no conserva texto y resultado unificado")
            require(client.get(f"/analisis/{analysis_id}", headers=headers(token_b)), 404, "detalle ajeno")
            require(client.delete(f"/analisis/{analysis_id}", headers=headers(token_b)), 404, "eliminación ajena")
            refreshed = require(
                client.post("/sesiones/renovar", json={"refresh_token": guest_a["refresh_token"]}),
                200,
                "renovar sesión",
            )
            token_a = refreshed["access_token"]
            active_refresh_token = refreshed["refresh_token"]
            owner_token = token_a
            require(client.get(f"/analisis/{analysis_id}", headers=headers(token_a)), 200, "detalle renovado")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                verification = require(
                    client.get(f"/analisis/{analysis_id}/verificacion", headers=headers(token_a)),
                    200,
                    "verificación blockchain",
                )
                if verification["estado_blockchain"] == "confirmado" and verification["verificado"] is True:
                    break
                time.sleep(2)
            else:
                raise RuntimeError(f"Blockchain no confirmó el análisis en {timeout} segundos")
            print(f"Invitados, historial, RLS, renovación y blockchain: OK; análisis {latency:.2f} s")

            blockchain_client = app.state.blockchain_client
            app.state.blockchain_client = None
            try:
                unavailable = require(
                    client.get(f"/analisis/{analysis_id}/verificacion", headers=headers(token_a)),
                    200,
                    "Anvil no disponible",
                )
                if unavailable["verificado"] is not None or unavailable["detalle"] != "blockchain_no_configurada":
                    raise RuntimeError("La degradación de blockchain no se comunicó")
            finally:
                app.state.blockchain_client = blockchain_client

            analysis_service = app.state.analysis_service
            app.state.analysis_service = None
            try:
                unavailable = require(
                    client.post("/analisis", headers=headers(token_a), json={"texto": TEXT}),
                    503,
                    "modelo no disponible",
                )
                if unavailable["detail"]["codigo"] != "modelo_no_disponible":
                    raise RuntimeError("El fallo del modelo no se comunicó")
            finally:
                app.state.analysis_service = analysis_service

            class FailingRepository:
                def list_analysis(self, *_args):
                    raise SupabaseDataError()

            app.dependency_overrides[history_repository] = lambda: FailingRepository()
            try:
                unavailable = require(
                    client.get("/analisis", headers=headers(token_a)),
                    503,
                    "Supabase no disponible",
                )
                if unavailable["detail"]["codigo"] != "supabase_no_disponible":
                    raise RuntimeError("El fallo de Supabase no se comunicó")
            finally:
                app.dependency_overrides.pop(history_repository, None)
            print("Respuestas de degradación de modelo, Supabase y Anvil: OK")

            if email and password:
                registration = require(
                    client.post(
                        "/cuentas",
                        headers=headers(token_a),
                        json={"correo": email, "contrasena": password},
                    ),
                    200,
                    "registro",
                )
                if registration["estado"] == "pendiente_confirmacion":
                    input("Confirma el correo de prueba y pulsa Enter para continuar: ")
                    login = require(
                        client.post(
                            "/sesiones",
                            headers={"X-Guest-Token": token_a},
                            json={"correo": email, "contrasena": password},
                        ),
                        200,
                        "inicio de sesión y transferencia",
                    )
                    account_token = login["sesion"]["access_token"]
                    active_refresh_token = login["sesion"]["refresh_token"]
                    transferred = login["registros_incorporados"]
                else:
                    account_token = registration["sesion"]["access_token"]
                    active_refresh_token = registration["sesion"]["refresh_token"]
                    transferred = registration["registros_incorporados"]
                owner_token = account_token
                if transferred != 1:
                    raise RuntimeError(f"Se esperó transferir un análisis; recibidos {transferred}")
                require(client.get(f"/analisis/{analysis_id}", headers=headers(account_token)), 200, "historial transferido")
                require(client.get(f"/analisis/{analysis_id}", headers=headers(token_a)), 404, "invitado tras transferencia")
                print("Registro, confirmación e incorporación del historial: OK")

            require(client.delete(f"/analisis/{analysis_id}", headers=headers(owner_token)), 200, "eliminación propia")
            require(client.get(f"/analisis/{analysis_id}", headers=headers(owner_token)), 404, "detalle eliminado")
            analysis_id = None
            print("Eliminación del análisis de prueba: OK")
            require(client.post("/sesiones/cerrar", headers=headers(owner_token)), 200, "cierre de sesión")
            require(
                client.post("/sesiones/renovar", json={"refresh_token": active_refresh_token}),
                401,
                "renovación de sesión cerrada",
            )
            print("Cierre de la sesión actual: OK")
        finally:
            if analysis_id and owner_token:
                response = client.delete(f"/analisis/{analysis_id}", headers=headers(owner_token))
                if response.status_code != 200:
                    print(f"Análisis de prueba pendiente de eliminar: {analysis_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Correo de prueba que se puede confirmar")
    parser.add_argument("--timeout", type=int, default=75, help="Segundos para esperar blockchain")
    args = parser.parse_args()
    password = getpass("Contraseña de la cuenta de prueba: ") if args.email else None
    run(args.email, password, args.timeout)
