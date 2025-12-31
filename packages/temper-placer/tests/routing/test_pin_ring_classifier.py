"""Tests for pin ring classifier."""

import pytest
import math
from temper_placer.routing.pin_ring_classifier import (
    classify_pin_rings,
    PinRing,
    PinClassification,
    get_ring_strategy,
)


class TestPinRingClassification:
    """Tests for pin ring classification logic."""

    def test_simple_3x3_grid(self):
        """Test classification of a simple 3x3 BGA grid."""
        pins = [
            # Outer ring (corners and edges)
            ("A1", -5.08, 5.08),   # Top-left corner
            ("A3", 5.08, 5.08),    # Top-right corner
            ("C1", -5.08, -5.08),  # Bottom-left corner
            ("C3", 5.08, -5.08),   # Bottom-right corner
            ("A2", 0.0, 5.08),     # Top edge
            ("B1", -5.08, 0.0),    # Left edge
            # Center
            ("B2", 0.0, 0.0),      # Center pin
        ]
        
        results = classify_pin_rings(pins)
        
        # All corners and edges should be OUTER
        outer_pins = [r for r in results if r.ring == PinRing.OUTER]
        assert len(outer_pins) == 6, "Expected 6 outer pins"
        
        # Center should be CENTER
        center_pins = [r for r in results if r.ring == PinRing.CENTER]
        assert len(center_pins) == 1, "Expected 1 center pin"
        assert center_pins[0].pin_name == "B2"

    def test_escape_direction_vectors(self):
        """Test that escape directions point away from center."""
        pins = [
            ("N", 0.0, 10.0),   # North
            ("S", 0.0, -10.0),  # South
            ("E", 10.0, 0.0),   # East
            ("W", -10.0, 0.0),  # West
        ]
        
        results = classify_pin_rings(pins)
        
        # North pin should escape north (0, 1)
        north = next(r for r in results if r.pin_name == "N")
        assert abs(north.escape_direction[0]) < 0.01  # x ~ 0
        assert abs(north.escape_direction[1] - 1.0) < 0.01  # y ~ 1
        
        # East pin should escape east (1, 0)
        east = next(r for r in results if r.pin_name == "E")
        assert abs(east.escape_direction[0] - 1.0) < 0.01  # x ~ 1
        assert abs(east.escape_direction[1]) < 0.01  # y ~ 0

    def test_custom_ring_thresholds(self):
        """Test classification with custom ring thresholds."""
        pins = [
            ("P1", 10.0, 0.0),  # Distance = 10mm
            ("P2", 7.0, 0.0),   # Distance = 7mm
            ("P3", 4.0, 0.0),   # Distance = 4mm
            ("P4", 1.0, 0.0),   # Distance = 1mm
        ]
        
        # Custom thresholds: [9, 6, 3, 0.5]
        thresholds = [9.0, 6.0, 3.0, 0.5]
        results = classify_pin_rings(pins, ring_thresholds=thresholds)
        
        assert results[0].ring == PinRing.OUTER   # 10 >= 9
        assert results[1].ring == PinRing.RING_2  # 7 >= 6
        assert results[2].ring == PinRing.RING_3  # 4 >= 3
        assert results[3].ring == PinRing.RING_4  # 1 >= 0.5

    def test_angle_calculation(self):
        """Test that angles are computed correctly."""
        pins = [
            ("East", 10.0, 0.0),    # 0 radians
            ("North", 0.0, 10.0),   # π/2 radians
            ("West", -10.0, 0.0),   # π radians
            ("South", 0.0, -10.0),  # -π/2 radians
        ]
        
        results = classify_pin_rings(pins)
        
        east = next(r for r in results if r.pin_name == "East")
        assert abs(east.angle - 0.0) < 0.01
        
        north = next(r for r in results if r.pin_name == "North")
        assert abs(north.angle - math.pi/2) < 0.01
        
        west = next(r for r in results if r.pin_name == "West")
        assert abs(abs(west.angle) - math.pi) < 0.01

    def test_empty_pins(self):
        """Test handling of empty pin list."""
        results = classify_pin_rings([])
        assert results == []

    def test_single_pin(self):
        """Test classification of a single pin."""
        pins = [("A1", 5.0, 5.0)]
        results = classify_pin_rings(pins)
        
        assert len(results) == 1
        # Single pin should be classified as OUTER
        assert results[0].ring == PinRing.OUTER


class TestRingStrategy:
    """Tests for ring escape strategy mapping."""

    def test_outer_ring_strategy(self):
        """Outer ring should use direct surface escape."""
        strategy = get_ring_strategy(PinRing.OUTER)
        assert strategy == "direct_surface"

    def test_inner_ring_strategies(self):
        """Inner rings should use progressively longer fanouts."""
        assert get_ring_strategy(PinRing.RING_2) == "short_fanout"
        assert get_ring_strategy(PinRing.RING_3) == "medium_fanout"
        assert get_ring_strategy(PinRing.RING_4) == "long_fanout"

    def test_center_strategy(self):
        """Center pins should connect to planes."""
        strategy = get_ring_strategy(PinRing.CENTER)
        assert strategy == "plane_connect"


class TestRealWorldBGA:
    """Tests with realistic BGA pin patterns."""

    def test_bga_64_8x8(self):
        """Test 8x8 BGA (64 pins) with 1mm pitch."""
        pitch = 1.0  # mm
        pins = []
        
        # Generate 8x8 grid
        for row in range(8):
            for col in range(8):
                pin_name = f"{chr(65+row)}{col+1}"  # A1, A2, ..., H8
                x = (col - 3.5) * pitch  # Center at origin
                y = (row - 3.5) * pitch
                pins.append((pin_name, x, y))
        
        results = classify_pin_rings(pins)
        
        # Outer edge (perimeter) should be OUTER
        outer_count = sum(1 for r in results if r.ring == PinRing.OUTER)
        assert outer_count > 0, "Should have outer ring pins"
        
        # Center pins should be CENTER or inner rings
        center_area = sum(1 for r in results if r.ring in (PinRing.CENTER, PinRing.RING_4))
        assert center_area > 0, "Should have center/inner pins"
        
        # All pins classified
        assert len(results) == 64

    def test_qfn_32_peripheral_only(self):
        """Test QFN-32 (pins on edges only, no center)."""
        # QFN has pins around perimeter, 7x7mm package
        pins = []
        
        # 8 pins per side
        for i in range(8):
            # Top edge
            pins.append((f"T{i+1}", (i - 3.5) * 0.65, 3.5))
            # Bottom edge  
            pins.append((f"B{i+1}", (i - 3.5) * 0.65, -3.5))
            # Left edge (skip corners to avoid duplicates)
            if 0 < i < 7:
                pins.append((f"L{i+1}", -3.5, (i - 3.5) * 0.65))
            # Right edge
            if 0 < i < 7:
                pins.append((f"R{i+1}", 3.5, (i - 3.5) * 0.65))
        
        results = classify_pin_rings(pins)
        
        # All pins should be OUTER (peripheral package)
        outer_count = sum(1 for r in results if r.ring == PinRing.OUTER)
        assert outer_count == len(pins), "All QFN pins should be outer ring"
