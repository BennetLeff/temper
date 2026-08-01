"""Minimum-displacement REQ-SAFE-01 clearance repair machinery (issue #504).

The routed board carries 123 REQ-SAFE-01 violations at the enforced 12.6mm
reinforced margin (PD3). A free CP-SAT reshuffle clears the movable pairs
but reproducibly regresses the routed board's DRC (shorting_items /
unconnected_items rise) because it moves nearly every component. The repair
machinery under test makes the solve *stay near the current board*:

- ``solve_placement(minimize_displacement_to=...)`` -- Manhattan-distance
  objective toward the current positions, hard constraints authoritative.
  Regression-guarded against the never-landed PR #498 no-op (terms were
  registered but ``Minimize`` was never called on the encoder solve path).
- ``solve_placement(fixed_rotations=...)`` -- routed-board repair must not
  rotate footprints (rotation moves pads, disconnecting routed copper).
- ``run_clearance_repair_solve`` -- the loop: full domain-clearance
  constraint set + unclassified-near-HV keep-away constraints +
  min-displacement objective + R24 post-solve audit + independent
  REQ-SAFE-01 checker re-verification + bounded constraint reinforcement.

Metamorphic relations asserted here (task brief):
1. Solver output re-checked by the INDEPENDENT REQ-SAFE-01 checker reports
   <= the solver's claimed violation bound (0 for inter-component pairs).
2. Solve determinism: same input + seed -> same output.
3. The checker's copper-to-copper distance is a LOWER bound on the old
   origin-to-origin distance (the relation that explains the old optimism).
4. BMC-exhaustive objective optimality against a truthful oracle (R24
   item-2 style) on small N.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.model import CpSatModel

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"

# ---------------------------------------------------------------------------
# Synthetic netlist/board helpers (same minimal shape as the rest of the
# placer/cp_sat test suite)
# ---------------------------------------------------------------------------


@dataclass
class MockPin:
    number: str
    net: str
    position: tuple[float, float]
    width: float = 1.0
    height: float = 1.0
    shape: str = "rect"
    roundrect_ratio: float = 0.0
    pad_rotation_deg: float = 0.0
    layer: str = "F.Cu"


@dataclass
class MockComp:
    ref: str
    bounds: tuple[float, float] = (10.0, 10.0)
    initial_position: tuple[float, float] = (0.0, 0.0)
    initial_rotation: int = 0
    pins: list = field(default_factory=list)
    zone: str | None = None
    attributes: dict = field(default_factory=dict)


@dataclass
class MockNet:
    name: str


@dataclass
class MockNetlist:
    components: list
    nets: list = field(default_factory=list)


@dataclass
class MockZone:
    name: str
    bounds: tuple[float, float, float, float]
    components: list = field(default_factory=list)


@dataclass
class MockBoard:
    width: float = 100.0
    height: float = 100.0
    zones: list = field(default_factory=list)
    origin: tuple[float, float] = (0.0, 0.0)
    constraints: list = field(default_factory=list)


def _pads_for_ref(ref: str, net: str, offset: tuple[float, float], half=0.5) -> list[dict]:
    """One 1x1mm rect pad at *offset* (validator pad schema)."""
    return [
        {
            "number": "1",
            "net": net,
            "offset": offset,
            "width": 1.0,
            "height": 1.0,
            "shape": "rect",
            "roundrect_ratio": 0.0,
            "pad_rotation_deg": 0.0,
            "layer": "F.Cu",
        }
    ]


def _make_placement(components: list[dict], nets: dict) -> dict:
    """Validator-shape placement: {"components": [...], "nets": {...}}."""
    return {
        "components": components,
        "nets": {name: {"domain": dom} for name, dom in nets.items()},
        "board": {"surface_cutouts": []},
    }


def _synthetic_board(comps: list[MockComp]) -> tuple[MockNetlist, MockBoard]:
    nets = sorted({p.net for c in comps for p in c.pins})
    return (
        MockNetlist(components=comps, nets=[MockNet(n) for n in nets]),
        MockBoard(width=152.0, height=234.0),
    )


# ---------------------------------------------------------------------------
# solve_placement(minimize_displacement_to=...) -- the objective is APPLIED
# ---------------------------------------------------------------------------


class TestSolvePlacementDisplacementObjective:
    """The objective must actually steer the solve (no-op regression)."""

    def test_reference_positions_returned_exactly_when_feasible(self) -> None:
        # Two 10mm components already separated by 60mm center-to-center:
        # both reference positions are feasible, so the unique optimum is
        # zero displacement and the solve must return them exactly.
        comps = [
            MockComp(ref="A", bounds=(10.0, 10.0), initial_position=(25.0, 50.0)),
            MockComp(ref="B", bounds=(10.0, 10.0), initial_position=(75.0, 50.0)),
        ]
        netlist, board = _synthetic_board(comps)
        ref = {"A": (25.0, 50.0), "B": (75.0, 50.0)}
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=10_000,
            seed=0,
            minimize_displacement_to=ref,
        )
        assert result.status == "optimal", result.status
        assert result.positions["A"] == (25.0, 50.0), result.positions
        assert result.positions["B"] == (75.0, 50.0), result.positions
        # Manhattan total: zero displacement.
        assert result.objective_value == 0.0

    def test_solver_breaks_infeasible_reference_with_minimal_moves(self) -> None:
        # Both components referenced at the shared center; a 50mm separation
        # between 10mm boxes forces |B - A| >= 60mm on at least one axis.
        # By |u - v| <= |u| + |v| the total Manhattan displacement is >= 60mm
        # and 60 is attainable, so EVERY optimal solution has total exactly 60.
        from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

        comps = [
            MockComp(ref="A", bounds=(10.0, 10.0), initial_position=(50.0, 50.0)),
            MockComp(ref="B", bounds=(10.0, 10.0), initial_position=(50.0, 50.0)),
        ]
        netlist, board = _synthetic_board(comps)
        sep = SeparatedConstraint(
            a="A",
            b="B",
            min_distance_mm=50.0,
            tier=ConstraintTier.HARD,
            id="test_sep_AB",
            because="test separation",
        )
        ref = {"A": (50.0, 50.0), "B": (50.0, 50.0)}
        result = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=[sep],
            timeout_ms=20_000,
            seed=0,
            minimize_displacement_to=ref,
        )
        assert result.status in ("optimal", "feasible"), result.status
        ax, ay = result.positions["A"]
        bx, by = result.positions["B"]
        # Feasibility: the 50mm box separation holds on at least one axis.
        assert max(abs(bx - ax), abs(by - ay)) >= 59.999, (ax, ay, bx, by)
        # Optimality: exactly the proven minimum total displacement.
        disp = abs(ax - 50.0) + abs(ay - 50.0) + abs(bx - 50.0) + abs(by - 50.0)
        assert disp <= 60.001, f"total displacement {disp} exceeds the optimum 60.0"

    def test_unknown_ref_in_objective_raises(self) -> None:
        comps = [MockComp(ref="A", bounds=(10.0, 10.0), initial_position=(10.0, 10.0))]
        netlist, board = _synthetic_board(comps)
        with pytest.raises(KeyError):
            solve_placement(
                netlist=netlist,
                board=board,
                timeout_ms=1_000,
                minimize_displacement_to={"GHOST": (0.0, 0.0)},
            )

    def test_displacement_bound_without_reference_raises(self) -> None:
        # Same silent-no-op class as never-landed PR #498: a bound with no
        # reference would constrain nothing. Must fail loudly.
        comps = [MockComp(ref="A", bounds=(10.0, 10.0), initial_position=(10.0, 10.0))]
        netlist, board = _synthetic_board(comps)
        with pytest.raises(ValueError, match="minimize_displacement_to"):
            solve_placement(
                netlist=netlist,
                board=board,
                timeout_ms=1_000,
                max_displacement_mm=5.0,
            )

    @settings(max_examples=10, deadline=30_000)
    @given(st.integers(min_value=1, max_value=6))
    def test_determinism_same_input_same_output(self, seed: int) -> None:
        from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

        comps = [
            MockComp(ref="A", bounds=(10.0, 10.0), initial_position=(30.0, 40.0)),
            MockComp(ref="B", bounds=(12.0, 8.0), initial_position=(70.0, 40.0)),
            MockComp(ref="C", bounds=(10.0, 10.0), initial_position=(50.0, 80.0)),
        ]
        netlist, board = _synthetic_board(comps)
        sep = SeparatedConstraint(
            a="A", b="B", min_distance_mm=30.0, tier=ConstraintTier.HARD, id="test_sep_AB",
            because="test separation",
        )
        ref = {c.ref: c.initial_position for c in comps}
        r1 = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=[sep],
            timeout_ms=20_000,
            seed=seed,
            minimize_displacement_to=ref,
        )
        r2 = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=[sep],
            timeout_ms=20_000,
            seed=seed,
            minimize_displacement_to=ref,
        )
        assert r1.positions == r2.positions
        assert r1.rotations == r2.rotations


class TestSolvePlacementFixedRotations:
    def test_rotation_pinned_to_current_board_value(self) -> None:
        comps = [
            MockComp(ref="A", bounds=(20.0, 10.0), initial_position=(30.0, 40.0), initial_rotation=1),
        ]
        netlist, board = _synthetic_board(comps)
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=10_000,
            seed=0,
            fixed_rotations={"A": 1},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.rotations["A"] == 1

    def test_conflicting_fixed_rotation_for_polarized_raises(self) -> None:
        comps = [MockComp(ref="A", bounds=(20.0, 10.0), initial_position=(30.0, 40.0))]
        netlist, board = _synthetic_board(comps)
        # A is not in the hardcoded polarized set, so build the model path
        # directly to hit the polarized branch:
        model = CpSatModel()
        model.add_component("A", 0, 0, width=2000, height=1000)
        model.add_rotation("A", is_polarized=True)
        with pytest.raises(ValueError):
            model.add_fixed_rotation("A", 2)
        model.add_fixed_rotation("A", 0)  # consistent no-op


# ---------------------------------------------------------------------------
# BMC-exhaustive objective optimality against a truthful oracle (R24 item 2)
# ---------------------------------------------------------------------------


class TestDisplacementObjectiveBMC:
    """Exhaustive small-N validation: the solver's displacement equals the
    minimum over ALL feasible placements, computed by an independent oracle.

    Setup: one 100x100-unit component in a [50, 950]^2 bounds window with a
    400x400-unit keepout zone centred at (500, 500). The feasible centre
    region is the union of four rectangles (component box must clear the
    keepout on x OR y, and stay inside bounds). For every reference point on
    a coarse grid, the oracle's optimum is the closed-form Manhattan distance
    to that union; the solver must reproduce it exactly.
    """

    KEEPOUT = (300, 300, 400, 400)  # x_min, y_min, w, h -> [300,700]^2
    FEASIBLE_RECTS = [
        (100, 250, 100, 900),  # left of keepout
        (750, 900, 100, 900),  # right of keepout
        (100, 900, 100, 250),  # below keepout
        (100, 900, 750, 900),  # above keepout
    ]

    @staticmethod
    def _oracle_distance(ref_x: int, ref_y: int) -> int:
        best = 10**9
        for x0, x1, y0, y1 in TestDisplacementObjectiveBMC.FEASIBLE_RECTS:
            dx = max(0, x0 - ref_x, ref_x - x1)
            dy = max(0, y0 - ref_y, ref_y - y1)
            best = min(best, dx + dy)
        return best

    @settings(max_examples=25, deadline=20_000)
    @given(
        st.integers(min_value=100, max_value=900),
        st.integers(min_value=100, max_value=900),
    )
    def test_solver_reproduces_oracle_minimum(self, ref_x: int, ref_y: int) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        model.set_bounds(x_min=50, y_min=50, x_max=950, y_max=950)
        kx, ky, kw, kh = self.KEEPOUT
        kx_iv, ky_iv = model.add_keepout_interval("k1", kx, ky, kw, kh)
        model.add_no_overlap_2d(["Q1"], extra_x_intervals=[kx_iv], extra_y_intervals=[ky_iv])
        model.add_displacement_objective("Q1", ref_x, ref_y)
        model.apply_objective()
        sol = model.solve(time_limit_s=5.0)
        assert sol.feasible, sol.status
        x, y = sol.positions["Q1"]
        # Feasibility: not overlapping the keepout, inside bounds.
        box_x0, box_x1 = x - 50, x + 50
        box_y0, box_y1 = y - 50, y + 50
        overlap = box_x0 < 700 and box_x1 > 300 and box_y0 < 700 and box_y1 > 300
        assert not overlap, (x, y)
        assert 100 <= x <= 900 and 100 <= y <= 900, (x, y)
        # Optimality: exact reproduction of the oracle minimum.
        oracle = self._oracle_distance(ref_x, ref_y)
        actual = abs(x - ref_x) + abs(y - ref_y)
        assert actual == oracle, f"ref=({ref_x},{ref_y}) solver={actual} oracle={oracle}"

    def test_reference_inside_keepout_moves_out_minimally(self) -> None:
        # Reference at the keepout center (500, 500): the closest feasible
        # point is 250 units away on any axis (250 or 750 coordinate).
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        model.set_bounds(x_min=50, y_min=50, x_max=950, y_max=950)
        kx, ky, kw, kh = self.KEEPOUT
        kx_iv, ky_iv = model.add_keepout_interval("k1", kx, ky, kw, kh)
        model.add_no_overlap_2d(["Q1"], extra_x_intervals=[kx_iv], extra_y_intervals=[ky_iv])
        model.add_displacement_objective("Q1", 500, 500)
        model.apply_objective()
        sol = model.solve(time_limit_s=5.0)
        assert sol.feasible
        x, y = sol.positions["Q1"]
        assert abs(x - 500) + abs(y - 500) == 250, (x, y)


# ---------------------------------------------------------------------------
# Unclassified-near-HV keep-away constraints (promoted from 2026-07-27 scratch)
# ---------------------------------------------------------------------------


class TestUnclassifiedHvKeepawayConstraints:
    def test_one_constraint_per_unclassified_hv_pair_at_max_margin(self) -> None:
        from temper_placer.pcl.constraints import ConstraintTier
        from temper_placer.placer.cp_sat.domain_clearance import (
            generate_unclassified_hv_keepaway_constraints,
        )
        from temper_placer.requirements.validators.clearance import (
            IEC60335_REQUIREMENTS,
            VoltageDomain,
        )

        max_margin = max(
            max(r["min_clearance_mm"], r["min_creepage_mm"]) for r in IEC60335_REQUIREMENTS.values()
        )
        placement = _make_placement(
            components=[
                {"ref": "A", "position": (0.0, 0.0), "nets": ["dc_bus"], "pads": []},
                {"ref": "B", "position": (0.0, 0.0), "nets": ["gnd"], "pads": []},
            ],
            nets={"dc_bus": VoltageDomain.DC_BUS, "gnd": VoltageDomain.LV_CONTROL},
        )
        cons = generate_unclassified_hv_keepaway_constraints(
            placement, {}, component_refs={"A", "B", "C", "D"}
        )
        # C and D are unclassified; only A is HV. Two constraints at max margin.
        assert {c.id for c in cons} == {"keepaway_unclassified_C_A", "keepaway_unclassified_D_A"}
        for c in cons:
            assert c.min_distance_mm == max_margin
            assert c.tier is ConstraintTier.HARD

    def test_chain_sibling_exempt_pairs_skipped(self) -> None:
        from temper_placer.placer.cp_sat.domain_clearance import (
            generate_unclassified_hv_keepaway_constraints,
        )
        from temper_placer.requirements.validators.clearance import VoltageDomain

        placement = _make_placement(
            components=[
                {"ref": "A", "position": (0.0, 0.0), "nets": ["dc_bus"], "pads": []},
            ],
            nets={"dc_bus": VoltageDomain.DC_BUS},
        )
        cons = generate_unclassified_hv_keepaway_constraints(
            placement,
            {},
            component_refs={"A", "C"},
            exempt_pairs={frozenset({"A", "C"})},
        )
        assert cons == []

    def test_no_unclassified_refs_produces_no_constraints(self) -> None:
        from temper_placer.placer.cp_sat.domain_clearance import (
            generate_unclassified_hv_keepaway_constraints,
        )
        from temper_placer.requirements.validators.clearance import VoltageDomain

        placement = _make_placement(
            components=[
                {"ref": "A", "position": (0.0, 0.0), "nets": ["dc_bus"], "pads": []},
                {"ref": "B", "position": (0.0, 0.0), "nets": ["gnd"], "pads": []},
            ],
            nets={"dc_bus": VoltageDomain.DC_BUS, "gnd": VoltageDomain.LV_CONTROL},
        )
        cons = generate_unclassified_hv_keepaway_constraints(
            placement, {}, component_refs={"A", "B"}
        )
        assert cons == []


# ---------------------------------------------------------------------------
# The repair loop itself
# ---------------------------------------------------------------------------


class TestRepairLoopSynthetic:
    """End-to-end repair-loop behaviour on small synthetic boards with real
    pad geometry (so the independent checker measures real copper)."""

    def _synthetic_repair_input(self, gap_mm: float, bounds_pad: float):
        """A (HV, SELV, unclassified) triple whose HV/SELV pair violates at
        *gap_mm*; ``bounds_pad`` widens the solver's box beyond the pads."""
        from temper_placer.requirements.validators.clearance import VoltageDomain

        # A: one 1x1mm DC_BUS pad at (0,0). B: one 1x1mm gnd pad at (gap, 0).
        half = 0.5
        comp_a = MockComp(
            ref="A",
            bounds=(2 * half + bounds_pad, 2 * half + bounds_pad),
            initial_position=(10.0, 10.0),
            pins=[MockPin("1", "dc_bus", (0.0, 0.0))],
        )
        comp_b = MockComp(
            ref="B",
            bounds=(2 * half + bounds_pad, 2 * half + bounds_pad),
            initial_position=(10.0 + gap_mm, 10.0),
            pins=[MockPin("1", "gnd", (0.0, 0.0))],
        )
        comp_c = MockComp(
            ref="C", bounds=(10.0, 10.0), initial_position=(40.0, 40.0), pins=[]
        )
        netlist, board = _synthetic_board([comp_a, comp_b, comp_c])
        placement = _make_placement(
            components=[
                {
                    "ref": "A",
                    "position": (10.0, 10.0),
                    "nets": ["dc_bus"],
                    "pads": _pads_for_ref("A", "dc_bus", (0.0, 0.0)),
                    "rotation_deg": 0.0,
                },
                {
                    "ref": "B",
                    "position": (10.0 + gap_mm, 10.0),
                    "nets": ["gnd"],
                    "pads": _pads_for_ref("B", "gnd", (0.0, 0.0)),
                    "rotation_deg": 0.0,
                },
            ],
            nets={"dc_bus": VoltageDomain.DC_BUS, "gnd": VoltageDomain.LV_CONTROL},
        )
        return netlist, board, placement, {"dc_bus": VoltageDomain.DC_BUS, "gnd": VoltageDomain.LV_CONTROL}

    def test_repair_drives_inter_component_violations_to_zero(self) -> None:
        from temper_placer.placer.cp_sat.clearance_repair import run_clearance_repair_solve
        from temper_placer.requirements.validators.clearance import (
            verify_iec60335_compliance,
        )

        netlist, board, placement, vd = self._synthetic_repair_input(gap_mm=5.0, bounds_pad=0.0)
        # Baseline: the checker must actually see the violation.
        before = verify_iec60335_compliance(placement, vd)
        assert before.error_count >= 1, "synthetic baseline must be violating"

        report = run_clearance_repair_solve(
            pcb_path=_PCB_PATH,  # unused for synthetic boards (positions in-memory)
            placement=placement,
            voltage_domains=vd,
            timeout_ms=20_000,
            seed=0,
            max_rounds=3,
            netlist=netlist,
            board=board,
        )
        assert report.status in ("clean", "intra_only"), report.reason
        assert report.final_inter_violations == 0, report.reason

        # Independent re-check on the solved placement: must report <= the
        # solver's claimed bound (0 inter-component records).
        solved = _override_positions(placement, report.final_positions)
        after = verify_iec60335_compliance(solved, vd)
        inter = [v for v in after.violations if v.pair_kind != "intra"]
        assert len(inter) == 0, after.report()
        assert report.audit_violations == 0

    def test_repair_keeps_unconstrained_component_in_place(self) -> None:
        from temper_placer.placer.cp_sat.clearance_repair import run_clearance_repair_solve

        netlist, board, placement, vd = self._synthetic_repair_input(gap_mm=5.0, bounds_pad=0.0)
        report = run_clearance_repair_solve(
            pcb_path=_PCB_PATH,
            placement=placement,
            voltage_domains=vd,
            timeout_ms=20_000,
            seed=0,
            max_rounds=3,
            netlist=netlist,
            board=board,
        )
        # C (unclassified, far from everything) must not have moved: the
        # min-displacement objective leaves unconstrained components put.
        assert report.final_positions["C"] == (40.0, 40.0), report.final_positions

    def test_repair_reports_bounded_infeasibility_honestly(self) -> None:
        """A too-tight hard displacement envelope must surface as PROVEN
        infeasible (with the UNSAT core reported), never as a silent
        failure or a false success."""
        from temper_placer.placer.cp_sat.clearance_repair import run_clearance_repair_solve

        netlist, board, placement, vd = self._synthetic_repair_input(gap_mm=5.0, bounds_pad=0.0)
        report = run_clearance_repair_solve(
            pcb_path=_PCB_PATH,
            placement=placement,
            voltage_domains=vd,
            timeout_ms=20_000,
            seed=0,
            max_rounds=2,
            max_displacement_mm=0.1,  # A/B are 5mm apart and need 8.0+; 0.1mm cannot fix it
            netlist=netlist,
            board=board,
        )
        assert report.status == "infeasible", report.reason
        assert "UNSAT" in report.reason or "infeasible" in report.reason.lower(), report.reason
        assert report.final_inter_violations >= 1, report.reason

    def test_repair_reports_constraint_model_gap_honestly(self) -> None:
        """If the solver's box model does NOT contain a component's pads, the
        checker can flag a pair the SAT'd constraints don't cover. The loop
        must add the reinforcement constraint, re-solve, and terminate with a
        loud 'gap' report -- never a silent false success."""
        from temper_placer.placer.cp_sat.clearance_repair import run_clearance_repair_solve
        from temper_placer.requirements.validators.clearance import (
            verify_iec60335_compliance,
        )

        netlist, board, placement, vd = self._synthetic_repair_input(gap_mm=5.0, bounds_pad=0.0)
        before = verify_iec60335_compliance(placement, vd)
        assert before.error_count >= 1

        # Shrink the solver's box to 1x1mm while the pad copper reaches
        # +/-0.5mm from the centre: box does not contain copper -> the box
        # separation constraint is weaker than the checker's requirement.
        for comp in netlist.components:
            if comp.ref in ("A", "B"):
                comp.bounds = (0.2, 0.2)

        report = run_clearance_repair_solve(
            pcb_path=_PCB_PATH,
            placement=placement,
            voltage_domains=vd,
            timeout_ms=20_000,
            seed=0,
            max_rounds=3,
            netlist=netlist,
            board=board,
        )
        # The loop must terminate (bounded) and must NOT claim a clean board.
        assert report.status == "gap", report.reason
        assert report.final_inter_violations >= 1, report.reason
        assert report.unreinforced_pairs, report.reason


