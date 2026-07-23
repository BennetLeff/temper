"""Tests for IECCreepageGate and PhysicsGate three-state measurement discipline.

Covers the contract invariant that CLEAN, VIOLATIONS, and UNMEASURED are
distinct states.  kicad-cli and PCB-parsing are mocked so the tests are
fast and deterministic.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    IECCreepageGate,
    PhysicsGate,
    Violation,
    ViolationType,
)

# =========================================================================
# Helpers
# =========================================================================


def _write_pcb(name: str = "test") -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", prefix=name, mode="w", delete=False)  # noqa: SIM115
    tmp.write("(kicad_pcb)\n")
    tmp.close()
    return Path(tmp.name)


def _fake_run_factory(
    returncode: int = 0,
    payload: dict | None = None,
    stderr: str = "",
):
    """Build a ``subprocess.run`` replacement for ``IECCreepageGate``."""

    def fake_run(cmd, **kwargs):  # noqa: ARG001
        if payload is not None:
            out_idx = cmd.index("--output") + 1
            Path(cmd[out_idx]).write_text(json.dumps(payload))
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    return fake_run


def _make_drc_payload(
    violations: list[dict] | None = None,
) -> dict:
    return {"violations": violations or []}


def _clearance_violation(
    severity: str = "error",
    items: list[dict] | None = None,
    description: str = "Clearance violation",
) -> dict:
    return {
        "type": "clearance",
        "severity": severity,
        "description": description,
        "items": items or [],
    }


# =========================================================================
# IECCreepageGate — UNMEASURED
# =========================================================================


def test_creepage_unmeasured_no_path():
    result = IECCreepageGate().check(BoardState(routed_pcb_path=None))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_creepage_unmeasured_missing_file():
    result = IECCreepageGate().check(BoardState(routed_pcb_path=Path("/nonexistent/x.kicad_pcb")))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_creepage_unmeasured_kicad_fails(monkeypatch):
    pcb = _write_pcb("creepage_fail")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run_factory(returncode=3, payload=None, stderr="board parse error"),
    )
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.UNMEASURED
    assert "creepage DRC failed" in result.error_message


# =========================================================================
# IECCreepageGate — CLEAN
# =========================================================================


def test_creepage_clean_no_clearance_violations(monkeypatch):
    pcb = _write_pcb("creepage_clean")
    payload = {
        "violations": [
            {
                "type": "unconnected_items",
                "severity": "error",
                "description": "not a clearance",
            },
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.CLEAN
    assert result.violations == ()


def test_creepage_clean_lv_to_lv_clearance_only(monkeypatch):
    """Clearance violation between LV nets only → not a creepage violation."""
    pcb = _write_pcb("creepage_lv_only")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [GATE_H] on F.Cu"},
                    {"description": "Track [GND] on F.Cu"},
                ],
                description="Clearance violation: GATE_H to GND",
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.CLEAN
    assert result.violations == ()


# =========================================================================
# IECCreepageGate — VIOLATIONS
# =========================================================================


def test_creepage_violation_hv_to_lv(monkeypatch):
    """Clearance violation DC_BUS+ → GATE_H is HV↔LV creepage."""
    pcb = _write_pcb("creepage_hv_lv")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [DC_BUS+] on F.Cu"},
                    {"description": "Track [GATE_H] on F.Cu"},
                ],
                description="Clearance: DC_BUS+ to GATE_H, actual 3.0mm",
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.type is ViolationType.CREEPAGE
    assert v.threshold == 6.0
    assert "DC_BUS+" in v.nets


def test_creepage_violation_ac_mains_to_lv(monkeypatch):
    """Clearance violation AC_L → GND is AC↔LV creepage."""
    pcb = _write_pcb("creepage_ac_lv")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [AC_L] on F.Cu"},
                    {"description": "Track [GND] on F.Cu"},
                ],
                description="Clearance: AC_L to GND, actual 4.5mm",
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert "AC_L" in result.violations[0].nets


def test_creepage_multiple_violations(monkeypatch):
    """Multiple HV↔LV crossing clearance violations → all reported."""
    pcb = _write_pcb("creepage_multi")
    payload = {
        "violations": [
            _clearance_violation(
                items=[
                    {"description": "Track [DC_BUS+] on F.Cu"},
                    {"description": "Track [GATE_H] on F.Cu"},
                ],
            ),
            _clearance_violation(
                items=[
                    {"description": "Track [SW_NODE] on F.Cu"},
                    {"description": "Track [+5V] on F.Cu"},
                ],
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) == 2


def test_creepage_warning_ignored(monkeypatch):
    """Warnings are not treated as violations."""
    pcb = _write_pcb("creepage_warn")
    payload = {
        "violations": [
            _clearance_violation(
                severity="warning",
                items=[
                    {"description": "Track [DC_BUS+] on F.Cu"},
                    {"description": "Track [GND] on F.Cu"},
                ],
            ),
        ],
    }
    monkeypatch.setattr("subprocess.run", _fake_run_factory(0, payload))
    monkeypatch.setattr(
        "temper_placer.validation._drc_api.is_kicad_cli_available",
        lambda: True,
    )
    try:
        result = IECCreepageGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.CLEAN


# =========================================================================
# IECCreepageGate — metadata
# =========================================================================


def test_creepage_gate_contract_metadata():
    gate = IECCreepageGate()
    assert gate.stage is GateStage.ROUTING
    assert gate.name == "iec_creepage"
    assert isinstance(gate, Gate)


def test_creepage_gate_to_delta():
    gate = IECCreepageGate()
    v = Violation(
        type=ViolationType.CREEPAGE,
        nets=("DC_BUS+", "GATE_H"),
        threshold=6.0,
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "SeparatedConstraint"


# =========================================================================
# PhysicsGate — UNMEASURED
# =========================================================================


def test_physics_unmeasured_no_path():
    result = PhysicsGate().check(BoardState(routed_pcb_path=None))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_physics_unmeasured_missing_file():
    result = PhysicsGate().check(BoardState(routed_pcb_path=Path("/nonexistent/x.kicad_pcb")))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


# =========================================================================
# PhysicsGate — metadata
# =========================================================================


def test_physics_gate_contract_metadata():
    gate = PhysicsGate()
    assert gate.stage is GateStage.ROUTING
    assert gate.name == "physics"
    assert isinstance(gate, Gate)


# =========================================================================
# PhysicsGate — to_delta
# =========================================================================


def test_physics_to_delta_loop_inductance():
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.LOOP_INDUCTANCE,
        components=("Q1", "Q2", "C_BUS1", "C_BUS2"),
        nets=("DC_BUS+", "SW_NODE", "DC_BUS-"),
        severity=2500.0,
        threshold=2000.0,
        description="Commutation loop too large",
        context={"loop": "commutation", "max_area_mm2": 2000.0},
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "LoopAreaConstraint"


def test_physics_to_delta_thermal():
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.THERMAL,
        components=("Q1", "Q2"),
        severity=100.0,
        threshold=200.0,
        description="Insufficient thermal pour",
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "SeparatedConstraint"


def test_physics_to_delta_creepage():
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.CREEPAGE,
        nets=("DC_BUS+", "GATE_H"),
        severity=4.0,
        threshold=6.0,
        description="Creepage too small",
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "SeparatedConstraint"


def test_physics_to_delta_via_count_returns_keepout():
    """VIA_COUNT violations map to a KeepoutConstraint corrective delta.

    VERIFIED 2026-07-18: this test previously asserted the opposite
    (delta is None) -- contradicted by test_delta_mapper.py's own
    test_via_count_maps_to_keepout, which confirms DeltaMapper.map()
    (the function PhysicsGate.to_delta() delegates to via the Gate base
    class) has always produced a real KeepoutConstraint for VIA_COUNT.
    """
    gate = PhysicsGate()
    v = Violation(
        type=ViolationType.VIA_COUNT,
        components=("Q1",),
        severity=3.0,
        threshold=9.0,
        description="Too few thermal vias",
        context={"device": "Q1"},
    )
    delta = gate.to_delta(v)
    assert delta is not None
    assert type(delta.constraint).__name__ == "KeepoutConstraint"


def test_physics_to_delta_unrecognized_returns_none():
    gate = PhysicsGate()
    v = Violation(type=ViolationType.CLEARANCE)
    assert gate.to_delta(v) is None


# =========================================================================
# Three-state invariant
# =========================================================================


def test_clean_and_unmeasured_are_distinct():
    """Empty violations means two different things depending on status."""
    clean = GateResult(GateStatus.CLEAN)
    unmeasured = GateResult(GateStatus.UNMEASURED, error_message="tool crashed")
    assert clean.violations == unmeasured.violations == ()
    assert clean.status is not unmeasured.status


# =========================================================================
# ViolationType completeness
# =========================================================================


def test_all_new_violation_types_defined():
    """Verify U5 violation types exist in the enum."""
    assert ViolationType.LOOP_INDUCTANCE
    assert ViolationType.THERMAL
    assert ViolationType.CREEPAGE
    assert ViolationType.VIA_COUNT
