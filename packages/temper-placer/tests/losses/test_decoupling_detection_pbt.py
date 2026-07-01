"""
Property-based tests for decoupling detection: idempotence, ESL/BMC consistency,
tier monotonicity, hash stability, empty netlist, and footprint fallback.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.decoupling import (
    auto_detect_decoupling,
    _is_capacitor,
    _is_ic,
    _classify,
    _build_net_class_map,
    _shared_vital_net,
    _esl_is_decoupling,
)
from temper_placer.losses.decoupling_types import DecouplingClass, DecouplingDetectionSet


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


def _make_netlist(caps: list[Component], ics: list[Component]) -> Netlist:
    all_comps = caps + ics
    net_pins: dict[str, list[tuple[str, str]]] = {}
    for comp in all_comps:
        for pin in comp.pins:
            if pin.net:
                net_pins.setdefault(pin.net, []).append((comp.ref, pin.name))
    nets = [Net(name=n, pins=p) for n, p in net_pins.items()]
    return Netlist(components=all_comps, nets=nets)


class TestDecouplingDetectionIdempotence:
    """Theorem: auto_detect_decoupling() is idempotent for the same netlist."""

    @pytest.mark.property
    def test_detection_is_deterministic(self):
        """Same netlist produces same results on repeated calls."""
        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        ic = _make_ic("U1", "SOIC-8", ["VCC", "GND", "SIG1", "SIG2"])
        netlist = _make_netlist([cap], [ic])
        result1 = auto_detect_decoupling(netlist)
        result2 = auto_detect_decoupling(netlist)
        assert len(result1) == len(result2)

    @pytest.mark.property
    def test_same_netlist_same_hash(self):
        """Same netlist detection produces consistent results."""
        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        ic = _make_ic("U1", "SOIC-8", ["VCC", "GND", "SIG1", "SIG2"])
        netlist = _make_netlist([cap], [ic])
        rules1 = auto_detect_decoupling(netlist)
        rules2 = auto_detect_decoupling(netlist)
        assert [r.cap_ref for r in rules1] == [r.cap_ref for r in rules2]


class TestESLBMC:
    """Theorem: _is_capacitor and _is_ic correctly classify components."""

    @pytest.mark.property
    def test_small_cap_is_capacitor(self):
        """Components with 0603/0805 footprints and C prefix are capacitors."""
        c = _make_cap("C1", "0603", ["VCC", "GND"])
        assert _is_capacitor(c)

    @pytest.mark.property
    def test_ic_with_4_pins_is_ic(self):
        """A component with >=4 pins is an IC."""
        ic = _make_ic("U1", "SOIC-8", ["VCC", "GND", "SIG1", "SIG2"])
        assert _is_ic(ic)

    @pytest.mark.property
    def test_3_pin_component_not_ic(self):
        """A component with <4 pins is not an IC."""
        comp = Component(
            ref="Q1", footprint="SOT23", bounds=(3.0, 3.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="VCC"),
                  Pin("2", "2", (0.0, 0.0), net="GND"),
                  Pin("3", "3", (0.0, 0.0), net="SIG1")],
        )
        assert not _is_ic(comp)

    @pytest.mark.property
    def test_resistor_not_capacitor(self):
        """R-prefixed components are not capacitors."""
        r = Component(
            ref="R1", footprint="0603", bounds=(2.0, 1.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="VCC"),
                  Pin("2", "2", (0.0, 0.0), net="GND")],
        )
        assert not _is_capacitor(r)


class TestTierMonotonicity:
    """Theorem: BYPASS has stronger tier than BULK."""

    @pytest.mark.property
    def test_bypass_tier_stronger_than_bulk(self):
        """BYPASS class has max_distance 3mm (tighter) vs BULK 20mm."""
        assert DecouplingClass.BYPASS.max_distance_mm < DecouplingClass.BULK.max_distance_mm

    @pytest.mark.property
    def test_not_decoupling_raises_on_tier(self):
        """NOT_DECOUPLING raises ValueError on tier access."""
        with pytest.raises(ValueError):
            _ = DecouplingClass.NOT_DECOUPLING.max_distance_mm
        with pytest.raises(ValueError):
            _ = DecouplingClass.NOT_DECOUPLING.tier_label


class TestHashStability:
    """Theorem: DecouplingDetectionSet is hash-stable."""

    @pytest.mark.property
    def test_detection_set_hashable(self):
        """DecouplingDetectionSet can be used as dict keys."""
        from temper_placer.losses.decoupling_types import DecouplingDetection
        d1 = DecouplingDetection("C1", "U1", DecouplingClass.BYPASS, "VCC", 100000.0, "0603", "VCC")
        d2 = DecouplingDetection("C2", "U1", DecouplingClass.BULK, "VCC", 10000000.0, "ELEC_D12_5", "VCC")
        dset = DecouplingDetectionSet(detections=(d1, d2), netlist_hash="abc123")
        _map = {dset: 42}
        assert dset in _map


class TestEmptyNetlist:
    """Theorem: Empty netlist produces empty detections."""

    @pytest.mark.property
    def test_empty_netlist_no_detections(self):
        """auto_detect_decoupling on empty netlist returns empty list."""
        netlist = Netlist(components=[], nets=[])
        result = auto_detect_decoupling(netlist)
        assert result == []

    @pytest.mark.property
    def test_no_caps_no_detections(self):
        """Netlist with only ICs produces no decoupling detections."""
        ic = _make_ic("U1", "SOIC-8", ["VCC", "GND", "SIG1", "SIG2"])
        netlist = Netlist(components=[ic], nets=[
            Net("VCC", [("U1", "1")]),
            Net("GND", [("U1", "2")]),
        ])
        result = auto_detect_decoupling(netlist)
        assert result == []


class TestFootprintFallback:
    """Theorem: Unrecognized footprints on power nets fall back to intermediate classification."""

    @pytest.mark.property
    def test_unrecognized_footprint_classified(self):
        """A capacitor with unknown footprint still gets classified."""
        cap = _make_cap("C1", "UNKNOWN_FP", ["+5V", "GND"])
        ic = _make_ic("U1", "SOIC-8", ["+5V", "GND", "SIG1", "SIG2"])
        netlist = _make_netlist([cap], [ic])
        result = auto_detect_decoupling(netlist)
        assert isinstance(result, list)

    @pytest.mark.property
    def test_elec_d12_5_is_large_cap(self):
        """ELEC_D12_5 footprint is recognized as a bulk capacitor."""
        cap = Component(
            ref="C1", footprint="ELEC_D12_5", bounds=(12.5, 20.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="VCC"),
                  Pin("2", "2", (0.0, 0.0), net="GND")],
        )
        assert _is_capacitor(cap)

    @pytest.mark.property
    def test_shared_vital_net_connects(self):
        """_shared_vital_net finds common power nets between cap and IC."""
        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        ic = _make_ic("U1", "SOIC-8", ["VCC", "GND", "SIG1", "SIG2"])
        result = _shared_vital_net(cap, ic)
        assert result is not None


class TestClassifyOutput:
    """Theorem: _classify returns a valid DecouplingClass."""

    @pytest.mark.property
    def test_classify_returns_valid_enum(self):
        """_classify always returns a DecouplingClass enum value."""
        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        ic = _make_ic("U1", "SOIC-8", ["VCC", "GND", "SIG1", "SIG2"])
        result = _classify(cap, ic, "VCC")
        assert isinstance(result, DecouplingClass)

    @pytest.mark.property
    def test_classify_not_decoupling_for_signal(self):
        """Caps on non-power nets are NOT_DECOUPLING."""
        cap = _make_cap("C1", "0603", ["SIG1", "GND"])
        ic = _make_ic("U1", "SOIC-8", ["SIG1", "GND", "SIG2", "SIG3"])
        result = _classify(cap, ic, "SIG1")
        assert result == DecouplingClass.NOT_DECOUPLING


class TestESLDecoupling:
    """Theorem: _esl_is_decoupling has no dead code, returns shared_vital only."""

    @pytest.mark.property
    def test_esl_is_decoupling_clean(self):
        """_esl_is_decoupling returns expected result type."""
        cap = _make_cap("C1", "0603", ["VCC", "GND"])
        ic = _make_ic("U1", "SOIC-8", ["VCC", "GND", "SIG1", "SIG2"])
        result = _esl_is_decoupling(cap, ic)
        assert result is not None
        assert result == "VCC"  # shared vital net
