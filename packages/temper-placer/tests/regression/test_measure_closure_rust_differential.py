"""Differential test: measure-closure compute kernel in Rust
(``temper_design_bundle_python.compute_drc_clearance_pass_pct``) vs the
pinned Python oracle (Wave 4, Phase 4 — regression slice).

``temper_placer/regression/measure_closure.py`` is a thin harness over
``ClosureTest.run()`` whose only portable compute is the DRC-clearance-pass
formula (the 100.0 / 100 - 10*errors clamped / 0.0 three-branch rule). The
rest of the module — ClosureTest construction, the payload dict assembly,
the zero-results truth-gate raise, the JSON CLI — is marshalling over the
kept ``ClosureResult`` and stays in the delegation module (the "leave a small
portable kernel in place rather than half-migrating" rule does not apply —
the kernel IS portable, so it migrates). The pre-migration module is pinned
verbatim as the oracle (``_measure_closure_py_oracle.py``, commit
``0a29f15e3``).

The end-to-end differential stubs ``ClosureTest.run`` on BOTH arms (the
closure pipeline itself is out of scope) and compares the full payload dict
bit-exactly, including the drc-clearance-pass formula's integration with
``stages_exercised``.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
import temper_design_bundle_python as _tdb

import tests.regression._measure_closure_py_oracle as _oracle

# Rust symbol under test — must exist or this file fails to collect (RED).
COMPUTE_DRC_CLEARANCE_PASS_PCT = _tdb.compute_drc_clearance_pass_pct

from temper_placer.regression import measure_closure as _shim_mod  # noqa: E402
from temper_placer.regression.closure_test import ClosureTest  # noqa: E402


def _f(v):
    return None if v is None else float(v).hex()


def _canon_payload(p):
    return tuple(
        (k, _f(v)) if k in ("router_completion_pct", "drc_clearance_pass_pct", "wall_clock_seconds")
        else (k, v)
        for k, v in p.items()
    )


def _ref_pct(stages, errors):
    """Verbatim transcription of the oracle's drc_clearance_pass_pct
    three-branch formula (from _measure_closure_py_oracle.py)."""
    if stages >= 4 and errors == 0:
        return 100.0
    elif stages >= 4:
        return max(0.0, 100.0 - 10.0 * errors)
    else:
        return 0.0


def _stub_run(result_fields: dict):
    """Monkeypatch ClosureTest.run (both arms construct the same class)."""

    def fake_run(self, _observer=None):
        return SimpleNamespace(**result_fields)

    return fake_run


# ---------------------------------------------------------------------------
# R1a — differential
# ---------------------------------------------------------------------------


def test_differential_pct_random():
    rng = random.Random(0xC0FFEE)
    for _ in range(400):
        stages = rng.randint(0, 8)
        errors = rng.randint(-5, 60)
        assert COMPUTE_DRC_CLEARANCE_PASS_PCT(stages, errors) == _ref_pct(stages, errors)


def test_differential_pct_branch_boundaries():
    # stages < 4 always 0.0 regardless of errors
    for errors in (0, 1, 10, 50):
        assert COMPUTE_DRC_CLEARANCE_PASS_PCT(3, errors) == 0.0
        assert COMPUTE_DRC_CLEARANCE_PASS_PCT(0, errors) == 0.0
    # stages == 4: 100.0 at 0 errors, clamps at >= 10 errors
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(4, 0) == 100.0
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(4, 1) == 90.0
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(4, 10) == 0.0
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(4, 20) == 0.0
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(5, 3) == 70.0


def test_differential_end_to_end_payload(monkeypatch, tmp_path):
    """The full measure_closure() payload (payload dict assembly + the
    drc-clearance-pass formula) must match the oracle bit-exactly."""
    result = {
        "stages_exercised": 4,
        "drc_errors": 2,
        "drc_warnings": 3,
        "drc_measured": True,
        "router_completion_pct": 96.5,
        "wall_clock_seconds": 12.34,
        "benders_iterations": 4,
        "passed": False,
        "errors": ["x"],
        "summary": lambda: "=== Closure Test: b ===",
    }
    monkeypatch.setattr(ClosureTest, "run", _stub_run(result))
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    o_payload = _oracle.measure_closure(pcb, repo_root=tmp_path, strategy="template")
    s_payload = _shim_mod.measure_closure(pcb, repo_root=tmp_path, strategy="template")
    assert _canon_payload(s_payload) == _canon_payload(o_payload)
    assert s_payload["drc_clearance_pass_pct"] == 80.0
    assert s_payload["ghost_pads_injected"] == 0


def test_differential_end_to_end_degraded_stages_drc_measured(monkeypatch, tmp_path):
    """stages_exercised < 4 with DRC genuinely measured (e.g. earlier
    optional stages failed but DRC itself ran clean) still uses the
    formula's stages<4 branch (0.0) — both arms, unchanged from the
    pre-fix formula. This is a pre-existing quirk of the formula itself
    (out of scope for finding 14, which is about the (>=4, 0) ambiguity),
    kept here so the differential still covers a stages<4-with-drc_measured
    input.
    """
    result = {
        "stages_exercised": 3,
        "drc_errors": 0,
        "drc_warnings": 0,
        "drc_measured": True,
        "router_completion_pct": 90.0,
        "wall_clock_seconds": 1.0,
        "benders_iterations": 2,
        "passed": True,
        "errors": [],
        "summary": lambda: "s",
    }
    monkeypatch.setattr(ClosureTest, "run", _stub_run(result))
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    o_payload = _oracle.measure_closure(pcb, repo_root=tmp_path)
    s_payload = _shim_mod.measure_closure(pcb, repo_root=tmp_path)
    assert _canon_payload(s_payload) == _canon_payload(o_payload)
    assert s_payload["drc_clearance_pass_pct"] == 0.0


def test_differential_end_to_end_zero_results_raise(monkeypatch, tmp_path):
    """The zero-results truth-gate raises RuntimeError with an identical
    message in both arms."""
    result = {
        "stages_exercised": 1,
        "drc_errors": 0,
        "drc_warnings": 0,
        "drc_measured": False,
        "router_completion_pct": 0.0,
        "wall_clock_seconds": 0.5,
        "benders_iterations": 0,
        "passed": False,
        "errors": ["Placement not available: nope"],
        "summary": lambda: "s",
    }
    monkeypatch.setattr(ClosureTest, "run", _stub_run(result))
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    with pytest.raises(RuntimeError) as oe:
        _oracle.measure_closure(pcb, repo_root=tmp_path)
    with pytest.raises(RuntimeError) as se:
        _shim_mod.measure_closure(pcb, repo_root=tmp_path)
    assert str(se.value) == str(oe.value)
    assert "zero results" in str(se.value)


def test_differential_end_to_end_drc_not_measured_raise(monkeypatch, tmp_path):
    """Finding 14's motivating condition: DRC never ran (kicad-cli missing,
    crash, or timeout) but the pipeline otherwise produced real placement
    and routing results, so the zero-results gate does NOT fire and
    stages_exercised independently reaches >=4 via the four pre-DRC stages.
    Pre-fix, this scored a fabricated 100.0 — identical to a genuine clean
    DRC run — in both arms. Post-fix, the DRC truth-gate raises instead,
    in both arms, with an identical message."""
    result = {
        "stages_exercised": 4,
        "drc_errors": 0,
        "drc_warnings": 0,
        "drc_measured": False,
        "router_completion_pct": 96.5,
        "wall_clock_seconds": 12.34,
        "benders_iterations": 4,
        "passed": True,
        "errors": [],
        "warnings": ["kicad-cli not available; skipping DRC"],
        "summary": lambda: "s",
    }
    monkeypatch.setattr(ClosureTest, "run", _stub_run(result))
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    with pytest.raises(RuntimeError) as oe:
        _oracle.measure_closure(pcb, repo_root=tmp_path)
    with pytest.raises(RuntimeError) as se:
        _shim_mod.measure_closure(pcb, repo_root=tmp_path)
    assert str(se.value) == str(oe.value)
    assert "did not measure DRC clearance" in str(se.value)


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (>=3, honestly bounded)
# ---------------------------------------------------------------------------


def test_mr1_error_monotonicity():
    """For stages >= 4, increasing drc_errors cannot increase the pass pct
    (piecewise: 10 per error down to a 0 clamp)."""
    for stages in (4, 5, 7):
        prev = float("inf")
        for errors in range(0, 15):
            cur = COMPUTE_DRC_CLEARANCE_PASS_PCT(stages, errors)
            assert cur <= prev
            prev = cur


def test_mr2_branch_stability_below_stages_4():
    """For stages < 4 the result is independent of drc_errors entirely."""
    vals = {COMPUTE_DRC_CLEARANCE_PASS_PCT(2, e) for e in range(0, 30)}
    assert vals == {0.0}


def test_mr3_linear_step_in_errors():
    """In the linear regime (0 < errors <= 10, stages >= 4) each extra error
    drops the pct by exactly 10.0."""
    for stages in (4, 6):
        for errors in range(0, 10):
            a = COMPUTE_DRC_CLEARANCE_PASS_PCT(stages, errors)
            b = COMPUTE_DRC_CLEARANCE_PASS_PCT(stages, errors + 1)
            assert a - b == 10.0


# ---------------------------------------------------------------------------
# R1c — non-vacuous properties (>=5)
# ---------------------------------------------------------------------------


def test_prop1_full_pass():
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(4, 0) == 100.0
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(6, 0) == 100.0


def test_prop2_clamped_at_zero():
    for stages in (4, 5, 9):
        for errors in (10, 11, 50):
            assert COMPUTE_DRC_CLEARANCE_PASS_PCT(stages, errors) == 0.0


def test_prop3_never_negative():
    for stages in range(0, 10):
        for errors in range(0, 50):
            assert COMPUTE_DRC_CLEARANCE_PASS_PCT(stages, errors) >= 0.0


def test_prop4_never_above_100():
    """For non-negative error counts the formula never exceeds 100.0 (a
    negative count would produce >100 in BOTH arms — the oracle's
    max(0.0, 100 - 10*errors) has no upper clamp; that is the oracle's own
    behavior and is pinned, not "fixed")."""
    for stages in range(0, 10):
        for errors in range(0, 50):
            assert COMPUTE_DRC_CLEARANCE_PASS_PCT(stages, errors) <= 100.0


def test_prop5_empty_stages_zero():
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(0, 0) == 0.0
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(1, 0) == 0.0


def test_prop6_exactly_four_stages_enables_the_formula():
    """The stages>=4 boundary is inclusive."""
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(4, 1) == 90.0
    assert COMPUTE_DRC_CLEARANCE_PASS_PCT(3, 1) == 0.0
