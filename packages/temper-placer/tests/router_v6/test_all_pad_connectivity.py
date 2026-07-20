"""Tests for the router-facing all-pad connectivity contract."""

from itertools import permutations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    CopperVia,
    PadIdentity,
    verify_connectivity_by_net,
    verify_net_connectivity,
)
from temper_placer.router_v6.constraints_geometry import Point


def _pad(name: str, x: float, *, layers: frozenset[int] = frozenset({0})) -> CopperPad:
    return CopperPad(
        PadIdentity("U1", name, "NET", x, 0, tuple(sorted(layers))),
        Point(x, 0),
        "rect",
        (1, 1),
    )


def test_audit_marks_endpoint_path_incomplete_when_a_third_pad_is_absent():
    audit = verify_net_connectivity(
        [_pad("1", 0), _pad("2", 10), _pad("3", 20)],
        [CopperTrack(Point(0, 0), Point(10, 0), layer=0)],
        [],
    )

    assert audit.disposition == "incomplete"
    assert audit.connected_pad_count == 2
    assert audit.total_required_pad_count == 3
    assert [pad.pad for island in audit.unresolved_islands for pad in island] == ["3"]


def test_audit_requires_a_legal_via_or_pth_bridge_for_layer_transition():
    top = _pad("1", 0)
    bottom = _pad("2", 10, layers=frozenset({1}))
    tracks = [
        CopperTrack(Point(0, 0), Point(5, 0), layer=0),
        CopperTrack(Point(5, 0), Point(10, 0), layer=1),
    ]

    without_via = verify_net_connectivity([top, bottom], tracks, [])
    with_via = verify_net_connectivity(
        [top, bottom], tracks, [CopperVia(Point(5, 0), frozenset({0, 1}))]
    )

    assert without_via.disposition == "incomplete"
    assert with_via.disposition == "routed"


def test_same_xy_smd_pads_on_different_layers_do_not_connect():
    audit = verify_net_connectivity(
        [_pad("1", 0), _pad("2", 0, layers=frozenset({1}))], [], []
    )

    assert audit.disposition == "incomplete"
    assert audit.connected_pad_count == 1


def test_track_intersection_with_rotated_pad_copper_connects_without_endpoint_inside():
    pad = CopperPad(PadIdentity("U1", "1", "NET", 0, 0, (0,)), Point(0, 0), "rect", (4, 1), 45)
    audit = verify_net_connectivity(
        [_pad("0", -5), pad], [CopperTrack(Point(-5, 0), Point(5, 0), layer=0)], []
    )

    assert audit.disposition == "routed"


def test_pth_pad_is_a_valid_layer_bridge_but_smd_pad_is_not():
    tracks = [
        CopperTrack(Point(-5, 0), Point(0, 0), layer=0),
        CopperTrack(Point(0, 0), Point(5, 0), layer=1),
    ]
    endpoints = [_pad("1", -5), _pad("3", 5, layers=frozenset({1}))]
    pth = verify_net_connectivity([*endpoints, _pad("2", 0, layers=frozenset({0, 1}))], tracks, [])
    smd = verify_net_connectivity([*endpoints, _pad("2", 0)], tracks, [])

    assert pth.disposition == "routed"
    assert smd.disposition == "incomplete"


def test_single_pad_is_not_silently_reported_as_routed():
    audit = verify_net_connectivity([_pad("1", 0)], [], [])

    assert audit.disposition == "incomplete"
    assert audit.reason == "disconnected_required_pads"


def test_grouped_verification_keeps_tracks_and_vias_with_their_net():
    pads = [_pad("1", 0), _pad("2", 10)]
    tracks = [CopperTrack(Point(0, 0), Point(10, 0), layer=0, net="NET")]

    audit = verify_connectivity_by_net(pads, tracks, [])

    assert audit["NET"].disposition == "routed"


@given(st.lists(st.integers(min_value=0, max_value=5), min_size=2, max_size=6, unique=True))
@settings(max_examples=50, deadline=30_000)
def test_connected_pad_set_and_disposition_are_invariant_under_pad_permutation(indices):
    pads = [_pad(str(index), index * 10) for index in indices]
    ordered = sorted(indices)
    tracks = [
        CopperTrack(Point(left * 10, 0), Point(right * 10, 0), layer=0)
        for left, right in zip(ordered, ordered[1:])
    ]
    expected = verify_net_connectivity(pads, tracks, [])

    # Exhaustive pad permutations remain small (at most 6!); reversing the
    # independently ordered track list covers the graph's other input order.
    for permutation in permutations(pads):
        actual = verify_net_connectivity(list(permutation), tuple(reversed(tracks)), [])
        assert actual.disposition == "routed"
        assert actual.connected_pad_ids == expected.connected_pad_ids


@given(st.lists(st.integers(min_value=0, max_value=4), min_size=2, max_size=5, unique=True))
@settings(max_examples=50, deadline=30_000)
def test_adding_an_isolated_required_pad_changes_routed_to_incomplete(indices):
    ordered = sorted(indices)
    pads = [_pad(str(index), index * 10) for index in ordered]
    tracks = [
        CopperTrack(Point(left * 10, 0), Point(right * 10, 0), layer=0)
        for left, right in zip(ordered, ordered[1:])
    ]
    routed = verify_net_connectivity(pads, tracks, [])
    isolated = _pad("isolated", 1000)
    incomplete = verify_net_connectivity([*pads, isolated], tracks, [])

    assert routed.disposition == "routed"
    assert incomplete.disposition == "incomplete"
    assert isolated.identity in incomplete.unresolved_islands[-1]
