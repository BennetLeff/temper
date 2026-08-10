"""Tests for TerminalDashboardObserver.

Covers all ProgressObserver protocol methods plus update() and
create_terminal_dashboard().
"""

from temper_placer.pipeline.terminal_dashboard import (
    TerminalDashboardObserver,
    create_terminal_dashboard,
)


class TestOnStageStart:
    """Tests for TerminalDashboardObserver.on_stage_start."""

    def test_sets_active_status(self):
        obs = TerminalDashboardObserver(stage_order=["load", "route"])
        obs.on_stage_start("load", 0, {})
        assert obs._stage_status["load"] == obs.STATUS_ACTIVE
        assert obs._current_stage == "load"

    def test_records_iteration(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        obs.on_stage_start("load", 3, {"ctx": 1})
        assert obs._stage_iterations["load"] == 3

    def test_sets_pipeline_start_once(self):
        obs = TerminalDashboardObserver(stage_order=["load", "route"])
        assert obs._pipeline_start == 0.0
        obs.on_stage_start("load", 0, {})
        first_start = obs._pipeline_start
        assert first_start > 0.0
        obs.on_stage_start("route", 0, {})
        # Pipeline start should not change on second call
        assert obs._pipeline_start == first_start

    def test_header_text_updated(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        obs.on_stage_start("load", 0, {})
        assert "load" in obs._header_text


class TestOnStageComplete:
    """Tests for TerminalDashboardObserver.on_stage_complete."""

    def test_sets_done_status(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        obs.on_stage_complete("load", 1.5, {"routed": 42})
        assert obs._stage_status["load"] == obs.STATUS_DONE
        assert obs._stage_durations["load"] == 1.5


class TestOnStageSkip:
    """Tests for TerminalDashboardObserver.on_stage_skip."""

    def test_sets_skip_status(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        obs.on_stage_skip("load", "condition false")
        assert obs._stage_status["load"] == obs.STATUS_SKIP
        assert obs._stage_durations["load"] == 0.0


class TestOnStageError:
    """Tests for TerminalDashboardObserver.on_stage_error."""

    def test_sets_error_status(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        obs.on_stage_error("load", ValueError("bad"))
        assert obs._stage_status["load"] == obs.STATUS_ERROR
        assert "FAILED" in obs._header_text


class TestOnFeedbackTriggered:
    """Tests for TerminalDashboardObserver.on_feedback_triggered."""

    def test_increments_feedback_count(self):
        obs = TerminalDashboardObserver(stage_order=["place", "route"])
        assert obs._feedback_count == 0
        obs.on_feedback_triggered("sidecar", "route", "place", 1)
        assert obs._feedback_count == 1
        obs.on_feedback_triggered("sidecar", "route", "place", 2)
        assert obs._feedback_count == 2


class TestOnPipelineComplete:
    """Tests for TerminalDashboardObserver.on_pipeline_complete."""

    def test_sets_success(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        obs.on_pipeline_complete(True, 12.5, {"load": 12.5})
        assert obs._pipeline_success is True
        assert obs._total_duration == 12.5
        assert "PASSED" in obs._header_text

    def test_sets_failure(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        obs.on_pipeline_complete(False, 5.0, {"load": 5.0})
        assert obs._pipeline_success is False
        assert "FAILED" in obs._header_text

    def test_stage_durations_updated(self):
        obs = TerminalDashboardObserver(stage_order=["a", "b"])
        obs.on_pipeline_complete(True, 10.0, {"a": 3.0, "b": 7.0})
        assert obs._stage_durations["a"] == 3.0
        assert obs._stage_durations["b"] == 7.0


class TestOnEpoch:
    """Tests for TerminalDashboardObserver.on_epoch."""

    def test_records_loss(self):
        obs = TerminalDashboardObserver(stage_order=["geometric"])
        obs.on_epoch("geometric", 0, 0.5)
        assert obs._losses == [0.5]
        assert obs._loss_epochs == [0]

    def test_truncates_at_200(self):
        obs = TerminalDashboardObserver(stage_order=["geometric"])
        for i in range(250):
            obs.on_epoch("geometric", i, float(i))
        assert len(obs._losses) == 200
        assert obs._losses[0] == 50.0  # oldest kept
        assert obs._losses[-1] == 249.0


class TestUpdate:
    """Tests for TerminalDashboardObserver.update (no-op without live context)."""

    def test_noop_when_no_live(self):
        obs = TerminalDashboardObserver(stage_order=["load"])
        # Should not raise -- _live is None, so update() is a no-op
        obs.update()


class TestCreateTerminalDashboard:
    """Tests for create_terminal_dashboard factory."""

    def test_returns_observer(self):
        obs = create_terminal_dashboard(["a", "b", "c"])
        assert isinstance(obs, TerminalDashboardObserver)
        assert obs.stage_order == ["a", "b", "c"]

    def test_passes_kwargs(self):
        obs = create_terminal_dashboard(["x"], refresh_per_second=10.0)
        assert obs.refresh_per_second == 10.0
