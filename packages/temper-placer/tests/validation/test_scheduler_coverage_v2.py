"""Tests for validation.scheduler module — ValidationScheduler and remaining config methods."""
import tempfile
from pathlib import Path

from temper_placer.validation.scheduler import (
    DRCScheduleConfig,
    SpiceScheduleConfig,
    SpiceSimulationConfig,
    ValidationScheduleConfig,
    ValidationScheduler,
    create_default_config,
    load_validation_config,
)


class TestValidationScheduler:
    """Tests for ValidationScheduler logic."""

    def test_default_construction(self):
        config = ValidationScheduleConfig()
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.total_epochs == 5000

    def test_is_final_phase_early(self):
        config = ValidationScheduleConfig(final_phase_epochs=500)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.is_final_phase(4499) is False

    def test_is_final_phase_late(self):
        config = ValidationScheduleConfig(final_phase_epochs=500)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.is_final_phase(4500) is True

    def test_get_drc_interval_early(self):
        config = ValidationScheduleConfig(final_phase_epochs=500)
        config.drc = DRCScheduleConfig(interval=100, final_phase_interval=20)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.get_drc_interval(0) == 100
        assert s.get_drc_interval(4500) == 20

    def test_get_spice_interval_early(self):
        config = ValidationScheduleConfig(final_phase_epochs=500)
        config.spice = SpiceScheduleConfig(interval=200, final_phase_interval=50)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.get_spice_interval(0) == 200
        assert s.get_spice_interval(4500) == 50

    def test_should_run_drc_first_epoch(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=True, interval=100)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_drc(0) is True

    def test_should_run_drc_not_enabled(self):
        config = ValidationScheduleConfig(enabled=False)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_drc(0) is False

    def test_should_run_drc_drc_disabled(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=False)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_drc(0) is False

    def test_should_run_drc_already_marked(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=True, interval=100)
        s = ValidationScheduler(config, total_epochs=5000)
        s.mark_drc_run(0)
        assert s.should_run_drc(0) is False

    def test_should_run_drc_last_epoch(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=True, interval=100)
        s = ValidationScheduler(config, total_epochs=5000)
        # epoch 4999 is the last epoch, should always run
        assert s.should_run_drc(4999) is True

    def test_should_run_drc_mid_epoch(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=True, interval=100)
        s = ValidationScheduler(config, total_epochs=5000)
        # epoch 1 is not divisible by interval=100
        assert s.should_run_drc(1) is False

    def test_should_run_spice_first_epoch(self):
        config = ValidationScheduleConfig()
        config.spice = SpiceScheduleConfig(enabled=True, interval=200)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_spice(0) is True

    def test_should_run_spice_disabled(self):
        config = ValidationScheduleConfig()
        config.spice = SpiceScheduleConfig(enabled=False)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_spice(0) is False

    def test_should_run_spice_last_epoch(self):
        config = ValidationScheduleConfig()
        config.spice = SpiceScheduleConfig(enabled=True, interval=200)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_spice(4999) is True

    def test_mark_drc_run(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=True, interval=100)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_drc(0) is True
        s.mark_drc_run(0)
        assert s.should_run_drc(0) is False

    def test_mark_spice_run(self):
        config = ValidationScheduleConfig()
        config.spice = SpiceScheduleConfig(enabled=True, interval=200)
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_spice(0) is True
        s.mark_spice_run(0)
        assert s.should_run_spice(0) is False

    def test_get_spice_config_found(self):
        config = ValidationScheduleConfig()
        sim = SpiceSimulationConfig(name="my_sim", enabled=True)
        config.spice = SpiceScheduleConfig(simulations=[sim])
        s = ValidationScheduler(config, total_epochs=5000)
        result = s.get_spice_config("my_sim")
        assert result is not None
        assert result.name == "my_sim"

    def test_get_spice_config_not_found(self):
        config = ValidationScheduleConfig()
        s = ValidationScheduler(config, total_epochs=5000)
        result = s.get_spice_config("nonexistent")
        assert result is None

    def test_get_enabled_spice_simulations(self):
        config = ValidationScheduleConfig()
        sim1 = SpiceSimulationConfig(name="a", enabled=True)
        sim2 = SpiceSimulationConfig(name="b", enabled=False)
        config.spice = SpiceScheduleConfig(simulations=[sim1, sim2])
        s = ValidationScheduler(config, total_epochs=5000)
        enabled = s.get_enabled_spice_simulations()
        assert len(enabled) == 1
        assert enabled[0].name == "a"

    def test_get_spice_weights(self):
        config = ValidationScheduleConfig()
        sim1 = SpiceSimulationConfig(name="a", enabled=True, weight=2.0)
        sim2 = SpiceSimulationConfig(name="b", enabled=False, weight=999.0)
        config.spice = SpiceScheduleConfig(simulations=[sim1, sim2])
        s = ValidationScheduler(config, total_epochs=5000)
        weights = s.get_spice_weights()
        assert weights == {"a": 2.0}

    def test_summary(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=True, interval=100)
        config.spice = SpiceScheduleConfig(enabled=False)
        s = ValidationScheduler(config, total_epochs=5000)
        text = s.summary()
        assert "Validation Schedule" in text
        assert "DRC:" in text
        assert "SPICE:" in text


