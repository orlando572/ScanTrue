"""Acceso a PostgREST usando el JWT de cada usuario para respetar RLS."""

from datetime import datetime
from uuid import UUID

import httpx

from backend.core.config import SupabaseSettings
from backend.schemas.analysis import AnalysisResponse, ModelResult
from backend.schemas.history import HistoryListRecord, HistoryRecord


SELECT_HISTORY_BASE = (
    "id,fecha,titulo,url,hash_texto,resultado_unificado,comparacion,estado_blockchain,"
    "hash_transaccion,resultados_modelo(modelo,version,clase,"
    "probabilidad_falsa,tokens_leidos)"
)
SELECT_HISTORY_WITH_TEXT = "texto," + SELECT_HISTORY_BASE


class SupabaseDataError(RuntimeError):
    def __init__(self, status_code: int | None = None) -> None:
        super().__init__("No se pudo completar la operación en Supabase.")
        self.status_code = status_code


class SupabaseRepository:
    def __init__(self, settings: SupabaseSettings) -> None:
        self.settings = settings

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        admin: bool = False,
        params: dict[str, str | int] | None = None,
        body: dict | None = None,
        prefer: str | None = None,
    ):
        key = self.settings.secret_key if admin else self.settings.publishable_key
        if not key:
            raise SupabaseDataError()
        headers = {"apikey": key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if prefer:
            headers["Prefer"] = prefer
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.request(
                    method,
                    f"{self.settings.url}/rest/v1/{path}",
                    headers=headers,
                    params=params,
                    json=body,
                )
            response.raise_for_status()
            return response.json() if response.content else None
        except httpx.HTTPStatusError as error:
            raise SupabaseDataError(error.response.status_code) from error
        except httpx.RequestError as error:
            raise SupabaseDataError() from error

    def create_analysis(
        self,
        user_id: UUID,
        title: str | None,
        url: str | None,
        text: str,
        text_hash: str,
        response: AnalysisResponse,
    ) -> UUID:
        predictions = [
            {
                "modelo": result.modelo,
                "version": result.version,
                "clase": result.clase,
                "probabilidad_falsa": result.probabilidad_falsa,
                "tokens_leidos": result.tokens_leidos,
            }
            for result in response.resultados.values()
            if result.estado == "ok"
        ]
        value = self._request(
            "POST",
            "rpc/crear_analisis_completo",
            admin=True,
            body={
                "p_usuario_id": str(user_id),
                "p_titulo": title,
                "p_url": url,
                "p_texto": text,
                "p_hash_texto": text_hash,
                "p_comparacion": response.comparacion,
                "p_resultados": predictions,
                "p_resultado_unificado": response.resultado_unificado.model_dump(),
            },
        )
        return UUID(value)

    @staticmethod
    def _record(value: dict) -> HistoryRecord:
        results = {
            item["modelo"]: ModelResult(**item, estado="ok")
            for item in value.pop("resultados_modelo", [])
        }
        value.setdefault("texto", None)
        return HistoryRecord(**value, resultados=results)

    def list_analysis(
        self, token: str, user_id: UUID, limit: int, offset: int
    ) -> list[HistoryListRecord]:
        rows = self._request(
            "GET",
            "analisis",
            token=token,
            params={
                "select": SELECT_HISTORY_WITH_TEXT,
                "usuario_id": f"eq.{user_id}",
                "order": "fecha.desc,id.desc",
                "limit": limit,
                "offset": offset,
            },
        )
        records: list[HistoryListRecord] = []
        for row in rows:
            record = self._record(row)
            preview = " ".join(record.texto.split()) if record.texto else None
            if preview and len(preview) > 160:
                preview = preview[:159].rstrip() + "…"
            records.append(
                HistoryListRecord(
                    **record.model_dump(exclude={"texto"}), vista_previa=preview
                )
            )
        return records

    def get_analysis(
        self, token: str, user_id: UUID, analysis_id: UUID
    ) -> HistoryRecord | None:
        rows = self._request(
            "GET",
            "analisis",
            token=token,
            params={
                "select": SELECT_HISTORY_WITH_TEXT,
                "usuario_id": f"eq.{user_id}",
                "id": f"eq.{analysis_id}",
                "limit": 1,
            },
        )
        return self._record(rows[0]) if rows else None

    def delete_analysis(
        self, token: str, user_id: UUID, analysis_id: UUID
    ) -> bool:
        rows = self._request(
            "DELETE",
            "analisis",
            token=token,
            params={"usuario_id": f"eq.{user_id}", "id": f"eq.{analysis_id}"},
            prefer="return=representation",
        )
        return bool(rows)

    def transfer_guest_history(self, guest_id: UUID, account_id: UUID) -> int:
        rows = self._request(
            "PATCH",
            "analisis",
            admin=True,
            params={"usuario_id": f"eq.{guest_id}", "select": "id"},
            body={"usuario_id": str(account_id)},
            prefer="return=representation",
        )
        return len(rows)

    def claim_blockchain_analysis(self) -> UUID | None:
        value = self._request(
            "POST", "rpc/reclamar_registro_blockchain", admin=True, body={}
        )
        return UUID(value) if value else None

    def get_blockchain_analysis(self, analysis_id: UUID) -> HistoryRecord | None:
        rows = self._request(
            "GET",
            "analisis",
            admin=True,
            params={"select": SELECT_HISTORY_BASE, "id": f"eq.{analysis_id}", "limit": 1},
        )
        return self._record(rows[0]) if rows else None

    def set_blockchain_state(
        self,
        analysis_id: UUID,
        *,
        state: str,
        transaction_hash: str | None,
        next_attempt: datetime,
        error: str | None = None,
    ) -> None:
        self._request(
            "PATCH",
            "analisis",
            admin=True,
            params={"id": f"eq.{analysis_id}"},
            body={
                "estado_blockchain": state,
                "hash_transaccion": transaction_hash,
                "proximo_intento_blockchain": next_attempt.isoformat(),
                "ultimo_error_blockchain": error,
            },
        )
