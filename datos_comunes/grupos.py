"""Agrupación de copias y noticias relacionadas (para que no crucen entre particiones).

Copiado sin cambios de los scripts de depuración del BiLSTM de producción
(`bilstm/depurar_y_particionar.py` y `bilstm/unificar_todos.py`, ver el historial de Git),
para que el conjunto común no dependa de ellos.
"""

from __future__ import annotations

import re
import unicodedata


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def fingerprint(value: object) -> str:
    """Ignora formato, acentos, puntuación y espacios; conserva letras y cifras."""
    plain = unicodedata.normalize("NFKD", normalize(value).casefold())
    return "".join(character for character in plain if character.isalnum())


class UnionFind:
    def __init__(self, count: int):
        self.parent = list(range(count))
        self.rank = [0] * count

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left == right:
            return
        if self.rank[left] < self.rank[right]:
            left, right = right, left
        self.parent[right] = left
        if self.rank[left] == self.rank[right]:
            self.rank[left] += 1


def related_keys(row: dict) -> list[str]:
    """Vincula copias con titular diferente, cuerpo igual o titular repetido."""
    text, title = row["texto"], row["titulo"].strip()
    keys = ["texto:" + fingerprint(text)]
    if title and len(title.split()) >= 6:
        keys.append("titular:" + fingerprint(title))
    if title and text.casefold().startswith(title.casefold()):
        body = text[len(title):].strip()
        if len(body) >= 100:
            keys.append("cuerpo:" + fingerprint(body))
    if row["url"]:
        keys.append("url:" + row["url"].strip().casefold().rstrip("/"))
    return keys
