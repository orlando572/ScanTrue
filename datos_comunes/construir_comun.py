"""Construye el conjunto común `datasets/comun_v1/` (docs/mejora_modelos/01_PLAN_COMUN.md §3).

Uso: bilstm/.venv/bin/python datos_comunes/construir_comun.py [--tope 400] [--sobrescribir]

No modifica los datos originales. Etiqueta común: `etiqueta_falsa` (1 = falsa, 0 = real).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bilstm"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from depurar_y_particionar import UnionFind, related_keys  # noqa: E402
from entrenar_baseline import TOKEN_PATTERN, tokenize  # noqa: E402
from limpieza import PATRONES, PATRONES_PREVIOS, limpiar, normalizar  # noqa: E402

VERSION = "comun_v1.0"
SEMILLA = 42
ENTRADA = ROOT / "datasets/unificado_total/todos_los_textos_unicos.csv"
SALIDA = ROOT / "datasets/comun_v1"
MIN_TOKENS = 100
MAX_FRAGMENTOS = 4
FRACCION_CONGELADA = 0.15
FUENTES = {"spanish_fake_news_corpus_v1": "v1", "fakedes_iberlef_2021": "fakedes",
           "polyglotfakefacts_v2": "polyglot", "falledesinfo_es": "falledesinfo"}
FUENTES_PRINCIPALES = ("v1", "fakedes", "polyglot")
PLIEGUES = {"F1": "v1", "F2": "fakedes", "F3": "polyglot"}
PLIEGUE_DE_FUENTE = {fuente: pliegue for pliegue, fuente in PLIEGUES.items()}
SATIRA = {"eldizque.com", "elruinaversal.com", "haynoticia.es", "lavozpopular.com",
          "elmundotoday.com"}
REDES = {"facebook.com", "m.facebook.com", "twitter.com", "x.com", "whatsapp.com"}
MAX_PAREJAS_POLITICA = 1000
COLUMNAS = ("id_fragmento", "id_articulo", "grupo", "fuente", "dominio", "texto",
            "etiqueta_falsa", "peso", "tokens_bilstm", "pliegue")
_FIN_ORACION = re.compile(r"[.!?…]")


def dominio(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def sha256_archivo(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for bloque in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(bloque)
    return hasher.hexdigest()


def semilla_de(texto: str) -> int:
    return int(hashlib.sha256(f"{SEMILLA}|{texto}".encode()).hexdigest()[:8], 16)


# --------------------------------------------------------------------------- fragmentos

def separar_titulo(texto: str, titulo: str) -> tuple[str, str]:
    """El unificado guarda `texto` = titular + cuerpo; separa el cuerpo."""
    titulo = (titulo or "").strip()
    if titulo and texto.startswith(titulo):
        return titulo, texto[len(titulo):].strip()
    return titulo, texto.strip()


def fragmentar(titulo: str, cuerpo: str, rng: np.random.Generator, tope: int,
               minimo: int = MIN_TOKENS, maximo_fragmentos: int = MAX_FRAGMENTOS) -> list[str]:
    """Corta un artículo en hasta `maximo_fragmentos` fragmentos de `minimo`–`tope` tokens.

    El tamaño de cada fragmento se sortea antes de mirar nada del artículo salvo su
    longitud total; nunca se usa la etiqueta. El titular solo puede ir en el primero.
    """
    completo = f"{titulo} {cuerpo}".strip() if titulo else cuerpo
    tramos = [m.span() for m in TOKEN_PATTERN.finditer(completo)]
    total = len(tramos)
    if total < minimo:
        return []
    inicios = {0}
    if titulo:
        inicios.add(len(TOKEN_PATTERN.findall(titulo)))
    for i in range(1, total):
        if _FIN_ORACION.search(completo, tramos[i - 1][1], tramos[i][0]):
            inicios.add(i)
    inicios_ordenados = sorted(inicios)

    tamanos: list[int] = []
    while len(tamanos) < maximo_fragmentos:
        objetivo = int(rng.integers(minimo, tope + 1))
        if not tamanos and total <= objetivo:
            return [completo]
        if sum(tamanos) + objetivo > total:
            break
        tamanos.append(objetivo)
    hueco = (total - sum(tamanos)) / (len(tamanos) - 1) if len(tamanos) > 1 else 0.0

    fragmentos, fin_anterior = [], 0
    for indice, objetivo in enumerate(tamanos):
        plan = round(sum(tamanos[:indice]) + indice * hueco)
        inicio = max(plan, fin_anterior)
        if indice:
            cercanos = [s for s in inicios_ordenados if fin_anterior <= s and abs(s - plan) <= 40]
            if cercanos:
                inicio = min(cercanos, key=lambda s: (abs(s - plan), s))
        if total - inicio < minimo:
            break
        limite = min(inicio + objetivo, total)
        finales = [s for s in inicios_ordenados if inicio + minimo <= s <= limite]
        if limite == total:
            finales.append(total)
        fin = max(finales) if finales else limite
        if fin - inicio < minimo:
            continue
        corte = tramos[fin][0] if fin < total else len(completo)
        fragmentos.append(completo[tramos[inicio][0]:corte].strip())
        fin_anterior = fin
    return fragmentos


# --------------------------------------------------------------------------- grupos

def tejas(texto: str) -> set[tuple[str, ...]]:
    palabras = re.findall(r"\w+", texto.casefold())
    return set(zip(*(palabras[i:] for i in range(5))))


def agrupar(filas: list[dict]) -> tuple[list[str], dict]:
    """Une huella, titular, cuerpo y URL (unificado) más casi duplicados por tejas de 5 palabras."""
    union = UnionFind(len(filas))
    primero: dict[str, int] = {}
    for i, fila in enumerate(filas):
        claves = related_keys(fila)
        if fila.get("url", "").strip():
            url = fila["url"].strip().casefold().split("://", 1)[-1]
            claves.append("url_sin_esquema:" + url.removeprefix("www.").rstrip("/"))
        for clave in claves:
            previo = primero.setdefault(clave, i)
            if previo != i:
                union.union(previo, i)
    conjuntos = [tejas(f["texto"]) for f in filas]
    indice = defaultdict(list)
    for i, teja in enumerate(conjuntos):
        for t in teja:
            indice[t].append(i)
    pares_casi = 0
    for i, teja in enumerate(conjuntos):
        cuentas = Counter()
        for t in teja:
            lista = indice[t]
            if len(lista) <= 20:
                cuentas.update(j for j in lista if j > i)
        for j, compartidas in cuentas.items():
            menor = min(len(teja), len(conjuntos[j]))
            if compartidas >= 5 and menor and compartidas / menor >= 0.65:
                if union.find(i) != union.find(j):
                    pares_casi += 1
                union.union(i, j)
    for clave, grupo in ((f["grupo_forzado"], i) for i, f in enumerate(filas) if f.get("grupo_forzado")):
        previo = primero.setdefault("forzado:" + clave, grupo)
        union.union(previo, grupo)
    miembros = defaultdict(list)
    for i in range(len(filas)):
        miembros[union.find(i)].append(i)
    ids = [""] * len(filas)
    for lista in miembros.values():
        gid = hashlib.sha256("|".join(sorted(filas[i]["id"] for i in lista)).encode()).hexdigest()[:16]
        for i in lista:
            ids[i] = gid
    return ids, {"grupos": len(miembros), "grupos_con_varias_filas":
                 sum(len(v) > 1 for v in miembros.values()),
                 "uniones_nuevas_por_casi_duplicado": pares_casi}


def elegir_congelada(articulos: list[dict], fraccion: float, semilla: int) -> set[str]:
    """Elige ~`fraccion` de los grupos, estratificado por fuente y clase del grupo."""
    por_grupo = defaultdict(list)
    for a in articulos:
        por_grupo[a["grupo"]].append(a)
    estratos = defaultdict(list)
    for grupo, lista in sorted(por_grupo.items()):
        primero = min(lista, key=lambda a: a["id_articulo"])
        clase = Counter(a["etiqueta_falsa"] for a in lista).most_common(1)[0][0]
        estratos[(primero["fuente"], clase)].append(grupo)
    rng = np.random.default_rng(semilla)
    elegidos = set()
    for clave in sorted(estratos):
        grupos = estratos[clave]
        orden = rng.permutation(len(grupos))
        meta = fraccion * sum(len(por_grupo[g]) for g in grupos)
        acumulado = 0
        for posicion in orden:
            grupo = grupos[posicion]
            n = len(por_grupo[grupo])
            if acumulado + n / 2 > meta:
                continue
            elegidos.add(grupo)
            acumulado += n
    return elegidos


# --------------------------------------------------------------------------- construcción

def leer_unificado(path: Path) -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def preparar_articulo(fila: dict, fuente: str, ejemplos: dict | None, conteo: Counter) -> dict:
    titulo, cuerpo = separar_titulo(fila["texto"], fila["titulo"])
    titulo, _ = normalizar(titulo)
    cuerpo, aplicados = limpiar(cuerpo, ejemplos)
    for nombre in aplicados:
        conteo[(nombre, fuente, 1 - int(fila["etiqueta_binaria"]))] += 1
    return {"id": fila["id"], "id_articulo": fila["id"], "titulo": titulo, "cuerpo": cuerpo,
            "texto": f"{titulo} {cuerpo}".strip(), "titulo_original": fila["titulo"],
            "url": fila["url"], "fuente": fuente, "dominio": dominio(fila["url"]),
            "etiqueta_falsa": 1 - int(fila["etiqueta_binaria"])}


def construir(entrada: Path, salida: Path, tope: int) -> dict:
    filas = leer_unificado(entrada)
    ejemplos: dict = {}
    conteo_patrones: Counter = Counter()
    excluidas = Counter()
    principales, satira, falle = [], [], []
    for fila in filas:
        fuente = FUENTES.get(fila["dataset_principal"])
        if not fuente or fila["etiqueta_binaria"] not in ("0", "1"):
            continue
        dom = dominio(fila["url"])
        if dom in REDES:
            excluidas[f"red_social:{fuente}"] += 1
            continue
        if dom in SATIRA:
            if fuente == "v1":
                satira.append(preparar_articulo(fila, fuente, None, Counter()))
            else:
                excluidas[f"satira_fuera_de_v1:{fuente}"] += 1
            continue
        articulo = preparar_articulo(fila, fuente, ejemplos, conteo_patrones)
        (falle if fuente == "falledesinfo" else principales).append(articulo)

    usmsc = []
    for fila in filas:
        if fila["dataset_principal"] == "usmsc_edds" and "usmsc_binario_derivado" in fila["tipo_tarea"] \
                and fila["etiqueta_binaria"] in ("0", "1"):
            texto, _ = limpiar(fila["texto"])
            usmsc.append({"id": fila["id"], "id_articulo": fila["id"], "titulo": "", "cuerpo": texto,
                          "texto": texto, "titulo_original": "", "url": "", "fuente": "usmsc",
                          "dominio": "", "etiqueta_falsa": 1 - int(fila["etiqueta_binaria"])})
    politica = parejas_politica(filas)

    todas = principales + falle + satira + usmsc + politica
    grupos, info_grupos = agrupar(todas)
    for articulo, grupo in zip(todas, grupos):
        articulo["grupo"] = grupo

    # Fragmentos de los artículos principales y de FalleDesinfo.
    descartados_cortos = Counter()
    frag_principales = []
    for articulo in principales + falle:
        rng = np.random.default_rng(semilla_de(articulo["id_articulo"]))
        trozos = fragmentar(articulo["titulo"], articulo["cuerpo"], rng, tope)
        if not trozos:
            descartados_cortos[(articulo["fuente"], articulo["etiqueta_falsa"])] += 1
            continue
        articulo["n_fragmentos"] = len(trozos)
        for n, trozo in enumerate(trozos):
            frag_principales.append(fila_fragmento(articulo, n, trozo, 1.0 / len(trozos)))

    articulos_ok = {f["id_articulo"] for f in frag_principales}
    vivos = [a for a in principales if a["id_articulo"] in articulos_ok]
    congelados = elegir_congelada(vivos, FRACCION_CONGELADA, SEMILLA)
    grupos_falle = {a["grupo"] for a in falle}
    congelados |= grupos_falle
    for frag in frag_principales:
        if frag["grupo"] in congelados or frag["fuente"] == "falledesinfo":
            frag["pliegue"] = "congelada"
        else:
            frag["pliegue"] = PLIEGUE_DE_FUENTE[frag["fuente"]]

    desarrollo = [f for f in frag_principales if f["pliegue"] != "congelada"]
    congelada = [f for f in frag_principales if f["pliegue"] == "congelada"]
    # Peso por fuente: Polyglot no pesa más que cada otra fuente del desarrollo.
    articulos_dev = Counter(f["fuente"] for f in desarrollo if f["id_fragmento"].endswith("#0"))
    factor_polyglot = min(1.0, min(articulos_dev["v1"], articulos_dev["fakedes"]) / articulos_dev["polyglot"])
    for frag in frag_principales:
        if frag["fuente"] == "polyglot":
            frag["peso"] *= factor_polyglot

    # Brazos de ablación: nunca filas de grupos de la prueba congelada.
    ablacion = {}
    retiradas_ablacion = Counter()
    frag_satira = []
    for articulo in satira:
        if articulo["grupo"] in congelados:
            retiradas_ablacion["satira"] += 1
            continue
        rng = np.random.default_rng(semilla_de(articulo["id_articulo"]))
        trozos = fragmentar(articulo["titulo"], articulo["cuerpo"], rng, tope)
        for n, trozo in enumerate(trozos):
            frag_satira.append(fila_fragmento(articulo, n, trozo, 1.0 / len(trozos), "ablacion"))
        if not trozos:
            retiradas_ablacion["satira_corta"] += 1
    ablacion["satira"] = frag_satira
    for nombre, lista in (("usmsc", usmsc), ("politica", politica)):
        filas_brazo = []
        for articulo in lista:
            if articulo["grupo"] in congelados:
                retiradas_ablacion[nombre] += 1
                continue
            filas_brazo.append(fila_fragmento(articulo, 0, articulo["texto"], 1.0, "ablacion"))
        ablacion[nombre] = filas_brazo

    salida.mkdir(parents=True, exist_ok=True)
    archivos = {
        "fragmentos_desarrollo.csv": desarrollo,
        "fragmentos_prueba_congelada.csv": congelada,
        "ablacion_satira.csv": ablacion["satira"],
        "ablacion_usmsc.csv": ablacion["usmsc"],
        "ablacion_politica.csv": ablacion["politica"],
    }
    for nombre, lista in archivos.items():
        escribir_csv(salida / nombre, lista)
    pliegues = {p: {"entrena": [x for x in FUENTES_PRINCIPALES if x != f], "valida": f}
                for p, f in PLIEGUES.items()}
    pliegues["_notas"] = [
        "Validación interna: 10 % de los grupos de entrenamiento del pliegue (datos_comunes/comun.py).",
        "Se excluyen del entrenamiento las filas cuyo grupo aparece en la fuente que queda fuera.",
        "Los brazos de ablación solo se añaden al entrenamiento y nunca con filas de la fuente que queda fuera.",
    ]
    (salida / "pliegues.json").write_text(json.dumps(pliegues, ensure_ascii=False, indent=2), "utf-8")

    manifiesto = construir_manifiesto(entrada, salida, tope, archivos, conteo_patrones, excluidas,
                                      descartados_cortos, info_grupos, factor_polyglot,
                                      retiradas_ablacion, principales, satira, desarrollo)
    (salida / "manifest.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), "utf-8")
    (salida / "REPORTE.md").write_text(reporte(manifiesto, ejemplos, desarrollo), "utf-8")
    return manifiesto


def fila_fragmento(articulo: dict, n: int, texto: str, peso: float, pliegue: str = "") -> dict:
    return {"id_fragmento": f"{articulo['id_articulo']}#{n}", "id_articulo": articulo["id_articulo"],
            "grupo": articulo["grupo"], "fuente": articulo["fuente"], "dominio": articulo["dominio"],
            "texto": texto, "etiqueta_falsa": articulo["etiqueta_falsa"], "peso": peso,
            "tokens_bilstm": len(tokenize(texto)), "pliegue": pliegue}


def parejas_politica(filas: list[dict]) -> list[dict]:
    """Hasta 1.000 parejas real/falsa con el mismo titular; cada pareja forma un grupo."""
    por_titulo = defaultdict(lambda: {"0": [], "1": []})
    for fila in filas:
        if fila["dataset_principal"] == "spanish_political_fake_news" and \
                fila["etiqueta_binaria"] in ("0", "1") and fila["titulo"].strip():
            por_titulo[fila["titulo"].strip()][fila["etiqueta_binaria"]].append(fila)
    titulos = sorted(t for t, d in por_titulo.items() if d["0"] and d["1"])
    rng = np.random.default_rng(SEMILLA)
    elegidos = [titulos[i] for i in sorted(rng.choice(len(titulos), min(MAX_PAREJAS_POLITICA, len(titulos)),
                                                      replace=False))]
    salida = []
    for titulo in elegidos:
        clave = hashlib.sha256(titulo.encode()).hexdigest()[:16]
        for etiqueta in ("1", "0"):
            fila = sorted(por_titulo[titulo][etiqueta], key=lambda f: f["id"])[0]
            texto, _ = limpiar(fila["texto"])
            salida.append({"id": fila["id"], "id_articulo": fila["id"], "titulo": "",
                           "cuerpo": texto, "texto": texto, "titulo_original": fila["titulo"],
                           "url": "", "fuente": "politica", "dominio": "",
                           "etiqueta_falsa": 1 - int(etiqueta), "grupo_forzado": clave})
    return salida


def escribir_csv(path: Path, filas: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        escritor = csv.DictWriter(stream, fieldnames=COLUMNAS, extrasaction="ignore")
        escritor.writeheader()
        for fila in filas:
            escritor.writerow({**fila, "peso": f"{fila['peso']:.6f}"})


def conteos(lista: list[dict]) -> dict:
    salida = defaultdict(lambda: defaultdict(dict))
    for clave in sorted({(f["pliegue"], f["fuente"]) for f in lista}):
        sub = [f for f in lista if (f["pliegue"], f["fuente"]) == clave]
        for clase in (0, 1):
            s = [f for f in sub if f["etiqueta_falsa"] == clase]
            salida[clave[0]][clave[1]][("real", "falsa")[clase]] = {
                "fragmentos": len(s), "articulos": len({f["id_articulo"] for f in s}),
                "peso_total": round(sum(f["peso"] for f in s), 3),
                "tokens_mediana": float(np.median([f["tokens_bilstm"] for f in s])) if s else None}
    return json.loads(json.dumps(salida))


def construir_manifiesto(entrada, salida, tope, archivos, conteo_patrones, excluidas, cortos,
                         info_grupos, factor, retiradas, principales, satira, desarrollo) -> dict:
    por_patron = defaultdict(dict)
    for (nombre, fuente, clase), n in sorted(conteo_patrones.items()):
        por_patron[nombre][f"{fuente}/{('real', 'falsa')[clase]}"] = n
    grupos_multi_fuente = defaultdict(set)
    for f in desarrollo:
        grupos_multi_fuente[f["grupo"]].add(f["fuente"])
    return {
        "version": VERSION,
        "script": {"ruta": "datos_comunes/construir_comun.py",
                   "sha256": sha256_archivo(Path(__file__)),
                   "sha256_limpieza": sha256_archivo(Path(__file__).with_name("limpieza.py"))},
        "entrada": {"ruta": str(entrada.relative_to(ROOT)), "sha256": sha256_archivo(entrada)},
        "parametros": {"semilla": SEMILLA, "min_tokens": MIN_TOKENS, "tope_tokens": tope,
                       "max_fragmentos_por_articulo": MAX_FRAGMENTOS,
                       "fraccion_congelada": FRACCION_CONGELADA,
                       "tokenizador": "bilstm/entrenar_baseline.py:tokenize",
                       "factor_peso_polyglot": factor, "max_parejas_politica": MAX_PAREJAS_POLITICA},
        "etiqueta": {"columna": "etiqueta_falsa", "real": 0, "falsa": 1},
        "pliegues": {p: {"valida": f, "entrena": [x for x in FUENTES_PRINCIPALES if x != f]}
                     for p, f in PLIEGUES.items()},
        "dominios_satira": sorted(SATIRA), "dominios_redes": sorted(REDES),
        "patrones_limpieza": [{"nombre": n, "regex": p.pattern} for n, p, _ in PATRONES_PREVIOS + PATRONES] +
                             [{"nombre": "comillas_escapadas", "regex": "['\"]{2,} -> \""},
                              {"nombre": "parrafos_pegados", "regex": "minúscula{3}+Mayúscula | [.!?]+Mayúscula"}],
        "filas_cambiadas_por_patron": por_patron,
        "excluidas": dict(excluidas),
        "articulos_principales": len(principales), "articulos_satira_v1": len(satira),
        "articulos_menos_de_100_tokens": {f"{f}/{('real', 'falsa')[c]}": n for (f, c), n in sorted(cortos.items())},
        "grupos": {**info_grupos, "grupos_del_desarrollo_en_varias_fuentes":
                   sum(len(v) > 1 for v in grupos_multi_fuente.values())},
        "ablacion_retiradas_por_grupo_congelado": dict(retiradas),
        "archivos": {nombre: {"sha256": sha256_archivo(salida / nombre), "filas": len(lista)}
                     for nombre, lista in archivos.items()},
        "conteos": {nombre: conteos(lista) for nombre, lista in archivos.items()},
    }


def reporte(m: dict, ejemplos: dict, desarrollo: list[dict]) -> str:
    lineas = [f"# Conjunto común {m['version']}", "",
              "Generado por `datos_comunes/construir_comun.py`. Etiqueta `etiqueta_falsa` (1 = falsa).",
              f"Tope de tokens por fragmento: **{m['parametros']['tope_tokens']}**. "
              f"Factor de peso de Polyglot: {m['parametros']['factor_peso_polyglot']:.3f}.", "",
              "## Archivos", "", "| Archivo | Filas | SHA-256 |", "| --- | ---: | --- |"]
    for nombre, info in m["archivos"].items():
        lineas.append(f"| `{nombre}` | {info['filas']} | `{info['sha256'][:16]}…` |")
    lineas += ["", "## Conteos por partición, fuente y clase", "",
               "| Archivo | Pliegue | Fuente | Clase | Artículos | Fragmentos | Peso | Mediana tokens |",
               "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for archivo, por_pliegue in m["conteos"].items():
        for pliegue, por_fuente in por_pliegue.items():
            for fuente, por_clase in por_fuente.items():
                for clase, c in por_clase.items():
                    lineas.append(f"| {archivo.replace('.csv', '')} | {pliegue or '—'} | {fuente} | {clase} | "
                                  f"{c['articulos']} | {c['fragmentos']} | {c['peso_total']} | {c['tokens_mediana']} |")
    lineas += ["", "## Exclusiones", "", f"- Excluidas: `{json.dumps(m['excluidas'], ensure_ascii=False)}`",
               f"- Artículos con menos de 100 tokens (descartados): "
               f"`{json.dumps(m['articulos_menos_de_100_tokens'], ensure_ascii=False)}`",
               f"- Filas de ablación retiradas por compartir grupo con la prueba congelada: "
               f"`{json.dumps(m['ablacion_retiradas_por_grupo_congelado'])}`",
               f"- Grupos: `{json.dumps(m['grupos'])}`", "",
               "## Limpieza: filas cambiadas por patrón", "",
               "| Patrón | Fuente/clase: filas |", "| --- | --- |"]
    for nombre, por in m["filas_cambiadas_por_patron"].items():
        lineas.append(f"| `{nombre}` | " + ", ".join(f"{k}: {v}" for k, v in por.items()) + " |")
    lineas += ["", "## Ejemplos de limpieza (hasta 20 por patrón)", ""]
    for nombre, pares in ejemplos.items():
        lineas += [f"### `{nombre}`", ""]
        for antes, despues in pares:
            lineas.append(f"- **Antes:** {antes.replace('|', '¦')}  \n  **Después:** {despues.replace('|', '¦')}")
        lineas.append("")
    lineas += ["## Avisos", "",
               "- `*NUMBER*` es una marca del corpus v1 (sustituyó las cifras en ambas clases). Se quita porque "
               "identifica a la fuente y la extensión nunca la recibe; las cifras originales no se pueden recuperar.",
               "- En FakeDeS las 72 filas sin titular son todas falsas: el primer fragmento de las reales empieza "
               "con titular y el de esas falsas no. Es un atajo débil que no se puede corregir sin inventar titulares.",
               "- Polyglot: todas las reales son de elmundo.es. Aunque se quitaron sus pies fijos, el estilo del "
               "medio sigue presente; el pliegue F3 se informa, pero no decide solo.",
               "- Las filas de `ablacion_usmsc.csv` y `ablacion_politica.csv` no se fragmentan: son textos cortos "
               "(< 100 tokens) y entran tal cual, con peso 1 por fila.",
               "- `ablacion_satira.csv` lleva `fuente = v1`: el cargador la quita del entrenamiento del pliegue F1.",
               ""]
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--salida", type=Path, default=SALIDA)
    parser.add_argument("--tope", type=int, default=400)
    parser.add_argument("--sobrescribir", action="store_true")
    args = parser.parse_args()
    if args.salida.exists() and any(args.salida.iterdir()) and not args.sobrescribir:
        raise FileExistsError(f"{args.salida} ya tiene archivos; usa --sobrescribir")
    m = construir(args.entrada, args.salida, args.tope)
    print(json.dumps({k: m[k] for k in ("archivos", "excluidas", "articulos_menos_de_100_tokens",
                                         "grupos", "parametros")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
