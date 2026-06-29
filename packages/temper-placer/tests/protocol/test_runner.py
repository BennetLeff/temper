"""Tests for runner.py — PipelineRunner, DataFlowError, resolve_and_run, StrategyExhaustedError."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from temper_placer.protocol import (
    Contract,
    ContractViolation,
    StageInput,
    StageOutput,
)
from temper_placer.runner import (
    DataFlowError,
    PipelineRunner,
    StrategyExhaustedError,
    resolve_and_run,
)
from temper_placer.strategy_registry import register

# ---- Test helpers -----------------------------------------------------------


class CountingStage:
    """A PipelineStage that records calls."""

    name = "counting"
    requires: list[str] = []
    provides: list[str] = []
    contract = None

    def __init__(self, name="counting", requires=None, provides=None, contract=None):
        self.name = name
        self.requires = requires or []
        self.provides = provides or []
        self.contract = contract
        self.call_count = 0
        self.last_input = None

    def run(self, inp):
        self.call_count += 1
        self.last_input = inp
        return StageOutput(
            data=f"result_{self.name}",
            meta=inp.meta,
        )


class RaisingStage:
    """A PipelineStage that always raises."""

    name = "raiser"
    requires: list[str] = []
    provides: list[str] = []
    contract = None

    def run(self, _inp):
        raise RuntimeError("deliberate failure")


# ---- PipelineRunner ---------------------------------------------------------


class TestPipelineRunner:
    def test_sequential_execution(self):
        s1 = CountingStage("s1", provides=["a"])
        s2 = CountingStage("s2", requires=["a"], provides=["b"])
        runner = PipelineRunner([s1, s2])
        result = runner.run(StageInput(data="hello"))
        assert result.data == "result_s2"
        assert s1.call_count == 1
        assert s2.call_count == 1

    def test_trace(self):
        s1 = CountingStage("s1", provides=["x"])
        s2 = CountingStage("s2", requires=["x"])
        runner = PipelineRunner([s1, s2])
        runner.run(StageInput())
        trace = runner.trace()
        assert len(trace) == 2
        assert trace[0][0] == "s1"
        assert trace[1][0] == "s2"
        assert all(isinstance(t[1], float) for t in trace)
        assert all(t[1] >= 0 for t in trace)

    def test_trace_before_run_raises(self):
        runner = PipelineRunner([CountingStage("s1")])
        with pytest.raises(RuntimeError, match="trace"):
            runner.trace()

    def test_timings_accumulate(self):
        s1 = CountingStage("s1", provides=["x"])
        s2 = CountingStage("s2", requires=["x"])
        runner = PipelineRunner([s1, s2])
        result = runner.run(StageInput())
        assert "s1" in result.meta.timings
        assert "s2" in result.meta.timings

    def test_meta_timestamp_set(self):
        s1 = CountingStage("s1", provides=["x"])
        runner = PipelineRunner([s1])
        inp = StageInput()
        result = runner.run(inp)
        assert result.meta.timestamp > 0

    def test_contract_satisfied_when_contract_exists(self):
        s = CountingStage("s", contract=Contract())
        runner = PipelineRunner([s])
        result = runner.run(StageInput())
        assert result.contract_satisfied is True

    def test_contract_satisfied_none_when_no_contract(self):
        s = CountingStage("s")
        runner = PipelineRunner([s])
        result = runner.run(StageInput())
        assert result.contract_satisfied is None


# ---- Data-flow validation ---------------------------------------------------


class TestDataFlowValidation:
    def test_missing_requires_raises(self):
        s = CountingStage("bad", requires=["nonexistent_key"])
        with pytest.raises(DataFlowError) as exc:
            PipelineRunner([s])
        assert "bad" in exc.value.stage_name
        assert "nonexistent_key" in exc.value.missing_keys

    def test_valid_chain(self):
        s1 = CountingStage("s1", provides=["a", "b"])
        s2 = CountingStage("s2", requires=["a"], provides=["c"])
        s3 = CountingStage("s3", requires=["b", "c"])
        PipelineRunner([s1, s2, s3])  # no error

    def test_partial_missing(self):
        s1 = CountingStage("s1", provides=["a"])
        s2 = CountingStage("s2", requires=["a", "missing"])
        with pytest.raises(DataFlowError) as exc:
            PipelineRunner([s1, s2])
        assert "missing" in exc.value.missing_keys
        assert "a" in exc.value.available_keys


# ---- Contract validation ----------------------------------------------------


class TestContractValidation:
    def test_input_contract_pass(self):
        @dataclass
        class GoodInput:
            x: int
            y: str

        s = CountingStage(
            "s",
            contract=Contract(
                input_schema={"x": int, "y": str},
                output_schema={},
            ),
        )
        runner = PipelineRunner([s])
        runner.run(StageInput(data=GoodInput(x=1, y="hello")))

    def test_input_contract_type_mismatch(self):
        @dataclass
        class BadInput:
            x: str  # wrong type!

        s = CountingStage(
            "s",
            contract=Contract(input_schema={"x": int}),
        )
        runner = PipelineRunner([s])
        with pytest.raises(ContractViolation) as exc:
            runner.run(StageInput(data=BadInput(x="oops")))
        assert exc.value.stage_name == "s"
        assert exc.value.schema == "input"
        assert exc.value.field_name == "x"
        assert exc.value.expected_type is int
        assert exc.value.actual_type is str

    def test_output_contract_type_mismatch(self):
        @dataclass
        class BadOutput:
            result: int

        class BadOutputStage:
            name = "bad_out"
            requires: list[str] = []
            provides: list[str] = []
            contract = Contract(output_schema={"result": str})

            def run(self, inp):
                return StageOutput(
                    data=BadOutput(result=42), meta=inp.meta
                )

        runner = PipelineRunner([BadOutputStage()])
        with pytest.raises(ContractViolation) as exc:
            runner.run(StageInput(data=object()))
        assert exc.value.schema == "output"
        assert exc.value.expected_type is str
        assert exc.value.actual_type is int

    def test_no_contract_skips_validation(self):
        s = CountingStage("s")
        runner = PipelineRunner([s])
        runner.run(StageInput(data="anything"))  # no error


# ---- resolve_and_run --------------------------------------------------------


class GoodStage:
    name = "good"
    requires: list[str] = []
    provides: list[str] = []
    contract = None

    def run(self, inp):
        return StageOutput(data="success", meta=inp.meta)


class BadStage:
    name = "bad"
    requires: list[str] = []
    provides: list[str] = []
    contract = None

    def run(self, _inp):
        raise RuntimeError("bad strategy")


@pytest.fixture(autouse=True)
def _setup_strategies():
    """Register test strategies for resolve_and_run tests."""
    import temper_placer.strategy_registry as sr

    sr._registry.clear()
    sr._composites.clear()
    register("test_phase", "good", lambda: GoodStage())
    register("test_phase", "bad", lambda: BadStage())
    yield
    sr._registry.clear()
    sr._composites.clear()


class TestResolveAndRun:
    def test_single_strategy_success(self):
        result = resolve_and_run("test_phase", ["good"], StageInput())
        assert result.data == "success"

    def test_fallback_on_failure(self):
        result = resolve_and_run(
            "test_phase", ["bad"],
            StageInput(),
            fallback="good",
        )
        assert result.data == "success"

    def test_exhausted_raises(self):
        with pytest.raises(StrategyExhaustedError) as exc:
            resolve_and_run("test_phase", ["bad"], StageInput())
        assert exc.value.phase == "test_phase"
        assert len(exc.value.failure_chain) == 1

    def test_exhausted_with_fallback(self):
        with pytest.raises(StrategyExhaustedError) as exc:
            resolve_and_run(
                "test_phase", ["bad"],
                StageInput(),
                fallback="bad",
            )
        assert len(exc.value.failure_chain) == 2

    def test_empty_strategies(self):
        with pytest.raises(StrategyExhaustedError):
            resolve_and_run("test_phase", [], StageInput())

    def test_composite_strategy(self):
        from temper_placer.strategy_registry import register_composite

        register("test_phase", "s1", lambda: GoodStage())
        register("test_phase", "s2", lambda: GoodStage())
        register_composite("test_composite", [
            ("test_phase", "s1"),
            ("test_phase", "s2"),
        ])
        result = resolve_and_run("test_phase", ["test_composite"], StageInput())
        assert result.data == "success"
