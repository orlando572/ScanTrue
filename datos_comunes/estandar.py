"""Estándar de fila de los datasets de ScanTrue (el de `datasets/comun_v1/`).

Cualquier fuente nueva (hoy, los casos revisados en el panel) se convierte con este
módulo en filas con las mismas columnas que el conjunto común, para que
`datos_comunes/comun.py` y los scripts de entrenamiento las lean sin cambios.

Reglas de longitud (medidas en comun_v1.1: cada noticia suma de media 402 tokens entre
sus fragmentos, mediana 317; los modelos leen unos 200):
- Cada noticia se limita a `TOPE_NOTICIA` tokens (la media de comun_v1 sumando sus
  fragmentos), cortando en el último fin de oración que cabe.
- Se parte en fragmentos de `MIN_TOKENS`–`MAX_TOKENS_FRAGMENTO` tokens (lo que leen los
  modelos), hechos de oraciones completas: cada fragmento empieza al inicio de una
  oración y termina en `.`, `!`, `?` o `…`. Nunca queda una oración a medias.
- Cada fragmento pesa 1/n: la noticia cuenta una vez, tenga los fragmentos que tenga.

Solo usa la biblioteca estándar (el backend lo importa sin PyTorch ni NumPy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from datos_comunes.limpieza import idioma_probable, limpiar

COLUMNAS_BASE = ("id_fragmento", "id_articulo", "grupo", "fuente", "dominio", "texto",
                 "etiqueta_falsa", "peso", "tokens_bilstm", "pliegue")
MIN_TOKENS = 100
MAX_TOKENS_FRAGMENTO = 200
TOPE_NOTICIA = 400
# Un trozo inicial sin puntuación y así de corto se toma como titular (va al principio
# del primer fragmento, como en comun_v1); en cualquier otro sitio es una oración cortada.
MAX_TOKENS_TITULAR = 30
# Cada fragmento de más «cuesta» estos tokens: se prefiere 2 fragmentos de ~190 a 3 de ~130
# aunque se quede fuera alguna oración suelta.
COSTE_FRAGMENTO = 50

# Mismo tokenizador que bilstm/modelo.py (TOKEN_PATTERN), sin importar PyTorch.
TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)
# Fin de oración: signos finales y cierres de comillas o paréntesis, seguidos de espacio o
# del final. Si lo que sigue empieza en minúscula no es fin de oración («etc. y», «Sr. tal»).
_FIN = re.compile(r"[.!?…]+[\"'”’»)\]]*(?=\s|$)")
# Siglas de letra doblada (EE. UU., FF. AA.): su punto no cierra la oración.
_SIGLA_DOBLADA = re.compile(r"\b([A-ZÁÉÍÓÚÑ])\1\.$")
_INICIO_MINUSCULA = re.compile(r"^[\"'“‘«(\[¿¡\s]*[a-záéíóúñü]")

MOTIVOS = ("no_espanol", "sin_fin_de_oracion", "menos_de_100_tokens", "oraciones_demasiado_largas")


def contar_tokens(texto: str) -> int:
    return len(TOKEN_PATTERN.findall(texto))


def separar_oraciones(texto: str) -> tuple[list[str], str]:
    """Oraciones completas y el resto final sin cerrar (vacío si el texto acaba en punto)."""
    oraciones, inicio = [], 0
    for fin in _FIN.finditer(texto):
        siguiente = texto[fin.end():].lstrip()[:1]
        if siguiente and (siguiente.islower() or _SIGLA_DOBLADA.search(texto, 0, fin.end())):
            continue
        oracion = texto[inicio:fin.end()].strip()
        if TOKEN_PATTERN.search(oracion):
            oraciones.append(oracion)
        inicio = fin.end()
    resto = texto[inicio:].strip()
    return oraciones, resto if TOKEN_PATTERN.search(resto) else ""


@dataclass
class Noticia:
    """Resultado de pasar una noticia por el estándar."""

    fragmentos: list[str] = field(default_factory=list)
    motivo: str | None = None              # por qué quedó fuera (uno de MOTIVOS)
    patrones: list[str] = field(default_factory=list)   # patrones de limpieza que la cambiaron
    recortes: list[str] = field(default_factory=list)   # qué se quitó para cumplir las reglas
    tokens_limpios: int = 0                # antes del tope
    tokens: int = 0                        # suma de los fragmentos

    @property
    def peso(self) -> float:
        return 1.0 / len(self.fragmentos) if self.fragmentos else 0.0


def _particionar(tokens: list[int], minimo: int, maximo: int) -> list[tuple[int, int]]:
    """Tramos [i, j) de oraciones seguidas, cada uno de `minimo`–`maximo` tokens.

    Programación dinámica sobre las oraciones: maximiza los tokens conservados menos
    `COSTE_FRAGMENTO` por fragmento y, a igualdad, reparte los fragmentos lo más parejos
    posible. Una oración que no cabe en ningún fragmento (más de `maximo`) se salta.
    """
    n = len(tokens)
    vacio = (-(10**9), 0)
    # mejor[i] = (tokens conservados - coste, -suma de cuadrados) del prefijo i; y cómo se llegó.
    mejor: list[tuple[int, int]] = [(0, 0)] + [vacio] * n
    paso: list[tuple[int, bool]] = [(0, False)] * (n + 1)
    for i in range(n):
        if mejor[i] == vacio:
            continue
        saltar = mejor[i]
        if saltar > mejor[i + 1]:
            mejor[i + 1], paso[i + 1] = saltar, (i, False)
        suma = 0
        for j in range(i, n):
            suma += tokens[j]
            if suma > maximo:
                break
            if suma >= minimo:
                valor, neg_sq = mejor[i]
                candidato = (valor + suma - COSTE_FRAGMENTO, neg_sq - suma * suma)
                if candidato > mejor[j + 1]:
                    mejor[j + 1], paso[j + 1] = candidato, (i, True)
    tramos, j = [], n
    while j > 0:
        i, es_tramo = paso[j]
        if es_tramo:
            tramos.append((i, j))
        j = i
    return tramos[::-1]


def preparar_noticia(
    partes: list[str],
    *,
    tope_noticia: int = TOPE_NOTICIA,
    minimo: int = MIN_TOKENS,
    maximo: int = MAX_TOKENS_FRAGMENTO,
) -> Noticia:
    """Limpia, comprueba el idioma, aplica el tope y parte en fragmentos de oraciones completas.

    `partes` son los fragmentos tal como se marcaron en la página (o el texto entero como
    única parte). El borde entre dos partes cuenta como borde de oración: una parte que
    empieza o acaba a media oración pierde ese trozo.
    """
    resultado = Noticia()
    limpias = []
    for parte in partes:
        texto, aplicados = limpiar(parte)
        resultado.patrones.extend(nombre for nombre in aplicados if nombre not in resultado.patrones)
        if texto:
            limpias.append(texto)
    completo = " ".join(limpias)
    resultado.tokens_limpios = contar_tokens(completo)
    if idioma_probable(completo) != "es":
        resultado.motivo = "no_espanol"
        return resultado

    oraciones: list[str] = []
    titular = ""
    for indice, parte in enumerate(limpias):
        frases, resto = separar_oraciones(parte)
        if not frases and indice == 0 and contar_tokens(resto) <= MAX_TOKENS_TITULAR:
            titular = resto
            continue
        if frases and _INICIO_MINUSCULA.match(frases[0]):
            frases = frases[1:]
            resultado.recortes.append("inicio_incompleto")
        if resto:
            resultado.recortes.append("final_incompleto")
        oraciones.extend(frases)
    if titular and oraciones:
        oraciones[0] = f"{titular} {oraciones[0]}"
    if not oraciones:
        resultado.motivo = "sin_fin_de_oracion"
        return resultado

    tokens = [contar_tokens(oracion) for oracion in oraciones]
    if sum(tokens) < minimo:
        resultado.motivo = "menos_de_100_tokens"
        return resultado
    # Tope por noticia: el prefijo de oraciones completas que cabe en `tope_noticia`.
    acumulado, corte = 0, 0
    for cuenta in tokens:
        if acumulado + cuenta > tope_noticia:
            break
        acumulado += cuenta
        corte += 1
    if corte < len(oraciones):
        resultado.recortes.append("tope_noticia")
    oraciones, tokens = oraciones[:corte], tokens[:corte]

    tramos = _particionar(tokens, minimo, maximo)
    usadas = sum(j - i for i, j in tramos)
    if usadas < len(oraciones):
        resultado.recortes.append("oraciones_sueltas")
    resultado.fragmentos = [" ".join(oraciones[i:j]) for i, j in tramos]
    resultado.tokens = sum(sum(tokens[i:j]) for i, j in tramos)
    if not resultado.fragmentos:
        resultado.motivo = ("menos_de_100_tokens" if acumulado < minimo
                            else "oraciones_demasiado_largas")
    return resultado


def filas_estandar(
    noticia: Noticia,
    *,
    id_articulo: str,
    grupo: str,
    fuente: str,
    dominio: str,
    etiqueta_falsa: int,
    pliegue: str,
) -> list[dict]:
    """Filas con `COLUMNAS_BASE` (una por fragmento), en el mismo formato que comun_v1."""
    if etiqueta_falsa not in (0, 1):
        raise ValueError("etiqueta_falsa debe ser 0 (real) o 1 (falsa)")
    return [
        {
            "id_fragmento": f"{id_articulo}#{n}",
            "id_articulo": id_articulo,
            "grupo": grupo,
            "fuente": fuente,
            "dominio": dominio,
            "texto": texto,
            "etiqueta_falsa": etiqueta_falsa,
            "peso": noticia.peso,
            "tokens_bilstm": contar_tokens(texto),
            "pliegue": pliegue,
        }
        for n, texto in enumerate(noticia.fragmentos)
    ]
