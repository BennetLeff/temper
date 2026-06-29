"""
Tests for EscapeClearance and RoutingCorridor constraint parsing.

Part of temper-g54c.1: Add routing-aware dataclasses for deterministic placement.
"""

import tempfile
from pathlib import Path

from temper_placer.io.config_loader import (
    EscapeClearance,
    RoutingCorridor,
    load_constraints,
)


class TestEscapeClearance:
    """Tests for EscapeClearance dataclass."""

    def test_defaults(self):
        """Verify default field values."""
        ec = EscapeClearance(component="U_MCU")
        assert ec.component == "U_MCU"
        assert ec.clearance_mm is None
        assert ec.tier == "soft"
        assert ec.priority_sides == []
        assert ec.description == ""

    def test_compute_clearance_qfn56(self):
        """Test clearance computation for QFN-56 (0.5mm pitch)."""
        ec = EscapeClearance(component="U_MCU")
        clearance = ec.compute_clearance(pin_count=56, pitch_mm=0.5)
        # sqrt(56) * 0.5 * 1.5 ≈ 5.6mm
        assert 5.0 < clearance < 6.0
        assert abs(clearance - 5.6) < 0.5

    def test_compute_clearance_qfn32(self):
        """Test clearance computation for QFN-32 (0.5mm pitch)."""
        ec = EscapeClearance(component="U_IC")
        clearance = ec.compute_clearance(pin_count=32, pitch_mm=0.5)
        # sqrt(32) * 0.5 * 1.5 ≈ 4.2mm
        assert 3.5 < clearance < 5.0

    def test_explicit_clearance_overrides_computation(self):
        """When clearance_mm is set, it should be preferred over computation."""
        ec = EscapeClearance(component="U_MCU", clearance_mm=8.0)
        assert ec.clearance_mm == 8.0
        # compute_clearance is still available but not automatic
        computed = ec.compute_clearance(pin_count=56, pitch_mm=0.5)
        assert computed != 8.0  # The explicit value is different


class TestRoutingCorridor:
    """Tests for RoutingCorridor dataclass."""

    def test_defaults(self):
        """Verify default field values."""
        rc = RoutingCorridor(
            name="usb_path",
            from_component="J_USB",
            to_component="U_MCU",
            width_mm=5.0,
        )
        assert rc.name == "usb_path"
        assert rc.from_component == "J_USB"
        assert rc.to_component == "U_MCU"
        assert rc.width_mm == 5.0
        assert rc.keep_clear is True
        assert rc.nets == []
        assert rc.tier == "soft"

    def test_with_nets(self):
        """Test with explicit net list."""
        rc = RoutingCorridor(
            name="usb_diff",
            from_component="J_USB",
            to_component="U_MCU",
            width_mm=3.0,
            nets=["USB_D+", "USB_D-"],
        )
        assert rc.nets == ["USB_D+", "USB_D-"]


class TestYAMLParsing:
    """Tests for YAML configuration parsing."""

    def test_load_escape_clearances(self):
        """Test loading escape_clearances from YAML."""
        config_yaml = """
board:
  width_mm: 100
  height_mm: 150

escape_clearances:
  - component: "U_MCU"
    priority_sides: ["bottom", "right"]
    tier: "soft"
    description: "MCU escape routing clearance"
  
  - component: "U_USB"
    clearance_mm: 6.0
    tier: "hard"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_yaml)
            config_path = Path(f.name)

        try:
            constraints = load_constraints(config_path)

            assert len(constraints.escape_clearances) == 2

            # First clearance
            ec1 = constraints.escape_clearances[0]
            assert ec1.component == "U_MCU"
            assert ec1.priority_sides == ["bottom", "right"]
            assert ec1.tier == "soft"
            assert ec1.clearance_mm is None  # Not specified, will be computed

            # Second clearance
            ec2 = constraints.escape_clearances[1]
            assert ec2.component == "U_USB"
            assert ec2.clearance_mm == 6.0
            assert ec2.tier == "hard"
        finally:
            config_path.unlink()

    def test_load_routing_corridors(self):
        """Test loading routing_corridors from YAML."""
        config_yaml = """
board:
  width_mm: 100
  height_mm: 150

routing_corridors:
  - name: "usb_path"
    from_component: "J_USB"
    to_component: "U_MCU"
    width_mm: 5.0
    keep_clear: true
    nets: ["USB_D+", "USB_D-"]
    tier: "soft"
    description: "USB differential pair routing corridor"
  
  - name: "spi_bus"
    from_component: "U_MCU"
    to_component: "U_FLASH"
    width_mm: 3.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_yaml)
            config_path = Path(f.name)

        try:
            constraints = load_constraints(config_path)

            assert len(constraints.routing_corridors) == 2

            # First corridor
            rc1 = constraints.routing_corridors[0]
            assert rc1.name == "usb_path"
            assert rc1.from_component == "J_USB"
            assert rc1.to_component == "U_MCU"
            assert rc1.width_mm == 5.0
            assert rc1.keep_clear is True
            assert rc1.nets == ["USB_D+", "USB_D-"]
            assert rc1.tier == "soft"

            # Second corridor
            rc2 = constraints.routing_corridors[1]
            assert rc2.name == "spi_bus"
            assert rc2.from_component == "U_MCU"
            assert rc2.to_component == "U_FLASH"
            assert rc2.width_mm == 3.0
            assert rc2.keep_clear is True  # Default
            assert rc2.nets == []  # Default
        finally:
            config_path.unlink()

    def test_backward_compatible_without_new_fields(self):
        """Existing configs without new fields should still load."""
        config_yaml = """
board:
  width_mm: 100
  height_mm: 150

zones:
  - name: "Signal"
    bounds: [5, 5, 95, 145]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_yaml)
            config_path = Path(f.name)

        try:
            constraints = load_constraints(config_path)

            # New fields should be empty lists (not None or error)
            assert constraints.escape_clearances == []
            assert constraints.routing_corridors == []

            # Existing functionality still works
            assert len(constraints.zones) == 1
            assert constraints.zones[0].name == "Signal"
        finally:
            config_path.unlink()

    def test_empty_sections_parsed_correctly(self):
        """Empty escape_clearances/routing_corridors sections parse as empty lists."""
        config_yaml = """
board:
  width_mm: 100
  height_mm: 150

escape_clearances: []
routing_corridors: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_yaml)
            config_path = Path(f.name)

        try:
            constraints = load_constraints(config_path)
            assert constraints.escape_clearances == []
            assert constraints.routing_corridors == []
        finally:
            config_path.unlink()
