"""Prepara corpus auditables para clasificación binaria de noticias en español.

Los originales nunca se modifican. Los archivos de salida se guardan bajo datasets/,
que permanece ignorado por Git. Uso: python bilstm/preparar_datasets.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit


COLUMNS = [
    "dataset", "archivo", "id_original", "titulo", "texto", "etiqueta",
    "etiqueta_original", "tipo_tarea", "idioma", "particion", "uso",
    "motivo", "url", "fecha", "fuente", "grupo_duplicados",
]
PRIORITY = {"prueba": 0, "validacion": 1, "entrenamiento": 2}
FALLEDESINFO_LABELS = {"T1": 0, "T2": 1, "T3": 1}


def clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


def key(value: object) -> str:
    return clean(value).casefold()


def content_key(row: dict) -> str:
    """Identidad conservadora: contenido completo normalizado, no solo titular."""
    return hashlib.sha256(key(row["texto"]).encode("utf-8")).hexdigest()


def record(dataset: str, path: Path, source_id: object, title: object,
           body: object, original_label: object, label: int | None,
           task: str, split: str, use: str, reason: str = "", url: object = "",
           date: object = "", source: object = "") -> dict:
    headline, text = clean(title), clean(body)
    if not text:
        text = headline
    elif headline and key(headline) not in key(text[: max(200, len(headline) + 25)]):
        text = headline + "\n" + text
    if use == "entrenamiento_binario" and (label not in (0, 1) or len(text) < 30):
        use, reason = "excluido", "sin etiqueta binaria o texto demasiado corto"
    return dict(dataset=dataset, archivo=str(path), id_original=clean(source_id),
                titulo=headline, texto=text, etiqueta=label,
                etiqueta_original=clean(original_label), tipo_tarea=task,
                idioma="es", particion=split, uso=use, motivo=reason,
                url=clean(url), fecha=clean(date), fuente=clean(source),
                grupo_duplicados=content_key({"texto": text}) if text else "")


def split_groups(rows: list[dict], seed: int = 42) -> None:
    """Asigna política 80/10/10, manteniendo titulares idénticos en un split."""
    if len(rows) < 10:
        raise ValueError("No hay suficientes noticias políticas para dividir")
    groups = [key(r["titulo"]) or r["grupo_duplicados"] for r in rows]
    indexes = list(range(len(rows)))
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=seed)
    train_idx, rest_idx = next(splitter.split(indexes, groups=groups))
    rest_groups = [groups[i] for i in rest_idx]
    splitter2 = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=seed)
    val_rel, test_rel = next(splitter2.split(rest_idx, groups=rest_groups))
    for i in train_idx:
        rows[int(i)]["particion"] = "entrenamiento"
    for i in val_rel:
        rows[int(rest_idx[int(i)])]["particion"] = "validacion"
    for i in test_rel:
        rows[int(rest_idx[int(i)])]["particion"] = "prueba"


def direct_rows(root: Path) -> list[dict]:
    result = []
    for filename, split in (("train.xlsx", "entrenamiento"),
                            ("development.xlsx", "validacion")):
        path = root / "servir_directamente/spanish_fake_news_corpus_v1" / filename
        df = pd.read_excel(path, dtype=str)
        for _, r in df.iterrows():
            label = {"fake": 0, "true": 1}.get(key(r["Category"]))
            result.append(record("spanish_fake_news_corpus_v1", path, r["Id"],
                                 r["Headline"], r["Text"], r["Category"], label,
                                 "noticia", split, "entrenamiento_binario",
                                 url=r["Link"], source=r["Source"]))
    path = root / "servir_directamente/spanish_political_fake_news/D57000_complete.csv"
    df = pd.read_csv(path, sep=";", dtype=str)
    political = []
    for i, r in df.iterrows():
        label = {"0": 0, "1": 1}.get(clean(r["Label"]))
        political.append(record("spanish_political_fake_news", path, i + 2,
                                r["Titulo"], r["Descripcion"], r["Label"], label,
                                "titulo_y_descripcion", "", "entrenamiento_binario",
                                date=r["Fecha"]))
    split_groups(political)
    result += political
    for filename, split in (("spanishFakeNews.csv", "entrenamiento"),
                            ("testSpanishFakeNews.csv", "prueba")):
        path = root / "servir_directamente/spanish_fake_and_real_news_acosta" / filename
        for i, r in pd.read_csv(path, dtype=str).iterrows():
            raw = key(r["clase"])
            result.append(record("spanish_fake_and_real_news_acosta", path, i + 2,
                                 "", r["texto"], raw, {"fake": 0, "real": 1}.get(raw),
                                 "noticia", split, "entrenamiento_binario"))
    return result


def nondirect_rows(root: Path) -> list[dict]:
    base = root / "no_directamente"
    result = []
    path = base / "fakedes_iberlef_2021/test.xlsx"
    for _, r in pd.read_excel(path, dtype=str).iterrows():
        # pandas/openpyxl convierte las celdas booleanas de este XLSX a True/False.
        label = {"0": 0, "1": 1, "false": 0, "true": 1}.get(key(r["CATEGORY"]))
        result.append(record("fakedes_iberlef_2021", path, r["ID"], r["HEADLINE"],
                             r["TEXT"], r["CATEGORY"], label, "noticia", "prueba",
                             "entrenamiento_binario", url=r["LINK"], source=r["SOURCE"]))

    path = base / "falledesinfo_es/FalleDesinfo_ES.xlsx"
    for _, r in pd.read_excel(path, dtype=str).iterrows():
        raw = clean(r["Tipo de noticia"])
        body = "\n".join((clean(r["Bajada"]), clean(r["Cuerpo"])))
        result.append(record("falledesinfo_es", path, r["ID noticia"],
                             r["Titular"], body, raw, FALLEDESINFO_LABELS.get(raw),
                             "noticia_sobre_fallecimiento", "prueba",
                             "entrenamiento_binario", date=r["Fecha"]))

    path = base / "usmsc/usmsc.csv"
    for i, r in pd.read_csv(path, sep=";", dtype=str).iterrows():
        raw = clean(r["label"])
        label = {"0": 0, "1": 1}.get(raw)
        result.append(record("usmsc", path, i + 2, "", r["text"], raw, label,
                             "noticia_o_satira", "sin_particion", "excluido",
                             "corpus derivado de fuentes presentes; sátira es clase separada"))

    # 80/20 son las particiones; Fake/Real contienen los mismos registros.
    for filename, split in (("80.xlsx", "entrenamiento"), ("20.xlsx", "prueba")):
        path = base / "polyglotfakefacts_v2" / filename
        df = pd.read_excel(path, dtype=str)
        df.columns = [c.strip().lower() for c in df.columns]
        df = df[df["language"].astype(str).str.strip().str.casefold() == "spanish"]
        for i, r in df.iterrows():
            raw = key(r["label"])
            result.append(record("polyglotfakefacts_v2", path, i + 2,
                                 r["news headline"], r["news original text"], raw,
                                 {"fake": 0, "real": 1}.get(raw), "noticia", split,
                                 "entrenamiento_binario", url=r["url"],
                                 date=r["news date"], source=r["domain"]))

    path = base / "spanish_fake_news_dataset_zenodo/esp_fake_news.csv"
    if path.exists():
        for i, r in pd.read_csv(path, dtype=str).iterrows():
            result.append(record("spanish_fake_news_dataset_zenodo", path, i + 2,
                                 r["Headlines"], r["Fake statement"], "fake_statement",
                                 None, "afirmacion", "sin_particion", "excluido",
                                 "solo afirmaciones falsas; no hay clase real comparable",
                                 url=r["Link source"], date=r["Date"], source=r["Media"]))

    for filename in ("FakeCovid_June2020.csv", "FakeCovid_July2020.csv"):
        path = base / "fakecovid" / filename
        df = pd.read_csv(path, dtype=str, low_memory=False)
        df = df[df["lang"].astype(str).str.strip().str.casefold().isin(("es", "spanish"))]
        for i, r in df.iterrows():
            result.append(record("fakecovid", path, i + 2,
                                 r["source_title"], r["content_text"], r["class"],
                                 None, "articulo_de_verificacion", "sin_particion",
                                 "excluido", "texto de verificación y veredicto de la afirmación no equivalen",
                                 url=r["article_source"], date=r["published_date"],
                                 source=r["verifiedby"]))

    path = base / "factores/dev.json"
    for i, r in enumerate(json.loads(path.read_text(encoding="utf-8")), 1):
        result.append(record("factores", path, f"{r['claim_id']}:{i}", "", r["claim"],
                             r["label"], None, "postura_afirmacion_evidencia",
                             "desarrollo", "excluido", "etiqueta depende de la evidencia"))

    path = base / "run_as/data.json"
    for source_id, r in json.loads(path.read_text(encoding="utf-8")).items():
        result.append(record("run_as", path, source_id, r["TITLE"], r["TEXT"],
                             r["VALUE"], None, "fiabilidad", "sin_particion",
                             "excluido", "fiabilidad no equivale a veracidad factual"))

    for path in sorted((base / "flares_2024").glob("*.json")):
        split = "prueba" if "test" in path.name else "entrenamiento"
        for line_number, line in enumerate(path.open(encoding="utf-8"), 1):
            if not line.strip():
                continue
            r = json.loads(line)
            raw = r.get("Reliability_Label", "")
            if not raw and r.get("Tags"):
                raw = ",".join(sorted({t.get("Reliability_Label", "") for t in r["Tags"]}))
            result.append(record("flares_2024", path, f"{r['Id']}:{line_number}",
                                 "", r["Text"], raw, None, "fiabilidad_fragmento",
                                 split, "excluido", "anotación de fragmentos, no etiqueta fake/real de noticia"))
    return result


def unify(direct: list[dict], nondirect: list[dict]) -> tuple[list[dict], dict]:
    candidates = [r for r in direct + nondirect if r["uso"] == "entrenamiento_binario"]
    grouped = defaultdict(list)
    for r in candidates:
        grouped[r["grupo_duplicados"]].append(r)
    selected = []
    report = Counter()
    for group in grouped.values():
        if len({r["etiqueta"] for r in group}) != 1:
            report["etiquetas_conflictivas"] += len(group)
            continue
        group.sort(key=lambda r: (PRIORITY[r["particion"]], r["dataset"], r["id_original"]))
        selected.append(group[0])
        report["duplicados_retirados"] += len(group) - 1
    # Una URL igual con textos distintos también puede filtrar el evento entre splits.
    by_url = defaultdict(list)
    for r in selected:
        if r["url"]:
            by_url[key(r["url"])].append(r)
    discard = set()
    for group in by_url.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (PRIORITY[r["particion"]], r["dataset"], r["id_original"]))
        if len({r["etiqueta"] for r in group}) != 1:
            discard.update(id(r) for r in group)
            report["urls_con_etiquetas_conflictivas"] += len(group)
        else:
            discard.update(id(r) for r in group[1:])
            report["urls_duplicadas_retiradas"] += len(group) - 1
    selected = [r for r in selected if id(r) not in discard]
    # El mismo titular puede tener un cuerpo o una URL levemente diferente.
    by_title = defaultdict(list)
    for r in selected:
        if len(key(r["titulo"])) >= 25:
            by_title[key(r["titulo"])].append(r)
    discard = set()
    for group in by_title.values():
        if len({r["particion"] for r in group}) < 2:
            continue
        if len({r["etiqueta"] for r in group}) > 1:
            discard.update(id(r) for r in group)
            report["titulares_con_etiquetas_conflictivas"] += len(group)
            continue
        keep_split = min((r["particion"] for r in group), key=PRIORITY.__getitem__)
        lower = [r for r in group if r["particion"] != keep_split]
        discard.update(id(r) for r in lower)
        report["titulares_cruzados_retirados"] += len(lower)
    selected = [r for r in selected if id(r) not in discard]
    return selected, dict(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "datasets")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or args.input / "estandarizados"
    direct = direct_rows(args.input)
    nondirect = nondirect_rows(args.input)
    unified, audit = unify(direct, nondirect)
    if not unified or {r["particion"] for r in unified} != {"entrenamiento", "validacion", "prueba"}:
        raise ValueError("Faltan datos o alguna partición final")
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in (("directos.csv", direct), ("no_directos.csv", nondirect),
                       ("unificado.csv", unified)):
        pd.DataFrame(rows, columns=COLUMNS).to_csv(output / name, index=False)
    audit.update({
        "directos": len(direct), "no_directos": len(nondirect), "unificado": len(unified),
        "por_dataset": dict(Counter(r["dataset"] for r in unified)),
        "por_particion_y_etiqueta": {f"{s}:{c}": n for (s, c), n in
                                    Counter((r["particion"], r["etiqueta"]) for r in unified).items()},
        "excluidos_no_directos": dict(Counter(r["dataset"] for r in nondirect if r["uso"] == "excluido")),
    })
    (output / "reporte.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
