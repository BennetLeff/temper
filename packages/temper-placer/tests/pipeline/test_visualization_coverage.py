"""Tests for pipeline visualization module.

Covers ProgressCallback, TerminalProgress, RichDashboard methods,
and create_progress_display factory.
"""

from unittest import mock

from temper_placer.pipeline.visualization import (
    ProgressCallback,
    RichDashboard,
    TerminalProgress,
    create_progress_display,
)


# =============================================================================
# ProgressCallback
# =============================================================================


class TestProgressCallback:
    """Tests for ProgressCallback base class (no-op methods)."""

    def test_on_phase_start_noop(self):
        cb = ProgressCallback()
        cb.on_phase_start("load", {"key": "val"})

    def test_on_phase_complete_noop(self):
        cb = ProgressCallback()
        cb.on_phase_complete("load", {"key": "val"})

    def test_on_iteration_noop(self):
        cb = ProgressCallback()
        cb.on_iteration(5, {"key": "val"})

    def test_on_epoch_noop(self):
        cb = ProgressCallback()
        cb.on_epoch(100, 0.42)


# =============================================================================
# TerminalProgress
# =============================================================================


class TestTerminalProgressOnPhaseStart:
    """Tests for TerminalProgress.on_phase_start."""

    def test_increments_phase(self):
        tp = TerminalProgress()
        assert tp.current_phase == 0
        tp.on_phase_start("load", None)
        assert tp.current_phase == 1

    def test_prints_bar(self, capsys):
        tp = TerminalProgress()
        tp.on_phase_start("load", None)
        captured = capsys.readouterr()
        assert "Phase 1/8: load" in captured.out

    def test_multiple_calls_increment(self):
        tp = TerminalProgress()
        tp.on_phase_start("a", None)
        tp.on_phase_start("b", None)
        assert tp.current_phase == 2


class TestTerminalProgressOnPhaseComplete:
    """Tests for TerminalProgress.on_phase_complete."""

    def test_prints_done(self, capsys):
        tp = TerminalProgress()
        tp.on_phase_complete("load", None)
        captured = capsys.readouterr()
        assert "[DONE]" in captured.out


class TestTerminalProgressOnIteration:
    """Tests for TerminalProgress.on_iteration."""

    def test_records_iteration(self):
        tp = TerminalProgress()
        tp.on_iteration(3, None)
        assert tp.current_iteration == 3

    def test_prints_iteration(self, capsys):
        tp = TerminalProgress()
        tp.on_iteration(5, None)
        captured = capsys.readouterr()
        assert "Iteration 5" in captured.out


class TestTerminalProgressOnEpoch:
    """Tests for TerminalProgress.on_epoch."""

    def test_prints_at_epoch_interval(self, capsys):
        tp = TerminalProgress(epoch_interval=10)
        tp.on_epoch(0, 0.5)
        captured = capsys.readouterr()
        assert "Epoch 0: loss=0.5000" in captured.out

    def test_skips_intermediate_epochs(self, capsys):
        tp = TerminalProgress(epoch_interval=10)
        tp.on_epoch(1, 0.3)  # 1 % 10 != 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_prints_at_interval_boundaries(self, capsys):
        tp = TerminalProgress(epoch_interval=5)
        tp.on_epoch(10, 0.1)
        captured = capsys.readouterr()
        assert "Epoch 10: loss=0.1000" in captured.out


class TestTerminalProgressMakeBar:
    """Tests for the private _make_bar helper (exercised via on_phase_start)."""

    def test_empty_bar(self):
        tp = TerminalProgress()
        bar = tp._make_bar(0, 8)
        assert "[" in bar and "]" in bar

    def test_full_bar(self):
        tp = TerminalProgress()
        bar = tp._make_bar(8, 8)
        assert "#" * 20 in bar

    def test_zero_total(self):
        tp = TerminalProgress()
        bar = tp._make_bar(0, 0)
        assert "." * 20 in bar


# =============================================================================
# RichDashboard
# =============================================================================


