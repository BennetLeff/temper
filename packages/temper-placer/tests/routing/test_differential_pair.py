"""
Tests for differential pair configuration and constraints.
"""

import pytest
from pathlib import Path
import yaml

from temper_placer.core.differential_pair import DifferentialPairConstraint
from temper_placer.io.config_loader import load_constraints, DifferentialPairRule


class TestDifferentialPairDataclass:
    """Tests for DifferentialPairConstraint dataclass."""

    def test_diff_pair_creation_minimal(self):
        """Test creating differential pair with minimal required fields."""
        pair = DifferentialPairConstraint(
            net_pos="USB_D+",
            net_neg="USB_D-"
        )
        assert pair.net_pos == "USB_D+"
        assert pair.net_neg == "USB_D-"
        assert pair.spacing_mm == 0.2  # Default
        assert pair.coupling_tolerance_mm == 0.5  # Default
        assert pair.max_skew_mm == 0.5  # Default
        assert pair.impedance_ohm is None  # Optional

    def test_diff_pair_creation_full(self):
        """Test creating differential pair with all fields specified."""
        pair = DifferentialPairConstraint(
            net_pos="USB_D+",
            net_neg="USB_D-",
            spacing_mm=0.15,
            coupling_tolerance_mm=0.3,
            impedance_ohm=90.0,
            max_skew_mm=0.5
        )
        assert pair.net_pos == "USB_D+"
        assert pair.net_neg == "USB_D-"
        assert pair.spacing_mm == 0.15
        assert pair.coupling_tolerance_mm == 0.3
        assert pair.impedance_ohm == 90.0
        assert pair.max_skew_mm == 0.5

    def test_diff_pair_validation_negative_spacing(self):
        """Test that negative spacing raises ValueError."""
        with pytest.raises(ValueError, match="spacing_mm must be positive"):
            DifferentialPairConstraint(
                net_pos="A",
                net_neg="B",
                spacing_mm=-0.1
            )

    def test_diff_pair_validation_negative_tolerance(self):
        """Test that negative tolerance raises ValueError."""
        with pytest.raises(ValueError, match="coupling_tolerance_mm must be non-negative"):
            DifferentialPairConstraint(
                net_pos="A",
                net_neg="B",
                coupling_tolerance_mm=-0.1
            )

    def test_diff_pair_validation_negative_skew(self):
        """Test that negative max_skew raises ValueError."""
        with pytest.raises(ValueError, match="max_skew_mm must be non-negative"):
            DifferentialPairConstraint(
                net_pos="A",
                net_neg="B",
                max_skew_mm=-0.1
            )

    def test_diff_pair_validation_negative_impedance(self):
        """Test that negative impedance raises ValueError."""
        with pytest.raises(ValueError, match="impedance_ohm must be positive"):
            DifferentialPairConstraint(
                net_pos="A",
                net_neg="B",
                impedance_ohm=-50.0
            )


class TestDifferentialPairConfig:
    """Tests for differential pair configuration loading."""

    def test_diff_pair_config_parsing(self, tmp_path):
        """Test loading differential pair from YAML config."""
        config = {
            "differential_pairs": [
                {
                    "net_pos": "USB_D+",
                    "net_neg": "USB_D-",
                    "spacing_mm": 0.15,
                    "coupling_tolerance_mm": 0.3,
                    "impedance_ohm": 90.0,
                    "max_skew_mm": 0.5,
                    "description": "USB 2.0 Full Speed"
                }
            ]
        }
        
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        constraints = load_constraints(config_path)
        
        assert len(constraints.differential_pairs) == 1
        pair = constraints.differential_pairs[0]
        assert isinstance(pair, DifferentialPairRule)
        assert pair.net_pos == "USB_D+"
        assert pair.net_neg == "USB_D-"
        assert pair.spacing_mm == 0.15
        assert pair.coupling_tolerance_mm == 0.3
        assert pair.impedance_ohm == 90.0
        assert pair.max_skew_mm == 0.5
        assert pair.description == "USB 2.0 Full Speed"

    def test_diff_pair_config_defaults(self, tmp_path):
        """Test that default values are applied when fields are missing."""
        config = {
            "differential_pairs": [
                {
                    "net_pos": "SIG_P",
                    "net_neg": "SIG_N"
                }
            ]
        }
        
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        constraints = load_constraints(config_path)
        
        assert len(constraints.differential_pairs) == 1
        pair = constraints.differential_pairs[0]
        assert pair.spacing_mm == 0.2  # Default
        assert pair.coupling_tolerance_mm == 0.5  # Default
        assert pair.max_skew_mm == 0.5  # Default
        assert pair.impedance_ohm is None  # Default
        assert pair.description == ""  # Default

    def test_diff_pair_config_multiple_pairs(self, tmp_path):
        """Test loading multiple differential pairs from config."""
        config = {
            "differential_pairs": [
                {"net_pos": "USB_D+", "net_neg": "USB_D-", "impedance_ohm": 90.0},
                {"net_pos": "HDMI_D0+", "net_neg": "HDMI_D0-", "impedance_ohm": 100.0},
                {"net_pos": "HDMI_D1+", "net_neg": "HDMI_D1-", "impedance_ohm": 100.0}
            ]
        }
        
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        constraints = load_constraints(config_path)
        
        assert len(constraints.differential_pairs) == 3
        assert constraints.differential_pairs[0].net_pos == "USB_D+"
        assert constraints.differential_pairs[1].net_pos == "HDMI_D0+"
        assert constraints.differential_pairs[2].net_pos == "HDMI_D1+"

    def test_diff_pair_config_empty_list(self, tmp_path):
        """Test that empty differential_pairs list is handled correctly."""
        config = {
            "differential_pairs": []
        }
        
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        constraints = load_constraints(config_path)
        assert len(constraints.differential_pairs) == 0

    def test_diff_pair_config_missing_section(self, tmp_path):
        """Test that missing differential_pairs section is handled gracefully."""
        config = {
            "board": {"width_mm": 100.0, "height_mm": 150.0}
        }
        
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        constraints = load_constraints(config_path)
        assert len(constraints.differential_pairs) == 0