def _override_positions(
    placement: dict, solved_positions: dict[str, tuple[float, float]]
) -> dict:
    """Return a copy of *placement* with component positions replaced by the
    solved positions (both in the local, origin-subtracted frame)."""
    import copy

    out = copy.deepcopy(placement)
    for c in out["components"]:
        pos = solved_positions.get(c["ref"])
        if pos is not None:
            c["position"] = pos
    return out


# ---------------------------------------------------------------------------
# Real-board integration: the actual success criterion of issue #504
# ---------------------------------------------------------------------------


class TestRealBoardClearanceRepair:
    def test_repair_solve_drives_inter_component_violations_to_zero(self) -> None:
        try:
            from tests.requirements.safety._real_board_fixture import (
                load_real_board_placement,
            )
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"real-board fixture unavailable: {exc}")
        if not _PCB_PATH.exists():
            pytest.skip("pcb/temper.kicad_pcb not present")

        placement, voltage_domains, stats = load_real_board_placement()
        full_placement = stats["full_placement"]
        full_vd = stats["full_voltage_domains"]

        from temper_placer.placer.cp_sat.clearance_repair import run_clearance_repair_solve

        report = run_clearance_repair_solve(
            pcb_path=_PCB_PATH,
            placement=full_placement,
            voltage_domains=full_vd,
            timeout_ms=90_000,
            seed=0,
            max_rounds=3,
            chain_exempt_pairs=stats["chain_sibling_exempt_pairs"],
        )

        # The independent checker must confirm the solver's claim: every
        # inter-component (movable) pair cleared.
        assert report.audit_violations == 0, (
            f"R24 post-solve audit found {report.audit_violations} mismatches"
        )
        assert report.final_inter_violations == 0, (
            f"repair left {report.final_inter_violations} inter-component "
            f"REQ-SAFE-01 violations: {report.reason}"
        )
        # Intra-footprint pairs are unfixable by placement: they must be
        # reported explicitly, never silently present in the count. On this
        # board the known intra family is the isolator set flagged by
        # find_intra_footprint_domain_conflicts.
        assert report.intra_blocker_refs, (
            "expected documented intra-footprint blockers (C6/K1/K2/K3/T1/U6 family)"
        )
        assert set(report.intra_blocker_refs) <= {
            "C6", "K1", "K2", "K3", "PS1", "T1", "U3", "U7",
        }, f"unexpected intra blocker refs: {report.intra_blocker_refs}"
        print(
            f"\nbaseline={report.baseline_violations} inter/final_inter="
            f"{report.final_inter_violations} intra={report.final_intra_violations} "
            f"blockers={sorted(report.intra_blocker_refs)} "
            f"displacement={report.total_displacement_mm:.2f}mm "
            f"status={report.status} rounds={len(report.rounds)}"
        )

    def test_checker_copper_distance_is_lower_bound_on_origin_distance(self) -> None:
        """Metamorphic relation (reach-bounded, provable): for any two
        components, copper-to-copper >= origin-to-origin - reach_A - reach_B,
        where reach = max pad |offset| + pad bounding radius. This is the
        sound bound the checker's own prune relies on. The stronger claim
        "copper <= origin" from the 2026-07-28 doc is *empirically* true for
        the pairs that board measured (their pads face each other) but is NOT
        a geometric law -- a pad pair facing away can exceed the origin
        distance (measured on this board: C22<->L2, copper 11.489mm vs
        origin 10.341mm). We assert the provable bound and count how many
        pairs sit in the optimistic (copper < origin) direction."""
        try:
            from tests.requirements.safety._real_board_fixture import (
                load_real_board_placement,
            )
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"real-board fixture unavailable: {exc}")
        from temper_placer.core.pad_geometry import pad_bounding_radius
        from temper_placer.requirements.validators.clearance import (
            verify_iec60335_compliance,
        )

        placement, voltage_domains, _stats = load_real_board_placement()
        result = verify_iec60335_compliance(placement, voltage_domains)
        positions = {c["ref"]: c["position"] for c in placement["components"]}
        pads_by_ref = {c["ref"]: c.get("pads", []) for c in placement["components"]}

        def _reach(ref: str) -> float:
            return max(
                (
                    math.hypot(*p["offset"])
                    + pad_bounding_radius(
                        p["width"], p["height"], p["shape"], p.get("roundrect_ratio", 0.0)
                    )
                    for p in pads_by_ref.get(ref, [])
                ),
                default=0.0,
            )

        inter = [v for v in result.violations if v.pair_kind != "intra"]
        assert inter, "expected inter-component violations in the baseline"
        optimistic = 0
        for v in inter:
            if not (v.ref_a and v.ref_b and v.ref_a in positions and v.ref_b in positions):
                continue
            origin_dist = math.dist(positions[v.ref_a], positions[v.ref_b])
            assert v.measured_mm is not None
            # Sound lower bound: copper >= origin - reach_a - reach_b.
            assert v.measured_mm >= origin_dist - _reach(v.ref_a) - _reach(v.ref_b) - 1e-9, (
                f"{v.ref_a}<->{v.ref_b}: copper {v.measured_mm}mm below the "
                f"sound origin-based lower bound "
                f"{origin_dist - _reach(v.ref_a) - _reach(v.ref_b):.3f}mm"
            )
            if v.measured_mm < origin_dist:
                optimistic += 1
        # The old origin-only checker was optimistic on a large majority of
        # the currently-flagged pairs -- that is the relation that explains
        # why 123 violations exist under the copper model.
        assert optimistic >= len(inter) // 2, (
            f"only {optimistic}/{len(inter)} violating pairs sit in the "
            "optimistic (copper < origin) direction"
        )


