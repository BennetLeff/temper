"""SLO definition schema and evaluation engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SloDefinition:
    metric: str
    type: str
    threshold: float
    window: int
    severity: str


def load_slo_definitions(path: str) -> dict[str, list[SloDefinition]]:
    with open(path) as f:
        data = yaml.safe_load(f)

    result: dict[str, list[SloDefinition]] = {}
    for stage_name, defs in data.get("stages", {}).items():
        result[stage_name] = []
        for d in defs:
            window = int(d["window"])
            if window <= 0:
                raise ValueError(
                    f"SLO {stage_name}/{d['metric']}: window must be > 0, got {window}"
                )
            result[stage_name].append(SloDefinition(
                metric=d["metric"],
                type=d["type"],
                threshold=float(d["threshold"]),
                window=window,
                severity=d["severity"],
            ))
    return result


def _compute_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    idx = 0.95 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def evaluate_slo(defn: SloDefinition, values: list[float]) -> tuple[bool, float]:
    if defn.type == "max":
        observed = max(values)
        violated = observed > defn.threshold
    elif defn.type == "min":
        observed = min(values)
        violated = observed < defn.threshold
    elif defn.type == "p95":
        observed = _compute_p95(values)
        violated = observed > defn.threshold
    elif defn.type == "mean":
        observed = sum(values) / len(values)
        violated = observed > defn.threshold
    else:
        raise ValueError(f"Unknown SLO type: {defn.type}")
    return violated, observed


def evaluate_all(
    definitions: dict[str, list[SloDefinition]],
    metrics_by_stage: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for stage, defs in definitions.items():
        records = metrics_by_stage.get(stage, [])
        for defn in defs:
            values = [
                r.get("metrics", {}).get(defn.metric)
                for r in records
                if r.get("metrics", {}).get(defn.metric) is not None
            ]
            windowed = values[-defn.window:] if len(values) >= defn.window else values

            status: str = "ok"
            violated = False
            observed = 0.0

            if len(values) < defn.window:
                status = "insufficient_data"
            elif len(windowed) >= 1:
                violated, observed = evaluate_slo(defn, windowed)
                status = "violated" if violated else "ok"

            results.append({
                "stage": stage,
                "metric": defn.metric,
                "type": defn.type,
                "threshold": defn.threshold,
                "observed": round(observed, 4),
                "window": defn.window,
                "severity": defn.severity,
                "violated": violated,
                "status": status,
                "data_points": len(values),
            })
    return results
