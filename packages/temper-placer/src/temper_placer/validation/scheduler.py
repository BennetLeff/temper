"""
Validation scheduler for training loop integration.

This module provides:
- ValidationScheduleConfig: YAML-configurable validation schedule
- ValidationScheduler: Manages when to run different validations
- Phase-aware scheduling with increased frequency in final phases

The scheduler controls:
- DRC validation frequency
- SPICE simulation frequency
- Penalty weights for each validation type
- Which simulations to run and when
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DRCScheduleConfig:
    """Configuration for DRC validation scheduling."""

    enabled: bool = True
    interval: int = 100  # Run every N epochs
    final_phase_interval: int = 20  # More frequent in final phase
    weight: float = 1.0  # Penalty weight
    fail_on_errors: bool = False  # Stop training on errors
    max_errors: int = 0  # Maximum allowed errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval": self.interval,
            "final_phase_interval": self.final_phase_interval,
            "weight": self.weight,
            "fail_on_errors": self.fail_on_errors,
            "max_errors": self.max_errors,
        }


@dataclass
class SpiceSimulationConfig:
    """Configuration for a single SPICE simulation."""

    name: str
    enabled: bool = True
    weight: float = 1.0
    # Component refs for loop inductance calculation
    loop_components: list[str] = field(default_factory=list)
    # Additional parameters
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "weight": self.weight,
            "loop_components": self.loop_components,
            "parameters": self.parameters,
        }


@dataclass
class SpiceScheduleConfig:
    """Configuration for SPICE validation scheduling."""

    enabled: bool = False  # Disabled by default (expensive)
    interval: int = 200  # Run every N epochs
    final_phase_interval: int = 50  # More frequent in final phase
    simulations: list[SpiceSimulationConfig] = field(default_factory=list)
    fail_on_errors: bool = False

    def __post_init__(self):
        # Default simulations if none provided
        if not self.simulations:
            self.simulations = [
                SpiceSimulationConfig(
                    name="gate_drive",
                    enabled=True,
                    weight=1.0,
                    loop_components=["U_GD", "Q1", "R_GATE"],
                    parameters={"gate_resistance": 4.7},
                ),
                SpiceSimulationConfig(
                    name="bootstrap_charging",
                    enabled=True,
                    weight=1.0,
                    loop_components=["U_GD", "D_BOOT", "C_BOOT"],
                    parameters={
                        "bootstrap_capacitance": 1e-6,
                        "bootstrap_resistance": 0.5,
                    },
                ),
                SpiceSimulationConfig(
                    name="power_integrity",
                    enabled=True,
                    weight=0.5,
                    loop_components=["C_DC", "Q1", "Q2"],
                    parameters={
                        "decap_esr": 0.05,
                        "decap_value": 100e-6,
                    },
                ),
            ]

    def get_enabled_simulations(self) -> list[SpiceSimulationConfig]:
        """Get list of enabled simulations."""
        return [sim for sim in self.simulations if sim.enabled]

    def get_weights(self) -> dict[str, float]:
        """Get weights dict for penalty computation."""
        return {sim.name: sim.weight for sim in self.simulations if sim.enabled}

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval": self.interval,
            "final_phase_interval": self.final_phase_interval,
            "fail_on_errors": self.fail_on_errors,
            "simulations": [sim.to_dict() for sim in self.simulations],
        }


@dataclass
class ValidationScheduleConfig:
    """
    Complete validation schedule configuration.

    Can be loaded from YAML or constructed programmatically.

    Example YAML:

    ```yaml
    validation:
      log_results: true
      final_phase_epochs: 500

      drc:
        enabled: true
        interval: 100
        final_phase_interval: 20
        weight: 1.0
        fail_on_errors: false
        max_errors: 0

      spice:
        enabled: true
        interval: 200
        final_phase_interval: 50
        fail_on_errors: false
        simulations:
          - name: gate_drive
            enabled: true
            weight: 1.0
            loop_components: [U_GD, Q1, R_GATE]
            parameters:
              gate_resistance: 4.7
          - name: bootstrap_charging
            enabled: true
            weight: 1.0
          - name: power_integrity
            enabled: true
            weight: 0.5
    ```
    """

    enabled: bool = True
    log_results: bool = True
    final_phase_epochs: int = 500  # Last N epochs are "final phase"

    drc: DRCScheduleConfig = field(default_factory=DRCScheduleConfig)
    spice: SpiceScheduleConfig = field(default_factory=SpiceScheduleConfig)

    # DRC-specific paths (loaded separately or via config)
    drc_template_pcb: Path | None = None
    drc_board_origin: tuple = (0.0, 0.0)

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> ValidationScheduleConfig:
        """Create config from dictionary."""
        schedule = cls()

        if "enabled" in config:
            schedule.enabled = config["enabled"]
        if "log_results" in config:
            schedule.log_results = config["log_results"]
        if "final_phase_epochs" in config:
            schedule.final_phase_epochs = config["final_phase_epochs"]

        # Parse DRC config
        if "drc" in config:
            drc_cfg = config["drc"]
            schedule.drc = DRCScheduleConfig(
                enabled=drc_cfg.get("enabled", True),
                interval=drc_cfg.get("interval", 100),
                final_phase_interval=drc_cfg.get("final_phase_interval", 20),
                weight=drc_cfg.get("weight", 1.0),
                fail_on_errors=drc_cfg.get("fail_on_errors", False),
                max_errors=drc_cfg.get("max_errors", 0),
            )

        # Parse SPICE config
        if "spice" in config:
            spice_cfg = config["spice"]
            simulations = []

            if "simulations" in spice_cfg:
                for sim_cfg in spice_cfg["simulations"]:
                    sim = SpiceSimulationConfig(
                        name=sim_cfg["name"],
                        enabled=sim_cfg.get("enabled", True),
                        weight=sim_cfg.get("weight", 1.0),
                        loop_components=sim_cfg.get("loop_components", []),
                        parameters=sim_cfg.get("parameters", {}),
                    )
                    simulations.append(sim)

            schedule.spice = SpiceScheduleConfig(
                enabled=spice_cfg.get("enabled", False),
                interval=spice_cfg.get("interval", 200),
                final_phase_interval=spice_cfg.get("final_phase_interval", 50),
                fail_on_errors=spice_cfg.get("fail_on_errors", False),
                simulations=simulations,
            )
            # Re-trigger __post_init__ for default simulations if none provided
            if not simulations:
                schedule.spice.__post_init__()

        # DRC paths
        if "drc_template_pcb" in config and config["drc_template_pcb"] is not None:
            schedule.drc_template_pcb = Path(config["drc_template_pcb"])
        if "drc_board_origin" in config and config["drc_board_origin"] is not None:
            schedule.drc_board_origin = tuple(config["drc_board_origin"])

        return schedule

    @classmethod
    def load(cls, config_path: Path) -> ValidationScheduleConfig:
        """Load configuration from YAML file."""
        with open(config_path) as f:
            raw_config = yaml.safe_load(f)

        # Config may be at top level or under 'validation' key
        config = raw_config.get("validation", raw_config)
        return cls.from_dict(config)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "log_results": self.log_results,
            "final_phase_epochs": self.final_phase_epochs,
            "drc": self.drc.to_dict(),
            "spice": self.spice.to_dict(),
            "drc_template_pcb": str(self.drc_template_pcb) if self.drc_template_pcb else None,
            "drc_board_origin": list(self.drc_board_origin),
        }

    def save(self, config_path: Path) -> None:
        """Save configuration to YAML file."""
        with open(config_path, "w") as f:
            yaml.dump({"validation": self.to_dict()}, f, default_flow_style=False)


class ValidationScheduler:
    """
    Manages validation scheduling during training.

    Determines when to run DRC, SPICE, and other validations based on:
    - Current epoch
    - Total epochs (for final phase detection)
    - Configured intervals

    Example usage:

        config = ValidationScheduleConfig.load("validation.yaml")
        scheduler = ValidationScheduler(config, total_epochs=5000)

        for epoch in range(5000):
            if scheduler.should_run_drc(epoch):
                # Run DRC validation
                pass

            if scheduler.should_run_spice(epoch):
                # Run SPICE validation
                pass
    """

    def __init__(
        self,
        config: ValidationScheduleConfig,
        total_epochs: int = 5000,
    ):
        """
        Initialize scheduler.

        Args:
            config: Validation schedule configuration.
            total_epochs: Total epochs for training (used to detect final phase).
        """
        self.config = config
        self.total_epochs = total_epochs

        # Track what has been run
        self._drc_epochs: set[int] = set()
        self._spice_epochs: set[int] = set()

    def is_final_phase(self, epoch: int) -> bool:
        """Check if we're in the final phase of training."""
        final_start = self.total_epochs - self.config.final_phase_epochs
        return epoch >= final_start

    def get_drc_interval(self, epoch: int) -> int:
        """Get DRC interval for current epoch."""
        if self.is_final_phase(epoch):
            return self.config.drc.final_phase_interval
        return self.config.drc.interval

    def get_spice_interval(self, epoch: int) -> int:
        """Get SPICE interval for current epoch."""
        if self.is_final_phase(epoch):
            return self.config.spice.final_phase_interval
        return self.config.spice.interval

    def should_run_drc(self, epoch: int) -> bool:
        """Check if DRC should run at this epoch."""
        if not self.config.enabled or not self.config.drc.enabled:
            return False

        if epoch in self._drc_epochs:
            return False

        interval = self.get_drc_interval(epoch)
        should_run = epoch % interval == 0 or epoch == self.total_epochs - 1

        return should_run

    def should_run_spice(self, epoch: int) -> bool:
        """Check if SPICE should run at this epoch."""
        if not self.config.enabled or not self.config.spice.enabled:
            return False

        if epoch in self._spice_epochs:
            return False

        interval = self.get_spice_interval(epoch)
        should_run = epoch % interval == 0 or epoch == self.total_epochs - 1

        return should_run

    def mark_drc_run(self, epoch: int) -> None:
        """Mark that DRC was run at this epoch."""
        self._drc_epochs.add(epoch)

    def mark_spice_run(self, epoch: int) -> None:
        """Mark that SPICE was run at this epoch."""
        self._spice_epochs.add(epoch)

    def get_spice_config(self, simulation_name: str) -> SpiceSimulationConfig | None:
        """Get configuration for a specific SPICE simulation."""
        for sim in self.config.spice.simulations:
            if sim.name == simulation_name:
                return sim
        return None

    def get_enabled_spice_simulations(self) -> list[SpiceSimulationConfig]:
        """Get list of enabled SPICE simulations."""
        return self.config.spice.get_enabled_simulations()

    def get_spice_weights(self) -> dict[str, float]:
        """Get penalty weights for SPICE simulations."""
        return self.config.spice.get_weights()

    def summary(self) -> str:
        """Get human-readable summary of schedule."""
        lines = ["=== Validation Schedule ==="]
        lines.append(f"Enabled: {self.config.enabled}")
        lines.append(f"Total epochs: {self.total_epochs}")
        lines.append(f"Final phase: last {self.config.final_phase_epochs} epochs")

        lines.append("\nDRC:")
        lines.append(f"  Enabled: {self.config.drc.enabled}")
        if self.config.drc.enabled:
            lines.append(f"  Interval: {self.config.drc.interval}")
            lines.append(f"  Final phase interval: {self.config.drc.final_phase_interval}")
            lines.append(f"  Weight: {self.config.drc.weight}")

        lines.append("\nSPICE:")
        lines.append(f"  Enabled: {self.config.spice.enabled}")
        if self.config.spice.enabled:
            lines.append(f"  Interval: {self.config.spice.interval}")
            lines.append(f"  Final phase interval: {self.config.spice.final_phase_interval}")
            for sim in self.config.spice.simulations:
                status = "✓" if sim.enabled else "✗"
                lines.append(f"  {status} {sim.name} (weight={sim.weight})")

        return "\n".join(lines)


def load_validation_config(config_path: Path) -> ValidationScheduleConfig:
    """
    Convenience function to load validation config from YAML.

    Args:
        config_path: Path to YAML configuration file.

    Returns:
        ValidationScheduleConfig object.
    """
    return ValidationScheduleConfig.load(config_path)


def create_default_config() -> ValidationScheduleConfig:
    """
    Create default validation schedule configuration.

    Returns:
        ValidationScheduleConfig with sensible defaults.
    """
    return ValidationScheduleConfig()
