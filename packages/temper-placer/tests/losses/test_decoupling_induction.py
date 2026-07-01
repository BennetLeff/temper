"""Induction ladder for decoupling detection.

Following the test_induction_base.py / test_clearance_induction.py pattern:
- Base case: Empty netlist -> empty detection set
- Add (cap): Adding capacitor to IC's power net produces detection
- Add (non-cap): Adding non-capacitor component doesn't change detections
- Remove: Removing a component removes its detections
- Modify: Changing capacitor footprint from small to large changes classification

Uses Hypothesis to generate valid netlists and verify invariants.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.decoupling import (
    auto_detect_decoupling,
    auto_detect_decoupling_set,
)
from temper_placer.losses.decoupling_types import DecouplingClass


def _make_cap(ref: str, footprint: str = "0603", nets: list[str] | None = None) -> Component:
    nets = nets or ["VCC", "GND"]
    pins = [
        Pin(str(i + 1), str(i + 1), (0.0, 0.0), net=nets[i])
        for i in range(min(len(nets), 2))
    ]
    return Component(ref=ref, footprint=footprint, bounds=(2.0, 1.0), pins=pins)


def _make_ic(ref: str, footprint: str = "SOIC-8", nets: list[str] | None = None) -> Component:
    nets = nets or ["VCC", "GND", "SIG1", "SIG2"]
    pins = [
        Pin(str(i + 1), str(i + 1), (0.0, 0.0), net=nets[i])
        for i in range(len(nets))
    ]
    return Component(ref=ref, footprint=footprint, bounds=(5.0, 5.0), pins=pins)


def _make_netlist(components: list[Component]) -> Netlist:
    net_pins: dict[str, list[tuple[str, str]]] = {}
    for comp in components:
        for pin in comp.pins:
            if pin.net:
                net_pins.setdefault(pin.net, []).append((comp.ref, pin.name))
    nets = [Net(name=n, pins=p) for n, p in net_pins.items()]
    return Netlist(components=components, nets=nets)


class TestDecouplingInductionBase:
    """Base case: empty netlist -> no detections."""

    def test_empty_netlist_empty_detections(self):
        """auto_detect_decoupling returns empty list for empty netlist."""
        netlist = Netlist(components=[], nets=[])
        rules = auto_detect_decoupling(netlist)
        assert rules == [], f"Expected empty, got {rules}"

    def test_empty_netlist_empty_set(self):
        """auto_detect_decoupling_set returns detections with zero items."""
        netlist = Netlist(components=[], nets=[])
        dset = auto_detect_decoupling_set(netlist)
        assert len(dset) == 0, f"Expected 0 detections, got {len(dset)}"

    def test_ics_only_no_detections(self):
        """Netlist with only ICs and no caps produces no detections."""
        ic = _make_ic("U1")
        netlist = _make_netlist([ic])
        rules = auto_detect_decoupling(netlist)
        assert rules == []


class TestDecouplingInductionAdd:
    """Inductive step: adding components."""

    def test_add_cap_to_power_net_produces_detection(self):
        """Adding a capacitor to an IC's power net yields at least one detection."""
        ic = _make_ic("U1", nets=["VCC", "GND", "SIG1", "SIG2"])
        netlist_before = _make_netlist([ic])
        assert auto_detect_decoupling(netlist_before) == []

        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        netlist_after = _make_netlist([ic, cap])
        rules = auto_detect_decoupling(netlist_after)
        assert len(rules) >= 1, f"Expected >=1 detection, got {len(rules)}"
        assert rules[0].cap_ref == "C1"
        assert rules[0].ic_ref == "U1"

    def test_add_non_capacitor_no_change(self):
        """Adding a resistor (non-cap) does not produce new decoupling detections."""
        ic = _make_ic("U1")
        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        netlist_before = _make_netlist([ic, cap])
        detections_before = auto_detect_decoupling(netlist_before)
        assert len(detections_before) >= 1

        resistor = Component(
            ref="R1",
            footprint="0603",
            bounds=(2.0, 1.0),
            pins=[
                Pin("1", "1", (0.0, 0.0), net="VCC"),
                Pin("2", "2", (0.0, 0.0), net="GND"),
            ],
        )
        netlist_after = _make_netlist([ic, cap, resistor])
        detections_after = auto_detect_decoupling(netlist_after)
        assert len(detections_after) == len(detections_before), (
            f"Adding non-cap should not change detections: "
            f"before={len(detections_before)}, after={len(detections_after)}"
        )

    def test_add_cap_to_signal_only_no_detection(self):
        """Capacitor on signal-only net (not power) produces no detection."""
        ic = _make_ic("U1", nets=["SIG1", "SIG2", "CLK", "RST"])
        cap = _make_cap("C1", "0603", ["SIG1", "GND"])
        netlist = _make_netlist([ic, cap])
        rules = auto_detect_decoupling(netlist)
        assert rules == [], f"Signal-only cap should not trigger decoupling, got {rules}"


