"""Freeze leakage-aware record IDs for the first mBERT experiments.

Reads immutable Phase B artifacts. Creates a new output directory exclusively.
No source text is changed and no model is trained.
"""

import csv
import gzip
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "datasets" / "processed" / "phase_b_20261007_v1"
OUT = ROOT / "datasets" / "processed" / "phase_c_seed42_v1"
SEED = 42

with gzip.open(SOURCE / "normalized_all.jsonl.gz", "rt", encoding="utf-8") as handle:
    rows = list(map(json.loads, handle))
by_id = {row["id"]: row for row in rows}
assert len(by_id) == len(rows)


class DSU:
    def __init__(self, keys):
        self.parent = {key: key for key in keys}

    def find(self, key):
        parent = self.parent[key]
        if parent != key:
            self.parent[key] = self.find(parent)
        return self.parent[key]

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


dsu = DSU(by_id)


def union_key(key, row_id, first):
    if key in first:
        dsu.union(first[key], row_id)
    else:
        first[key] = row_id


exact_first, url_first, title_first = {}, {}, {}
for row in rows:
    union_key(row["hash_texto_exacto"], row["id"], exact_first)
    url = row["url_normalizada"]
    # A site home page is not an article identity.
    if url and urlsplit(url).path not in ("", "/"):
        union_key(url, row["id"], url_first)
    title_words = re.findall(r"\w+", row["titular"].casefold(), re.UNICODE)
    if len(title_words) >= 6:
        union_key(" ".join(title_words), row["id"], title_first)

with (SOURCE / "near_title_candidates.csv").open(encoding="utf-8", newline="") as handle:
    for pair in csv.DictReader(handle):
        dsu.union(pair["id_1"], pair["id_2"])

components = defaultdict(list)
for row in rows:
    components[dsu.find(row["id"])].append(row)
group_for = {row["id"]: root for root, group in components.items() for row in group}
assigned = {}
reasons = {}


def place(row, partition, reason):
    assert row["id"] not in assigned, row["id"]
    assigned[row["id"]] = partition
    reasons[row["id"]] = reason


def bad_article(row):
    flags = set(row["flags_revision"])
    if "missing_body" in flags:
        return "cuerpo_vacio"
    if "under_50_words" in flags:
        return "menos_50_palabras"
    if "possible_label_prefix" in flags:
        return "posible_marca_etiqueta_en_texto"
    if "non_latin_script_over_15pct" in flags:
        return "idioma_dudoso"
    return ""


def is_social_or_factcheck(row):
    source = row["fuente"].casefold()
    flags = set(row["flags_revision"])
    if "afpfactual_source_review" in flags:
        return "afpfactual_tipo_no_confirmado"
    if "social_url_review" in flags or source in {"facebook", "twitter", "instagram", "tiktok"}:
        return "plataforma_social"
    if any(token in source for token in ("maldita", "colombia check", "newtral", "chequeado")):
        return "fuente_de_verificacion"
    return ""


# Preserve original Spanish v1 training before its development split. Duplicate
# representatives are deterministic by original source row order.
for split, destination in (("train", "es_train"), ("development", "es_validation")):
    seen = set()
    subset = sorted((row for row in rows if row["dataset"] == "spanish_v1" and row["split_origen"] == split),
                    key=lambda row: int(row["fila_origen"]))
    for row in subset:
        issue = bad_article(row) or is_social_or_factcheck(row)
        group = group_for[row["id"]]
        if issue:
            place(row, "excluded", issue)
        elif group in seen:
            place(row, "excluded", "duplicado_dentro_del_split")
        elif split == "development" and any(
            assigned.get(member["id"]) == "es_train" for member in components[group]
        ):
            place(row, "excluded", "cruce_train_development_es")
        else:
            place(row, destination, "split_original_sin_cruce")
            seen.add(group)

# V2 remains reserved. We exclude overlap against *all* v1 rows, including
# rows filtered out from training, to preserve a conservative external test.
v1_groups = {group_for[row["id"]] for row in rows if row["dataset"] == "spanish_v1"}
seen = set()
for row in sorted((row for row in rows if row["dataset"] == "spanish_v2"),
                  key=lambda row: int(row["fila_origen"])):
    group = group_for[row["id"]]
    issue = bad_article(row) or is_social_or_factcheck(row)
    if group in v1_groups:
        place(row, "excluded", "cruce_v1_v2")
    elif issue:
        place(row, "es_test_quarantine", issue)
    elif group in seen:
        place(row, "excluded", "duplicado_dentro_del_test")
    else:
        place(row, "es_test_main", "v2_articulo_reservado")
        seen.add(group)

# Spanish Polyglot is an out-of-domain stress set, never training/validation.
# English Polyglot is held aside because source-language checks and source-label
# confounding have not been resolved.
seen = set()
for row in sorted((row for row in rows if row["dataset"] == "polyglot_v2"),
                  key=lambda row: (row["archivo_origen"], int(row["fila_origen"]))):
    if row["idioma_original"] != "es":
        place(row, "excluded", "polyglot_en_no_incluido")
    elif bad_article(row):
        place(row, "excluded", bad_article(row))
    elif group_for[row["id"]] in seen:
        place(row, "excluded", "duplicado_polyglot_es")
    else:
        place(row, "es_test_polyglot_stress", "prueba_estres_fuente_sesgada")
        seen.add(group_for[row["id"]])

