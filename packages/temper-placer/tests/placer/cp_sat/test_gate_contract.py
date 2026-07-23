"""Gate contract data-type invariants.

Covers the pure-data-type contract from
``docs/brainstorms/2026-07-08-gate-contract.md``: every requirement in
U1 (GateStatus, GateStage, ViolationType, Violation, GateResult,
BoardState, Gate) is verified here.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)

# ---------------------------------------------------------------------------
# GateStatus
# ---------------------------------------------------------------------------


class TestGateStatus:
    def test_exactly_three_members(self):
        members = list(GateStatus)
        assert len(members) == 3
        assert GateStatus.CLEAN in members
        assert GateStatus.VIOLATIONS in members
        assert GateStatus.UNMEASURED in members

    def test_values_are_strings(self):
        assert GateStatus.CLEAN.value == "clean"
        assert GateStatus.VIOLATIONS.value == "violations"
        assert GateStatus.UNMEASURED.value == "unmeasured"


# ---------------------------------------------------------------------------
# GateStage
# ---------------------------------------------------------------------------


class TestGateStage:
    def test_exactly_two_members(self):
        members = list(GateStage)
        assert len(members) == 2
        assert GateStage.PLACEMENT in members
        assert GateStage.ROUTING in members

    def test_values_are_strings(self):
        assert GateStage.PLACEMENT.value == "placement"
        assert GateStage.ROUTING.value == "routing"


# ---------------------------------------------------------------------------
# ViolationType
# ---------------------------------------------------------------------------


class TestViolationType:
    def test_has_contract_types(self):
        required = {
            ViolationType.CLEARANCE,
            ViolationType.UNROUTED,
            ViolationType.LOOP_INDUCTANCE,
            ViolationType.THERMAL,
            ViolationType.CREEPAGE,
            ViolationType.VIA_COUNT,
            ViolationType.SLOP,
        }
        all_types = set(ViolationType)
        assert required <= all_types

    def test_has_w1_w2_w4_types(self):
        assert ViolationType.SHORTING
        assert ViolationType.MASK_BRIDGE
        assert ViolationType.EDGE_CLEARANCE
        assert ViolationType.REFERENCE_PLANE_SPLIT
        assert ViolationType.CURRENT_DENSITY
        assert ViolationType.OCTILINEAR

    def test_values_are_strings(self):
        assert ViolationType.CLEARANCE.value == "clearance"
        assert ViolationType.UNROUTED.value == "unrouted"
        assert ViolationType.CREEPAGE.value == "creepage"


# ---------------------------------------------------------------------------
# Violation
# ---------------------------------------------------------------------------


class TestViolation:
    def test_default_values(self):
        v = Violation(type=ViolationType.CLEARANCE)
        assert v.components == ()
        assert v.nets == ()
        assert v.severity == 0.0
        assert v.threshold == 0.0
        assert v.description == ""
        assert v.context == {}

    def test_all_fields_populated(self):
        v = Violation(
            type=ViolationType.CREEPAGE,
            components=("Q1", "Q2"),
            nets=("DC_BUS+", "AC_L"),
            severity=4.5,
            threshold=6.0,
            description="Creepage too small",
            context={"required_mm": 6.0},
        )
        assert v.type is ViolationType.CREEPAGE
        assert v.components == ("Q1", "Q2")
        assert v.nets == ("DC_BUS+", "AC_L")
        assert v.severity == 4.5
        assert v.threshold == 6.0
        assert v.description == "Creepage too small"
        assert v.context == {"required_mm": 6.0}

    def test_is_frozen(self):
        v = Violation(type=ViolationType.CLEARANCE)
        with pytest.raises(dataclasses.FrozenInstanceError):
            v.severity = 1.0  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            v.components = ("X",)  # type: ignore[misc]

    def test_is_hashable(self):
        v1 = Violation(type=ViolationType.CLEARANCE, severity=1.0)
        v2 = Violation(type=ViolationType.CLEARANCE, severity=1.0)
        assert v1 == v2
        assert v1 is not v2


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


class TestGateResult:
    def test_clean_has_empty_violations(self):
        r = GateResult(GateStatus.CLEAN)
        assert r.status is GateStatus.CLEAN
        assert r.violations == ()
        assert r.error_message == ""

    def test_unmeasured_has_error_message(self):
        r = GateResult(GateStatus.UNMEASURED, error_message="kicad-cli exit 3")
        assert r.status is GateStatus.UNMEASURED
        assert r.violations == ()
        assert r.error_message == "kicad-cli exit 3"

    def test_violations_with_items(self):
        v = Violation(type=ViolationType.CLEARANCE)
        r = GateResult(GateStatus.VIOLATIONS, violations=(v,))
        assert r.status is GateStatus.VIOLATIONS
        assert r.violations == (v,)

    def test_violations_with_empty_tuple_is_rejected(self):
        with pytest.raises(
            ValueError,
            match="VIOLATIONS must have at least one",
        ):
            GateResult(GateStatus.VIOLATIONS, violations=())

    def test_clean_and_unmeasured_not_equal(self):
        clean = GateResult(GateStatus.CLEAN)
        unmeasured = GateResult(GateStatus.UNMEASURED, error_message="tool crashed")
        assert clean.status is not unmeasured.status
        assert clean != unmeasured

    def test_is_frozen(self):
        r = GateResult(GateStatus.CLEAN)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.status = GateStatus.UNMEASURED  # type: ignore[misc]

    def test_is_hashable(self):
        r1 = GateResult(GateStatus.CLEAN)
        r2 = GateResult(GateStatus.CLEAN)
        assert hash(r1) == hash(r2)


def is_green(result: GateResult) -> bool:
    """Predicate that gates the contract invariant:
    only ``CLEAN`` counts as passing; UNMEASURED is never green.
    """
    return result.status is GateStatus.CLEAN


class TestIsGreenPredicate:
    """The loop convergence predicate — a pure function over status."""

    def test_clean_is_green(self):
        assert is_green(GateResult(GateStatus.CLEAN)) is True

    def test_violations_is_not_green(self):
        v = Violation(type=ViolationType.CLEARANCE)
        assert is_green(GateResult(GateStatus.VIOLATIONS, violations=(v,))) is False

    def test_unmeasured_is_not_green(self):
        assert is_green(GateResult(GateStatus.UNMEASURED, error_message="tool crash")) is False

    def test_empty_violations_but_unmeasured_is_not_green(self):
        """Architectural heart: UNMEASURED with no violations is NOT CLEAN."""
        r = GateResult(GateStatus.UNMEASURED, error_message="tool crash")
        assert r.violations == ()
        assert r.status is not GateStatus.CLEAN
        assert is_green(r) is False


# ---------------------------------------------------------------------------
# BoardState
# ---------------------------------------------------------------------------


class TestBoardState:
    def test_default_values(self):
        bs = BoardState()
        assert bs.placement is None
        assert bs.routing is None
        assert bs.netlist is None
        assert bs.board is None
        assert bs.design_rules is None
        assert bs.routed_pcb_path is None

    def test_all_fields_populated(self):
        fake_placement: Any = object()
        fake_routing: Any = object()
        fake_netlist: Any = object()
        fake_board: Any = object()
        fake_drc: Any = object()
        path = Path("/tmp/test.kicad_pcb")

        bs = BoardState(
            placement=fake_placement,
            routing=fake_routing,
            netlist=fake_netlist,
            board=fake_board,
            design_rules=fake_drc,
            routed_pcb_path=path,
        )
        assert bs.placement is fake_placement
        assert bs.routing is fake_routing
        assert bs.netlist is fake_netlist
        assert bs.board is fake_board
        assert bs.design_rules is fake_drc
        assert bs.routed_pcb_path is path

    def test_is_frozen(self):
        bs = BoardState()
        with pytest.raises(dataclasses.FrozenInstanceError):
            bs.placement = object()  # type: ignore[misc]

    def test_equality(self):
        path = Path("/tmp/a.kicad_pcb")
        bs1 = BoardState(routed_pcb_path=path)
        bs2 = BoardState(routed_pcb_path=path)
        assert bs1 == bs2
        assert bs1 is not bs2

    def test_has_required_fields(self):
        fields = {f.name for f in dataclasses.fields(BoardState)}
        assert "placement" in fields
        assert "routing" in fields
        assert "netlist" in fields
        assert "board" in fields
        assert "design_rules" in fields
        assert "routed_pcb_path" in fields


# ---------------------------------------------------------------------------
# Gate base class
# ---------------------------------------------------------------------------


class TestGate:
    def test_has_stage_and_name_annotations(self):
        assert "stage" in Gate.__annotations__
        assert "name" in Gate.__annotations__

    def test_check_raises_not_implemented(self):
        g = Gate()
        with pytest.raises(NotImplementedError):
            g.check(BoardState())

    def test_to_delta_returns_none_on_base(self):
        g = Gate()
        v = Violation(type=ViolationType.CLEARANCE)
        assert g.to_delta(v) is None

    def test_gate_is_subclassable(self):
        class MyGate(Gate):
            stage = GateStage.PLACEMENT
            name = "my_gate"

            def check(self, state: BoardState) -> GateResult:
                return GateResult(GateStatus.CLEAN)

        g = MyGate()
        assert g.stage is GateStage.PLACEMENT
        assert g.name == "my_gate"
        result = g.check(BoardState())
        assert result.status is GateStatus.CLEAN
