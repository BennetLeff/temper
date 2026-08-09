"""Tests for derivation module."""

import pytest

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.specification import (
    EMISpec,
    PcbSpecification,
    SafetySpec,
    SignalIntegritySpec,
    ThermalSpec,
)
from temper_placer.pipeline.derivation import (
    apply_derived_constraints,
    derive_constraints_from_spec,
)


def _make_minimal_netlist() -> Netlist:
    comps = [
        Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(5, 4),
            pins=[Pin("1", "1", (0, 0))],
        ),
        Component(
            ref="R1",
            footprint="R0603",
            bounds=(1, 1),
            pins=[Pin("1", "1", (0, 0))],
        ),
    ]
    nets = [
        Net(name="NET1", pins=[("U1", "1")]),
        Net(name="NET2", pins=[("R1", "1")]),
    ]
    return Netlist(components=comps, nets=nets)


def _make_minimal_spec() -> PcbSpecification:
    return PcbSpecification(
        name="test",
        thermal=ThermalSpec(power_dissipation={"U1": 5.0, "R1": 0.5}),
        emi=EMISpec(max_loop_area_mm2={"loop1": 100.0}),
        signal_integrity=SignalIntegritySpec(max_length_mm={"NET1": 50.0}),
        safety=SafetySpec(mains_voltage_v=240, pollution_degree=2),
    )


class TestDeriveConstraintsFromSpec:
    """Tests for derive_constraints_from_spec."""

    def test_derives_emi_max_dist(self):
        """EMI loop area produces max_dist and max_area keys."""
        spec = _make_minimal_spec()
        netlist = _make_minimal_netlist()
        derived = derive_constraints_from_spec(spec, netlist)
        assert "loop1_max_dist" in derived
        assert "loop1_max_area_mm2" in derived
        # sqrt(100) * 0.8 = 8.0
        assert derived["loop1_max_dist"] == pytest.approx(8.0)

    def test_derives_thermal_clearance(self):
        """Power dissipation produces min_clearance keys."""
        spec = _make_minimal_spec()
        netlist = _make_minimal_netlist()
        derived = derive_constraints_from_spec(spec, netlist)
        # 5.0W * 2.0 = 10.0mm
        assert derived["U1_min_clearance"] == 10.0
        # 0.5W * 2.0 = 1.0mm
        assert derived["R1_min_clearance"] == 1.0

    def test_derives_signal_integrity_max_dist(self):
        """Signal integrity max length produces placement distance."""
        spec = _make_minimal_spec()
        netlist = _make_minimal_netlist()
        derived = derive_constraints_from_spec(spec, netlist)
        assert "NET1_max_placement_dist" in derived
        # 50.0 / 1.5 = 33.33...
        assert derived["NET1_max_placement_dist"] == pytest.approx(50.0 / 1.5)

    def test_derives_safety_isolation(self):
        """Safety spec produces hv_lv_isolation_mm."""
        spec = _make_minimal_spec()
        netlist = _make_minimal_netlist()
        derived = derive_constraints_from_spec(spec, netlist)
        assert "hv_lv_isolation_mm" in derived

    def test_no_safety_spec_warns_and_defaults(self):
        """Missing safety spec emits warning and uses 6.5mm default."""
        spec = PcbSpecification(
            name="no-safety",
            thermal=ThermalSpec(power_dissipation={}),
            emi=EMISpec(max_loop_area_mm2={}),
            signal_integrity=SignalIntegritySpec(max_length_mm={}),
            safety=None,
        )
        netlist = _make_minimal_netlist()
        with pytest.warns(UserWarning, match="No safety spec"):
            derived = derive_constraints_from_spec(spec, netlist)
        assert derived["hv_lv_isolation_mm"] == 6.5

    def test_empty_specs_produce_empty_derived(self):
        """Empty spec dictionaries produce only safety default."""
        spec = PcbSpecification(
            name="empty",
            thermal=ThermalSpec(power_dissipation={}),
            emi=EMISpec(max_loop_area_mm2={}),
            signal_integrity=SignalIntegritySpec(max_length_mm={}),
            safety=None,
        )
        netlist = _make_minimal_netlist()
        with pytest.warns(UserWarning):
            derived = derive_constraints_from_spec(spec, netlist)
        # Only the safety fallback should be present
        assert set(derived.keys()) == {"hv_lv_isolation_mm"}


class TestApplyDerivedConstraints:
    """Tests for apply_derived_constraints."""

    def test_without_pcl_returns_netlist(self):
        """Without PCL constraints, returns the netlist unchanged."""
        netlist = _make_minimal_netlist()
        derived = {"U1_min_clearance": 5.0}
        result = apply_derived_constraints(netlist, derived)
        assert result is netlist

    def test_with_pcl_adds_separated_constraints(self):
        """With PCL collection, adds SeparatedConstraint for each clearance."""
        from temper_placer.pcl.parser import ConstraintCollection

        netlist = _make_minimal_netlist()
        pcl = ConstraintCollection(constraints=[])
        derived = {"U1_min_clearance": 5.0, "R1_min_clearance": 3.0}
        result = apply_derived_constraints(netlist, derived, pcl)

        assert len(result.constraints) == 2
        # Check first constraint
        c0 = result.constraints[0]
        assert c0.a == "U1"
        assert c0.min_distance_mm == 5.0
        # Check second constraint
        c1 = result.constraints[1]
        assert c1.a == "R1"
        assert c1.min_distance_mm == 3.0

    def test_nested_key_endings_are_handled(self):
        """Only _min_clearance keys produce constraints."""
        from temper_placer.pcl.parser import ConstraintCollection

        netlist = _make_minimal_netlist()
        pcl = ConstraintCollection(constraints=[])
        derived = {
            "loop1_max_dist": 8.0,
            "loop1_max_area_mm2": 100.0,
            "U1_min_clearance": 10.0,
            "NET1_max_placement_dist": 33.3,
            "hv_lv_isolation_mm": 3.0,
        }
        result = apply_derived_constraints(netlist, derived, pcl)
        # Only U1_min_clearance should produce a constraint
        assert len(result.constraints) == 1
        assert result.constraints[0].a == "U1"