class TestRepairLoopTermination:
    def test_max_rounds_caps_loop(self) -> None:
        """Termination: even when reinforcement can never clear a pair (a
        constraint-model gap), the loop exits within max_rounds and reports
        why, rather than spinning forever."""
        from temper_placer.placer.cp_sat.clearance_repair import run_clearance_repair_solve
        from temper_placer.requirements.validators.clearance import VoltageDomain

        # A pair with pads outside the solver's box, and an unclassified ref
        # with no HV neighbour: reinforcement cannot help.
        comp_a = MockComp(
            ref="A",
            bounds=(0.2, 0.2),
            initial_position=(10.0, 10.0),
            pins=[MockPin("1", "dc_bus", (0.0, 0.0))],
        )
        comp_b = MockComp(
            ref="B",
            bounds=(0.2, 0.2),
            initial_position=(15.0, 10.0),
            pins=[MockPin("1", "gnd", (0.0, 0.0))],
        )
        netlist, board = _synthetic_board([comp_a, comp_b])
        placement = _make_placement(
            components=[
                {
                    "ref": "A",
                    "position": (10.0, 10.0),
                    "nets": ["dc_bus"],
                    "pads": _pads_for_ref("A", "dc_bus", (0.0, 0.0)),
                    "rotation_deg": 0.0,
                },
                {
                    "ref": "B",
                    "position": (15.0, 10.0),
                    "nets": ["gnd"],
                    "pads": _pads_for_ref("B", "gnd", (0.0, 0.0)),
                    "rotation_deg": 0.0,
                },
            ],
            nets={"dc_bus": VoltageDomain.DC_BUS, "gnd": VoltageDomain.LV_CONTROL},
        )
        report = run_clearance_repair_solve(
            pcb_path=_PCB_PATH,
            placement=placement,
            voltage_domains={"dc_bus": VoltageDomain.DC_BUS, "gnd": VoltageDomain.LV_CONTROL},
            timeout_ms=10_000,
            seed=0,
            max_rounds=3,
            netlist=netlist,
            board=board,
        )
        assert len(report.rounds) <= 3
        assert report.status in ("gap", "max_rounds"), report.status
