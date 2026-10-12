"""Normaliza artefactos de presentación sin reescribir una noticia."""

import html
import re
import unicodedata


HEADING_MARKER = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+")
HTML_ENTITY = re.compile(r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);")
EMPHASIS_MARKER = re.compile(
    r"(?<!\w)(\*\*|__)(?=\S)([^\n*_]*?\S)([ \t]*)\1"
)
INVISIBLE_FORMAT = re.compile("[\u200b\u2060\ufeff]")
WHITESPACE = re.compile(r"\s+")


def clean_news_text(value: str) -> str:
    """Devuelve texto plano para los modelos, preservando palabras y cifras."""
    text = value
    while (decoded := HTML_ENTITY.sub(lambda match: html.unescape(match[0]), text)) != text:
        text = decoded
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE_FORMAT.sub(" ", text)
    text = HEADING_MARKER.sub("", text)
    text = EMPHASIS_MARKER.sub(lambda match: match[2] + match[3], text)
    return WHITESPACE.sub(" ", text).strip()
