"""
Tests for validation scheduler module.

Tests cover:
- Configuration loading from YAML
- Default configuration creation
- DRC scheduling logic
- SPICE scheduling logic
- Final phase detection
- Serialization round-trip
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from temper_placer.validation.scheduler import (
    DRCScheduleConfig,
    SpiceScheduleConfig,
    SpiceSimulationConfig,
    ValidationScheduleConfig,
    ValidationScheduler,
    create_default_config,
    load_validation_config,
)


class TestDRCScheduleConfig:
    """Tests for DRC schedule configuration."""

    def test_default_values(self):
        """Test DRC config has sensible defaults."""
        config = DRCScheduleConfig()
        assert config.enabled is True
        assert config.interval == 100
        assert config.final_phase_interval == 20
        assert config.weight == 1.0
        assert config.fail_on_errors is False
        assert config.max_errors == 0

    def test_custom_values(self):
        """Test DRC config accepts custom values."""
        config = DRCScheduleConfig(
            enabled=False,
            interval=50,
            final_phase_interval=10,
            weight=2.0,
            fail_on_errors=True,
            max_errors=5,
        )
        assert config.enabled is False
        assert config.interval == 50
        assert config.final_phase_interval == 10
        assert config.weight == 2.0
        assert config.fail_on_errors is True
        assert config.max_errors == 5

    def test_to_dict(self):
        """Test DRC config serialization."""
        config = DRCScheduleConfig(interval=200)
        d = config.to_dict()
        assert d["interval"] == 200
        assert "enabled" in d
        assert "weight" in d


class TestSpiceSimulationConfig:
    """Tests for individual SPICE simulation configuration."""

    def test_default_values(self):
        """Test SPICE simulation config defaults."""
        config = SpiceSimulationConfig(name="test_sim")
        assert config.name == "test_sim"
        assert config.enabled is True
        assert config.weight == 1.0
        assert config.loop_components == []
        assert config.parameters == {}

    def test_custom_values(self):
        """Test SPICE simulation config with custom values."""
        config = SpiceSimulationConfig(
            name="gate_drive",
            enabled=True,
            weight=1.5,
            loop_components=["U_GD", "Q1", "R_GATE"],
            parameters={"gate_resistance": 4.7},
        )
        assert config.name == "gate_drive"
        assert config.weight == 1.5
        assert "U_GD" in config.loop_components
        assert config.parameters["gate_resistance"] == 4.7

    def test_to_dict(self):
        """Test SPICE simulation config serialization."""
        config = SpiceSimulationConfig(
            name="test",
            loop_components=["A", "B"],
            parameters={"x": 1},
        )
        d = config.to_dict()
        assert d["name"] == "test"
        assert d["loop_components"] == ["A", "B"]
        assert d["parameters"]["x"] == 1


class TestSpiceScheduleConfig:
    """Tests for SPICE schedule configuration."""

    def test_default_values(self):
        """Test SPICE config has sensible defaults."""
        config = SpiceScheduleConfig()
        assert config.enabled is False  # Disabled by default (expensive)
        assert config.interval == 200
        assert config.final_phase_interval == 50
        assert config.fail_on_errors is False

    def test_default_simulations_created(self):
        """Test default simulations are created if none provided."""
        config = SpiceScheduleConfig()
        assert len(config.simulations) == 3
        names = [s.name for s in config.simulations]
        assert "gate_drive" in names
        assert "bootstrap_charging" in names
        assert "power_integrity" in names

    def test_custom_simulations(self):
        """Test custom simulations override defaults."""
        config = SpiceScheduleConfig(
            simulations=[
                SpiceSimulationConfig(name="custom_sim", weight=2.0),
            ]
        )
        assert len(config.simulations) == 1
        assert config.simulations[0].name == "custom_sim"

    def test_get_enabled_simulations(self):
        """Test filtering for enabled simulations."""
        config = SpiceScheduleConfig(
            simulations=[
                SpiceSimulationConfig(name="enabled_1", enabled=True),
                SpiceSimulationConfig(name="disabled", enabled=False),
                SpiceSimulationConfig(name="enabled_2", enabled=True),
            ]
        )
        enabled = config.get_enabled_simulations()
        assert len(enabled) == 2
        names = [s.name for s in enabled]
        assert "enabled_1" in names
        assert "enabled_2" in names
        assert "disabled" not in names

    def test_get_weights(self):
        """Test getting weights for enabled simulations."""
        config = SpiceScheduleConfig(
            simulations=[
                SpiceSimulationConfig(name="sim_a", enabled=True, weight=1.0),
                SpiceSimulationConfig(name="sim_b", enabled=True, weight=0.5),
                SpiceSimulationConfig(name="sim_c", enabled=False, weight=2.0),
            ]
        )
        weights = config.get_weights()
        assert weights["sim_a"] == 1.0
        assert weights["sim_b"] == 0.5
        assert "sim_c" not in weights  # Disabled

    def test_to_dict(self):
        """Test SPICE config serialization."""
        config = SpiceScheduleConfig(enabled=True, interval=100)
        d = config.to_dict()
        assert d["enabled"] is True
        assert d["interval"] == 100
        assert "simulations" in d


class TestValidationScheduleConfig:
    """Tests for complete validation schedule configuration."""

    def test_default_values(self):
        """Test schedule config has sensible defaults."""
        config = ValidationScheduleConfig()
        assert config.enabled is True
        assert config.log_results is True
        assert config.final_phase_epochs == 500
        assert isinstance(config.drc, DRCScheduleConfig)
        assert isinstance(config.spice, SpiceScheduleConfig)

    def test_from_dict(self):
        """Test creating config from dictionary."""
        raw = {
            "enabled": False,
            "log_results": False,
            "final_phase_epochs": 1000,
            "drc": {
                "enabled": True,
                "interval": 50,
            },
            "spice": {
                "enabled": True,
                "interval": 100,
                "simulations": [
                    {"name": "test_sim", "weight": 1.5},
                ],
            },
        }
        config = ValidationScheduleConfig.from_dict(raw)
        assert config.enabled is False
        assert config.log_results is False
        assert config.final_phase_epochs == 1000
        assert config.drc.interval == 50
        assert config.spice.enabled is True
        assert config.spice.interval == 100
        assert len(config.spice.simulations) == 1

    def test_from_dict_with_nested_validation_key(self):
        """Test parsing when config is under 'validation' key."""
        raw = {
            "validation": {
                "enabled": True,
                "final_phase_epochs": 200,
            }
        }
        # from_dict expects the inner dict directly, load() handles the nesting
        config = ValidationScheduleConfig.from_dict(raw.get("validation", raw))
        assert config.final_phase_epochs == 200

    def test_load_from_yaml_file(self):
        """Test loading config from YAML file."""
        yaml_content = """
