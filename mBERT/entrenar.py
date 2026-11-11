"""Entrenamiento de mBERT (y de BETO, MarIA o XLM-R) con el conjunto común `datasets/comun_v1/`.

Es el único script de entrenamiento de mBERT. Tiene la misma forma que `bilstm/entrenar.py`
(plan: docs/mejora_modelos/03_PLAN_MBERT.md §5.2 y §6). Subcomandos, en el orden en que se usan:

  corrida      Entrena un pliegue con una semilla y guarda sus predicciones (logits).
  experimento  Lanza una configuración en 3 pliegues × 3 semillas y la evalúa.
  truncado     M0-len: % de fragmentos que cada tokenizador trunca a N tokens.
  plan         Ejecuta M0 → M3c en orden (§7) y aplica la regla de decisión fijada.
  decidir      Compara dos configuraciones ya evaluadas con la regla de decisión.
  final        Entrena el ganador con todo el desarrollo y escribe el contrato (§8–§9).

Ejemplos (desde la raíz del repositorio):
  mBERT/.venv/Scripts/python.exe mBERT/entrenar.py corrida --pliegue F1 --configuracion prueba --salida X --epocas 1
  mBERT/.venv/Scripts/python.exe mBERT/entrenar.py experimento M1a --modelo beto
  mBERT/.venv/Scripts/python.exe mBERT/entrenar.py plan

Convenciones:
- Etiqueta `etiqueta_falsa`: la salida 1 del modelo es «falsa» y la 0 es «real».
- Entrada: solo `texto`, como secuencia única `[CLS] texto [SEP]`, truncada a --max-length.
- Pérdida por muestra × `peso` (artículo y fuente) × peso de clase calculado con esos pesos.
- La época se elige con la validación interna del pliegue (F1 macro de artículo; empate a favor
  de la época anterior). La fuente que queda fuera solo se predice al final.
- No se guardan checkpoints por época: el mejor estado se guarda en memoria y se recarga.
- Nunca abre la prueba congelada.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import subprocess
import sys
import time
import traceback
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mBERT"))
sys.path.insert(0, str(ROOT / "datos_comunes"))
from comun import CONJUNTO, leer, manifiesto, particiones, sha256  # noqa: E402
from evaluar_comun import COLUMNAS_PRED, cargar_predicciones, softmax_falsa  # noqa: E402
import modelo as bases  # noqa: E402

CORRIDAS = ROOT / "datasets/comun_v1_corridas"
ETIQUETAS = bases.ETIQUETAS
PLIEGUES = ("F1", "F2", "F3")
SEMILLAS = (42, 43, 44)
UMBRAL = 0.02  # regla de decisión (plan común §6)


# =========================================================================== datos

class Fragmentos(Dataset):
    """Fragmentos tokenizados con su etiqueta y su peso final (peso × peso de clase)."""

    def __init__(self, frame: pd.DataFrame, tokenizador, max_length: int, pesos_clase: np.ndarray | None = None):
        self.items = []
        if len(frame):  # con --pliegue todo no hay validación
            cod = tokenizador(frame.texto.tolist(), truncation=True, max_length=max_length)
            claves = [k for k in ("input_ids", "attention_mask", "token_type_ids") if k in cod]
            self.items = [{k: cod[k][i] for k in claves} for i in range(len(frame))]
        self.etiquetas = frame.etiqueta_falsa.astype(int).to_numpy()
        peso = frame.peso.astype(float).to_numpy()
        self.pesos = peso * (pesos_clase[self.etiquetas] if pesos_clase is not None else 1.0)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        return self.items[i], int(self.etiquetas[i]), float(self.pesos[i])


def cargador(datos: Fragmentos, tokenizador, lote: int, mezclar: bool, semilla: int) -> DataLoader:
    def agrupar(muestras):
        entrada = tokenizador.pad([m[0] for m in muestras], return_tensors="pt")
        entrada["labels"] = torch.tensor([m[1] for m in muestras], dtype=torch.long)
        entrada["peso"] = torch.tensor([m[2] for m in muestras], dtype=torch.float32)
        return entrada
    return DataLoader(datos, batch_size=lote, shuffle=mezclar, collate_fn=agrupar,
                      generator=torch.Generator().manual_seed(semilla))


def fraccion_truncada(textos, tokenizador, max_length: int) -> float:
    """Fracción de textos con más de `max_length` tokens (incluidos [CLS] y [SEP])."""
    textos = list(textos)
    if not textos:
        return 0.0
    largos = [len(x) for x in tokenizador(textos, truncation=False, verbose=False)["input_ids"]]
    return float(np.mean(np.asarray(largos) > max_length))


# =========================================================================== entrenamiento

def fijar_semilla(semilla: int) -> None:
    random.seed(semilla)
    np.random.seed(semilla)
    torch.manual_seed(semilla)
    torch.cuda.manual_seed_all(semilla)


def pesos_de_clase(frame: pd.DataFrame) -> np.ndarray:
    """Factor por clase que iguala el peso total de reales y falsas, contando con `peso`."""
    total = frame.peso.sum()
    return np.array([total / (2 * frame.peso[frame.etiqueta_falsa == c].sum()) for c in (0, 1)])


def perdida_ponderada(logits: torch.Tensor, etiquetas: torch.Tensor, pesos: torch.Tensor) -> torch.Tensor:
    """Entropía cruzada por muestra ponderada (plan §6.2): Σ(pérdida × peso) / Σ peso."""
    por_muestra = torch.nn.functional.cross_entropy(logits.float(), etiquetas, reduction="none")
    return (por_muestra * pesos).sum() / pesos.sum()


def autocast(dispositivo: torch.device):
    if dispositivo.type == "cuda" and torch.cuda.is_bf16_supported():
        return torch.autocast("cuda", dtype=torch.bfloat16)
    return nullcontext()


def predecir(modelo, carga: DataLoader, dispositivo: torch.device) -> np.ndarray:
    modelo.eval()
    salida = []
    with torch.inference_mode():
        for lote in carga:
            entrada = {k: v.to(dispositivo) for k, v in lote.items() if k not in ("labels", "peso")}
            with autocast(dispositivo):
                logits = modelo(**entrada).logits
            salida.append(logits.float().cpu().numpy())  # logits en float32 aunque corra en BF16
    return np.concatenate(salida) if salida else np.zeros((0, 2), np.float32)


def f1_articulo(frame: pd.DataFrame, logits: np.ndarray) -> float:
    """F1 macro de artículo: la probabilidad del artículo es la media de las de sus fragmentos."""
    p = softmax_falsa(logits[:, 0], logits[:, 1])
    arts = frame.assign(p=p).groupby("id_articulo").agg(p=("p", "mean"), y=("etiqueta_falsa", "first"))
    return float(f1_score(arts.y, arts.p >= 0.5, average="macro", labels=[0, 1], zero_division=0))


def optimizador_y_planificador(modelo, args, pasos_totales: int):
    """AdamW y calentamiento lineal: los mismos valores por defecto que usaba `Trainer`."""
    sin_decaimiento = ("bias", "LayerNorm.weight", "layernorm.weight", "layer_norm.weight")
    grupos = [
        {"params": [p for n, p in modelo.named_parameters() if not n.endswith(sin_decaimiento)],
         "weight_decay": args.weight_decay},
        {"params": [p for n, p in modelo.named_parameters() if n.endswith(sin_decaimiento)],
         "weight_decay": 0.0},
    ]
    optimizador = torch.optim.AdamW(grupos, lr=args.lr, betas=(0.9, 0.999), eps=1e-8)
    calentamiento = max(1, round(pasos_totales * args.calentamiento))

    def factor(paso: int) -> float:
        if paso < calentamiento:
            return paso / calentamiento
        return max(0.0, (pasos_totales - paso) / max(1, pasos_totales - calentamiento))
    return optimizador, torch.optim.lr_scheduler.LambdaLR(optimizador, factor), calentamiento


def corrida(args: argparse.Namespace) -> dict:
    """Entrena un pliegue (o todo el desarrollo con `--pliegue todo`) con una semilla."""
    if args.salida.exists() and any(args.salida.iterdir()):
        raise FileExistsError(f"La salida ya contiene archivos: {args.salida}")
    if args.pliegue == "todo" and not args.epocas_fijas:
        raise ValueError("El modelo final necesita --epocas-fijas (mediana de los pliegues)")
    if args.lote_efectivo % args.microlote:
        raise ValueError("--lote-efectivo debe ser múltiplo de --microlote")
    dispositivo = torch.device(args.dispositivo)
    if dispositivo.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible")
    args.salida.mkdir(parents=True, exist_ok=True)
    inicio = time.time()
    try:
        return _corrida(args, dispositivo, inicio)
    except Exception:
        (args.salida / "error.txt").write_text(traceback.format_exc(), "utf-8")
        raise


def _corrida(args: argparse.Namespace, dispositivo: torch.device, inicio: float) -> dict:
    ruta_base = args.ruta_modelo or bases.carpeta(args.modelo)
    base = bases.resumen(None if args.ruta_modelo else args.modelo, ruta_base)
    datos = particiones(args.pliegue, args.brazo, args.conjunto)
    entreno, interna, fuera = datos["entrenamiento"], datos["validacion_interna"], datos["validacion"]
    fijar_semilla(args.semilla)
    tokenizador = bases.cargar_tokenizador(ruta_base)
    modelo = bases.cargar_modelo(ruta_base)
    if args.gradient_checkpointing:
        modelo.gradient_checkpointing_enable()
    modelo.to(dispositivo)

    factor_clase = pesos_de_clase(entreno)
    d_entreno = Fragmentos(entreno, tokenizador, args.max_length, factor_clase)
    suma_clase = {nombre: float(d_entreno.pesos[d_entreno.etiquetas == c].sum()) for nombre, c in ETIQUETAS.items()}
    lote_eval = max(args.microlote, 4 if args.max_length > 256 else 16)
    carga_entreno = cargador(d_entreno, tokenizador, args.microlote, True, args.semilla)
    carga_interna = cargador(Fragmentos(interna, tokenizador, args.max_length), tokenizador, lote_eval, False, 0)
    carga_fuera = cargador(Fragmentos(fuera, tokenizador, args.max_length), tokenizador, lote_eval, False, 0)

    acumulacion = args.lote_efectivo // args.microlote
    epocas = args.epocas_fijas or args.epocas
    pasos_por_epoca = math.ceil(len(carga_entreno) / acumulacion)
    optimizador, planificador, calentamiento = optimizador_y_planificador(modelo, args, pasos_por_epoca * epocas)

    config = {
        "modelo": args.modelo, "configuracion": args.configuracion, "pliegue": args.pliegue,
        "semilla": args.semilla, "brazo": args.brazo, "max_length": args.max_length, "lr": args.lr,
        "epocas_max": args.epocas, "epocas_fijas": args.epocas_fijas, "weight_decay": args.weight_decay,
        "calentamiento": args.calentamiento, "pasos_calentamiento": calentamiento,
        "lote_efectivo": args.lote_efectivo, "microlote": args.microlote, "acumulacion": acumulacion,
        "gradient_checkpointing": args.gradient_checkpointing,
        "bf16": dispositivo.type == "cuda" and torch.cuda.is_bf16_supported(),
        "modelo_base": base, "etiquetas": ETIQUETAS, "entrada": "texto_unico",
        "conjunto": str(args.conjunto),
        "sha256_conjunto": manifiesto(args.conjunto)["archivos"]["fragmentos_desarrollo.csv"]["sha256"],
        "sha256_script": sha256(Path(__file__)), "sha256_modelo_py": sha256(Path(bases.__file__)),
        "torch": torch.__version__, "cuda": torch.version.cuda, "dispositivo": str(dispositivo),
        "gpu": torch.cuda.get_device_name(0) if dispositivo.type == "cuda" else None,
        "filas": {"entrenamiento": len(entreno), "validacion_interna": len(interna), "validacion": len(fuera)},
        "articulos": {"entrenamiento": int(entreno.id_articulo.nunique()),
                      "validacion_interna": int(interna.id_articulo.nunique()),
                      "validacion": int(fuera.id_articulo.nunique())},
        "suma_pesos_por_clase": suma_clase,
        "fraccion_truncada": {n: fraccion_truncada(f.texto, tokenizador, args.max_length)
                              for n, f in (("entrenamiento", entreno), ("validacion_interna", interna),
                                           ("validacion", fuera))},
    }
    (args.salida / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"suma_pesos_por_clase": suma_clase}), flush=True)

    if dispositivo.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    mejor, mejor_epoca, mejor_estado, historial = -math.inf, 0, None, []
    for epoca in range(1, epocas + 1):
        modelo.train()
        total, n, grupo = 0.0, 0, []
        lotes = len(carga_entreno)
        for i, lote in enumerate(carga_entreno):
            lote = {k: v.to(dispositivo) for k, v in lote.items()}
            etiquetas, pesos = lote.pop("labels"), lote.pop("peso")
            # En el último paso de la época la acumulación puede tener menos microlotes.
            tamano_grupo = acumulacion if (i // acumulacion) < (lotes // acumulacion) else lotes % acumulacion
            with autocast(dispositivo):
                logits = modelo(**lote).logits
            perdida = perdida_ponderada(logits, etiquetas, pesos)
            (perdida / tamano_grupo).backward()
            total += float(perdida.item()) * len(etiquetas)
            n += len(etiquetas)
            if (i + 1) % acumulacion == 0 or i + 1 == lotes:
                torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
                optimizador.step()
                planificador.step()
                optimizador.zero_grad(set_to_none=True)
        registro = {"epoca": epoca, "perdida": total / n, "lr_final": planificador.get_last_lr()[0]}
        if args.pliegue != "todo":
            f1 = f1_articulo(interna, predecir(modelo, carga_interna, dispositivo))
            registro["f1_macro_articulo_interna"] = f1
            if f1 > mejor:  # empate: se queda la época anterior
                mejor, mejor_epoca = f1, epoca
                mejor_estado = {k: v.detach().to("cpu", copy=True) for k, v in modelo.state_dict().items()}
        historial.append(registro)
        print(json.dumps(registro), flush=True)

    resultado = {"historial": historial}
    if args.pliegue == "todo":
        mejor_epoca = epocas
    else:
        modelo.load_state_dict(mejor_estado)
        recarga = f1_articulo(interna, predecir(modelo, carga_interna, dispositivo))
        if abs(recarga - mejor) > 1e-6:
            raise AssertionError(f"El mejor estado recargado no reproduce su F1: {recarga} != {mejor}")
        resultado["f1_macro_articulo_interna"] = mejor
        resultado["f1_recargado"] = recarga
        logits = predecir(modelo, carga_fuera, dispositivo)
        pd.DataFrame({
            "id_fragmento": fuera.id_fragmento, "modelo": args.modelo, "configuracion": args.configuracion,
            "semilla": args.semilla, "pliegue": args.pliegue,
            "logit_real": logits[:, 0], "logit_falsa": logits[:, 1],
            "prob_falsa": torch.softmax(torch.tensor(logits, dtype=torch.float32), dim=-1)[:, 1].numpy(),
        }).to_csv(args.salida / "predicciones.csv", index=False)
    resultado["mejor_epoca"] = mejor_epoca
    if args.guardar_modelo:
        destino = args.salida / "best_model"
        modelo.save_pretrained(destino, safe_serialization=True)
        tokenizador.save_pretrained(destino)
        resultado["sha256_modelo"] = sha256(destino / "model.safetensors")
        resultado["sha256_tokenizer_json"] = sha256(destino / "tokenizer.json")
    resultado["segundos"] = round(time.time() - inicio, 1)
    if dispositivo.type == "cuda":
        resultado["pico_cuda_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 3)
    (args.salida / "resultados.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), "utf-8")
    return resultado


# =========================================================================== experimento

def argumentos(config: dict) -> list[str]:
    """Convierte una configuración ({"modelo": "beto", "brazo": [...]}) en opciones de `corrida`."""
    salida = []
    for clave, valor in config.items():
        if clave == "brazo":
            if valor:
                salida += ["--brazo", *valor]
        elif valor is True:
            salida.append(f"--{clave}")
        elif valor is not False:
            salida += [f"--{clave}", str(valor)]
    return salida


def experimento(nombre: str, opciones: list[str], corridas: Path = CORRIDAS,
                semillas: tuple[int, ...] = SEMILLAS) -> None:
    """Pliegues × semillas de una configuración y su evaluación. Las corridas ya terminadas no se
    repiten; si una falla, se detiene. Una corrida fallida anterior se aparta (no se borra)."""
    carpeta = corridas / "mbert" / nombre
    for semilla in semillas:
        for pliegue in PLIEGUES:
            salida = carpeta / f"{pliegue}_s{semilla}"
            if (salida / "predicciones.csv").exists():
                continue
            if salida.exists():
                apartada = salida.with_name(f"{salida.name}_fallida_{dt.datetime.now():%Y%m%d-%H%M%S}")
                salida.rename(apartada)
                print(f"Corrida incompleta anterior apartada en {apartada}", flush=True)
            comando = [sys.executable, str(Path(__file__)), "corrida", "--pliegue", pliegue,
                       "--semilla", str(semilla), "--configuracion", nombre, "--salida", str(salida),
                       "--no-guardar-modelo", *opciones]
            print(" ".join(comando), flush=True)
            subprocess.run(comando, check=True)
    hechas = sorted(str(p) for p in carpeta.glob("F?_s*/predicciones.csv"))
    (carpeta / "comando.json").write_text(json.dumps({"configuracion": nombre, "argumentos": opciones,
                                                      "semillas": list(semillas)}), "utf-8")
    subprocess.run([sys.executable, str(ROOT / "datos_comunes/evaluar_comun.py"), "--predicciones",
                    *hechas, "--salida", str(carpeta / "evaluacion")], check=True)


def truncado(claves: list[str], max_length: int, conjunto: Path = CONJUNTO) -> dict:
    """M0-len: % de fragmentos del desarrollo que cada tokenizador trunca a `max_length`."""
    textos = leer("fragmentos_desarrollo.csv", conjunto).texto
    salida = {}
    for clave in claves:
        bases.verificar(clave)
        salida[clave] = fraccion_truncada(textos, bases.cargar_tokenizador(bases.carpeta(clave)), max_length)
    return {"max_length": max_length, "fragmentos": len(textos), "fraccion_truncada": salida}


# =========================================================================== decisión y plan

def cargar(nombre: str, corridas: Path = CORRIDAS) -> dict:
    """Evaluación de una configuración de mBERT, del BiLSTM o de una referencia."""
    for ruta in (corridas / "mbert" / nombre / "evaluacion/metricas.json",
                 corridas / "bilstm" / nombre / "evaluacion/metricas.json",
                 corridas / "referencias/evaluacion/metricas.json"):
        if ruta.exists():
            for clave, valor in json.loads(ruta.read_text("utf-8"))["configuraciones"].items():
                if nombre in clave.split("/", 1):
                    return valor
    raise FileNotFoundError(nombre)


def fila(nombre: str, r: dict) -> dict:
    s = r["seleccion"]
    return {"nombre": nombre, "f1": s["f1_macro_articulo_media"], "desv": s["f1_macro_articulo_desv_semillas"],
            "fa": s["falsas_alarmas_articulo_media"], "semillas": s["semillas"], "completo": s["completo"],
            "por_semilla": {int(k): v["f1_macro_articulo_media_pliegues"] for k, v in r["por_semilla"].items()},
            "pliegues": {p: v["articulo_f1_macro"]["media"] for p, v in r["por_pliegue"].items()}}


def decidir(candidata: dict, referencia: dict, brazo: bool) -> dict:
    """Regla fijada (plan común §6): F1 sube ≥ 0,02 y falsas alarmas suben ≤ 2 puntos;
    un brazo además debe mejorar al menos dos de los tres pliegues."""
    sube = candidata["f1"] - referencia["f1"]
    alarmas = candidata["fa"] - referencia["fa"]
    mejoras = sum(candidata["pliegues"][p] > referencia["pliegues"][p] for p in PLIEGUES)
    adopta = sube >= UMBRAL and alarmas <= UMBRAL and (not brazo or mejoras >= 2)
    return {"delta_f1": sube, "delta_falsas_alarmas": alarmas, "pliegues_que_mejoran": mejoras,
            "adopta": adopta}


def elegir_modelo(filas: dict[str, dict], modelos: dict[str, str]) -> dict:
    """Paso 1 (§7): gana el mejor F1; si otro queda a menos de 0,02 y sin más de 2 puntos de falsas
    alarmas por encima, gana el más pequeño y rápido (BETO > MarIA > mBERT > XLM-R)."""
    mejor = max(filas.values(), key=lambda f: f["f1"])
    empatados = [n for n, f in filas.items()
                 if mejor["f1"] - f["f1"] < UMBRAL and f["fa"] - mejor["fa"] <= UMBRAL]
    ganador = min(empatados, key=lambda n: bases.PREFERENCIA.index(modelos[n]))
    return {"mejor_f1": mejor["nombre"], "empatados": sorted(empatados), "ganador": ganador}


def aplicar(config: dict, cambio: dict) -> dict:
    nuevo = {k: (list(v) if isinstance(v, list) else v) for k, v in config.items()}
    for clave, valor in cambio.items():
        if clave == "brazo+":
            nuevo["brazo"] = nuevo.get("brazo", []) + [valor]
        else:
            nuevo[clave] = valor
    return nuevo


# Pasos 2 y 3 del plan (§7): (id, descripción, cambio respecto al ganador, es brazo).
PASO_2 = [("M2a", "lr 1e-5 y hasta 5 épocas", {"lr": "1e-05", "epocas": "5"}),
          ("M2b", "lr 3e-5 y hasta 3 épocas", {"lr": "3e-05", "epocas": "3"})]
M2C = ("M2c", "512 tokens (microlote 2, acumulación 8, gradient checkpointing)",
       {"max-length": "512", "microlote": "2", "gradient-checkpointing": True})
PASO_3 = [("M3b", "Brazo +usmsc", {"brazo+": "usmsc"}), ("M3a", "Brazo +satira", {"brazo+": "satira"}),
          ("M3c", "Brazo +politica", {"brazo+": "politica"})]


def plan(corridas: Path = CORRIDAS) -> None:
    """M0 → M3c en orden; cada experimento cambia una cosa respecto al ganador vigente."""
    carpeta = corridas / "mbert"
    carpeta.mkdir(parents=True, exist_ok=True)
    registro_json = carpeta / "decisiones.json"
    registro: list[dict] = []

    def correr(nombre: str, config: dict, semillas=SEMILLAS) -> dict:
        with (carpeta / f"{nombre}.log").open("a", encoding="utf-8") as log:
            subprocess.run([sys.executable, str(Path(__file__)), "--corridas", str(corridas), "experimento",
                            nombre, "--semillas", *map(str, semillas), *argumentos(config)],
                           check=True, stdout=log, stderr=subprocess.STDOUT)
        return fila(nombre, cargar(nombre, corridas))

    def guardar(ganador, config):
        registro_json.write_text(json.dumps({"ganador": ganador, "config_ganadora": config,
                                             "registro": registro}, ensure_ascii=False, indent=2), "utf-8")

    disponibles = [c for c in bases.MODELOS if not bases.MODELOS[c].get("no_disponible")]
    registro.append({"id": "M0-len", "descripcion": "% de fragmentos truncados a 256 por tokenizador",
                     "resultado": truncado(disponibles, 256)})

    # Paso 0 y prueba rápida 1R.
    m0 = {"modelo": "mbert", "brazo": []}
    filas = {"M0": correr("M0", m0)}
    registro.append({"id": "M0", "descripcion": "Receta actual con comun_v1", "config": m0,
                     "metricas": filas["M0"], "decision": "línea base", "ganador_despues": "M0"})
    guardar("M0", m0)
    configs, modelos = {"M0": m0}, {"M0": "mbert"}
    for ident, clave in (("M1a", "beto"), ("M1b", "roberta_bne"), ("M1c", "xlmr")):
        config = aplicar(m0, {"modelo": clave})
        if clave not in disponibles:
            registro.append({"id": ident, "config": config, "decision": "no se ejecuta: " +
                             bases.MODELOS[clave]["no_disponible"]})
            continue
        if ident in ("M1a", "M1b"):
            rapida = correr(ident, config, semillas=(42,))
            dif = rapida["por_semilla"][42] - filas["M0"]["por_semilla"][42]
            entrada = {"id": f"{ident}-1R", "config": config, "f1_s42": rapida["por_semilla"][42],
                       "f1_s42_M0": filas["M0"]["por_semilla"][42], "diferencia": dif}
            if dif < -UMBRAL:
                registro.append({**entrada, "decision": "descartado en la prueba rápida (> 0,02 por debajo de M0)"})
                guardar("M0", m0)
                continue
            registro.append({**entrada, "decision": "se completan las semillas 43 y 44"})
        filas[ident] = correr(ident, config)
        configs[ident], modelos[ident] = config, clave
    eleccion = elegir_modelo(filas, modelos)
    ganador, config = eleccion["ganador"], configs[eleccion["ganador"]]
    registro.append({"id": "paso 1", "metricas": {n: filas[n] for n in filas}, "regla": eleccion,
                     "ganador_despues": ganador})
    guardar(ganador, config)

    # Paso 2: lr y épocas; después la longitud sobre el ganador de M2a/M2b.
    ref = filas[ganador]
    adoptados = []
    for ident, descripcion, cambio in PASO_2:
        candidata = aplicar(config, cambio)
        c = correr(ident, candidata)
        d = decidir(c, ref, brazo=False)
        registro.append({"id": ident, "descripcion": descripcion, "config": candidata, "frente_a": ganador,
                         "metricas": c, "regla": d, "decision": "adoptado" if d["adopta"] else "rechazado"})
        if d["adopta"]:
            adoptados.append((ident, candidata, c))
    if adoptados:
        # Si los dos se adoptan y quedan a menos de 0,02, gana el más barato (M2b, 3 épocas).
        adoptados.sort(key=lambda x: x[2]["f1"], reverse=True)
        elegido = adoptados[0]
        if len(adoptados) == 2 and adoptados[0][2]["f1"] - adoptados[1][2]["f1"] < UMBRAL:
            elegido = next(a for a in adoptados if a[0] == "M2b")
        ganador, config, ref = elegido
    registro[-1]["ganador_despues"] = ganador
    guardar(ganador, config)
    for ident, descripcion, cambio, brazo in [(*M2C, False)] + [(*p, True) for p in PASO_3]:
        candidata = aplicar(config, cambio)
        c = correr(ident, candidata)
        d = decidir(c, ref, brazo)
        entrada = {"id": ident, "descripcion": descripcion, "config": candidata, "frente_a": ganador,
                   "metricas": c, "regla": d, "decision": "adoptado" if d["adopta"] else "rechazado"}
        if d["adopta"]:
            ganador, config, ref = ident, candidata, c
        entrada["ganador_despues"] = ganador
        registro.append(entrada)
        guardar(ganador, config)
        print(ident, entrada["decision"], f"F1 {c['f1']:.3f}", flush=True)
    print("Ganador:", ganador, config)


# =========================================================================== modelo final

def final(ganador_manual: str | None, motivo: str, corridas: Path = CORRIDAS) -> dict:
    """Modelo final (§8–§9): mediana de épocas de las 9 corridas, 3 semillas con todo el desarrollo,
    predicciones fuera de pliegue y contrato. No calibra: la temperatura la fija Orlando."""
    salida_final = corridas / "mbert/final"
    decisiones = json.loads((corridas / "mbert/decisiones.json").read_text("utf-8"))
    ganador, config = decisiones["ganador"], decisiones["config_ganadora"]
    eleccion = {"ganador_regla": ganador, "manual": False}
    if ganador_manual and ganador_manual != ganador:
        if not motivo:
            raise SystemExit("--ganador necesita --motivo")
        entrada = next(r for r in decisiones["registro"] if r.get("id") == ganador_manual and "config" in r)
        ganador, config = ganador_manual, entrada["config"]
        eleccion.update(manual=True, ganador_elegido=ganador, motivo=motivo)
    carpeta = corridas / "mbert" / ganador
    rutas = [carpeta / f"{p}_s{s}/predicciones.csv" for s in SEMILLAS for p in PLIEGUES]
    epocas = [json.loads((r.parent / "resultados.json").read_text("utf-8"))["mejor_epoca"] for r in rutas]
    epocas_final = int(np.median(epocas))

    oof = cargar_predicciones(rutas)

    salida_final.mkdir(parents=True, exist_ok=True)
    for semilla in SEMILLAS:
        salida = salida_final / f"todo_s{semilla}"
        if not (salida / "best_model/model.safetensors").exists():
            with (salida_final / f"todo_s{semilla}.log").open("w", encoding="utf-8") as log:
                subprocess.run([sys.executable, str(Path(__file__)), "corrida", "--pliegue", "todo",
                                "--semilla", str(semilla), "--configuracion", ganador, "--salida", str(salida),
                                "--epocas-fijas", str(epocas_final), *argumentos(config)],
                               check=True, stdout=log, stderr=subprocess.STDOUT)

    # Con estas predicciones Orlando decide si promediar las semillas y calibra la temperatura (§8.3–§8.4).
    oof[list(COLUMNAS_PRED)].to_csv(salida_final / "predicciones_fuera_de_pliegue.csv", index=False)
    clave = config.get("modelo", "mbert")
    info = bases.resumen(clave, bases.carpeta(clave))
    modelo_s42 = salida_final / "todo_s42/best_model"
    contrato = {
        "modelo": "mbert",
        "version": f"{manifiesto()['version']}_{ganador}_{dt.date.today():%Y%m%d}",
        "eleccion": eleccion,
        "modelo_base": {k: info[k] for k in ("clave", "hub_id", "revision", "sha256")},
        "etiquetas": ETIQUETAS,
        "max_tokens": int(config.get("max-length", 256)),
        "entrada": "texto_unico",
        "temperatura": 1.0, "temperatura_provisional": True,
        "umbral_falsa": 0.5,
        "semillas": list(SEMILLAS), "promediar_logits_semillas": None,  # lo decide Orlando (§8.3)
        "epocas": epocas_final,
        "checkpoints": {f"s{s}": {"ruta": (salida_final / f"todo_s{s}/best_model").relative_to(ROOT).as_posix(),
                                  "sha256": sha256(salida_final / f"todo_s{s}/best_model/model.safetensors")}
                        for s in SEMILLAS},
        "tokenizador": {"ruta": modelo_s42.relative_to(ROOT).as_posix(),
                        "sha256_tokenizer_json": sha256(modelo_s42 / "tokenizer.json")},
        "sha256_conjunto": manifiesto()["archivos"]["fragmentos_desarrollo.csv"]["sha256"],
    }
    (salida_final / "contrato.json").write_text(json.dumps(contrato, ensure_ascii=False, indent=2), "utf-8")
    resumen = {"ganador": ganador, "eleccion": eleccion, "config": config, "epocas_por_corrida": epocas,
               "epocas_final": epocas_final}
    (salida_final / "resumen_final.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return resumen


# =========================================================================== línea de comandos

def opciones_de_corrida(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pliegue", choices=(*PLIEGUES, "todo"), required=True)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--configuracion", required=True, help="nombre de la configuración, p. ej. M1a")
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--epocas-fijas", type=int, default=0,
                        help="entrena exactamente N épocas (obligatorio con --pliegue todo)")
    parser.add_argument("--no-guardar-modelo", dest="guardar_modelo", action="store_false",
                        help="no guarda best_model/ (las corridas de experimentos solo necesitan predicciones)")
    parser.add_argument("--conjunto", type=Path, default=CONJUNTO)
    parser.add_argument("--dispositivo", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--ruta-modelo", type=Path, default=None,
                        help="carpeta local de un modelo base fuera del registro (solo para pruebas)")
    parser.add_argument("--modelo", choices=tuple(bases.MODELOS), default="mbert")
    parser.add_argument("--brazo", choices=("satira", "usmsc", "politica"), nargs="*", default=[],
                        help="brazos de ablación que se añaden al entrenamiento")
    parser.add_argument("--max-length", type=int, default=256, help="tokens, incluidos [CLS] y [SEP]")
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--epocas", type=int, default=3)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--calentamiento", type=float, default=0.10, help="fracción de pasos de calentamiento")
    parser.add_argument("--lote-efectivo", type=int, default=16)
    parser.add_argument("--microlote", type=int, default=4, help="la acumulación es lote efectivo / microlote")
    parser.add_argument("--gradient-checkpointing", action="store_true")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corridas", type=Path, default=CORRIDAS, help="carpeta de resultados")
    sub = parser.add_subparsers(dest="comando", required=True)
    opciones_de_corrida(sub.add_parser("corrida", help="un pliegue y una semilla"))
    p = sub.add_parser("experimento", allow_abbrev=False,
                       help="3 pliegues × semillas de una configuración; el resto de opciones va a `corrida`")
    p.add_argument("nombre", help="nombre de la configuración, p. ej. M1a")
    p.add_argument("--semillas", type=int, nargs="+", default=list(SEMILLAS))
    p = sub.add_parser("truncado", help="M0-len: %% de fragmentos truncados por tokenizador")
    p.add_argument("claves", nargs="*", default=[])
    p.add_argument("--max-length", type=int, default=256)
    sub.add_parser("plan", help="M0 → M3c en orden con la regla de decisión")
    p = sub.add_parser("decidir", help="aplica la regla entre dos configuraciones evaluadas")
    p.add_argument("candidata")
    p.add_argument("referencia")
    p.add_argument("--brazo", action="store_true")
    p = sub.add_parser("final", help="modelo final y contrato")
    p.add_argument("--ganador", help="ID del registro (p. ej. M1a) que sustituye al ganador de la regla")
    p.add_argument("--motivo", default="", help="motivo de la elección manual (obligatorio con --ganador)")
    # Las opciones que `experimento` no conoce son las de `corrida` (p. ej. --modelo beto).
    args, resto = parser.parse_known_args(argv)
    if args.comando != "experimento" and resto:
        parser.error(f"opciones no reconocidas: {' '.join(resto)}")
    args.opciones = [x for x in resto if x != "--"]
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.comando == "corrida":
        print(json.dumps(corrida(args), ensure_ascii=False)[:2000])
    elif args.comando == "experimento":
        experimento(args.nombre, args.opciones, args.corridas, tuple(args.semillas))
    elif args.comando == "truncado":
        claves = args.claves or [c for c in bases.MODELOS if (bases.carpeta(c) / "origen.json").exists()]
        print(json.dumps(truncado(claves, args.max_length), indent=2))
    elif args.comando == "plan":
        plan(args.corridas)
    elif args.comando == "decidir":
        c = fila(args.candidata, cargar(args.candidata, args.corridas))
        r = fila(args.referencia, cargar(args.referencia, args.corridas))
        print(json.dumps({"candidata": c, "referencia": r, "decision": decidir(c, r, args.brazo)},
                         ensure_ascii=False, indent=2))
    else:
        final(args.ganador, args.motivo, args.corridas)


if __name__ == "__main__":
    main()
