"""Contrato de la extracción de afirmaciones (incremento 2, paso 1 del plan).

Es el esquema que se fuerza al LLM: hasta MAX_CLAIMS afirmaciones verificables, cada una
reescrita para entenderse sola. Una lista vacía significa que el texto no tiene ninguna.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Tope por caso. El plan proponía 5 (docs/llm/PLAN_INCREMENTO_2.md, 4.5); se bajó a 3 (docs/llm/FUENTE_PREVIA.md).
MAX_CLAIMS = 3
# Pasajes que el juicio puede citar como respaldo de su veredicto.
MAX_CITED_PASSAGES = 3

Verdict = Literal["apoyada", "contradicha", "fuera_de_contexto", "insuficiente"]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1, le=MAX_CLAIMS)
    texto: str = Field(min_length=10, max_length=500)


class ClaimExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    afirmaciones: list[Claim] = Field(max_length=MAX_CLAIMS)


class ShortQuery(BaseModel):
    """Consulta corta (2 o 3 palabras clave) para la fuente previa; la de la búsqueda web no cambia."""

    model_config = ConfigDict(extra="forbid")

    consulta: Annotated[str, StringConstraints(min_length=2, max_length=60)]


class SearchQueries(BaseModel):
    """Paso 3: consultas de búsqueda para una afirmación (la primera, la más directa)."""

    model_config = ConfigDict(extra="forbid")

    consultas: list[Annotated[str, StringConstraints(min_length=8, max_length=200)]] = Field(
        min_length=1, max_length=2
    )


class ClaimJudgment(BaseModel):
    """Paso 4: veredicto de una afirmación ante los pasajes recuperados.

    El orden de los campos es el de la salida. Con el veredicto primero el modelo acertó más que con
    la cita primero (18 de 22 frente a 15 de 22 en docs/llm/BUSQUEDA_Y_JUICIO.md): al escribir antes
    los pasajes dejaba vacía la lista en veredictos «contradicha», que el backend descarta.
    """

    model_config = ConfigDict(extra="forbid")

    veredicto: Verdict
    pasajes: list[Annotated[int, Field(ge=1, le=20)]] = Field(max_length=MAX_CITED_PASSAGES)
    cita: str = Field(max_length=400)


class CaseSummary(BaseModel):
    """Paso 5: resumen breve del resultado. La conclusión ya está decidida; el modelo solo la explica."""

    model_config = ConfigDict(extra="forbid")

    resumen: str = Field(min_length=40, max_length=600)
