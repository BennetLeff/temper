"""Tests for derivation module."""

from unittest.mock import MagicMock

from temper_placer.core.netlist import Component, Net, Netlist
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


class TestDeriveConstraintsFromSpec:
    """Tests for derive_constraints_from_spec."""

    def test_emi_max_loop_area(self):
        """EMI loop area specs produce max_dist and max_area_mm2 keys."""
        spec = PcbSpecification(
            name="test",
            emi=EMISpec(max_loop_area_mm2={"gate_drive": 25.0, "power_loop": 100.0}),
        )
        netlist = Netlist()
        result = derive_constraints_from_spec(spec, netlist)
        assert "gate_drive_max_dist" in result
        assert "gate_drive_max_area_mm2" in result
        assert result["gate_drive_max_area_mm2"] == 25.0
        assert "power_loop_max_dist" in result
        assert "power_loop_max_area_mm2" in result
        assert result["power_loop_max_area_mm2"] == 100.0

    def test_thermal_power_dissipation(self):
        """Thermal power dissipation produces min_clearance keys."""
        spec = PcbSpecification(
            name="test",
            thermal=ThermalSpec(
                power_dissipation={"Q1": 5.0, "Q2": 10.0}
            ),
        )
        netlist = Netlist()
        result = derive_constraints_from_spec(spec, netlist)
        assert result["Q1_min_clearance"] == pytest.approx(10.0)  # 5.0 * 2.0
        assert result["Q2_min_clearance"] == pytest.approx(20.0)  # 10.0 * 2.0

    def test_signal_integrity_max_length(self):
        """Signal integrity max lengths produce max_placement_dist keys."""
        spec = PcbSpecification(
            name="test",
            signal_integrity=SignalIntegritySpec(
                max_length_mm={"SPI_CLK": 100.0, "SPI_MISO": 150.0}
            ),
        )
        netlist = Netlist()
        result = derive_constraints_from_spec(spec, netlist)
        assert "SPI_CLK_max_placement_dist" in result
        assert result["SPI_CLK_max_placement_dist"] == pytest.approx(100.0 / 1.5)
        assert "SPI_MISO_max_placement_dist" in result

    def test_safety_isolation(self):
        """Safety spec produces hv_lv_isolation_mm."""
        spec = PcbSpecification(
            name="test",
            safety=SafetySpec(mains_voltage_v=230.0, pollution_degree=2),
        )
        netlist = Netlist()
        result = derive_constraints_from_spec(spec, netlist)
        assert "hv_lv_isolation_mm" in result
        assert isinstance(result["hv_lv_isolation_mm"], float)
        assert result["hv_lv_isolation_mm"] > 0

    def test_no_safety_falls_back_to_default(self):
        """Without safety spec, defaults to 6.5mm with a warning."""
        import warnings

        spec = PcbSpecification(name="test")
        netlist = Netlist()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = derive_constraints_from_spec(spec, netlist)
        assert result["hv_lv_isolation_mm"] == 6.5
        assert any("No safety spec" in str(warning.message) for warning in w)


class TestApplyDerivedConstraints:
    """Tests for apply_derived_constraints."""

    def test_no_pcl_returns_netlist(self):
        """When pcl_constraints is None, returns the netlist unchanged."""
        comps = [Component(ref="Q1", footprint="TO-220", bounds=(10, 10))]
        netlist = Netlist(components=comps, nets=[])
        result = apply_derived_constraints(netlist, {}, None)
        assert result is netlist

    def test_clearance_key_adds_separated_constraint(self):
        """_min_clearance keys produce SeparatedConstraint entries."""
        derived = {"Q1_min_clearance": 10.0}
        comps = [Component(ref="Q1", footprint="TO-220", bounds=(10, 10))]
        netlist = Netlist(components=comps, nets=[])

        pcl = MagicMock()
        result = apply_derived_constraints(netlist, derived, pcl)
        assert result is pcl
        pcl.add.assert_called_once()
        call_arg = pcl.add.call_args[0][0]
        assert call_arg.a == "Q1"
        assert call_arg.b == "*"
        assert call_arg.min_distance_mm == 10.0

    def test_non_clearance_keys_ignored(self):
        """Keys not ending in _min_clearance don't produce constraints."""
        derived = {"hv_lv_isolation_mm": 6.5, "gate_drive_max_dist": 5.0}
        netlist = Netlist()
        pcl = MagicMock()
        result = apply_derived_constraints(netlist, derived, pcl)
        assert result is pcl
        pcl.add.assert_not_called()


import pytest
