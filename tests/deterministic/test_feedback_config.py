"""
Tests for feedback configuration extension (FEEDBACK-4).

Tests the zone adjustment parameters in the config system.
"""

import pytest
from pathlib import Path
from temper_placer.io.config_loader import load_constraints, FeedbackConfig


def test_feedback_config_has_defaults():
    """Feedback config should have sensible defaults."""
    config = FeedbackConfig()

    assert config.violation_threshold == 5
    assert config.expansion_per_violation == 0.5
    assert config.max_iterations == 5


def test_feedback_config_loads_from_yaml():
    """Feedback config should load from YAML file."""
    config_path = Path("configs/temper_deterministic_config.yaml")
    constraints = load_constraints(config_path)

    assert constraints.feedback is not None
    assert constraints.feedback.max_iterations > 0
    assert constraints.feedback.violation_threshold > 0
    assert constraints.feedback.expansion_per_violation > 0


def test_zone_has_expansion_parameters():
    """Zones should include expansion parameters from config."""
    config_path = Path("configs/temper_deterministic_config.yaml")
    constraints = load_constraints(config_path)

    assert len(constraints.zones) > 0

    # Check that zones have max_size and can_expand
    for zone in constraints.zones:
        assert zone.max_size is not None
        assert len(zone.max_size) == 2
        assert zone.can_expand is not None
        assert isinstance(zone.can_expand, list)


def test_zone_current_size_computed():
    """Zone should compute current size from bounds."""
    config_path = Path("configs/temper_deterministic_config.yaml")
    constraints = load_constraints(config_path)

    for zone in constraints.zones:
        # Compute current size
        x1, y1, x2, y2 = zone.bounds
        width = x2 - x1
        height = y2 - y1

        assert width > 0
        assert height > 0


def test_zone_expansion_room():
    """Zone should have expansion room within max_size."""
    config_path = Path("configs/temper_deterministic_config.yaml")
    constraints = load_constraints(config_path)

    for zone in constraints.zones:
        if zone.max_size:
            x1, y1, x2, y2 = zone.bounds
            current_width = x2 - x1
            current_height = y2 - y1

            max_width, max_height = zone.max_size

            # Current size should be <= max_size
            assert current_width <= max_width, f"Zone {zone.name} width exceeds max"
            assert current_height <= max_height, f"Zone {zone.name} height exceeds max"


def test_feedback_expected_types_configurable():
    """Expected violation types should be configurable."""
    # For now, expected_types are not in FeedbackConfig yet
    # This test documents the desired API
    pass


def test_zone_priority_field():
    """Zones should support priority field for conflict resolution."""
    # Priority field not yet implemented in Zone dataclass
    # This test documents the desired API
    pass


def test_backward_compatibility():
    """Config loading should work with zones missing expansion parameters."""
    # Zones in config should have sensible defaults if parameters omitted
    config_path = Path("configs/temper_deterministic_config.yaml")
    constraints = load_constraints(config_path)

    # Should not raise
    assert constraints is not None
