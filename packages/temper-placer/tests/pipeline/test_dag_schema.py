"""Tests for dag_schema: manifest loading, validation, cycle/dependency checks."""

import warnings
from pathlib import Path

import pytest
import yaml

from temper_placer.pipeline.dag_schema import (
    StageDAGManifest,
    load_manifest,
)
from temper_placer.pipeline.dag_types import (
    DAGCycleError,
    DAGDuplicateStageError,
    DAGExprSyntaxError,
    DAGMissingDependencyError,
)


def _write_manifest(path: Path, stages: list[dict], pipeline_name: str = "test") -> None:
    manifest = {
        "pipeline": {"name": pipeline_name, "version": "1.0.0"},
        "stages": stages,
    }
    with open(path, "w") as f:
        yaml.dump(manifest, f)


class TestLoadManifest:
    def test_valid_minimal_manifest(self, minimal_manifest):
        manifest = load_manifest(minimal_manifest)
        assert manifest.pipeline.name == "minimal-test"
        assert len(manifest.stages) == 2

    def test_stage_names_are_preserved(self, minimal_manifest):
        manifest = load_manifest(minimal_manifest)
        names = [s.name for s in manifest.stages]
        assert names == ["producer", "consumer"]

    def test_requires_and_provides(self, minimal_manifest):
        manifest = load_manifest(minimal_manifest)
        producer = manifest.stages[0]
        assert producer.requires == []
        assert producer.provides == ["data_a"]
        consumer = manifest.stages[1]
        assert consumer.requires == ["data_a"]
        assert consumer.provides == ["data_b"]

    def test_load_default_manifest(self, default_manifest_path):
        manifest = load_manifest(default_manifest_path)
        assert manifest.pipeline.name == "temper-default"
        assert len(manifest.stages) == 8
        names = [s.name for s in manifest.stages]
        assert names == [
            "input", "semantic", "topological", "preflight",
            "geometric", "routing", "refinement", "output",
        ]

    def test_default_manifest_has_data_keys(self, default_manifest_path):
        manifest = load_manifest(default_manifest_path)
        assert manifest.data_keys is not None
        assert "board" in manifest.data_keys
        assert "netlist" in manifest.data_keys

    def test_default_manifest_routing_has_feedback(self, default_manifest_path):
        manifest = load_manifest(default_manifest_path)
        routing = next(s for s in manifest.stages if s.name == "routing")
        assert len(routing.feedback_contracts) == 1
        fc = routing.feedback_contracts[0]
        assert fc.name == "routability-retry"
        assert fc.target_stage == "geometric"
        assert fc.trigger.metric == "routing_completion"
        assert fc.trigger.condition == "lt"
        assert fc.trigger.threshold == 0.5
        assert fc.max_retriggers == 3

    def test_skip_if_expressions_are_valid(self, default_manifest_path):
        manifest = load_manifest(default_manifest_path)
        for stage in manifest.stages:
            if stage.skip_if:
                assert stage.skip_if is not None


class TestDuplicateStageDetection:
    def test_duplicate_names_raise(self, tmp_path):
        stages = [
            {"name": "dup", "handler": "m.H", "requires": [], "provides": []},
            {"name": "dup", "handler": "m.H2", "requires": [], "provides": []},
        ]
        path = tmp_path / "dup.yaml"
        _write_manifest(path, stages)
        with pytest.raises(DAGDuplicateStageError, match="dup"):
            load_manifest(path)


class TestCycleDetection:
    def test_direct_cycle_detected(self, tmp_path):
        stages = [
            {"name": "a", "handler": "m.A", "requires": ["key_b"], "provides": ["key_a"]},
            {"name": "b", "handler": "m.B", "requires": ["key_a"], "provides": ["key_b"]},
        ]
        path = tmp_path / "cycle.yaml"
        _write_manifest(path, stages)
        with pytest.raises(DAGCycleError, match="Cycle"):
            load_manifest(path)

    def test_indirect_cycle_detected(self, tmp_path):
        stages = [
            {"name": "a", "handler": "m.A", "requires": ["key_c"], "provides": ["key_a"]},
            {"name": "b", "handler": "m.B", "requires": ["key_a"], "provides": ["key_b"]},
            {"name": "c", "handler": "m.C", "requires": ["key_b"], "provides": ["key_c"]},
        ]
        path = tmp_path / "cycle3.yaml"
        _write_manifest(path, stages)
        with pytest.raises(DAGCycleError):
            load_manifest(path)

    def test_acyclic_dag_loads(self, tmp_path):
        stages = [
            {"name": "a", "handler": "m.A", "requires": [], "provides": ["key_a"]},
            {"name": "b", "handler": "m.B", "requires": ["key_a"], "provides": ["key_b"]},
            {"name": "c", "handler": "m.C", "requires": ["key_b"], "provides": ["key_c"]},
            {"name": "d", "handler": "m.D", "requires": ["key_a", "key_b"], "provides": ["key_d"]},
        ]
        path = tmp_path / "acyclic.yaml"
        _write_manifest(path, stages)
        manifest = load_manifest(path)
        assert len(manifest.stages) == 4


