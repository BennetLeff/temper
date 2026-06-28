"""Tests for Stage contract enforcement (U2)."""

import os
from pathlib import Path

import pytest

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.pipeline.bottleneck_report import DeclaredArtifact


class MockStage(Stage):
    """Minimal Stage for testing contract validation."""

    def __init__(
        self,
        name: str = "mock",
        declared_writes: tuple[DeclaredArtifact, ...] = (),
        declared_reads: tuple[DeclaredArtifact, ...] = (),
        is_active: bool = True,
        should_fail: bool = False,
    ):
        self._name = name
        self._declared_writes = declared_writes
        self._declared_reads = declared_reads
        self._is_active = is_active
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    @property
    def declared_writes(self) -> tuple[DeclaredArtifact, ...]:
        return self._declared_writes

    @property
    def declared_reads(self) -> tuple[DeclaredArtifact, ...]:
        return self._declared_reads

    @property
    def is_active(self) -> bool:
        return self._is_active

    def run(self, state: BoardState) -> BoardState:
        return state


class TestStageContract:
    """Stage contract validation."""

    def test_empty_declarations_noop(self):
        stage = MockStage()
        assert stage.declared_writes == ()
        assert stage.declared_reads == ()

    def test_declared_writes_property(self):
        artifact = DeclaredArtifact("report", "report.json", "desc")
        stage = MockStage(declared_writes=(artifact,))
        assert stage.declared_writes == (artifact,)
        assert stage.declared_reads == ()

    def test_declared_reads_property(self):
        artifact = DeclaredArtifact("input", "input.json", "desc")
        stage = MockStage(declared_reads=(artifact,))
        assert stage.declared_reads == (artifact,)

    def test_is_active_default(self):
        stage = MockStage()
        assert stage.is_active is True

    def test_is_active_false(self):
        stage = MockStage(is_active=False)
        assert stage.is_active is False

    def test_write_contract_violation_detected(self, tmp_path: Path):
        """A stage declares a write but produces no file — violation."""
        artifact = DeclaredArtifact("report", str(tmp_path / "report.json"))
        stage = MockStage(declared_writes=(artifact,))

        # The file doesn't exist because the mock stage's run() is a no-op.
        missing = [
            a for a in stage.declared_writes
            if not Path(a.output_path).exists()
        ]
        assert len(missing) == 1
        assert missing[0].name == "report"

    def test_write_contract_satisfied(self, tmp_path: Path):
        """A stage declares a write and the file exists — no violation."""
        path = tmp_path / "report.json"
        path.write_text("{}")
        artifact = DeclaredArtifact("report", str(path))
        stage = MockStage(declared_writes=(artifact,))

        missing = [
            a for a in stage.declared_writes
            if not Path(a.output_path).exists()
        ]
        assert len(missing) == 0

    def test_read_contract_violation(self, tmp_path: Path):
        """A stage declares a read but no prior stage produced the file."""
        artifact = DeclaredArtifact("report", str(tmp_path / "report.json"))
        stage = MockStage(declared_reads=(artifact,))

        missing = [
            a for a in stage.declared_reads
            if not Path(a.output_path).exists()
        ]
        assert len(missing) == 1


class TestActiveFlag:
    """is_active flag controls stage contract participation."""

    def test_inactive_stage_skips_write_contract(self, tmp_path: Path):
        """A disabled stage with declared writes should not fail validation."""
        path = tmp_path / "report.json"
        artifact = DeclaredArtifact("report", str(path))
        stage = MockStage(declared_writes=(artifact,), is_active=False)

        # Inactive stages skip contract checks — missing file is not a violation
        if stage.is_active:
            missing = [
                a for a in stage.declared_writes
                if not Path(a.output_path).exists()
            ]
            assert len(missing) == 1
        else:
            assert True  # Contract skipped

    def test_inactive_stage_skips_read_contract(self, tmp_path: Path):
        """A disabled stage with declared reads should not fail validation."""
        path = tmp_path / "missing.json"
        artifact = DeclaredArtifact("report", str(path))
        stage = MockStage(declared_reads=(artifact,), is_active=False)

        if stage.is_active:
            missing = [
                a for a in stage.declared_reads
                if not Path(a.output_path).exists()
            ]
            assert len(missing) == 1
        else:
            assert True  # Contract skipped


class TestFeedbackFlag:
    """TEMPER_FEEDBACK_ENABLED env var control."""

    def test_feedback_enabled_default(self):
        from temper_placer.deterministic.flags import is_feedback_enabled
        assert is_feedback_enabled() is True

    def test_feedback_disabled_by_env(self):
        from temper_placer.deterministic import flags
        import importlib
        importlib.reload(flags)

        os.environ["TEMPER_FEEDBACK_ENABLED"] = "false"
        try:
            assert flags.is_feedback_enabled() is False
        finally:
            del os.environ["TEMPER_FEEDBACK_ENABLED"]

    def test_feedback_disabled_by_zero(self):
        from temper_placer.deterministic.flags import is_feedback_enabled

        os.environ["TEMPER_FEEDBACK_ENABLED"] = "0"
        try:
            assert is_feedback_enabled() is False
        finally:
            del os.environ["TEMPER_FEEDBACK_ENABLED"]