class TestDecouplingInductionRemove:
    """Inductive step: removing components."""

    def test_remove_cap_removes_detection(self):
        """Removing a capacitor removes its detection from the set."""
        ic = _make_ic("U1")
        cap1 = _make_cap("C1", "0603", ["VCC", "GND"])
        cap2 = _make_cap("C2", "0603", ["VCC", "GND"])
        netlist_full = _make_netlist([ic, cap1, cap2])
        detections_full = auto_detect_decoupling(netlist_full)
        assert len(detections_full) >= 2

        netlist_without_c1 = _make_netlist([ic, cap2])
        detections_without = auto_detect_decoupling(netlist_without_c1)
        c1_detections = [d for d in detections_without if d.cap_ref == "C1"]
        assert len(c1_detections) == 0, "C1 should have no detections after removal"

    def test_remove_ic_removes_detection(self):
        """Removing an IC removes its detection from the set."""
        ic = _make_ic("U1")
        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        netlist_full = _make_netlist([ic, cap])
        detections_full = auto_detect_decoupling(netlist_full)
        assert len(detections_full) >= 1

        netlist_without_ic = _make_netlist([cap])
        detections_without = auto_detect_decoupling(netlist_without_ic)
        assert detections_without == [], (
            f"No IC should mean no detections, got {detections_without}"
        )


class TestDecouplingInductionModify:
    """Inductive step: modifying component attributes."""

    def test_footprint_change_changes_classification(self):
        """Changing cap footprint from small (0603/BYPASS) to large (ELEC) changes to BULK."""
        ic = _make_ic("U1")
        cap_small = _make_cap("C1", "0603", ["VCC", "GND"])
        netlist = _make_netlist([ic, cap_small])
        detections = auto_detect_decoupling_set(netlist)
        assert len(detections) >= 1
        for d in detections:
            if d.cap_ref == "C1":
                assert d.classification == DecouplingClass.BYPASS, (
                    f"0603 footprint should be BYPASS, got {d.classification}"
                )

        cap_large = _make_cap("C1", "ELEC_D12_5", ["VCC", "GND"])
        netlist_large = _make_netlist([ic, cap_large])
        detections_large = auto_detect_decoupling_set(netlist_large)
        for d in detections_large:
            if d.cap_ref == "C1":
                assert d.classification == DecouplingClass.BULK, (
                    f"ELEC_D12_5 footprint should be BULK, got {d.classification}"
                )

    def test_non_power_net_modify_to_power_produces_detection(self):
        """Changing cap from signal net to power net produces detection."""
        ic = _make_ic("U1", nets=["SIG1", "SIG2", "CLK", "RST"])
        cap = _make_cap("C1", "0603", ["SIG1", "GND"])
        netlist = _make_netlist([ic, cap])
        assert auto_detect_decoupling(netlist) == []

        cap_power = _make_cap("C1", "0603", ["VCC", "GND"])
        ic_power = _make_ic("U1", nets=["VCC", "GND", "SIG1", "SIG2"])
        netlist_power = _make_netlist([ic_power, cap_power])
        rules = auto_detect_decoupling(netlist_power)
        assert len(rules) >= 1, f"Expected detection with power net, got {len(rules)}"


class TestDecouplingInductionInvariants:
    """Invariants that hold across all add/remove/modify operations."""

    @pytest.mark.property
    @given(st.lists(st.sampled_from(["C1", "C2", "C3"]), min_size=1, max_size=3, unique=True))
    @settings(max_examples=30, deadline=30000)
    def test_detection_count_monotonic_with_caps(self, cap_refs):
        """More capacitors never reduce total detection count on same IC set."""
        ic = _make_ic("U1")
        caps = [_make_cap(ref, "0603", ["VCC", "GND"]) for ref in cap_refs]
        netlist = _make_netlist([ic] + caps)
        dset = auto_detect_decoupling_set(netlist)
        assert len(dset) >= len(cap_refs), (
            f"Expected >= {len(cap_refs)} detections for {cap_refs} caps, got {len(dset)}"
        )

    def test_detection_is_deterministic(self):
        """Same netlist always produces same detections."""
        ic = _make_ic("U1")
        caps = [_make_cap("C1", "0603", ["VCC", "GND"]),
                _make_cap("C2", "0603", ["VCC", "GND"])]
        netlist = _make_netlist([ic] + caps)
        d1 = auto_detect_decoupling_set(netlist)
        d2 = auto_detect_decoupling_set(netlist)
        assert len(d1) == len(d2)
        r1 = auto_detect_decoupling(netlist)
        r2 = auto_detect_decoupling(netlist)
        assert len(r1) == len(r2)

    def test_bypass_has_tighter_distance_than_bulk(self):
        """BYPASS capacitors require tighter placement than BULK."""
        assert DecouplingClass.BYPASS.max_distance_mm < DecouplingClass.BULK.max_distance_mm
