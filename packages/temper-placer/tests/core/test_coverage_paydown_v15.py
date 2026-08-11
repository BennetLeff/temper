"""Coverage paydown v15: validation/scheduler, router_v6/layer_assignment,
router_v6/net_classification.

Targets allowlist entries across:
- validation/scheduler.py (22): config objects, scheduler state machine
- router_v6/layer_assignment.py (7): layer name lookups, pattern matching
- router_v6/net_classification.py (9): single-layer mode, net classification

All tests are pure Python; no fixtures, no temp files.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
# ===========================================================================
# validation/scheduler.py
# ===========================================================================


class TestDRCScheduleConfig:
    """Covers DRCScheduleConfig.to_dict."""

    def test_to_dict(self):
        from temper_placer.validation.scheduler import DRCScheduleConfig

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
    """Covers SpiceSimulationConfig.to_dict."""

    def test_to_dict(self):
        from temper_placer.validation.scheduler import SpiceSimulationConfig

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
    """Covers SpiceScheduleConfig.to_dict, get_enabled_simulations, get_weights."""

    def test_to_dict(self):
        from temper_placer.validation.scheduler import SpiceScheduleConfig

        c = SpiceScheduleConfig(enabled=True, interval=50, final_phase_interval=10)
        d = c.to_dict()
        assert d["enabled"] is True
        assert d["interval"] == 50
        assert d["final_phase_interval"] == 10
        assert "simulations" in d

    def test_get_enabled_simulations(self):
        from temper_placer.validation.scheduler import SpiceScheduleConfig

        c = SpiceScheduleConfig()
        enabled = c.get_enabled_simulations()
        assert len(enabled) >= 1
        for sim in enabled:
            assert sim.enabled is True

    def test_get_weights(self):
        from temper_placer.validation.scheduler import SpiceScheduleConfig

        c = SpiceScheduleConfig()
        weights = c.get_weights()
        assert isinstance(weights, dict)
        assert len(weights) >= 1


class TestValidationScheduleConfig:
    """Covers ValidationScheduleConfig.to_dict, from_dict, load, save."""

    def test_to_dict(self):
        from temper_placer.validation.scheduler import ValidationScheduleConfig

        c = ValidationScheduleConfig(final_phase_epochs=300)
        d = c.to_dict()
        assert d["enabled"] is True
        assert d["log_results"] is True
        assert d["final_phase_epochs"] == 300
        assert "drc" in d
        assert "spice" in d

    def test_from_dict(self):
        from temper_placer.validation.scheduler import ValidationScheduleConfig

        cfg = {
            "enabled": False,
            "log_results": False,
            "final_phase_epochs": 200,
            "drc": {
                "enabled": False,
                "interval": 50,
                "final_phase_interval": 10,
                "weight": 2.0,
                "fail_on_errors": True,
                "max_errors": 3,
            },
            "spice": {
                "enabled": True,
                "interval": 100,
                "final_phase_interval": 25,
                "fail_on_errors": False,
                "simulations": [
                    {
                        "name": "test_sim",
                        "enabled": True,
                        "weight": 0.8,
                        "loop_components": ["U1", "C1"],
                        "parameters": {"r": 10},
                    }
                ],
            },
        }
        c = ValidationScheduleConfig.from_dict(cfg)
        assert c.enabled is False
        assert c.log_results is False
        assert c.final_phase_epochs == 200
        assert c.drc.enabled is False
        assert c.drc.interval == 50
        assert c.drc.weight == 2.0
        assert c.spice.enabled is True
        assert c.spice.interval == 100
        assert len(c.spice.simulations) == 1
        assert c.spice.simulations[0].name == "test_sim"

    def test_load_and_save(self):
        from temper_placer.validation.scheduler import ValidationScheduleConfig

        c = ValidationScheduleConfig()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            c.save(Path(f.name))
            tmp_path = f.name

        try:
            loaded = ValidationScheduleConfig.load(Path(tmp_path))
            assert loaded.enabled == c.enabled
            assert loaded.drc.interval == c.drc.interval
        finally:
            Path(tmp_path).unlink()

    def test_load_validation_config(self):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            load_validation_config,
        )

        c = ValidationScheduleConfig()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            c.save(Path(f.name))
            tmp_path = f.name

        try:
            loaded = load_validation_config(Path(tmp_path))
            assert loaded.enabled == c.enabled
        finally:
            Path(tmp_path).unlink()

    def test_create_default_config(self):
        from temper_placer.validation.scheduler import create_default_config

        c = create_default_config()
        assert c.enabled is True
        assert c.drc.enabled is True
        assert isinstance(c.drc.interval, int)


class TestValidationScheduler:
    """Covers ValidationScheduler methods."""

    def _make_scheduler(self, total_epochs=5000):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            ValidationScheduler,
        )

        config = ValidationScheduleConfig()
        return ValidationScheduler(config, total_epochs=total_epochs)

    def test_is_final_phase(self):
        s = self._make_scheduler(total_epochs=5000)
        # final_phase_epochs default is 500, so final phase starts at 4500
        assert s.is_final_phase(4500) is True
        assert s.is_final_phase(4999) is True
        assert s.is_final_phase(0) is False
        assert s.is_final_phase(4499) is False

    def test_get_drc_interval(self):
        s = self._make_scheduler(total_epochs=5000)
        assert s.get_drc_interval(0) == 100  # default
        # In final phase, should use final_phase_interval
        assert s.get_drc_interval(4500) == 20  # default final_phase_interval

    def test_get_spice_interval(self):
        s = self._make_scheduler(total_epochs=5000)
        assert s.get_spice_interval(0) == 200  # default
        # In final phase
        assert s.get_spice_interval(4500) == 50  # default final_phase_interval

    def test_should_run_drc(self):
        s = self._make_scheduler(total_epochs=5000)
        assert s.should_run_drc(0) is True  # epoch 0
        assert s.should_run_drc(100) is True  # interval boundary
        assert s.should_run_drc(1) is False

    def test_should_run_drc_disabled(self):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            ValidationScheduler,
        )

        config = ValidationScheduleConfig()
        config.enabled = False
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_drc(0) is False

    def test_should_run_spice(self):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            ValidationScheduler,
        )

        config = ValidationScheduleConfig()
        config.spice.enabled = True
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_spice(0) is True  # epoch 0
        assert s.should_run_spice(200) is True  # interval boundary

    def test_should_run_spice_disabled(self):
        s = self._make_scheduler(total_epochs=5000)
        # spice is disabled by default
        assert s.should_run_spice(0) is False

    def test_mark_drc_run(self):
        s = self._make_scheduler(total_epochs=5000)
        assert s.should_run_drc(0) is True
        s.mark_drc_run(0)
        assert s.should_run_drc(0) is False  # already run

    def test_mark_spice_run(self):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            ValidationScheduler,
        )

        config = ValidationScheduleConfig()
        config.spice.enabled = True
        s = ValidationScheduler(config, total_epochs=5000)
        assert s.should_run_spice(0) is True
        s.mark_spice_run(0)
        assert s.should_run_spice(0) is False  # already run

    def test_get_spice_config(self):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            ValidationScheduler,
        )

        config = ValidationScheduleConfig()
        # Default has gate_drive, bootstrap_charging, power_integrity
        s = ValidationScheduler(config, total_epochs=5000)
        sim = s.get_spice_config("gate_drive")
        assert sim is not None
        assert sim.name == "gate_drive"
        # Non-existent
        assert s.get_spice_config("nonexistent") is None

    def test_get_enabled_spice_simulations(self):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            ValidationScheduler,
        )

        config = ValidationScheduleConfig()
        config.spice.enabled = True
        s = ValidationScheduler(config, total_epochs=5000)
        enabled = s.get_enabled_spice_simulations()
        assert len(enabled) >= 1

    def test_get_spice_weights(self):
        from temper_placer.validation.scheduler import (
            ValidationScheduleConfig,
            ValidationScheduler,
        )

        config = ValidationScheduleConfig()
        config.spice.enabled = True
        s = ValidationScheduler(config, total_epochs=5000)
        weights = s.get_spice_weights()
        assert isinstance(weights, dict)
        assert len(weights) >= 1

    def test_summary(self):
        s = self._make_scheduler(total_epochs=5000)
        text = s.summary()
        assert "Validation Schedule" in text
        assert "DRC:" in text
        assert "SPICE:" in text


# ===========================================================================
# router_v6/layer_assignment.py
# ===========================================================================


class TestLayerAssignment:
    """Covers layer_assignment pure lookups and helpers."""

    def test_layer_name_to_enum(self):
        from temper_placer.router_v6.layer_assignment import (
            Layer,
            layer_name_to_enum,
        )

        assert layer_name_to_enum("F.Cu") == Layer.L1_TOP
        assert layer_name_to_enum("In1.Cu") == Layer.L2_GND
        assert layer_name_to_enum("In2.Cu") == Layer.L3_PWR
        assert layer_name_to_enum("B.Cu") == Layer.L4_BOT

        with pytest.raises(KeyError):
            layer_name_to_enum("Invalid.Layer")

    def test_layer_name_to_index(self):
        from temper_placer.router_v6.layer_assignment import layer_name_to_index

        assert layer_name_to_index("F.Cu") == 0
        assert layer_name_to_index("In1.Cu") == 1
        assert layer_name_to_index("In2.Cu") == 2
        assert layer_name_to_index("B.Cu") == 3

        with pytest.raises(KeyError):
            layer_name_to_index("Invalid.Layer")

    def test_matches_pattern(self):
        from temper_placer.router_v6.layer_assignment import matches_pattern

        assert matches_pattern("DC_BUS_P", r"DC_BUS_.*") is True
        assert matches_pattern("VCC_3V3", r"DC_BUS_.*") is False
        assert matches_pattern("GATE_DRV_H", r"GATE_.*") is True
        assert matches_pattern("SPI_MOSI", r"SPI_.*") is True
        assert matches_pattern("random_net", r".*") is True
        assert matches_pattern("", r".*") is True

    def test_get_routing_layers(self):
        from temper_placer.router_v6.layer_assignment import (
            Layer,
            get_routing_layers,
        )

        layers = get_routing_layers()
        assert Layer.L1_TOP in layers
        assert Layer.L2_GND in layers
        assert Layer.L3_PWR in layers
        assert Layer.L4_BOT in layers
        assert len(layers) == 4

    def test_get_plane_layers(self):
        from temper_placer.router_v6.layer_assignment import (
            Layer,
            get_plane_layers,
        )

        layers = get_plane_layers()
        assert Layer.L2_GND in layers
        assert Layer.L3_PWR in layers
        assert len(layers) == 2

    def test_get_signal_only_layers(self):
        from temper_placer.router_v6.layer_assignment import (
            Layer,
            get_signal_only_layers,
        )

        layers = get_signal_only_layers()
        assert Layer.L1_TOP in layers
        assert Layer.L4_BOT in layers
        assert len(layers) == 2

    def test_find_layer_conflicts(self):
        from temper_placer.router_v6.layer_assignment import find_layer_conflicts

        conflicts = find_layer_conflicts({})
        assert conflicts == []


# ===========================================================================
# router_v6/net_classification.py
# ===========================================================================


class TestNetClassification:
    """Covers set_single_layer_mode, get_single_layer_mode,
    and the Rust-delegated classification functions."""

    def test_set_and_get_single_layer_mode(self):
        from temper_placer.router_v6.net_classification import (
            get_single_layer_mode,
            set_single_layer_mode,
        )

        # Save original
        original = get_single_layer_mode()

        try:
            set_single_layer_mode(True)
            assert get_single_layer_mode() is True
            set_single_layer_mode(False)
            assert get_single_layer_mode() is False
        finally:
            set_single_layer_mode(original)

    def test_is_ground_net(self):
        from temper_placer.router_v6.net_classification import is_ground_net

        assert is_ground_net("GND") is True
        assert is_ground_net("PGND") is True
        assert is_ground_net("VCC") is False
        assert is_ground_net("SIGNAL1") is False

    def test_is_power_net(self):
        from temper_placer.router_v6.net_classification import is_power_net

        assert is_power_net("+3V3") is True
        assert is_power_net("+15V") is True
        assert is_power_net("VCC") is True
        assert is_power_net("SIGNAL1") is False

    def test_is_hv_net(self):
        from temper_placer.router_v6.net_classification import is_hv_net

        assert is_hv_net("AC_L") is True
        assert is_hv_net("AC_N") is True
        assert is_hv_net("SW_NODE") is True
        assert is_hv_net("GND") is False

    def test_is_signal_net(self):
        from temper_placer.router_v6.net_classification import is_signal_net

        assert is_signal_net("GPIO1") is True
        assert is_signal_net("SPI_MOSI") is True
        assert is_signal_net("GND") is False
        assert is_signal_net("+3V3") is False
        assert is_signal_net("AC_L") is False

    def test_classify_net_type(self):
        from temper_placer.router_v6.net_classification import classify_net_type

        assert classify_net_type("GND") == "ground"
        assert classify_net_type("PGND") == "ground"
        assert classify_net_type("+3V3") == "power"
        assert classify_net_type("VCC") == "power"
        assert classify_net_type("AC_L") == "hv"
        assert classify_net_type("SW_NODE") == "hv"
        assert classify_net_type("GPIO1") == "signal"
        assert classify_net_type("SPI_CLK") == "signal"

    def test_is_ground_pin(self):
        from temper_placer.router_v6.net_classification import is_ground_pin

        assert is_ground_pin("GND") is True
        assert is_ground_pin("VSS") is True
        assert is_ground_pin("VCC") is False
        assert is_ground_pin("DATA") is False

    def test_is_power_pin(self):
        from temper_placer.router_v6.net_classification import is_power_pin

        assert is_power_pin("VCC") is True
        assert is_power_pin("VDD") is True
        assert is_power_pin("GND") is False
        assert is_power_pin("DATA") is False

    def test_is_hv_pin(self):
        from temper_placer.router_v6.net_classification import is_hv_pin

        assert is_hv_pin("AC_L") is True
        assert is_hv_pin("HV") is True
        assert is_hv_pin("GND") is False

    def test_is_clock_pin(self):
        from temper_placer.router_v6.net_classification import is_clock_pin

        assert is_clock_pin("CLK") is True
        assert is_clock_pin("CLOCK") is True
        assert is_clock_pin("XTAL1") is True
        assert is_clock_pin("DATA") is False
        assert is_clock_pin("GND") is False
