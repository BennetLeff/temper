"""Tests for dag_types: DataContext, StageResult, error types."""

import pytest

from temper_placer.pipeline.dag_types import (
    DAGCycleError,
    DAGDuplicateStageError,
    DAGExprError,
    DAGExprSyntaxError,
    DAGMissingDependencyError,
    FeedbackExhaustedError,
    StageResult,
    StageTimeoutError,
)


class TestStageResult:
    def test_default_construction(self):
        result = StageResult()
        assert result.outputs == {}
        assert result.duration_s == 0.0

    def test_with_outputs(self):
        result = StageResult(outputs={"key": "value"}, duration_s=1.5)
        assert result.outputs == {"key": "value"}
        assert result.duration_s == 1.5

    def test_success_classmethod_default(self):
        result = StageResult.success()
        assert result.outputs == {}
        assert result.duration_s == 0.0

    def test_success_classmethod_with_outputs(self):
        result = StageResult.success({"a": 1})
        assert result.outputs == {"a": 1}
        assert result.duration_s == 0.0


class TestDAGCycleError:
    def test_cycle_path_in_message(self):
        err = DAGCycleError(["a", "b", "c"])
        assert err.cycle == ["a", "b", "c"]
        assert "a -> b -> c" in str(err)

    def test_single_edge_cycle(self):
        err = DAGCycleError(["x", "x"])
        assert err.cycle == ["x", "x"]
        assert "x -> x" in str(err)


class TestDAGMissingDependencyError:
    def test_fields(self):
        err = DAGMissingDependencyError(key="missing_key", requiring_stage="consumer")
        assert err.key == "missing_key"
        assert err.requiring_stage == "consumer"
        assert "missing_key" in str(err)
        assert "consumer" in str(err)


class TestDAGDuplicateStageError:
    def test_fields(self):
        err = DAGDuplicateStageError(name="duplicate")
        assert err.name == "duplicate"
        assert "duplicate" in str(err)


class TestStageTimeoutError:
    def test_fields(self):
        err = StageTimeoutError(stage_name="slow_stage", timeout_s=30.0)
        assert err.stage_name == "slow_stage"
        assert err.timeout_s == 30.0
        assert "slow_stage" in str(err)
        assert "30.0" in str(err)


class TestFeedbackExhaustedError:
    def test_fields(self):
        err = FeedbackExhaustedError(
            contract_name="retry_contract", stage_name="geometric", attempts=3
        )
        assert err.contract_name == "retry_contract"
        assert err.stage_name == "geometric"
        assert err.attempts == 3
        assert "retry_contract" in str(err)
        assert "geometric" in str(err)
        assert "3" in str(err)


class TestDAGExprError:
    def test_message(self):
        err = DAGExprError("bad expression")
        assert "bad expression" in str(err)


class TestDAGExprSyntaxError:
    def test_message(self):
        err = DAGExprSyntaxError("syntax error at pos 5")
        assert "syntax error at pos 5" in str(err)


class TestErrorInheritance:
    def test_all_errors_inherit_from_exception(self):
        errors = [
            DAGCycleError(["a"]),
            DAGMissingDependencyError("k", "s"),
            DAGDuplicateStageError("d"),
            StageTimeoutError("s", 1.0),
            FeedbackExhaustedError("c", "s", 1),
            DAGExprError("e"),
            DAGExprSyntaxError("e"),
        ]
        for err in errors:
            assert isinstance(err, Exception), f"{type(err).__name__} should be Exception"
