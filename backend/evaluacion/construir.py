"""Herramientas del conjunto `verificacion_v1`: validar, congelar el manifiesto y revisar etiquetas.

    PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir validar [--completo] [--aprobados]
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir hoja-revision
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir aplicar-revision hoja.csv --revisor "Nombre"
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir congelar
    PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir comprobar

La **hoja de revisión** es lo que lee la persona que revisa (5.2: «una persona revisa cada etiqueta y la
equivalencia aplicada; las dudosas se descartan»): un CSV con el texto, la conclusión esperada, el veredicto
original del medio de verificación y cómo se tradujo. Ella escribe `aprobado` o `descartado` (y una nota) y
`aplicar-revision` lo anota en `casos.jsonl`. Nada de eso lo decide el código.
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

from backend.evaluacion.casos import DEFAULT_DIR, build_manifest, check_manifest, load_cases, save_cases, validate
from backend.evaluacion.equivalencias import as_json

SHEET_COLUMNS = (
    "id", "particion", "grupo_evento", "conclusion_esperada", "tipo_etiqueta", "veredicto_original", "equivalencia",
    "verificador", "url_verificacion", "fuentes", "fecha_hecho", "origen_url", "texto", "notas_del_armado", "decision", "nota",
)


def review_sheet(directory: Path, path: Path) -> int:
    cases = [c for c in load_cases(directory / "casos.jsonl") if c.revision.estado == "pendiente"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        for c in cases:
            writer.writerow({
                "id": c.id, "particion": c.particion, "grupo_evento": c.grupo_evento, "conclusion_esperada": c.conclusion_esperada,
                "tipo_etiqueta": c.etiqueta.tipo, "veredicto_original": c.etiqueta.veredicto_original or "", "equivalencia": c.etiqueta.equivalencia or "",
                "verificador": c.etiqueta.verificador or "", "url_verificacion": c.etiqueta.url_verificacion or "", "fuentes": " | ".join(c.etiqueta.fuentes),
                "fecha_hecho": c.fecha_hecho, "origen_url": c.origen_url or "", "texto": c.texto, "notas_del_armado": c.notas or "", "decision": "", "nota": "",
            })
    return len(cases)


def apply_review(directory: Path, path: Path, reviewer: str) -> tuple[int, int]:
    cases = {c.id: c for c in load_cases(directory / "casos.jsonl")}
    approved = discarded = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            decision = (row.get("decision") or "").strip().lower()
            if decision not in ("aprobado", "descartado") or row["id"] not in cases:
                continue
            review = cases[row["id"]].revision
            review.estado, review.revisor, review.fecha = decision, reviewer, date.today().isoformat()
            review.nota = (row.get("nota") or "").strip() or None
            approved += decision == "aprobado"
            discarded += decision == "descartado"
    save_cases(list(cases.values()), directory / "casos.jsonl")
    return approved, discarded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("orden", choices=("validar", "hoja-revision", "aplicar-revision", "congelar", "comprobar"))
    parser.add_argument("hoja", nargs="?", type=Path)
    parser.add_argument("--directorio", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--completo", action="store_true", help="Exige los 80 casos y su reparto.")
    parser.add_argument("--aprobados", action="store_true", help="Exige que todos estén aprobados por una persona.")
    parser.add_argument("--revisor")
    args = parser.parse_args(argv)
    directory = args.directorio

    if args.orden == "validar":
        cases = load_cases(directory / "casos.jsonl")
        problems = validate(cases, complete=args.completo, approved_only=args.aprobados)
        print(f"{len(cases)} casos; {len(problems)} problemas")
        for problem in problems:
            print(" -", problem)
        return 1 if problems else 0
    if args.orden == "hoja-revision":
        path = args.hoja or directory / "hoja_revision.csv"
        print(f"{review_sheet(directory, path)} casos pendientes de revisión en {path}")
        return 0
    if args.orden == "aplicar-revision":
        if not args.hoja or not args.revisor:
            raise SystemExit("Uso: aplicar-revision HOJA.csv --revisor «Nombre»")
        approved, discarded = apply_review(directory, args.hoja, args.revisor)
        print(f"{approved} aprobados y {discarded} descartados")
        return 0
    if args.orden == "congelar":
        problems = validate(load_cases(directory / "casos.jsonl"), complete=True, approved_only=True)
        if problems:
            raise SystemExit("No se congela un conjunto con problemas:\n- " + "\n- ".join(problems))
        (directory / "equivalencias.json").write_text(json.dumps(as_json(), ensure_ascii=False, indent=1), encoding="utf-8")
        manifest = build_manifest(directory)
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        print("Manifiesto congelado:", manifest["archivos"])
        return 0
    problems = check_manifest(directory)
    print("Manifiesto sin cambios." if not problems else "\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
