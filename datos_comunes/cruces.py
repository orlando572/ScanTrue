"""Casi duplicados y cruces con el conjunto común (comun_v1).

Usa la misma regla de casi duplicado que `construir_comun.agrupar`: dos textos son la misma
noticia si comparten al menos 5 tejas de 5 palabras y esas tejas son al menos el 65 % de
las del texto más corto. Así, una noticia del panel que contiene un fragmento de comun_v1
(o al revés) cuenta como cruce.

`IndiceComun` lee los CSV de `datasets/comun_v1/` solo para buscar cruces: no usa sus
etiquetas ni evalúa nada, así que no «abre» la prueba congelada en el sentido del plan
(sus métricas se miran una sola vez, en `prueba_congelada.py`). Se lee con `csv` y no con
`comun.leer()` para no depender de pandas ni de su candado.

Solo usa la biblioteca estándar.
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from datos_comunes.grupos import fingerprint

TAMANO_TEJA = 5
MIN_COMPARTIDAS = 5
MIN_PROPORCION = 0.65
CONGELADA = "congelada"
ARCHIVOS = ("fragmentos_desarrollo.csv", "fragmentos_prueba_congelada.csv",
            "ablacion_satira.csv", "ablacion_usmsc.csv", "ablacion_politica.csv")
_PALABRA = re.compile(r"\w+")


def tejas(texto: str) -> frozenset[int]:
    palabras = _PALABRA.findall(texto.casefold())
    return frozenset(hash(teja) for teja in zip(*(palabras[i:] for i in range(TAMANO_TEJA))))


def parecidas(a: frozenset[int], b: frozenset[int]) -> bool:
    menor = min(len(a), len(b))
    if not menor:
        return False
    compartidas = len(a & b)
    return compartidas >= MIN_COMPARTIDAS and compartidas / menor >= MIN_PROPORCION


@dataclass(frozen=True)
class Cruce:
    archivo: str
    grupo: str
    pliegue: str

    @property
    def congelada(self) -> bool:
        return self.pliegue == CONGELADA


class IndiceComun:
    """Huellas y tejas de todos los fragmentos de comun_v1, para buscar cruces."""

    def __init__(self, filas: list[dict]):
        self._filas = [(f["archivo"], f["grupo"], f["pliegue"]) for f in filas]
        self._huellas: dict[str, int] = {}
        self._tejas: list[frozenset[int]] = []
        self._indice: dict[int, list[int]] = {}
        for posicion, fila in enumerate(filas):
            self._huellas.setdefault(fingerprint(fila["texto"]), posicion)
            conjunto = tejas(fila["texto"])
            self._tejas.append(conjunto)
            for teja in conjunto:
                self._indice.setdefault(teja, []).append(posicion)

    @classmethod
    def cargar(cls, carpeta: Path) -> "IndiceComun | None":
        """None si la carpeta no existe (por ejemplo, en un clon sin datasets/)."""
        if not (carpeta / ARCHIVOS[0]).is_file():
            return None
        csv.field_size_limit(sys.maxsize)
        filas = []
        for nombre in ARCHIVOS:
            ruta = carpeta / nombre
            if not ruta.is_file():
                continue
            with ruta.open(encoding="utf-8", newline="") as stream:
                for fila in csv.DictReader(stream):
                    filas.append({"archivo": nombre, "grupo": fila["grupo"],
                                  "pliegue": fila.get("pliegue") or "", "texto": fila["texto"]})
        return cls(filas)

    def __len__(self) -> int:
        return len(self._filas)

    def cruces(self, texto: str) -> list[Cruce]:
        """Fragmentos de comun_v1 que son el mismo texto o un casi duplicado de `texto`."""
        encontrados: set[int] = set()
        exacta = self._huellas.get(fingerprint(texto))
        if exacta is not None:
            encontrados.add(exacta)
        consulta = tejas(texto)
        cuentas: dict[int, int] = {}
        for teja in consulta:
            for posicion in self._indice.get(teja, ()):
                cuentas[posicion] = cuentas.get(posicion, 0) + 1
        for posicion, compartidas in cuentas.items():
            menor = min(len(consulta), len(self._tejas[posicion]))
            if compartidas >= MIN_COMPARTIDAS and menor and compartidas / menor >= MIN_PROPORCION:
                encontrados.add(posicion)
        return sorted({Cruce(*self._filas[p]) for p in encontrados},
                      key=lambda c: (c.archivo, c.grupo))
