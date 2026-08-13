"""Tests for ``temper-placer repair-unplaced`` (packages/temper-placer/src/
temper_placer/cli/repair_commands.py).

Three groups:

1. ``TestPlanBuilding`` -- pure unit tests for ``_build_plan`` /
   ``_frozen_positions`` / ``_rot_idx``: the free/displace/frozen
   partitioning and the fail-closed validation (unknown refs, refs named in
   both ``--refs`` and ``--displace``).
2. ``TestFixedCopperBites`` -- the explicit falsifier this module's task
   requires: a synthetic board where a naive courtyard-only placer WOULD
   accept a placement that actually lands on a live, different-net routed
   trace, proving (a) the naive/courtyard-only placement really is accepted
   absent ``fixed_copper`` (so the scenario is not vacuously already
   infeasible), (b) adding ``fixed_copper`` correctly turns it infeasible
   with an unsat core naming the ``fixed_copper_`` assumption, and (c)
   allowing exactly one neighbour to move (the same composition
   ``repair_unplaced``'s Phase 2 uses: ``fixed_positions`` for everyone
   else, ``minimize_displacement_to`` + ``max_displacement_mm`` +
   ``fixed_rotations`` for the mover) finds a legal, copper-clear placement
   with a small, non-zero, reported displacement -- the "minimum
   displacement" repair this command exists for. This exercises the exact
   constraint composition ``repair_unplaced`` builds, via ``solve_placement``
   directly (no CLI/file-IO layer), so it stays fast and hermetic.
3. ``TestSpuriousUnsatFromUnrelatedViolationsRegression`` -- pins the
   PR #1158 control-test finding: a placement request for an entirely
   uninvolved component must not be affected by unrelated pre-existing
   violations elsewhere on the board (two frozen components that violate
   courtyard clearance with EACH OTHER, and a frozen component whose real
   position sits outside the solver's representable coordinate domain).
   Proves the unfiltered composition IS spuriously infeasible (falsifier,
   not vacuous) and that ``auto_pairwise_touch_refs`` fixes it, including
   via the actual ``repair_unplaced`` plan-building helpers.
4. ``TestCliSmoke`` -- CliRunner-level checks that don't need a real
   CP-SAT solve: ``--help`` exits 0, and refusing to write to the tracked
   board / unknown refs fail loudly with a non-zero exit before any solve
   is attempted.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from temper_placer.cli import main as cli_main
from temper_placer.cli.repair_commands import _build_plan, _frozen_positions, _rot_idx
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io._kicad_types import TraceData
from temper_placer.placer.cp_sat._encoder_solve import solve_placement


# ---------------------------------------------------------------------------
# Group 1: plan building (pure, no solver)
# ---------------------------------------------------------------------------


class TestPlanBuilding:
    def test_partitions_free_displace_frozen(self) -> None:
        plan = _build_plan({"A", "B", "C", "D"}, {"A"}, {"B"})
        assert plan.free_refs == {"A"}
        assert plan.displace_refs == {"B"}
        assert plan.frozen_refs == {"C", "D"}
        assert plan.touch_set == {"A", "B"}

    def test_unknown_free_ref_rejected(self) -> None:
        with pytest.raises(click.ClickException, match="unknown component"):
            _build_plan({"A", "B"}, {"Z"}, set())

    def test_unknown_displace_ref_rejected(self) -> None:
        with pytest.raises(click.ClickException, match="unknown component"):
            _build_plan({"A", "B"}, {"A"}, {"Z"})

    def test_ref_in_both_refs_and_displace_rejected(self) -> None:
        with pytest.raises(click.ClickException, match="both --refs and --displace"):
            _build_plan({"A", "B"}, {"A"}, {"A"})

    def test_rot_idx_is_a_safe_no_op_on_an_already_quadrant_index(self) -> None:
        """``Component.initial_rotation`` is ALREADY the 0-3 quadrant index
        (quantized at parse time by ``io/_parse_modules.py``), never
        degrees -- confirmed on the real board (only values {0,1,2,3}
        occur across all 168 components). ``_rot_idx`` must be a
        normalizing no-op on that input, not divide by 90 (a real,
        previously-shipped bug: ``round(1/90) % 4 == 0`` silently forced
        the rotation of every non-zero-rotated frozen/displaced ref to 0)."""
        assert _rot_idx(None) == 0
        assert _rot_idx(0) == 0
        assert _rot_idx(1) == 1
        assert _rot_idx(2) == 2
        assert _rot_idx(3) == 3
        assert _rot_idx(4) == 0  # tolerates an out-of-range value via mod 4

    def test_frozen_positions_reads_current_board_position(self) -> None:
        comp = Component(
            ref="U1",
            footprint="t",
            bounds=(2.0, 2.0),
            pins=[],
            initial_position=(12.5, 7.25),
            initial_rotation=1,  # already a quadrant index, not degrees
        )
        out = _frozen_positions({"U1": comp}, {"U1"})
        assert out == {"U1": (12.5, 7.25, 1)}

    def test_frozen_positions_fails_loud_on_missing_position(self) -> None:
        comp = Component(
            ref="U1", footprint="t", bounds=(2.0, 2.0), pins=[], initial_position=None,
            initial_rotation=0,
        )
        with pytest.raises(click.ClickException, match="no board position"):
            _frozen_positions({"U1": comp}, {"U1"})


# ---------------------------------------------------------------------------
# Group 2: the fixed-copper falsifier + minimum-displacement repair
# ---------------------------------------------------------------------------


def _comp(ref: str, bounds: tuple[float, float], pos: tuple[float, float], net: str) -> Component:
    w, h = bounds
    pins = [
        Pin(
            name="1", number="1", position=(0.0, 0.0), net=net, width=w, height=h,
            shape="rect", layer="all", is_pth=True,
        )
    ]
    return Component(
        ref=ref, footprint="t", bounds=bounds, pins=pins, initial_position=pos,
        initial_rotation=0,
    )


@pytest.fixture
def copper_maze():
    """A hand-engineered 80x4mm board, wide enough for exactly one free
    component (U1, 2x2mm) to slot in, that a courtyard-only search would
    place directly on top of live copper -- and where the ONLY legal
    alternative requires nudging one neighbour (OBST_RIGHT) sideways.

    Layout (mm, board frame, board width 80 x height 4, edge margin 0.5):

        x:  0.5      20.5  20    43         44        64  64        79  79.5
            |OBST_LEFT|    |--TR1(NET_B)--|  |OBST_RIGHT|  |--TR2(NET_C)--|
                            (blocks the      (44-64, courtyard-             (blocks the
                             0.5mm sliver     blocks U1                     ~0.5mm sliver
                             left of it)      regardless of                 right of it)
                                              copper)

    Every square millimetre of the board is covered by either a courtyard
    obstacle or a different-net trace -- courtyard-only geometry (ignoring
    copper) is NOT similarly blocked at TR1/TR2, which is exactly the gap
    this module's machinery closes. OBST_RIGHT's own pin sits on NET_C
    (matching TR2), so once OBST_RIGHT itself becomes a free/displaceable
    ref, TR2 is exempt for its OWN pads (the same-net skip rule) even
    though it still blocks U1 (a different net).
    """
    u1 = _comp("U1", (2.0, 2.0), (30.0, 2.0), "NET_U1")
    obst_left = _comp("OBST_LEFT", (20.0, 2.8), (10.5, 2.0), "NET_A")
    obst_right = _comp("OBST_RIGHT", (20.0, 2.8), (54.0, 2.0), "NET_C")
    comps = [u1, obst_left, obst_right]
    netlist = Netlist(
        components=comps,
        nets=[
            Net(name="NET_U1", pins=[("U1", "1")]),
            Net(name="NET_A", pins=[("OBST_LEFT", "1")]),
            Net(name="NET_C", pins=[("OBST_RIGHT", "1")]),
        ],
    )
    board = Board(width=80.0, height=4.0, origin=(0.0, 0.0), zones=[])
    tr1 = TraceData(start=(20.0, 2.0), end=(43.0, 2.0), width=1.0, layer="F.Cu", net="NET_B")
    tr2 = TraceData(start=(64.0, 2.0), end=(79.0, 2.0), width=1.0, layer="F.Cu", net="NET_C")
    parse_result = SimpleNamespace(traces=[tr1, tr2], vias=[], board=board)
    return SimpleNamespace(netlist=netlist, board=board, comps={c.ref: c for c in comps}, parse_result=parse_result)


class TestFixedCopperBites:
    def test_naive_courtyard_only_placer_accepts_the_bad_spot(self, copper_maze) -> None:
        """Precondition check: without fixed_copper, a courtyard-only solve
        (everyone but U1 frozen at their current board position) finds SOME
        legal placement for U1 -- proving the scenario is not vacuously
        already infeasible before fixed_copper is even in the picture."""
        cm = copper_maze
        fixed_positions = {
            ref: (c.initial_position[0], c.initial_position[1], 0)
            for ref, c in cm.comps.items()
            if ref != "U1"
        }
        result = solve_placement(
            netlist=cm.netlist, board=cm.board, timeout_ms=10_000, fixed_positions=fixed_positions
        )
        assert result.status in ("optimal", "feasible")
        assert "U1" in result.positions

    def test_fixed_copper_correctly_refuses_the_same_scenario(self, copper_maze) -> None:
        """Same frozen neighbourhood, same board -- WITH fixed_copper wired
        in (repair_unplaced's Phase 1 composition), the solve must be
        infeasible, and the unsat core must name the fixed_copper family so
        a caller can tell which constraint blocked it."""
        cm = copper_maze
        fixed_positions = {
            ref: (c.initial_position[0], c.initial_position[1], 0)
            for ref, c in cm.comps.items()
            if ref != "U1"
        }
        fixed_copper = {"parse_result": cm.parse_result, "free_refs": {"U1"}, "margin_mm": 0.05}
        result = solve_placement(
            netlist=cm.netlist, board=cm.board, timeout_ms=10_000,
            fixed_positions=fixed_positions, fixed_copper=fixed_copper,
        )
        assert result.status == "infeasible"
        names = [u.get("name", "") for u in result.unsat_core]
        assert any(n.startswith("fixed_copper_") for n in names), (
            f"expected the fixed_copper assumption to be named in the unsat core, got {names}"
        )

    def test_minimum_displacement_repair_finds_the_legal_slot(self, copper_maze) -> None:
        """Phase 2's exact composition: freeze everyone except U1 (free) and
        OBST_RIGHT (displaceable, translation-only, bounded), with fixed_copper
        armed for both. Must find a feasible placement, and OBST_RIGHT's
        reported displacement must be small (well under the 15mm bound --
        this is a MINIMUM-displacement repair, not just "some" repair) and
        strictly positive (it actually had to move)."""
        cm = copper_maze
        frozen = {
            ref: (c.initial_position[0], c.initial_position[1], 0)
            for ref, c in cm.comps.items()
            if ref not in ("U1", "OBST_RIGHT")
        }
        obst_right0 = cm.comps["OBST_RIGHT"].initial_position
        fixed_copper = {
            "parse_result": cm.parse_result,
            "free_refs": {"U1", "OBST_RIGHT"},
            "margin_mm": 0.05,
        }
        result = solve_placement(
            netlist=cm.netlist, board=cm.board, timeout_ms=10_000,
            fixed_positions=frozen,
            minimize_displacement_to={"OBST_RIGHT": obst_right0},
            max_displacement_mm=15.0,
            fixed_rotations={"OBST_RIGHT": 0},
            fixed_copper=fixed_copper,
        )
        assert result.status in ("optimal", "feasible"), result.unsat_core
        assert "U1" in result.positions

        ox, oy = obst_right0
        nx, ny = result.positions["OBST_RIGHT"]
        displacement = abs(nx - ox) + abs(ny - oy)
        assert 0.0 < displacement <= 15.0, (
            f"OBST_RIGHT displacement {displacement}mm should be positive (it had to "
            "move) and within the 15mm bound"
        )
        # A real "minimum" displacement repair should not need to use the
        # whole budget -- the legal slot is close to OBST_RIGHT's own
        # original footprint width (20mm), well under the 15mm cap.
        assert displacement < 10.0, (
            f"displacement {displacement}mm is suspiciously large for a minimum-"
            "displacement objective on this scenario"
        )

        # solve_placement() itself already re-verified this: audit_fixed_copper
        # runs automatically whenever fixed_copper= is passed and the solve is
        # feasible/optimal (against the ACTUAL resolved positions, including
        # OBST_RIGHT's new one -- unlike a hand-rolled re-check here, which
        # would need to know to re-point OBST_RIGHT's obstacle geometry at its
        # solved position rather than its stale pre-solve one). A violation
        # there raises RuntimeError, which would have failed this test at the
        # solve_placement() call above -- reaching this line is itself the
        # proof that every U1 pad clears both traces by at least the margin.


# ---------------------------------------------------------------------------
# Group 3: spurious-UNSAT-from-unrelated-violations regression (PR #1158
# control-test finding, 2026-08-13)
# ---------------------------------------------------------------------------
#
# A control test on a completely uninvolved component (an "R75") against the
# real board returned UNSAT purely because SOME OTHER frozen, unrelated pair
# of components already violated courtyard clearance with EACH OTHER (48
# such pairs measured on pcb/temper.kicad_pcb) or because some OTHER frozen
# component's real position sat outside the solver's representable
# coordinate domain (22 components measured; 12 of those hit the CP-SAT
# variable's hard >=0 floor, not just the softer edge-margin assumption).
# Both are real, separately-tracked, pre-existing board conditions that have
# nothing to do with what a caller is actually trying to place -- the fix is
# `auto_pairwise_touch_refs` (restricting every auto-generated pairwise
# constraint family -- courtyard, netclass, the redundant NoOverlap2D, and
# per-component edge-margin -- to pairs touching the free/displaceable set)
# plus `_frozen_positions`'s clamp for the hard variable-domain floor. This
# group pins the "uninvolved placement request is unaffected by unrelated
# pre-existing violations elsewhere on the board" property directly.


class TestSpuriousUnsatFromUnrelatedViolationsRegression:
    @pytest.fixture
    def messy_board(self):
        """A synthetic board carrying BOTH discovered pre-existing-defect
        shapes, deliberately unrelated to TARGET:

        - BAD_A / BAD_B: two frozen components whose courtyard boxes
          genuinely overlap each other (mirrors the real board's 48
          courtyard-violating pairs).
        - EDGE: a frozen component whose real position implies a negative
          courtyard start coordinate (mirrors the real board's 12
          components that hit the CP-SAT variable's hard >=0 domain floor,
          e.g. C18 at x_start=-0.24mm).

        TARGET has ample legal room elsewhere on the board, entirely clear
        of all three.
        """

        def comp(ref, bounds, pos, net):
            w, h = bounds
            pins = [
                Pin(
                    name="1", number="1", position=(0.0, 0.0), net=net, width=w, height=h,
                    shape="rect", layer="all", is_pth=True,
                )
            ]
            return Component(
                ref=ref, footprint="t", bounds=bounds, pins=pins, initial_position=pos,
                initial_rotation=0,
            )

        target = comp("TARGET", (4.0, 4.0), (50.0, 10.0), "NET_T")
        bad_a = comp("BAD_A", (10.0, 10.0), (10.0, 10.0), "NET_A")
        bad_b = comp("BAD_B", (10.0, 10.0), (12.0, 10.0), "NET_B")  # overlaps BAD_A
        edge = comp("EDGE", (4.0, 4.0), (1.0, 1.0), "NET_E")  # implies x_start = -1.0

        comps = [target, bad_a, bad_b, edge]
        netlist = Netlist(
            components=comps,
            nets=[Net(name=c.pins[0].net, pins=[(c.ref, "1")]) for c in comps],
        )
        board = Board(width=100.0, height=20.0, origin=(0.0, 0.0), zones=[])
        return SimpleNamespace(
            netlist=netlist, board=board, comp_by_ref={c.ref: c for c in comps}
        )

    def test_unrelated_violations_do_cause_spurious_unsat_unfiltered(self, messy_board) -> None:
        """Precondition: WITHOUT auto_pairwise_touch_refs (the pre-fix
        default), freezing BAD_A/BAD_B/EDGE at their real positions makes a
        request for the entirely-uninvolved TARGET infeasible -- proving
        the scenario is a real falsifier, not a vacuous one."""
        mb = messy_board
        frozen = _frozen_positions(mb.comp_by_ref, {"BAD_A", "BAD_B", "EDGE"})
        result = solve_placement(
            netlist=mb.netlist, board=mb.board, timeout_ms=5000, fixed_positions=frozen
        )
        assert result.status == "infeasible", (
            "expected the unfiltered composition to reproduce the spurious UNSAT "
            f"(got {result.status}) -- the regression scenario itself may be stale"
        )

    def test_uninvolved_placement_request_is_unaffected_when_filtered(self, messy_board) -> None:
        """The fix: with auto_pairwise_touch_refs={TARGET} (repair_unplaced's
        actual composition for a free ref), the same frozen neighbourhood no
        longer blocks TARGET -- an uninvolved component's placement request
        must not be affected by unrelated pre-existing violations elsewhere
        on the board."""
        mb = messy_board
        frozen = _frozen_positions(mb.comp_by_ref, {"BAD_A", "BAD_B", "EDGE"})
        result = solve_placement(
            netlist=mb.netlist,
            board=mb.board,
            timeout_ms=5000,
            fixed_positions=frozen,
            auto_pairwise_touch_refs={"TARGET"},
        )
        assert result.status in ("optimal", "feasible"), (
            f"uninvolved TARGET placement request returned {result.status}, blocked by "
            "unrelated pre-existing violations elsewhere on the board"
        )
        assert "TARGET" in result.positions

    def test_repair_unplaced_cli_composes_the_filter_by_default(self, messy_board, tmp_path: Path) -> None:
        """End-to-end: the actual CLI plan-building helpers (not a hand-rolled
        stand-in) produce a touch_set that, when threaded through
        solve_placement exactly as repair_unplaced's Phase 1 does, is
        unaffected by BAD_A/BAD_B/EDGE. Exercises `_build_plan` +
        `_frozen_positions` + the `auto_pairwise_touch_refs` wiring together,
        the same call shape `repair_unplaced` itself uses for Phase 1."""
        mb = messy_board
        all_refs = set(mb.comp_by_ref)
        plan = _build_plan(all_refs, {"TARGET"}, set())
        fixed_positions = _frozen_positions(mb.comp_by_ref, plan.frozen_refs)
        result = solve_placement(
            netlist=mb.netlist,
            board=mb.board,
            timeout_ms=5000,
            fixed_positions=fixed_positions,
            auto_pairwise_touch_refs=plan.touch_set,
        )
        assert result.status in ("optimal", "feasible")
        assert "TARGET" in result.positions


# ---------------------------------------------------------------------------
# Group 4: CLI smoke tests (no solver invoked)
# ---------------------------------------------------------------------------


class TestCliSmoke:
    def test_help_exits_zero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli_main, ["repair-unplaced", "--help"])
        assert result.exit_code == 0
        assert "repair-unplaced" in result.output or "Usage" in result.output

    def test_refuses_to_write_tracked_board(self, tmp_path: Path, monkeypatch) -> None:
        """If --output resolves to the tracked pcb/temper.kicad_pcb, refuse
        before doing any work (hard constraint: never touch the tracked
        board)."""
        fake_repo_pcb = tmp_path / "pcb" / "temper.kicad_pcb"
        fake_repo_pcb.parent.mkdir(parents=True)
        fake_repo_pcb.write_text("(kicad_pcb)", encoding="utf-8")

        import temper_placer.cli.repair_commands as rc

        monkeypatch.setattr(rc, "_find_repo_file", lambda rel: fake_repo_pcb if rel == "pcb/temper.kicad_pcb" else None)

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "repair-unplaced",
                str(fake_repo_pcb),
                "--refs",
                "U1",
                "-o",
                str(fake_repo_pcb),
            ],
        )
        assert result.exit_code != 0
        assert "tracked board" in result.output

    def test_unknown_ref_fails_before_solving(self, tmp_path: Path) -> None:
        """A tiny but real, parseable board -- an unknown --refs name must
        fail loudly (ClickException) rather than silently solving nothing."""
        pytest.importorskip("temper_design_bundle_python")
        fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
        minimal_pcb = fixtures_dir / "minimal_board.kicad_pcb"
        if not minimal_pcb.exists():
            pytest.skip("minimal_board.kicad_pcb fixture not present")

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "repair-unplaced",
                str(minimal_pcb),
                "--refs",
                "THIS_REF_DOES_NOT_EXIST",
                "-o",
                str(tmp_path / "candidate.kicad_pcb"),
                "--no-domain-clearance",
                "--no-isolation-barrier",
            ],
        )
        assert result.exit_code != 0
        assert "unknown component" in result.output
