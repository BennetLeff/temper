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
    _cluster_key,
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
# 1b. Regression tests for three defects found in this module itself
#     (found by a review agent, fixed here; see pad_connectivity_audit.py's
#     ``_UnionFind``, ``_cluster_key``, and ``_parse_zones`` docstrings for
#     the full mechanism of each). Each test is a faithful, self-contained
#     reproduction -- verified to FAIL against the pre-fix code before being
#     pinned here.
# ---------------------------------------------------------------------------


def test_union_find_stale_root_does_not_split_a_genuinely_connected_net():
    """Defect 1: union-find stale-root reassignment on a THT/``"*"`` pad's
    multi-layer node expansion.

    Shape: pad1 (SMD, F.Cu) is joined to pad2 (THT, all layers) by one
    F.Cu segment. Before the fix, the pad-processing loop read back
    ``uf.find()`` immediately after each pad's own multi-layer union and
    kept that snapshot forever. Processing pad2's THT expansion (F.Cu ->
    B.Cu -> In1.Cu, each union reparenting the previous root) silently
    moved the root that pad1's *already-recorded* snapshot pointed to --
    pad1's stale root no longer matched pad2's fresh one, so two
    physically-joined pads counted as two separate one-pad components.
    Verified: this exact case returns ``fully_connected=False`` against
    the pre-fix module; the real-board shape (both pads THT, joined by a
    same-layer segment chain, no explicit via) is this net's
    ``thermal.j_fan-p1``/``discharge.r_dis1a-p2``/``discharge.r_dis2a-p2``
    on ``temper_routed_nlayer.kicad_pcb`` (fix/router-nlayer-routing
    branch) -- see ``test_stale_root_and_rounding_bugs_on_the_real_routed_board``
    below for the direct real-board pin.
    """
    pads = [
        NetPad(position=(0.0, 0.0), layer="F.Cu", ref="U1.1"),
        NetPad(position=(10.0, 0.0), layer=ALL_LAYERS, ref="J1.1"),
    ]
    segments = [CopperSegment(p1=(0.0, 0.0), p2=(10.0, 0.0), layer="F.Cu")]
    result = check_net_pad_connectivity(
        "STALE_ROOT_REPRO", pads, segments, [], all_layers=["B.Cu", "F.Cu", "In1.Cu"]
    )
    assert result.fully_connected is True, (
        "pad1 and pad2 are genuinely joined by the F.Cu segment -- a stale "
        "union-find root snapshot must not report them as disconnected"
    )
    assert result.pads_connected == 2
    assert result.unreached_pads == ()


def test_cluster_key_nm_snap_collapses_sub_nanometre_float_noise():
    """Defect 2 (unit-level): ``_cluster_key`` must treat two float
    representations of the same nanometre-resolution point identically,
    even when one carries ~1e-14 mm of transform-composition noise that
    pushes it across a ``round()`` round-half-to-even tie the clean value
    sits exactly on."""
    clean = _cluster_key((0.0, 139.53), 0.02)
    noisy = _cluster_key((0.0, 139.53000000000003), 0.02)
    assert clean == noisy == (0, 6976)


