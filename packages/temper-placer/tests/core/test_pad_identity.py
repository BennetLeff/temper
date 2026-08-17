"""Tests for core.pad_identity -- the physical-pad-identity SSOT.

Fixtures mirror the real board's K2/K3 shape (a pad number duplicated
twice, 7.5mm apart, same net per pair) and K1's shape (a pad number
duplicated with no net at all) rather than inventing an unrelated one, so
a regression here tracks the real defect this module exists to prevent.
"""

from __future__ import annotations

import pytest

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.core.pad_identity import (
    AmbiguousPinError,
    PadOccurrence,
    duplicate_pad_numbers,
    get_unique_pin,
    iter_matching_pins,
    iter_pin_occurrences,
    net_pad_positions,
    net_pin_occurrence_indices,
    nth_matching_pin,
    resolve_net_pins,
)


def _k2_like_component() -> Component:
    """A component shaped like K2: pad "3" duplicated twice, 7.5mm apart,
    same net; pad "2" appears once, on a different net."""
    pins = [
        Pin(name="2", number="2", position=(0.0, 0.0), net="COIL"),
        Pin(name="3", number="3", position=(25.34, -7.5), net="NO"),
        Pin(name="3", number="3", position=(25.34, 0.0), net="NO"),
    ]
    return Component(ref="K2", footprint="Relay", bounds=(10.0, 10.0), pins=pins)


def _k1_like_component() -> Component:
    """A component shaped like K1: pad "" duplicated four times, no net."""
    pins = [
        Pin(name="A1", number="A1", position=(0.0, 0.0), net="COIL1"),
        Pin(name="", number="", position=(-11.0, 5.75), net=None),
        Pin(name="", number="", position=(11.0, 5.75), net=None),
        Pin(name="", number="", position=(-11.0, -6.25), net=None),
        Pin(name="", number="", position=(11.0, -6.25), net=None),
    ]
    return Component(ref="K1", footprint="Relay2", bounds=(10.0, 10.0), pins=pins)


class TestIterMatchingPins:
    def test_returns_all_physical_occurrences(self):
        comp = _k2_like_component()
        matches = iter_matching_pins(comp, "3")
        assert len(matches) == 2
        assert {m.position for m in matches} == {(25.34, -7.5), (25.34, 0.0)}

    def test_single_match_for_non_duplicated_pin(self):
        comp = _k2_like_component()
        matches = iter_matching_pins(comp, "2")
        assert len(matches) == 1

    def test_no_match_returns_empty_list(self):
        comp = _k2_like_component()
        assert iter_matching_pins(comp, "99") == []

    def test_matches_by_name_or_number(self):
        comp = _k1_like_component()
        matches = iter_matching_pins(comp, "A1")
        assert len(matches) == 1
        assert matches[0].net == "COIL1"


class TestNthMatchingPin:
    def test_resolves_distinct_physical_pads_by_occurrence(self):
        """The exact regression this module exists to prevent:
        nth_matching_pin(comp, "3", 0) and nth_matching_pin(comp, "3", 1)
        must return DIFFERENT pins, not the same first match twice."""
        comp = _k2_like_component()
        first = nth_matching_pin(comp, "3", 0)
        second = nth_matching_pin(comp, "3", 1)
        assert first is not None
        assert second is not None
        assert first.position != second.position
        assert first.position == (25.34, -7.5)
        assert second.position == (25.34, 0.0)

    def test_occurrence_beyond_match_count_is_none(self):
        comp = _k2_like_component()
        assert nth_matching_pin(comp, "3", 2) is None

    def test_no_match_at_all_is_none(self):
        comp = _k2_like_component()
        assert nth_matching_pin(comp, "99", 0) is None

    def test_negative_occurrence_is_none(self):
        comp = _k2_like_component()
        assert nth_matching_pin(comp, "3", -1) is None


class TestGetUniquePin:
    def test_raises_on_duplicate_pad_number(self):
        """The Part-3 enforcement primitive: asking for "the" pin on a
        component with two of them fails loud, not silently picks one."""
        comp = _k2_like_component()
        with pytest.raises(AmbiguousPinError) as exc_info:
            get_unique_pin(comp, "3")
        assert exc_info.value.ref == "K2"
        assert exc_info.value.pin_number == "3"
        assert exc_info.value.count == 2

    def test_returns_the_pin_when_unambiguous(self):
        comp = _k2_like_component()
        pin = get_unique_pin(comp, "2")
        assert pin is not None
        assert pin.net == "COIL"

    def test_returns_none_when_no_match(self):
        comp = _k2_like_component()
        assert get_unique_pin(comp, "99") is None


