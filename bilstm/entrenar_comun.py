"""Entrena el BiLSTM con el conjunto común `comun_v1` (docs/mejora_modelos/02_PLAN_BILSTM.md §2).

Una corrida = un pliegue y una semilla. Ejemplo (B0):
  bilstm/.venv/bin/python bilstm/entrenar_comun.py --pliegue F1 --semilla 42 \
      --configuracion B0 --salida datasets/comun_v1_corridas/bilstm/B0/F1_s42

Diferencias con los scripts anteriores (que no se tocan):
- Etiqueta `etiqueta_falsa`: la neurona 1 es «falsa», la 0 es «real».
- Pérdida por muestra × `peso` (artículo/fuente) × peso de clase calculado con esos pesos.
- Parada temprana con la validación interna del pliegue (10 % de sus grupos), nunca con
  la fuente que queda fuera; la métrica es F1 macro de artículo.
- Guarda `predicciones.csv` (formato común §7), `config.json` y `resultados.json`.
- `--pliegue todo --epocas N` entrena el modelo final con todo el desarrollo y épocas fijas.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bilstm"))
sys.path.insert(0, str(ROOT / "datos_comunes"))
from comun import CONJUNTO, leer, manifiesto, particiones, sha256  # noqa: E402
from entrenar_baseline import build_vocab, tokenize  # noqa: E402

VECTORES = ROOT / "datasets/embeddings_preentrenados/cc.es.300.vec.gz"
CACHE = ROOT / "datasets/comun_v1_corridas/cache_fasttext_cc300.npz"
ETIQUETAS = {"real": 0, "falsa": 1}


# --------------------------------------------------------------------------- datos

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


# --------------------------------------------------------------------------- modelo

class BiLSTMComun(nn.Module):
    """Embedding → BiLSTM 1 capa → pooling → dropout → lineal(2). Neurona 1 = falsa."""

    def __init__(self, vocab_size: int, embedding_dim: int = 300, hidden_dim: int = 64,
                 dropout: float = 0.3, pooling: str = "final"):
        super().__init__()
        if pooling not in ("final", "maxmedia", "atencion"):
            raise ValueError(f"pooling desconocido: {pooling}")
        self.pooling = pooling
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        salida = hidden_dim * (4 if pooling == "maxmedia" else 2)
        if pooling == "atencion":
            self.atencion = nn.Sequential(nn.Linear(2 * hidden_dim, hidden_dim), nn.Tanh(),
                                          nn.Linear(hidden_dim, 1, bias=False))
        self.classifier = nn.Linear(salida, 2)

    def forward(self, ids: torch.Tensor, largos: torch.Tensor) -> torch.Tensor:
        empaquetado = pack_padded_sequence(self.embedding(ids), largos.cpu(), batch_first=True,
                                           enforce_sorted=False)
        salidas, (oculto, _) = self.lstm(empaquetado)
        if self.pooling == "final":
            representacion = torch.cat((oculto[-2], oculto[-1]), dim=1)
        else:
            h, _ = pad_packed_sequence(salidas, batch_first=True)
            mascara = (torch.arange(h.size(1), device=h.device)[None, :]
                       < largos.to(h.device)[:, None])
            if self.pooling == "maxmedia":
                maximo = h.masked_fill(~mascara[..., None], float("-inf")).max(dim=1).values
                media = (h * mascara[..., None]).sum(1) / mascara.sum(1, keepdim=True)
                representacion = torch.cat((maximo, media), dim=1)
            else:
                puntaje = self.atencion(h).squeeze(-1).masked_fill(~mascara, float("-inf"))
                alfa = torch.softmax(puntaje, dim=1)
                representacion = (alfa[..., None] * h).sum(1)
        return self.classifier(self.dropout(representacion))


# --------------------------------------------------------------------------- vectores

def palabras_del_conjunto(conjunto: Path) -> set[str]:
    palabras: set[str] = set()
    for nombre in ("fragmentos_desarrollo.csv", "ablacion_satira.csv", "ablacion_usmsc.csv",
                   "ablacion_politica.csv"):
        for texto in leer(nombre, conjunto).texto:
            palabras.update(tokenize(texto))
    return palabras


def cache_vectores(conjunto: Path = CONJUNTO, vectores: Path = VECTORES, cache: Path = CACHE) -> dict:
    """Extrae una sola vez los vectores fastText de las palabras del conjunto común."""
    sha_conjunto = manifiesto(conjunto)["archivos"]["fragmentos_desarrollo.csv"]["sha256"]
    if cache.exists():
        datos = np.load(cache, allow_pickle=False)
        if str(datos["sha_conjunto"]) == sha_conjunto:
            return {"palabras": {w: i for i, w in enumerate(datos["palabras"].tolist())},
                    "matriz": datos["matriz"], "archivo": str(vectores), "tamano": int(datos["tamano"])}
    buscadas = palabras_del_conjunto(conjunto)
    palabras, filas = [], []
    with gzip.open(vectores, "rt", encoding="utf-8", errors="replace") as stream:
        cabecera = stream.readline().split()
        dimension = int(cabecera[1])
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
    return {"palabras": {w: i for i, w in enumerate(palabras)}, "matriz": matriz,
            "archivo": str(vectores), "tamano": vectores.stat().st_size}


def iniciar_embeddings(modelo: BiLSTMComun, vocab: dict[str, int], vectores: dict) -> dict:
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


# --------------------------------------------------------------------------- entrenamiento

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


def predecir(modelo: nn.Module, cargador: DataLoader, dispositivo: torch.device) -> np.ndarray:
    modelo.eval()
    salida = []
    with torch.inference_mode():
        for ids, largos, _, _ in cargador:
            salida.append(modelo(ids.to(dispositivo), largos).float().cpu().numpy())
    return np.concatenate(salida) if salida else np.zeros((0, 2), np.float32)


def f1_articulo(frame: pd.DataFrame, logits: np.ndarray) -> float:
    z = logits[:, 1] - logits[:, 0]
    p = 1 / (1 + np.exp(-z))
    arts = frame.assign(p=p).groupby("id_articulo").agg(p=("p", "mean"), y=("etiqueta_falsa", "first"))
    return float(f1_score(arts.y, arts.p >= 0.5, average="macro", labels=[0, 1], zero_division=0))


def cargador(frame, vocab, max_len, lote, mezclar, semilla):
    return DataLoader(Fragmentos(frame, vocab, max_len), batch_size=lote, shuffle=mezclar,
                      collate_fn=agrupar_lote, generator=torch.Generator().manual_seed(semilla))


def entrenar(args: argparse.Namespace) -> dict:
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
    vocab = build_vocab(entreno.texto, max_size=args.vocab_size)
    modelo = BiLSTMComun(len(vocab), 300, args.hidden_dim, args.dropout, args.pooling)
    cobertura = iniciar_embeddings(modelo, vocab, cache_vectores(args.conjunto, args.vectores, args.cache))
    modelo.to(dispositivo)

    emb = [modelo.embedding.weight]
    resto = [p for n, p in modelo.named_parameters() if not n.startswith("embedding.")]
    optimizador = torch.optim.AdamW([{"params": resto, "lr": args.lr},
                                     {"params": emb, "lr": args.lr}],
                                    lr=args.lr, weight_decay=args.weight_decay)
    planificador = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizador, mode="max",
                                                              factor=0.5, patience=2)
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


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pliegue", choices=("F1", "F2", "F3", "todo"), required=True)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--configuracion", required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--conjunto", type=Path, default=CONJUNTO)
    parser.add_argument("--brazo", choices=("satira", "usmsc", "politica"), nargs="*", default=[],
                        help="uno o varios brazos de ablación que se añaden al entrenamiento")
    parser.add_argument("--pooling", choices=("final", "maxmedia", "atencion"), default="final")
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
    parser.add_argument("--epocas-fijas", type=int, default=0)
    parser.add_argument("--vocab-size", type=int, default=30000)
    parser.add_argument("--dispositivo", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--vectores", type=Path, default=VECTORES)
    parser.add_argument("--cache", type=Path, default=CACHE)
    return parser.parse_args(argv)


if __name__ == "__main__":
    print(json.dumps(entrenar(parse_args()), ensure_ascii=False)[:2000])
