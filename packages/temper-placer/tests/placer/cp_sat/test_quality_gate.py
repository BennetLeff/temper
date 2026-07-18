"""Tests for QualityGate three-state measurement discipline.

Covers the contract invariant that CLEAN, VIOLATIONS, and UNMEASURED are
distinct states. slop_linter is mocked so tests are fast and deterministic.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    QualityGate,
    Violation,
    ViolationType,
)

# =========================================================================
# Helpers
# =========================================================================


def _write_pcb() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False)
    tmp.write("(kicad_pcb)\n")
    tmp.close()
    return Path(tmp.name)


def _artifacts(*findings: dict) -> list[dict]:
    return list(findings)


# =========================================================================
# CLEAN
# =========================================================================


def test_clean_no_artifacts():
    """Zero-slop board → CLEAN."""
    pcb = _write_pcb()
    try:
        gate = QualityGate()
        with mock.patch(
            "temper_placer.router_v6.metrics.slop_linter.lint_all",
            return_value=[],
        ):
            result = gate.check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.CLEAN
    assert result.violations == ()
    assert result.error_message == ""


# =========================================================================
# VIOLATIONS
# =========================================================================


def test_violations_one_hairpin():
    """Single hairpin artifact → VIOLATIONS with SLOP type."""
    pcb = _write_pcb()
    hairpin = {
        "type": "hairpin",
        "net_name": "NET1",
        "position": (10.0, 20.0),
        "severity": 170.0,
        "description": "Hairpin turn (170.0 deg) at (10.00, 20.00) mm",
    }
    try:
        gate = QualityGate()
        with mock.patch(
            "temper_placer.router_v6.metrics.slop_linter.lint_all",
            return_value=[hairpin],
        ):
            result = gate.check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) == 1
    assert result.violations[0].type is ViolationType.SLOP
    assert result.violations[0].nets == ("NET1",)
    assert result.violations[0].severity == 1.0
    assert "hairpin" in result.violations[0].description


def test_violations_multiple_artifact_types():
    """Multiple artifact types produce multiple SLOP violations."""
    pcb = _write_pcb()
    artifacts = [
        {
            "type": "hairpin",
            "net_name": "NET1",
            "position": (10.0, 20.0),
            "severity": 170.0,
            "description": "Hairpin at (10.00, 20.00)",
        },
        {
            "type": "hairpin",
            "net_name": "NET2",
            "position": (30.0, 40.0),
            "severity": 165.0,
            "description": "Hairpin at (30.00, 40.00)",
        },
        {
            "type": "zigzag",
            "net_name": "NET3",
            "position": (50.0, 60.0),
            "severity": 3.0,
            "description": "Zigzag (3 turns) at (50.00, 60.00)",
        },
        {
            "type": "isolated_via",
            "net_name": "NET4",
            "position": (70.0, 80.0),
            "severity": 1.0,
            "description": "Isolated via at (70.00, 80.00)",
        },
        {
            "type": "single_net_detour",
            "net_name": "NET5",
            "position": (90.0, 100.0),
            "severity": 2.0,
            "description": "Detour ratio 2.00 at (90.00, 100.00)",
        },
    ]
    try:
        gate = QualityGate()
        with mock.patch(
            "temper_placer.router_v6.metrics.slop_linter.lint_all",
            return_value=artifacts,
        ):
            result = gate.check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) == 4  # hairpins grouped, others each
    types_found = {v.context.get("artifact_type") for v in result.violations}
    assert types_found == {"hairpin", "zigzag", "isolated_via", "single_net_detour"}


def test_violations_context_has_artifacts():
    """Each violation's context should carry the raw artifact list."""
    pcb = _write_pcb()
    hairpin = {
        "type": "hairpin",
        "net_name": "NET1",
        "position": (10.0, 20.0),
        "severity": 170.0,
        "description": "Hairpin turn",
    }
    try:
        gate = QualityGate()
        with mock.patch(
            "temper_placer.router_v6.metrics.slop_linter.lint_all",
            return_value=[hairpin],
        ):
            result = gate.check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.violations[0].context.get("artifact_type") == "hairpin"
    assert result.violations[0].context.get("artifacts") == [hairpin]


# =========================================================================
# UNMEASURED
# =========================================================================


def test_unmeasured_no_path():
    """Missing routed_pcb_path → UNMEASURED."""
    gate = QualityGate()
    result = gate.check(BoardState(routed_pcb_path=None))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_unmeasured_missing_file():
    """Non-existent file → UNMEASURED."""
    gate = QualityGate()
    result = gate.check(BoardState(routed_pcb_path=Path("/nonexistent/x.kicad_pcb")))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_unmeasured_linter_exception():
    """Linter exception → UNMEASURED (fail-closed)."""
    pcb = _write_pcb()
    try:
        gate = QualityGate()
        with mock.patch(
            "temper_placer.router_v6.metrics.slop_linter.lint_all",
            side_effect=RuntimeError("PCB parse error"),
        ):
            result = gate.check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.UNMEASURED
    assert "PCB parse error" in result.error_message