class TestRichDashboardCreateLayout:
    """Tests for RichDashboard.create_layout."""

    def test_returns_layout(self):
        rd = RichDashboard()
        layout = rd.create_layout()
        assert layout is not None
        assert rd._layout is layout

    def test_layout_has_header_body_footer(self):
        rd = RichDashboard()
        layout = rd.create_layout()
        # Rich Layout supports __getitem__
        assert layout["header"] is not None
        assert layout["body"] is not None
        assert layout["footer"] is not None


class TestRichDashboardUpdateHeader:
    """Tests for RichDashboard.update_header."""

    def test_returns_panel(self):
        rd = RichDashboard()
        panel = rd.update_header("place", 5)
        assert panel is not None

    def test_panel_contains_phase_and_iteration(self):
        rd = RichDashboard()
        panel = rd.update_header("route", 10)
        rendered = panel.renderable
        assert "route" in str(rendered)
        assert "10" in str(rendered)


class TestRichDashboardUpdateMetrics:
    """Tests for RichDashboard.update_metrics."""

    def test_returns_table(self):
        rd = RichDashboard(metrics={"loss": 0.5, "overlap": 0.0})
        table = rd.update_metrics()
        assert table is not None

    def test_empty_metrics_returns_table(self):
        rd = RichDashboard(metrics={})
        table = rd.update_metrics()
        assert table is not None

    def test_non_float_values(self):
        rd = RichDashboard(metrics={"status": "running"})
        table = rd.update_metrics()
        assert table is not None


class TestRichDashboardUpdateLossChart:
    """Tests for RichDashboard.update_loss_chart."""

    def test_no_data(self):
        rd = RichDashboard(losses=[])
        result = rd.update_loss_chart()
        assert result == "No data"

    def test_single_loss_value(self):
        rd = RichDashboard(losses=[1.0])
        result = rd.update_loss_chart()
        assert "Loss: 1.0000" in result

    def test_multiple_loss_values(self):
        rd = RichDashboard(losses=[0.1, 0.5, 1.0])
        result = rd.update_loss_chart()
        assert "Loss: 1.0000" in result

    def test_all_same_loss(self):
        rd = RichDashboard(losses=[0.5, 0.5, 0.5])
        result = rd.update_loss_chart()
        assert "Loss: 0.5000" in result


class TestRichDashboardOnPhaseStart:
    """Tests for RichDashboard.on_phase_start."""

    def test_sets_current_phase(self):
        rd = RichDashboard()
        rd.on_phase_start("geometric", None)
        assert rd.current_phase == "geometric"


class TestRichDashboardOnPhaseComplete:
    """Tests for RichDashboard.on_phase_complete."""

    def test_no_error(self):
        rd = RichDashboard()
        rd.on_phase_complete("geometric", None)


class TestRichDashboardOnIteration:
    """Tests for RichDashboard.on_iteration."""

    def test_sets_iteration(self):
        rd = RichDashboard()
        rd.on_iteration(42, None)
        assert rd.iteration == 42


class TestRichDashboardOnEpoch:
    """Tests for RichDashboard.on_epoch."""

    def test_appends_loss(self):
        rd = RichDashboard()
        rd.on_epoch(10, 0.25)
        assert rd.losses == [0.25]
        assert rd.metrics["epoch"] == 10
        assert rd.metrics["loss"] == 0.25

    def test_truncates_at_1000(self):
        rd = RichDashboard()
        for i in range(1200):
            rd.on_epoch(i, float(i))
        assert len(rd.losses) == 1000
        assert rd.losses[-1] == 1199.0


# =============================================================================
# create_progress_display
# =============================================================================


class TestCreateProgressDisplay:
    """Tests for create_progress_display factory."""

    def test_terminal_default(self):
        display = create_progress_display()
        assert isinstance(display, TerminalProgress)

    def test_terminal_explicit(self):
        display = create_progress_display("terminal")
        assert isinstance(display, TerminalProgress)

    def test_rich(self):
        display = create_progress_display("rich")
        assert isinstance(display, RichDashboard)

    def test_unknown_type_defaults_to_terminal(self):
        display = create_progress_display("unknown")
        assert isinstance(display, TerminalProgress)
