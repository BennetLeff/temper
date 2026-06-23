"""Tests for the seed_filter config knobs in PlacementConstraints.

@req(2026-06-23-004, R4)
"""

from __future__ import annotations

import pytest
import yaml

from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.io.config_loader import (
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
        """A config without seed_filter uses the K3 defaults."""
        # Bypass the loader; default-construct a PlacementConstraints.
        c = PlacementConstraints()
        assert c.seed_filter == SeedFilterConfig(enabled=True, threshold=0.7, hv_threshold=0.5)

    def test_config_loader_defaults(self, tmp_path) -> None:
        """The YAML loader returns the K3 defaults when seed_filter is omitted."""
        path = _write_config(tmp_path, {"board": {"width_mm": 50, "height_mm": 50}})
        c = load_constraints(path)
        assert c.seed_filter.enabled is True
        assert c.seed_filter.threshold == 0.7
        assert c.seed_filter.hv_threshold == 0.5

    def test_config_override_respected(self, tmp_path) -> None:
        """Explicit seed_filter override is reflected on the constraints."""
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
        """Missing keys in seed_filter fall back to defaults."""
        path = _write_config(
            tmp_path,
            {
                "board": {"width_mm": 50, "height_mm": 50},
                "seed_filter": {"threshold": 0.4},
            },
        )
        c = load_constraints(path)
        assert c.seed_filter.enabled is True
        assert c.seed_filter.threshold == 0.4
        assert c.seed_filter.hv_threshold == 0.5


class TestConfigValidation:
    def test_invalid_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
            SeedFilterConfig(threshold=1.5, hv_threshold=0.5)

    def test_negative_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
            SeedFilterConfig(threshold=-0.1, hv_threshold=0.5)

    def test_invalid_hv_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
            SeedFilterConfig(threshold=0.7, hv_threshold=2.0)

    def test_non_finite_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"must be finite"):
            SeedFilterConfig(threshold=float("inf"), hv_threshold=0.5)

    def test_loader_rejects_invalid_threshold(self, tmp_path) -> None:
        path = _write_config(
            tmp_path,
            {
                "board": {"width_mm": 50, "height_mm": 50},
                "seed_filter": {"threshold": 1.5},
            },
        )
        with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
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