# Pérez-Rosas is the external English test; opposite-label title pairs remain
# in the same test component, with no counterpart in ISOT partitions.
seen = set()
for row in sorted((row for row in rows if row["dataset"] == "perez_rosas_2018"),
                  key=lambda row: row["archivo_origen"]):
    if bad_article(row):
        place(row, "excluded", bad_article(row))
    elif group_for[row["id"]] in seen and len({m["etiqueta_binaria"] for m in components[group_for[row["id"]]]}) == 1:
        place(row, "excluded", "duplicado_perez_rosas")
    else:
        place(row, "en_test_perez_rosas", "prueba_inglesa_externa")
        seen.add(group_for[row["id"]])

# ISOT: retain one representative per exact/near-duplicate group, then split
# by connected component with fixed seed and approximate label stratification.
eligible = defaultdict(list)
for row in rows:
    if row["dataset"] == "isot":
        issue = bad_article(row)
        if issue:
            place(row, "excluded", issue)
        else:
            eligible[group_for[row["id"]]].append(row)

isot_groups = defaultdict(list)
for group, members in eligible.items():
    labels = {member["etiqueta_binaria"] for member in members}
    if len(labels) != 1:
        for member in members:
            place(member, "excluded", "grupo_isot_etiquetas_opuestas")
    else:
        isot_groups[next(iter(labels))].append((group, members))

rng = random.Random(SEED)
for label in (0, 1):
    groups = sorted(isot_groups[label], key=lambda item: item[0])
    rng.shuffle(groups)
    validation_groups = {group for group, _ in groups[:round(len(groups) * 0.2)]}
    for group, members in groups:
        members.sort(key=lambda row: int(row["fila_origen"]))
        representative = members[0]
        destination = "en_validation" if group in validation_groups else "en_train"
        place(representative, destination, "isot_grupo_estratificado_semilla_42")
        for duplicate in members[1:]:
            place(duplicate, "excluded", "duplicado_isot")

assert len(assigned) == len(rows)

# Validate that a connected group cannot span any two active partitions.
active = {"es_train", "es_validation", "es_test_main", "es_test_polyglot_stress",
          "en_train", "en_validation", "en_test_perez_rosas"}
for group, members in components.items():
    destinations = {assigned[row["id"]] for row in members} & active
    assert len(destinations) <= 1, (group, destinations)

# Reserved test quarantine is never an active training or test partition.
assert not ({"es_train", "es_validation", "en_train", "en_validation"} &
            {assigned[row["id"]] for row in rows if row["dataset"] == "spanish_v2"})

source_hash = hashlib.sha256((SOURCE / "normalized_all.jsonl.gz").read_bytes()).hexdigest()
manifest = {
    "phase": "C", "version": "seed42_v1", "seed": SEED,
    "source": str(SOURCE / "normalized_all.jsonl.gz"), "source_sha256": source_hash,
    "label_map": {"0": "REAL", "1": "FALSA"},
    "partitions": dict(sorted(Counter(assigned.values()).items())),
    "exclusion_reasons": dict(sorted(Counter(reasons[key] for key in assigned if assigned[key] == "excluded").items())),
    "quarantine_reasons": dict(sorted(Counter(reasons[key] for key in assigned if assigned[key] == "es_test_quarantine").items())),
    "by_partition_label": {
        partition: dict(sorted(Counter(str(by_id[key]["etiqueta_binaria"]) for key in assigned if assigned[key] == partition).items()))
        for partition in sorted(active)
    },
    "component_count": len(components),
    "leakage_check": "No exact-text, article-URL, normalized-title (>=6 words), or phase-B near-title component spans two active partitions.",
    "limitations": [
        "Semantic event overlap and cross-language paraphrases are not exhaustively detected.",
        "Spanish v2 social/article type has no authoritative per-row field; ambiguous rows are quarantined.",
        "Polyglot Spanish stress test has all real examples from one source; not a balanced independent estimate.",
        "ISOT source-label confounding remains; English validation is only for checkpoint selection.",
    ],
}

OUT.mkdir(parents=True, exist_ok=False)
with (OUT / "decisions.csv").open("x", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["id", "dataset", "source_split", "label", "partition", "reason", "component_id"])
    writer.writeheader()
    for row in rows:
        writer.writerow({"id": row["id"], "dataset": row["dataset"], "source_split": row["split_origen"],
                         "label": row["etiqueta_binaria"], "partition": assigned[row["id"]],
                         "reason": reasons[row["id"]], "component_id": group_for[row["id"]]})
for partition in sorted(active | {"es_test_quarantine"}):
    with (OUT / f"{partition}_ids.txt").open("x", encoding="utf-8") as handle:
        for row in rows:
            if assigned[row["id"]] == partition:
                handle.write(row["id"] + "\n")
with (OUT / "manifest.json").open("x", encoding="utf-8") as handle:
    json.dump(manifest, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps({"output": str(OUT), "partitions": manifest["partitions"],
                  "exclusion_reasons": manifest["exclusion_reasons"]}, ensure_ascii=False))
