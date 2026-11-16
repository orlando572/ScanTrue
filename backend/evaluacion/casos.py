"""Formato de los casos de `verificacion_v1`, su validación y el manifiesto (docs/llm/PLAN_INCREMENTO_2.md, 5.2).

Un caso es lo que recibiría la extensión: un texto de al menos 100 tokens y la conclusión que se espera.
Los casos viven en `datasets/verificacion_v1/casos.jsonl` (una línea por caso, fuera de Git). Este módulo
no decide ninguna etiqueta: solo comprueba que el conjunto cumple las reglas del plan antes de usarlo.
"""

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from bilstm.modelo import TOKEN_PATTERN

CONCLUSIONS = ("respaldada", "contradicha", "fuera_de_contexto", "evidencia_insuficiente")
PARTITIONS = ("ajuste", "final")
MIN_TOKENS = 100
CASES_PER_CONCLUSION = 20  # 80 casos en total (D15)
PER_PARTITION = 10  # por conclusión, en cada partición
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "datasets" / "verificacion_v1"

Conclusion = Literal["respaldada", "contradicha", "fuera_de_contexto", "evidencia_insuficiente"]


class Review(BaseModel):
    """Revisión humana de la etiqueta y de la equivalencia aplicada (5.2: las dudosas se descartan)."""

    model_config = ConfigDict(extra="forbid")

    estado: Literal["pendiente", "aprobado", "descartado"] = "pendiente"
    revisor: str | None = None
    fecha: str | None = None
    nota: str | None = None


class Label(BaseModel):
    """De dónde sale la conclusión esperada."""

    model_config = ConfigDict(extra="forbid")

    tipo: Literal["verificador", "fuentes_independientes"]
    # Si lo etiquetó un medio de verificación:
    verificador: str | None = None
    url_verificacion: str | None = None
    veredicto_original: str | None = None
    fecha_verificacion: str | None = None
    equivalencia: str | None = Field(default=None, description="Cómo se tradujo el veredicto original a la conclusión.")
    # Si lo confirman varias fuentes independientes (conclusión `respaldada`):
    fuentes: list[str] = Field(default_factory=list)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^vv1-\d{3}$")
    particion: Literal["ajuste", "final"]
    grupo_evento: str = Field(min_length=3, max_length=120, description="Los casos del mismo hecho van en la misma partición.")
    texto: str
    tipo_texto: Literal["original", "descripcion_verificador"] = Field(
        default="original",
        description="«original»: el texto tal como circuló. «descripcion_verificador»: lo que cuenta el medio de verificación "
        "sobre el contenido, escrito sin su veredicto (cuando el original no se puede recuperar o es muy corto). Se analizan por separado.",
    )
    conclusion_esperada: Conclusion
    fecha_hecho: str = Field(description="Fecha del hecho o del texto, AAAA-MM-DD.")
    origen_url: str | None = Field(default=None, description="Página de donde sale el texto; no puede servir de evidencia.")
    etiqueta: Label
    dominios_excluidos: list[str] = Field(
        default_factory=list, description="Medios de verificación usados para etiquetar y el origen del texto (D7)."
    )
    afirmaciones_centrales: list[str] = Field(default_factory=list)
    revision: Review = Field(default_factory=Review)
    notas: str | None = None


