"""Identity-normalization tests for the regional feasibility adapter."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import temper_quality_oracle as quality


_SCRIPT = Path(__file__).parents[1] / "evaluate_regional_layout.py"
_SPEC = importlib.util.spec_from_file_location("evaluate_regional_layout", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _evaluate(**overrides):
    values = {
        "baseline_pairs": ["A<->B", "C<->D"],
        "candidate_pairs": ["C<->D"],
        "baseline_drc": {"creepage": 10, "shorting_items": 2},
        "candidate_drc": {"creepage": 9, "shorting_items": 2},
        "baseline_body_overlaps": {},
        "candidate_body_overlaps": {},
        "baseline_pads": [("U1.1", 1.0, 1.0)],
        "baseline_endpoints": [(1.0, 1.0)],
        "candidate_pads": [("U1.1", 1.0, 1.0)],
        "candidate_endpoints": [(1.0, 1.0)],
        "endpoint_tolerance_mm": 0.01,
        "instrument_errors": [],
    }
    values.update(overrides)
    return quality.evaluate_regional_candidate_py(**values)


def test_binding_accepts_pareto_improvement():
    result = _evaluate()
    assert result["accepted"] is True
    assert result["removed_cross_domain_pairs"] == ["A<->B"]


def test_binding_rejects_metric_whack_a_mole():
    result = _evaluate(candidate_drc={"creepage": 9, "shorting_items": 3})
    assert result["accepted"] is False
    assert any("shorting_items" in reason for reason in result["reasons"])


def test_binding_rejects_routed_pad_endpoint_drift():
    result = _evaluate(candidate_pads=[("U1.1", 2.0, 1.0)])
    assert result["accepted"] is False
    assert result["routed_pad_endpoint_drift"] == ["U1.1"]


def test_binding_fails_closed_on_instrument_error():
    result = _evaluate(instrument_errors=["stale extension"])
    assert result["accepted"] is False
    assert "stale extension" in result["reasons"]


def test_pad_identity_survives_reference_renumber() -> None:
    before = _MODULE._stable_pad_label("R43.2(RTD_HW_FAULT)", {"R43": "rtd.pullup"})
    after = _MODULE._stable_pad_label("R44.2(RTD_HW_FAULT)", {"R44": "rtd.pullup"})
    assert before == after == "rtd.pullup.2(RTD_HW_FAULT)"


def test_pair_identity_canonicalizes_both_sides() -> None:
    identities = {"R4": "power.bleed", "U16": "safety.ovp"}
    assert _MODULE._stable_pair_label("R4.1(+170V)<->U16.5(+3V3)", identities) == (
        "power.bleed.1(+170V)<->safety.ovp.5(+3V3)"
    )
