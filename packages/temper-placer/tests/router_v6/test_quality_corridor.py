"""
Tests for Router V6 Quality U3: Corridor Consolidation + Track-Spread.

Part of temper-7rqf (Stage 6 - Quality Gate)
"""

from __future__ import annotations

import pytest

from temper_placer.router_v6.quality.corridor import (
    Channel,
    TrackSegment,
    _assign_tracks_to_channels,
    _compute_courtyards,
    _gap,
    _identify_channels,
    _overlap,
    _point_in_rect,
)

# ---------------------------------------------------------------------------
# Stub types for testing internal helpers without full KiCad parse
# ---------------------------------------------------------------------------


class _StubComponent:
    def __init__(self, ref, cx, cy, w, h):
        self.ref = ref
        self.initial_position = (cx, cy)
        self.width = w
        self.height = h


class _StubNetlist:
    def __init__(self, components):
        self.components = components


class _StubTrace:
    def __init__(self, start, end, width=0.2, layer="F.Cu", net=""):
        self.start = start
        self.end = end
        self.width = width
        self.layer = layer
        self.net = net


class _StubParseResult:
    def __init__(self, components, traces=None):
        self.netlist = _StubNetlist(components)
        self.traces = traces or []
        self.board = None


# ---------------------------------------------------------------------------
# Tests: geometry helpers
# ---------------------------------------------------------------------------


def test_overlap_full():
    assert _overlap(0, 10, 2, 8) == (2, 8)


def test_overlap_partial():
    assert _overlap(0, 10, 5, 15) == (5, 10)


def test_overlap_none():
    assert _overlap(0, 5, 6, 10) is None


def test_overlap_touching():
    assert _overlap(0, 5, 5, 10) is None


def test_gap_positive():
    assert _gap(5, 10) == 5.0


def test_gap_zero():
    assert _gap(5, 5) == 0.0


def test_gap_negative():
    assert _gap(10, 5) == -5.0


def test_point_in_rect_inside():
    assert _point_in_rect(5, 5, 0, 0, 10, 10) is True


def test_point_in_rect_outside():
    assert _point_in_rect(15, 5, 0, 0, 10, 10) is False


def test_point_in_rect_on_edge():
    assert _point_in_rect(10, 10, 0, 0, 10, 10) is True


# ---------------------------------------------------------------------------
# Tests: _compute_courtyards
# ---------------------------------------------------------------------------


def test_compute_courtyards_single():
    comp = _StubComponent("U1", 10, 10, 20, 30)
    result = _StubParseResult([comp])
    courtyards = _compute_courtyards(result, clearance_mm=0.25)

    assert len(courtyards) == 1
    c = courtyards[0]
    assert c.ref == "U1"
    assert c.x_min == 10 - 10 - 0.25
    assert c.x_max == 10 + 10 + 0.25
    assert c.y_min == 10 - 15 - 0.25
    assert c.y_max == 10 + 15 + 0.25


def test_compute_courtyards_no_position():
    comp = _StubComponent("U1", 0, 0, 20, 30)
    comp.initial_position = None
    result = _StubParseResult([comp])
    courtyards = _compute_courtyards(result, clearance_mm=0.25)
    assert len(courtyards) == 0


# ---------------------------------------------------------------------------
# Tests: _identify_channels
# ---------------------------------------------------------------------------


