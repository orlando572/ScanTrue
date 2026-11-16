"""Ejecutor de la evaluación: corre el sistema (y las referencias) sobre los casos de `verificacion_v1`.

Uso (desde la raíz, con el entorno de desarrollo y `llama-server` levantado):

    PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.correr \\
        --env backend/.env.desarrollo --particion ajuste --modo en_vivo --evidencia base \\
        --salida ajuste_en_vivo_1 --referencias

Cada caso se verifica con el mismo código que usa la API (`CaseVerifier`), pero **sin base de afirmaciones
anteriores** (cada caso se mide por sí solo) y **sin los medios de verificación** (D7) ni la página de origen del
texto. Los resultados se guardan caso por caso, así que una corrida interrumpida se retoma donde quedó.

La prueba final se abre **una sola vez** (5.1, regla 2): hace falta `umbrales.json` con la cifra mínima de F1
macro fijada antes, el manifiesto sin cambios y `--abrir-prueba-final`; la apertura queda registrada.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

from backend.core.config import EvidenceLimits, LlmSettings, SearchSettings
from backend.evaluacion.casos import DEFAULT_DIR, Case, check_manifest, load_cases, validate
from backend.evaluacion.evidencia import EvidenceStore, FrozenFetcher, FrozenSearch
from backend.evaluacion.informe import report
from backend.evaluacion.metricas import summarize
from backend.evaluacion.referencias import REFERENCE_B_VERSION, reference_a, reference_b
from backend.services.llm_client import LlmClient, LlmError
from backend.services.verification.case import PROMPT_VERSIONS, CaseVerifier
from backend.services.verification.fetch import PageFetcher
from backend.services.verification.search import SearchError, build_search_provider

# Medios de verificación que nunca sirven de evidencia al evaluar (D7); cada caso añade los suyos.
FACT_CHECKERS = (
    "maldita.es", "newtral.es", "chequeado.com", "colombiacheck.com", "factual.afp.com", "verifica.efe.com",
    "efe.com/verifica", "animalpolitico.com", "verificado.com.mx", "lasillavacia.com", "ecuadorchequea.com",
    "bolivialibre.org", "boliviaverifica.bo", "fastcheck.cl", "lupa.news", "aosfatos.org", "snopes.com",
    "politifact.com", "fullfact.org", "reuters.com/fact-check", "factcheck.org", "ojo-publico.com",
)
FINAL_OPENED = "prueba_final_abierta.json"


class MemoryRepository:
    """Lo mínimo que necesita `CaseVerifier`: el texto del caso y una base de afirmaciones siempre vacía."""

    def __init__(self, text: str) -> None:
        self.text = text

    def analysis_text(self, analysis_id):
        return self.text

    def find_verified_claims(self, claim_hash, normalized, threshold, limit=5):
        return []

    def save_verified_claim(self, **fields):
        return uuid4()


def _claim_records(verifier: CaseVerifier, outcome) -> list[dict]:
    sources = {source["id"]: source for source in outcome.sources}
    records = []
    for index, claim in enumerate(outcome.claims):
        trace = verifier.trace[index] if index < len(verifier.trace) else None
        records.append({
            "texto": claim["texto"],
            "veredicto": claim["veredicto"],
            "motivo": trace.motivo if trace else None,
            "consultas": trace.consultas if trace else [],
            "resultados": trace.resultados if trace else 0,
            "paginas": trace.paginas if trace else 0,
            "paginas_fallidas": trace.paginas_fallidas if trace else {},
            "pasajes": trace.pasajes if trace else 0,
            "incompleta": trace.incompleta if trace else False,
            "segundos": trace.segundos if trace else 0.0,
            "fuentes": [
                {"url": sources[i]["url"], "dominio": sources[i]["dominio"], "extracto": sources[i]["extracto"]}
                for i in claim["fuente_ids"] if i in sources
            ],
        })
    return records


def evaluate_case(
    case: Case, *, llm: LlmClient, search, fetcher, limits: EvidenceLimits, case_seconds: float,
    references: bool = False, clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Verifica un caso y devuelve su registro: conclusión, afirmaciones, fuentes, tiempos y fallas."""
    exclude = sorted({*FACT_CHECKERS, *(d.lower() for d in case.dominios_excluidos)})
    verifier = CaseVerifier(
        MemoryRepository(case.texto), llm, search, fetcher, limits=limits, case_seconds=case_seconds,
        exclude_domains=exclude, clock=clock,
    )
    record = {
        "id": case.id, "particion": case.particion, "esperado": case.conclusion_esperada, "predicho": None,
        "error": None, "segundos": None, "resumen": None, "afirmaciones": [], "extraccion": None,
        "version_prompts": PROMPT_VERSIONS,
    }
    started = clock()
    try:
        outcome = verifier.verify(uuid4())
        record.update(predicho=outcome.conclusion, resumen=outcome.summary, afirmaciones=_claim_records(verifier, outcome))
    except (LlmError, SearchError) as error:
        record["error"] = {"codigo": error.code, "mensaje": str(error)}
    except Exception as error:  # un caso que falla no debe tumbar la corrida entera
        record["error"] = {"codigo": "error_interno", "mensaje": f"{type(error).__name__}: {error}"}
    record["segundos"] = round(clock() - started, 2)
    extraction = verifier.extraction
    if extraction is not None:
        record["extraccion"] = {
            "afirmaciones": len(extraction.afirmaciones), "rechazadas": len(extraction.rechazadas),
            "ordenes_descartadas": extraction.ordenes_descartadas,
        }
    if references:
        record["referencia_a"] = {"predicho": reference_a(case.texto)}
        try:
            claims = [c.texto for c in extraction.afirmaciones] if extraction is not None else None
            result = reference_b(llm, case.texto, claims)
            record["referencia_b"] = {"predicho": result.conclusion, "afirmaciones": result.claims, "version": REFERENCE_B_VERSION}
        except LlmError as error:
            record["referencia_b"] = {"predicho": None, "error": {"codigo": error.code, "mensaje": str(error)}}
    return record