class TestDuplicatePadNumbers:
    def test_k2_shape(self):
        comp = _k2_like_component()
        assert duplicate_pad_numbers(comp) == {"3": 2}

    def test_k1_shape_empty_string_pad_number(self):
        comp = _k1_like_component()
        assert duplicate_pad_numbers(comp) == {"": 4}

    def test_empty_for_component_with_no_duplicates(self):
        comp = Component(
            ref="R1",
            footprint="R_0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin(name="1", number="1", position=(-1.0, 0.0), net="A"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="B"),
            ],
        )
        assert duplicate_pad_numbers(comp) == {}


class TestIterPinOccurrences:
    def test_yields_stable_pad_occurrence_per_pin(self):
        comp = _k2_like_component()
        results = list(iter_pin_occurrences(comp))
        assert len(results) == 3
        occurrences = [occ for occ, _pin in results]
        assert occurrences == [
            PadOccurrence(ref="K2", pin_number="2", occurrence=0),
            PadOccurrence(ref="K2", pin_number="3", occurrence=0),
            PadOccurrence(ref="K2", pin_number="3", occurrence=1),
        ]

    def test_distinct_occurrences_are_distinct_padoccurrence_values(self):
        comp = _k2_like_component()
        occs = [occ for occ, _pin in iter_pin_occurrences(comp)]
        assert len(occs) == len(set(occs)), "PadOccurrence values must be unique per physical pad"


class TestNetPinOccurrenceIndices:
    def test_counts_repeats_of_the_same_tuple(self):
        pins = [("K2", "3"), ("K2", "3")]
        assert net_pin_occurrence_indices(pins) == [0, 1]

    def test_distinct_tuples_all_get_occurrence_zero(self):
        pins = [("K2", "1"), ("K3", "1"), ("R1", "1")]
        assert net_pin_occurrence_indices(pins) == [0, 0, 0]

    def test_mixed_repeats(self):
        pins = [("K2", "3"), ("R1", "1"), ("K2", "3"), ("K2", "3")]
        assert net_pin_occurrence_indices(pins) == [0, 0, 1, 2]

    def test_empty_input(self):
        assert net_pin_occurrence_indices([]) == []


class TestResolveNetPins:
    def test_resolves_the_discharge_no_net_shape(self):
        """The exact discharge.k_dis1-no shape: Net.pins ==
        [('K2', '3'), ('K2', '3')] must resolve to two DISTINCT pins,
        not the same one twice."""
        comp = _k2_like_component()
        net = Net(name="discharge.k_dis1-no", pins=[("K2", "3"), ("K2", "3")])
        comp_by_ref = {"K2": comp}
        results = list(resolve_net_pins(net, comp_by_ref))
        assert len(results) == 2
        _, _, pin_a = results[0]
        _, _, pin_b = results[1]
        assert pin_a is not None and pin_b is not None
        assert pin_a.position != pin_b.position

    def test_missing_component_yields_none_pin(self):
        net = Net(name="N", pins=[("MISSING", "1")])
        results = list(resolve_net_pins(net, {}))
        assert results == [("MISSING", "1", None)]

    def test_missing_pin_on_present_component_yields_none(self):
        comp = _k2_like_component()
        net = Net(name="N", pins=[("K2", "99")])
        results = list(resolve_net_pins(net, {"K2": comp}))
        assert results == [("K2", "99", None)]

    def test_empty_net_pins(self):
        net = Net(name="N", pins=[])
        assert list(resolve_net_pins(net, {})) == []


class TestNetPadPositions:
    def test_resolves_distinct_world_positions_for_duplicate_pads(self):
        comp = Component(
            ref="K2",
            footprint="Relay",
            bounds=(10.0, 10.0),
            pins=_k2_like_component().pins,
            initial_position=(100.0, 100.0),
            initial_rotation_quadrant=0,
        )
        net = Net(name="discharge.k_dis1-no", pins=[("K2", "3"), ("K2", "3")])
        positions = net_pad_positions(net, {"K2": comp})
        assert len(positions) == 2
        assert positions[0] != positions[1]

    def test_skips_component_missing_initial_position(self):
        pins = [Pin(name="1", number="1", position=(0.0, 0.0), net="A")]
        comp = Component(ref="X", footprint="fp", bounds=(1.0, 1.0), pins=pins)
        net = Net(name="N", pins=[("X", "1")])
        assert net_pad_positions(net, {"X": comp}) == []

    def test_falls_back_to_component_position_when_pin_unresolvable(self):
        pins = [Pin(name="1", number="1", position=(0.0, 0.0), net="A")]
        comp = Component(
            ref="X",
            footprint="fp",
            bounds=(1.0, 1.0),
            pins=pins,
            initial_position=(5.0, 6.0),
            initial_rotation_quadrant=0,
        )
        net = Net(name="N", pins=[("X", "99")])
        positions = net_pad_positions(net, {"X": comp})
        assert positions == [(5.0, 6.0)]
