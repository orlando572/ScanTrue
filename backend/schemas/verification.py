"""Contrato de la extracción de afirmaciones (incremento 2, paso 1 del plan).

Es el esquema que se fuerza al LLM: hasta MAX_CLAIMS afirmaciones verificables, cada una
reescrita para entenderse sola. Una lista vacía significa que el texto no tiene ninguna.
"""

from pydantic import BaseModel, ConfigDict, Field

# Tope por caso propuesto en el plan (docs/llm/PLAN_INCREMENTO_2.md, 4.5); se ajusta en la Fase 5.
MAX_CLAIMS = 5


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1, le=MAX_CLAIMS)
    texto: str = Field(min_length=10, max_length=500)


class ClaimExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    afirmaciones: list[Claim] = Field(max_length=MAX_CLAIMS)
