"""Utilidades de texto compartidas por los pasos de la verificación."""

import unicodedata


def fold(text: str) -> str:
    """Minúsculas y sin tildes: «Juárez» y «Juarez» cuentan como la misma palabra."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
