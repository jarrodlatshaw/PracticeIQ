"""Transparent arithmetic for shared-patient edge-volume estimates."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Mapping


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a number") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return result


@dataclass(frozen=True)
class Scenarios:
    low: Decimal = Decimal("0.05")
    base: Decimal = Decimal("0.10")
    high: Decimal = Decimal("0.15")

    def __post_init__(self):
        rates = tuple(_decimal(v, "capture rate") for v in (self.low, self.base, self.high))
        if not (rates[0] <= rates[1] <= rates[2] <= 1):
            raise ValueError("rates must be ordered between 0 and 1")
        for name, value in zip(("low", "base", "high"), rates):
            object.__setattr__(self, name, value)


def opportunity(observed: object, captured: object, collections_per_patient: object | None,
                scenarios: Scenarios = Scenarios()) -> dict:
    observed = _decimal(observed, "observed")
    captured = _decimal(captured, "captured")
    if captured > observed:
        raise ValueError("captured flow cannot exceed observed flow")
    leakage = observed - captured
    collections = None if collections_per_patient is None else _decimal(collections_per_patient, "collections")
    incremental = {name: leakage * getattr(scenarios, name) for name in ("low", "base", "high")}
    return {"observed": observed, "captured": captured, "leakage": leakage,
            "incremental": incremental,
            "revenue": {name: None if collections is None else value * collections
                        for name, value in incremental.items()}}


def weighted_score(components: Mapping[str, float | None], weights: Mapping[str, float],
                   minimum_coverage: float = 0.7) -> dict:
    if set(components) != set(weights) or not weights:
        raise ValueError("components and weights must have the same nonempty keys")
    if not isfinite(minimum_coverage) or not 0 <= minimum_coverage <= 1:
        raise ValueError("invalid minimum coverage")
    if any(not isfinite(w) or w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("weights must be finite and nonnegative with positive total")
    if any(v is not None and (not isfinite(v) or not 0 <= v <= 100) for v in components.values()):
        raise ValueError("component scores must be between 0 and 100")
    available = sum(weights[k] for k, v in components.items() if v is not None)
    coverage = available / sum(weights.values())
    score = (sum(weights[k] * v for k, v in components.items() if v is not None) / available
             if available and coverage >= minimum_coverage else None)
    return {"score": score, "coverage": coverage, "components": dict(components)}
