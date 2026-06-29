"""Tests for SLO evaluation engine in slo_evaluator.py."""

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slo_evaluator import (
    SloDefinition,
    evaluate_all,
    evaluate_slo,
    load_slo_definitions,
)


def _make_record(stage: str, metrics: dict[str, float], timestamp: str = "") -> dict:
    return {
        "board": "temper",
        "stage": stage,
        "metrics": metrics,
        "timestamp": timestamp or "2026-06-28T00:00:00+00:00",
    }


# --- Unit tests: evaluate_slo ---

def test_evaluate_slo_max_ok():
    defn = SloDefinition(metric="wall_time_ms", type="max", threshold=1000, window=3, severity="warn")
    violated, observed = evaluate_slo(defn, [100, 200, 300])
    assert violated is False
    assert observed == 300


def test_evaluate_slo_max_violated():
    defn = SloDefinition(metric="wall_time_ms", type="max", threshold=1000, window=3, severity="warn")
    violated, observed = evaluate_slo(defn, [100, 200, 1500])
    assert violated is True
    assert observed == 1500


def test_evaluate_slo_min_ok():
    defn = SloDefinition(metric="completion_pct", type="min", threshold=90.0, window=5, severity="block")
    violated, observed = evaluate_slo(defn, [95.0, 98.0, 92.0, 97.0, 99.0])
    assert violated is False
    assert observed == 92.0


def test_evaluate_slo_min_violated():
    defn = SloDefinition(metric="completion_pct", type="min", threshold=90.0, window=5, severity="block")
    violated, observed = evaluate_slo(defn, [95.0, 80.0, 92.0, 97.0, 99.0])
    assert violated is True
    assert observed == 80.0


def test_evaluate_slo_p95_ok():
    defn = SloDefinition(metric="wall_time_ms", type="p95", threshold=1000, window=4, severity="block")
    values = [100, 200, 300, 400]
    violated, observed = evaluate_slo(defn, values)
    assert violated is False
    assert observed == pytest.approx(385.0)


def test_evaluate_slo_p95_violated():
    defn = SloDefinition(metric="wall_time_ms", type="p95", threshold=500, window=5, severity="block")
    values = [100, 200, 300, 400, 2000]
    violated, observed = evaluate_slo(defn, values)
    assert violated is True
    assert observed == pytest.approx(1680.0)


def test_evaluate_slo_mean_ok():
    defn = SloDefinition(metric="latency", type="mean", threshold=500, window=3, severity="warn")
    violated, observed = evaluate_slo(defn, [100, 200, 300])
    assert violated is False
    assert observed == 200.0


def test_evaluate_slo_mean_violated():
    defn = SloDefinition(metric="latency", type="mean", threshold=500, window=3, severity="warn")
    violated, observed = evaluate_slo(defn, [800, 600, 700])
    assert violated is True
    assert observed == 700.0


def test_evaluate_slo_unknown_type():
    defn = SloDefinition(metric="foo", type="median", threshold=100, window=3, severity="warn")
    try:
        evaluate_slo(defn, [1, 2, 3])
        assert False, "Expected ValueError"
    except ValueError:
        pass


# --- Unit tests: load_slo_definitions ---

def test_load_slo_definitions(tmp_path):
    slo_file = tmp_path / "slo.yaml"
    slo_file.write_text("""slo_version: 1
stages:
  closure:
    - metric: wall_time_ms
      type: max
      threshold: 600000
      window: 5
      severity: warn
  routing:
    - metric: completion_pct
      type: min
      threshold: 95.0
      window: 5
      severity: block
""")
    definitions = load_slo_definitions(str(slo_file))

    assert "closure" in definitions
    assert "routing" in definitions
    assert len(definitions["closure"]) == 1
    assert definitions["closure"][0].metric == "wall_time_ms"
    assert definitions["closure"][0].type == "max"
    assert definitions["closure"][0].threshold == 600000
    assert definitions["closure"][0].window == 5
    assert definitions["closure"][0].severity == "warn"
    assert definitions["routing"][0].metric == "completion_pct"
    assert definitions["routing"][0].type == "min"
    assert definitions["routing"][0].threshold == 95.0


# --- Unit tests: evaluate_all ---

def test_evaluate_all_happy_path():
    definitions = {
        "closure": [SloDefinition(metric="wall_time_ms", type="max", threshold=1000, window=3, severity="warn")],
    }
    records = [
        _make_record("closure", {"wall_time_ms": 100}),
        _make_record("closure", {"wall_time_ms": 200}),
        _make_record("closure", {"wall_time_ms": 300}),
    ]
    results = evaluate_all(definitions, {"closure": records})
    assert len(results) == 1
    assert results[0]["violated"] is False
    assert results[0]["status"] == "ok"


def test_evaluate_all_block_violation():
    definitions = {
        "routing": [SloDefinition(metric="wall_time_ms", type="p95", threshold=500, window=5, severity="block")],
    }
    records = [
        _make_record("routing", {"wall_time_ms": v})
        for v in [100, 200, 300, 400, 600, 700, 800, 900, 1000]
    ]
    results = evaluate_all(definitions, {"routing": records})
    assert len(results) == 1
    assert results[0]["violated"] is True
    assert results[0]["status"] == "violated"
    assert results[0]["severity"] == "block"


def test_evaluate_all_warn_violation():
    definitions = {
        "closure": [SloDefinition(metric="wall_time_ms", type="max", threshold=500, window=3, severity="warn")],
    }
    records = [
        _make_record("closure", {"wall_time_ms": v})
        for v in [100, 200, 800]
    ]
    results = evaluate_all(definitions, {"closure": records})
    assert len(results) == 1
    assert results[0]["violated"] is True
    assert results[0]["status"] == "violated"
    assert results[0]["severity"] == "warn"


def test_evaluate_all_insufficient_data():
    definitions = {
        "closure": [SloDefinition(metric="wall_time_ms", type="max", threshold=500, window=5, severity="warn")],
    }
    records = [
        _make_record("closure", {"wall_time_ms": 100}),
        _make_record("closure", {"wall_time_ms": 200}),
    ]
    results = evaluate_all(definitions, {"closure": records})
    assert len(results) == 1
    assert results[0]["status"] == "insufficient_data"
    assert results[0]["violated"] is False
    assert results[0]["data_points"] == 2


def test_evaluate_all_stage_not_in_definitions():
    definitions: dict[str, list[SloDefinition]] = {}
    records = [
        _make_record("closure", {"wall_time_ms": 100}),
    ]
    results = evaluate_all(definitions, {"closure": records})
    assert results == []


def test_evaluate_all_metric_not_in_records():
    definitions = {
        "closure": [SloDefinition(metric="missing_metric", type="max", threshold=100, window=3, severity="warn")],
    }
    records = [
        _make_record("closure", {"wall_time_ms": 100}),
    ]
    results = evaluate_all(definitions, {"closure": records})
    assert len(results) == 1
    assert results[0]["status"] == "insufficient_data"
    assert results[0]["data_points"] == 0