def test_unmeasured_import_error():
    """Import error → UNMEASURED (fail-closed)."""
    pcb = _write_pcb()
    try:
        gate = QualityGate()
        with mock.patch(
            "temper_placer.router_v6.metrics.slop_linter.lint_all",
            side_effect=ImportError("no module named slop_linter"),
        ):
            result = gate.check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.UNMEASURED
    assert "import" in result.error_message.lower() or "slop_linter" in result.error_message.lower()


# =========================================================================
# to_delta
# =========================================================================


def test_to_delta_slop_returns_keepout():
    """SLOP violation → KeepoutConstraint delta dict."""
    gate = QualityGate()
    v = Violation(
        type=ViolationType.SLOP,
        nets=("NET1",),
        severity=1.0,
        threshold=0.0,
        description="Slop: 1 hairpin artifact(s)",
        context={
            "artifact_type": "hairpin",
            "artifacts": [{
                "type": "hairpin",
                "net_name": "NET1",
                "position": (10.0, 20.0),
                "severity": 170.0,
                "description": "Hairpin at (10.00, 20.00) mm",
            }],
        },
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "KeepoutConstraint"
    assert delta.constraint.zone_name == "SLOP_hairpin_NET1"
    assert "NET1" in delta.constraint.id


def test_to_delta_via_count_returns_keepout():
    """VIA_COUNT violation maps to a KeepoutConstraint corrective delta.

    VERIFIED 2026-07-18: this test previously asserted the opposite
    (delta is None) -- contradicted by test_delta_mapper.py's own
    test_via_count_maps_to_keepout, which confirms DeltaMapper.map()
    has always produced a real KeepoutConstraint for VIA_COUNT.
    """
    gate = QualityGate()
    v = Violation(
        type=ViolationType.VIA_COUNT,
        severity=150.0,
        threshold=100.0,
        description="Signal via count 150 > 100",
        context={},
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "KeepoutConstraint"


def test_to_delta_octilinear_returns_none():
    """OCTILINEAR violation → None (informational only)."""
    gate = QualityGate()
    v = Violation(
        type=ViolationType.OCTILINEAR,
        severity=0.55,
        threshold=0.70,
        description="Diagonal fraction 0.55 < 0.70",
        context={},
    )
    assert gate.to_delta(v) is None


def test_to_delta_clearance_returns_none():
    """Unknown/unrelated violation type → None."""
    gate = QualityGate()
    v = Violation(
        type=ViolationType.CLEARANCE,
        severity=1.0,
        threshold=0.0,
        description="DRC clearance",
        context={},
    )
    assert gate.to_delta(v) is None


def test_to_delta_no_artifacts_in_context_falls_back_to_generic_keepout():
    """SLOP violation with an empty artifacts list still maps to a
    KeepoutConstraint using a fallback zone name.

    VERIFIED 2026-07-18: this test previously asserted the opposite
    (delta is None) -- contradicted by test_delta_mapper.py's own
    test_slop_fallback_zone_name, which confirms DeltaMapper.map()
    always produces a KeepoutConstraint for SLOP, falling back to a
    generic zone name when no specific artifact is available.
    """
    gate = QualityGate()
    v = Violation(
        type=ViolationType.SLOP,
        nets=(),
        severity=0.0,
        threshold=0.0,
        description="No artifacts",
        context={"artifact_type": "hairpin", "artifacts": []},
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "KeepoutConstraint"


# =========================================================================
# Contract conformance
# =========================================================================


def test_gate_contract_metadata():
    """QualityGate meets the Gate interface contract."""
    gate = QualityGate()
    assert gate.stage is GateStage.ROUTING
    assert gate.name == "quality"
    assert isinstance(gate, Gate)


def test_clean_and_unmeasured_are_distinct():
    """Empty violations means two different things depending on status."""
    clean = GateResult(GateStatus.CLEAN)
    unmeasured = GateResult(GateStatus.UNMEASURED, error_message="no board")
    assert clean.violations == unmeasured.violations == ()
    assert clean.status is not unmeasured.status


def test_violationtype_has_new_types():
    """OCTILINEAR and SLOP are in ViolationType enum."""
    assert ViolationType.OCTILINEAR.value == "octilinear"
    assert ViolationType.SLOP.value == "slop"
