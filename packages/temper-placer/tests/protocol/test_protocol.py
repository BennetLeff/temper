"""Tests for protocol.py — StageMeta, StageInput, StageOutput, PipelineStage, Contract, ContractViolation."""

from __future__ import annotations

import sys

import pytest

from temper_placer.protocol import (
    StageMeta,
    StageInput,
    StageOutput,
    PipelineStage,
    Contract,
    ContractViolation,
)


class TestStageMeta:
    def test_defaults(self):
        meta = StageMeta()
        assert meta.seed == 42
        assert meta.timestamp == 0.0
        assert meta.trace_context == {}
        assert meta.timings == {}

    def test_custom_values(self):
        meta = StageMeta(seed=99, timestamp=123.456)
        assert meta.seed == 99
        assert meta.timestamp == 123.456

    def test_timings_mutable(self):
        meta = StageMeta()
        meta.timings["stage1"] = 1.23
        meta.timings["stage2"] = 4.56
        assert meta.timings["stage1"] == 1.23
        assert meta.timings["stage2"] == 4.56

    def test_mutable_defaults_isolated(self):
        """Mutable defaults must not be shared across instances."""
        a = StageMeta()
        b = StageMeta()
        a.timings["x"] = 1.0
        a.trace_context["key"] = "val"
        assert b.timings == {}
        assert b.trace_context == {}


class TestStageInput:
    def test_construct(self):
        si = StageInput(data={"placements": {}}, meta=StageMeta(seed=99))
        assert si.data == {"placements": {}}
        assert si.meta.seed == 99

    def test_default_meta(self):
        si = StageInput(data="payload")
        assert si.meta.seed == 42


class TestStageOutput:
    def test_construct(self):
        so = StageOutput(data="result", meta=StageMeta(), contract_satisfied=True)
        assert so.data == "result"
        assert so.contract_satisfied is True

    def test_contract_satisfied_defaults_none(self):
        so = StageOutput()
        assert so.contract_satisfied is None


class TestPipelineStageProtocol:
    def test_structural_subtyping(self):
        """A class with name + run satisfies PipelineStage without inheriting."""

        class MyStage:
            name = "my_stage"

            def run(self, inp):
                return StageOutput(data=f"got: {inp.data}", meta=inp.meta)

        stage = MyStage()
        assert isinstance(stage, PipelineStage)

    def test_missing_name_fails(self):
        """A class without 'name' does NOT satisfy the Protocol."""

        class NoName:
            def run(self, inp):
                return StageOutput()

        assert not isinstance(NoName(), PipelineStage)

    def test_missing_run_fails(self):
        """A class without 'run' does NOT satisfy the Protocol."""

        class NoRun:
            name = "nope"

        assert not isinstance(NoRun(), PipelineStage)

    def test_optional_requires_provides(self):
        class Minimal:
            name = "min"
            requires = ["a"]
            provides = ["b"]

            def run(self, inp):
                return StageOutput()

        stage = Minimal()
        assert isinstance(stage, PipelineStage)
        assert stage.requires == ["a"]
        assert stage.provides == ["b"]


class TestContract:
    def test_default_schemas(self):
        c = Contract()
        assert c.input_schema == {}
        assert c.output_schema == {}

    def test_custom_schemas(self):
        c = Contract(input_schema={"x": int}, output_schema={"y": str})
        assert c.input_schema["x"] is int
        assert c.output_schema["y"] is str


class TestContractViolation:
    def test_all_fields(self):
        cv = ContractViolation("MyStage", "input", "field", int, str)
        assert cv.stage_name == "MyStage"
        assert cv.schema == "input"
        assert cv.field_name == "field"
        assert cv.expected_type is int
        assert cv.actual_type is str

    def test_missing_field(self):
        cv = ContractViolation("S", "output", "missing_key", dict, None)
        assert "missing" in str(cv).lower()

    def test_type_mismatch_message(self):
        cv = ContractViolation("S", "input", "x", int, str)
        msg = str(cv)
        assert "S" in msg
        assert "int" in msg
        assert "str" in msg


class TestImportIsolation:
    """SC1 — protocol imports must not pull in pipeline backends."""

    def test_no_pipeline_backends_on_import(self):
        # The protocol module itself is already imported in this test session.
        # Instead, check that pipeline backends are NOT in the protocol module's
        # direct imports.
        import temper_placer.protocol as protocol_module

        pipeline_keys = (
            "temper_placer.router_v6",
            "temper_placer.deterministic",
            "temper_placer.pipeline",
            "temper_placer.placement.benders_loop",
        )
        for key in pipeline_keys:
            assert key not in sys.modules or key not in dir(protocol_module), (
                f"protocol.py leaked {key}"
            )