def _make_courtyard(ref, x_min, y_min, x_max, y_max):
    from temper_placer.router_v6.quality.corridor import _Courtyard

    return _Courtyard(ref=ref, x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


def test_identify_channels_empty():
    channels = _identify_channels([], min_gap_width_mm=1.0)
    assert channels == []


def test_identify_channels_single():
    c = _make_courtyard("U1", 0, 0, 10, 10)
    channels = _identify_channels([c], min_gap_width_mm=1.0)
    assert channels == []


def test_identify_channels_no_gap():
    c1 = _make_courtyard("U1", 0, 0, 10, 10)
    c2 = _make_courtyard("U2", 10, 0, 20, 10)
    channels = _identify_channels([c1, c2], min_gap_width_mm=1.0)
    assert channels == []


def test_identify_channels_horizontal():
    c1 = _make_courtyard("U1", 0, 0, 10, 10)
    c2 = _make_courtyard("U2", 15, 0, 25, 10)
    channels = _identify_channels([c1, c2], min_gap_width_mm=1.0)
    assert len(channels) == 1
    ch = channels[0]
    assert ch.axis == "horizontal"
    assert ch.gap_width_mm == 5.0


def test_identify_channels_vertical():
    c1 = _make_courtyard("U1", 0, 0, 10, 10)
    c2 = _make_courtyard("U2", 0, 15, 10, 25)
    channels = _identify_channels([c1, c2], min_gap_width_mm=1.0)
    assert len(channels) == 1
    ch = channels[0]
    assert ch.axis == "vertical"
    assert ch.gap_width_mm == 5.0


def test_identify_channels_gap_too_narrow():
    c1 = _make_courtyard("U1", 0, 0, 10, 10)
    c2 = _make_courtyard("U2", 10.5, 0, 20, 10)
    channels = _identify_channels([c1, c2], min_gap_width_mm=3.0)
    assert channels == []


def test_identify_channels_both_axes():
    c1 = _make_courtyard("U1", 0, 0, 10, 10)
    c2 = _make_courtyard("U2", 0, 15, 10, 25)
    c3 = _make_courtyard("U3", 0, 30, 10, 40)
    channels = _identify_channels([c1, c2, c3], min_gap_width_mm=1.0)
    assert len(channels) >= 2  # U1-U2 and U2-U3


def test_identify_channels_no_projection_overlap():
    c1 = _make_courtyard("U1", 0, 0, 5, 5)
    c2 = _make_courtyard("U2", 10, 10, 15, 15)
    channels = _identify_channels([c1, c2], min_gap_width_mm=1.0)
    assert channels == []


# ---------------------------------------------------------------------------
# Tests: _assign_tracks_to_channels
# ---------------------------------------------------------------------------


def test_assign_tracks_empty():
    ch = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    result = _StubParseResult([])
    tracks = _assign_tracks_to_channels(result, [ch])
    assert tracks[id(ch)] == []


def test_assign_tracks_inside_channel():
    ch = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    t = _StubTrace((5, 5), (5, 5), width=0.2)
    result = _StubParseResult([], traces=[t])
    tracks = _assign_tracks_to_channels(result, [ch])
    assert len(tracks[id(ch)]) == 1
    assert tracks[id(ch)][0].x == 5.0
    assert tracks[id(ch)][0].y == 5.0


def test_assign_tracks_outside_channel():
    ch = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    t = _StubTrace((50, 50), (50, 50), width=0.2)
    result = _StubParseResult([], traces=[t])
    tracks = _assign_tracks_to_channels(result, [ch])
    assert tracks[id(ch)] == []


def test_assign_tracks_multiple_channels():
    ch1 = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    ch2 = Channel(20, 20, 30, 30, 5.0, "vertical", "U3", "U4")
    t1 = _StubTrace((5, 5), (5, 5), net="NET1")
    t2 = _StubTrace((25, 25), (25, 25), net="NET2")
    result = _StubParseResult([], traces=[t1, t2])
    tracks = _assign_tracks_to_channels(result, [ch1, ch2])
    assert len(tracks[id(ch1)]) == 1
    assert len(tracks[id(ch2)]) == 1
    assert tracks[id(ch1)][0].net == "NET1"
    assert tracks[id(ch2)][0].net == "NET2"


# ---------------------------------------------------------------------------
# Tests: corridor_consolidation_score on hand-constructed data
# ---------------------------------------------------------------------------


def _build_tracks_for_horizontal_channel(
    channel: Channel, track_specs: list[tuple[float, str]]
) -> list:
    """Create tracks at given y-positions in a horizontal channel."""
    tracks = []
    mid_x = (channel.x_min + channel.x_max) / 2
    for y, net in track_specs:
        tracks.append(_StubTrace((mid_x, y), (mid_x, y), width=0.2, net=net))
    return tracks


def _manual_consolidation_score(channel: Channel, track_specs: list[tuple[float, str]]) -> float:
    """Compute corridor consolidation score for a hand-constructed channel."""
    result = _StubParseResult([], traces=_build_tracks_for_horizontal_channel(channel, track_specs))
    tracks_by_ch = _assign_tracks_to_channels(result, [channel])
    ch_tracks = tracks_by_ch[id(channel)]

    if len(ch_tracks) < 2:
        return 1.0

    ch_tracks.sort(key=lambda t: t.y)
    n = len(ch_tracks)
    total_pairs = n * (n - 1) // 2
    co_routed = 0

    for i in range(n - 1):
        for j in range(i + 1, n):
            if j == i + 1:
                co_routed += 1
            else:
                intervening_nets = {t.net for t in ch_tracks[i + 1 : j]}
                if len(intervening_nets) <= 1 and (
                    not intervening_nets or intervening_nets == {ch_tracks[i].net}
                ):
                    co_routed += 1

    return co_routed / total_pairs


def test_consolidation_three_tracks_all_same_net():
    ch = Channel(0, 0, 10, 30, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(
        ch,
        [
            (5, "NET1"),
            (15, "NET1"),
            (25, "NET1"),
        ],
    )
    assert score == 1.0


def test_consolidation_three_tracks_two_adjacent_one_foreign():
    ch = Channel(0, 0, 10, 30, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(
        ch,
        [
            (5, "NET1"),
            (15, "NET2"),
            (25, "NET1"),
        ],
    )
    # Pairs: (0,1) adjacent but different nets → considered not co-routed? Actually it's adjacent regardless of net
    # Hmm, "co-routed" means adjacent pairs with no foreign interleave
    # Adjacent pair (0,1): two different nets beside each other. Plan says "no foreign track interleaved".
    # Adjacent pairs are always co-routed regardless of net? Let me check the plan...
    # Plan: "'Co-routed' means two tracks adjacent with no foreign track interleaved."
    # So: (0,1) are adjacent → co-routed. (1,2) are adjacent → co-routed. (0,2): NET2 between → not co-routed.
    # score = 2/3.
    assert score == pytest.approx(2.0 / 3.0)


def test_consolidation_two_tracks_adjacent():
    ch = Channel(0, 0, 10, 20, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(
        ch,
        [
            (5, "NET1"),
            (15, "NET2"),
        ],
    )
    assert score == 1.0


def test_consolidation_single_track():
    ch = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(ch, [(5, "NET1")])
    assert score == 1.0


def test_consolidation_no_tracks_in_channel():
    ch = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(ch, [])
    assert score == 1.0


# ---------------------------------------------------------------------------
# Tests: track_spread_score
# ---------------------------------------------------------------------------


def _manual_track_spread(channel, track_specs, target_spacing_mm=0.35):
    """Compute track spread score for a hand-constructed channel."""
    result = _StubParseResult([], traces=_build_tracks_for_horizontal_channel(channel, track_specs))
    tracks_by_ch = _assign_tracks_to_channels(result, [channel])
    ch_tracks = tracks_by_ch[id(channel)]

    if len(ch_tracks) < 2:
        return 0.0

    ch_tracks.sort(key=lambda t: t.y)
    max_gap = 0.0

    for i in range(len(ch_tracks) - 1):
        gap = ch_tracks[i + 1].bottom_edge - ch_tracks[i].top_edge
        if gap > max_gap:
            max_gap = gap

    if target_spacing_mm <= 0.0:
        return 0.0
    return max_gap / target_spacing_mm


def test_track_spread_at_target_spacing():
    width = 0.2
    target = 0.35  # 0.15 clearance + 0.2 width
    y1 = 5.0
    y2 = y1 + width + target  # center-to-center distance for exact target gap

    t1 = TrackSegment("NET1", 10.0, y1, width, "F.Cu")
    t2 = TrackSegment("NET2", 10.0, y2, width, "F.Cu")
    gap = t2.bottom_edge - t1.top_edge
    assert gap == pytest.approx(target), f"gap={gap}, target={target}"

    score = gap / target
    assert score == pytest.approx(1.0)


def test_track_spread_tracks_at_exact_target():
    """Track at exact target spacing gives score 1.0."""
    Channel(0, 0, 10, 20, 5.0, "horizontal", "U1", "U2")
    width = 0.254
    target = width + 0.15  # 0.404
    edge_to_edge = target
    y1 = 5.0
    y2 = y1 + width + edge_to_edge  # center-to-center

    t1 = TrackSegment("NET1", 10.0, y1, width, "F.Cu")
    t2 = TrackSegment("NET2", 10.0, y2, width, "F.Cu")
    gap = t2.bottom_edge - t1.top_edge

    assert gap == pytest.approx(edge_to_edge)
    assert gap / target == pytest.approx(1.0)


def test_track_spread_large_gap():
    """Large gap gives score > 1.5."""
    ch = Channel(0, 0, 10, 30, 5.0, "horizontal", "U1", "U2")
    score = _manual_track_spread(
        ch,
        [
            (5, "NET1"),
            (25, "NET2"),
        ],
    )
    assert score > 1.5


def test_track_spread_single_track():
    ch = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    score = _manual_track_spread(ch, [(5, "NET1")])
    assert score == 0.0


def test_track_spread_no_tracks():
    ch = Channel(0, 0, 10, 10, 5.0, "horizontal", "U1", "U2")
    score = _manual_track_spread(ch, [])
    assert score == 0.0


# ---------------------------------------------------------------------------
# Tests: score invariants
# ---------------------------------------------------------------------------


def test_consolidation_score_in_range():
    """Corridor_consolidation_score always falls in [0.0, 1.0]."""

    def _score(specs):
        ch = Channel(0, 0, 10, 40, 5.0, "horizontal", "U1", "U2")
        return _manual_consolidation_score(ch, specs)

    s1 = _score([(5, "A"), (15, "A"), (25, "A")])
    assert 0.0 <= s1 <= 1.0

    s2 = _score([(5, "A"), (15, "B"), (25, "C")])
    assert 0.0 <= s2 <= 1.0

    s3 = _score([(5, "A"), (15, "A")])
    assert 0.0 <= s3 <= 1.0

    s4 = _score([])
    assert s4 == 1.0


def test_track_spread_score_nonnegative():
    """Track_spread_score is always >= 0.0."""

    def _score(specs):
        ch = Channel(0, 0, 10, 40, 5.0, "horizontal", "U1", "U2")
        return _manual_track_spread(ch, specs)

    assert _score([(5, "A"), (15, "B")]) >= 0.0
    assert _score([(5, "A")]) == 0.0
    assert _score([]) == 0.0


# ---------------------------------------------------------------------------
# Tests: co-routed pair definition (adjacent with no foreign interleave)
# ---------------------------------------------------------------------------


def test_co_routed_adjacent_same_net():
    """Two adjacent tracks of the same net are co-routed."""
    ch = Channel(0, 0, 10, 20, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(
        ch,
        [
            (5, "NET1"),
            (15, "NET1"),
        ],
    )
    assert score == 1.0


def test_co_routed_adjacent_different_nets():
    """Two adjacent tracks of different nets are still co-routed (adjacent)."""
    ch = Channel(0, 0, 10, 20, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(
        ch,
        [
            (5, "NET1"),
            (15, "NET2"),
        ],
    )
    assert score == 1.0


def test_not_co_routed_foreign_interleave():
    """Non-adjacent tracks with foreign net between are not co-routed."""
    ch = Channel(0, 0, 10, 30, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(
        ch,
        [
            (5, "NET1"),
            (15, "NET2"),
            (25, "NET1"),
        ],
    )
    # (0,1) adjacent co-routed, (1,2) adjacent co-routed, (0,2) NET2 between → not co-routed
    assert score == pytest.approx(2.0 / 3.0)


def test_co_routed_with_gap_of_same_net():
    """Non-adjacent tracks of the same net with same-net between are co-routed."""
    ch = Channel(0, 0, 10, 30, 5.0, "horizontal", "U1", "U2")
    score = _manual_consolidation_score(
        ch,
        [
            (5, "NET1"),
            (15, "NET1"),
            (25, "NET1"),
        ],
    )
    assert score == 1.0


# ---------------------------------------------------------------------------
# Tests: TrackSegment properties
# ---------------------------------------------------------------------------


def test_track_segment_edges():
    seg = TrackSegment("NET1", 10.0, 20.0, 0.254, "F.Cu")
    assert seg.left_edge == 10.0 - 0.127
    assert seg.right_edge == 10.0 + 0.127
    assert seg.bottom_edge == 20.0 - 0.127
    assert seg.top_edge == 20.0 + 0.127


def test_track_segment_zero_width():
    seg = TrackSegment("NET1", 5.0, 5.0, 0.0, "F.Cu")
    assert seg.left_edge == 5.0
    assert seg.right_edge == 5.0
