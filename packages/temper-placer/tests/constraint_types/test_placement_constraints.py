"""Unit tests for PlacementConstraints root Pydantic model.

@req(2026-07-22-005, R1)
@req(2026-07-22-005, R2)
@req(2026-07-22-005, R6)
"""

import pytest
from pydantic import ValidationError

from temper_placer._constraint_types.config import (
    AestheticConstraints,
    FeedbackConfig,
    LossConfig,
    LossesConfig,
    ManufacturingConstraints,
    PlacementConstraints,
    PlacementInitialization,
    SeedFilterConfig,
)


class TestPlacementConstraintsConstruction:
    def test_empty_construction(self):
        pc = PlacementConstraints()
        assert pc.board_width_mm == 100.0
        assert pc.board_height_mm == 150.0
        assert pc.board_margin_mm == 3.0
        assert pc.zones == []
        assert pc.component_groups == []
        assert isinstance(pc.aesthetics, AestheticConstraints)
        assert isinstance(pc.feedback, FeedbackConfig)
        assert isinstance(pc.manufacturing, ManufacturingConstraints)
        assert isinstance(pc.initialization, PlacementInitialization)
        assert isinstance(pc.seed_filter, SeedFilterConfig)
        assert pc.losses is None
        assert pc.net_classification is None

    def test_partial_construction(self):
        pc = PlacementConstraints(board_width_mm=100, board_height_mm=150, board_margin_mm=5.0)
        assert pc.board_width_mm == 100
        assert pc.board_height_mm == 150
        assert pc.board_margin_mm == 5.0

    def test_post_construction_mutation(self):
        pc = PlacementConstraints()
        pc.zones.append("test_zone")  # frozen=False allows mutation
        assert "test_zone" in pc.zones

    def test_get_zone_for_component(self):
        pc = PlacementConstraints(zone_assignments={"U1": "power_zone"})
        assert pc.get_zone_for_component("U1") == "power_zone"
        assert pc.get_zone_for_component("U2") is None

    def test_get_net_class(self):
        pc = PlacementConstraints(net_classes={"VCC": "Power"})
        assert pc.get_net_class("VCC") == "Power"
        # Default inference
        assert pc.get_net_class("HV_BUS") == "HighVoltage"
        assert pc.get_net_class("GND") == "Power"
        assert pc.get_net_class("UNKNOWN") == "Signal"


class TestPlacementConstraintsValidation:
    def test_board_width_zero_rejected(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            PlacementConstraints(board_width_mm=0)

    def test_board_width_negative_rejected(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            PlacementConstraints(board_width_mm=-10)

    def test_board_width_too_large_rejected(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            PlacementConstraints(board_width_mm=3000)

    def test_board_margin_negative_rejected(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            PlacementConstraints(board_margin_mm=-1)

    def test_extra_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            PlacementConstraints(unknown_key=42)

    def test_board_width_mm_at_boundary(self):
        pc = PlacementConstraints(board_width_mm=0.1)
        assert pc.board_width_mm == 0.1

        pc = PlacementConstraints(board_width_mm=2500)
        assert pc.board_width_mm == 2500

    def test_hv_clearance_mm_default(self):
        pc = PlacementConstraints()
        assert pc.hv_clearance_mm == 10.0


class TestPlacementConstraintsNestedModels:
    def test_nested_losses_config(self):
        pc = PlacementConstraints(
            losses=LossesConfig(overlap=LossConfig(weight=100.0)),
        )
        assert pc.losses.overlap.weight == 100.0

    def test_nested_feedback_config(self):
        pc = PlacementConstraints(
            feedback=FeedbackConfig(max_iterations=10),
        )
        assert pc.feedback.max_iterations == 10

    def test_nested_seed_filter(self):
        pc = PlacementConstraints(
            seed_filter=SeedFilterConfig(threshold=0.3),
        )
        assert pc.seed_filter.threshold == 0.3