def read_results(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def run(
    cases: list[Case], output: Path, *, llm, search, fetcher, limits: EvidenceLimits, case_seconds: float,
    references: bool, store: EvidenceStore | None, log=print,
) -> dict:
    """Corre los casos, guardando cada resultado al terminarlo; retoma lo que ya estaba en `output`."""
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "resultados.jsonl"
    done = {r["id"]: r for r in read_results(results_path)}
    for case in cases:
        if case.id in done:
            continue
        record = evaluate_case(case, llm=llm, search=search, fetcher=fetcher, limits=limits, case_seconds=case_seconds, references=references)
        with results_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        done[case.id] = record
        mark = "ok" if record["predicho"] == record["esperado"] else "ERROR" if record["error"] else "x"
        log(f"{case.id} [{mark}] esperado={record['esperado']} predicho={record['predicho']} {record['segundos']} s")
    ordered = [done[case.id] for case in cases if case.id in done]
    summary = summarize(ordered, store)
    # Solo cuentan las faltas de esta ejecución (los casos retomados de una corrida anterior no se vuelven a pedir).
    summary["evidencia_faltante"] = {"busquedas": getattr(search, "misses", 0), "paginas": getattr(fetcher, "misses", 0)}
    (output / "resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (output / "RESUMEN.md").write_text(report(ordered, summary, title=output.name), encoding="utf-8")
    return summary


def open_final_test(directory: Path) -> None:
    """La prueba final se abre una sola vez y solo con la cifra mínima fijada antes (5.1 y 5.6)."""
    marker = directory / FINAL_OPENED
    if marker.exists():
        raise SystemExit(f"La prueba final ya se abrió ({marker.read_text(encoding='utf-8')[:120]}...). No se puede repetir.")
    thresholds = directory / "umbrales.json"
    if not thresholds.is_file() or "f1_macro_minimo" not in json.loads(thresholds.read_text(encoding="utf-8")):
        raise SystemExit("Falta umbrales.json con f1_macro_minimo: se fija después del ajuste y antes de abrir la prueba final.")
    problems = check_manifest(directory)
    if problems:
        raise SystemExit("El conjunto cambió desde que se congeló el manifiesto: " + "; ".join(problems))
    marker.write_text(json.dumps({"abierta_en": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


def build_services(env_file: Path, search_name: str):
    """LLM, buscador y descargador con las claves de un archivo de entorno (sin imprimirlas ni leer `backend/.env`)."""
    values = {k: v.strip().strip('"') for k, v in dotenv_values(env_file).items() if v}
    llm = LlmClient(LlmSettings(values["LLM_BASE_URL"].rstrip("/"), values.get("LLM_MODEL") or "qwen", values.get("LLM_API_KEY"), float(values.get("LLM_TIMEOUT") or 120)), retries=1)
    key = values[{"tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY"}[search_name]]
    search = build_search_provider(SearchSettings(search_name, key, 15.0))
    return llm, search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--directorio", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--env", type=Path, default=Path("backend/.env.desarrollo"))
    parser.add_argument("--buscador", choices=("tavily", "brave"), default="tavily")
    parser.add_argument("--particion", choices=("ajuste", "final", "todas"), default="ajuste")
    parser.add_argument("--modo", choices=("en_vivo", "congelado"), default="congelado")
    parser.add_argument("--evidencia", default="base", help="Nombre de la copia en evidencia_congelada/.")
    parser.add_argument("--salida", required=True, help="Nombre de la corrida (carpeta dentro de corridas/).")
    parser.add_argument("--referencias", action="store_true", help="También las referencias A y B.")
    parser.add_argument("--ids", help="Solo estos casos, separados por comas.")
    parser.add_argument("--limite", type=int, help="Solo los primeros N casos.")
    parser.add_argument("--solo-aprobados", action="store_true")
    parser.add_argument("--abrir-prueba-final", action="store_true")
    parser.add_argument("--segundos-por-caso", type=float, default=300.0)
    args = parser.parse_args(argv)

    cases = load_cases(args.directorio / "casos.jsonl")
    if args.solo_aprobados:
        cases = [c for c in cases if c.revision.estado == "aprobado"]
    if args.particion != "todas":
        cases = [c for c in cases if c.particion == args.particion]
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [c for c in cases if c.id in wanted]
    if args.limite:
        cases = cases[: args.limite]
    problems = validate(cases, approved_only=args.solo_aprobados)
    if problems:
        raise SystemExit("Casos con problemas:\n- " + "\n- ".join(problems))
    if any(c.particion == "final" for c in cases):
        if not args.abrir_prueba_final:
            raise SystemExit("Los casos de la prueba final solo se corren con --abrir-prueba-final (se abre una sola vez).")
        open_final_test(args.directorio)

    llm, live_search = build_services(args.env, args.buscador)
    store = EvidenceStore(args.directorio / "evidencia_congelada" / args.evidencia)
    limits = EvidenceLimits()
    live = args.modo == "en_vivo"
    search = FrozenSearch(store, args.modo, live_search if live else None)
    fetcher = FrozenFetcher(store, args.modo, PageFetcher(limits) if live else None)
    summary = run(
        cases, args.directorio / "corridas" / args.salida, llm=llm, search=search, fetcher=fetcher, limits=limits,
        case_seconds=args.segundos_por_caso, references=args.referencias, store=store,
    )
    print(f"F1 macro {summary['f1_macro']:.3f} · aciertos {summary['acierto']['aciertos']}/{summary['casos']} · fallas {summary['fallas']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