class TestValidationScheduleConfigMore:
    """Tests for ValidationScheduleConfig advanced methods."""

    def test_from_dict_with_all_fields(self):
        d = {
            "enabled": False,
            "log_results": False,
            "final_phase_epochs": 1000,
            "drc": {
                "enabled": False,
                "interval": 50,
                "final_phase_interval": 5,
                "weight": 2.5,
                "fail_on_errors": True,
                "max_errors": 10,
            },
            "spice": {
                "enabled": True,
                "interval": 300,
                "final_phase_interval": 75,
                "fail_on_errors": True,
                "simulations": [
                    {
                        "name": "test_sim",
                        "enabled": True,
                        "weight": 0.5,
                        "loop_components": ["U1"],
                        "parameters": {"cap": 1e-6},
                    }
                ],
            },
            "drc_template_pcb": "/tmp/test.kicad_pcb",
            "drc_board_origin": [10.0, 20.0],
        }
        config = ValidationScheduleConfig.from_dict(d)
        assert config.enabled is False
        assert config.log_results is False
        assert config.final_phase_epochs == 1000
        assert config.drc.enabled is False
        assert config.drc.interval == 50
        assert config.drc.final_phase_interval == 5
        assert config.drc.weight == 2.5
        assert config.drc.fail_on_errors is True
        assert config.drc.max_errors == 10
        assert config.spice.enabled is True
        assert config.spice.interval == 300
        assert config.spice.final_phase_interval == 75
        assert len(config.spice.simulations) == 1
        assert config.drc_template_pcb == Path("/tmp/test.kicad_pcb")
        assert config.drc_board_origin == (10.0, 20.0)

    def test_from_dict_missing_drc_uses_defaults(self):
        d = {"spice": {"enabled": False}}
        config = ValidationScheduleConfig.from_dict(d)
        assert config.drc.enabled is True  # default
        assert config.drc.interval == 100  # default

    def test_from_dict_missing_spice_uses_defaults(self):
        d = {"drc": {"enabled": False}}
        config = ValidationScheduleConfig.from_dict(d)
        assert config.spice.enabled is False  # default

    def test_to_dict_includes_paths(self):
        config = ValidationScheduleConfig()
        config.drc_template_pcb = Path("/some/pcb.kicad_pcb")
        config.drc_board_origin = (5.0, 6.0)
        d = config.to_dict()
        assert d["drc_template_pcb"] == "/some/pcb.kicad_pcb"
        assert d["drc_board_origin"] == [5.0, 6.0]

    def test_to_dict_none_path(self):
        config = ValidationScheduleConfig()
        config.drc_template_pcb = None
        d = config.to_dict()
        assert d["drc_template_pcb"] is None

    def test_save_and_load_roundtrip(self):
        config = ValidationScheduleConfig()
        config.drc = DRCScheduleConfig(enabled=False, interval=50)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            config.save(tmp_path)
            loaded = ValidationScheduleConfig.load(tmp_path)
            assert loaded.drc.enabled == config.drc.enabled
            assert loaded.drc.interval == config.drc.interval
            assert loaded.spice.enabled == config.spice.enabled
        finally:
            tmp_path.unlink(missing_ok=True)


class TestCreateDefaults:
    """Tests for factory functions."""

    def test_create_default_config(self):
        config = create_default_config()
        assert isinstance(config, ValidationScheduleConfig)
        assert config.drc.enabled is True
        assert config.spice.enabled is False

    def test_load_validation_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("validation:\n  enabled: true\n  drc:\n    interval: 42\n")
            tmp_path = Path(f.name)
        try:
            config = load_validation_config(tmp_path)
            assert config.drc.interval == 42
        finally:
            tmp_path.unlink(missing_ok=True)
