"""
Tests for U6: Soft-launch flip (WARNING -> hard-fail) for the
no_component_center_in_critical_bottleneck invariant.

Covers:
- WARNING-only behavior when DRC_FENCE_FAIL_ENABLED is False
- Hard-fail raises PhasedComponentAssignmentError when flag is True
- Env var TEMPER_DRC_FENCE_FAIL flips behavior at runtime
- MEDIUM/HIGH bottlenecks do not trigger the fence in either state
"""

from __future__ import annotations

import logging
import os

import pytest

from temper_placer.deterministic.channels import ChannelMap
from temper_placer.deterministic.flags import is_drc_fence_fail_enabled
from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentError,
    PhasedComponentAssignmentStage,
)
from temper_placer.io.config_loader import PlacementConstraints


def _cmap_with_critical() -> ChannelMap:
    grid = [[0.0] * 4 for _ in range(4)]
    return ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": 1000.0,
            "grid": grid,
            "bottlenecks": [
                {"x": 1, "y": 1, "layer": "F.Cu", "severity": "CRITICAL", "score": 1.0},
            ],
        }
    )


def _cmap_with_medium_high() -> ChannelMap:
    grid = [[0.0] * 4 for _ in range(4)]
    return ChannelMap._from_payload(
        {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": 1000.0,
            "grid": grid,
            "bottlenecks": [
                {"x": 0, "y": 0, "layer": "F.Cu", "severity": "MEDIUM", "score": 0.5},
                {"x": 1, "y": 0, "layer": "F.Cu", "severity": "HIGH", "score": 0.9},
            ],
        }
    )


def _stage(cmap: ChannelMap) -> PhasedComponentAssignmentStage:
    return PhasedComponentAssignmentStage(
        constraints=PlacementConstraints(),
        slot_spacing=10.0,
        channel_map=cmap,
    )


@pytest.fixture
def fence_env(monkeypatch):
    """Default: clear TEMPER_DRC_FENCE_FAIL for the test duration."""
    monkeypatch.delenv("TEMPER_DRC_FENCE_FAIL", raising=False)
    yield monkeypatch


class TestFenceWarningOnly:
    def test_fence_warning_only_when_disabled(self, fence_env, caplog):
        stage = _stage(_cmap_with_critical())
        placements = {"U1": (1.5, 1.5)}
        with caplog.at_level(logging.WARNING):
            violations = stage._check_critical_bottlenecks(placements)
        assert len(violations) == 1
        assert any("CRITICAL" in r.message for r in caplog.records)
        # The default (env var unset) is False.
        assert is_drc_fence_fail_enabled() is False


class TestFenceHardFail:
    def test_fence_hard_fails_when_enabled(self, fence_env, caplog):
        fence_env.setenv("TEMPER_DRC_FENCE_FAIL", "1")
        assert is_drc_fence_fail_enabled() is True
        stage = _stage(_cmap_with_critical())
        placements = {"U1": (1.5, 1.5)}
        with pytest.raises(PhasedComponentAssignmentError) as exc:
            stage._check_critical_bottlenecks(placements)
        msg = str(exc.value)
        assert "U1" in msg
        assert "CRITICAL" in msg


class TestFenceEnvVarOverrides:
    def test_fence_env_var_overrides_default(self, fence_env, caplog):
        # Default is False.
        assert is_drc_fence_fail_enabled() is False
        fence_env.setenv("TEMPER_DRC_FENCE_FAIL", "true")
        assert is_drc_fence_fail_enabled() is True
        fence_env.setenv("TEMPER_DRC_FENCE_FAIL", "FALSE")
        assert is_drc_fence_fail_enabled() is False
        fence_env.setenv("TEMPER_DRC_FENCE_FAIL", "0")
        assert is_drc_fence_fail_enabled() is False
        fence_env.setenv("TEMPER_DRC_FENCE_FAIL", "yes")
        assert is_drc_fence_fail_enabled() is True
        # Unknown values are falsy.
        fence_env.setenv("TEMPER_DRC_FENCE_FAIL", "garbage")
        assert is_drc_fence_fail_enabled() is False


class TestFenceNonCriticalUnaffected:
    def test_fence_non_critical_violations_unaffected_disabled(self, fence_env, caplog):
        """MEDIUM/HIGH do not trigger the fence when disabled."""
        stage = _stage(_cmap_with_medium_high())
        placements = {
            "U1": (0.5, 0.5),  # MEDIUM
            "U2": (1.5, 0.5),  # HIGH
        }
        with caplog.at_level(logging.WARNING):
            violations = stage._check_critical_bottlenecks(placements)
        assert violations == []
        # No fence-fail WARNINGs logged
        assert not any("DRC fence violation" in r.message for r in caplog.records)

    def test_fence_non_critical_violations_unaffected_enabled(self, fence_env, caplog):
        """MEDIUM/HIGH do not trigger the fence when enabled either."""
        fence_env.setenv("TEMPER_DRC_FENCE_FAIL", "1")
        stage = _stage(_cmap_with_medium_high())
        placements = {
            "U1": (0.5, 0.5),  # MEDIUM
            "U2": (1.5, 0.5),  # HIGH
        }
        # No raise, no violations.
        violations = stage._check_critical_bottlenecks(placements)
        assert violations == []


class TestSingleSourceOfTruth:
    def test_flag_constant_lives_in_flags_module(self):
        # DRC_FENCE_FAIL_ENABLED is a public constant for callers that
        # want a single read at import time; is_drc_fence_fail_enabled()
        # is the runtime-resolved version.
        from temper_placer.deterministic import flags

        assert hasattr(flags, "DRC_FENCE_FAIL_ENABLED")
        assert hasattr(flags, "is_drc_fence_fail_enabled")
        # The phased stage imports the function, not the constant.
        import inspect

        src = inspect.getsource(
            PhasedComponentAssignmentStage._check_critical_bottlenecks
        )
        assert "is_drc_fence_fail_enabled" in src
