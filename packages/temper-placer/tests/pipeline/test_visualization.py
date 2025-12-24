"""
Tests for pipeline visualization components.

This module tests the visualization classes for pipeline progress:
- TerminalProgress: ASCII progress display
- RichDashboard: Rich library terminal dashboard
- Progress callback integration
"""

from unittest.mock import Mock

# =============================================================================
# TerminalProgress Tests
# =============================================================================


class TestTerminalProgressExists:
    """Test that TerminalProgress class exists and is importable."""

    def test_terminal_progress_importable(self):
        """TerminalProgress should be importable."""
        from temper_placer.pipeline.visualization import TerminalProgress

        assert TerminalProgress is not None

    def test_terminal_progress_is_class(self):
        """TerminalProgress should be a class."""
        from temper_placer.pipeline.visualization import TerminalProgress

        assert isinstance(TerminalProgress, type)


class TestTerminalProgressInit:
    """Test TerminalProgress initialization."""

    def test_can_create_instance(self):
        """Should be able to create TerminalProgress instance."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert progress is not None

    def test_default_total_phases(self):
        """Default total_phases should be 8."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert progress.total_phases == 8

    def test_custom_total_phases(self):
        """Should accept custom total_phases."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress(total_phases=5)
        assert progress.total_phases == 5

    def test_initial_phase_is_zero(self):
        """Initial current_phase should be 0."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert progress.current_phase == 0

    def test_initial_iteration_is_zero(self):
        """Initial current_iteration should be 0."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert progress.current_iteration == 0


class TestTerminalProgressCallbacks:
    """Test TerminalProgress callback methods."""

    def test_has_on_phase_start(self):
        """Should have on_phase_start method."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert hasattr(progress, "on_phase_start")
        assert callable(progress.on_phase_start)

    def test_has_on_phase_complete(self):
        """Should have on_phase_complete method."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert hasattr(progress, "on_phase_complete")
        assert callable(progress.on_phase_complete)

    def test_has_on_iteration(self):
        """Should have on_iteration method."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert hasattr(progress, "on_iteration")
        assert callable(progress.on_iteration)

    def test_has_on_epoch(self):
        """Should have on_epoch method."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert hasattr(progress, "on_epoch")
        assert callable(progress.on_epoch)


class TestTerminalProgressPhaseStart:
    """Test TerminalProgress.on_phase_start behavior."""

    def test_increments_current_phase(self):
        """on_phase_start should increment current_phase."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        mock_state = Mock()

        assert progress.current_phase == 0
        progress.on_phase_start("input", mock_state)
        assert progress.current_phase == 1
        progress.on_phase_start("semantic", mock_state)
        assert progress.current_phase == 2

    def test_outputs_phase_name(self, capsys):
        """on_phase_start should output phase name."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        mock_state = Mock()

        progress.on_phase_start("semantic", mock_state)
        captured = capsys.readouterr()
        assert "semantic" in captured.out.lower()

    def test_outputs_progress_indicator(self, capsys):
        """on_phase_start should output progress indicator."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress(total_phases=4)
        mock_state = Mock()

        progress.on_phase_start("input", mock_state)
        captured = capsys.readouterr()
        assert "1" in captured.out and "4" in captured.out


