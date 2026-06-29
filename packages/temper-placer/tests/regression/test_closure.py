"""Tests for closure test infrastructure."""

import json
from pathlib import Path
from unittest.mock import patch

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


class TestClosureResultValidation:
    """Unit tests for ClosureResult.validate() truth assertions."""

    def test_validate_all_passing(self):
        result = ClosureResult(
            passed=True,
            board_id="test",
            benders_iterations=5,
            router_completion_pct=95.0,
            stages_exercised=4,
        )
        failures = result.validate()
        assert failures == []

    def test_validate_zero_benders(self):
        result = ClosureResult(
            passed=True,
            board_id="test",
            benders_iterations=0,
            router_completion_pct=95.0,
            stages_exercised=4,
        )
        failures = result.validate()
        assert len(failures) >= 1
        assert any("benders_iterations" in f for f in failures)

    def test_validate_zero_router(self):
        result = ClosureResult(
            passed=True,
            board_id="test",
            benders_iterations=5,
            router_completion_pct=0.0,
            stages_exercised=4,
        )
        failures = result.validate()
        assert len(failures) >= 1
        assert any("router_completion_pct" in f for f in failures)

    def test_validate_stages_below_two(self):
        result = ClosureResult(
            passed=True,
            board_id="test",
            benders_iterations=5,
            router_completion_pct=95.0,
            stages_exercised=1,
        )
        failures = result.validate()
        assert len(failures) >= 1
        assert any("stages_exercised" in f for f in failures)

    def test_validate_zero_results(self):
        result = ClosureResult(
            passed=True,
            board_id="test",
            benders_iterations=0,
            router_completion_pct=0.0,
            stages_exercised=4,
        )
        failures = result.validate()
        assert any("zero-results" in f for f in failures)

    def test_validate_backward_compat(self):
        """Default-constructed ClosureResult (all zeros) should produce failures."""
        result = ClosureResult(passed=True, board_id="test")
        failures = result.validate()
        assert len(failures) > 0
        assert result.stages_exercised == 0


class TestClosureTestRequireAllStages:
    """Unit tests for require_all_stages behavior."""

    def test_require_all_stages_placement_error(self, tmp_path: Path):
        """Placement ImportError with require_all_stages=True becomes an error."""
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.regression.closure_test.parse_kicad_pcb_v6",
            return_value={},
        ), patch(
            "temper_placer.regression.closure_test.resolve_and_run",
            side_effect=ImportError("No module named temper_placer.protocol"),
        ):
            test = ClosureTest(
                pcb_path=pcb_path,
                require_all_stages=True,
            )
            result = test.run()
            assert result.passed is False
            assert any("Placement not available" in e for e in result.errors)

    def test_default_graceful_degradation(self, tmp_path: Path):
        """Placement ImportError without require_all_stages is a warning, not error."""
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.regression.closure_test.parse_kicad_pcb_v6",
            return_value={},
        ), patch(
            "temper_placer.regression.closure_test.resolve_and_run",
            side_effect=ImportError("No module named temper_placer.protocol"),
        ):
            test = ClosureTest(
                pcb_path=pcb_path,
                require_all_stages=False,
            )
            result = test.run()
            assert any("Placement not available" in w for w in result.warnings)
            # validate() will catch the zero-results and make passed=False
            # because benders_iterations=0, router_completion_pct=0
