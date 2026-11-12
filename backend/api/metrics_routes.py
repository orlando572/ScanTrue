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


@router.get("/metricas", response_model=MetricsResponse)
async def get_metrics(
    request: Request, modelo: Literal["bilstm", "mbert"] = "bilstm"
) -> MetricsResponse:
    """Devuelve las evaluaciones publicadas de la versión activa de cada modelo."""
    versions = getattr(request.app.state, "model_versions", None)
    active = versions.active_metrics(modelo) if versions is not None else None
    return active or _catalogs[modelo]
