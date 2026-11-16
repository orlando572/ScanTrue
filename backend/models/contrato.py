"""Contratos de inferencia y combinación calibrada de los modelos de producción.

Cada modelo tiene un `contrato.json` (mismos campos para BiLSTM y mBERT, ver
docs/mejora_modelos/03_PLAN_MBERT.md §9) y los dos se combinan según
`datasets/combinacion_produccion/combinacion.json` (docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import exp, isfinite, log
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
BILSTM_CONTRACT = ROOT / "datasets/bilstm_produccion/modelo/contrato.json"
MBERT_CONTRACT = ROOT / "datasets/mbert_produccion/modelo/contrato.json"
COMBINATION_FILE = ROOT / "datasets/combinacion_produccion/combinacion.json"
LABELS = {"real": 0, "falsa": 1}
COMBINATION_METHOD = "media_ponderada_logits_calibrados"
PROBABILITY_EPSILON = 1e-7
# Modelos base admitidos en el hueco «mbert»: BETO y mBERT, con la revisión que fija
# mBERT/modelo.py (se copia aquí para no importar código de entrenamiento).
MODELOS_BASE_ADMITIDOS = {
    "beto": ("dccuchile/bert-base-spanish-wwm-cased", "c4d86612f51b4f46759c8390d1798c2febe71b93"),
    "mbert": ("google-bert/bert-base-multilingual-cased", "3f076fdb1ab68d5b2880cb87a0886f315b8146f8"),
}


class UnsupportedBaseModel(ValueError):
    """El contrato es de un transformer que no es BETO ni mBERT."""


def file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_sha_cache: dict[tuple[str, int, int], str] = {}


def cached_sha256(path: Path) -> str:
    """SHA-256 recordado mientras el archivo no cambie (BETO pesa ~440 MB)."""
    stat = Path(path).stat()
    key = (str(Path(path).resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _sha_cache:
        _sha_cache[key] = file_sha256(path)
    return _sha_cache[key]


def resolve(path: str, base: Path | None = None) -> Path:
    """Ruta de un archivo citado en un contrato.

    Sin `base`, relativa a la raíz del repositorio. Con `base` (la carpeta del contrato) se
    busca primero dentro de esa carpeta, probando la ruta y sus sufijos cada vez más cortos
    («datasets/…/final/todo_s42/modelo.pt» → «todo_s42/modelo.pt» → «modelo.pt»), y después
    en la raíz. Así sirve un contrato tal como lo deja el entrenamiento aunque su carpeta se
    haya movido; el SHA-256 del contrato confirma que es el archivo correcto.
    """
    root = ROOT.resolve()
    if base is not None:
        folder = Path(base).resolve()
        parts = [part for part in PurePosixPath(str(path).replace("\\", "/")).parts
                 if part not in ("", "/")]
        for start in range(len(parts)):
            candidate = folder.joinpath(*parts[start:]).resolve()
            if candidate.is_relative_to(folder) and candidate.exists():
                return candidate
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"La ruta del contrato sale del repositorio: {path}")
    return resolved


@dataclass(frozen=True)
class ModelContract:
    model: str
    version: str
    max_tokens: int
    temperature: float
    threshold: float
    checkpoint: Path
    checkpoint_sha256: str
    data: dict
    folder: Path | None = None
    provisional: bool = False

    @classmethod
    def load(cls, path: Path, model: str, allow_provisional: bool = False) -> "ModelContract":
        """Lee y valida un contrato. Sus rutas se buscan junto al contrato (ver `resolve`).

        `allow_provisional` solo sirve para listar modelos recién entrenados en el panel:
        un contrato con temperatura provisional nunca se carga para analizar.
        """
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("modelo") != model:
            raise ValueError(f"El contrato {path} no es del modelo {model}")
        if data.get("etiquetas") != LABELS:
            raise ValueError(f"El contrato {model} no usa 0 = real y 1 = falsa")
        provisional = bool(data.get("temperatura_provisional"))
        if provisional and not allow_provisional:
            raise ValueError(f"La temperatura del contrato {model} sigue siendo provisional")
        if model == "mbert":
            base = data.get("modelo_base") or {}
            admitted = MODELOS_BASE_ADMITIDOS.get(base.get("clave"))
            if admitted is None or (base.get("hub_id"), base.get("revision")) != admitted:
                raise UnsupportedBaseModel(
                    "Solo se admiten BETO y mBERT con la revisión fijada en mBERT/modelo.py"
                )
        temperature = float(data["temperatura"])
        threshold = float(data["umbral_falsa"])
        if not isfinite(temperature) or temperature <= 0:
            raise ValueError(f"Temperatura no válida en el contrato {model}")
        if not 0 < threshold < 1:
            raise ValueError(f"Umbral no válido en el contrato {model}")
        seeds = data.get("semillas") or []
        if len(seeds) != 1 or data.get("promediar_logits_semillas"):
            raise ValueError(f"El backend usa una sola semilla; el contrato {model} pide otra cosa")
        checkpoint = data["checkpoints"][f"s{seeds[0]}"]
        return cls(
            model=model,
            version=data["version"],
            max_tokens=int(data["max_tokens"]),
            temperature=temperature,
            threshold=threshold,
            checkpoint=resolve(checkpoint["ruta"], path.parent),
            checkpoint_sha256=checkpoint["sha256"],
            data=data,
            folder=path.parent,
            provisional=provisional,
        )

    def resolve(self, value: str) -> Path:
        """Otra ruta del contrato (p. ej. el tokenizador), buscada igual que el checkpoint."""
        return resolve(value, self.folder)

    def verify(self, weights: Path) -> None:
        if cached_sha256(weights) != self.checkpoint_sha256:
            raise ValueError(f"Los pesos de {self.model} no coinciden con su contrato: {weights}")


def logit(probability: float) -> float:
    p = min(1.0 - PROBABILITY_EPSILON, max(PROBABILITY_EPSILON, probability))
    return log(p / (1.0 - p))


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + exp(-value))
    z = exp(value)
    return z / (1.0 + z)


def calibrated_probability(logit_fake_minus_real: float, temperature: float) -> float:
    return sigmoid(logit_fake_minus_real / temperature)


@dataclass(frozen=True)
class Combination:
    """p = sigmoide(Σ w_i · logit(p_i)), con p_i ya calibrada por la temperatura de su contrato."""

    version: str
    weights: dict[str, float]
    temperatures: dict[str, float]
    model_versions: dict[str, str]
    threshold: float

    @classmethod
    def load(cls, path: Path = COMBINATION_FILE) -> "Combination":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("metodo") != COMBINATION_METHOD:
            raise ValueError(f"Método de combinación desconocido: {data.get('metodo')}")
        if data.get("regla_discrepancia") is not None:
            raise ValueError("La regla de discrepancia aún no está implementada en el backend")
        weights = {name: float(value) for name, value in data["pesos"].items()}
        if set(weights) != {"bilstm", "mbert"} or any(w < 0 for w in weights.values()) \
                or abs(sum(weights.values()) - 1.0) > 1e-6:
            raise ValueError("Los pesos de la combinación deben ser bilstm y mbert, ≥ 0 y sumar 1")
        return cls(
            version=data["version"],
            weights=weights,
            temperatures={name: float(value) for name, value in data["temperaturas"].items()},
            model_versions=dict(data["contratos"]),
            threshold=float(data["umbral_falsa"]),
        )

    def check(self, contract: ModelContract) -> None:
        """La combinación se calibró con estos contratos; si cambian, hay que recalibrar."""
        if self.model_versions.get(contract.model) != contract.version:
            raise ValueError(f"La combinación es de otra versión de {contract.model}")
        if abs(self.temperatures[contract.model] - contract.temperature) > 1e-9:
            raise ValueError(f"La temperatura de {contract.model} no coincide con la combinación")

    @classmethod
    def for_models(
        cls, contracts: dict[str, "ModelContract"], weights: dict[str, float],
        calibrated: "Combination | None" = None,
    ) -> "Combination":
        """Combinación de los modelos desplegados con los pesos del panel.

        Si coincide con la calibrada (mismos contratos, temperaturas y pesos), se usa esa tal
        cual, con su versión: así el resultado es idéntico al de antes del panel.
        """
        weights = {name: float(weights.get(name, 0.0)) for name in ("bilstm", "mbert")}
        if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1.0) > 1e-6:
            raise ValueError("Los pesos deben ser ≥ 0 y sumar 1")
        if not contracts:
            raise ValueError("No hay modelos que combinar")
        if calibrated is not None and set(contracts) == set(calibrated.model_versions) \
                and all(calibrated.model_versions[name] == c.version
                        and abs(calibrated.temperatures[name] - c.temperature) < 1e-9
                        for name, c in contracts.items()) \
                and all(abs(calibrated.weights[name] - weights[name]) < 1e-9 for name in weights):
            return calibrated
        names = " + ".join(contracts[name].version if name in contracts else "—"
                           for name in ("bilstm", "mbert"))
        return cls(
            version=f"panel: {names} @ {weights['bilstm']:.2f}/{weights['mbert']:.2f}",
            weights=weights,
            temperatures={name: c.temperature for name, c in contracts.items()},
            model_versions={name: c.version for name, c in contracts.items()},
            threshold=0.5,
        )

    def combine(self, probabilities: dict[str, float]) -> tuple[float, dict[str, float]]:
        """Combina las probabilidades calibradas disponibles. Si solo hay un modelo, usa la suya."""
        if not probabilities:
            raise ValueError("No hay probabilidades que combinar")
        if len(probabilities) == 1:
            (name, probability), = probabilities.items()
            return probability, {name: 1.0}
        weights = {name: self.weights[name] for name in probabilities}
        value = sum(weight * logit(probabilities[name]) for name, weight in weights.items())
        return sigmoid(value), weights
