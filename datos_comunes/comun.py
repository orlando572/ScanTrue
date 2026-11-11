"""Carga del conjunto común por pliegue (plan común §4.1). Sirve a cualquier modelo.

Reglas que aplica:
- Verifica el SHA-256 de cada CSV contra `manifest.json`.
- Entrenamiento = fuentes del pliegue menos los grupos que aparecen en la fuente que queda fuera.
- Validación interna = 10 % de los grupos del entrenamiento (fija por pliegue, no depende de la semilla).
- Los brazos de ablación solo se añaden al entrenamiento, sin filas de la fuente que queda fuera
  ni de grupos de la validación (externa o interna).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONJUNTO = ROOT / "datasets/comun_v1"
PLIEGUES = {"F1": "v1", "F2": "fakedes", "F3": "polyglot"}
BRAZOS = {"satira": "ablacion_satira.csv", "usmsc": "ablacion_usmsc.csv",
          "politica": "ablacion_politica.csv"}
SEMILLA_INTERNA = 42
FRACCION_INTERNA = 0.10


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for bloque in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(bloque)
    return hasher.hexdigest()


def manifiesto(conjunto: Path = CONJUNTO) -> dict:
    return json.loads((conjunto / "manifest.json").read_text("utf-8"))


def leer(nombre: str, conjunto: Path = CONJUNTO) -> pd.DataFrame:
    """Lee un CSV del conjunto y falla si su hash no coincide con el manifiesto."""
    if nombre == "fragmentos_prueba_congelada.csv":
        raise PermissionError("La prueba congelada solo se abre en el paso final del plan")
    path = conjunto / nombre
    esperado = manifiesto(conjunto)["archivos"][nombre]["sha256"]
    real = sha256(path)
    if real != esperado:
        raise ValueError(f"SHA-256 de {nombre} no coincide con manifest.json: {real} != {esperado}")
    frame = pd.read_csv(path, dtype={"id_fragmento": str, "id_articulo": str, "grupo": str,
                                     "fuente": str, "dominio": str, "texto": str, "pliegue": str},
                        keep_default_na=False)
    frame["etiqueta_falsa"] = frame["etiqueta_falsa"].astype(int)
    frame["peso"] = frame["peso"].astype(float)
    frame["tokens_bilstm"] = frame["tokens_bilstm"].astype(int)
    return frame


def separar_interna(frame: pd.DataFrame, fraccion: float = FRACCION_INTERNA,
                    semilla: int = SEMILLA_INTERNA) -> np.ndarray:
    """Máscara booleana de validación interna: ~`fraccion` de los artículos, por grupos,
    estratificada por fuente y clase."""
    articulos = frame.drop_duplicates("id_articulo")
    por_grupo = articulos.groupby("grupo")
    estratos = defaultdict(list)
    for grupo, sub in por_grupo:
        primero = sub.sort_values("id_articulo").iloc[0]
        clase = Counter(sub.etiqueta_falsa).most_common(1)[0][0]
        estratos[(primero.fuente, clase)].append((grupo, len(sub)))
    rng = np.random.default_rng(semilla)
    elegidos = set()
    for clave in sorted(estratos):
        grupos = sorted(estratos[clave])
        meta = fraccion * sum(n for _, n in grupos)
        acumulado = 0
        for posicion in rng.permutation(len(grupos)):
            grupo, n = grupos[posicion]
            if acumulado + n / 2 > meta:
                continue
            elegidos.add(grupo)
            acumulado += n
    return frame.grupo.isin(elegidos).to_numpy()


def particiones(pliegue: str, brazo: str | list[str] | None = None, conjunto: Path = CONJUNTO,
                desarrollo: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Devuelve {'entrenamiento', 'validacion_interna', 'validacion'} para un pliegue.

    `pliegue` = 'F1' | 'F2' | 'F3' | 'todo' (modelo final: todo el desarrollo, sin validación externa).
    """
    if desarrollo is None:
        desarrollo = leer("fragmentos_desarrollo.csv", conjunto)
    if pliegue == "todo":
        fuera = desarrollo.iloc[0:0]
        resto = desarrollo
    else:
        if pliegue not in PLIEGUES:
            raise ValueError(f"Pliegue desconocido: {pliegue}")
        es_fuera = desarrollo.pliegue.eq(pliegue).to_numpy()
        fuera = desarrollo[es_fuera]
        resto = desarrollo[~es_fuera]
        resto = resto[~resto.grupo.isin(set(fuera.grupo))]
    # El modelo final entrena con todo el desarrollo y un número fijo de épocas.
    interna = (np.zeros(len(resto), dtype=bool) if pliegue == "todo"
               else separar_interna(resto))
    entrenamiento = resto[~interna]
    validacion_interna = resto[interna]
    brazos = [brazo] if isinstance(brazo, str) else list(brazo or [])
    for nombre in brazos:
        if nombre not in BRAZOS:
            raise ValueError(f"Brazo desconocido: {nombre}")
        extra = leer(BRAZOS[nombre], conjunto)
        if pliegue != "todo":
            extra = extra[extra.fuente != PLIEGUES[pliegue]]
        prohibidos = set(fuera.grupo) | set(validacion_interna.grupo)
        extra = extra[~extra.grupo.isin(prohibidos)]
        entrenamiento = pd.concat([entrenamiento, extra], ignore_index=True)
    for nombre, a, b in (("entrenamiento/validación", entrenamiento, fuera),
                         ("entrenamiento/interna", entrenamiento, validacion_interna),
                         ("interna/validación", validacion_interna, fuera)):
        if set(a.grupo) & set(b.grupo):
            raise AssertionError(f"Fuga de grupos {nombre}")
    return {"entrenamiento": entrenamiento.reset_index(drop=True),
            "validacion_interna": validacion_interna.reset_index(drop=True),
            "validacion": fuera.reset_index(drop=True)}
