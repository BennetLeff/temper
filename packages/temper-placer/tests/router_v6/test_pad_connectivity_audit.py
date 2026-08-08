"""Tests for ``pad_connectivity_audit.py``.

This is the spike's correctness-verification deliverable: a check that a
net's emitted copper (segments + vias) actually joins its own pads, not
merely that copper with the right net number exists somewhere. The primary
scenario this suite must pin (``test_catches_b39b382d_fake_completion_shape``)
reconstructs the exact failure mode the codebase already rejected once: a
net's segments exist, carry the right net attribution, and would make a
naive "has copper" counter go up -- but they never touch the net's own
pads. See ``pad_connectivity_audit.py``'s module docstring for the full
b39b382d history and why this is not a hypothetical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.router_v6.pad_connectivity_audit import (
    ALL_LAYERS,
    CopperSegment,
    CopperVia,
    NetPad,
    audit_pcb_file,
    check_net_pad_connectivity,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# 1. The headline scenario: reconstruct b39b382d's rejected-predecessor
#    shape and prove the checker rejects it as fake completion.
# ---------------------------------------------------------------------------


def test_catches_b39b382d_fake_completion_shape():
    """Two F.Cu pads; the only emitted copper is a chain of segments
    entirely on In1.Cu that never touches either pad -- the documented
    shape of the *rejected* predecessor to b39b382d (a tree-route edge
    landing on a grid-backed-but-wrong layer). A naive "does this net have
    copper" check (a segment/via counter, or topology_copper_audit's own
    ``nets_carrying_copper`` applied without this module) would count this
    net as carrying copper. This check must not.
    """
    pads = [
        NetPad(position=(10.0, 10.0), layer="F.Cu", ref="U1.1"),
        NetPad(position=(50.0, 50.0), layer="F.Cu", ref="U2.3"),
    ]
    wrong_layer_segments = [
        CopperSegment(p1=(20.0, 20.0), p2=(30.0, 30.0), layer="In1.Cu"),
        CopperSegment(p1=(30.0, 30.0), p2=(40.0, 40.0), layer="In1.Cu"),
    ]

    result = check_net_pad_connectivity(
        "FAKE_NET", pads, wrong_layer_segments, [], all_layers=["F.Cu", "In1.Cu"]
    )

    assert result.has_any_copper is True, "the fake segments are real emitted copper"
    assert result.fully_connected is False, "neither pad is touched by the fake copper"
    assert result.pads_connected == 1, "each pad is its own isolated component"
    assert result.is_fake_completion is True, (
        "has_any_copper=True and fully_connected=False is exactly the "
        "b39b382d shape: completion appears to rise while nothing real "
        "connects"
    )
    assert {p.ref for p in result.unreached_pads} == {"U1.1", "U2.3"}


def test_real_connectivity_is_not_flagged_as_fake():
    """The positive control: a real route that actually reaches both pads
    on their own layer must NOT be flagged."""
    pads = [
        NetPad(position=(10.0, 10.0), layer="F.Cu", ref="U1.1"),
        NetPad(position=(50.0, 50.0), layer="F.Cu", ref="U2.3"),
    ]
    real_segments = [
        CopperSegment(p1=(10.0, 10.0), p2=(30.0, 30.0), layer="F.Cu"),
        CopperSegment(p1=(30.0, 30.0), p2=(50.0, 50.0), layer="F.Cu"),
    ]
    result = check_net_pad_connectivity("REAL_NET", pads, real_segments, [], all_layers=["F.Cu"])
    assert result.fully_connected is True
    assert result.is_fake_completion is False
    assert result.unreached_pads == ()


def test_via_correctly_joins_two_layers():
    """A pad on F.Cu and a pad on B.Cu, joined by an F.Cu segment + via +
    B.Cu segment, must be recognized as fully connected -- the checker
    must model a via as a real layer-spanning connection, not merely
    ignore layer entirely (which would silently paper over legality, not
    verify it)."""
    pads = [
        NetPad(position=(0.0, 0.0), layer="F.Cu", ref="U1.1"),
        NetPad(position=(20.0, 0.0), layer="B.Cu", ref="U2.1"),
    ]
    segments = [
        CopperSegment(p1=(0.0, 0.0), p2=(10.0, 0.0), layer="F.Cu"),
        CopperSegment(p1=(10.0, 0.0), p2=(20.0, 0.0), layer="B.Cu"),
    ]
    vias = [CopperVia(position=(10.0, 0.0), layers=("F.Cu", "B.Cu"))]
    result = check_net_pad_connectivity(
        "VIA_NET", pads, segments, vias, all_layers=["F.Cu", "B.Cu"]
    )
    assert result.fully_connected is True


def test_missing_via_leaves_layers_disconnected():
    """Same geometry as above but WITHOUT the via: F.Cu and B.Cu segments
    that happen to share an (x, y) point are NOT connected -- a segment
    never implicitly changes layer, only a via does."""
    pads = [
        NetPad(position=(0.0, 0.0), layer="F.Cu", ref="U1.1"),
        NetPad(position=(20.0, 0.0), layer="B.Cu", ref="U2.1"),
    ]
    segments = [
        CopperSegment(p1=(0.0, 0.0), p2=(10.0, 0.0), layer="F.Cu"),
        CopperSegment(p1=(10.0, 0.0), p2=(20.0, 0.0), layer="B.Cu"),
    ]
    result = check_net_pad_connectivity(
        "NO_VIA_NET", pads, segments, [], all_layers=["F.Cu", "B.Cu"]
    )
    assert result.fully_connected is False
    assert result.is_fake_completion is True


def test_through_hole_pad_reachable_from_either_layer():
    """Two THT pads (``ALL_LAYERS`` sentinel), joined by a trace on only
    ONE layer, must be recognized as connected -- a real through-hole
    pad's barrel spans the whole stackup, so copper arriving on any
    single layer still reaches it."""
    pads = [
        NetPad(position=(0.0, 0.0), layer=ALL_LAYERS, ref="J1.1"),
        NetPad(position=(20.0, 0.0), layer=ALL_LAYERS, ref="J1.2"),
    ]
    segments = [CopperSegment(p1=(0.0, 0.0), p2=(20.0, 0.0), layer="B.Cu")]
    result = check_net_pad_connectivity(
        "THT_NET", pads, segments, [], all_layers=["F.Cu", "B.Cu"]
    )
    assert result.fully_connected is True


def test_smd_pad_not_reachable_by_a_same_position_trace_on_a_different_layer():
    """Contrast case: an SMD pad pinned to ONE specific layer is NOT
    reached by a trace at the same (x, y) on a different layer without an
    explicit via -- a segment never implicitly changes layer."""
    pads = [
        NetPad(position=(0.0, 0.0), layer="F.Cu", ref="U1.1"),
        NetPad(position=(20.0, 0.0), layer="F.Cu", ref="U2.1"),
    ]
    segments = [CopperSegment(p1=(0.0, 0.0), p2=(20.0, 0.0), layer="B.Cu")]
    result = check_net_pad_connectivity(
        "SMD_WRONG_LAYER", pads, segments, [], all_layers=["F.Cu", "B.Cu"]
    )
    assert result.fully_connected is False
    assert result.is_fake_completion is True


def test_zero_or_one_pad_net_is_trivially_connected():
    """A net with 0 or 1 pads has nothing to join -- must not be flagged,
    matching topology_copper_audit's own self-referential-net handling."""
    single = check_net_pad_connectivity("SELF_REF", [NetPad((0.0, 0.0), "F.Cu")], [], [])
    assert single.fully_connected is True
    assert single.is_fake_completion is False

    empty = check_net_pad_connectivity("NO_PADS", [], [], [])
    assert empty.fully_connected is True