validation:
  enabled: true
  log_results: true
  final_phase_epochs: 300
  drc:
    enabled: true
    interval: 75
    final_phase_interval: 15
  spice:
    enabled: true
    interval: 150
    simulations:
      - name: gate_drive
        enabled: true
        weight: 1.0
        loop_components: [U_GD, Q1]
        parameters:
          gate_resistance: 5.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = ValidationScheduleConfig.load(Path(f.name))

        assert config.enabled is True
        assert config.final_phase_epochs == 300
        assert config.drc.interval == 75
        assert config.drc.final_phase_interval == 15
        assert config.spice.enabled is True
        assert config.spice.interval == 150
        assert len(config.spice.simulations) == 1
        assert config.spice.simulations[0].name == "gate_drive"
        assert config.spice.simulations[0].parameters["gate_resistance"] == 5.0

    def test_to_dict_and_back(self):
        """Test serialization round-trip."""
        original = ValidationScheduleConfig(
            enabled=True,
            final_phase_epochs=600,
        )
        original.drc.interval = 123
        original.spice.enabled = True
        original.spice.interval = 456

        # Round trip
        d = original.to_dict()
        restored = ValidationScheduleConfig.from_dict(d)

        assert restored.enabled == original.enabled
        assert restored.final_phase_epochs == original.final_phase_epochs
        assert restored.drc.interval == original.drc.interval
        assert restored.spice.enabled == original.spice.enabled
        assert restored.spice.interval == original.spice.interval

    def test_save_and_load(self):
        """Test saving to file and loading back."""
        config = ValidationScheduleConfig()
        config.final_phase_epochs = 999

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_config.yaml"
            config.save(path)

            # Verify file was created
            assert path.exists()

            # Load and verify
            loaded = ValidationScheduleConfig.load(path)
            assert loaded.final_phase_epochs == 999


