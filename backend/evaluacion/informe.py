"""Informe en Markdown de una corrida (`RESUMEN.md`), con el mismo estilo que los de la prueba congelada."""

from collections.abc import Sequence

from backend.evaluacion.casos import CONCLUSIONS
from backend.evaluacion.metricas import NO_RESULT

SHORT = {"respaldada": "respaldada", "contradicha": "contradicha", "fuera_de_contexto": "fuera de ctx.", "evidencia_insuficiente": "insuficiente", NO_RESULT: "sin resultado"}


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f} %".replace(".", ",")


def _num(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}".replace(".", ",")


def _ci(interval) -> str:
    return f"[{_num(interval[0])}; {_num(interval[1])}]"


def report(results: Sequence[dict], summary: dict, *, title: str) -> str:
    n = summary["casos"]
    hits = summary["acierto"]
    lines = [
        f"# Corrida «{title}»",
        "",
        f"**{n} casos** · {summary['con_resultado']} con resultado · fallas: {summary['fallas'] or 'ninguna'}. "
        "Cifras orientativas: con tan pocos casos cada una lleva su intervalo.",
        "",
        "## Resultado",
        "",
        "| Medida | Valor |",
        "| --- | --- |",
        f"| Aciertos | {hits['aciertos']} de {hits['casos']} ({_pct(hits['aciertos'] / hits['casos'] if hits['casos'] else None)}; IC 95 % Wilson {_ci(hits['wilson95'])}) |",
        f"| **F1 macro** | **{_num(summary['f1_macro'])}** (IC 95 % bootstrap {_ci(summary['f1_macro_ic95'])}) |",
        f"| Error más grave: «respaldada» cuando era contradicha | {summary['error_grave']['respaldada_cuando_era_contradicha']} |",
        f"| Error grave inverso: «contradicha» cuando era respaldada | {summary['error_grave']['contradicha_cuando_era_respaldada']} |",
        f"| Casos que terminan en «evidencia insuficiente» | {_pct(summary['pct_insuficiente'])} |",
        f"| Afirmaciones por caso | {_num(summary['afirmaciones_por_caso'], 1)} |",
        f"| Duración por caso (media · p90) | {_num(summary['duracion']['media'], 1)} s · {_num(summary['duracion']['p90'], 1)} s |",
        "",
    ]
    missing = summary.get("evidencia_faltante") or {}
    if missing.get("busquedas") or missing.get("paginas"):
        lines.append(
            f"- **Evidencia congelada incompleta:** faltaron {missing.get('busquedas', 0)} búsquedas y {missing.get('paginas', 0)} páginas "
            "(el LLM generó consultas distintas a las de la grabación); el resultado no es del todo comparable."
        )
    for name, label in (("referencia_a", "A. Siempre «evidencia insuficiente»"), ("referencia_b", "B. LLM sin búsqueda")):
        ref = summary.get(name)
        if ref:
            lines.append(
                f"- **Referencia {label}:** F1 macro {_num(ref['f1_macro'])} {_ci(ref['f1_macro_ic95'])}; "
                f"el sistema {'supera' if ref['diferencia_sistema_menos_referencia'] > 0 else 'no supera'} "
                f"a esta referencia por {_num(ref['diferencia_sistema_menos_referencia'])} (IC 95 % de la diferencia {_ci(ref['diferencia_ic95'])})."
            )
    lines += ["", "## Matriz de confusión (filas: esperado; columnas: obtenido)", "", "| esperado \\ obtenido | " + " | ".join(SHORT.values()) + " |", "| --- |" + " ---: |" * len(SHORT)]
    for expected in CONCLUSIONS:
        row = summary["matriz"][expected]
        lines.append(f"| {SHORT[expected]} | " + " | ".join(str(row[column]) for column in SHORT) + " |")
    lines += ["", "## Por clase", "", "| Clase | Casos | Precisión | Recall | F1 |", "| --- | ---: | ---: | ---: | ---: |"]
    for conclusion, item in summary["por_clase"].items():
        lines.append(f"| {SHORT[conclusion]} | {item['casos']} | {_num(item['precision'])} | {_num(item['recall'])} | {_num(item['f1'])} |")
    citations = summary["citas"]
    lines += [
        "", "## Citas y enlaces", "",
        f"- Veredictos con evidencia que propuso el modelo: **{citations['propuestas']}**; de ellos, con la cita bien hecha: "
        f"{citations['validas_modelo']} ({_pct(citations['tasa_validas_modelo'])}). Lo que falla lo baja el backend a «insuficiente».",
        f"- Fuentes que llegan al usuario: **{citations['presentadas']}**. Comprobadas aparte contra la copia guardada: "
        f"{citations['verificadas'] if citations['verificadas'] is not None else '—'} ({_pct(citations['tasa_verificadas'])}); "
        f"**direcciones que no se descargaron: {citations['urls_inventadas'] if citations['urls_inventadas'] is not None else '—'}** (umbral: 0).",
        "", "## Caso por caso", "", "| Caso | Esperado | Obtenido | Resultado | Segundos | Nota |", "| --- | --- | --- | :---: | ---: | --- |",
    ]
    for r in results:
        ok = "✅" if r["predicho"] == r["esperado"] else "❌"
        note = (r.get("error") or {}).get("codigo") or ", ".join(sorted({c["motivo"] for c in r.get("afirmaciones", []) if c.get("motivo")}))
        lines.append(f"| {r['id']} | {SHORT.get(r['esperado'], r['esperado'])} | {SHORT.get(r['predicho'] or NO_RESULT)} | {ok} | {r['segundos']} | {note} |")
    return "\n".join(lines) + "\n"
