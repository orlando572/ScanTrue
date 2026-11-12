"""Acceso a PostgREST usando el JWT de cada usuario para respetar RLS."""

from datetime import datetime
import re
from uuid import UUID

import httpx

from backend.core.config import SupabaseSettings
from backend.repositories.filters import (
    REVIEW_DECISIONS,
    VERIFICATION_CONCLUSIONS,
    AnalysisFilters,
    Params,
    embed,
    filter_params,
    preview,
    public_url,
)
from backend.schemas.admin import (
    AdminCase,
    AdminCaseDetail,
    AdminCasePage,
    AdminSummary,
    DatasetDetail,
    DatasetItem,
    DatasetVersion,
    Review,
)
from backend.schemas.analysis import AnalysisResponse, ModelResult, UnifiedResult
from backend.schemas.history import HistoryListRecord, HistoryRecord
from backend.schemas.public import (
    PublicAnalysis,
    PublicAnalysisDetail,
    PublicAnalysisPage,
    PublicModelOutput,
    PublicSummary,
    WebVerification,
)


SELECT_HISTORY_BASE = (
    "id,fecha,url,hash_texto,resultado_unificado,comparacion,estado_blockchain,"
    "hash_transaccion,resultados_modelo(modelo,version,clase,"
    "probabilidad_falsa,tokens_leidos)"
)
SELECT_HISTORY_WITH_TEXT = "texto," + SELECT_HISTORY_BASE

# La web nunca pide usuario_id ni datos de la cuenta.
WEB_COLUMNS = (
    "id,fecha,url,texto,texto_original,fragmentos,texto_recortado,hash_texto,"
    "resultado_unificado,comparacion,estado_blockchain,hash_transaccion,oculto,"
    "resultados_modelo(modelo,version,clase,probabilidad_falsa,tokens_leidos,texto_modelo)"
)
VERIFICATION_COLUMNS = "estado,conclusion,resumen,afirmaciones,fuentes,modelo_llm,actualizado_en"
REVIEW_COLUMNS = "decision,etiqueta_final,nota,evidencia,grupo_evento,fecha"
# En las listas los fragmentos van abreviados; el detalle los devuelve completos.
LIST_FRAGMENT_LENGTH = 700
LIST_FRAGMENT_COUNT = 6
# Mismo patrón de palabra que el BiLSTM (TOKEN_PATTERN de bilstm/modelo.py).
WORD = re.compile(r"\b\w+\b")
# PostgREST devuelve como máximo 1000 filas por petición en Supabase.
PAGE_ROWS = 1000


def web_select(filters: AnalysisFilters | None = None, *, admin: bool = False) -> str:
    """Columnas de la web; un filtro sobre una tabla hija exige que la fila exista."""
    verification = filters is not None and filters.verificacion in VERIFICATION_CONCLUSIONS
    parts = [WEB_COLUMNS, embed("verificaciones_web", VERIFICATION_COLUMNS, required=verification)]
    if admin:
        review = filters is not None and filters.revision in (*REVIEW_DECISIONS, "revisado")
        parts.append(embed("revisiones", REVIEW_COLUMNS, required=review))
    return ",".join(parts)


