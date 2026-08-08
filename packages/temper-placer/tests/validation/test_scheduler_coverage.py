"""Tests for validation.scheduler module (config objects)."""

from temper_placer.validation.scheduler import (
    DRCScheduleConfig,
    SpiceScheduleConfig,
    SpiceSimulationConfig,
    ValidationScheduleConfig,
)


class TestDRCScheduleConfig:
    """Tests for DRCScheduleConfig."""

    def test_defaults(self):
        c = DRCScheduleConfig()
        assert c.enabled is True
        assert c.interval == 100
        assert c.final_phase_interval == 20
        assert c.weight == 1.0
        assert c.fail_on_errors is False
        assert c.max_errors == 0

    def test_to_dict(self):
        c = DRCScheduleConfig(
            enabled=False, interval=50, final_phase_interval=10,
            weight=2.0, fail_on_errors=True, max_errors=5,
        )
        d = c.to_dict()
        assert d["enabled"] is False
        assert d["interval"] == 50
        assert d["final_phase_interval"] == 10
        assert d["weight"] == 2.0
        assert d["fail_on_errors"] is True
        assert d["max_errors"] == 5


class TestSpiceSimulationConfig:
    """Tests for SpiceSimulationConfig."""

    def test_defaults(self):
        c = SpiceSimulationConfig(name="gate_drive")
        assert c.name == "gate_drive"
        assert c.enabled is True
        assert c.weight == 1.0
        assert c.loop_components == []
        assert c.parameters == {}

    def test_to_dict(self):
        c = SpiceSimulationConfig(
            name="bootstrap",
            enabled=False,
            weight=0.5,
            loop_components=["U1", "C1"],
            parameters={"cap": 1e-6},
        )
        d = c.to_dict()
        assert d["name"] == "bootstrap"
        assert d["enabled"] is False
        assert d["weight"] == 0.5
        assert d["loop_components"] == ["U1", "C1"]
        assert d["parameters"] == {"cap": 1e-6}


class TestSpiceScheduleConfig:
    """Tests for SpiceScheduleConfig."""

    def test_defaults(self):
        c = SpiceScheduleConfig()
        assert c.enabled is False
        assert c.interval == 200
        assert c.final_phase_interval == 50
        # Defaults should create simulation configs in __post_init__
        assert len(c.simulations) >= 2

    def test_get_enabled_simulations(self):
        c = SpiceScheduleConfig()
        enabled = c.get_enabled_simulations()
        assert len(enabled) >= 1
        for sim in enabled:
            assert sim.enabled is True

    def test_get_weights(self):
        c = SpiceScheduleConfig()
        weights = c.get_weights()
        assert isinstance(weights, dict)
        assert len(weights) >= 1

    def test_to_dict(self):
        c = SpiceScheduleConfig(enabled=True, interval=100)
        d = c.to_dict()
        assert d["enabled"] is True
        assert d["interval"] == 100
        assert "simulations" in d


class TestValidationScheduleConfig:
    """Tests for ValidationScheduleConfig."""

    def test_default_construction(self):
        c = ValidationScheduleConfig()
        assert c.drc is not None
        assert c.spice is not None

    def test_to_dict_and_from_dict_roundtrip(self):
        c1 = ValidationScheduleConfig()
        d = c1.to_dict()
        c2 = ValidationScheduleConfig.from_dict(d)
        assert c2.drc.enabled == c1.drc.enabled
        assert c2.spice.enabled == c1.spice.enabled
        assert c2.drc.interval == c1.drc.interval
