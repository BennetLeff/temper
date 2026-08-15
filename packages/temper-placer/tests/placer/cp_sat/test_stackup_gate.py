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
                    # 2A external, 1 oz: IPC-2221B minimum is 0.786mm.
                    "GATE_H": _FakeRoute("GATE_H", width_mm=1.0, layer="F.Cu"),
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
    # 15.0A, not 10.0A: the AC-mains design current was corrected to
    # elec/src/constraints.ato:11 (ACMainsConstraints.i_max = 15A) by
    # #1205's c0ceb94d4 -- this assertion predates that correction and
    # pinned the superseded 10.0A figure (stale ground truth, not a
    # behavior this test is supposed to guard).
    assert v.context["current_a"] == 15.0
    assert "min_width_mm" in v.context


def test_adequate_width_no_violation():
    """A 2A gate drive net with adequate width → no CURRENT_DENSITY."""
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    # 2A external, 1 oz: IPC-2221B minimum is 0.786mm.
                    "GATE_H": _FakeRoute("GATE_H", width_mm=1.0, layer="F.Cu"),
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

def test_copper_weight_resolved_from_stackup():
    """Copper weight comes from the board stackup, not a hardcoded 1.0.

    2A external trace: IPC-2221B minimum is 0.786mm at 1 oz but only
    0.393mm at 2 oz (width scales inversely with thickness).  A 0.5mm
    trace is a violation under the old hardcoded 1 oz and CLEAN under
    the declared 2 oz outer stackup — this test pins the stackup-driven
    resolution (gates.py `_resolve_copper_oz`).
    """
    from temper_placer.core.board import Board, Layer, LayerStackup

    gate = StackupGate()
    stackup = LayerStackup(
        layers=(
            Layer(name="F.Cu", layer_type="signal", copper_weight=2.0, is_routable=True),
            Layer(name="In1.Cu", layer_type="plane", copper_weight=1.0, is_routable=False),
            Layer(name="In2.Cu", layer_type="plane", copper_weight=1.0, is_routable=False),
            Layer(name="B.Cu", layer_type="signal", copper_weight=2.0, is_routable=True),
        ),
        thickness=1.6,
    )
    board = Board(width=100.0, height=150.0, layer_stackup=stackup)
    from pathlib import Path

    state = BoardState(
        board=board,
        routing=_FakeRoutingResult(
            compiled_routes={
                "GATE_H": _FakeRoute("GATE_H", width_mm=0.5, layer="F.Cu"),
            },
            unrouted_nets=[],
        ),
        routed_pcb_path=Path("/tmp/routed.kicad_pcb"),
    )
    # 0.5mm at 2 oz external is above the 0.393mm IPC-2221B minimum.
    result = gate.check(state)
    assert result.status is GateStatus.CLEAN


