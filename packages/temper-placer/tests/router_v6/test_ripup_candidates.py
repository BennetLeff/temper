"""TDD and property tests for inherited-copper rip-up candidate selection."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from shapely.geometry import box

from temper_placer.io._kicad_types import TraceData, ViaData
from temper_placer.router_v6.ripup_candidates import select_ripup_candidates


def _track(net: str | None, x: float, y: float) -> TraceData:
    return TraceData(
        start=(x, y), end=(x + 1.0, y), width=0.2, layer="F.Cu", net=net
    )


def test_selection_includes_target_without_existing_copper() -> None:
    selection = select_ripup_candidates(
        tracks=[_track("blocking", 5.0, 5.0)],
        vias=[],
        target_nets=["target"],
        corridor=box(0.0, 0.0, 1.0, 1.0),
    )

    assert selection.selected_net_names == ("target",)
    assert selection.unaddressed_copper_count == 0


def test_selection_reports_unaddressable_inherited_copper() -> None:
    selection = select_ripup_candidates(
        tracks=[_track(None, 0.25, 0.25)],
        vias=[],
        target_nets=["target"],
        corridor=box(0.0, 0.0, 1.0, 1.0),
    )

    assert selection.selected_net_names == ("target",)
    assert selection.unaddressed_copper_count == 1


def test_candidates_are_ranked_by_copper_then_name() -> None:
    selection = select_ripup_candidates(
        tracks=[
            _track("z-net", 0.0, 0.0),
            _track("a-net", 0.0, 0.5),
            _track("a-net", 0.0, 0.75),
        ],
        vias=[ViaData((0.5, 0.5), 0.4, 0.2, "z-net")],
        target_nets=["target"],
        corridor=box(0.0, 0.0, 2.0, 2.0),
    )

    assert [candidate.net_name for candidate in selection.candidates] == [
        "a-net",
        "z-net",
        "target",
    ]
    assert selection.candidates[0].copper_count == 2
    assert selection.candidates[1].copper_count == 2


def test_invalid_target_names_fail_closed() -> None:
    with pytest.raises(ValueError, match="target_nets"):
        select_ripup_candidates([], [], [" ", "target"], box(0, 0, 1, 1))


@st.composite
def _track_sets(draw: st.DrawFn) -> list[TraceData]:
    rows = draw(
        st.lists(
            st.tuples(
                st.sampled_from(["a", "b", "c"]),
                st.floats(0.0, 4.0, allow_nan=False, allow_infinity=False),
                st.floats(0.0, 4.0, allow_nan=False, allow_infinity=False),
            ),
            max_size=12,
        )
    )
    return [_track(net, x, y) for net, x, y in rows]


@given(tracks=_track_sets())
def test_selection_is_invariant_to_input_track_order(
    tracks: list[TraceData],
) -> None:
    corridor = box(1.0, 1.0, 3.0, 3.0)
    forward = select_ripup_candidates(tracks, [], ["target"], corridor)
    reverse = select_ripup_candidates(list(reversed(tracks)), [], ["target"], corridor)

    assert forward == reverse


@given(tracks=_track_sets())
def test_expanding_corridor_can_only_add_candidate_nets(
    tracks: list[TraceData],
) -> None:
    narrow = select_ripup_candidates(tracks, [], ["target"], box(1.0, 1.0, 2.0, 2.0))
    wide = select_ripup_candidates(tracks, [], ["target"], box(0.0, 0.0, 4.0, 4.0))

    assert set(narrow.selected_net_names) <= set(wide.selected_net_names)


@given(tracks=_track_sets())
def test_outside_copper_does_not_change_selection(
    tracks: list[TraceData],
) -> None:
    corridor = box(1.0, 1.0, 2.0, 2.0)
    baseline = select_ripup_candidates(tracks, [], ["target"], corridor)
    outside = tracks + [_track("outside", 100.0, 100.0)]
    changed = select_ripup_candidates(outside, [], ["target"], corridor)

    assert changed == baseline


@given(tracks=_track_sets())
def test_adding_copper_to_existing_candidate_preserves_net_set(
    tracks: list[TraceData],
) -> None:
    corridor = box(0.0, 0.0, 4.0, 4.0)
    baseline = select_ripup_candidates(tracks, [], ["target"], corridor)
    candidate = next(iter(set(baseline.selected_net_names) - {"target"}), "target")
    added = tracks + [_track(candidate, 0.5, 0.5)]
    changed = select_ripup_candidates(added, [], ["target"], corridor)

    assert set(changed.selected_net_names) == set(baseline.selected_net_names)
