"""Paso 1 de la verificación: extraer afirmaciones y descartar las que inventan datos.

El LLM, aunque se le pida lo contrario, a veces completa de memoria una cifra que el texto no
trae, o añade un nombre o un lugar que no aparece. Como una afirmación con un dato inventado
llevaría la búsqueda y el juicio por mal camino, se comprueba de forma determinista que cada
cifra y cada nombre propio de la afirmación estén en el texto, y las que no cumplen se descartan.

Además se descartan las afirmaciones que dependen del texto («el texto», «esta noticia», «dicho
país», «las comunidades mencionadas»): se verifican solas, sin el resto de la noticia, y una
referencia así no se puede buscar ni comparar con otras afirmaciones.

Limitaciones conocidas (docs/llm/MEDICIONES_LLM.md):
- Una cifra escrita con letras («doce») en el texto y con dígitos en la afirmación se descarta
  por error, y lo mismo una deducción acertada como «Colombia» a partir de «Barranquilla».
  Se prefiere perder una afirmación a verificar un dato que el texto no dice.
- No detecta atribuciones cambiadas ni monedas cambiadas: eso lo mide la evaluación de la Fase 7.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from backend.schemas.verification import Claim, ClaimExtraction
from backend.services.llm_client import LlmClient
from backend.services.verification.prompts import extraction_messages

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
CAPITALIZED = re.compile(r"[A-ZÁÉÍÓÚÑÜ][\wáéíóúñü-]{2,}")
WORD = re.compile(r"[\wáéíóúñü]+")
# Salida típica medida: 209–371 tokens con 5 afirmaciones.
EXTRACTION_MAX_TOKENS = 600
# Referencias al texto de origen. «dicho que» (de «decir») no cuenta; «dicho país» sí.
TEXT_REFERENCE = re.compile(
    r"\b(?:el texto|la noticia|esta noticia|este art[ií]culo|el art[ií]culo|mencionad[oa]s?"
    r"|dich[oa]s?(?!\s+que\b)\s+\w+)",
    re.IGNORECASE,
)


def fold(text: str) -> str:
    """Minúsculas y sin tildes: «Juárez» y «Juarez» cuentan como la misma palabra."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def number_key(raw: str) -> str:
    """«2.000», «2,000» y «2000» son la misma cifra; «3,5» es un decimal."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return re.sub(r"[.,]", "", raw)
    return raw.replace(",", ".")


def unsupported_numbers(claim: str, source: str) -> list[str]:
    """Cifras de la afirmación que no aparecen en el texto."""
    present = {number_key(n) for n in NUMBER.findall(source)}
    return [n for n in NUMBER.findall(claim) if number_key(n) not in present]


def unsupported_names(claim: str, source: str) -> list[str]:
    """Palabras con mayúscula inicial de la afirmación que no aparecen en el texto.

    La primera palabra se ignora: va con mayúscula por ser inicio de oración, no por ser un nombre.
    """
    words = set(WORD.findall(fold(source)))
    missing = []
    for index, name in enumerate(CAPITALIZED.findall(claim)):
        if index == 0 and claim.startswith(name):
            continue
        if not all(part in words for part in WORD.findall(fold(name))):
            missing.append(name)
    return missing


def text_reference(claim: str) -> str | None:
    """La referencia al texto de origen que contiene la afirmación, si la hay."""
    match = TEXT_REFERENCE.search(claim)
    return match.group(0) if match else None


@dataclass(frozen=True)
class RejectedClaim:
    texto: str
    motivo: str  # "cifra_ausente", "nombre_ausente" o "depende_del_texto"
    detalle: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractionResult:
    """`afirmaciones` son las que pasaron la comprobación, numeradas de nuevo desde 1.

    Si quedan vacías pero `rechazadas` no, el modelo sí encontró afirmaciones y todas inventaban
    algún dato: no es lo mismo que un texto sin afirmaciones comprobables.
    """

    afirmaciones: list[Claim]
    rechazadas: list[RejectedClaim]


def check_claims(extraction: ClaimExtraction, source: str) -> ExtractionResult:
    kept: list[str] = []
    rejected: list[RejectedClaim] = []
    for claim in extraction.afirmaciones:
        numbers = unsupported_numbers(claim.texto, source)
        names = unsupported_names(claim.texto, source)
        if numbers:
            rejected.append(RejectedClaim(claim.texto, "cifra_ausente", numbers))
        elif names:
            rejected.append(RejectedClaim(claim.texto, "nombre_ausente", names))
        elif reference := text_reference(claim.texto):
            rejected.append(RejectedClaim(claim.texto, "depende_del_texto", [reference]))
        else:
            kept.append(claim.texto)
    return ExtractionResult(
        afirmaciones=[Claim(id=i, texto=text) for i, text in enumerate(kept, start=1)],
        rechazadas=rejected,
    )


def extract_claims(client: LlmClient, text: str) -> ExtractionResult:
    """Pide las afirmaciones al LLM y descarta las que no están respaldadas por el texto.

    Propaga `LlmUnavailable` y `LlmInvalidResponse` del cliente sin tocarlas.
    """
    extraction = client.complete_json(
        extraction_messages(text), ClaimExtraction, max_tokens=EXTRACTION_MAX_TOKENS
    )
    return check_claims(extraction, text)
