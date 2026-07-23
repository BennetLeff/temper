"""Unit tests for leaf config Pydantic models.

@req(2026-07-22-005, R1)
@req(2026-07-22-005, R2)
"""

import pytest
from pydantic import ValidationError

from temper_placer._constraint_types.config import (
    AestheticConstraints,
    FeedbackConfig,
    LossConfig,
    LossesConfig,
    ManufacturingConstraints,
    PlacementInitialization,
    SeedFilterConfig,
)


class TestLossConfig:
    def test_default_construction(self):
        lc = LossConfig()
        assert lc.weight == 1.0
        assert lc.enabled is True
        assert lc.margin is None

    def test_custom_construction(self):
        lc = LossConfig(weight=5.0, enabled=False, margin=2.0)
        assert lc.weight == 5.0
        assert lc.enabled is False
        assert lc.margin == 2.0

    def test_weight_zero_valid(self):
        lc = LossConfig(weight=0.0)
        assert lc.weight == 0.0

    def test_negative_weight_rejected(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            LossConfig(weight=-1.0)

    def test_weight_too_large_rejected(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            LossConfig(weight=2e6)

    def test_inf_weight_rejected(self):
        with pytest.raises(ValidationError):
            LossConfig(weight=float("inf"))

    def test_nan_weight_rejected(self):
        with pytest.raises(ValidationError):
            LossConfig(weight=float("nan"))

    def test_string_weight_rejected(self):
        with pytest.raises(ValidationError):
            LossConfig(weight="heavy")

    def test_frozen_prevents_mutation(self):
        lc = LossConfig(weight=1.0)
        with pytest.raises(ValidationError):
            lc.weight = 2.0


class TestLossesConfig:
    def test_default_construction(self):
        lsc = LossesConfig()
        assert lsc.overlap is None
        assert lsc.boundary is None

    def test_set_single_loss(self):
        lsc = LossesConfig(overlap=LossConfig(weight=100.0))
        assert lsc.overlap.weight == 100.0

    def test_get_active_losses(self):
        lsc = LossesConfig(
            overlap=LossConfig(weight=100.0),
            boundary=LossConfig(weight=50.0, enabled=False),
            wirelength=LossConfig(weight=10.0),
        )
        active = lsc.get_active_losses()
        assert "overlap" in active
        assert "boundary" not in active  # disabled
        assert "wirelength" in active
        assert active["overlap"].weight == 100.0

    def test_get_active_losses_all_none(self):
        lsc = LossesConfig()
        assert lsc.get_active_losses() == {}

    def test_get_weights(self):
        lsc = LossesConfig(
            overlap=LossConfig(weight=100.0),
            boundary=LossConfig(weight=50.0, enabled=False),
            wirelength=LossConfig(weight=10.0),
        )
        weights = lsc.get_weights()
        assert weights == {"overlap": 100.0, "wirelength": 10.0}


class TestFeedbackConfig:
    def test_default_construction(self):
        fc = FeedbackConfig()
        assert fc.max_iterations == 5
        assert fc.violation_threshold == 5
        assert fc.expansion_per_violation == 0.5

    def test_max_iterations_gt_1000_rejected(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            FeedbackConfig(max_iterations=2000)

    def test_max_iterations_negative_rejected(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            FeedbackConfig(max_iterations=-1)


class TestAestheticConstraints:
    def test_default_construction(self):
        ac = AestheticConstraints()
        assert ac.grid_size_mm == 0.5
        assert ac.align_by_prefix is True

    def test_grid_size_zero_rejected(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            AestheticConstraints(grid_size_mm=0)

    def test_grid_size_negative_rejected(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            AestheticConstraints(grid_size_mm=-1)


class TestManufacturingConstraints:
    def test_default_construction(self):
        mc = ManufacturingConstraints()
        assert mc.target_margin_mm == 0.1
        assert mc.margin_weight == 0.0
        assert mc.etch_tolerance_mm == 0.02

    def test_margin_zero_rejected(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            ManufacturingConstraints(target_margin_mm=0)


class TestSeedFilterConfig:
    def test_default_construction(self):
        sf = SeedFilterConfig()
        assert sf.enabled is True
        assert sf.threshold == 0.7
        assert sf.hv_threshold == 0.5

    def test_threshold_above_1_rejected(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            SeedFilterConfig(threshold=1.5)

    def test_threshold_below_0_rejected(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            SeedFilterConfig(threshold=-0.1)

    def test_hv_threshold_above_1_rejected(self):
        with pytest.raises(ValidationError, match="less_than_equal"):
            SeedFilterConfig(hv_threshold=2.0)

    def test_nan_rejected(self):
        with pytest.raises(ValidationError):
            SeedFilterConfig(threshold=float("nan"))

    def test_string_rejected(self):
        with pytest.raises(ValidationError):
            SeedFilterConfig(threshold="high")

    def test_no_post_init_method(self):
        """SeedFilterConfig.__post_init__ must be gone after Pydantic migration."""
        assert not hasattr(SeedFilterConfig, "__post_init__")


class TestPlacementInitialization:
    def test_default_construction(self):
        pi = PlacementInitialization()
        assert pi.thermal_anchoring is False
        assert pi.anchoring_grid_resolution == 50

    def test_custom_construction(self):
        pi = PlacementInitialization(thermal_anchoring=True, anchoring_grid_resolution=100)
        assert pi.thermal_anchoring is True
        assert pi.anchoring_grid_resolution == 100

    def test_grid_resolution_zero_rejected(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            PlacementInitialization(anchoring_grid_resolution=0)
