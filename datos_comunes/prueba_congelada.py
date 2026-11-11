"""Prueba congelada: se abre UNA SOLA VEZ, con los modelos, la calibración y la combinación ya fijados.

Uso (solo cuando Orlando lo indique; plan común §6):
  PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python datos_comunes/prueba_congelada.py --abrir-una-sola-vez

Usa el mismo código que la app (backend/models/): carga B6 y BETO desde sus contratos de producción,
predice cada fragmento de `fragmentos_prueba_congelada.csv`, calibra con la temperatura del contrato y
combina con `datasets/combinacion_produccion/combinacion.json`. Los fragmentos se pasan tal cual, igual
que en las predicciones fuera de pliegue con las que se calibró.

Escribe en `datasets/comun_v1_corridas/prueba_congelada/`: las predicciones de cada modelo en el formato
común (`pliegue = congelada`), `metricas.json` y `RESUMEN.md`. Si la carpeta ya existe, se niega a
repetir: el resultado se informa tal como salió y no se ajusta nada después.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import ROOT, leer, manifiesto, sha256  # noqa: E402
from evaluar_comun import bootstrap_f1, metricas, por_articulo, tabla_niveles  # noqa: E402

SALIDA = ROOT / "datasets/comun_v1_corridas/prueba_congelada"
CALIBRACION = ROOT / "datasets/comun_v1_corridas/calibracion/metricas.json"


def comprobar_una_vez(salida: Path, abrir: bool) -> None:
    if not abrir:
        raise SystemExit("La prueba congelada se abre una sola vez: añade --abrir-una-sola-vez cuando toque.")
    if salida.exists():
        raise SystemExit(f"La prueba congelada ya se evaluó ({salida}). No se repite.")


def predecir(textos: list[str]) -> tuple[dict[str, np.ndarray], dict]:
    """Logits sin calibrar de cada modelo con el código de producción."""
    from backend.models.bilstm import BilstmPredictor, predict_logits
    from backend.models.contrato import Combination
    from backend.models.mbert import MbertPredictor, MbertTokenizer

    combinacion = Combination.load()
    bilstm = BilstmPredictor()
    politica = MbertTokenizer()
    combinacion.check(bilstm.contract)
    combinacion.check(politica.contract)
    beto = MbertPredictor(politica)
    z_bilstm = np.asarray(predict_logits(bilstm.model, bilstm.vocab, bilstm.max_len, bilstm.device, textos))
    z_beto = np.asarray([beto.margin(texto)[0] for texto in textos])
    info = {"combinacion": combinacion, "contratos": {"bilstm": bilstm.contract, "mbert": politica.contract}}
    return {"bilstm": z_bilstm, "mbert": z_beto}, info


def formato_comun(frame: pd.DataFrame, z: np.ndarray, modelo: str, configuracion: str, semilla: int) -> pd.DataFrame:
    return pd.DataFrame({"id_fragmento": frame.id_fragmento, "modelo": modelo, "configuracion": configuracion,
                         "semilla": semilla, "pliegue": "congelada", "logit_real": 0.0,
                         "logit_falsa": z.astype(np.float32), "prob_falsa": 1 / (1 + np.exp(-z))})


def bloque(frame: pd.DataFrame, p: np.ndarray) -> dict:
    marco = frame.assign(p=p)
    articulos = por_articulo(marco)
    salida = {"articulo": metricas(articulos.y, articulos.p), "fragmento": metricas(marco.etiqueta_falsa, p),
              "bootstrap": bootstrap_f1(marco), "niveles": tabla_niveles(p, marco.etiqueta_falsa), "por_fuente": {}}
    for fuente, sub in marco.groupby("fuente"):
        a = por_articulo(sub)
        salida["por_fuente"][fuente] = {"articulos": int(len(a)), "articulo": metricas(a.y, a.p)}
    return salida


def resumen_md(r: dict) -> str:
    filas = ["| Modelo | F1 macro art. | IC 95 % | Falsas alarmas art. | AUC frag. | Brier frag. | Validación por fuente (F1 art.) |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    for nombre, b in r["resultados"].items():
        ic = b["bootstrap"]["articulo_ic95"]
        filas.append(f"| {nombre} | {b['articulo']['f1_macro']:.3f} | [{ic[0]:.3f}; {ic[1]:.3f}] | "
                     f"{100 * b['articulo']['tasa_falsas_alarmas']:.1f} % | {b['fragmento']['auc_roc']:.3f} | "
                     f"{b['fragmento']['brier']:.3f} | {r['referencia_validacion'].get(nombre, '—')} |")
    fuentes = sorted({f for b in r["resultados"].values() for f in b["por_fuente"]})
    por_fuente = ["| Modelo | " + " | ".join(fuentes) + " |", "| --- |" + " ---: |" * len(fuentes)]
    for nombre, b in r["resultados"].items():
        por_fuente.append(f"| {nombre} | " + " | ".join(
            f"{b['por_fuente'][f]['articulo']['f1_macro']:.3f} (n={b['por_fuente'][f]['articulos']})" for f in fuentes) + " |")
    niveles = ["| Nivel | Fragmentos | % realmente falsas | Objetivo | Dentro |", "| --- | ---: | ---: | --- | :---: |"]
    for f in r["resultados"]["combinacion"]["niveles"]:
        pct = "—" if f["pct_falsas"] is None else f"{100 * f['pct_falsas']:.0f} %"
        niveles.append(f"| {f['nivel']} | {f['fragmentos']} | {pct} | {f['objetivo']} | "
                       f"{ {True: 'sí', False: 'no', None: '—'}[f['dentro_objetivo']] } |")
    return "\n".join([
        f"# Prueba congelada ({r['fecha']})", "",
        f"Evaluada una sola vez con los modelos de producción ({r['versiones']['bilstm']}, {r['versiones']['mbert']}) "
        f"y la combinación {r['versiones']['combinacion']}. {r['fragmentos']} fragmentos de {r['articulos']} artículos.", "",
        "## Resultado (por artículo, umbral 0,5)", "", *filas, "",
        "## Por fuente (F1 macro por artículo)", "", *por_fuente, "",
        "## Niveles de la extensión (combinación, por fragmento)", "", *niveles, "",
    ]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--abrir-una-sola-vez", action="store_true")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()
    comprobar_una_vez(args.salida, args.abrir_una_sola_vez)

    from backend.models.contrato import calibrated_probability

    congelada = leer("fragmentos_prueba_congelada.csv", abrir_congelada=True)
    logits, info = predecir(list(congelada.texto))
    combinacion, contratos = info["combinacion"], info["contratos"]
    probs = {nombre: np.array([calibrated_probability(z, contratos[nombre].temperature) for z in logits[nombre]])
             for nombre in ("bilstm", "mbert")}
    probs["combinacion"] = np.array([combinacion.combine({"bilstm": b, "mbert": m})[0]
                                     for b, m in zip(probs["bilstm"], probs["mbert"])])

    args.salida.mkdir(parents=True, exist_ok=False)
    formato_comun(congelada, logits["bilstm"], "bilstm", "B6", 42).to_csv(
        args.salida / "predicciones_congelada_bilstm.csv", index=False)
    formato_comun(congelada, logits["mbert"], "beto", "M3b", 42).to_csv(
        args.salida / "predicciones_congelada_beto.csv", index=False)
    congelada.drop(columns=["texto"]).assign(
        p_bilstm=probs["bilstm"], p_mbert=probs["mbert"], p_combinada=probs["combinacion"]).to_csv(
        args.salida / "probabilidades_calibradas.csv", index=False)

    referencia = {}
    if CALIBRACION.exists():
        v = json.loads(CALIBRACION.read_text("utf-8"))["validacion_por_fuente"]
        referencia = {"bilstm": f"{v['bilstm_calibrado']['articulo']['f1_macro']:.3f}",
                      "mbert": f"{v['mbert_calibrado']['articulo']['f1_macro']:.3f}",
                      "combinacion": f"{v['combinacion_bilstm_0.20']['articulo']['f1_macro']:.3f}"}
    resultado = {
        "fecha": f"{dt.datetime.now():%Y-%m-%d %H:%M}",
        "fragmentos": int(len(congelada)), "articulos": int(congelada.id_articulo.nunique()),
        "versiones": {"bilstm": contratos["bilstm"].version, "mbert": contratos["mbert"].version,
                      "combinacion": combinacion.version},
        "sha256_congelada": manifiesto()["archivos"]["fragmentos_prueba_congelada.csv"]["sha256"],
        "sha256_script": sha256(Path(__file__)),
        "referencia_validacion": referencia,
        "resultados": {nombre: bloque(congelada, p) for nombre, p in probs.items()},
    }
    (args.salida / "metricas.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (args.salida / "RESUMEN.md").write_text(resumen_md(resultado), "utf-8")
    print(resumen_md(resultado))


if __name__ == "__main__":
    main()
