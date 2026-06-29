"""Tests for StageDRCFailure and validator registry."""

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.stage_validators import (
    VALIDATOR_REGISTRY,
    StageDRCFailure,
    clear_validators,
    get_registered_stages,
    register_validator,
    run_validators,
)


class TestStageDRCFailure:
    def test_creation(self):
        f = StageDRCFailure(field="test", value=42, reason="bad", stage="Test")
        assert f.field == "test"
        assert f.value == 42
        assert f.reason == "bad"
        assert f.stage == "Test"

    def test_str_format(self):
        f = StageDRCFailure(field="f1", value="v1", reason="r1", stage="S1")
        s = str(f)
        assert "[S1]" in s
        assert "f1" in s
        assert "r1" in s


class TestValidatorRegistry:
    def setup_method(self):
        clear_validators()

    def teardown_method(self):
        clear_validators()

    def test_register_and_discover(self):
        @register_validator("TestStage")
        def dummy_validator(_state):
            return [StageDRCFailure(field="x", value=1, reason="test", stage="TestStage")]

        assert "TestStage" in VALIDATOR_REGISTRY
        assert len(VALIDATOR_REGISTRY["TestStage"]) == 1
        assert "TestStage" in get_registered_stages()

    def test_run_validators(self):
        @register_validator("S1")
        def v1(_state):
            return [StageDRCFailure(field="a", value=1, reason="r1", stage="S1")]

        @register_validator("S1")
        def v2(_state):
            return [StageDRCFailure(field="b", value=2, reason="r2", stage="S1")]

        state = BoardState()
        failures = run_validators("S1", state)
        assert len(failures) == 2
        assert failures[0].field == "a"
        assert failures[1].field == "b"

    def test_run_validators_nonexistent_stage(self):
        state = BoardState()
        failures = run_validators("NonexistentStage", state)
        assert failures == []

    def test_clear_validators(self):
        @register_validator("C1")
        def v1(_state):
            return []

        assert "C1" in VALIDATOR_REGISTRY
        clear_validators()
        assert "C1" not in VALIDATOR_REGISTRY

    def test_multiple_registrations_same_name(self):
        @register_validator("Multi")
        def v1(_state):
            return []

        @register_validator("Multi")
        def v2(_state):
            return []

        assert len(VALIDATOR_REGISTRY["Multi"]) == 2
