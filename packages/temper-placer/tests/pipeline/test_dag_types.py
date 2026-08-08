"""Tests for dag_types module."""

from temper_placer.pipeline.dag_types import StageResult


def test_stage_result_success_default():
    """StageResult.success() returns a StageResult with empty outputs."""
    sr = StageResult.success()
    assert isinstance(sr, StageResult)
    assert sr.outputs == {}
    assert sr.duration_s == 0.0


def test_stage_result_success_with_outputs():
    """StageResult.success() accepts an outputs dict."""
    sr = StageResult.success({"key": "value"})
    assert sr.outputs == {"key": "value"}
    assert sr.duration_s == 0.0


def test_stage_result_success_with_none_outputs():
    """StageResult.success(None) uses empty dict."""
    sr = StageResult.success(None)
    assert sr.outputs == {}
