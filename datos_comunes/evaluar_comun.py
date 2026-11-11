"""Evaluador común (plan común §4.3, §5.3 y §7). Mide cualquier modelo con el mismo código.

Uso:
  bilstm/.venv/bin/python datos_comunes/evaluar_comun.py --predicciones RUN1/predicciones.csv ... \
      --salida carpeta [--temperatura 1.3]

Lee `predicciones.csv` (id_fragmento, modelo, configuracion, semilla, pliegue, logit_real,
logit_falsa, prob_falsa) y las une con `fragmentos_desarrollo.csv` del conjunto común.
La probabilidad de un artículo es la media de las de sus fragmentos.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import leer  # noqa: E402

COLUMNAS_PRED = ("id_fragmento", "modelo", "configuracion", "semilla", "pliegue",
                 "logit_real", "logit_falsa", "prob_falsa")
NIVELES = ((0.0, 0.2, "Muy probablemente verdadero", "≤ 20 %"),
           (0.2, 0.4, "Probablemente verdadero", "20–40 %"),
           (0.4, 0.6, "Resultado incierto", "40–60 %"),
           (0.6, 0.8, "Probablemente falso", "60–80 %"),
           (0.8, 1.0, "Muy probablemente falso", "≥ 80 %"))


# --------------------------------------------------------------------------- métricas

def ece(y: np.ndarray, p: np.ndarray, tramos: int = 10) -> float:
    """Error de calibración esperado con tramos de igual anchura."""
    bordes = np.linspace(0, 1, tramos + 1)
    indice = np.clip(np.digitize(p, bordes[1:-1], right=False), 0, tramos - 1)
    total = 0.0
    for t in range(tramos):
        m = indice == t
        if m.any():
            total += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(total)


def metricas(y, p, umbral: float = 0.5) -> dict:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    pred = (p >= umbral).astype(int)
    tn = int(((y == 0) & (pred == 0)).sum())
    fp = int(((y == 0) & (pred == 1)).sum())
    fn = int(((y == 1) & (pred == 0)).sum())
    tp = int(((y == 1) & (pred == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    ambas = len(set(y.tolist())) == 2
    return {
        "n": int(len(y)), "n_falsas": int(y.sum()), "n_reales": int((y == 0).sum()),
        "f1_macro": float(f1_score(y, pred, average="macro", labels=[0, 1], zero_division=0)),
        "f1_falsa": float(f1_score(y, pred, pos_label=1, zero_division=0)),
        "precision_falsa": precision, "recall_falsa": recall,
        "tasa_falsas_alarmas": fp / (tn + fp) if tn + fp else 0.0,
        "auc_roc": float(roc_auc_score(y, p)) if ambas else None,
        "ap": float(average_precision_score(y, p)) if ambas else None,
        "brier": float(np.mean((p - y) ** 2)),
        "ece_10": ece(y, p),
        "matriz_confusion_real_falsa": [[tn, fp], [fn, tp]],
    }


def softmax_falsa(logit_real, logit_falsa, temperatura: float = 1.0) -> np.ndarray:
    z = (np.asarray(logit_falsa, float) - np.asarray(logit_real, float)) / temperatura
    return 1.0 / (1.0 + np.exp(-z))


def ajustar_temperatura(logit_real, logit_falsa, y) -> float:
    """Escalado de temperatura: T que minimiza el log-loss (búsqueda en rejilla + refinado)."""
    z = np.asarray(logit_falsa, float) - np.asarray(logit_real, float)
    y = np.asarray(y, float)

    def perdida(t):
        p = np.clip(1.0 / (1.0 + np.exp(-z / t)), 1e-7, 1 - 1e-7)
        return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))

    rejilla = np.exp(np.linspace(np.log(0.05), np.log(20), 400))
    mejor = rejilla[int(np.argmin([perdida(t) for t in rejilla]))]
    fina = np.linspace(mejor * 0.95, mejor * 1.05, 201)
    return float(fina[int(np.argmin([perdida(t) for t in fina]))])


def por_articulo(frame: pd.DataFrame, columna: str = "p") -> pd.DataFrame:
    return (frame.groupby("id_articulo", sort=True)
            .agg(p=(columna, "mean"), y=("etiqueta_falsa", "first"), fuente=("fuente", "first"))
            .reset_index())


def bootstrap_f1(frame: pd.DataFrame, repeticiones: int = 1000, semilla: int = 42) -> dict:
    """IC 95 % de F1 macro remuestreando artículos (a nivel de artículo y de fragmento)."""
    arts = por_articulo(frame)
    ids = arts.id_articulo.to_numpy()
    y_art, p_art = arts.y.to_numpy(), arts.p.to_numpy()
    codigos = pd.Categorical(frame.id_articulo, categories=ids).codes
    orden = np.argsort(codigos, kind="stable")
    limites = np.searchsorted(codigos[orden], np.arange(len(ids) + 1))
    y_fr, p_fr = frame.etiqueta_falsa.to_numpy()[orden], frame.p.to_numpy()[orden]
    rng = np.random.default_rng(semilla)
    art, frag = [], []
    for _ in range(repeticiones):
        m = rng.integers(0, len(ids), len(ids))
        art.append(f1_score(y_art[m], p_art[m] >= 0.5, average="macro", labels=[0, 1], zero_division=0))
        idx = np.concatenate([np.arange(limites[i], limites[i + 1]) for i in m])
        frag.append(f1_score(y_fr[idx], p_fr[idx] >= 0.5, average="macro", labels=[0, 1], zero_division=0))
    return {"articulo_ic95": [float(np.percentile(art, 2.5)), float(np.percentile(art, 97.5))],
            "fragmento_ic95": [float(np.percentile(frag, 2.5)), float(np.percentile(frag, 97.5))]}


def bootstrap_pareado(a: pd.DataFrame, b: pd.DataFrame, repeticiones: int = 1000,
                      semilla: int = 42) -> dict:
    """Diferencia de F1 macro de artículo (a − b) con remuestreo pareado de artículos."""
    aa, bb = por_articulo(a), por_articulo(b)
    unido = aa.merge(bb, on=["id_articulo", "y"], suffixes=("_a", "_b"))
    y, pa, pb = unido.y.to_numpy(), unido.p_a.to_numpy() >= 0.5, unido.p_b.to_numpy() >= 0.5
    rng = np.random.default_rng(semilla)
    dif = []
    for _ in range(repeticiones):
        m = rng.integers(0, len(y), len(y))
        dif.append(f1_score(y[m], pa[m], average="macro", zero_division=0) -
                   f1_score(y[m], pb[m], average="macro", zero_division=0))
    dif = np.asarray(dif)
    return {"n_articulos": int(len(y)),
            "diferencia": float(f1_score(y, pa, average="macro") - f1_score(y, pb, average="macro")),
            "ic95": [float(np.percentile(dif, 2.5)), float(np.percentile(dif, 97.5))],
            "prob_a_mejor": float((dif > 0).mean())}


def tabla_niveles(p, y) -> list[dict]:
    p, y = np.asarray(p, float), np.asarray(y, int)
    filas = []
    for inicio, fin, nombre, objetivo in NIVELES:
        m = (p >= inicio) & ((p < fin) if fin < 1 else (p <= fin))
        n = int(m.sum())
        pct = float(y[m].mean()) if n else None
        lo, hi = inicio, fin
        dentro = None if pct is None else (lo - 1e-9 <= pct <= hi + 1e-9 if 0 < lo and hi < 1
                                           else (pct <= 0.2 if lo == 0 else pct >= 0.8))
        filas.append({"nivel": f"{int(inicio * 100)}–{int(fin * 100)} «{nombre}»", "fragmentos": n,
                      "pct_falsas": pct, "objetivo": objetivo, "dentro_objetivo": dentro})
    return filas


# --------------------------------------------------------------------------- evaluación

def cargar_predicciones(rutas: list[Path], temperatura: float = 1.0,
                        desarrollo: pd.DataFrame | None = None) -> pd.DataFrame:
    partes = []
    for ruta in rutas:
        pred = pd.read_csv(ruta, dtype={"id_fragmento": str, "modelo": str, "configuracion": str,
                                        "pliegue": str})
        faltan = set(COLUMNAS_PRED) - set(pred.columns)
        if faltan:
            raise ValueError(f"{ruta}: faltan columnas {sorted(faltan)}")
        partes.append(pred)
    pred = pd.concat(partes, ignore_index=True)
    if (pred.pliegue == "congelada").any():
        raise PermissionError("Las predicciones de la prueba congelada no se evalúan en esta fase")
    if desarrollo is None:
        desarrollo = leer("fragmentos_desarrollo.csv")
    unido = pred.merge(desarrollo[["id_fragmento", "id_articulo", "fuente", "etiqueta_falsa", "pliegue",
                                   "tokens_bilstm"]].rename(columns={"pliegue": "pliegue_dato"}),
                       on="id_fragmento", how="left", validate="many_to_one")
    if unido.id_articulo.isna().any():
        raise ValueError("Hay id_fragmento que no están en el conjunto común")
    if (unido.pliegue != unido.pliegue_dato).any():
        raise ValueError("Hay predicciones de fragmentos que no pertenecen a la fuente que quedó fuera")
    duplicados = unido.duplicated(["modelo", "configuracion", "semilla", "id_fragmento"])
    if duplicados.any():
        raise ValueError("Hay fragmentos repetidos dentro de una misma corrida")
    unido["p"] = softmax_falsa(unido.logit_real, unido.logit_falsa, temperatura)
    return unido


def evaluar_bloque(frame: pd.DataFrame, bootstrap: bool = True) -> dict:
    arts = por_articulo(frame)
    salida = {"fragmento": metricas(frame.etiqueta_falsa, frame.p),
              "articulo": metricas(arts.y, arts.p)}
    if bootstrap:
        salida["bootstrap"] = bootstrap_f1(frame)
    salida["por_fuente"] = {}
    for fuente, sub in frame.groupby("fuente"):
        a = por_articulo(sub)
        salida["por_fuente"][fuente] = {"fragmento": metricas(sub.etiqueta_falsa, sub.p),
                                        "articulo": metricas(a.y, a.p)}
    return salida


def evaluar_configuracion(frame: pd.DataFrame, bootstrap: bool = True) -> dict:
    """Métrica de selección (§4.1): media entre pliegues de F1 macro de artículo, por semilla;
    después media y desviación entre semillas. También predicciones fuera de pliegue juntas."""
    por_semilla, por_pliegue = {}, {}
    for (semilla, pliegue), sub in frame.groupby(["semilla", "pliegue"]):
        arts = por_articulo(sub)
        por_pliegue.setdefault(pliegue, {})[int(semilla)] = {
            "articulo": metricas(arts.y, arts.p), "fragmento": metricas(sub.etiqueta_falsa, sub.p)}
    for semilla in sorted({s for v in por_pliegue.values() for s in v}):
        f1 = [por_pliegue[p][semilla]["articulo"]["f1_macro"] for p in sorted(por_pliegue)
              if semilla in por_pliegue[p]]
        fa = [por_pliegue[p][semilla]["articulo"]["tasa_falsas_alarmas"] for p in sorted(por_pliegue)
              if semilla in por_pliegue[p]]
        por_semilla[semilla] = {"f1_macro_articulo_media_pliegues": float(np.mean(f1)),
                                "falsas_alarmas_articulo_media_pliegues": float(np.mean(fa)),
                                "pliegues": len(f1)}
    medias = [v["f1_macro_articulo_media_pliegues"] for v in por_semilla.values()]
    alarmas = [v["falsas_alarmas_articulo_media_pliegues"] for v in por_semilla.values()]
    resumen_pliegues = {}
    for pliegue, semillas in sorted(por_pliegue.items()):
        for nivel in ("articulo", "fragmento"):
            for clave in ("f1_macro", "tasa_falsas_alarmas", "auc_roc", "f1_falsa"):
                valores = [s[nivel][clave] for s in semillas.values() if s[nivel][clave] is not None]
                resumen_pliegues.setdefault(pliegue, {})[f"{nivel}_{clave}"] = {
                    "media": float(np.mean(valores)), "desv": float(np.std(valores, ddof=1)) if len(valores) > 1 else 0.0}
    fuera_de_pliegue = {int(s): evaluar_bloque(sub, bootstrap) for s, sub in frame.groupby("semilla")}
    return {
        "seleccion": {"f1_macro_articulo_media": float(np.mean(medias)),
                      "f1_macro_articulo_desv_semillas": float(np.std(medias, ddof=1)) if len(medias) > 1 else 0.0,
                      "falsas_alarmas_articulo_media": float(np.mean(alarmas)),
                      "semillas": len(medias), "completo": all(v["pliegues"] == 3 for v in por_semilla.values())},
        "por_semilla": por_semilla, "por_pliegue": resumen_pliegues,
        "por_pliegue_y_semilla": por_pliegue, "fuera_de_pliegue_por_semilla": fuera_de_pliegue,
    }


def promedio_semillas(frame: pd.DataFrame) -> pd.DataFrame:
    """Promedia logits de las semillas por fragmento (para el modelo final de varias semillas)."""
    cols = ["id_fragmento", "id_articulo", "fuente", "etiqueta_falsa", "pliegue"]
    media = frame.groupby(cols, as_index=False)[["logit_real", "logit_falsa"]].mean()
    return media


def evaluar(rutas: list[Path], temperatura: float = 1.0, bootstrap: bool = True) -> dict:
    frame = cargar_predicciones(rutas, temperatura)
    salida = {"temperatura": temperatura, "configuraciones": {}}
    for (modelo, config), sub in frame.groupby(["modelo", "configuracion"]):
        resultado = evaluar_configuracion(sub, bootstrap)
        resultado["niveles_por_semilla"] = {int(s): tabla_niveles(x.p, x.etiqueta_falsa)
                                            for s, x in sub.groupby("semilla")}
        media = promedio_semillas(sub)
        media["p"] = softmax_falsa(media.logit_real, media.logit_falsa, temperatura)
        resultado["niveles_media_semillas"] = tabla_niveles(media.p, media.etiqueta_falsa)
        salida["configuraciones"][f"{modelo}/{config}"] = resultado
    return salida


def resumen_md(resultado: dict) -> str:
    lineas = [f"Temperatura aplicada: {resultado['temperatura']}", "",
              "| Configuración | F1 macro artículo (media pliegues) | Desv. semillas | Falsas alarmas | F1 | F2 | F3 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for nombre, r in resultado["configuraciones"].items():
        s = r["seleccion"]
        celdas = [f"{r['por_pliegue'][p]['articulo_f1_macro']['media']:.3f}" if p in r["por_pliegue"] else "—"
                  for p in ("F1", "F2", "F3")]
        lineas.append(f"| {nombre} | {s['f1_macro_articulo_media']:.3f} | {s['f1_macro_articulo_desv_semillas']:.3f} | "
                      f"{s['falsas_alarmas_articulo_media']:.3f} | " + " | ".join(celdas) + " |")
    return "\n".join(lineas) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predicciones", type=Path, nargs="+", required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--temperatura", type=float, default=1.0)
    parser.add_argument("--sin-bootstrap", action="store_true")
    args = parser.parse_args()
    resultado = evaluar(args.predicciones, args.temperatura, not args.sin_bootstrap)
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "metricas.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), "utf-8")
    (args.salida / "resumen.md").write_text(resumen_md(resultado), "utf-8")
    print(resumen_md(resultado))


if __name__ == "__main__":
    main()
