"""Tests for the F.Fab body-collision fail-closed post-solve audit
(placer/cp_sat/body_collision.py).

This is the guard PR ``fix/placer-fail-closed-collision-guard`` adds so a
placement with a real physical body collision -- like the 7.73mm C2xC3
interpenetration commit ``de59c0458``/PR #602 put on the board, or the
9.47mm collision PR #1168 reproduced live from a relaxed re-solve -- fails
at the point it is produced (``solve_placement``), not three steps
downstream as an opaque ``courtyards_overlap`` ratchet number.

Test groups:

1. ``TestAllowlist`` -- ``load_body_collision_allowlist`` parsing and its
   fail-loud contracts (missing file, missing key, duplicate pair).
2. ``TestAuditBodyCollisions`` -- ``audit_body_collisions`` unit-level: new
   collision, allowlisted-clean, allowlisted-but-worsened, bodies-clear
   (the courtyard-only-touch case), refs excluded for missing geometry,
   and the bbox broad-phase not missing a real pair.
3. ``TestSolvePlacementBites`` -- the task brief's proof requirement,
   through the real ``solve_placement`` chokepoint: (a) a placement whose
   solver-box model is satisfied but whose TRUE F.Fab bodies collide (the
   exact class of defect this guard exists for -- the solver's own box
   size does not carry the real body envelope) is rejected with
   ``RuntimeError``; (b) the real board's own benign courtyard-only-touch
   pair (``C3``x``K3``, measured 0.39mm real body clearance) is pinned at
   its exact committed coordinates and passes cleanly.
4. ``TestSolvePlacementWiringContract`` -- absent ``body_collision_input``
   leaves the audit ``None`` (byte-identical to pre-wiring); missing
   ``fab_bodies``/``allowlist`` keys raise ``ValueError``; a non-optimal
   solve logs a WARNING skip, never silent.
5. ``TestProductionBoardAllowlistCoverage`` -- the real, committed board
   against the real, checked-in allowlist: exactly the 6 known real body
   collisions are allowlisted-clean, and the 2 benign courtyard-only pairs
   never appear in either bucket (their bodies are clear).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from temper_placer.core.fab_body import FabBody
from temper_placer.placer.cp_sat._encoder_solve import solve_placement
from temper_placer.placer.cp_sat.body_collision import (
    EMPTY_ALLOWLIST,
    BodyCollisionAllowlist,
    BodyCollisionAllowlistEntry,
    audit_body_collisions,
    load_body_collision_allowlist,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_ALLOWLIST_PATH = (
    _REPO_ROOT / "packages" / "temper-placer" / "configs" / "body_collision_allowlist.yaml"
)


# ---------------------------------------------------------------------------
# Synthetic netlist/board helpers (same minimal shape used throughout the
# placer/cp_sat test suite -- see test_validator_audit.py).
# ---------------------------------------------------------------------------


@dataclass
class MockComp:
    ref: str
    bounds: tuple[float, float] = (0.1, 0.1)
    initial_position: tuple[float, float] = (0.0, 0.0)
    initial_rotation: int = 0
    pins: list = field(default_factory=list)
    zone: str | None = None
    attributes: dict = field(default_factory=dict)


@dataclass
class MockNetlist:
    components: list
    nets: list = field(default_factory=list)


@dataclass
class MockBoard:
    width: float = 152.0
    height: float = 234.0
    zones: list = field(default_factory=list)
    origin: tuple[float, float] = (0.0, 0.0)
    constraints: list = field(default_factory=list)


def _circle_points(radius: float, n: int = 24) -> list[tuple[float, float]]:
    return [
        (radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def _square_body(ref: str, half: float = 1.0) -> FabBody:
    return FabBody(
        component_ref=ref,
        points=[(-half, -half), (half, -half), (half, half), (-half, half)],
    )


# ---------------------------------------------------------------------------
# Group 1: allowlist loading
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_load_real_allowlist(self) -> None:
        allowlist = load_body_collision_allowlist(_ALLOWLIST_PATH)
        # PR #1158 measured 6 real body collisions. Five have since been
        # fixed on the board and were pruned from the allowlist on
        # 2026-08-25 -- C5<->C7 (106.8341mm^2) by #1498's C7 move, which is
        # the fix that entry's own note described as "not yet applied", plus
        # C5<->L1 (10.3219), C4<->R46 (5.1200), C4<->C22 (1.2800) and
        # C4<->R4 (0.0306). Re-measured with an emptied allowlist, C2<->C3
        # is the only real body overlap left on this board.
        #
        # Pruning is a ratchet: a dead entry would silently re-accept its
        # overlap if it ever came back, whereas with the entry gone the
        # return is a NEW violation and fails the gate.
        expected_pairs = {frozenset(("C2", "C3"))}
        assert set(allowlist.entries.keys()) == expected_pairs
        assert len(allowlist) == 1
        entry = allowlist.get("C2", "C3")
        assert entry is not None
        assert entry.baseline_overlap_mm2 == pytest.approx(115.6512, abs=1e-3)
        # Order-independence.
        assert allowlist.get("C3", "C2") is entry

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_body_collision_allowlist(tmp_path / "does_not_exist.yaml")

    def test_missing_required_key_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("pairs:\n  - a: X\n    b: Y\n")  # no baseline_overlap_mm2
        with pytest.raises(ValueError, match="missing required key"):
            load_body_collision_allowlist(p)

    def test_duplicate_pair_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "dup.yaml"
        p.write_text(
            "pairs:\n"
            "  - a: X\n    b: Y\n    baseline_overlap_mm2: 1.0\n"
            "  - a: Y\n    b: X\n    baseline_overlap_mm2: 2.0\n"
        )
        with pytest.raises(ValueError, match="more than once"):
            load_body_collision_allowlist(p)


# ---------------------------------------------------------------------------
# Group 2: audit_body_collisions unit-level
# ---------------------------------------------------------------------------


class TestAuditBodyCollisions:
    def test_new_collision_not_on_allowlist_is_a_violation(self) -> None:
        bodies = {"A": _square_body("A"), "B": _square_body("B")}
        positions = {"A": (0.0, 0.0), "B": (0.5, 0.0)}  # 1x1 boxes, 0.5mm apart -> overlap
        rotations = {"A": 0, "B": 0}
        result = audit_body_collisions(bodies, positions, rotations, EMPTY_ALLOWLIST)
        assert not result.clean
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.kind == "new"
        assert {v.ref_a, v.ref_b} == {"A", "B"}
        assert v.overlap_mm2 > 0

    def test_bodies_clear_is_never_a_violation_even_unallowlisted(self) -> None:
        """The courtyard-only-touch case: real bodies do not overlap at
        all. Must never fire, allowlisted or not."""
        bodies = {"A": _square_body("A"), "B": _square_body("B")}
        positions = {"A": (0.0, 0.0), "B": (5.0, 0.0)}  # 1x1 boxes, clear by 3mm
        rotations = {"A": 0, "B": 0}
        result = audit_body_collisions(bodies, positions, rotations, EMPTY_ALLOWLIST)
        assert result.clean
        assert result.violations == []
        assert result.allowlisted == []

    def test_allowlisted_pair_at_or_below_baseline_is_clean(self) -> None:
        bodies = {"A": _square_body("A"), "B": _square_body("B")}
        positions = {"A": (0.0, 0.0), "B": (0.5, 0.0)}
        rotations = {"A": 0, "B": 0}
        # Measure the true overlap first so the allowlist baseline is
        # honest (>=), matching how the real allowlist was seeded.
        measured = audit_body_collisions(bodies, positions, rotations, EMPTY_ALLOWLIST)
        area = measured.violations[0].overlap_mm2
        allowlist = BodyCollisionAllowlist(
            entries={frozenset(("A", "B")): BodyCollisionAllowlistEntry("A", "B", area)}
        )
        result = audit_body_collisions(bodies, positions, rotations, allowlist)
        assert result.clean
        assert result.violations == []
        assert len(result.allowlisted) == 1
        assert result.allowlisted[0].overlap_mm2 == pytest.approx(area)

    def test_allowlisted_pair_worse_than_baseline_is_a_violation(self) -> None:
        """The #1168 failure mode: a pair already on the allowlist gets
        WORSE, not just a brand-new pair appearing. Must still fire."""
        bodies = {"A": _square_body("A"), "B": _square_body("B")}
        positions = {"A": (0.0, 0.0), "B": (0.5, 0.0)}
        rotations = {"A": 0, "B": 0}
        # Allowlist a much smaller baseline than what these positions
        # actually produce.
        allowlist = BodyCollisionAllowlist(
            entries={frozenset(("A", "B")): BodyCollisionAllowlistEntry("A", "B", 0.01)}
        )
        result = audit_body_collisions(bodies, positions, rotations, allowlist)
        assert not result.clean
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.kind == "worsened"
        assert v.baseline_overlap_mm2 == pytest.approx(0.01)
        assert v.overlap_mm2 > v.baseline_overlap_mm2

    def test_refs_without_geometry_are_excluded_not_treated_as_clear(self) -> None:
        bodies = {"A": _square_body("A")}  # B has no geometry
        positions = {"A": (0.0, 0.0), "B": (0.0, 0.0)}
        rotations = {"A": 0, "B": 0}
        result = audit_body_collisions(bodies, positions, rotations, EMPTY_ALLOWLIST)
        assert result.checked_pairs == 0
        assert result.refs_without_geometry == ["B"]
        assert result.clean  # nothing WAS checked -- not proof of safety, just no opinion

    def test_bbox_broad_phase_does_not_miss_a_real_collision(self) -> None:
        """Three components: A/B far apart and clear, B/C overlapping.
        Confirms the cheap bounding-box pre-filter used for performance does
        not accidentally skip a pair whose bodies really do intersect."""
        bodies = {"A": _square_body("A"), "B": _square_body("B"), "C": _square_body("C")}
        positions = {"A": (0.0, 0.0), "B": (100.0, 0.0), "C": (100.5, 0.0)}
        rotations = {"A": 0, "B": 0, "C": 0}
        result = audit_body_collisions(bodies, positions, rotations, EMPTY_ALLOWLIST)
        assert len(result.violations) == 1
        v = result.violations[0]
        assert {v.ref_a, v.ref_b} == {"B", "C"}


# ---------------------------------------------------------------------------
# Group 3: proof through the real chokepoint (task brief item 5)
# ---------------------------------------------------------------------------


class TestSolvePlacementBites:
    def test_new_body_collision_rejects_a_solve_the_box_model_missed(self) -> None:
        """The exact defect class this guard exists for: the solver's own
        box model (``comp.bounds``) is small enough that CP-SAT's own
        courtyard/no-overlap machinery is fully satisfied (status
        optimal/feasible) -- but the TRUE F.Fab body geometry (much larger
        than the declared box, e.g. because ``comp.bounds`` does not carry
        the real footprint envelope -- PR #1158 section 3.3's open
        hypothesis for how C2xC3 happened) collides badly. The guard must
        still reject it."""
        comps = [
            MockComp(ref="P", bounds=(0.1, 0.1), initial_position=(50.0, 50.0)),
            MockComp(ref="Q", bounds=(0.1, 0.1), initial_position=(51.0, 50.0)),
        ]
        netlist = MockNetlist(components=comps)
        board = MockBoard()
        fab_bodies = {
            "P": FabBody(component_ref="P", points=_circle_points(radius=3.0)),
            "Q": FabBody(component_ref="Q", points=_circle_points(radius=3.0)),
        }

        with pytest.raises(RuntimeError, match="physically unassemblable"):
            solve_placement(
                netlist=netlist,
                board=board,
                timeout_ms=20_000,
                seed=0,
                fixed_positions={"P": (50.0, 50.0, 0), "Q": (51.0, 50.0, 0)},
                body_collision_input={"fab_bodies": fab_bodies, "allowlist": EMPTY_ALLOWLIST},
            )

    @pytest.mark.skipif(not _PCB_PATH.exists(), reason="real board not present")
    def test_benign_courtyard_touch_on_the_real_board_passes(self) -> None:
        """C3xK3: one of the board's 8 tracked ``courtyards_overlap``
        pairs, but F.Fab bodies clear by a measured 0.39mm (PR #1158 sec
        2.2, reproduced independently in test_fab_body_extraction.py).
        Pinned at their EXACT committed board coordinates through the real
        ``solve_placement`` chokepoint, this must pass cleanly."""
        from kiutils.board import Board

        from temper_placer.io.fab_body_extraction import extract_fab_bodies

        kboard = Board.from_file(str(_PCB_PATH))
        raw_pos: dict[str, tuple[float, float]] = {}
        raw_rot: dict[str, int] = {}
        for fp in kboard.footprints:
            ref = fp.properties.get("Reference") if isinstance(fp.properties, dict) else None
            if ref in ("C3", "K3"):
                angle = fp.position.angle or 0
                raw_pos[ref] = (fp.position.X, fp.position.Y)
                raw_rot[ref] = int(angle // 90) % 4

        all_bodies = extract_fab_bodies(_PCB_PATH)
        fab_bodies = {ref: all_bodies[ref] for ref in ("C3", "K3")}

        comps = [
            MockComp(ref=ref, bounds=(0.1, 0.1), initial_position=raw_pos[ref])
            for ref in ("C3", "K3")
        ]
        netlist = MockNetlist(components=comps)
        board = MockBoard()
        fixed_positions = {
            ref: (raw_pos[ref][0], raw_pos[ref][1], raw_rot[ref]) for ref in ("C3", "K3")
        }

        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=20_000,
            seed=0,
            fixed_positions=fixed_positions,
            body_collision_input={"fab_bodies": fab_bodies, "allowlist": EMPTY_ALLOWLIST},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.body_collision_audit is not None
        assert result.body_collision_audit.clean, result.body_collision_audit.report()


# ---------------------------------------------------------------------------
# Group 4: wiring contract (mirrors TestSolvePlacementIntegration in
# test_validator_audit.py)
# ---------------------------------------------------------------------------


class TestSolvePlacementWiringContract:
    def _inputs(self) -> tuple[MockNetlist, MockBoard, dict]:
        comps = [
            MockComp(ref="A", bounds=(4.0, 4.0), initial_position=(10.0, 10.0)),
            MockComp(ref="B", bounds=(4.0, 4.0), initial_position=(30.0, 10.0)),
        ]
        netlist = MockNetlist(components=comps)
        board = MockBoard()
        fab_bodies = {"A": _square_body("A"), "B": _square_body("B")}
        return netlist, board, fab_bodies

    def test_absent_input_leaves_audit_none(self) -> None:
        netlist, board, _bodies = self._inputs()
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=20_000,
            seed=0,
            fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.body_collision_audit is None

    def test_feasible_clean_solve_populates_audit(self) -> None:
        netlist, board, fab_bodies = self._inputs()
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=20_000,
            seed=0,
            fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
            body_collision_input={"fab_bodies": fab_bodies, "allowlist": EMPTY_ALLOWLIST},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.body_collision_audit is not None
        assert result.body_collision_audit.clean

    def test_missing_fab_bodies_key_raises_value_error(self) -> None:
        netlist, board, _bodies = self._inputs()
        with pytest.raises(ValueError, match="body_collision_input must carry both"):
            solve_placement(
                netlist=netlist,
                board=board,
                timeout_ms=20_000,
                seed=0,
                fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
                body_collision_input={"allowlist": EMPTY_ALLOWLIST},
            )

    def test_missing_allowlist_key_raises_value_error(self) -> None:
        netlist, board, fab_bodies = self._inputs()
        with pytest.raises(ValueError, match="body_collision_input must carry both"):
            solve_placement(
                netlist=netlist,
                board=board,
                timeout_ms=20_000,
                seed=0,
                fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
                body_collision_input={"fab_bodies": fab_bodies},
            )

    def test_non_optimal_solve_logs_audit_skip_warning(self, caplog) -> None:
        netlist, board, fab_bodies = self._inputs()
        with caplog.at_level(logging.WARNING, logger="temper_placer.placer.cp_sat._encoder_solve"):
            result = solve_placement(
                netlist=netlist,
                board=board,
                timeout_ms=5_000,
                seed=0,
                fixed_positions={"A": (999.0, 999.0, 0), "B": (999.0, 999.0, 0)},
                body_collision_input={"fab_bodies": fab_bodies, "allowlist": EMPTY_ALLOWLIST},
            )
        assert result.status == "infeasible", result.status
        assert result.body_collision_audit is None
        assert any(
            "body-collision post-solve audit did NOT run" in r.message
            and r.levelno == logging.WARNING
            for r in caplog.records
        ), [r.message for r in caplog.records]


# ---------------------------------------------------------------------------
# Group 5: the real, committed board against the real, checked-in allowlist
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PCB_PATH.exists(), reason="real board not present")
class TestProductionBoardAllowlistCoverage:
    def test_real_board_is_clean_against_the_real_allowlist(self) -> None:
        from kiutils.board import Board

        from temper_placer.io.fab_body_extraction import extract_fab_bodies

        kboard = Board.from_file(str(_PCB_PATH))
        positions: dict[str, tuple[float, float]] = {}
        rotations: dict[str, int] = {}
        for fp in kboard.footprints:
            ref = fp.properties.get("Reference") if isinstance(fp.properties, dict) else None
            if not ref:
                continue
            angle = fp.position.angle or 0
            positions[ref] = (fp.position.X, fp.position.Y)
            rotations[ref] = int(angle // 90) % 4

        fab_bodies = extract_fab_bodies(_PCB_PATH)
        allowlist = load_body_collision_allowlist(_ALLOWLIST_PATH)

        result = audit_body_collisions(fab_bodies, positions, rotations, allowlist)

        assert result.clean, result.report()
        # 1, not 6, since 2026-08-25. Five allowlist entries were pruned
        # because the overlaps they accepted no longer exist -- notably
        # C5<->C7 (106.8341mm^2), whose own note said "Verified single-part
        # fix exists (move C7 63.5mm) -- not yet applied", which #1498
        # applied. Re-measured with an emptied allowlist, C2<->C3 is the only
        # real body overlap left on this board. See the PRUNED block in
        # configs/body_collision_allowlist.yaml for the five figures.
        assert len(result.allowlisted) == 1, result.report()

        touched_refs = {frozenset((v.ref_a, v.ref_b)) for v in result.allowlisted}
        assert touched_refs == set(allowlist.entries.keys())

        # The 2 benign courtyard-only pairs must appear in NEITHER bucket --
        # their bodies are clear, so they are never even classified against
        # the allowlist.
        for pair in (frozenset(("C3", "K3")), frozenset(("C2", "PS1"))):
            assert pair not in touched_refs
            assert pair not in {frozenset((v.ref_a, v.ref_b)) for v in result.violations}
