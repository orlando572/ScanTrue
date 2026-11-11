"""Create a compact review queue; no records are removed or relabeled."""

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path


OUT = Path(__file__).resolve().parent.parent / "datasets" / "processed" / "phase_b_20261007_v1"
with gzip.open(OUT / "normalized_all.jsonl.gz", "rt", encoding="utf-8") as handle:
    rows = list(map(json.loads, handle))
by_id = {row["id"]: row for row in rows}
groups = defaultdict(list)
for row in rows:
    if row["dataset"] == "spanish_v1":
        groups[row["hash_texto_exacto"]].append(row)

queue = []


def add(kind, row, pair_id="", note=""):
    queue.append({
        "motivo": kind, "id": row["id"], "id_pareja": pair_id,
        "dataset": row["dataset"], "split_origen": row["split_origen"],
        "etiqueta_binaria": row["etiqueta_binaria"], "titulo": row["titular"],
        "fuente": row["fuente"], "url": row["url_normalizada"],
        "nota": note,
    })


for group in groups.values():
    trains = [row for row in group if row["split_origen"] == "train"]
    developments = [row for row in group if row["split_origen"] == "development"]
    if trains and developments:
        for row in developments:
            add("texto_igual_train_development", row, trains[0]["id"],
                "Excluir o reasignar el registro de development antes de usar el split; decidir en fase C")

with (OUT / "near_title_candidates.csv").open(encoding="utf-8", newline="") as handle:
    for pair in csv.DictReader(handle):
        left, right = by_id[pair["id_1"]], by_id[pair["id_2"]]
        if {left["dataset"], right["dataset"]} == {"spanish_v1", "spanish_v2"}:
            test = left if left["dataset"] == "spanish_v2" else right
            train = right if test is left else left
            add("titular_similar_v1_v2", test, train["id"],
                "Probable mismo artículo; revisar cuerpo y URL, excluir de prueba o entrenamiento en fase C")
        elif pair["misma_etiqueta"] == "False":
            add("titular_similar_etiquetas_distintas", left, right["id"],
                "Revisar semántica y posible par intencional antes de agrupar")

for row in rows:
    if "non_latin_script_over_15pct" in row["flags_revision"]:
        add("idioma_declarado_en_es_dudoso", row,
            note="Texto con más del 15 % de letras fuera del alfabeto latino")
    if "afpfactual_source_review" in row["flags_revision"]:
        add("tipo_social_v2_sin_confirmar", row,
            note="La fuente AFPFactual no confirma por sí sola el tipo de texto")

with (OUT / "review_queue.csv").open("x", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(queue[0]))
    writer.writeheader()
    writer.writerows(queue)
print(json.dumps({"review_queue_rows": len(queue)}, ensure_ascii=False))