def test_float_noise_pad_position_does_not_split_from_a_clean_via_WDT_KICK_repro():
    """Defect 2: exact reproduction of the real ``WDT_KICK`` failure on
    ``temper_routed_nlayer.kicad_pcb`` (fix/router-nlayer-routing branch,
    unmerged). Pad U20.4 sits at (117.3925, 139.53000000000003) -- ~3e-14mm
    of float noise from this codebase's footprint-transform composition --
    while the via that actually bridges it to the routed copper was
    written cleanly at (117.3925, 139.53). ``139.53 / 0.02 == 6976.5``
    exactly, so Python's round-half-to-even rounds the clean via's value
    down to 6976 (even) while the noisy pad value, being strictly above
    .5, rounds up to 6977 -- splitting one physical point into two
    tolerance buckets and reading a genuinely-landed via as a fake
    completion. WDT_KICK's own vias and segments were hand-verified
    correct and genuinely connecting; the pre-fix audit's "fake
    completion" verdict on it was wrong.
    """
    pads = [
        NetPad(position=(117.3925, 139.53000000000003), layer="F.Cu", ref="U20.4"),
        NetPad(position=(36.64, 56.96), layer="F.Cu", ref="U27.7"),
    ]
    vias = [
        CopperVia(position=(117.3925, 139.53), layers=("F.Cu", "In4.Cu")),
        CopperVia(position=(36.64, 56.96), layers=("In4.Cu", "F.Cu")),
    ]
    segments = [CopperSegment(p1=(117.3925, 139.53), p2=(36.64, 56.96), layer="In4.Cu")]
    result = check_net_pad_connectivity(
        "WDT_KICK", pads, segments, vias, all_layers=["F.Cu", "In4.Cu"]
    )
    assert result.fully_connected is True, (
        "WDT_KICK's via lands exactly on its own pad (modulo float noise "
        "below any real fabrication tolerance) -- this must not read as "
        "fake completion"
    )
    assert result.unreached_pads == ()


def test_zone_dependent_net_with_no_explicit_copper_is_unmeasured_not_broken():
    """Defect 3: a net whose only possible source of copper is a zone pour
    on its pads' own layer must not be silently counted as a confirmed
    "honest gap" (nor as "connected" -- this audit still cannot see zone
    fill geometry at all). It must land in the explicit
    zone_dependent_unmeasured category."""
    pads = [NetPad((0.0, 0.0), "F.Cu", ref="C1.1"), NetPad((50.0, 50.0), "F.Cu", ref="C2.1")]
    result = check_net_pad_connectivity("gnd_like", pads, [], [], zone_layers=["F.Cu"])
    assert result.fully_connected is False
    assert result.has_any_copper is False
    assert result.zone_dependent_unmeasured is True
    assert result.category == "zone_dependent_unmeasured"


def test_zone_on_a_different_layer_does_not_excuse_the_gap():
    """A zone that exists for this net but on a layer neither unreached
    pad is on cannot explain the gap -- must stay a measured 'broken'
    verdict, not be waved through as unmeasured."""
    pads = [NetPad((0.0, 0.0), "F.Cu", ref="C1.1"), NetPad((50.0, 50.0), "F.Cu", ref="C2.1")]
    result = check_net_pad_connectivity("not_really_covered", pads, [], [], zone_layers=["B.Cu"])
    assert result.zone_dependent_unmeasured is False
    assert result.category == "broken"


def test_partial_zone_coverage_still_counts_as_a_measured_gap():
    """3-pad net: A/B are joined by a real segment, C is isolated on a
    layer the net's zone does NOT cover. Even though the net has SOME
    zone somewhere, C's specific gap is real and must not be silently
    excused into the unmeasured bucket -- only a net where EVERY unreached
    pad has zone cover becomes zone_dependent_unmeasured."""
    pads = [
        NetPad((0.0, 0.0), "F.Cu", ref="A"),
        NetPad((10.0, 0.0), "F.Cu", ref="B"),
        NetPad((100.0, 100.0), "B.Cu", ref="C"),
    ]
    segments = [CopperSegment((0.0, 0.0), (10.0, 0.0), "F.Cu")]
    result = check_net_pad_connectivity("partial", pads, segments, [], zone_layers=["F.Cu"])
    assert result.zone_dependent_unmeasured is False
    assert result.category == "broken"
    assert [p.ref for p in result.unreached_pads] == ["C"]


