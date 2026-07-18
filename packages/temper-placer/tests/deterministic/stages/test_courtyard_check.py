"""Regression test for CourtyardCheckStage's collision detection.

Covers the bug in docs/solutions/logic-errors/
courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md:
shapely>=2.0's STRtree.query() returns integer indices, not geometry
objects. The stage previously matched candidates back to their ref via
`if p is candidate_poly` (Python object identity against a Polygon vs. a
numpy.int64), which could never succeed -- every candidate was silently
skipped and the stage detected zero collisions on any board, regardless
of real overlaps. There was no direct test for this stage before this
file, which is exactly how a 100%-inert detector went unnoticed.
"""

from dataclasses import replace

from temper_placer.core.courtyard import Courtyard
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.courtyard_check import CourtyardCheckStage


def _square_courtyard(ref: str, half_size: float = 2.0) -> Courtyard:
    return Courtyard(
        component_ref=ref,
        points=[
            (-half_size, -half_size),
            (half_size, -half_size),
            (half_size, half_size),
            (-half_size, half_size),
        ],
    )


def test_find_collisions_detects_real_overlap():
    """Two components placed close enough that their courtyards overlap
    must be detected -- this is the exact scenario the STRtree index/
    identity bug made invisible."""
    stage = CourtyardCheckStage(
        courtyards={
            "R1": _square_courtyard("R1"),
            "R2": _square_courtyard("R2"),
        },
        board_width=100.0,
        board_height=100.0,
    )
    # 3mm apart with 2mm half-size courtyards (4mm wide each) -> genuinely overlapping
    placements = {"R1": (10.0, 10.0), "R2": (13.0, 10.0)}
    collisions = stage._find_collisions(placements)
    assert set(collisions) == {("R1", "R2")}, (
        f"expected R1/R2 to collide, got {collisions!r} -- if this is empty, "
        "the STRtree index-vs-identity bug has regressed"
    )


def test_find_collisions_ignores_non_overlapping():
    """Components far enough apart must NOT be reported as colliding."""
    stage = CourtyardCheckStage(
        courtyards={
            "R1": _square_courtyard("R1"),
            "R2": _square_courtyard("R2"),
        },
        board_width=100.0,
        board_height=100.0,
    )
    placements = {"R1": (10.0, 10.0), "R2": (50.0, 50.0)}
    collisions = stage._find_collisions(placements)
    assert collisions == []


def test_find_collisions_scales_beyond_two_components():
    """A larger set with one genuinely overlapping pair among several
    non-overlapping ones -- guards against an off-by-one in index
    resolution that only breaks past the trivial 2-component case."""
    stage = CourtyardCheckStage(
        courtyards={ref: _square_courtyard(ref) for ref in ["A", "B", "C", "D", "E"]},
        board_width=100.0,
        board_height=100.0,
    )
    placements = {
        "A": (10.0, 10.0),
        "B": (13.0, 10.0),  # overlaps A
        "C": (50.0, 10.0),
        "D": (80.0, 10.0),
        "E": (10.0, 80.0),
    }
    collisions = stage._find_collisions(placements)
    assert set(collisions) == {("A", "B")}


def test_run_resolves_a_real_collision_end_to_end():
    """Full stage.run() on a colliding pair must actually separate them --
    exercises the nudge loop on top of (now-working) detection."""
    stage = CourtyardCheckStage(
        courtyards={
            "R1": _square_courtyard("R1"),
            "R2": _square_courtyard("R2"),
        },
        board_width=100.0,
        board_height=100.0,
        max_iterations=200,
    )
    state = BoardState(
        placements=frozenset({"R1": (10.0, 10.0), "R2": (13.0, 10.0)}.items())
    )
    result = stage.run(state)
    final_collisions = stage._find_collisions(dict(result.placements))
    assert final_collisions == [], (
        f"stage.run() left unresolved collisions: {final_collisions!r}"
    )