def _single(value):
    """PostgREST incrusta una relación 1:1 como objeto; por si acaso, admite lista."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


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
        params: dict[str, str | int] | Params | None = None,
        body: dict | list | None = None,
        prefer: str | None = None,
    ):
        response = self._send(
            method, path, token=token, admin=admin, params=params, body=body, prefer=prefer
        )
        return response.json() if response.content else None

    def _request_page(self, path: str, params: Params) -> tuple[list[dict], int | None]:
        """GET con recuento exacto: devuelve las filas y el total del filtro."""
        response = self._send("GET", path, admin=True, params=params, prefer="count=exact")
        total = response.headers.get("content-range", "").rpartition("/")[2]
        return (response.json() if response.content else []), (
            int(total) if total.isdigit() else None
        )

    def _send(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        admin: bool = False,
        params: dict[str, str | int] | Params | None = None,
        body: dict | list | None = None,
        prefer: str | None = None,
    ) -> httpx.Response:
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
            return response
        except httpx.HTTPStatusError as error:
            raise SupabaseDataError(error.response.status_code) from error
        except httpx.RequestError as error:
            raise SupabaseDataError() from error

    def create_analysis(
        self,
        user_id: UUID,
        url: str | None,
        text: str,
        text_hash: str,
        response: AnalysisResponse,
        *,
        original_text: str | None = None,
        fragments: list[str] | None = None,
        truncated: bool = False,
        model_texts: dict[str, str] | None = None,
    ) -> UUID:
        predictions = [
            {
                "modelo": result.modelo,
                "version": result.version,
                "clase": result.clase,
                "probabilidad_falsa": result.probabilidad_falsa,
                "tokens_leidos": result.tokens_leidos,
                "texto_modelo": (model_texts or {}).get(result.modelo),
            }
            for result in response.resultados.values()
            if result.estado == "ok"
        ]
        body = {
            "p_usuario_id": str(user_id),
            "p_url": url,
            "p_texto": text,
            "p_hash_texto": text_hash,
            "p_comparacion": response.comparacion,
            "p_resultados": predictions,
            "p_resultado_unificado": response.resultado_unificado.model_dump(),
        }
        try:
            value = self._request(
                "POST",
                "rpc/crear_analisis_con_fragmentos",
                admin=True,
                body={
                    **body,
                    "p_texto_original": original_text,
                    "p_fragmentos": fragments,
                    "p_texto_recortado": truncated,
                },
            )
        except SupabaseDataError as error:
            # Sin la migración 007 la función no existe: se guarda como antes.
            if error.status_code != 404:
                raise
            value = self._request(
                "POST", "rpc/crear_analisis_texto_unico", admin=True, body=body
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

    # ── Web pública ─────────────────────────────────────────────────

    @staticmethod
    def _web_fields(row: dict, *, detail: bool) -> dict:
        """Campos comunes de la web a partir de una fila; nunca incluye usuario_id."""
        domain, url = public_url(row.get("url"))
        text = row.get("texto")
        original = row.get("texto_original")
        stored = row.get("fragmentos")
        fragments = [
            item.strip() for item in stored or [] if isinstance(item, str) and item.strip()
        ] or [value for value in [original or text] if value]
        total = len(fragments)
        if not detail:
            fragments = [
                preview(item, LIST_FRAGMENT_LENGTH) for item in fragments[:LIST_FRAGMENT_COUNT]
            ]
        try:
            unified = UnifiedResult(**row["resultado_unificado"])
        except Exception:  # Registros antiguos sin resultado unificado completo.
            unified = None
        verification = _single(row.get("verificaciones_web"))
        fields = {
            "id": row["id"],
            "fecha": row["fecha"],
            "dominio": domain,
            "url": url,
            "fragmentos": fragments,
            "fragmentos_total": total,
            "palabras": len(WORD.findall(text or "")),
            "texto_recortado": bool(row.get("texto_recortado")),
            "probabilidad_falsa": unified.probabilidad_falsa if unified else None,
            "comparacion": row["comparacion"],
            "estado_blockchain": row["estado_blockchain"],
            "hash_transaccion": row.get("hash_transaccion"),
            "resultados": {
                item["modelo"]: PublicModelOutput(
                    modelo=item["modelo"],
                    version=item.get("version"),
                    clase=item["clase"],
                    probabilidad_falsa=item["probabilidad_falsa"],
                    tokens_leidos=item.get("tokens_leidos"),
                    texto_modelo=item.get("texto_modelo") if detail else None,
                )
                for item in row.get("resultados_modelo") or []
            },
            "resultado_unificado": unified,
            "verificacion_web": WebVerification(**verification) if verification else None,
        }
        if detail:
            fields.update(hash_texto=row["hash_texto"], texto=text, texto_original=original)
        return fields

    @staticmethod
    def _admin_fields(row: dict) -> dict:
        unified = row.get("resultado_unificado") or {}
        probability = unified.get("probabilidad_falsa")
        review = _single(row.get("revisiones"))
        return {
            "oculto": bool(row.get("oculto")),
            "etiqueta_modelo": (
                None if probability is None else "falsa" if probability >= 0.5 else "real"
            ),
            "revision": Review(**review) if review else None,
        }

    def list_public_analysis(
        self, filters: AnalysisFilters, limit: int, offset: int
    ) -> PublicAnalysisPage:
        params: Params = [
            ("select", web_select(filters)),
            ("oculto", "is.false"),
            *filter_params(filters),
            ("limit", limit),
            ("offset", offset),
        ]
        rows, total = self._request_page("analisis", params)
        return PublicAnalysisPage(
            elementos=[PublicAnalysis(**self._web_fields(row, detail=False)) for row in rows],
            total=total,
        )

    def get_public_analysis(self, analysis_id: UUID) -> PublicAnalysisDetail | None:
        rows = self._request(
            "GET",
            "analisis",
            admin=True,
            params=[
                ("select", web_select()),
                ("id", f"eq.{analysis_id}"),
                ("oculto", "is.false"),
                ("limit", 1),
            ],
        )
        return PublicAnalysisDetail(**self._web_fields(rows[0], detail=True)) if rows else None

    def _summary(self, visible_only: bool) -> dict:
        return self._request(
            "POST", "rpc/resumen_plataforma", admin=True,
            body={"p_solo_visibles": visible_only},
        ) or {}

    def public_summary(self) -> PublicSummary:
        data = self._summary(True)
        return PublicSummary(**{key: data[key] for key in PublicSummary.model_fields if key in data})

    # ── Panel de administración: casos y revisión ───────────────────

    def admin_summary(self) -> AdminSummary:
        data = self._summary(False)
        days = [{**day, "dia": str(day["dia"])} for day in data.get("por_dia") or []]
        return AdminSummary(**{**data, "por_dia": days})

    def list_admin_cases(
        self, filters: AnalysisFilters, limit: int, offset: int
    ) -> AdminCasePage:
        params: Params = [
            ("select", web_select(filters, admin=True)),
            *filter_params(filters),
            ("limit", limit),
            ("offset", offset),
        ]
        rows, total = self._request_page("analisis", params)
        return AdminCasePage(
            elementos=[
                AdminCase(**self._web_fields(row, detail=False), **self._admin_fields(row))
                for row in rows
            ],
            total=total,
        )

    def get_admin_case(self, analysis_id: UUID) -> AdminCaseDetail | None:
        rows = self._request(
            "GET",
            "analisis",
            admin=True,
            params=[
                ("select", web_select(admin=True)),
                ("id", f"eq.{analysis_id}"),
                ("limit", 1),
            ],
        )
        if not rows:
            return None
        return AdminCaseDetail(
            **self._web_fields(rows[0], detail=True), **self._admin_fields(rows[0])
        )

    def set_hidden(self, analysis_id: UUID, hidden: bool) -> bool:
        rows = self._request(
            "PATCH",
            "analisis",
            admin=True,
            params={"id": f"eq.{analysis_id}", "select": "id"},
            body={"oculto": hidden},
            prefer="return=representation",
        )
        return bool(rows)

    def save_review(self, analysis_id: UUID, reviewer_id: UUID, review: Review) -> None:
        self._request(
            "POST",
            "revisiones",
            admin=True,
            params={"on_conflict": "analisis_id"},
            body={
                "analisis_id": str(analysis_id),
                "decision": review.decision,
                "etiqueta_final": review.etiqueta_final,
                "nota": review.nota,
                "evidencia": review.evidencia,
                "grupo_evento": review.grupo_evento,
                "revisor_id": str(reviewer_id),
                "fecha": datetime.now().astimezone().isoformat(),
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def delete_review(self, analysis_id: UUID) -> bool:
        rows = self._request(
            "DELETE",
            "revisiones",
            admin=True,
            params={"analisis_id": f"eq.{analysis_id}", "select": "analisis_id"},
            prefer="return=representation",
        )
        return bool(rows)

    # ── Versiones de dataset ────────────────────────────────────────

    def reviewed_cases(self) -> list[dict]:
        """Casos aprobados o corregidos, con lo necesario para armar un dataset."""
        select = (
            "decision,etiqueta_final,nota,evidencia,grupo_evento,fecha,"
            "analisis!inner(id,fecha,url,texto,texto_original,hash_texto,comparacion,"
            "resultado_unificado,resultados_modelo(modelo,version,probabilidad_falsa))"
        )
        cases: list[dict] = []
        while True:
            rows = self._request(
                "GET",
                "revisiones",
                admin=True,
                params=[
                    ("select", select),
                    ("decision", "in.(aprobado,corregido)"),
                    ("order", "fecha.asc,analisis_id.asc"),
                    ("limit", PAGE_ROWS),
                    ("offset", len(cases)),
                ],
            ) or []
            cases.extend(rows)
            if len(rows) < PAGE_ROWS:
                return cases

    def create_dataset_version(
        self, name: str, description: str | None, creator_id: UUID,
        summary: dict, items: list[dict],
    ) -> UUID:
        value = self._request(
            "POST",
            "rpc/crear_version_dataset",
            admin=True,
            body={
                "p_nombre": name,
                "p_descripcion": description,
                "p_creado_por": str(creator_id),
                "p_resumen": summary,
                "p_items": items,
            },
        )
        return UUID(value)

    def list_dataset_versions(self) -> list[DatasetVersion]:
        rows = self._request(
            "GET",
            "datasets_version",
            admin=True,
            params={"select": "id,nombre,descripcion,fecha,resumen", "order": "fecha.desc"},
        )
        return [DatasetVersion(**row) for row in rows or []]

    def get_dataset_version(self, version_id: UUID) -> DatasetVersion | None:
        rows = self._request(
            "GET",
            "datasets_version",
            admin=True,
            params={
                "select": "id,nombre,descripcion,fecha,resumen",
                "id": f"eq.{version_id}",
                "limit": 1,
            },
        )
        return DatasetVersion(**rows[0]) if rows else None

    def dataset_items(
        self, version_id: UUID, limit: int | None = None, offset: int = 0
    ) -> tuple[list[DatasetItem], int | None]:
        """Filas de una versión; sin `limit` las devuelve todas (para exportar)."""
        items: list[DatasetItem] = []
        total = None
        while True:
            size = PAGE_ROWS if limit is None else min(limit - len(items), PAGE_ROWS)
            rows, total = self._request_page(
                "dataset_items",
                [
                    ("select", "id,analisis_id,texto,hash_texto,etiqueta,particion,grupo,"
                               "url,dominio,decision,procedencia,evidencia"),
                    ("version_id", f"eq.{version_id}"),
                    ("order", "particion.asc,grupo.asc,id.asc"),
                    ("limit", size),
                    ("offset", offset + len(items)),
                ],
            )
            items.extend(DatasetItem(**row) for row in rows)
            if len(rows) < size or (limit is not None and len(items) >= limit):
                return items, total

    def delete_dataset_version(self, version_id: UUID) -> bool:
        rows = self._request(
            "DELETE",
            "datasets_version",
            admin=True,
            params={"id": f"eq.{version_id}", "select": "id"},
            prefer="return=representation",
        )
        return bool(rows)

    # ── Versiones de modelos ────────────────────────────────────────

    def model_version_usage(self) -> dict[tuple[str, str], int]:
        """Análisis guardados con cada versión de cada modelo."""
        rows = self._request("POST", "rpc/resumen_versiones_modelo", admin=True, body={})
        return {(row["modelo"], row["version"]): int(row["casos"]) for row in rows or []}