def test_tht_pad_gets_zone_coverage_from_any_declared_layer():
    """A through-hole pad's barrel spans every copper layer, so a zone
    declared on ANY layer is a candidate connection for it -- unlike an
    SMD pad, which only benefits from a zone on its own specific layer."""
    pads = [
        NetPad((0.0, 0.0), ALL_LAYERS, ref="J1.1"),
        NetPad((50.0, 50.0), ALL_LAYERS, ref="J1.2"),
    ]
    result = check_net_pad_connectivity("tht_pour_net", pads, [], [], zone_layers=["In2.Cu"])
    assert result.zone_dependent_unmeasured is True
    assert result.category == "zone_dependent_unmeasured"


def test_parse_zones_extracts_net_layer_and_fill_state():
    """``_parse_zones`` must (a) map net name -> declared zone layers and
    (b) separately count zone blocks that carry real ``filled_polygon``
    fill geometry vs. ones that are outline-only -- the distinction this
    module's docstring explains is the difference between "a pour is
    intended here" and "there is actually copper here". A zone block
    without ``filled_polygon`` provides no geometry a real point-in-polygon
    check could even test against."""
    from temper_placer.router_v6.pad_connectivity_audit import _parse_zones

    content = (
        '(net 5 "gnd")\n'
        '(zone (net 5) (net_name "gnd") (layer "F.Cu")\n'
        "  (polygon (pts (xy 0 0) (xy 1 0) (xy 1 1)))\n"
        ")\n"
        '(zone (net 5) (net_name "gnd") (layer "B.Cu")\n'
        '  (filled_polygon (layer "B.Cu") (pts (xy 0 0) (xy 1 0) (xy 1 1)))\n'
        ")\n"
    )
    zone_layers, n_filled, n_unfilled = _parse_zones(content)
    assert zone_layers == {"gnd": {"F.Cu", "B.Cu"}}
    assert n_filled == 1
    assert n_unfilled == 1


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


# ---------------------------------------------------------------------------
# 3. Direct real-board pins for defects 1 and 2 -- the actual artifact that
#    produced this project's reported "52/139 fully pad-connected" figure.
#    This file lives outside this repo's worktree, on the unmerged
#    fix/router-nlayer-routing branch's own scratch output, so it is not
#    guaranteed present in every checkout/CI environment -- skip cleanly
#    when absent rather than failing the suite.
# ---------------------------------------------------------------------------

_ROUTED_NLAYER_BOARD = Path(
    "/home/bennet/Desktop/temper-worktrees/router-nlayer-routing/scratch_out/temper_routed_nlayer.kicad_pcb"
)


@pytest.mark.slow
def test_stale_root_and_rounding_bugs_on_the_real_routed_board():
    """Direct pin against the real artifact: these five nets were
    misreported as NOT fully pad-connected before this module's defect 1
    (union-find stale root) and defect 2 (round-half-to-even tie boundary)
    fixes, on hand-verified-correct copper. This is the strongest possible
    regression for both defects -- the actual failing production data,
    not a synthetic reconstruction.
    """
    if not _ROUTED_NLAYER_BOARD.exists():
        pytest.skip(f"external routed-board artifact not found: {_ROUTED_NLAYER_BOARD}")
    results = audit_pcb_file(_ROUTED_NLAYER_BOARD)
    # Defect 2 (rounding): WDT_KICK, i2c_sda_ui, safety.ocp-line, safety-line-3.
    # Defect 1 (stale root): thermal.j_fan-p1, discharge.r_dis2a-p2.
    # discharge.r_dis1a-p2 needs BOTH fixes (it hits both defects at once).
    for net_name in (
        "WDT_KICK",
        "i2c_sda_ui",
        "safety.ocp-line",
        "safety-line-3",
        "thermal.j_fan-p1",
        "discharge.r_dis2a-p2",
        "discharge.r_dis1a-p2",
    ):
        result = results.get(net_name)
        assert result is not None, f"{net_name} not found on the routed board"
        assert result.fully_connected is True, (
            f"{net_name} should be fully pad-connected -- got unreached "
            f"pads {[p.ref for p in result.unreached_pads]}"
        )