class TestTerminalProgressPhaseComplete:
    """Test TerminalProgress.on_phase_complete behavior."""

    def test_outputs_done_indicator(self, capsys):
        """on_phase_complete should output done indicator."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        mock_state = Mock()

        progress.on_phase_complete("input", mock_state)
        captured = capsys.readouterr()
        assert (
            "done" in captured.out.lower()
            or "✓" in captured.out
            or "complete" in captured.out.lower()
        )


class TestTerminalProgressIteration:
    """Test TerminalProgress.on_iteration behavior."""

    def test_updates_current_iteration(self):
        """on_iteration should update current_iteration."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        mock_state = Mock()

        assert progress.current_iteration == 0
        progress.on_iteration(1, mock_state)
        assert progress.current_iteration == 1
        progress.on_iteration(2, mock_state)
        assert progress.current_iteration == 2

    def test_outputs_iteration_number(self, capsys):
        """on_iteration should output iteration number."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        mock_state = Mock()

        progress.on_iteration(3, mock_state)
        captured = capsys.readouterr()
        assert "3" in captured.out


class TestTerminalProgressEpoch:
    """Test TerminalProgress.on_epoch behavior."""

    def test_outputs_at_intervals(self, capsys):
        """on_epoch should output at regular intervals (every 100)."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()

        # Epoch 50 should not output (not multiple of 100)
        progress.on_epoch(50, 1.5)
        captured = capsys.readouterr()
        assert captured.out == "" or "50" not in captured.out

        # Epoch 100 should output
        progress.on_epoch(100, 1.2)
        captured = capsys.readouterr()
        assert "100" in captured.out or "1.2" in captured.out

    def test_outputs_loss_value(self, capsys):
        """on_epoch should output loss value at intervals."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()

        progress.on_epoch(100, 0.5432)
        captured = capsys.readouterr()
        assert "0.54" in captured.out or "0.5432" in captured.out


class TestTerminalProgressBar:
    """Test TerminalProgress progress bar rendering."""

    def test_has_make_bar_method(self):
        """Should have _make_bar method."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        assert hasattr(progress, "_make_bar")

    def test_make_bar_returns_string(self):
        """_make_bar should return a string."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()
        result = progress._make_bar(1, 4)
        assert isinstance(result, str)

    def test_make_bar_shows_progress(self):
        """_make_bar should show different progress levels."""
        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()

        bar_25 = progress._make_bar(1, 4)
        bar_50 = progress._make_bar(2, 4)
        bar_100 = progress._make_bar(4, 4)

        # Different progress should produce different bars
        assert bar_25 != bar_100
        assert bar_50 != bar_100


# =============================================================================
# RichDashboard Tests
# =============================================================================


class TestRichDashboardExists:
    """Test that RichDashboard class exists and is importable."""

    def test_rich_dashboard_importable(self):
        """RichDashboard should be importable."""
        from temper_placer.pipeline.visualization import RichDashboard

        assert RichDashboard is not None

    def test_rich_dashboard_is_class(self):
        """RichDashboard should be a class."""
        from temper_placer.pipeline.visualization import RichDashboard

        assert isinstance(RichDashboard, type)


class TestRichDashboardInit:
    """Test RichDashboard initialization."""

    def test_can_create_instance(self):
        """Should be able to create RichDashboard instance."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert dashboard is not None

    def test_has_console(self):
        """Should have a console attribute."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert hasattr(dashboard, "console")

    def test_has_losses_list(self):
        """Should have a losses list."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert hasattr(dashboard, "losses")
        assert isinstance(dashboard.losses, list)

    def test_has_metrics_dict(self):
        """Should have a metrics dict."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert hasattr(dashboard, "metrics")
        assert isinstance(dashboard.metrics, dict)


class TestRichDashboardMethods:
    """Test RichDashboard methods."""

    def test_has_create_layout(self):
        """Should have create_layout method."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert hasattr(dashboard, "create_layout")
        assert callable(dashboard.create_layout)

    def test_has_update_header(self):
        """Should have update_header method."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert hasattr(dashboard, "update_header")
        assert callable(dashboard.update_header)

    def test_has_update_metrics(self):
        """Should have update_metrics method."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert hasattr(dashboard, "update_metrics")
        assert callable(dashboard.update_metrics)

    def test_has_update_loss_chart(self):
        """Should have update_loss_chart method."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        assert hasattr(dashboard, "update_loss_chart")
        assert callable(dashboard.update_loss_chart)


class TestRichDashboardLossChart:
    """Test RichDashboard loss chart rendering."""

    def test_loss_chart_returns_string(self):
        """update_loss_chart should return a string."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        result = dashboard.update_loss_chart()
        assert isinstance(result, str)

    def test_loss_chart_empty_when_no_data(self):
        """update_loss_chart should indicate no data when empty."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        result = dashboard.update_loss_chart()
        assert "no data" in result.lower() or result == ""

    def test_loss_chart_shows_data_when_present(self):
        """update_loss_chart should show data when losses exist."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        dashboard.losses = [1.0, 0.8, 0.6, 0.4, 0.2]
        result = dashboard.update_loss_chart()
        # Should show current loss value
        assert "0.2" in result or len(result) > 5


