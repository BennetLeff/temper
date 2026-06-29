"""Tests for strategy_registry.py — register, get, list, register_composite, get_composite."""

from __future__ import annotations

import pytest

from temper_placer.protocol import PipelineStage, StageOutput
from temper_placer.strategy_registry import (
    get,
    get_composite,
    list_stages,
    register,
    register_composite,
)


class FakeStage:
    """Minimal PipelineStage for registry tests."""

    name = "fake"
    requires: list[str] = []
    provides: list[str] = []
    contract = None

    def __init__(self, label: str = ""):
        self.label = label

    def run(self, inp):
        return StageOutput(data=f"fake:{self.label}", meta=inp.meta)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test gets a clean registry by re-importing the module."""
    import temper_placer.strategy_registry as sr

    # Re-initialize the module-level dicts
    sr._registry.clear()
    sr._composites.clear()
    yield


class TestRegisterGet:
    def test_round_trip(self):
        register("test", "fake1", lambda: FakeStage("a"))
        stage = get("test", "fake1")
        assert isinstance(stage, PipelineStage)
        assert isinstance(stage, FakeStage)
        assert stage.label == "a"

    def test_different_phase_names(self):
        register("phase_a", "s1", lambda: FakeStage("a1"))
        register("phase_b", "s1", lambda: FakeStage("b1"))
        assert get("phase_a", "s1").label == "a1"
        assert get("phase_b", "s1").label == "b1"

    def test_idempotent_register(self):
        register("x", "y", lambda: FakeStage("first"))
        register("x", "y", lambda: FakeStage("second"))  # no-op
        assert get("x", "y").label == "first"

    def test_get_missing_raises_keyerror(self):
        with pytest.raises(KeyError, match="nonexistent"):
            get("missing", "nonexistent")


class TestListStages:
    def test_list_all(self):
        register("a", "x", lambda: FakeStage())
        register("b", "y", lambda: FakeStage())
        result = list_stages()
        assert "a/x" in result
        assert "b/y" in result
        assert len(result) == 2

    def test_list_filtered_by_phase(self):
        register("phase1", "s1", lambda: FakeStage())
        register("phase1", "s2", lambda: FakeStage())
        register("phase2", "s3", lambda: FakeStage())
        result = list_stages("phase1")
        assert set(result.keys()) == {"phase1/s1", "phase1/s2"}

    def test_list_empty_phase(self):
        register("p1", "s1", lambda: FakeStage())
        result = list_stages("nonexistent")
        assert result == {}


class TestComposite:
    def test_register_and_get(self):
        register("p", "a", lambda: FakeStage("a"))
        register("p", "b", lambda: FakeStage("b"))
        register_composite("composite1", [("p", "a"), ("p", "b")])
        stages = get_composite("composite1")
        assert len(stages) == 2
        assert stages[0].label == "a"
        assert stages[1].label == "b"

    def test_idempotent_register(self):
        register("p", "a", lambda: FakeStage("a"))
        register("p", "b", lambda: FakeStage("b"))
        register_composite("c", [("p", "a")])
        register_composite("c", [("p", "a"), ("p", "b")])  # no-op
        stages = get_composite("c")
        assert len(stages) == 1

    def test_get_missing_composite(self):
        with pytest.raises(KeyError, match="no_such_composite"):
            get_composite("no_such_composite")
