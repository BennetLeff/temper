"""Tests for validation.drc_runner module (CheckRunner)."""

from temper_placer.validation.drc_result import ClearanceCheck
from temper_placer.validation.drc_runner import CheckRunner


class TestCheckRunner:
    """Tests for CheckRunner."""

    def test_empty_runner(self):
        runner = CheckRunner()
        assert runner.check_names == []
        assert runner.categories == set()

    def test_add_check(self):
        runner = CheckRunner()
        check = ClearanceCheck()
        runner.add_check(check)
        assert runner.check_names == ["drc_clearance"]
        assert "drc" in runner.categories

    def test_add_checks(self):
        runner = CheckRunner()
        checks = [ClearanceCheck()]
        runner.add_checks(checks)
        assert "drc_clearance" in runner.check_names

    def test_clear(self):
        runner = CheckRunner()
        runner.add_check(ClearanceCheck())
        assert len(runner.check_names) == 1
        runner.clear()
        assert runner.check_names == []
        assert runner.categories == set()

    def test_get_checks_by_category(self):
        runner = CheckRunner()
        c = ClearanceCheck()
        runner.add_check(c)
        drc_checks = runner.get_checks_by_category("drc")
        assert len(drc_checks) == 1
        assert drc_checks[0] is c

    def test_get_checks_by_category_empty(self):
        runner = CheckRunner()
        checks = runner.get_checks_by_category("nonexistent")
        assert checks == []

    def test_summary(self):
        runner = CheckRunner()
        runner.add_check(ClearanceCheck())
        s = runner.summary()
        assert "drc_clearance" in s