class TestValidationScheduler:
    """Tests for validation scheduler logic."""

    def test_initialization(self):
        """Test scheduler initialization."""
        config = ValidationScheduleConfig()
        scheduler = ValidationScheduler(config, total_epochs=5000)
        assert scheduler.total_epochs == 5000
        assert scheduler.config is config

    def test_is_final_phase(self):
        """Test final phase detection."""
        config = ValidationScheduleConfig()
        config.final_phase_epochs = 500
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # Before final phase
        assert scheduler.is_final_phase(0) is False
        assert scheduler.is_final_phase(1000) is False
        assert scheduler.is_final_phase(4499) is False

        # At and after final phase start (5000 - 500 = 4500)
        assert scheduler.is_final_phase(4500) is True
        assert scheduler.is_final_phase(4999) is True

    def test_get_drc_interval_normal_phase(self):
        """Test DRC interval during normal phase."""
        config = ValidationScheduleConfig()
        config.drc.interval = 100
        config.drc.final_phase_interval = 20
        config.final_phase_epochs = 500
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # Normal phase
        assert scheduler.get_drc_interval(0) == 100
        assert scheduler.get_drc_interval(1000) == 100
        assert scheduler.get_drc_interval(4499) == 100

    def test_get_drc_interval_final_phase(self):
        """Test DRC interval during final phase."""
        config = ValidationScheduleConfig()
        config.drc.interval = 100
        config.drc.final_phase_interval = 20
        config.final_phase_epochs = 500
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # Final phase
        assert scheduler.get_drc_interval(4500) == 20
        assert scheduler.get_drc_interval(4999) == 20

    def test_should_run_drc_at_intervals(self):
        """Test DRC runs at correct intervals."""
        config = ValidationScheduleConfig()
        config.enabled = True
        config.drc.enabled = True
        config.drc.interval = 100
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # Should run at multiples of 100
        assert scheduler.should_run_drc(0) is True
        assert scheduler.should_run_drc(100) is True
        assert scheduler.should_run_drc(200) is True

        # Should not run at non-multiples
        assert scheduler.should_run_drc(50) is False
        assert scheduler.should_run_drc(101) is False
        assert scheduler.should_run_drc(199) is False

    def test_should_run_drc_at_last_epoch(self):
        """Test DRC always runs at last epoch."""
        config = ValidationScheduleConfig()
        config.enabled = True
        config.drc.enabled = True
        config.drc.interval = 100
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # Last epoch (4999) should always run
        assert scheduler.should_run_drc(4999) is True

    def test_should_run_drc_respects_disabled(self):
        """Test DRC doesn't run when disabled."""
        config = ValidationScheduleConfig()
        config.drc.enabled = False
        scheduler = ValidationScheduler(config, total_epochs=5000)

        assert scheduler.should_run_drc(0) is False
        assert scheduler.should_run_drc(100) is False

    def test_should_run_drc_respects_master_enabled(self):
        """Test DRC doesn't run when validation is globally disabled."""
        config = ValidationScheduleConfig()
        config.enabled = False
        config.drc.enabled = True
        scheduler = ValidationScheduler(config, total_epochs=5000)

        assert scheduler.should_run_drc(0) is False

    def test_should_run_spice_at_intervals(self):
        """Test SPICE runs at correct intervals."""
        config = ValidationScheduleConfig()
        config.enabled = True
        config.spice.enabled = True
        config.spice.interval = 200
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # Should run at multiples of 200
        assert scheduler.should_run_spice(0) is True
        assert scheduler.should_run_spice(200) is True
        assert scheduler.should_run_spice(400) is True

        # Should not run at non-multiples
        assert scheduler.should_run_spice(100) is False
        assert scheduler.should_run_spice(201) is False

    def test_should_run_spice_at_last_epoch(self):
        """Test SPICE always runs at last epoch."""
        config = ValidationScheduleConfig()
        config.enabled = True
        config.spice.enabled = True
        config.spice.interval = 200
        scheduler = ValidationScheduler(config, total_epochs=5000)

        assert scheduler.should_run_spice(4999) is True

    def test_should_run_spice_respects_disabled(self):
        """Test SPICE doesn't run when disabled."""
        config = ValidationScheduleConfig()
        config.spice.enabled = False
        scheduler = ValidationScheduler(config, total_epochs=5000)

        assert scheduler.should_run_spice(0) is False

    def test_mark_run_prevents_double_run(self):
        """Test marking epochs prevents double execution."""
        config = ValidationScheduleConfig()
        config.enabled = True
        config.drc.enabled = True
        config.drc.interval = 100
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # First check - should run
        assert scheduler.should_run_drc(100) is True
        scheduler.mark_drc_run(100)

        # Second check - should not run (already marked)
        assert scheduler.should_run_drc(100) is False

    def test_get_spice_config(self):
        """Test getting config for specific simulation."""
        config = ValidationScheduleConfig()
        scheduler = ValidationScheduler(config, total_epochs=5000)

        gate_drive = scheduler.get_spice_config("gate_drive")
        assert gate_drive is not None
        assert gate_drive.name == "gate_drive"

        # Non-existent simulation
        nonexistent = scheduler.get_spice_config("nonexistent")
        assert nonexistent is None

    def test_get_enabled_spice_simulations(self):
        """Test getting list of enabled simulations."""
        config = ValidationScheduleConfig()
        # Default has 3 enabled simulations
        scheduler = ValidationScheduler(config, total_epochs=5000)

        enabled = scheduler.get_enabled_spice_simulations()
        assert len(enabled) == 3

    def test_get_spice_weights(self):
        """Test getting simulation weights."""
        config = ValidationScheduleConfig()
        scheduler = ValidationScheduler(config, total_epochs=5000)

        weights = scheduler.get_spice_weights()
        assert "gate_drive" in weights
        assert "bootstrap_charging" in weights
        assert "power_integrity" in weights

    def test_summary(self):
        """Test human-readable summary generation."""
        config = ValidationScheduleConfig()
        scheduler = ValidationScheduler(config, total_epochs=5000)

        summary = scheduler.summary()
        assert "Validation Schedule" in summary
        assert "DRC" in summary
        assert "SPICE" in summary
        assert "5000" in summary  # Total epochs


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_load_validation_config(self):
        """Test load_validation_config convenience function."""
        yaml_content = """
validation:
  final_phase_epochs: 123
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = load_validation_config(Path(f.name))

        assert config.final_phase_epochs == 123

    def test_create_default_config(self):
        """Test create_default_config convenience function."""
        config = create_default_config()
        assert isinstance(config, ValidationScheduleConfig)
        assert config.enabled is True


class TestLoadActualConfigFile:
    """Tests that load the actual configs/temper/validation.yaml file."""

    @pytest.fixture
    def config_path(self):
        """Path to actual config file."""
        return Path(__file__).parent.parent.parent / "configs" / "temper" / "validation.yaml"

    def test_load_actual_config(self, config_path):
        """Test loading the actual validation.yaml config."""
        if not config_path.exists():
            pytest.skip(f"Config file not found: {config_path}")

        config = ValidationScheduleConfig.load(config_path)

        # Verify basic structure
        assert config.enabled is True
        assert config.log_results is True
        assert config.final_phase_epochs > 0

        # Verify DRC config
        assert config.drc.enabled is True
        assert config.drc.interval > 0
        assert config.drc.final_phase_interval > 0
        assert config.drc.final_phase_interval < config.drc.interval

        # Verify SPICE config structure (may be disabled)
        assert config.spice.interval > 0
        assert len(config.spice.simulations) > 0

        # Verify known simulations exist
        sim_names = [s.name for s in config.spice.simulations]
        assert "gate_drive" in sim_names
        assert "bootstrap_charging" in sim_names
        assert "power_integrity" in sim_names

    def test_actual_config_creates_working_scheduler(self, config_path):
        """Test that actual config creates a working scheduler."""
        if not config_path.exists():
            pytest.skip(f"Config file not found: {config_path}")

        config = ValidationScheduleConfig.load(config_path)
        scheduler = ValidationScheduler(config, total_epochs=5000)

        # Should be able to check scheduling
        assert isinstance(scheduler.should_run_drc(0), bool)
        assert isinstance(scheduler.should_run_spice(0), bool)

        # Summary should work
        summary = scheduler.summary()
        assert len(summary) > 0
