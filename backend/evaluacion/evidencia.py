"""Evidencia en vivo y congelada (docs/llm/PLAN_INCREMENTO_2.md, 5.3, D14).

- **En vivo:** búsqueda y descarga reales; cada respuesta y cada página se guardan.
- **Congelado:** se leen solo las copias guardadas, así que un cambio de instrucciones o de modelo se
  compara en igualdad de condiciones. Lo que no se guardó **no se busca**: una búsqueda que falta devuelve
  «sin resultados» y una página que falta falla como una descarga fallida, y las dos se **cuentan**
  (`misses`). El LLM, aunque se pida con temperatura 0, no es idéntico de una corrida a otra: una extracción
  distinta produce una consulta que no estaba guardada. Si las faltas son pocas la comparación vale; si son
  muchas, hay que volver a grabar en vivo.

La copia es solo local (`datasets/verificacion_v1/evidencia_congelada/<nombre>/`, fuera de Git): no se
publica ni se sube. Se guardan también las fallas de descarga, para que repetirlas dé lo mismo. Cada
página lleva el SHA-256 de los bytes que se leyeron.
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from backend.services.verification.fetch import FetchedPage, FetchError
from backend.services.verification.search import SearchError, SearchProvider, SearchResult

Mode = Literal["en_vivo", "congelado"]


def _key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.searches = root / "busquedas"
        self.pages = root / "paginas"
        self._by_final: dict[str, str | None] | None = None

    def read(self, folder: Path, key: str) -> dict | None:
        path = folder / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def write(self, folder: Path, key: str, data: dict) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{key}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def page_text(self, url: str) -> str | None:
        """El texto guardado de una página (por la dirección pedida o por la final tras redirecciones)."""
        data = self.read(self.pages, _key("pagina", url))
        if data is not None:
            return data.get("texto")
        if self._by_final is None:
            self._by_final = {}
            for path in self.pages.glob("*.json") if self.pages.is_dir() else []:
                item = json.loads(path.read_text(encoding="utf-8"))
                if item.get("url_final"):
                    self._by_final[item["url_final"]] = item.get("texto")
        return self._by_final.get(url)


class FrozenSearch:
    """`SearchProvider` que graba (en vivo) o reproduce (congelado) las búsquedas."""

    name = "congelada"

    def __init__(self, store: EvidenceStore, mode: Mode, live: SearchProvider | None = None) -> None:
        if mode == "en_vivo" and live is None:
            raise ValueError("El modo en vivo necesita un proveedor de búsqueda.")
        self.store, self.mode, self.live = store, mode, live
        self.misses = 0

    def search(self, query: str, *, max_results: int = 5, exclude_domains: Sequence[str] = ()) -> list[SearchResult]:
        key = _key("busqueda", " ".join(query.split()).lower(), max_results, sorted(d.lower() for d in exclude_domains))
        saved = self.store.read(self.store.searches, key)
        if saved is not None:
            if saved.get("error"):
                raise SearchError(saved["error"]["mensaje"], saved["error"]["codigo"])
            return [SearchResult(**item) for item in saved["resultados"]]
        if self.mode == "congelado":
            self.misses += 1
            return []
        try:
            results = self.live.search(query, max_results=max_results, exclude_domains=exclude_domains)
        except SearchError as error:
            self.store.write(self.store.searches, key, {"consulta": query, "error": {"codigo": error.code, "mensaje": str(error)}})
            raise
        self.store.write(
            self.store.searches, key,
            {"consulta": query, "registrado_en": datetime.now(timezone.utc).isoformat(), "resultados": [r.__dict__ for r in results]},
        )
        return results


class FrozenFetcher:
    """Igual que `PageFetcher.fetch`, pero grabando o reproduciendo las páginas."""

    def __init__(self, store: EvidenceStore, mode: Mode, live=None) -> None:
        if mode == "en_vivo" and live is None:
            raise ValueError("El modo en vivo necesita un descargador de páginas.")
        self.store, self.mode, self.live = store, mode, live
        self.misses = 0

    def fetch(self, url: str) -> FetchedPage:
        key = _key("pagina", url)
        saved = self.store.read(self.store.pages, key)
        if saved is not None:
            if saved.get("error"):
                raise FetchError(saved["error"]["mensaje"], saved["error"]["codigo"])
            return FetchedPage(
                url=saved["url_final"], titulo=saved["titulo"], texto=saved["texto"],
                consultada_en=datetime.fromisoformat(saved["consultada_en"]), sha256=saved["sha256"], truncada=saved["truncada"],
            )
        if self.mode == "congelado":
            self.misses += 1
            raise FetchError("Esta página no estaba en la evidencia congelada.", "no_congelada")
        try:
            page = self.live.fetch(url)
        except FetchError as error:
            self.store.write(self.store.pages, key, {"url": url, "error": {"codigo": error.code, "mensaje": str(error)}})
            raise
        self.store.write(
            self.store.pages, key,
            {"url": url, "url_final": page.url, "titulo": page.titulo, "texto": page.texto, "sha256": page.sha256,
             "truncada": page.truncada, "consultada_en": page.consultada_en.isoformat()},
        )
        return page
