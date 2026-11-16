"""Consulta pública de evaluaciones publicadas."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request

from backend.schemas.metrics import MetricsResponse

router = APIRouter()
METRICS_ROOT = Path(__file__).resolve().parents[1] / "metrics"
_catalogs = {
    name: MetricsResponse.model_validate_json(
        (METRICS_ROOT / filename).read_text(encoding="utf-8")
    )
    for name, filename in (
        ("bilstm", "evaluaciones.json"),
        ("mbert", "mbert_evaluaciones.json"),
    )
}


NO_METRICS = (
    "Este modelo no tiene métricas publicadas: se entrenó sin una prueba propia (por ejemplo, con "
    "comun_v1, cuya prueba congelada no se abre). Sus cifras no se pueden mostrar todavía."
)
NOT_DEPLOYED = "No hay un modelo de este tipo desplegado: los análisis no lo usan."


def _empty(modelo: str, version: str, reason: str) -> MetricsResponse:
    return MetricsResponse(modelo=modelo, version=version, orden_clases=("falsa", "real"),
                           evaluaciones=[], limitaciones=[reason])


@router.get("/metricas", response_model=MetricsResponse)
async def get_metrics(
    request: Request, modelo: Literal["bilstm", "mbert"] = "bilstm"
) -> MetricsResponse:
    """Evaluaciones publicadas del modelo desplegado de ese tipo.

    Nunca se muestran las de otro modelo: si el desplegado no tiene métricas, o el tipo está
    retirado, la lista de evaluaciones va vacía con el motivo en `limitaciones`. Solo sin gestor
    de modelos (la API no pudo cargarlo) se publican las de producción de siempre.
    """
    versions = getattr(request.app.state, "model_versions", None)
    if versions is None:
        return _catalogs[modelo]
    entry = versions.selection().get(modelo)
    if entry is None:
        return _empty(modelo, "ninguno", NOT_DEPLOYED)
    return entry.load_metrics() or _empty(modelo, entry.version, NO_METRICS)
