"""Traducción de los filtros de la web y del panel a parámetros de PostgREST."""

from dataclasses import dataclass
from datetime import date, timedelta
import re
from urllib.parse import urlsplit, urlunsplit

# Límites de los cinco niveles, iguales a frontend/src/popup/result-presentation.js:
# el porcentaje redondeado ≤ 20, 40, 60, 80 y 100. En probabilidad: < 0,205, < 0,405…
LEVEL_BOUNDS = {
    1: (0.0, 0.205),
    2: (0.205, 0.405),
    3: (0.405, 0.605),
    4: (0.605, 0.805),
    5: (0.805, None),
}

MAX_QUERY_LENGTH = 100
# Solo letras, números, espacios, puntos y guiones: así ningún carácter cambia el
# sentido del filtro de PostgREST ni actúa como comodín de LIKE (% _ *).
_UNSAFE = re.compile(r"[^\w\s.\-]|_", re.UNICODE)
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9.\-]{0,251}[a-z0-9])?$")
# Las fechas de los filtros son días de calendario en Perú (sin horario de verano).
_LOCAL_OFFSET = "-05:00"

ORDERS = {
    "recientes": "fecha.desc,id.desc",
    "antiguos": "fecha.asc,id.asc",
    "mas_falsa": "probabilidad_unificada.desc.nullslast,fecha.desc,id.desc",
    "menos_falsa": "probabilidad_unificada.asc.nullslast,fecha.desc,id.desc",
    # Panel: primero los casos donde BiLSTM y BETO discrepan (aprendizaje activo).
    "prioridad": "discrepa.desc,fecha.desc,id.desc",
}
VERIFICATION_CONCLUSIONS = (
    "respaldada", "contradicha", "fuera_de_contexto", "evidencia_insuficiente",
)
REVIEW_DECISIONS = ("aprobado", "corregido", "descartado")

Params = list[tuple[str, str | int]]


@dataclass(frozen=True)
class AnalysisFilters:
    q: str | None = None
    nivel: int | None = None
    comparacion: str | None = None
    desde: date | None = None
    hasta: date | None = None
    dominio: str | None = None
    oculto: bool | None = None
    # «sin_verificar» o una conclusión de la verificación web (incremento 2).
    verificacion: str | None = None
    # «pendiente», «revisado» o una decisión concreta (solo el panel).
    revision: str | None = None
    orden: str = "recientes"


def clean_query(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(_UNSAFE.sub(" ", value).split())[:MAX_QUERY_LENGTH].strip()
    return cleaned or None


def clean_domain(value: str | None) -> str | None:
    if not value:
        return None
    domain = value.strip().lower().removeprefix("www.")
    return domain if _DOMAIN.fullmatch(domain) else None


def filter_params(filters: AnalysisFilters) -> Params:
    params: Params = []
    query = clean_query(filters.q)
    if query:
        pattern = f'"*{query}*"'
        params.append(("or", f"(texto.ilike.{pattern},url.ilike.{pattern})"))
    if filters.nivel is not None:
        low, high = LEVEL_BOUNDS[filters.nivel]
        params.append(("probabilidad_unificada", f"gte.{low}"))
        if high is not None:
            params.append(("probabilidad_unificada", f"lt.{high}"))
    if filters.comparacion:
        params.append(("comparacion", f"eq.{filters.comparacion}"))
    if filters.desde:
        params.append(("fecha", f"gte.{filters.desde.isoformat()}T00:00:00{_LOCAL_OFFSET}"))
    if filters.hasta:
        end = filters.hasta + timedelta(days=1)
        params.append(("fecha", f"lt.{end.isoformat()}T00:00:00{_LOCAL_OFFSET}"))
    domain = clean_domain(filters.dominio)
    if domain:
        params.append(("dominio", f"eq.{domain}"))
    elif filters.dominio:
        # Un dominio que no se puede leer no debe devolver todos los casos.
        params.append(("dominio", "eq.-"))
    if filters.oculto is not None:
        params.append(("oculto", f"is.{str(filters.oculto).lower()}"))
    if filters.verificacion == "sin_verificar":
        params.append(("verificaciones_web", "is.null"))
    elif filters.verificacion in VERIFICATION_CONCLUSIONS:
        params.append(("verificaciones_web.conclusion", f"eq.{filters.verificacion}"))
    if filters.revision == "pendiente":
        params.append(("revisiones", "is.null"))
    elif filters.revision in REVIEW_DECISIONS:
        params.append(("revisiones.decision", f"eq.{filters.revision}"))
    params.append(("order", ORDERS.get(filters.orden, ORDERS["recientes"])))
    return params


def embed(resource: str, columns: str, *, required: bool) -> str:
    """Recurso incrustado; «!inner» cuando un filtro exige que la fila exista."""
    return f"{resource}{'!inner' if required else ''}({columns})"


def public_url(url: str | None) -> tuple[str | None, str | None]:
    """Devuelve (dominio, url sin credenciales, consulta ni fragmento) de una página http(s)."""
    if not url:
        return None, None
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None, None
    if parts.scheme not in ("http", "https") or not host:
        return None, None
    netloc = host if port is None else f"{host}:{port}"
    return host.removeprefix("www."), urlunsplit((parts.scheme, netloc, parts.path or "/", "", ""))


def preview(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"
