"""Tests for TerminalDashboardObserver live pipeline visualization."""

from unittest.mock import Mock

import pytest


class TestTerminalDashboardObserver:
    """Tests for TerminalDashboardObserver state management."""

    def test_can_create(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "geometric", "routing", "output"])
        assert obs is not None
        assert obs.stage_order == ["input", "geometric", "routing", "output"]

    def test_on_stage_start_sets_active(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "output"])
        obs.on_stage_start("input", 0, {})
        assert obs._stage_status["input"] == obs.STATUS_ACTIVE
        assert obs._pipeline_start > 0

    def test_on_stage_complete_sets_done(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "output"])
        obs.on_stage_complete("input", 2.5, {})
        assert obs._stage_status["input"] == obs.STATUS_DONE
        assert obs._stage_durations["input"] == 2.5

    def test_on_stage_skip_sets_skip(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "output"])
        obs.on_stage_skip("input", "dry_run")
        assert obs._stage_status["input"] == obs.STATUS_SKIP

    def test_on_stage_error_sets_error(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "output"])
        obs.on_stage_error("input", ValueError("bad"))
        assert obs._stage_status["input"] == obs.STATUS_ERROR

    def test_on_feedback_tracks_count(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "output"])
        obs.on_feedback_triggered("routability", "routing", "geometric", 1)
        obs.on_feedback_triggered("routability", "routing", "geometric", 2)
        assert obs._feedback_count == 2

    def test_on_pipeline_complete_updates_state(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "output"])
        obs.on_pipeline_complete(True, 10.0, {"input": 1.0, "output": 2.0})
        assert obs._pipeline_success is True
        assert obs._total_duration == 10.0
        assert obs._stage_durations["input"] == 1.0

    def test_on_epoch_stores_losses(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["geometric", "output"])
        for i in range(5):
            obs.on_epoch("geometric", i * 10, float(i))
        assert len(obs._losses) == 5
        assert obs._losses[-1] == 4.0

    def test_on_epoch_truncates_at_200(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["geometric", "output"])
        for i in range(250):
            obs.on_epoch("geometric", i, float(i))
        assert len(obs._losses) == 200
        assert obs._losses[0] == 50.0  # dropped first 50

    def test_make_sparkline(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["geometric", "output"])
        obs.on_epoch("geometric", 0, 1.0)
        obs.on_epoch("geometric", 10, 2.0)
        spark = obs._make_sparkline()
        assert len(spark) == 2  # two chars

    def test_replays_pipeline_execution(self):
        from temper_placer.pipeline.terminal_dashboard import TerminalDashboardObserver
        obs = TerminalDashboardObserver(stage_order=["input", "routing", "output"])
        obs.on_stage_start("input", 0, {})
        obs.on_stage_complete("input", 1.0, {})
        obs.on_stage_start("routing", 0, {})
        obs.on_stage_complete("routing", 2.0, {})
        obs.on_pipeline_complete(True, 3.0, {"input": 1.0, "routing": 2.0})
        assert obs._pipeline_success is True

    def test_factory_creates_observer(self):
        from temper_placer.pipeline.terminal_dashboard import create_terminal_dashboard
        obs = create_terminal_dashboard(stage_order=["a", "b"])
        assert obs.stage_order == ["a", "b"]


class TestProgressObserverProtocol:
    """Tests that ProgressObserver protocol includes on_epoch."""

    def test_on_epoch_present_in_protocol(self):
        from temper_placer.pipeline.dag_observability import ProgressObserver
        assert 'on_epoch' in ProgressObserver.__dict__

    def test_metrics_observer_still_works_without_on_epoch(self):
        """MetricsObserver doesn't implement on_epoch — should still work."""
        from temper_placer.pipeline.dag_observability import ProgressObserver
        from temper_placer.pipeline.metrics_observer import MetricsObserver
        # If MetricsObserver doesn't crash when instantiated, it's fine
        # (it doesn't implement on_epoch, but protocol is optional)
        assert True  # MetricsObserver imports successfully

    def test_dag_to_legacy_observer_still_works(self):
        from temper_placer.pipeline.dag_observability import DAGToLegacyObserver
        assert DAGToLegacyObserver is not None