def domain_of(url: str | None) -> str:
    try:
        host = (urlsplit(url or "").hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return host.removeprefix("www.")


# Palabras del veredicto que no pueden aparecer en la descripción de un contenido (sería darle la respuesta al sistema).
VERDICT_WORDS = re.compile(
    r"\b(fals[oa]s?|bulos?|enga[ñn]os[oa]s?|desmient\w+|desmentid\w+|verificad\w+|estafas?|fake|inventad[oa]s?|sin pruebas|descontextualizad\w+)\b",
    re.IGNORECASE,
)


def token_count(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def load_cases(path: Path) -> list[Case]:
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                cases.append(Case.model_validate(json.loads(line)))
            except ValueError as error:
                raise ValueError(f"{path.name}, línea {number}: {error}") from error
    return cases


def save_cases(cases: list[Case], path: Path) -> None:
    path.write_text("".join(case.model_dump_json() + "\n" for case in cases), encoding="utf-8")


def validate(cases: list[Case], *, complete: bool = False, approved_only: bool = False) -> list[str]:
    """Problemas del conjunto, en texto. Con `complete=True` exige además los 80 casos y su reparto."""
    problems: list[str] = []
    ids = Counter(case.id for case in cases)
    problems += [f"{id_}: id repetido" for id_, n in ids.items() if n > 1]
    texts = Counter(" ".join(case.texto.split()).lower() for case in cases)
    problems += [f"texto repetido en {n} casos" for n in texts.values() if n > 1]

    for case in cases:
        tag = case.etiqueta
        where = case.id
        if token_count(case.texto) < MIN_TOKENS:
            problems.append(f"{where}: el texto tiene {token_count(case.texto)} tokens (mínimo {MIN_TOKENS})")
        try:
            date.fromisoformat(case.fecha_hecho)
        except ValueError:
            problems.append(f"{where}: fecha_hecho no es AAAA-MM-DD")
        if case.tipo_texto == "descripcion_verificador" and (leak := VERDICT_WORDS.search(case.texto)):
            problems.append(f"{where}: la descripción contiene palabras del veredicto («{leak.group(0)}»)")
        if approved_only and case.revision.estado != "aprobado":
            problems.append(f"{where}: la revisión está «{case.revision.estado}»")
        if case.conclusion_esperada == "respaldada":
            domains = {domain_of(url) for url in tag.fuentes}
            if tag.tipo != "fuentes_independientes" or len(tag.fuentes) < 2 or len(domains - {""}) < 2:
                problems.append(f"{where}: `respaldada` exige al menos 2 fuentes de dominios distintos")
        else:
            if tag.tipo != "verificador" or not (tag.verificador and tag.url_verificacion and tag.veredicto_original and tag.equivalencia):
                problems.append(f"{where}: la etiqueta de un medio de verificación necesita nombre, enlace, veredicto original y equivalencia")
            checker = domain_of(tag.url_verificacion)
            if checker and checker not in {d.lower() for d in case.dominios_excluidos}:
                problems.append(f"{where}: falta excluir el dominio del verificador ({checker}) de la evidencia")
        origin = domain_of(case.origen_url)
        if origin and origin not in {d.lower() for d in case.dominios_excluidos}:
            problems.append(f"{where}: falta excluir el dominio de origen ({origin}) de la evidencia")

    # Los casos del mismo hecho no se reparten entre ajuste y prueba final (sin fugas).
    partitions: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        partitions[case.grupo_evento].add(case.particion)
    problems += [f"grupo «{group}»: repartido entre ajuste y final" for group, parts in partitions.items() if len(parts) > 1]

    if complete:
        if len(cases) != CASES_PER_CONCLUSION * len(CONCLUSIONS):
            problems.append(f"hay {len(cases)} casos y se esperaban {CASES_PER_CONCLUSION * len(CONCLUSIONS)}")
        for conclusion in CONCLUSIONS:
            for partition in PARTITIONS:
                n = sum(1 for c in cases if c.conclusion_esperada == conclusion and c.particion == partition)
                if n != PER_PARTITION:
                    problems.append(f"{conclusion} en {partition}: {n} casos (se esperaban {PER_PARTITION})")
    return problems


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


MANIFEST_FILES = ("casos.jsonl", "equivalencias.json")


def build_manifest(directory: Path = DEFAULT_DIR) -> dict:
    """Huella de cada archivo del conjunto; se congela antes de correr nada (5.7, paso 1)."""
    cases = load_cases(directory / "casos.jsonl")
    return {
        "version": "verificacion_v1",
        "casos": len(cases),
        "por_particion": dict(Counter(c.particion for c in cases)),
        "por_conclusion": dict(Counter(c.conclusion_esperada for c in cases)),
        "archivos": {name: {"sha256": sha256_of(directory / name)} for name in MANIFEST_FILES if (directory / name).is_file()},
    }


def check_manifest(directory: Path = DEFAULT_DIR) -> list[str]:
    """Compara los archivos con `manifest.json`; cualquier cambio después de congelar queda a la vista."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    for name, info in manifest.get("archivos", {}).items():
        path = directory / name
        if not path.is_file():
            problems.append(f"{name}: falta")
        elif sha256_of(path) != info["sha256"]:
            problems.append(f"{name}: cambió desde que se congeló el manifiesto")
    return problems
