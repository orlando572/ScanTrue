"""Entrenamiento del BiLSTM de ScanTrue con el conjunto común `datasets/comun_v1/`.

Es el único script de entrenamiento del BiLSTM. Tiene cinco subcomandos, en el orden en
que se usan (detalle en bilstm/README.md):

  corrida      Entrena un pliegue con una semilla y guarda sus predicciones.
  experimento  Lanza una configuración en 3 pliegues × 3 semillas y la evalúa.
  plan         Ejecuta B0–B8 en orden y aplica la regla de decisión fijada.
  decidir      Compara dos configuraciones ya evaluadas con la regla de decisión.
  final        Entrena el modelo final con todo el desarrollo, ajusta T y escribe el contrato.

Ejemplos:
  bilstm/.venv/bin/python bilstm/entrenar.py experimento B6 --brazo usmsc
  bilstm/.venv/bin/python bilstm/entrenar.py plan
  bilstm/.venv/bin/python bilstm/entrenar.py final --ganador B6 --motivo "…"

Convenciones:
- Etiqueta `etiqueta_falsa`: la salida 1 del modelo es «falsa» y la 0 es «real».
- Pérdida por muestra × `peso` (artículo y fuente) × peso de clase calculado con esos pesos.
- Parada temprana con la validación interna del pliegue (10 % de sus grupos), nunca con la
  fuente que queda fuera; la métrica es F1 macro de artículo.
- Nunca abre la prueba congelada.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bilstm"))
sys.path.insert(0, str(ROOT / "datos_comunes"))
from comun import CONJUNTO, leer, manifiesto, particiones, sha256  # noqa: E402
from evaluar_comun import (  # noqa: E402
    ajustar_temperatura, bootstrap_pareado, cargar_predicciones, evaluar_configuracion, metricas,
    por_articulo, softmax_falsa, tabla_niveles,
)
from modelo import POOLINGS, BiLSTM, construir_vocabulario, tokenize  # noqa: E402

VECTORES = ROOT / "datasets/embeddings/cc.es.300.vec.gz"
CORRIDAS = ROOT / "datasets/comun_v1_corridas"
ETIQUETAS = {"real": 0, "falsa": 1}
PLIEGUES = ("F1", "F2", "F3")
SEMILLAS = (42, 43, 44)

# Plan B1–B8 (docs/mejora_modelos/02_PLAN_BILSTM.md §3): (id, descripción, cambio, es brazo).
EXPERIMENTOS = [
    ("B1", "Pooling max + media", {"pooling": "maxmedia"}, False),
    ("B2", "Pooling con atención aditiva", {"pooling": "atencion"}, False),
    ("B3", "Embeddings congelados 3 épocas, después lr × 0,1",
     {"congelar-embeddings": "3", "lr-embeddings": "0.1"}, False),
    ("B4", "Tamaño oculto 128", {"hidden-dim": "128"}, False),
    ("B5", "Brazo +satira", {"brazo+": "satira"}, True),
    ("B6", "Brazo +usmsc", {"brazo+": "usmsc"}, True),
    ("B7", "Brazo +politica", {"brazo+": "politica"}, True),
    ("B8", "Máximo de 320 tokens", {"max-tokens": "320"}, False),
]


# =========================================================================== datos

class Fragmentos(Dataset):
    def __init__(self, frame: pd.DataFrame, vocab: dict[str, int], max_len: int):
        self.ids = [[vocab.get(w, 1) for w in tokenize(t)[:max_len]] or [1] for t in frame.texto]
        self.etiquetas = frame.etiqueta_falsa.astype(int).tolist()
        self.pesos = frame.peso.astype(float).tolist()

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, i: int):
        return self.ids[i], self.etiquetas[i], self.pesos[i]


def agrupar_lote(lote):
    largos = torch.tensor([len(x[0]) for x in lote], dtype=torch.long)
    ids = torch.zeros((len(lote), int(largos.max())), dtype=torch.long)
    for i, (secuencia, _, _) in enumerate(lote):
        ids[i, :len(secuencia)] = torch.tensor(secuencia, dtype=torch.long)
    etiquetas = torch.tensor([x[1] for x in lote], dtype=torch.long)
    pesos = torch.tensor([x[2] for x in lote], dtype=torch.float32)
    return ids, largos, etiquetas, pesos


def cargador(frame, vocab, max_len, lote, mezclar, semilla):
    return DataLoader(Fragmentos(frame, vocab, max_len), batch_size=lote, shuffle=mezclar,
                      collate_fn=agrupar_lote, generator=torch.Generator().manual_seed(semilla))


# =========================================================================== vectores fastText

def palabras_del_conjunto(conjunto: Path) -> set[str]:
    palabras: set[str] = set()
    for nombre in ("fragmentos_desarrollo.csv", "ablacion_satira.csv", "ablacion_usmsc.csv",
                   "ablacion_politica.csv"):
        for texto in leer(nombre, conjunto).texto:
            palabras.update(tokenize(texto))
    return palabras


def cache_vectores(conjunto: Path, vectores: Path, cache: Path) -> dict:
    """Extrae una sola vez los vectores fastText de las palabras del conjunto común."""
    sha_conjunto = manifiesto(conjunto)["archivos"]["fragmentos_desarrollo.csv"]["sha256"]
    if cache.exists():
        datos = np.load(cache, allow_pickle=False)
        if str(datos["sha_conjunto"]) == sha_conjunto:
            return {"palabras": {w: i for i, w in enumerate(datos["palabras"].tolist())},
                    "matriz": datos["matriz"]}
    buscadas = palabras_del_conjunto(conjunto)
    palabras, filas = [], []
    with gzip.open(vectores, "rt", encoding="utf-8", errors="replace") as stream:
        dimension = int(stream.readline().split()[1])
        for linea in stream:
            palabra, _, valores = linea.partition(" ")
            if palabra not in buscadas:
                continue
            vector = np.array(valores.split(), dtype=np.float32)
            if vector.size == dimension and np.isfinite(vector).all():
                palabras.append(palabra)
                filas.append(vector)
                buscadas.discard(palabra)
    cache.parent.mkdir(parents=True, exist_ok=True)
    matriz = np.stack(filas)
    np.savez(cache, palabras=np.array(palabras), matriz=matriz, sha_conjunto=sha_conjunto,
             tamano=vectores.stat().st_size)
    return {"palabras": {w: i for i, w in enumerate(palabras)}, "matriz": matriz}


def iniciar_embeddings(modelo: BiLSTM, vocab: dict[str, int], vectores: dict) -> dict:
    encontrados = 0
    with torch.no_grad():
        for palabra, indice in vocab.items():
            fila = vectores["palabras"].get(palabra)
            if fila is not None:
                modelo.embedding.weight[indice].copy_(torch.from_numpy(vectores["matriz"][fila]))
                encontrados += 1
    total = len(vocab) - 2
    return {"vocabulario": total, "vectores_encontrados": encontrados,
            "cobertura": encontrados / total if total else 0.0}


# =========================================================================== corrida

def fijar_semilla(semilla: int) -> None:
    random.seed(semilla)
    np.random.seed(semilla)
    torch.manual_seed(semilla)
    torch.cuda.manual_seed_all(semilla)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def pesos_de_clase(frame: pd.DataFrame) -> torch.Tensor:
    """Iguala el peso total de reales y falsas, contando con la columna `peso`."""
    total = frame.peso.sum()
    return torch.tensor([total / (2 * frame.peso[frame.etiqueta_falsa == c].sum()) for c in (0, 1)],
                        dtype=torch.float32)


def perdida_ponderada(logits, etiquetas, pesos, pesos_clase) -> torch.Tensor:
    por_muestra = nn.functional.cross_entropy(logits, etiquetas, reduction="none")
    w = pesos * pesos_clase[etiquetas]
    return (por_muestra * w).sum() / w.sum()


def predecir(modelo: nn.Module, carga: DataLoader, dispositivo: torch.device) -> np.ndarray:
    modelo.eval()
    salida = []
    with torch.inference_mode():
        for ids, largos, _, _ in carga:
            salida.append(modelo(ids.to(dispositivo), largos).float().cpu().numpy())
    return np.concatenate(salida) if salida else np.zeros((0, 2), np.float32)


def f1_articulo(frame: pd.DataFrame, logits: np.ndarray) -> float:
    p = 1 / (1 + np.exp(-(logits[:, 1] - logits[:, 0])))
    arts = frame.assign(p=p).groupby("id_articulo").agg(p=("p", "mean"), y=("etiqueta_falsa", "first"))
    return float(f1_score(arts.y, arts.p >= 0.5, average="macro", labels=[0, 1], zero_division=0))


def corrida(args: argparse.Namespace) -> dict:
    """Entrena un pliegue (o todo el desarrollo con `--pliegue todo`) con una semilla."""
    if args.salida.exists() and any(args.salida.iterdir()):
        raise FileExistsError(f"La salida ya contiene archivos: {args.salida}")
    if args.pliegue == "todo" and not args.epocas_fijas:
        raise ValueError("El modelo final necesita --epocas-fijas (mediana de los pliegues)")
    dispositivo = torch.device(args.dispositivo)
    if dispositivo.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible")
    datos = particiones(args.pliegue, args.brazo, args.conjunto)
    fijar_semilla(args.semilla)
    entreno, interna, fuera = datos["entrenamiento"], datos["validacion_interna"], datos["validacion"]
    vocab = construir_vocabulario(entreno.texto, max_size=args.vocab_size)
    modelo = BiLSTM(len(vocab), 300, args.hidden_dim, args.dropout, args.pooling)
    cobertura = iniciar_embeddings(modelo, vocab, cache_vectores(args.conjunto, args.vectores, args.cache))
    modelo.to(dispositivo)

    emb = [modelo.embedding.weight]
    resto = [p for n, p in modelo.named_parameters() if not n.startswith("embedding.")]
    optimizador = torch.optim.AdamW([{"params": resto, "lr": args.lr}, {"params": emb, "lr": args.lr}],
                                    lr=args.lr, weight_decay=args.weight_decay)
    planificador = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizador, mode="max", factor=0.5, patience=2)
    pesos_clase = pesos_de_clase(entreno).to(dispositivo)
    carga_entreno = cargador(entreno, vocab, args.max_tokens, args.lote, True, args.semilla)
    carga_interna = cargador(interna, vocab, args.max_tokens, 256, False, args.semilla)
    carga_fuera = cargador(fuera, vocab, args.max_tokens, 256, False, args.semilla)

    args.salida.mkdir(parents=True, exist_ok=True)
    config = {
        "modelo": "bilstm", "configuracion": args.configuracion, "pliegue": args.pliegue,
        "semilla": args.semilla, "brazo": args.brazo, "pooling": args.pooling,
        "congelar_embeddings_epocas": args.congelar_embeddings, "lr_embeddings_factor": args.lr_embeddings,
        "max_tokens": args.max_tokens, "hidden_dim": args.hidden_dim, "embedding_dim": 300,
        "dropout": args.dropout, "lr": args.lr, "weight_decay": args.weight_decay, "lote": args.lote,
        "epocas_max": args.epocas, "paciencia": args.paciencia, "epocas_fijas": args.epocas_fijas,
        "vocab_size": len(vocab), "cobertura_vectores": cobertura,
        "etiquetas": ETIQUETAS, "conjunto": str(args.conjunto),
        "sha256_conjunto": manifiesto(args.conjunto)["archivos"]["fragmentos_desarrollo.csv"]["sha256"],
        "sha256_script": sha256(Path(__file__)), "torch": torch.__version__,
        "cuda": torch.version.cuda, "dispositivo": str(dispositivo),
        "filas": {"entrenamiento": len(entreno), "validacion_interna": len(interna), "validacion": len(fuera)},
        "articulos": {"entrenamiento": int(entreno.id_articulo.nunique()),
                      "validacion_interna": int(interna.id_articulo.nunique()),
                      "validacion": int(fuera.id_articulo.nunique())},
    }
    (args.salida / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")

    epocas = args.epocas_fijas or args.epocas
    mejor, mejor_epoca, mejor_estado, quietas, historial = -math.inf, 0, None, 0, []
    for epoca in range(1, epocas + 1):
        congelado = epoca <= args.congelar_embeddings
        modelo.embedding.weight.requires_grad_(not congelado)
        if args.congelar_embeddings:
            optimizador.param_groups[1]["lr"] = (0.0 if congelado else
                                                 optimizador.param_groups[0]["lr"] * args.lr_embeddings)
        modelo.train()
        total = 0.0
        for ids, largos, etiquetas, pesos in carga_entreno:
            optimizador.zero_grad(set_to_none=True)
            logits = modelo(ids.to(dispositivo), largos)
            perdida = perdida_ponderada(logits, etiquetas.to(dispositivo), pesos.to(dispositivo), pesos_clase)
            perdida.backward()
            nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            optimizador.step()
            total += float(perdida.item()) * len(etiquetas)
        registro = {"epoca": epoca, "perdida": total / len(entreno), "embeddings_congelados": congelado}
        if args.pliegue != "todo":
            f1 = f1_articulo(interna, predecir(modelo, carga_interna, dispositivo))
            registro["f1_macro_articulo_interna"] = f1
            planificador.step(f1)
            if f1 > mejor + args.min_delta:
                mejor, mejor_epoca, quietas = f1, epoca, 0
                mejor_estado = {k: v.detach().cpu().clone() for k, v in modelo.state_dict().items()}
            else:
                quietas += 1
        historial.append(registro)
        print(json.dumps(registro), flush=True)
        if args.pliegue != "todo" and quietas >= args.paciencia:
            break
    if args.pliegue == "todo":
        mejor_epoca = epocas
        mejor_estado = {k: v.detach().cpu().clone() for k, v in modelo.state_dict().items()}
    modelo.load_state_dict(mejor_estado)
    if args.guardar_modelo:
        torch.save({"state_dict": mejor_estado, "vocab": vocab, "mejor_epoca": mejor_epoca,
                    "config": {"max_len": args.max_tokens, "embedding_dim": 300, "hidden_dim": args.hidden_dim,
                               "dropout": args.dropout, "pooling": args.pooling, "etiquetas": ETIQUETAS}},
                   args.salida / "modelo.pt")
    resultado = {"mejor_epoca": mejor_epoca, "epocas_corridas": len(historial),
                 "f1_macro_articulo_interna": mejor if args.pliegue != "todo" else None,
                 "historial": historial}
    if args.pliegue != "todo":
        logits = predecir(modelo, carga_fuera, dispositivo)
        z = logits[:, 1] - logits[:, 0]
        pd.DataFrame({"id_fragmento": fuera.id_fragmento, "modelo": "bilstm",
                      "configuracion": args.configuracion, "semilla": args.semilla,
                      "pliegue": args.pliegue, "logit_real": logits[:, 0], "logit_falsa": logits[:, 1],
                      "prob_falsa": 1 / (1 + np.exp(-z))}).to_csv(args.salida / "predicciones.csv", index=False)
    (args.salida / "resultados.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), "utf-8")
    return resultado


# =========================================================================== experimento

def argumentos(config: dict) -> list[str]:
    """Convierte una configuración ({"brazo": [...], "pooling": ...}) en opciones de `corrida`."""
    salida = []
    for clave, valor in config.items():
        if clave == "brazo":
            if valor:
                salida += ["--brazo", *valor]
        else:
            salida += [f"--{clave}", str(valor)]
    return salida


def experimento(nombre: str, opciones: list[str], corridas: Path = CORRIDAS) -> None:
    """3 pliegues × 3 semillas de una configuración y su evaluación. Reutiliza corridas hechas."""
    carpeta = corridas / "bilstm" / nombre
    predicciones = []
    for semilla in SEMILLAS:
        for pliegue in PLIEGUES:
            salida = carpeta / f"{pliegue}_s{semilla}"
            if not (salida / "predicciones.csv").exists():
                if salida.exists():
                    for archivo in salida.iterdir():
                        archivo.unlink()
                comando = [sys.executable, str(Path(__file__)), "corrida", "--pliegue", pliegue,
                           "--semilla", str(semilla), "--configuracion", nombre, "--salida", str(salida),
                           "--no-guardar-modelo", *opciones]
                print(" ".join(comando), flush=True)
                subprocess.run(comando, check=True)
            predicciones.append(str(salida / "predicciones.csv"))
    (carpeta / "comando.json").write_text(json.dumps({"configuracion": nombre, "argumentos": opciones}), "utf-8")
    subprocess.run([sys.executable, str(ROOT / "datos_comunes/evaluar_comun.py"), "--predicciones",
                    *predicciones, "--salida", str(carpeta / "evaluacion")], check=True)


# =========================================================================== decisión y plan

def cargar(nombre: str, corridas: Path = CORRIDAS) -> dict:
    """Busca la evaluación de una configuración del BiLSTM o de una referencia."""
    for ruta in (corridas / "bilstm" / nombre / "evaluacion/metricas.json",
                 corridas / "referencias/evaluacion/metricas.json"):
        if ruta.exists():
            for clave, valor in json.loads(ruta.read_text("utf-8"))["configuraciones"].items():
                if nombre in clave.split("/", 1):
                    return valor
    raise FileNotFoundError(nombre)


def fila(nombre: str, r: dict) -> dict:
    s = r["seleccion"]
    return {"nombre": nombre, "f1": s["f1_macro_articulo_media"], "desv": s["f1_macro_articulo_desv_semillas"],
            "fa": s["falsas_alarmas_articulo_media"],
            "pliegues": {p: v["articulo_f1_macro"]["media"] for p, v in r["por_pliegue"].items()},
            "auc": {p: v["articulo_auc_roc"]["media"] for p, v in r["por_pliegue"].items()}}


def decidir(candidata: dict, referencia: dict, brazo: bool) -> dict:
    """Regla fijada (plan común §6): F1 sube ≥ 0,02 y falsas alarmas suben ≤ 2 puntos;
    un brazo además debe mejorar al menos dos de los tres pliegues."""
    sube = candidata["f1"] - referencia["f1"]
    alarmas = candidata["fa"] - referencia["fa"]
    mejoras = sum(candidata["pliegues"][p] > referencia["pliegues"][p] for p in PLIEGUES)
    adopta = sube >= 0.02 and alarmas <= 0.02 and (not brazo or mejoras >= 2)
    return {"delta_f1": sube, "delta_falsas_alarmas": alarmas, "pliegues_que_mejoran": mejoras,
            "adopta": adopta}


def aplicar(config: dict, cambio: dict) -> dict:
    nuevo = {k: (list(v) if isinstance(v, list) else v) for k, v in config.items()}
    for clave, valor in cambio.items():
        if clave == "brazo+":
            nuevo["brazo"] = nuevo.get("brazo", []) + [valor]
        else:
            nuevo[clave] = valor
    return nuevo


def plan(corridas: Path = CORRIDAS) -> None:
    """B0–B8 en orden; cada uno cambia una cosa respecto al ganador vigente."""
    registro_json = corridas / "bilstm/decisiones.json"

    def correr(nombre: str, config: dict) -> None:
        (corridas / "bilstm").mkdir(parents=True, exist_ok=True)
        with (corridas / "bilstm" / f"{nombre}.log").open("a") as log:
            subprocess.run([sys.executable, str(Path(__file__)), "--corridas", str(corridas), "experimento",
                            nombre, *argumentos(config)], check=True, stdout=log, stderr=subprocess.STDOUT)

    def guardar(ganador, config, registro):
        registro_json.write_text(json.dumps({"ganador": ganador, "config_ganadora": config,
                                             "registro": registro}, ensure_ascii=False, indent=2), "utf-8")

    ganador, config = "B0", {"brazo": []}
    correr("B0", config)
    registro = [{"id": "B0", "descripcion": "Receta actual con comun_v1", "config": config,
                 "metricas": fila("B0", cargar("B0", corridas)), "decision": "línea base",
                 "ganador_despues": "B0"}]
    b1_adoptado = False
    for ident, descripcion, cambio, brazo in EXPERIMENTOS:
        if ident == "B2" and not b1_adoptado:
            registro.append({"id": ident, "descripcion": descripcion, "decision": "no se ejecuta: B1 no se adoptó",
                             "ganador_despues": ganador})
            continue
        candidata = aplicar(config, cambio)
        correr(ident, candidata)
        c, r = fila(ident, cargar(ident, corridas)), fila(ganador, cargar(ganador, corridas))
        d = decidir(c, r, brazo)
        entrada = {"id": ident, "descripcion": descripcion, "config": candidata, "frente_a": ganador,
                   "metricas": c, "regla": d, "decision": "adoptado" if d["adopta"] else "rechazado"}
        if d["adopta"]:
            ganador, config = ident, candidata
            b1_adoptado = b1_adoptado or ident == "B1"
        entrada["ganador_despues"] = ganador
        registro.append(entrada)
        guardar(ganador, config, registro)
        print(ident, entrada["decision"], f"F1 {c['f1']:.3f} vs {r['f1']:.3f}", flush=True)
    guardar(ganador, config, registro)
    print("Ganador:", ganador, config)


# =========================================================================== modelo final

def final(ganador_manual: str | None, motivo: str, corridas: Path = CORRIDAS) -> dict:
    """Modelo final (02_PLAN_BILSTM.md §4–§5): compara con TF-IDF, entrena con todo el desarrollo
    (mediana de épocas de los pliegues), decide si promediar semillas, ajusta la temperatura T
    (provisional hasta calibrar con mBERT) y escribe `contrato.json`."""
    salida_final = corridas / "bilstm/final"
    decisiones = json.loads((corridas / "bilstm/decisiones.json").read_text("utf-8"))
    ganador, config = decisiones["ganador"], decisiones["config_ganadora"]
    eleccion = {"ganador_regla": ganador, "manual": False}
    if ganador_manual and ganador_manual != ganador:
        if not motivo:
            raise SystemExit("--ganador necesita --motivo")
        entrada = next(r for r in decisiones["registro"] if r["id"] == ganador_manual)
        ganador, config = ganador_manual, entrada["config"]
        eleccion.update(manual=True, ganador_elegido=ganador, motivo=motivo)
    carpeta = corridas / "bilstm" / ganador
    rutas = [carpeta / f"{p}_s{s}/predicciones.csv" for s in SEMILLAS for p in PLIEGUES]
    epocas = [json.loads((r.parent / "resultados.json").read_text())["mejor_epoca"] for r in rutas]
    epocas_final = int(np.median(epocas))

    # Predicciones fuera de pliegue del ganador (todas las semillas) y su media de logits.
    oof = cargar_predicciones(rutas)
    media = (oof.groupby(["id_fragmento", "id_articulo", "fuente", "etiqueta_falsa", "pliegue"], as_index=False)
             [["logit_real", "logit_falsa"]].mean())
    media["p"] = softmax_falsa(media.logit_real, media.logit_falsa)
    media["semilla"] = 0
    individual = evaluar_configuracion(oof, bootstrap=False)["seleccion"]["f1_macro_articulo_media"]
    promediada = evaluar_configuracion(media, bootstrap=False)["seleccion"]["f1_macro_articulo_media"]
    promediar = promediada - individual >= 0.01

    # Comparación con TF-IDF: misma métrica y bootstrap pareado por artículo.
    tfidf = cargar_predicciones([corridas / "referencias/ref_tfidf_char35/predicciones.csv"])
    base = media if promediar else oof[oof.semilla == 42]
    tfidf_sel = evaluar_configuracion(tfidf, bootstrap=False)["seleccion"]["f1_macro_articulo_media"]
    seleccion = promediada if promediar else individual
    comparacion = {"bilstm_seleccion": seleccion, "tfidf_seleccion": tfidf_sel,
                   "diferencia_seleccion": seleccion - tfidf_sel,
                   "bootstrap_pareado_fuera_de_pliegue": bootstrap_pareado(base, tfidf)}

    # Temperatura con las predicciones fuera de pliegue (fragmento), sin tocar el umbral.
    temperatura = ajustar_temperatura(base.logit_real, base.logit_falsa, base.etiqueta_falsa)
    p_cal = softmax_falsa(base.logit_real, base.logit_falsa, temperatura)
    p_sin = softmax_falsa(base.logit_real, base.logit_falsa)
    arts_cal = por_articulo(base.assign(p=p_cal))
    fuentes = base.fuente.to_numpy()
    calibracion = {
        "temperatura": temperatura, "fragmentos": int(len(base)),
        "sin_calibrar": metricas(base.etiqueta_falsa, p_sin),
        "calibrado": metricas(base.etiqueta_falsa, p_cal),
        "calibrado_articulo": metricas(arts_cal.y, arts_cal.p),
        "niveles_sin_calibrar": tabla_niveles(p_sin, base.etiqueta_falsa),
        "niveles_calibrados": tabla_niveles(p_cal, base.etiqueta_falsa),
        "niveles_calibrados_por_fuente": {
            f: tabla_niveles(p_cal[fuentes == f], base.etiqueta_falsa.to_numpy()[fuentes == f])
            for f in sorted(base.fuente.unique())},
    }

    # Modelo final con todo el desarrollo.
    salida_final.mkdir(parents=True, exist_ok=True)
    semillas_final = SEMILLAS if promediar else (42,)
    for semilla in semillas_final:
        salida = salida_final / f"todo_s{semilla}"
        if not (salida / "modelo.pt").exists():
            with (salida_final / f"todo_s{semilla}.log").open("w") as log:
                subprocess.run([sys.executable, str(Path(__file__)), "corrida", "--pliegue", "todo",
                                "--semilla", str(semilla), "--configuracion", ganador, "--salida", str(salida),
                                "--epocas-fijas", str(epocas_final), *argumentos(config)],
                               check=True, stdout=log, stderr=subprocess.STDOUT)

    oof.drop(columns=["p", "pliegue_dato"]).to_csv(salida_final / "predicciones_fuera_de_pliegue.csv", index=False)
    media.drop(columns=["p", "semilla"]).assign(modelo="bilstm", configuracion=f"{ganador}_media_semillas") \
        .to_csv(salida_final / "predicciones_fuera_de_pliegue_media_semillas.csv", index=False)
    contrato = {
        "modelo": "bilstm",
        "version": f"{manifiesto()['version']}_{ganador}_{dt.date.today():%Y%m%d}", "eleccion": eleccion,
        "etiquetas": ETIQUETAS,
        "max_tokens": int(config.get("max-tokens", 192)),
        "pooling": config.get("pooling", "final"), "hidden_dim": int(config.get("hidden-dim", 64)),
        "temperatura": round(temperatura, 4), "temperatura_provisional": True,
        "nota_temperatura": "Ajustada solo con las predicciones fuera de pliegue del BiLSTM; se recalibra "
                            "junto con mBERT (01_PLAN_COMUN.md §5) antes de usarla en el backend.",
        "umbral_falsa": 0.5,
        "semillas": list(semillas_final), "promediar_logits_semillas": promediar,
        "epocas": epocas_final,
        "checkpoints": {f"s{s}": {"ruta": str((salida_final / f"todo_s{s}/modelo.pt").relative_to(ROOT)),
                                  "sha256": sha256(salida_final / f"todo_s{s}/modelo.pt")}
                        for s in semillas_final},
        "sha256_conjunto": manifiesto()["archivos"]["fragmentos_desarrollo.csv"]["sha256"],
    }
    (salida_final / "contrato.json").write_text(json.dumps(contrato, ensure_ascii=False, indent=2), "utf-8")
    resumen = {"ganador": ganador, "eleccion": eleccion, "config": config, "epocas_por_corrida": epocas,
               "epocas_final": epocas_final, "seleccion_semilla_individual_media": individual,
               "seleccion_media_logits": promediada, "promediar_semillas": promediar,
               "comparacion_tfidf": comparacion, "calibracion": calibracion}
    (salida_final / "resumen_final.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(comparacion, indent=2), "\nT =", temperatura)
    return resumen


# =========================================================================== línea de comandos

def opciones_de_corrida(parser: argparse.ArgumentParser, completa: bool) -> None:
    """Opciones del modelo. `completa` añade las que solo tiene una corrida suelta."""
    if completa:
        parser.add_argument("--pliegue", choices=(*PLIEGUES, "todo"), required=True)
        parser.add_argument("--semilla", type=int, default=42)
        parser.add_argument("--configuracion", required=True, help="nombre de la configuración, p. ej. B6")
        parser.add_argument("--salida", type=Path, required=True)
        parser.add_argument("--epocas-fijas", type=int, default=0,
                            help="entrena exactamente N épocas (obligatorio con --pliegue todo)")
        parser.add_argument("--no-guardar-modelo", dest="guardar_modelo", action="store_false",
                            help="no guarda modelo.pt (las corridas de experimentos solo necesitan predicciones)")
        parser.add_argument("--conjunto", type=Path, default=CONJUNTO)
        parser.add_argument("--dispositivo", choices=("cuda", "cpu"), default="cuda")
        parser.add_argument("--vectores", type=Path, default=VECTORES)
        parser.add_argument("--cache", type=Path, default=CORRIDAS / "cache_fasttext_cc300.npz")
    parser.add_argument("--brazo", choices=("satira", "usmsc", "politica"), nargs="*", default=[],
                        help="brazos de ablación que se añaden al entrenamiento")
    parser.add_argument("--pooling", choices=POOLINGS, default="final")
    parser.add_argument("--congelar-embeddings", type=int, default=0,
                        help="épocas con embeddings congelados; después lr × --lr-embeddings")
    parser.add_argument("--lr-embeddings", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--lote", type=int, default=32)
    parser.add_argument("--epocas", type=int, default=20)
    parser.add_argument("--paciencia", type=int, default=5)
    parser.add_argument("--min-delta", type=float, default=0.001)
    parser.add_argument("--vocab-size", type=int, default=30000)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corridas", type=Path, default=CORRIDAS, help="carpeta de resultados")
    sub = parser.add_subparsers(dest="comando", required=True)
    opciones_de_corrida(sub.add_parser("corrida", help="un pliegue y una semilla"), completa=True)
    p = sub.add_parser("experimento", help="3 pliegues × 3 semillas de una configuración")
    p.add_argument("nombre", help="nombre de la configuración, p. ej. B6")
    p.add_argument("opciones", nargs=argparse.REMAINDER,
                   help="opciones del modelo para `corrida` (p. ej. --brazo usmsc)")
    sub.add_parser("plan", help="B0–B8 en orden con la regla de decisión")
    p = sub.add_parser("decidir", help="aplica la regla entre dos configuraciones evaluadas")
    p.add_argument("candidata")
    p.add_argument("referencia")
    p.add_argument("--brazo", action="store_true")
    p = sub.add_parser("final", help="modelo final, temperatura y contrato")
    p.add_argument("--ganador", help="ID del registro (p. ej. B6) que sustituye al ganador de la regla")
    p.add_argument("--motivo", default="", help="motivo de la elección manual (obligatorio con --ganador)")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.comando == "corrida":
        print(json.dumps(corrida(args), ensure_ascii=False)[:2000])
    elif args.comando == "experimento":
        experimento(args.nombre, args.opciones, args.corridas)
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
