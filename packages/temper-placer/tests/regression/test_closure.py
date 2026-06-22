"""Tests for closure test infrastructure."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.regression.closure_test import ClosureResult, ClosureTest


class TestClosureResult:
    def test_pass(self):
        result = ClosureResult(passed=True, board_id="test", benders_iterations=5, benders_cuts=10)
        assert result.passed
        assert result.benders_iterations == 5

    def test_fail_with_errors(self):
        result = ClosureResult(
            passed=False,
            board_id="test",
            errors=["Benders crashed"],
        )
        assert not result.passed
        assert len(result.errors) == 1

    def test_summary(self):
        result = ClosureResult(
            passed=True,
            board_id="test",
            benders_iterations=5,
            benders_cuts=10,
            router_completion_pct=95.0,
            drc_errors=3,
            drc_warnings=1,
            wall_clock_seconds=12.5,
        )
        summary = result.summary()
        assert "test" in summary
        assert "PASS" in summary
        assert "5" in summary
        assert "95.0%" in summary


class TestClosureTest:
    def test_load_seed(self, tmp_path: Path):
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps({"benders_seed": 42, "router_seed": 137}))
        seed = ClosureTest.load_seed(seed_path)
        assert seed["benders_seed"] == 42
        assert seed["router_seed"] == 137

    def test_load_seed_defaults(self, tmp_path: Path):
        seed_path = tmp_path / "missing.json"
        seed = ClosureTest.load_seed(seed_path)
        assert seed["benders_seed"] == 42
        assert seed["router_seed"] == 42

    def test_parse_failure(self, tmp_path: Path):
        pcb_path = tmp_path / "nonexistent.kicad_pcb"
        test = ClosureTest(pcb_path=pcb_path)
        result = test.run()
        assert not result.passed
        assert any("Parse failed" in e for e in result.errors)

    def test_importable_without_benders(self):
        """T4.6: ClosureTest can be imported without triggering Benders or Router."""
        from temper_placer.regression.closure_test import ClosureTest as CT

        ct = CT(pcb_path=Path("test.kicad_pcb"))
        assert ct.benders_seed == 42
        assert ct.router_seed == 42