def test_no_copper_at_all_is_not_fake_completion_it_is_honest_incompleteness():
    """A net with pads and NO copper at all is a legitimate "not routed
    yet" outcome, not fake completion -- ``is_fake_completion`` requires
    copper to exist AND fail to connect, not merely fail to connect."""
    pads = [NetPad((0.0, 0.0), "F.Cu"), NetPad((10.0, 0.0), "F.Cu")]
    result = check_net_pad_connectivity("UNROUTED", pads, [], [])
    assert result.has_any_copper is False
    assert result.fully_connected is False
    assert result.is_fake_completion is False, (
        "no copper at all is an honest gap, not fake completion -- "
        "is_fake_completion should only fire when copper EXISTS but doesn't connect"
    )


def test_partial_star_topology_flags_only_the_unreached_pad():
    """3-pad net where 2 pads are joined and the third is isolated: the
    majority component wins, and only the genuinely unreached pad is named."""
    pads = [
        NetPad((0.0, 0.0), "F.Cu", ref="A"),
        NetPad((10.0, 0.0), "F.Cu", ref="B"),
        NetPad((100.0, 100.0), "F.Cu", ref="C"),
    ]
    segments = [CopperSegment(p1=(0.0, 0.0), p2=(10.0, 0.0), layer="F.Cu")]
    result = check_net_pad_connectivity("STAR", pads, segments, [])
    assert result.fully_connected is False
    assert result.pads_connected == 2
    assert [p.ref for p in result.unreached_pads] == ["C"]


# ---------------------------------------------------------------------------
# 2. Real-board adapter smoke test.
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_audit_pcb_file_runs_on_the_fixture_board():
    """The file-parsing adapter must run end-to-end on a real (small)
    board without crashing, returning one result per net with a pad."""
    fixture = REPO_ROOT / "pcb" / "benchmarks" / "temper_fixture_33.kicad_pcb"
    if not fixture.exists():
        pytest.skip(f"fixture board not found: {fixture}")
    results = audit_pcb_file(fixture)
    assert results, "expected at least one net with pads on the fixture board"
    for net_name, result in results.items():
        assert result.net_name == net_name
        assert result.pad_count >= 0
