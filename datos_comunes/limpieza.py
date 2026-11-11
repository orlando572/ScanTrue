"""Normalización y limpieza de marcas de procedencia del conjunto común (plan común §3.2).

La lista de patrones se revisó a mano sobre v1, FakeDeS y Polyglot (7 nov 2026).
Cada patrón tiene nombre para poder contar en el manifiesto cuántas filas cambió.
"""

from __future__ import annotations

import html
import re
import unicodedata

AGENCIAS = (r"apro|EFE|Efe|AFP|AP|Europa Press|EUROPA PRESS|EP|Reuters|REUTERS|Notimex|"
            r"NOTIMEX|proceso\.com\.mx|CNNMoney|CNN|DPA|dpa|ANSA|Sputnik|RT|Xinhua|"
            r"Prensa Latina|Télam|Telam|Infobae|EL UNIVERSAL|El Universal")
_LUGAR = r"[A-ZÁÉÍÓÚÑ][\w\.]*(?:,?\s+(?:de\s+|del\s+|DE\s+|DEL\s+)?[A-ZÁÉÍÓÚÑ][\w\.]*){0,4}"
_FECHA = r"(?:(?:\d{1,2}|\*NUMBER\*)\s+[A-Za-zé]{3,10}\.?\s*(?:\d{4}|\*NUMBER\*)?\s*)"

# (nombre, expresión, reemplazo). El orden importa: las fechas usan *NUMBER* antes de quitarlo.
# Se aplican antes de separar párrafos pegados, para no partir usuarios ni enlaces.
PATRONES_PREVIOS: list[tuple[str, re.Pattern, str]] = [
    ("url", re.compile(r"(?:https?://|www\.|pic\.twitter\.com/)\S+"), " "),
    ("mencion_arroba", re.compile(r"\(?(?<![\w@])@\w+\)?"), " "),
]

PATRONES: list[tuple[str, re.Pattern, str]] = [
    ("dateline_agencia", re.compile(
        rf"(?:{_LUGAR},?\s*)?{_FECHA}?\((?:{AGENCIAS})\)\s*\.?\s*[-–—]+\s*"), " "),
    ("dateline_inicio", re.compile(rf"^\s*{_LUGAR}\s*\.\s*[-–—]+\s*"), ""),
    ("marca_number_v1", re.compile(r"\*NUMBER\*"), " "),
    ("hashtags_cierre", re.compile(r"(?:\s*#\w+)+[\s.]*$"), ""),
    ("trust_project", re.compile(
        r"Conforme a los criterios de\s*(?:The Trust Project)?\s*"
        r"(?:El director de El Mundo selecciona las noticias de mayor interés para ti\.?)?"), " "),
    ("suscripcion_el_mundo", re.compile(
        r"Hazte Premium desde 1\s?€ el primer mes\s*Aprovecha esta oferta por tiempo limitado "
        r"y accede a todo el contenido web|Para seguir leyendo gratis\s*O suscríbete a Premium "
        r"y tendrás acceso a todo el contenido web de El Mundo|El director de El Mundo "
        r"selecciona las noticias de mayor interés para ti\.?"), " "),
    ("etiqueta_opinion", re.compile(
        r"^\s*Transmite ideas y extrae conclusiones basadas en la interpretación de hechos "
        r"y datos por parte del autor\.?"), " "),
    ("fuente_sin_noticias", re.compile(r"(?:Fuente)?\s*Noticias relevantes no encontradas\.?"), " "),
    ("descargo_rt", re.compile(
        r"Las declaraciones y opiniones expresadas en este artículo son de exclusiva "
        r"responsabilidad de su autor y no representan necesariamente el punto de vista de RT\.?"),
     " "),
    ("pie_compartir_seguir", re.compile(
        r"Si te ha (?:gustado|parecido interesante),?\s*¡?compártelo con tus amigos!?|"
        r"¡?Comparte (?:esta|la) (?:noticia|nota|información)[.!]?|"
        r"Síguenos en (?:Telegram|Facebook|Twitter|Instagram|YouTube|WhatsApp|"
        r"nuestras redes(?: sociales)?)[.!]?", re.IGNORECASE), " "),
    ("enlace_relacionado", re.compile(
        r"\b(?:Lee también|Lea también|Lea más|Leer más|Te puede interesar)\s*:?|"
        r"\b(?:También )?te recomendamos(?: leer)?\s*:", re.IGNORECASE), " "),
    ("credito_imagen", re.compile(
        r"Derechos de autor de la imagen\s*[^.]{0,60}?\s*Image caption|Image caption|"
        r"\(\s*Fotos?\s*:[^)]{0,80}\)|\bFotos?\s*:\s*(?:@\w+\.?|(?:[A-ZÁÉÍÓÚÑ][\w']*\s?){1,4})|"
        r"(?:\b[A-ZÁÉÍÓÚÑ]{2,}(?: [A-ZÁÉÍÓÚÑ]{2,}){1,2} )?Ampliar la imagen"), " "),
    ("creditos_redaccion", re.compile(
        r"\b(?:Redacción|Infografía|Dirección de arte|Ilustración|Edición|Diseño)\s*:\s*[^.]{1,80}\."),
     " "),
    ("firma_por", re.compile(
        r"(?:✒️\s*FIRMAS:\s*)?(?<![\w])Por (?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:[- ][A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,2})"
        r"(?:\s*\(@\w+\))?(?=\s*$|\s+[A-ZÁÉÍÓÚÑ¿¡]|\s*\()"), " "),
    ("con_informacion_de", re.compile(r"\(?Con información de[^.)]{0,60}\)?\.?\s*$"), ""),
]