class TestMissingDependency:
    def test_missing_dependency_raises(self, tmp_path):
        stages = [
            {
                "name": "consumer",
                "handler": "m.C",
                "requires": ["nonexistent_key"],
                "provides": ["output"],
            },
        ]
        path = tmp_path / "missing.yaml"
        _write_manifest(path, stages)
        with pytest.raises(DAGMissingDependencyError, match="nonexistent_key"):
            load_manifest(path)

    def test_builtin_config_keys_are_ok(self, tmp_path):
        stages = [
            {
                "name": "s",
                "handler": "m.S",
                "requires": ["input_pcb", "epochs"],
                "provides": ["x"],
            },
        ]
        path = tmp_path / "builtin.yaml"
        _write_manifest(path, stages)
        manifest = load_manifest(path)
        assert len(manifest.stages) == 1


class TestFeedbackContractValidation:
    def test_invalid_target_stage_raises(self, tmp_path):
        stages = [
            {
                "name": "producer",
                "handler": "m.P",
                "requires": [],
                "provides": ["data"],
                "feedback_contracts": [
                    {
                        "name": "bad-feedback",
                        "trigger": {"metric": "data", "condition": "lt", "threshold": 0.5},
                        "target_stage": "nonexistent",
                        "max_retriggers": 1,
                    }
                ],
            },
        ]
        path = tmp_path / "bad_feedback.yaml"
        _write_manifest(path, stages)
        with pytest.raises(ValueError, match="nonexistent"):
            load_manifest(path)

    def test_valid_feedback_contract(self, tmp_path):
        stages = [
            {
                "name": "producer",
                "handler": "m.P",
                "requires": [],
                "provides": ["data"],
                "feedback_contracts": [
                    {
                        "name": "good-feedback",
                        "trigger": {"metric": "data", "condition": "lt", "threshold": 0.5},
                        "target_stage": "producer",
                        "max_retriggers": 2,
                    }
                ],
            },
        ]
        path = tmp_path / "good_feedback.yaml"
        _write_manifest(path, stages)
        manifest = load_manifest(path)
        assert len(manifest.stages[0].feedback_contracts) == 1


class TestSkipIfValidation:
    def test_invalid_skip_if_raises(self, tmp_path):
        stages = [
            {
                "name": "s",
                "handler": "m.S",
                "requires": [],
                "provides": [],
                "skip_if": "config.x + 1",
            },
        ]
        path = tmp_path / "bad_skip.yaml"
        _write_manifest(path, stages)
        with pytest.raises(DAGExprSyntaxError):
            load_manifest(path)

    def test_valid_skip_if_parses(self, tmp_path):
        stages = [
            {
                "name": "s",
                "handler": "m.S",
                "requires": [],
                "provides": [],
                "skip_if": "config.dry_run == true",
            },
        ]
        path = tmp_path / "good_skip.yaml"
        _write_manifest(path, stages)
        manifest = load_manifest(path)
        assert manifest.stages[0].skip_if == "config.dry_run == true"


class TestUnreachableStageWarning:
    def test_disconnected_dag_warns(self, tmp_path):
        stages = [
            {"name": "root", "handler": "m.R", "requires": [], "provides": ["key_r"]},
            {
                "name": "disconnected",
                "handler": "m.D",
                "requires": ["key_r"],
                "provides": ["key_d"],
            },
            {
                "name": "orphan",
                "handler": "m.O",
                "requires": ["key_o"],
                "provides": ["key_z"],
            },
        ]
        path = tmp_path / "unreachable.yaml"
        _write_manifest(path, stages)
        with pytest.raises(DAGMissingDependencyError, match="key_o"):
            load_manifest(path)

    def test_all_reachable_no_warning(self, tmp_path):
        stages = [
            {"name": "a", "handler": "m.A", "requires": [], "provides": ["key_a"]},
            {"name": "b", "handler": "m.B", "requires": ["key_a"], "provides": ["key_b"]},
        ]
        path = tmp_path / "reachable.yaml"
        _write_manifest(path, stages)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            load_manifest(path)
            user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
            assert len(user_warnings) == 0


class TestStageDefinitionDefaults:
    def test_empty_requires_provides(self, tmp_path):
        stages = [{"name": "s", "handler": "m.S"}]
        path = tmp_path / "empty.yaml"
        _write_manifest(path, stages)
        manifest = load_manifest(path)
        assert manifest.stages[0].requires == []
        assert manifest.stages[0].provides == []

    def test_retry_config_defaults(self, tmp_path):
        stages = [{"name": "s", "handler": "m.S", "requires": [], "provides": []}]
        path = tmp_path / "retry_default.yaml"
        _write_manifest(path, stages)
        manifest = load_manifest(path)
        assert manifest.stages[0].retry is None
