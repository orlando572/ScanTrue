"""Estado del registro de un análisis en la cadena local."""

from typing import Literal

from pydantic import BaseModel


class VerificationResponse(BaseModel):
    estado_blockchain: Literal["no_iniciado", "pendiente", "confirmado", "fallido"]
    hash_transaccion: str | None
    verificado: bool | None
    detalle: str
