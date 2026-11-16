"""Métricas de la evaluación (docs/llm/PLAN_INCREMENTO_2.md, 5.5 y 5.6).

Con 40 casos por conjunto cada cifra va con el número de casos y su intervalo de incertidumbre (Wilson
para proporciones, bootstrap de casos para el F1 macro y para la diferencia con una referencia): son
resultados orientativos. Un caso sin resultado (falló el LLM, la búsqueda o se agotó el tiempo) cuenta
como acierto imposible: está en la matriz como `sin_resultado` y baja el recall de su clase.
"""

import math
import random
from collections import Counter
from collections.abc import Sequence

from backend.evaluacion.casos import CONCLUSIONS
from backend.evaluacion.evidencia import EvidenceStore
from backend.services.verification.judge import quote_is_literal
from backend.services.verification.prompts import one_line

NO_RESULT = "sin_resultado"
CITATION_REASONS = ("cita_no_literal", "pasaje_inexistente", "sin_pasajes_citados")
Pair = tuple[str, str | None]  # (esperado, predicho o None)


def confusion(pairs: Sequence[Pair]) -> dict[str, dict[str, int]]:
    matrix = {expected: {predicted: 0 for predicted in (*CONCLUSIONS, NO_RESULT)} for expected in CONCLUSIONS}
    for expected, predicted in pairs:
        matrix[expected][predicted if predicted in CONCLUSIONS else NO_RESULT] += 1
    return matrix


def per_class(pairs: Sequence[Pair]) -> dict[str, dict]:
    matrix = confusion(pairs)
    result = {}
    for conclusion in CONCLUSIONS:
        tp = matrix[conclusion][conclusion]
        fp = sum(matrix[other][conclusion] for other in CONCLUSIONS if other != conclusion)
        fn = sum(n for predicted, n in matrix[conclusion].items() if predicted != conclusion)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        result[conclusion] = {"casos": tp + fn, "precision": precision, "recall": recall, "f1": f1}
    return result


def macro_f1(pairs: Sequence[Pair]) -> float:
    classes = per_class(pairs)
    return sum(item["f1"] for item in classes.values()) / len(CONCLUSIONS)


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def bootstrap_macro_f1(pairs: Sequence[Pair], resamples: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    values = [macro_f1([rng.choice(pairs) for _ in pairs]) for _ in range(resamples)] if pairs else [0.0]
    return (_percentile(values, 0.025), _percentile(values, 0.975))


def bootstrap_difference(
    system: Sequence[Pair], reference: Sequence[Pair], resamples: int = 2000, seed: int = 0
) -> tuple[float, float]:
    """IC 95 % de F1(sistema) − F1(referencia), remuestreando los mismos casos en ambos."""
    if not system:
        return (0.0, 0.0)
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        indexes = [rng.randrange(len(system)) for _ in system]
        values.append(macro_f1([system[i] for i in indexes]) - macro_f1([reference[i] for i in indexes]))
    return (_percentile(values, 0.025), _percentile(values, 0.975))


def _claims(result: dict) -> list[dict]:
    return result.get("afirmaciones") or []


def citation_stats(results: Sequence[dict], store: EvidenceStore | None = None) -> dict:
    """Citas y enlaces del sistema.

    - `propuestas`: veredictos con evidencia que propuso el modelo (apoyada, contradicha o fuera de contexto).
    - `validas_modelo`: de esas, las que citaron bien (pasaje que existe y frase literal); lo que falla aquí
      el backend lo baja a `insuficiente` (por eso lo presentado siempre cita bien).
    - `presentadas`: fuentes que llegan al usuario. Con la evidencia guardada se vuelven a comprobar por
      separado: `verificadas` (la página está en la copia y la cita aparece en ella) y `urls_inventadas`
      (la dirección no está entre las páginas que se descargaron).
    """
    proposals = valid_model = presented = verified = invented = 0
    for result in results:
        for claim in _claims(result):
            reason = claim.get("motivo")
            accepted = claim["veredicto"] != "insuficiente"
            if accepted or reason in (*CITATION_REASONS, "apoyo_incompleto"):
                proposals += 1
                valid_model += accepted or reason == "apoyo_incompleto"
            for source in claim.get("fuentes") or []:
                presented += 1
                if store is None:
                    continue
                text = store.page_text(source["url"])
                if text is None:
                    invented += 1
                elif quote_is_literal(source.get("extracto", ""), one_line(text)):
                    verified += 1
    return {
        "propuestas": proposals,
        "validas_modelo": valid_model,
        "tasa_validas_modelo": valid_model / proposals if proposals else None,
        "presentadas": presented,
        "verificadas": verified if store is not None else None,
        "urls_inventadas": invented if store is not None else None,
        "tasa_verificadas": verified / presented if store is not None and presented else None,
    }


def _pairs(results: Sequence[dict], key: str = "predicho") -> list[Pair]:
    return [(r["esperado"], r.get(key)) for r in results]


def summarize(results: Sequence[dict], store: EvidenceStore | None = None) -> dict:
    """Todo lo que pide 5.5 para un conjunto de casos ya ejecutado."""
    pairs = _pairs(results)
    hits = sum(1 for expected, predicted in pairs if expected == predicted)
    classes = per_class(pairs)
    matrix = confusion(pairs)
    durations = [r["segundos"] for r in results if r.get("segundos") is not None]
    answered = [r for r in results if r.get("predicho") in CONCLUSIONS]
    reference_results = {name: [(r["esperado"], (r.get(name) or {}).get("predicho")) for r in results] for name in ("referencia_a", "referencia_b")}
    summary = {
        "casos": len(results),
        "con_resultado": len(answered),
        "fallas": dict(Counter((r.get("error") or {}).get("codigo", "?") for r in results if r.get("error"))),
        "acierto": {"aciertos": hits, "casos": len(results), "wilson95": wilson(hits, len(results))},
        "f1_macro": macro_f1(pairs),
        "f1_macro_ic95": bootstrap_macro_f1(pairs),
        "por_clase": classes,
        "matriz": matrix,
        "error_grave": {
            "respaldada_cuando_era_contradicha": matrix["contradicha"]["respaldada"],
            "contradicha_cuando_era_respaldada": matrix["respaldada"]["contradicha"],
        },
        "pct_insuficiente": (sum(1 for r in answered if r["predicho"] == "evidencia_insuficiente") / len(answered)) if answered else None,
        "afirmaciones_por_caso": (sum(len(_claims(r)) for r in answered) / len(answered)) if answered else None,
        "duracion": {
            "media": sum(durations) / len(durations) if durations else None,
            "p90": _percentile(durations, 0.9) if durations else None,
        },
        "citas": citation_stats(results, store),
    }
    for name, ref_pairs in reference_results.items():
        if any(predicted is not None for _, predicted in ref_pairs):
            summary[name] = {
                "f1_macro": macro_f1(ref_pairs),
                "f1_macro_ic95": bootstrap_macro_f1(ref_pairs),
                "diferencia_sistema_menos_referencia": macro_f1(pairs) - macro_f1(ref_pairs),
                "diferencia_ic95": bootstrap_difference(pairs, ref_pairs),
            }
    return summary
