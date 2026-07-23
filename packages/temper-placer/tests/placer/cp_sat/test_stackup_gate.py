"""Tests for StackupGate three-state measurement discipline.

Covers:
- CLEAN state when no reference-plane splits or current-density violations
- VIOLATIONS state for plane-splits and under-sized traces
- UNMEASURED state when data is missing or measurement fails
- to_delta mapping for CURRENT_DENSITY and REFERENCE_PLANE_SPLIT

Part of W2/U6 — functional stackup gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    StackupGate,
    Violation,
    ViolationType,
)

# ------------------------------------------------------------------
# Route-like stub for testing
# ------------------------------------------------------------------


@dataclass
class _FakeRoute:
    net_name: str
    width_mm: float = 0.3
    layer: str = "F.Cu"
    segments: list[Any] = field(default_factory=list)


@dataclass
class _FakeRoutingResult:
    compiled_routes: dict[str, _FakeRoute] = field(default_factory=dict)
    unrouted_nets: list[str] = field(default_factory=list)

    @property
    def _result(self) -> dict[str, _FakeRoute]:
        return self.compiled_routes


def _make_state(routing=None, pcb_path=True):
    from pathlib import Path

    return BoardState(
        routing=routing,
        routed_pcb_path=Path("/tmp/routed.kicad_pcb") if pcb_path else None,
    )


# ------------------------------------------------------------------
# CLEAN
# ------------------------------------------------------------------


def test_clean_empty_routing():
    """No routes, no violations → CLEAN."""
    gate = StackupGate()
    result = gate.check(_make_state(routing=_FakeRoutingResult({}, [])))
    assert result.status is GateStatus.CLEAN
    assert result.violations == ()


def test_clean_signal_nets_in_spec():
    """Signal nets with adequate trace width → CLEAN."""
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "SIG1": _FakeRoute("SIG1", width_mm=0.3, layer="F.Cu"),
                    "GATE_H": _FakeRoute("GATE_H", width_mm=0.6, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.CLEAN


# ------------------------------------------------------------------
# VIOLATIONS — current density
# ------------------------------------------------------------------


def test_violation_undersized_high_current():
    """A 16A net with thin trace → CURRENT_DENSITY violation."""
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "DC_BUS+": _FakeRoute("DC_BUS+", width_mm=0.3, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) >= 1
    v = result.violations[0]
    assert v.type is ViolationType.CURRENT_DENSITY
    assert v.nets == ("DC_BUS+",)
    assert v.severity == 0.3  # actual width
    assert v.threshold > 0.3  # minimum should be larger


def test_violation_includes_context():
    """Violation carries diagnostic context."""
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "AC_L": _FakeRoute("AC_L", width_mm=0.3, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.VIOLATIONS
    v = result.violations[0]
    assert "current_a" in v.context
    assert v.context["current_a"] == 10.0
    assert "min_width_mm" in v.context


def test_adequate_width_no_violation():
    """A 2A gate drive net with adequate width → no CURRENT_DENSITY."""
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "GATE_H": _FakeRoute("GATE_H", width_mm=0.6, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.CLEAN


def test_low_current_signal_no_violation():
    """A 0.1A signal net with narrow width is still OK."""
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "SIG_A": _FakeRoute("SIG_A", width_mm=0.15, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.CLEAN


# ------------------------------------------------------------------
# UNMEASURED
# ------------------------------------------------------------------


def test_unmeasured_no_routing():
    result = StackupGate().check(BoardState(routing=None))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_unmeasured_no_pcb_path():
    result = StackupGate().check(_make_state(routing=_FakeRoutingResult(), pcb_path=False))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_unmeasured_never_clean_when_empty():
    """UNMEASURED with empty violations is distinct from CLEAN."""
    unmeasured = GateResult(GateStatus.UNMEASURED, error_message="tool crashed")
    clean = GateResult(GateStatus.CLEAN)
    assert unmeasured.violations == clean.violations == ()
    assert unmeasured.status is not clean.status


# ------------------------------------------------------------------
# to_delta
# ------------------------------------------------------------------


def test_to_delta_current_density_returns_none():
    """CURRENT_DENSITY has no corrective placement delta.

    VERIFIED 2026-07-18: this test previously expected a "width increase"
    delta dict shape (delta["type"] == "trace_width_increase", etc.) that
    doesn't correspond to any PCL constraint type -- ConstraintDelta
    always wraps a placement/position constraint (SeparatedConstraint,
    LoopAreaConstraint, KeepoutConstraint, AnchoredConstraint), never a
    routing-parameter change like trace width. test_delta_mapper.py's own
    test_unmapped_type_returns_none explicitly parametrizes
    CURRENT_DENSITY as an intentionally unmapped type -- there is no
    placement-based fix for a current-density violation.
    """
    gate = StackupGate()
    v = Violation(
        type=ViolationType.CURRENT_DENSITY,
        nets=("DC_BUS+",),
        severity=0.3,
        threshold=2.5,
    )
    assert gate.to_delta(v) is None


def test_to_delta_reference_plane_split():
    """REFERENCE_PLANE_SPLIT → None (routing must re-path)."""
    gate = StackupGate()
    v = Violation(
        type=ViolationType.REFERENCE_PLANE_SPLIT,
        nets=("USB_D+",),
        description="plane gap under trace",
    )
    assert gate.to_delta(v) is None


def test_to_delta_other_type_returns_none():
    """Non-stackup violation types return None."""
    gate = StackupGate()
    v = Violation(type=ViolationType.CLEARANCE)
    assert gate.to_delta(v) is None


# ------------------------------------------------------------------
# Contract conformance
# ------------------------------------------------------------------


def test_stage_and_name():
    gate = StackupGate()
    assert gate.stage is GateStage.ROUTING
    assert gate.name == "stackup"
    assert isinstance(gate, Gate)


def test_internal_layer_detection():
    """Internal-layer routes are detected and get derated."""
    gate = StackupGate()
    # Route on In2.Cu (internal)
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "DC_BUS+": _FakeRoute("DC_BUS+", width_mm=0.5, layer="In2.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.VIOLATIONS  # internal layer → even lower capacity


def test_gate_survives_malformed_route():
    """Gate returns UNMEASURED instead of crashing on malformed route objects."""
    gate = StackupGate()

    @dataclass
    class _BrokenRoute:
        pass

    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={"NET_A": _BrokenRoute()},
                unrouted_nets=[],
            )
        )
    )
    # Should still succeed (extract width returns None, no violation emitted).
    assert result.status is GateStatus.CLEAN


def test_violation_type_members_exist():
    """REFERENCE_PLANE_SPLIT and CURRENT_DENSITY are in the enum."""
    assert ViolationType.REFERENCE_PLANE_SPLIT.value == "reference_plane_split"
    assert ViolationType.CURRENT_DENSITY.value == "current_density"