class TestRichDashboardMetrics:
    """Test RichDashboard metrics display."""

    def test_update_metrics_with_empty(self):
        """update_metrics should work with no metrics."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        result = dashboard.update_metrics()
        # Should return a table even if empty
        assert result is not None

    def test_update_metrics_with_data(self):
        """update_metrics should include metric data."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()
        dashboard.metrics = {"epoch": 100, "loss": 0.5}
        result = dashboard.update_metrics()
        assert result is not None


# =============================================================================
# ProgressCallback Tests
# =============================================================================


class TestProgressCallbackExists:
    """Test that ProgressCallback class exists."""

    def test_progress_callback_importable(self):
        """ProgressCallback should be importable."""
        from temper_placer.pipeline.visualization import ProgressCallback

        assert ProgressCallback is not None


class TestProgressCallbackMethods:
    """Test ProgressCallback interface methods."""

    def test_has_on_phase_start(self):
        """ProgressCallback should define on_phase_start."""
        from temper_placer.pipeline.visualization import ProgressCallback

        callback = ProgressCallback()
        assert hasattr(callback, "on_phase_start")

    def test_has_on_phase_complete(self):
        """ProgressCallback should define on_phase_complete."""
        from temper_placer.pipeline.visualization import ProgressCallback

        callback = ProgressCallback()
        assert hasattr(callback, "on_phase_complete")

    def test_has_on_iteration(self):
        """ProgressCallback should define on_iteration."""
        from temper_placer.pipeline.visualization import ProgressCallback

        callback = ProgressCallback()
        assert hasattr(callback, "on_iteration")

    def test_has_on_epoch(self):
        """ProgressCallback should define on_epoch."""
        from temper_placer.pipeline.visualization import ProgressCallback

        callback = ProgressCallback()
        assert hasattr(callback, "on_epoch")


# =============================================================================
# Integration Tests
# =============================================================================


class TestVisualizationIntegration:
    """Integration tests for visualization with pipeline."""

    def test_terminal_progress_as_callback(self):
        """TerminalProgress should work as orchestrator callback."""

        from temper_placer.pipeline.visualization import TerminalProgress

        progress = TerminalProgress()

        # Should be able to assign callbacks
        mock_orchestrator = Mock()
        mock_orchestrator.on_phase_start = progress.on_phase_start
        mock_orchestrator.on_phase_complete = progress.on_phase_complete
        mock_orchestrator.on_iteration = progress.on_iteration

        # Callbacks should be callable
        assert callable(mock_orchestrator.on_phase_start)
        assert callable(mock_orchestrator.on_phase_complete)
        assert callable(mock_orchestrator.on_iteration)

    def test_rich_dashboard_tracking(self):
        """RichDashboard should track losses over time."""
        from temper_placer.pipeline.visualization import RichDashboard

        dashboard = RichDashboard()

        # Simulate epoch updates
        for i in range(10):
            dashboard.losses.append(1.0 - i * 0.1)
            dashboard.metrics["epoch"] = i * 100
            dashboard.metrics["loss"] = dashboard.losses[-1]

        assert len(dashboard.losses) == 10
        assert dashboard.metrics["epoch"] == 900
        assert abs(dashboard.metrics["loss"] - 0.1) < 0.01


class TestCreateProgressDisplay:
    """Test factory function for creating progress displays."""

    def test_create_progress_display_exists(self):
        """create_progress_display function should exist."""
        from temper_placer.pipeline.visualization import create_progress_display

        assert create_progress_display is not None
        assert callable(create_progress_display)

    def test_create_terminal_progress(self):
        """create_progress_display('terminal') should return TerminalProgress."""
        from temper_placer.pipeline.visualization import (
            TerminalProgress,
            create_progress_display,
        )

        progress = create_progress_display("terminal")
        assert isinstance(progress, TerminalProgress)

    def test_create_rich_dashboard(self):
        """create_progress_display('rich') should return RichDashboard."""
        from temper_placer.pipeline.visualization import (
            RichDashboard,
            create_progress_display,
        )

        dashboard = create_progress_display("rich")
        assert isinstance(dashboard, RichDashboard)

    def test_create_default_returns_terminal(self):
        """create_progress_display() should default to terminal."""
        from temper_placer.pipeline.visualization import (
            TerminalProgress,
            create_progress_display,
        )

        progress = create_progress_display()
        assert isinstance(progress, TerminalProgress)
