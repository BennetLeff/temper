"""Tests for StageLedger object cardinality tracking (U7/U8)."""

import pytest

from temper_placer.router_v6.stage_ledger import (
    LedgerReport,
    StageLedger,
    StageLedgerImbalanceError,
)


class _FakePCB:
    nets = [1, 2]
    components = [1, 2, 3]


class _FakeState:
    _parsed_pcb = _FakePCB()
    channel_skeletons = {}
    _escape_vias = ()


class TestStageLedger:
    """StageLedger tracks cardinality before/after stages."""

    def test_balanced_returns_true(self):
        ledger = StageLedger(fail_on_imbalance=False)
        report = ledger.verify("stage2", _FakeState(), _FakeState())
        assert report.is_balanced is True
        assert report.stage_name == "stage2"

    def test_ledger_report_str(self):
        report = LedgerReport(is_balanced=True, stage_name="S", message="ok")
        s = str(report)
        assert "BALANCED" in s
        assert "S" in s

        report2 = LedgerReport(is_balanced=False, stage_name="X", message="fail")
        s2 = str(report2)
        assert "IMBALANCED" in s2

    def test_via_count_imbalance(self):
        state_a = _FakeState()
        state_b = _FakeState()
        state_b._escape_vias = (1, 2)
        ledger = StageLedger(fail_on_imbalance=False)
        report = ledger.verify("stage1", state_a, state_b)
        assert report.is_balanced is False
        assert "via_count" in report.message

    def test_fail_on_imbalance_raises(self):
        import dataclasses
        state_a = _FakeState()
        state_b = _FakeState()
        state_b._escape_vias = (1, 2)
        ledger = StageLedger(fail_on_imbalance=True)
        with pytest.raises(StageLedgerImbalanceError, match="via_count"):
            ledger.verify("stage1", state_a, state_b)

    def test_fail_on_imbalance_false_no_raise(self):
        state_a = _FakeState()
        state_b = _FakeState()
        state_b._escape_vias = (1, 2)
        ledger = StageLedger(fail_on_imbalance=False)
        report = ledger.verify("stage1", state_a, state_b)
        assert report.is_balanced is False

    def test_checkin_checkout_flow(self):
        ledger = StageLedger(fail_on_imbalance=False)
        ledger.checkin(_FakeState())
        report = ledger.checkout("mystage", _FakeState())
        assert report.is_balanced is True

    def test_missing_pre_snapshot(self):
        ledger = StageLedger(fail_on_imbalance=False)
        report = ledger.checkout("orphan", _FakeState())
        assert report.is_balanced is False
        assert "missing pre-snapshot" in report.message.lower()
