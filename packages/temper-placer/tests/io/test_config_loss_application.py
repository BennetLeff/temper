"""
TDD tests for verifying the optimizer respects config-specified losses.

Hypothesis: The optimizer should ONLY use losses explicitly specified in the config.
If this test fails, it proves the optimizer is adding extra losses beyond what's configured.

Scientific Method:
- H0 (Null): Optimizer uses only configured losses
- H1 (Alternative): Optimizer adds hardcoded/default losses regardless of config

Related issue: temper-h0n9.5
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestConfigLossApplication:
    """Tests verifying optimizer respects loss configuration."""

    def test_overlap_only_config_produces_only_overlap_loss(self, tmp_path: Path):
        """
        GIVEN a config that specifies ONLY overlap loss
        WHEN the optimizer runs
        THEN the loss history should contain ONLY overlap-related losses

        This test will FAIL if extra losses (spread, alignment, etc.) appear.
        """
        # Arrange: Create minimal config with only overlap
        config_content = """
board:
  width_mm: 100.0
  height_mm: 150.0
  margin_mm: 5.0

losses:
  overlap:
    weight: 1.0

# Explicitly disable aesthetics
aesthetics:
  grid_weight: 0.0
  alignment_weight: 0.0
  rotation_consistency_weight: 0.0
  consensus_weight: 0.0

zones: []
groups: []
"""
        config_path = tmp_path / "overlap_only.yaml"
        config_path.write_text(config_content)

        output_path = tmp_path / "output.kicad_pcb"
        loss_history_path = tmp_path / "loss_history.json"

        # Get the test PCB path (use a simple test fixture)
        # Path: tests/io/test_config_loss_application.py -> temper-placer -> packages -> temper -> pcb
        test_pcb = Path(__file__).parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
        if not test_pcb.exists():
            pytest.skip(f"Test PCB not found: {test_pcb}")

        # Act: Run optimizer
        cmd = [
            sys.executable,
            "-m",
            "temper_placer.cli",
            "optimize",
            str(test_pcb),
            "-c",
            str(config_path),
            "-o",
            str(output_path),
            "--epochs",
            "5",
            "--seed",
            "42",
            "--loss-history",
            str(loss_history_path),
            "--no-heuristics",
            "--no-auto-group",  # Disable auto community detection
            "--no-curriculum",  # Disable curriculum to use config-specified losses
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Assert: Check loss history
        assert result.returncode == 0, f"Optimizer failed: {result.stderr}"
        assert loss_history_path.exists(), "Loss history not created"

        with open(loss_history_path) as f:
            loss_history = json.load(f)

        # Get the final epoch's breakdown
        assert "data_points" in loss_history, "Expected data_points in loss history"
        final_epoch = loss_history["data_points"][-1]
        assert "breakdown" in final_epoch, "Expected breakdown in final epoch"

        breakdown = final_epoch["breakdown"]
        loss_names = [
            k
            for k in breakdown
            if not k.endswith("_normalized") and not k.endswith("_weighted")
        ]

        # THE KEY ASSERTION: Only overlap-related losses should exist
        # Note: manufacturing_margin and pin_accessibility are always enabled as safety losses
        # These are intentionally hardcoded to ensure PCB manufacturability
        allowed_losses = {
            "overlap", "overlap_per_component", "total",
            # Safety losses always enabled:
            "manufacturing_margin", "manufacturing_margin_mean_margin",
            "manufacturing_margin_min_margin", "manufacturing_margin_n_pairs",
            "manufacturing_margin_n_tight_margins", "manufacturing_margin_n_violations",
            "pin_accessibility", "pin_accessibility_max_pin_body_violation",
            "pin_accessibility_max_pin_pin_violation", "pin_accessibility_pin_body_loss",
            "pin_accessibility_pin_pin_loss",
        }
        unexpected_losses = set(loss_names) - allowed_losses

        assert unexpected_losses == set(), (
            f"Config specified only 'overlap' but found extra losses: {sorted(unexpected_losses)}\n"
            f"All losses in output: {sorted(loss_names)}\n"
            f"This proves H1: optimizer adds losses beyond config specification"
        )

    def test_config_losses_match_output_losses(self, tmp_path: Path):
        """
        GIVEN a config specifying overlap, boundary, and wirelength losses
        WHEN the optimizer runs
        THEN exactly those losses should appear in the output (plus 'total')
        """
        # Arrange
        config_content = """
board:
  width_mm: 100.0
  height_mm: 150.0
  margin_mm: 5.0

losses:
  overlap:
    weight: 100.0
  boundary:
    weight: 10.0
  wirelength:
    weight: 1.0

# Explicitly disable all aesthetics
aesthetics:
  grid_weight: 0.0
  alignment_weight: 0.0
  rotation_consistency_weight: 0.0
  consensus_weight: 0.0

