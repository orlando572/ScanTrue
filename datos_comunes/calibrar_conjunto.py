"""Calibración conjunta del BiLSTM y mBERT (plan común §5).

Uso:
  bilstm/.venv/bin/python datos_comunes/calibrar_conjunto.py [--peso-bilstm 0.2] [--actualizar-contratos]

Lee las predicciones fuera de pliegue de los dos modelos finales
(`datasets/comun_v1_corridas/{bilstm,mbert}/final/predicciones_fuera_de_pliegue.csv`) y:

1. Ajusta la temperatura de cada modelo (escalado de temperatura, mínimo log-loss).
2. Combina los dos modelos con una media ponderada de sus logits calibrados:
       p_falsa = sigmoide(w_bilstm · z_bilstm / T_bilstm + w_mbert · z_mbert / T_mbert)
   con z = logit_falsa − logit_real y w_bilstm + w_mbert = 1. El peso es una decisión de diseño
   (los dos modelos cuentan); se informa qué pasaría con otros pesos y con pesos aprendidos.
3. Evalúa todo de forma honesta: la temperatura se ajusta con dos fuentes y se mide en la tercera.
4. Rellena la tabla de niveles de la extensión (§5.3) y evalúa la regla de discrepancia (§5.2).
5. Decide si promediar las semillas de mBERT (regla del plan de mBERT §8: +0,01 de F1).

Escribe `combinacion.json`, `metricas.json`, `RESUMEN.md` y las probabilidades combinadas en la salida.
Con `--actualizar-contratos` guarda la temperatura en el `contrato.json` de cada modelo (deja una copia
`contrato_antes_calibracion.json`). Nunca lee la prueba congelada.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import PLIEGUES, ROOT, leer, manifiesto, sha256  # noqa: E402
from evaluar_comun import (  # noqa: E402
    COLUMNAS_PRED, ajustar_temperatura, bootstrap_pareado, ece, metricas, por_articulo, tabla_niveles,
)

CORRIDAS = ROOT / "datasets/comun_v1_corridas"
UMBRAL_PROMEDIO_SEMILLAS = 0.01
PESOS_COMPARADOS = (0.0, 0.1, 0.2, 0.3, 0.5)
UMBRALES_DISCREPANCIA = (0.4, 0.5)
MOTIVO_PESO_0_20 = (
    "Decisión de diseño de Orlando (11 nov 2026): los dos modelos cuentan en el resultado unificado. "
    "La regresión logística aprendida da al BiLSTM un coeficiente negativo y, con coeficientes ≥ 0, "
    "un peso 0. Se fija 0,20 para el BiLSTM: es el mayor peso probado cuya pérdida de F1 frente a "
    "mBERT solo queda por debajo del margen de 0,02 de la regla común (§6).")
PESO_MBERT_ACTUAL = 0.70  # backend/core/config.py: media ponderada de probabilidades sin calibrar


def sigmoide(z) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, float)))


def combinar(z_bilstm, z_mbert, t_bilstm: float, t_mbert: float, peso_bilstm: float) -> np.ndarray:
    """Media ponderada de logits calibrados; los pesos suman 1."""
    if not 0.0 <= peso_bilstm <= 1.0:
        raise ValueError("El peso del BiLSTM debe estar entre 0 y 1")
    z = peso_bilstm * np.asarray(z_bilstm, float) / t_bilstm + \
        (1.0 - peso_bilstm) * np.asarray(z_mbert, float) / t_mbert
    return sigmoide(z)


def discrepancia(p_bilstm, p_mbert, umbral: float) -> np.ndarray:
    """§5.2: los modelos caen a lados distintos de 0,5 y se separan más que `umbral`."""
    p_bilstm, p_mbert = np.asarray(p_bilstm, float), np.asarray(p_mbert, float)
    return ((p_bilstm - 0.5) * (p_mbert - 0.5) < 0) & (np.abs(p_bilstm - p_mbert) > umbral)


# --------------------------------------------------------------------------- datos

def cargar_fuera_de_pliegue(ruta: Path, semilla: int | None, desarrollo: pd.DataFrame) -> pd.DataFrame:
    """Predicciones fuera de pliegue de un modelo, unidas a las etiquetas del conjunto común."""
    pred = pd.read_csv(ruta, dtype={"id_fragmento": str, "modelo": str, "configuracion": str, "pliegue": str})
    faltan = set(COLUMNAS_PRED) - set(pred.columns)
    if faltan:
        raise ValueError(f"{ruta}: faltan columnas {sorted(faltan)}")
    pred = pred[list(COLUMNAS_PRED)]
    if (pred.pliegue == "congelada").any():
        raise PermissionError("Las predicciones de la prueba congelada no se usan para calibrar")
    if semilla is not None:
        pred = pred[pred.semilla == semilla]
    if pred.empty:
        raise ValueError(f"{ruta}: no hay predicciones de la semilla {semilla}")
    if pred.duplicated(["semilla", "id_fragmento"]).any():
        raise ValueError(f"{ruta}: fragmentos repetidos dentro de una semilla")
    unido = pred.merge(desarrollo[["id_fragmento", "id_articulo", "fuente", "etiqueta_falsa", "pliegue"]]
                       .rename(columns={"pliegue": "pliegue_dato"}), on="id_fragmento", how="left",
                       validate="many_to_one")
    if unido.id_articulo.isna().any():
        raise ValueError(f"{ruta}: hay id_fragmento que no están en el conjunto común")
    if (unido.pliegue != unido.pliegue_dato).any():
        raise ValueError(f"{ruta}: hay predicciones fuera de la fuente que quedó fuera")
    unido["z"] = unido.logit_falsa - unido.logit_real
    return unido.drop(columns="pliegue_dato")


def emparejar(bilstm: pd.DataFrame, mbert: pd.DataFrame, desarrollo: pd.DataFrame) -> pd.DataFrame:
    """Une las dos tablas por fragmento y exige que cubran todo el desarrollo."""
    claves = ["id_fragmento", "id_articulo", "fuente", "etiqueta_falsa", "pliegue"]
    d = bilstm[claves + ["z"]].rename(columns={"z": "z_bilstm"}).merge(
        mbert[["id_fragmento", "z"]].rename(columns={"z": "z_mbert"}), on="id_fragmento", how="inner",
        validate="one_to_one")
    if len(d) != len(desarrollo) or set(d.id_fragmento) != set(desarrollo.id_fragmento):
        raise ValueError("Las predicciones de los dos modelos no cubren el mismo desarrollo completo")
    return d.sort_values("id_fragmento").reset_index(drop=True)


# --------------------------------------------------------------------------- evaluación

def temperatura(z, y) -> float:
    z = np.asarray(z, float)
    return ajustar_temperatura(np.zeros_like(z), z, y)


def por_fuente(d: pd.DataFrame, columnas: dict[str, callable]) -> dict[str, np.ndarray]:
    """Validación honesta: los parámetros se ajustan con dos fuentes y se aplican a la tercera.
    Cada función recibe (entrenamiento, prueba) y devuelve las probabilidades de prueba."""
    salida = {nombre: np.zeros(len(d)) for nombre in columnas}
    for pliegue in PLIEGUES:
        prueba = (d.pliegue == pliegue).to_numpy()
        for nombre, funcion in columnas.items():
            salida[nombre][prueba] = funcion(d[~prueba], d[prueba])
    return salida


def resumen_metodo(d: pd.DataFrame, p: np.ndarray) -> dict:
    p = np.clip(np.asarray(p, float), 1e-7, 1 - 1e-7)
    marco = d.assign(p=p)
    articulos = por_articulo(marco)
    f1_pliegues = {}
    for pliegue, sub in marco.groupby("pliegue"):
        a = por_articulo(sub)
        f1_pliegues[pliegue] = metricas(a.y, a.p)["f1_macro"]
    return {
        "f1_macro_articulo_media_pliegues": float(np.mean(list(f1_pliegues.values()))),
        "f1_macro_articulo_por_pliegue": f1_pliegues,
        "articulo": metricas(articulos.y, articulos.p),
        "fragmento": metricas(marco.etiqueta_falsa, p),
        "log_loss_fragmento": float(log_loss(marco.etiqueta_falsa, p, labels=[0, 1])),
        "ece_fragmento": ece(marco.etiqueta_falsa.to_numpy(), p),
    }


def metodos(peso_bilstm: float) -> dict[str, callable]:
    def calibrado(columna):
        return lambda tr, te: sigmoide(te[columna] / temperatura(tr[columna], tr.etiqueta_falsa))

    def combinado(peso):
        def f(tr, te):
            tb, tm = temperatura(tr.z_bilstm, tr.etiqueta_falsa), temperatura(tr.z_mbert, tr.etiqueta_falsa)
            return combinar(te.z_bilstm, te.z_mbert, tb, tm, peso)
        return f

    def aprendido(no_negativo: bool):
        def f(tr, te):
            tb, tm = temperatura(tr.z_bilstm, tr.etiqueta_falsa), temperatura(tr.z_mbert, tr.etiqueta_falsa)
            x_tr = np.c_[tr.z_bilstm / tb, tr.z_mbert / tm]
            x_te = np.c_[te.z_bilstm / tb, te.z_mbert / tm]
            modelo = LogisticRegression(C=1e6, max_iter=1000).fit(x_tr, tr.etiqueta_falsa)
            coef = modelo.coef_[0].copy()
            if no_negativo and (coef < 0).any():
                # Con un coeficiente negativo, el óptimo con coeficientes ≥ 0 lo deja en 0.
                malo = int(np.argmin(coef))
                bueno = 1 - malo
                solo = LogisticRegression(C=1e6, max_iter=1000).fit(x_tr[:, [bueno]], tr.etiqueta_falsa)
                coef = np.zeros(2)
                coef[bueno] = solo.coef_[0][0]
                return sigmoide(solo.intercept_[0] + x_te @ coef)
            return sigmoide(modelo.intercept_[0] + x_te @ coef)
        return f

    salida = {
        "bilstm_sin_calibrar": lambda tr, te: sigmoide(te.z_bilstm),
        "mbert_sin_calibrar": lambda tr, te: sigmoide(te.z_mbert),
        "media_70_30_actual": lambda tr, te: (1 - PESO_MBERT_ACTUAL) * sigmoide(te.z_bilstm)
        + PESO_MBERT_ACTUAL * sigmoide(te.z_mbert),
        "bilstm_calibrado": calibrado("z_bilstm"),
        "mbert_calibrado": calibrado("z_mbert"),
        "regresion_logistica_libre": aprendido(False),
        "regresion_logistica_pesos_no_negativos": aprendido(True),
    }
    for peso in sorted(set(PESOS_COMPARADOS) | {peso_bilstm}):
        salida[f"combinacion_bilstm_{peso:.2f}"] = combinado(peso)
    return salida


def promedio_semillas(ruta: Path, desarrollo: pd.DataFrame) -> dict:
    """Plan de mBERT §8.3: promediar logits de las semillas solo si sube el F1 al menos 0,01."""
    todas = cargar_fuera_de_pliegue(ruta, None, desarrollo)
    semillas = sorted(int(s) for s in todas.semilla.unique())

    def f1_media_pliegues(marco: pd.DataFrame) -> float:
        valores = []
        for _, sub in marco.groupby("pliegue"):
            a = por_articulo(sub.assign(p=sigmoide(sub.z)))
            valores.append(metricas(a.y, a.p)["f1_macro"])
        return float(np.mean(valores))

    por_semilla = {s: f1_media_pliegues(todas[todas.semilla == s]) for s in semillas}
    media = todas.groupby(["id_fragmento", "id_articulo", "fuente", "etiqueta_falsa", "pliegue"],
                          as_index=False).z.mean()
    f1_promedio = f1_media_pliegues(media)
    ganancia = f1_promedio - float(np.mean(list(por_semilla.values())))
    return {"semillas": semillas, "f1_por_semilla": por_semilla, "f1_logits_promediados": f1_promedio,
            "ganancia": ganancia, "umbral": UMBRAL_PROMEDIO_SEMILLAS,
            "promediar": bool(ganancia >= UMBRAL_PROMEDIO_SEMILLAS)}


# --------------------------------------------------------------------------- informe

def tabla_md(filas: list[dict], columnas: list[tuple[str, str]]) -> str:
    lineas = ["| " + " | ".join(t for _, t in columnas) + " |",
              "| " + " | ".join("---" if i == 0 else "---:" for i in range(len(columnas))) + " |"]
    for fila in filas:
        lineas.append("| " + " | ".join(str(fila[c]) for c, _ in columnas) + " |")
    return "\n".join(lineas)


def niveles_md(filas: list[dict]) -> str:
    salida = [{"nivel": f["nivel"], "n": f["fragmentos"],
               "pct": "—" if f["pct_falsas"] is None else f"{100 * f['pct_falsas']:.0f} %",
               "obj": f["objetivo"], "ok": {True: "sí", False: "no", None: "—"}[f["dentro_objetivo"]]}
              for f in filas]
    return tabla_md(salida, [("nivel", "Nivel"), ("n", "Fragmentos"), ("pct", "% realmente falsas"),
                             ("obj", "Objetivo"), ("ok", "Dentro")])


def resumen_md(resultado: dict) -> str:
    c = resultado["combinacion"]
    filas = []
    for nombre, r in resultado["validacion_por_fuente"].items():
        filas.append({"m": nombre, "f1": f"{r['f1_macro_articulo_media_pliegues']:.3f}",
                      "f1g": f"{r['articulo']['f1_macro']:.3f}",
                      "fa": f"{100 * r['articulo']['tasa_falsas_alarmas']:.1f} %",
                      "auc": f"{r['fragmento']['auc_roc']:.3f}", "ll": f"{r['log_loss_fragmento']:.3f}",
                      "br": f"{r['fragmento']['brier']:.3f}", "ece": f"{r['ece_fragmento']:.3f}"})
    tabla = tabla_md(filas, [("m", "Método"), ("f1", "F1 art. (media pliegues)"), ("f1g", "F1 art. (global)"),
                             ("fa", "Falsas alarmas art."), ("auc", "AUC frag."), ("ll", "Log-loss frag."),
                             ("br", "Brier frag."), ("ece", "ECE frag.")])
    disc = tabla_md([{"u": u, **v} for u, v in resultado["regla_discrepancia"].items()],
                    [("u", "Umbral"), ("fragmentos", "Fragmentos afectados"),
                     ("f1_articulo", "F1 art."), ("auc_fragmento", "AUC frag."), ("brier_fragmento", "Brier frag.")])
    s = resultado["semillas_mbert"]
    lineas = [
        f"# Calibración conjunta ({c['version']})", "",
        f"- Temperaturas (todas las predicciones fuera de pliegue): BiLSTM **{c['temperaturas']['bilstm']:.4f}**, "
        f"mBERT **{c['temperaturas']['mbert']:.4f}**.",
        f"- Combinación: `{c['formula']}` con pesos BiLSTM **{c['pesos']['bilstm']:.2f}** y mBERT "
        f"**{c['pesos']['mbert']:.2f}**. Umbral 0,5.",
        f"- Semillas de mBERT: promediar sube el F1 {s['ganancia']:+.4f} (umbral +{s['umbral']}), "
        f"así que {'se promedian' if s['promediar'] else 'se usa una sola semilla'}.", "",
        "## Validación por fuente", "",
        "La temperatura (y los pesos aprendidos) se ajustan con dos fuentes y se miden en la tercera.", "",
        tabla, "",
        "## Niveles de la extensión (§5.3), combinación elegida, validación por fuente", "",
        niveles_md(resultado["niveles"]["combinacion_por_fuente"]), "",
        "Con los parámetros finales aplicados a todas las predicciones fuera de pliegue:", "",
        niveles_md(resultado["niveles"]["combinacion_final"]), "",
        "Referencia: cómo se ven hoy los niveles con la media 70/30 sin calibrar:", "",
        niveles_md(resultado["niveles"]["media_70_30_actual"]), "",
        "## Regla de discrepancia (§5.2), sobre la combinación elegida", "",
        "Si un modelo da más de 0,5 y el otro menos, y se separan más que el umbral, la probabilidad se "
        "lleva a la franja 0,4–0,6.", "",
        disc, "",
        "## Comparación pareada por artículo (bootstrap, 1.000 remuestreos)", "",
    ]
    for nombre, r in resultado["comparaciones_pareadas"].items():
        lineas.append(f"- {nombre}: diferencia {r['diferencia']:+.3f}, IC 95 % [{r['ic95'][0]:+.3f}; "
                      f"{r['ic95'][1]:+.3f}]")
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------- principal

def calibrar(bilstm_final: Path, mbert_final: Path, peso_bilstm: float, semilla_mbert: int | None,
             motivo: str = "") -> dict:
    desarrollo = leer("fragmentos_desarrollo.csv")
    contrato_b = json.loads((bilstm_final / "contrato.json").read_text("utf-8"))
    contrato_m = json.loads((mbert_final / "contrato.json").read_text("utf-8"))
    for contrato in (contrato_b, contrato_m):
        if contrato["sha256_conjunto"] != manifiesto()["archivos"]["fragmentos_desarrollo.csv"]["sha256"]:
            raise ValueError(f"El contrato de {contrato['modelo']} es de otro conjunto")
        if contrato["etiquetas"] != {"real": 0, "falsa": 1}:
            raise ValueError(f"Etiquetas inesperadas en el contrato de {contrato['modelo']}")

    ruta_b = bilstm_final / "predicciones_fuera_de_pliegue.csv"
    ruta_m = mbert_final / "predicciones_fuera_de_pliegue.csv"
    semillas = promedio_semillas(ruta_m, desarrollo)
    if semillas["promediar"]:
        raise NotImplementedError("Promediar semillas de mBERT compensa: hay que calibrar la media de logits")
    semilla_b = int(contrato_b["semillas"][0])
    semilla_m = semilla_mbert if semilla_mbert is not None else int(contrato_m["semillas"][0])
    d = emparejar(cargar_fuera_de_pliegue(ruta_b, semilla_b, desarrollo),
                  cargar_fuera_de_pliegue(ruta_m, semilla_m, desarrollo), desarrollo)
    y = d.etiqueta_falsa.to_numpy()

    t_b, t_m = temperatura(d.z_bilstm, y), temperatura(d.z_mbert, y)
    final = combinar(d.z_bilstm, d.z_mbert, t_b, t_m, peso_bilstm)
    probs = por_fuente(d, metodos(peso_bilstm))
    elegido = f"combinacion_bilstm_{peso_bilstm:.2f}"
    validacion = {nombre: resumen_metodo(d, p) for nombre, p in probs.items()}

    # Regla de discrepancia, con las probabilidades calibradas de cada modelo por fuente.
    p_b, p_m = probs["bilstm_calibrado"], probs["mbert_calibrado"]
    regla = {}
    for umbral in UMBRALES_DISCREPANCIA:
        marca = discrepancia(p_b, p_m, umbral)
        p = probs[elegido].copy()
        p[marca] = np.clip(p[marca], 0.4, 0.6)
        r = resumen_metodo(d, p)
        regla[str(umbral)] = {"fragmentos": int(marca.sum()), "f1_articulo": round(r["articulo"]["f1_macro"], 3),
                              "auc_fragmento": round(r["fragmento"]["auc_roc"], 3),
                              "brier_fragmento": round(r["fragmento"]["brier"], 3)}
    regla["sin regla"] = {"fragmentos": 0, "f1_articulo": round(validacion[elegido]["articulo"]["f1_macro"], 3),
                          "auc_fragmento": round(validacion[elegido]["fragmento"]["auc_roc"], 3),
                          "brier_fragmento": round(validacion[elegido]["fragmento"]["brier"], 3)}

    marco = d.assign(p=0.0)
    comparar = {
        "combinación − mBERT calibrado": ("mbert_calibrado",),
        "combinación − BiLSTM calibrado": ("bilstm_calibrado",),
        "combinación − media 70/30 actual": ("media_70_30_actual",),
    }
    pareadas = {nombre: bootstrap_pareado(marco.assign(p=probs[elegido]), marco.assign(p=probs[otro]))
                for nombre, (otro,) in comparar.items()}

    combinacion = {
        "version": f"{manifiesto()['version']}_conjunta_{dt.date.today():%Y%m%d}",
        "metodo": "media_ponderada_logits_calibrados",
        "formula": "p_falsa = sigmoide(w_bilstm * z_bilstm / T_bilstm + w_mbert * z_mbert / T_mbert), "
                   "z = logit_falsa - logit_real",
        "temperaturas": {"bilstm": round(t_b, 4), "mbert": round(t_m, 4)},
        "pesos": {"bilstm": peso_bilstm, "mbert": round(1.0 - peso_bilstm, 4)},
        "motivo_pesos": motivo,
        "umbral_falsa": 0.5,
        "regla_discrepancia": None,
        "nota_regla_discrepancia": "Evaluada en RESUMEN.md; no se aplica hasta que se decida.",
        "semillas": {"bilstm": semilla_b, "mbert": semilla_m},
        "promediar_logits_semillas_mbert": False,
        "contratos": {"bilstm": contrato_b["version"], "mbert": contrato_m["version"]},
        "entradas": {"bilstm": {"ruta": ruta_b.relative_to(ROOT).as_posix(), "sha256": sha256(ruta_b)},
                     "mbert": {"ruta": ruta_m.relative_to(ROOT).as_posix(), "sha256": sha256(ruta_m)}},
        "sha256_conjunto": manifiesto()["archivos"]["fragmentos_desarrollo.csv"]["sha256"],
        "sha256_script": sha256(Path(__file__)),
    }
    return {
        "combinacion": combinacion,
        "semillas_mbert": semillas,
        "validacion_por_fuente": validacion,
        "metodo_elegido": elegido,
        "niveles": {"combinacion_por_fuente": tabla_niveles(probs[elegido], y),
                    "combinacion_final": tabla_niveles(final, y),
                    "media_70_30_actual": tabla_niveles(probs["media_70_30_actual"], y)},
        "regla_discrepancia": regla,
        "comparaciones_pareadas": pareadas,
        "_predicciones": d.assign(p_bilstm=sigmoide(d.z_bilstm / t_b), p_mbert=sigmoide(d.z_mbert / t_m),
                                  p_combinada=final, p_combinada_por_fuente=probs[elegido]),
    }


def actualizar_contrato(ruta: Path, temperatura_nueva: float, version: str, extra: dict | None = None) -> None:
    copia = ruta.with_name("contrato_antes_calibracion.json")
    if not copia.exists():
        shutil.copy2(ruta, copia)
    contrato = json.loads(ruta.read_text("utf-8"))
    contrato["temperatura"] = temperatura_nueva
    contrato["temperatura_provisional"] = False
    contrato["nota_temperatura"] = (f"Calibración conjunta {version} (datos_comunes/calibrar_conjunto.py) con las "
                                    "predicciones fuera de pliegue; ver datasets/comun_v1_corridas/calibracion/.")
    contrato["calibracion"] = "datasets/comun_v1_corridas/calibracion/combinacion.json"
    contrato.update(extra or {})
    ruta.write_text(json.dumps(contrato, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bilstm", type=Path, default=CORRIDAS / "bilstm/final")
    parser.add_argument("--mbert", type=Path, default=CORRIDAS / "mbert/final")
    parser.add_argument("--peso-bilstm", type=float, default=0.2)
    parser.add_argument("--semilla-mbert", type=int, default=42)
    parser.add_argument("--motivo", default="", help="motivo del peso elegido (obligatorio si no es 0,2)")
    parser.add_argument("--salida", type=Path, default=CORRIDAS / "calibracion")
    parser.add_argument("--sobrescribir", action="store_true")
    parser.add_argument("--actualizar-contratos", action="store_true")
    args = parser.parse_args()
    if args.salida.exists() and any(args.salida.iterdir()) and not args.sobrescribir:
        raise SystemExit(f"La salida ya existe: {args.salida} (usa --sobrescribir)")

    motivo = args.motivo or (MOTIVO_PESO_0_20 if args.peso_bilstm == 0.2 else "")
    if not motivo:
        raise SystemExit("Con un peso distinto de 0,2 hay que dar --motivo")
    resultado = calibrar(args.bilstm, args.mbert, args.peso_bilstm, args.semilla_mbert, motivo)
    predicciones = resultado.pop("_predicciones")
    args.salida.mkdir(parents=True, exist_ok=True)
    c = resultado["combinacion"]
    (args.salida / "combinacion.json").write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (args.salida / "metricas.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (args.salida / "RESUMEN.md").write_text(resumen_md(resultado), "utf-8")
    predicciones.to_csv(args.salida / "predicciones_combinadas_fuera_de_pliegue.csv", index=False)

    if args.actualizar_contratos:
        actualizar_contrato(args.bilstm / "contrato.json", c["temperaturas"]["bilstm"], c["version"])
        actualizar_contrato(args.mbert / "contrato.json", c["temperaturas"]["mbert"], c["version"], {
            "semillas": [c["semillas"]["mbert"]], "promediar_logits_semillas": False,
            "nota_semillas": (f"Promediar las 3 semillas sube el F1 {resultado['semillas_mbert']['ganancia']:+.4f} "
                              "(< +0,01, plan de mBERT §8.3): se usa una sola semilla. Los checkpoints s43 y s44 "
                              "se conservan.")})
    print(resumen_md(resultado))


if __name__ == "__main__":
    main()
