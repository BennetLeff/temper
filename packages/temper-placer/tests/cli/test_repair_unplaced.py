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
3. ``TestCliSmoke`` -- CliRunner-level checks that don't need a real
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

    def test_rot_idx_snaps_degrees_to_quadrant(self) -> None:
        assert _rot_idx(None) == 0
        assert _rot_idx(0.0) == 0
        assert _rot_idx(90.0) == 1
        assert _rot_idx(180.0) == 2
        assert _rot_idx(270.0) == 3
        assert _rot_idx(360.0) == 0

    def test_frozen_positions_reads_current_board_position(self) -> None:
        comp = Component(
            ref="U1",
            footprint="t",
            bounds=(2.0, 2.0),
            pins=[],
            initial_position=(12.5, 7.25),
            initial_rotation=90,
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
# Group 3: CLI smoke tests (no solver invoked)
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
