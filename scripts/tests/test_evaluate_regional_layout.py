from __future__ import annotations

import temper_quality_oracle as quality


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