zones: []
groups: []
"""
        config_path = tmp_path / "three_losses.yaml"
        config_path.write_text(config_content)

        output_path = tmp_path / "output.kicad_pcb"
        loss_history_path = tmp_path / "loss_history.json"

        test_pcb = Path(__file__).parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
        if not test_pcb.exists():
            pytest.skip(f"Test PCB not found: {test_pcb}")

        # Act
        cmd = [
            sys.executable,
            "-m",
            "temper_placer.cli",
            "optimize",
            str(test_pcb),
            "-c",
            str(config_path),
            "-o",
            str(output_path),
            "--epochs",
            "5",
            "--seed",
            "42",
            "--loss-history",
            str(loss_history_path),
            "--no-heuristics",
            "--no-auto-group",
            "--no-curriculum",  # Use config-specified losses instead of curriculum
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Assert
        assert result.returncode == 0, f"Optimizer failed: {result.stderr}"

        with open(loss_history_path) as f:
            loss_history = json.load(f)

        final_epoch = loss_history["data_points"][-1]
        breakdown = final_epoch["breakdown"]
        loss_names = {
            k
            for k in breakdown
            if not k.endswith("_normalized") and not k.endswith("_weighted")
        }

        # Expected losses (with per_component variants)
        # Note: manufacturing_margin and pin_accessibility are always enabled as safety losses
        expected_base = {"overlap", "boundary", "wirelength", "total"}
        expected_variants = {
            "overlap_per_component",
            "boundary_per_component",
            "boundary_edge_violation",
            "boundary_keepout_violation",
        }
        # Safety losses always enabled:
        safety_losses = {
            "manufacturing_margin", "manufacturing_margin_mean_margin",
            "manufacturing_margin_min_margin", "manufacturing_margin_n_pairs",
            "manufacturing_margin_n_tight_margins", "manufacturing_margin_n_violations",
            "pin_accessibility", "pin_accessibility_max_pin_body_violation",
            "pin_accessibility_max_pin_pin_violation", "pin_accessibility_pin_body_loss",
            "pin_accessibility_pin_pin_loss",
        }
        expected = expected_base | expected_variants | safety_losses

        # Check no unexpected losses
        unexpected = loss_names - expected
        assert unexpected == set(), (
            f"Found unexpected losses: {sorted(unexpected)}\n"
            f"Expected: {sorted(expected)}\n"
            f"Actual: {sorted(loss_names)}"
        )

        # Check required losses present
        required = {"overlap", "boundary", "wirelength"}
        missing = required - loss_names
        assert missing == set(), f"Missing expected losses: {sorted(missing)}"

    def test_empty_losses_config_uses_defaults(self, tmp_path: Path):
        """
        GIVEN a config with empty losses dict (losses: {})
        WHEN the optimizer runs
        THEN it should fall back to hardcoded defaults (legacy behavior)

        This tests the edge case of explicitly specifying an empty losses section.
        Empty dict means "use defaults", not "use no losses".
        """
        config_content = """
board:
  width_mm: 100.0
  height_mm: 150.0
  margin_mm: 5.0

# Empty losses dict means use defaults
losses: {}

# Disable all aesthetics
aesthetics:
  grid_weight: 0.0
  alignment_weight: 0.0
  rotation_consistency_weight: 0.0
  consensus_weight: 0.0

zones: []
groups: []
"""
        config_path = tmp_path / "no_losses.yaml"
        config_path.write_text(config_content)

        output_path = tmp_path / "output.kicad_pcb"
        loss_history_path = tmp_path / "loss_history.json"

        test_pcb = Path(__file__).parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
        if not test_pcb.exists():
            pytest.skip(f"Test PCB not found: {test_pcb}")

        # Act
        cmd = [
            sys.executable,
            "-m",
            "temper_placer.cli",
            "optimize",
            str(test_pcb),
            "-c",
            str(config_path),
            "-o",
            str(output_path),
            "--epochs",
            "5",
            "--seed",
            "42",
            "--loss-history",
            str(loss_history_path),
            "--no-heuristics",
            "--no-auto-group",
            "--no-curriculum",  # Use config-specified losses instead of curriculum
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Assert: Should succeed with default losses (legacy behavior)
        assert result.returncode == 0, f"Optimizer failed: {result.stderr}"

        with open(loss_history_path) as f:
            loss_history = json.load(f)
        final_epoch = loss_history["data_points"][-1]
        breakdown = final_epoch["breakdown"]
        loss_names = {
            k
            for k in breakdown
            if not k.endswith("_normalized") and not k.endswith("_weighted")
        }

        # Empty losses: {} should fall back to defaults (overlap, boundary, wirelength, spread)
        # Plus safety losses that are always enabled
        expected_defaults = {
            "overlap", "boundary", "wirelength", "spread",
            # Safety losses always enabled:
            "manufacturing_margin", "pin_accessibility",
        }
        # Filter to base losses only (not per-component variants, metrics, or total)
        base_losses = {
            name
            for name in loss_names
            if not name.endswith("_per_component")
            and not name.endswith("_edge_violation")
            and not name.endswith("_keepout_violation")
            and not name.endswith("_mean_margin")
            and not name.endswith("_min_margin")
            and not name.endswith("_n_pairs")
            and not name.endswith("_n_tight_margins")
            and not name.endswith("_n_violations")
            and not name.endswith("_pin_body_violation")
            and not name.endswith("_pin_pin_violation")
            and not name.endswith("_pin_body_loss")
            and not name.endswith("_pin_pin_loss")
            and name != "total"
        }

        assert base_losses == expected_defaults, (
            f"Empty losses config should use defaults, got: {sorted(base_losses)}\n"
            f"Expected: {sorted(expected_defaults)}"
        )