_COMILLAS = re.compile(r"['\"]{2,}")
_PEGADO_MINUSCULA = re.compile(r"(?<=[a-záéíóúñü]{3})(?=[A-ZÁÉÍÓÚÑ][a-záéíóúñü])")
_PEGADO_PUNTO = re.compile(r"(?<=[a-záéíóúñü)\"»”][.!?])(?=[A-ZÁÉÍÓÚÑ¿¡])")
_ESPACIOS = re.compile(r"\s+")


def normalizar(texto: str, ejemplos: dict | None = None) -> tuple[str, list[str]]:
    """NFC, entidades HTML, comillas escapadas, espacios y párrafos pegados.

    Enlaces y menciones se quitan antes de separar párrafos pegados.
    """
    cambios = []
    texto = unicodedata.normalize("NFC", html.unescape(str(texto or "")))
    texto, n = _COMILLAS.subn('"', texto)
    if n:
        cambios.append("comillas_escapadas")
    texto = _ESPACIOS.sub(" ", texto).strip()
    texto = _aplicar(texto, PATRONES_PREVIOS, cambios, ejemplos)
    texto, n1 = _PEGADO_MINUSCULA.subn(" ", texto)
    texto, n2 = _PEGADO_PUNTO.subn(" ", texto)
    if n1 or n2:
        cambios.append("parrafos_pegados")
    return _ESPACIOS.sub(" ", texto).strip(), cambios


def _aplicar(texto: str, patrones, aplicados: list[str], ejemplos: dict | None) -> str:
    for nombre, patron, reemplazo in patrones:
        coincidencia = patron.search(texto)
        if not coincidencia:
            continue
        nuevo = _ESPACIOS.sub(" ", patron.sub(reemplazo, texto)).strip()
        if nuevo == texto:
            continue
        if ejemplos is not None and len(ejemplos.setdefault(nombre, [])) < 20:
            inicio, fin = max(0, coincidencia.start() - 60), coincidencia.end() + 60
            antes = texto[inicio:fin]
            ejemplos[nombre].append((antes, _ESPACIOS.sub(" ", patron.sub(reemplazo, antes)).strip()))
        aplicados.append(nombre)
        texto = nuevo
    return texto


def limpiar(texto: str, ejemplos: dict | None = None) -> tuple[str, list[str]]:
    """Devuelve el texto limpio y la lista de patrones que lo cambiaron.

    Si se pasa `ejemplos`, guarda hasta 20 pares (antes, después) por patrón.
    """
    texto, aplicados = normalizar(texto, ejemplos)
    texto = _aplicar(texto, PATRONES, aplicados, ejemplos)
    return texto, aplicados


# --------------------------------------------------------------------------- idioma

# Palabras funcionales exclusivas de cada idioma (sin las que comparten español, francés,
# italiano y portugués, como «la», «de», «que», «una» o «con»).
_FUNCIONALES = {
    "es": frozenset("el los las y del por para como pero sus fue este esta está hay entre sobre "
                    "desde cuando muy ya también porque según tras".split()),
    "en": frozenset("the and of to in is that for it with as was on are by this be from at".split()),
    "fr": frozenset("le les des est dans pour pas qui sur au avec sont ont aux cette être".split()),
    "it": frozenset("il di che è della sono gli nel alla dei delle anche questo più stato".split()),
    "pt": frozenset("não com os das dos em ao pela pelo são foi mais uma".split()),
    "ca": frozenset("els amb però això aquest aquesta són dels pel perquè molt seva seu".split()),
}
MIN_EVIDENCIA = 3
_PALABRA = re.compile(r"\w+")


def idioma_probable(texto: str) -> str:
    """Idioma con más palabras funcionales exclusivas que el español.

    Devuelve «es» si el español empata o gana, o si el otro idioma tiene menos de
    `MIN_EVIDENCIA` palabras (los textos cortos de USMSC dan cuentas de 1 o 2 por azar).
    """
    palabras = _PALABRA.findall(texto.lower())
    cuentas = {idioma: sum(p in lista for p in palabras) for idioma, lista in _FUNCIONALES.items()}
    otro = max((i for i in cuentas if i != "es"), key=cuentas.get)
    if cuentas[otro] > cuentas["es"] and cuentas[otro] >= MIN_EVIDENCIA:
        return otro
    return "es"
