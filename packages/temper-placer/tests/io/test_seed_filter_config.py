"""Tests for the seed_filter config knobs in PlacementConstraints.

@req(2026-06-23-004, R4)
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.io.config_loader import (
    ConfigValidationError,
    PlacementConstraints,
    SeedFilterConfig,
    load_constraints,
)


def _write_config(tmp_path, data: dict) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data))
    return str(p)


class TestConfigDefaults:
    def test_config_defaults_present(self) -> None:
        c = PlacementConstraints()
        assert c.seed_filter == SeedFilterConfig(enabled=True, threshold=0.7, hv_threshold=0.5)

    def test_config_loader_defaults(self, tmp_path) -> None:
        path = _write_config(tmp_path, {"board": {"width_mm": 50, "height_mm": 50}})
        c = load_constraints(path)
        assert c.seed_filter.enabled is True
        assert c.seed_filter.threshold == 0.7
        assert c.seed_filter.hv_threshold == 0.5

    def test_config_override_respected(self, tmp_path) -> None:
        path = _write_config(
            tmp_path,
            {
                "board": {"width_mm": 50, "height_mm": 50},
                "seed_filter": {"enabled": False, "threshold": 0.3, "hv_threshold": 0.1},
            },
        )
        c = load_constraints(path)
        assert c.seed_filter.enabled is False
        assert c.seed_filter.threshold == 0.3
        assert c.seed_filter.hv_threshold == 0.1

    def test_config_partial_override(self, tmp_path) -> None:
        path = _write_config(
            tmp_path,
            {"board": {"width_mm": 50, "height_mm": 50}, "seed_filter": {"threshold": 0.4}},
        )
        c = load_constraints(path)
        assert c.seed_filter.enabled is True
        assert c.seed_filter.threshold == 0.4
        assert c.seed_filter.hv_threshold == 0.5


class TestConfigValidation:
    def test_invalid_threshold_rejected(self) -> None:
        with pytest.raises(ValidationError, match="less_than_equal"):
            SeedFilterConfig(threshold=1.5, hv_threshold=0.5)

    def test_negative_threshold_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater_than_equal"):
            SeedFilterConfig(threshold=-0.1, hv_threshold=0.5)

    def test_invalid_hv_threshold_rejected(self) -> None:
        with pytest.raises(ValidationError, match="less_than_equal"):
            SeedFilterConfig(threshold=0.7, hv_threshold=2.0)

    def test_non_finite_threshold_rejected(self) -> None:
        with pytest.raises(ValidationError, match="less_than_equal"):
            SeedFilterConfig(threshold=float("inf"), hv_threshold=0.5)

    def test_loader_rejects_invalid_threshold(self, tmp_path) -> None:
        path = _write_config(
            tmp_path,
            {"board": {"width_mm": 50, "height_mm": 50}, "seed_filter": {"threshold": 1.5}},
        )
        with pytest.raises(ConfigValidationError, match="less_than_equal"):
            load_constraints(path)


class TestStageIntegration:
    def test_stage_receives_seed_filter_from_constraints(self) -> None:
        c = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(c)
        assert stage.seed_filter is c.seed_filter

    def test_stage_explicit_seed_filter_overrides_constraints(self) -> None:
        c = PlacementConstraints()
        override = SeedFilterConfig(enabled=False, threshold=0.2, hv_threshold=0.1)
        stage = PhasedComponentAssignmentStage(c, seed_filter=override)
        assert stage.seed_filter is override
        assert stage.seed_filter.enabled is False

    def test_stage_explicit_none_falls_back_to_constraints(self) -> None:
        c = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(c, seed_filter=None)
        assert stage.seed_filter is c.seed_filter