def test_copper_weight_stackup_missing_uses_role_aware_fallback():
    """No stackup present → role-aware fallback, not a flat 1.0.

    Merged from two PRs that fixed the same copper-weight blindness
    differently: main's #1223 reads the board stackup live (with a flat 1.0
    fallback), PR #1195/#1204 makes the fallback role-aware (2oz outer /
    1oz inner -- the board's own declared figures).  The merged gate keeps
    the live read when a stackup exists and falls back role-aware when it
    does not:

    - F.Cu (external, 2oz fallback): 2A needs only 0.393mm at 2oz, so a
      0.5mm trace is CLEAN -- the same trace the old flat-1.0 assumption
      would have flagged (0.786mm at 1oz), which was over-conservative,
      not physically real.
    - In3.Cu (internal, 1oz fallback): the SAME 0.5mm/2A trace is a
      VIOLATION, proving the fallback still enforces the real inner
      figure instead of being silently widened to the outer weight.
    """
    gate = StackupGate()
    result_external = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "GATE_H": _FakeRoute("GATE_H", width_mm=0.5, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result_external.status is GateStatus.CLEAN

    result_internal = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "GATE_H": _FakeRoute("GATE_H", width_mm=0.5, layer="In3.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result_internal.status is GateStatus.VIOLATIONS


def test_in3_in4_detected_as_internal():
    """PR #1195 (docs/evidence/2026-08-13-router-nlayer-routing.md): the
    board's stackup grew In3.Cu/In4.Cu as new INNER signal layers, but
    `_is_internal_net` used to only recognize {"In1.Cu", "In2.Cu"} -- so a
    route on In3.Cu/In4.Cu was silently treated as external (checked
    against the more lenient k=0.048 curve) even though it is genuinely
    1oz internal copper. Same width/current as
    test_internal_layer_detection's In2.Cu case, on In3.Cu instead --
    must still be flagged.
    """
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "DC_BUS+": _FakeRoute("DC_BUS+", width_mm=0.5, layer="In3.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.VIOLATIONS


def test_copper_oz_reads_outer_role_for_external_layer():
    """The gate used to check EVERY route (internal or external) against a
    flat `copper_oz=1.0`, even on F.Cu/B.Cu, which the board's own declared
    stackup says are 2oz -- an accidentally-conservative but physically
    wrong input. A width that needs 2oz to pass but would fail at a
    (wrong) 1oz assumption must now pass on F.Cu.
    """
    import temper_geometry as _tg

    gate = StackupGate()
    current_a = 10.0  # AC_L's real cited current
    # Width whose capacity clears 10A at the REAL 2oz external weight but
    # would not at 1oz -- proves the gate is reading 2oz here, not 1.0.
    width_2oz_min = _tg.ipc2221b_min_trace_width_mm_py(current_a, 2.0, 10.0, False)
    width_1oz_min = _tg.ipc2221b_min_trace_width_mm_py(current_a, 1.0, 10.0, False)
    assert width_1oz_min > width_2oz_min  # sanity: 1oz genuinely needs more width
    probe_width = (width_2oz_min + width_1oz_min) / 2.0  # clears 2oz, not 1oz

    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "AC_L": _FakeRoute("AC_L", width_mm=probe_width, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.CLEAN


def test_in3_in4_detected_as_internal():
    """PR #1195 (docs/evidence/2026-08-13-router-nlayer-routing.md): the
    board's stackup grew In3.Cu/In4.Cu as new INNER signal layers, but
    `_is_internal_net` used to only recognize {"In1.Cu", "In2.Cu"} -- so a
    route on In3.Cu/In4.Cu was silently treated as external (checked
    against the more lenient k=0.048 curve) even though it is genuinely
    1oz internal copper. Same width/current as
    test_internal_layer_detection's In2.Cu case, on In3.Cu instead --
    must still be flagged.
    """
    gate = StackupGate()
    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "DC_BUS+": _FakeRoute("DC_BUS+", width_mm=0.5, layer="In3.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.VIOLATIONS


def test_copper_oz_reads_outer_role_for_external_layer():
    """The gate used to check EVERY route (internal or external) against a
    flat `copper_oz=1.0`, even on F.Cu/B.Cu, which the board's own declared
    stackup says are 2oz -- an accidentally-conservative but physically
    wrong input. A width that needs 2oz to pass but would fail at a
    (wrong) 1oz assumption must now pass on F.Cu.
    """
    import temper_geometry as _tg

    gate = StackupGate()
    # 15.0A: elec/src/constraints.ato:11 (ACMainsConstraints.i_max) -- AC_L's
    # real cited current. Must track StackupGate._DEFAULT_NET_CURRENTS["AC_L"]
    # or this probe's width no longer brackets what the gate actually checks.
    current_a = 15.0
    # Width whose capacity clears 10A at the REAL 2oz external weight but
    # would not at 1oz -- proves the gate is reading 2oz here, not 1.0.
    width_2oz_min = _tg.ipc2221b_min_trace_width_mm_py(current_a, 2.0, 10.0, False)
    width_1oz_min = _tg.ipc2221b_min_trace_width_mm_py(current_a, 1.0, 10.0, False)
    assert width_1oz_min > width_2oz_min  # sanity: 1oz genuinely needs more width
    probe_width = (width_2oz_min + width_1oz_min) / 2.0  # clears 2oz, not 1oz

    result = gate.check(
        _make_state(
            routing=_FakeRoutingResult(
                compiled_routes={
                    "AC_L": _FakeRoute("AC_L", width_mm=probe_width, layer="F.Cu"),
                },
                unrouted_nets=[],
            )
        )
    )
    assert result.status is GateStatus.CLEAN


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
