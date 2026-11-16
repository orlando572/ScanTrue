"""Partes comunes del subcomando `reentrenar` de `bilstm/entrenar.py` y `mBERT/entrenar.py`.

`reentrenar` entrena un modelo desde cero con la receta de otro (su `config.json`) y un conjunto
con el formato de comun_v1: el propio `datasets/comun_v1/` o una versión del panel de datasets
(`fragmentos_desarrollo.csv` + `fragmentos_prueba.csv` + `manifest.json`). Lo lanza el panel de
administración (Entrenamiento), pero también se puede usar a mano.

Reglas:
- Entrena con todo `fragmentos_desarrollo.csv` (`--pliegue todo`) y las épocas fijas de la receta.
- Escribe en una carpeta oculta `.<versión>.parcial` junto a la salida y solo al terminar la
  renombra: el catálogo de modelos no ve nada a medio escribir. Nunca sobrescribe una salida.
- Si el conjunto trae `fragmentos_prueba.csv` (versiones del panel), la evalúa por artículo y
  escribe `metricas.json`. La prueba congelada de comun_v1 no se abre nunca.
- El contrato sale con temperatura provisional: falta la calibración conjunta.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from comun import BRAZOS, ROOT, manifiesto, sha256
from evaluar_comun import metricas, por_articulo, softmax_falsa

PRUEBA = "fragmentos_prueba.csv"
FASES = ("preparando", "descargando_base", "entrenando", "evaluando", "guardando", "terminado")


class Progreso:
    """Líneas JSON `{"progreso": …}` en stdout que el panel lee del registro.

    Sin `activo`, no imprime nada: la salida de la CLI queda como siempre."""

    def __init__(self, activo: bool) -> None:
        self.activo = activo
        self.inicio = time.time()
        # Corrida en curso cuando hay pliegues: {"corrida": 2, "corridas": 4, "nombre": "F2"}.
        self.contexto: dict = {}

    def __call__(self, fase: str, **datos) -> None:
        if not self.activo:
            return
        registro = {"progreso": fase, "segundos": round(time.time() - self.inicio, 1), **self.contexto, **datos}
        print(json.dumps(registro, ensure_ascii=False), flush=True)

    def lotes(self, epoca: int, epocas: int, total: int):
        """Función para el bucle de lotes: avisa cada ~2 % de la época."""
        if not self.activo:
            return None
        paso = max(1, total // 50)

        def avisar(lote: int) -> None:
            if lote == total or lote % paso == 0:
                self("entrenando", epoca=epoca, epocas=epocas, lote=lote, lotes=total)
        return avisar


def leer_receta(ruta: Path) -> dict:
    receta = json.loads(Path(ruta).read_text("utf-8"))
    if not isinstance(receta, dict) or not receta.get("configuracion"):
        raise ValueError(f"La receta {ruta} no es un config.json de una corrida")
    return receta


def archivos_del_conjunto(conjunto: Path) -> set[str]:
    return set(manifiesto(conjunto).get("archivos", {}))


def brazos_disponibles(brazos: list[str], conjunto: Path) -> tuple[list[str], list[str]]:
    """Separa los brazos de la receta en los que el conjunto trae y los que no (se omiten)."""
    archivos = archivos_del_conjunto(conjunto)
    usados = [b for b in brazos if BRAZOS.get(b) in archivos]
    return usados, [b for b in brazos if b not in usados]


def epocas_de(receta: dict, epocas: int | None) -> int:
    valor = int(epocas or receta.get("epocas_fijas") or 0)
    if valor < 1:
        raise ValueError("La receta no fija épocas: pasa --epocas")
    return valor


def carpeta_parcial(salida: Path) -> Path:
    """Carpeta oculta de trabajo junto a la salida. Falla si la salida ya existe."""
    salida = Path(salida)
    if salida.exists():
        raise FileExistsError(f"La salida ya existe y no se sobrescribe: {salida}")
    parcial = salida.parent / f".{salida.name}.parcial"
    if parcial.exists():  # restos de un intento anterior con la misma versión
        shutil.rmtree(parcial)
    parcial.mkdir(parents=True)
    return parcial


def ruta_contrato(salida: Path, relativa: str) -> str:
    """Ruta de un archivo del modelo tal como va al contrato: desde la raíz del repositorio si la
    salida está dentro; si no, relativa a la carpeta del contrato (el backend prueba las dos)."""
    destino = Path(salida) / relativa
    try:
        return destino.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return Path(relativa).as_posix()


def leer_prueba(conjunto: Path) -> pd.DataFrame | None:
    """`fragmentos_prueba.csv` del conjunto (solo las versiones del panel lo traen)."""
    if PRUEBA not in archivos_del_conjunto(conjunto):
        return None
    from comun import leer

    frame = leer(PRUEBA, conjunto)
    return frame if len(frame) else None


def metricas_prueba(modelo: str, version: str, prueba: pd.DataFrame, logits: np.ndarray,
                    temperatura: float = 1.0) -> dict:
    """`metricas.json` en el formato de `GET /metricas` (backend/schemas/metrics.py), por artículo."""
    p = softmax_falsa(logits[:, 0], logits[:, 1], temperatura)
    arts = por_articulo(prueba.assign(p=p))
    m = metricas(arts.y, arts.p)
    (tn, fp), (fn, tp) = m["matriz_confusion_real_falsa"]
    n = int(len(arts))
    return {
        "modelo": modelo,
        "version": version,
        "orden_clases": ["falsa", "real"],
        "evaluaciones": [{
            "conjunto": "prueba_panel_articulos",
            "n": n,
            # Filas: etiqueta real; columnas: predicción, en el orden (falsa, real).
            "matriz_confusion": [[tp, fn], [fp, tn]],
            "exactitud": (tp + tn) / n if n else 0.0,
            "precision_falsa": m["precision_falsa"],
            "recall_falsa": m["recall_falsa"],
            "f1_falsa": m["f1_falsa"],
            "f1_macro": m["f1_macro"],
            "fuente": f"{PRUEBA} ({len(prueba)} fragmentos)",
        }],
        "limitaciones": [
            "Prueba del panel: noticias revisadas que no comparten grupo con el entrenamiento.",
            f"Solo {n} {'noticia' if n == 1 else 'noticias'}: las cifras tienen mucha incertidumbre."
            if n < 200 else
            "La prueba sale de las mismas fuentes que el entrenamiento.",
            "Temperatura provisional (1,0): falta la calibración conjunta; el umbral 0,5 no cambia.",
        ],
    }


OOF = "predicciones_fuera_de_pliegue.csv"


def escribir_fuera_de_pliegue(rutas: list[Path], conjunto: Path, destino: Path) -> int:
    """Une las predicciones de los pliegues con sus etiquetas, como las de los modelos finales
    (`final()`): así la calibración funciona aunque el conjunto ya no esté en el equipo."""
    from comun import leer
    from evaluar_comun import cargar_predicciones

    oof = cargar_predicciones(rutas, desarrollo=leer("fragmentos_desarrollo.csv", conjunto))
    oof.drop(columns=["p", "pliegue_dato"]).to_csv(destino, index=False)
    return len(oof)


def pliegues_del_conjunto(conjunto: Path) -> list[str]:
    """Pliegues F1–F3 presentes en el desarrollo (comun_v1 o una versión del panel ya repartida)."""
    from comun import PLIEGUES, leer

    presentes = set(leer("fragmentos_desarrollo.csv", conjunto).pliegue)
    faltan = [p for p in PLIEGUES if p not in presentes]
    if faltan:
        raise ValueError(f"El conjunto no tiene los pliegues {faltan}: no se puede preparar la calibración")
    return list(PLIEGUES)


def escribir_json(ruta: Path, datos: dict) -> None:
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2), "utf-8")


def procedencia(conjunto: Path, receta_ruta: Path, receta: dict, semilla: int, epocas: int,
                brazos: list[str], omitidos: list[str], segundos: float, pliegues: list[str] | None = None
                ) -> dict:
    """`entrenamiento.json`: de dónde sale el modelo, para poder repetirlo."""
    man = manifiesto(conjunto)
    return {
        "subcomando": "reentrenar",
        "conjunto": {
            "ruta": ruta_contrato(conjunto, "."),
            "version": man.get("version"),
            "nombre": man.get("nombre"),
            "id": man.get("id"),
            "sha256_manifest": sha256(Path(conjunto) / "manifest.json"),
            "sha256_desarrollo": man["archivos"]["fragmentos_desarrollo.csv"]["sha256"],
        },
        "receta": {"ruta": ruta_contrato(Path(receta_ruta).parent, Path(receta_ruta).name),
                   "configuracion": receta.get("configuracion"),
                   "sha256": sha256(Path(receta_ruta))},
        "semilla": semilla,
        "epocas": epocas,
        "brazos": brazos,
        "brazos_omitidos": omitidos,
        "pliegues": pliegues or [],
        "segundos": round(segundos, 1),
        "python": sys.version.split()[0],
    }


def cerrar(parcial: Path, salida: Path) -> None:
    """Pasa la carpeta de trabajo a su sitio. Si alguien creó la salida entretanto, falla."""
    if Path(salida).exists():
        raise FileExistsError(f"La salida apareció mientras se entrenaba: {salida}")
    Path(parcial).rename(salida)


def descartar(parcial: Path) -> None:
    shutil.rmtree(parcial, ignore_errors=True)


def comprobar_conjunto(conjunto: Path) -> None:
    """El conjunto debe tener `fragmentos_desarrollo.csv` en su manifiesto."""
    if "fragmentos_desarrollo.csv" not in archivos_del_conjunto(conjunto):
        raise ValueError(f"{conjunto} no tiene fragmentos_desarrollo.csv en su manifest.json")
