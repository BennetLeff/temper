"""Unit tests for sub-module constraint Pydantic models."""

import pytest
from pydantic import ValidationError

from temper_placer._constraint_types.clearance import (
    ClearanceRule,
    DifferentialPairRule,
    NetClassRule,
    SignalToHVClearance,
)
from temper_placer._constraint_types.groups import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    GroupSeparation,
    ManufacturingConstraint,
    ProximityRule,
)
from temper_placer._constraint_types.noise import NoiseDomain, NoiseIsolationRule
from temper_placer._constraint_types.routing import (
    HVExclusionZone,
    IsolationSlot,
    PlacementProximityConstraint,
    RoutingCorridor,
)
from temper_placer._constraint_types.safety import (
    BleedResistor,
    IsolationBarrier,
    SkinEffectDerating,
    SnubberRequirement,
)
from temper_placer._constraint_types.thermal import ThermalConstraint, ThermalProperties
from temper_placer._constraint_types.topology import (
    CriticalLoop,
    CriticalPath,
    MatchedLengthGroup,
    StarGroundConfig,
)


class TestClearanceRule:
    def test_construction(self):
        cr = ClearanceRule(from_class="HV", to_class="LV", clearance_mm=6.0)
        assert cr.from_class == "HV"
        assert cr.to_class == "LV"
        assert cr.clearance_mm == 6.0

    def test_negative_clearance_rejected(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            ClearanceRule(from_class="HV", to_class="LV", clearance_mm=-1.0)

    def test_zero_clearance_valid(self):
        cr = ClearanceRule(from_class="A", to_class="A", clearance_mm=0.0)
        assert cr.clearance_mm == 0.0


class TestNetClassRule:
    def test_minimal_construction(self):
        ncr = NetClassRule(name="Power")
        assert ncr.name == "Power"
        assert ncr.trace_width_mm == 0.2

    def test_full_construction(self):
        ncr = NetClassRule(
            name="HighVoltage", trace_width_mm=0.5, clearance_mm=0.3,
            max_current_rating=20.0, routing_strategy="plane_required",
        )
        assert ncr.max_current_rating == 20.0
        assert ncr.routing_strategy == "plane_required"

    def test_zero_trace_width_rejected(self):
        with pytest.raises(ValidationError):
            NetClassRule(name="X", trace_width_mm=0)


class TestComponentGroup:
    def test_minimal_construction(self):
        cg = ComponentGroup(name="pwr", components=["U1", "Q1"])
        assert cg.name == "pwr"
        assert cg.components == ["U1", "Q1"]
        assert cg.max_spread_mm == 30.0

    def test_with_proximity_rules(self):
        cg = ComponentGroup(
            name="pwr", components=["U1", "Q1"],
            proximity_rules=[ProximityRule(component_a="U1", component_b="Q1", max_distance_mm=20.0)],
        )
        assert len(cg.proximity_rules) == 1
        assert cg.proximity_rules[0].max_distance_mm == 20.0

    def test_empty_components_valid(self):
        cg = ComponentGroup(name="empty", components=[])
        assert cg.components == []


class TestComponentSpacingRule:
    def test_construction(self):
        csr = ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=2.0)
        assert csr.min_separation_mm == 2.0

    def test_negative_separation_rejected(self):
        with pytest.raises(ValidationError):
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=-1)


class TestEscapeClearance:
    def test_compute_clearance(self):
        ec = EscapeClearance(component="U_MCU")
        clearance = ec.compute_clearance(pin_count=56, pitch_mm=0.5)
        assert abs(clearance - 5.61) < 0.1


class TestCriticalLoop:
    def test_construction(self):
        cl = CriticalLoop(name="commutation", nets=["SW", "GND"])
        assert cl.name == "commutation"
        assert cl.nets == ["SW", "GND"]

    def test_negative_max_area_rejected(self):
        with pytest.raises(ValidationError):
            CriticalLoop(name="loop", nets=["A"], max_area_mm2=-1.0)


class TestCriticalPath:
    def test_construction(self):
        cp = CriticalPath(name="gate1", from_comp="U1", to_comp="Q1")
        assert cp.from_comp == "U1"
        assert cp.to_comp == "Q1"
        assert cp.max_length_mm == 50.0


class TestBleedResistor:
    def test_construction(self):
        br = BleedResistor(bus_voltage_v=340.0, target_voltage_v=50.0)
        assert br.bus_voltage_v == 340.0
        assert br.timeout_s == 5.0

    def test_zero_bus_voltage_rejected(self):
        with pytest.raises(ValidationError):
            BleedResistor(bus_voltage_v=0, target_voltage_v=0)


class TestHVExclusionZone:
    def test_construction(self):
        hz = HVExclusionZone(name="zone1", center=(10.0, 20.0), size=(5.0, 5.0))
        assert hz.center == (10.0, 20.0)
        assert hz.size == (5.0, 5.0)

    def test_negative_clearance_rejected(self):
        with pytest.raises(ValidationError):
            HVExclusionZone(name="z", center=(0, 0), size=(1, 1), clearance_mm=-1)
