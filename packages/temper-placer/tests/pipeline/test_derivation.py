from unittest.mock import MagicMock

import pytest

from temper_placer.core.specification import (
    EMISpec,
    PcbSpecification,
    SafetySpec,
    ThermalSpec,
)
from temper_placer.pipeline.derivation import derive_constraints_from_spec


def test_derive_constraints_from_spec():
    """Existing test: EMI, thermal derivation still work."""
    spec = PcbSpecification(
        emi=EMISpec(max_loop_area_mm2={"gate": 100.0}),
        thermal=ThermalSpec(power_dissipation={"Q1": 10.0})
    )

    mock_netlist = MagicMock()
    derived = derive_constraints_from_spec(spec, mock_netlist)

    # 100mm2 area -> 10mm side -> 8mm max dist
    assert derived["gate_max_dist"] == pytest.approx(8.0)

    # 10W thermal -> 20mm min clearance
    assert derived["Q1_min_clearance"] == pytest.approx(20.0)


class TestSafetyDerivation:
    """Tests for the SafetySpec-driven HV/LV isolation derivation."""

    def test_safety_spec_240v_pd2_gives_3_0mm(self):
        """MAINS_240V (230V), pollution degree 2 → clearance = 3.0mm."""
        spec = PcbSpecification(
            safety=SafetySpec(mains_voltage_v=230.0, pollution_degree=2),
        )
        derived = derive_constraints_from_spec(spec, MagicMock())
        assert derived["hv_lv_isolation_mm"] == pytest.approx(3.0)

    def test_no_safety_spec_falls_back_to_6_5mm(self):
        """When safety is None, backward-compatible: hardcoded 6.5mm."""
        spec = PcbSpecification()
        assert spec.safety is None
        derived = derive_constraints_from_spec(spec, MagicMock())
        assert derived["hv_lv_isolation_mm"] == pytest.approx(6.5)

    def test_pollution_degree_3_multiplies_clearance(self):
        """PD3 applies 1.5x multiplier on the base clearance."""
        spec = PcbSpecification(
            safety=SafetySpec(mains_voltage_v=230.0, pollution_degree=3),
        )
        derived = derive_constraints_from_spec(spec, MagicMock())
        # MAINS_240V base = 3.0, PD3 multiplier = 1.5 → 4.5
        assert derived["hv_lv_isolation_mm"] == pytest.approx(4.5)

    def test_120v_maps_to_mains_120v(self):
        """120V mains maps to MAINS_120V → clearance = 1.5mm (PD2)."""
        spec = PcbSpecification(
            safety=SafetySpec(mains_voltage_v=120.0, pollution_degree=2),
        )
        derived = derive_constraints_from_spec(spec, MagicMock())
        assert derived["hv_lv_isolation_mm"] == pytest.approx(1.5)
