"""Tests for visualization/live.py - LiveVisualizer integration."""

import threading

import numpy as np
import pytest

# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def sample_positions():
    """Create sample component positions."""
    return np.array([[10.0, 20.0], [50.0, 40.0], [80.0, 60.0]])


@pytest.fixture
def sample_rotations():
    """Create sample component rotations."""
    return np.array([0.0, 90.0, 45.0])


@pytest.fixture
def sample_widths():
    """Create sample component widths."""
    return np.array([10.0, 15.0, 12.0])


@pytest.fixture
def sample_heights():
    """Create sample component heights."""
    return np.array([5.0, 8.0, 6.0])


@pytest.fixture
def sample_refs():
    """Create sample component references."""
    return ["U1", "U2", "U3"]


@pytest.fixture
def sample_losses():
    """Create sample loss values."""
    return {"overlap": 0.5, "boundary": 0.3, "wirelength": 0.2, "total": 1.0}


# ============================================================================
# Tests for LiveVisualizerConfig
# ============================================================================


class TestLiveVisualizerConfig:
    """Tests for LiveVisualizerConfig dataclass."""

    def test_default_config(self):
        from temper_placer.visualization.live import LiveVisualizerConfig

        config = LiveVisualizerConfig()
        assert config.host == "localhost"
        assert config.port == 8765
        assert config.open_browser is True
        assert config.update_interval_ms == 100
        assert config.headless is False
        assert config.verbose is True

    def test_custom_config(self):
        from temper_placer.visualization.live import LiveVisualizerConfig

        config = LiveVisualizerConfig(
            host="0.0.0.0",
            port=9000,
            headless=True,
            verbose=False,
        )
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.headless is True
        assert config.verbose is False


# ============================================================================
# Tests for LiveVisualizer initialization
# ============================================================================


class TestLiveVisualizerInit:
    """Tests for LiveVisualizer initialization."""

    def test_create_visualizer_default(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer()
        assert viz.config.port == 8765
        assert viz.config.host == "localhost"
        assert not viz.is_running

    def test_create_visualizer_custom_port(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(port=9000, open_browser=False)
        assert viz.config.port == 9000

    def test_create_visualizer_headless(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True)
        assert viz.config.headless is True

    def test_url_property(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(port=8888)
        assert viz.url == "http://localhost:8888"


# ============================================================================
# Tests for LiveVisualizer lifecycle
# ============================================================================


class TestLiveVisualizerLifecycle:
    """Tests for LiveVisualizer start/stop lifecycle."""

    def test_start_stop_headless(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        assert not viz.is_running

        viz.start()
        assert viz.is_running

        viz.stop()
        assert not viz.is_running

    def test_double_start_is_noop(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()
        viz.start()  # Should not raise
        assert viz.is_running
        viz.stop()

    def test_stop_when_not_running(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.stop()  # Should not raise
        assert not viz.is_running

    def test_client_count_headless(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True)
        viz.start()
        assert viz.client_count == 0
        viz.stop()


# ============================================================================
# Tests for LiveVisualizer updates
# ============================================================================


class TestLiveVisualizerUpdates:
    """Tests for LiveVisualizer update functionality."""

    def test_update_adds_to_history(
        self,
        sample_positions,
        sample_rotations,
        sample_widths,
        sample_heights,
        sample_refs,
        sample_losses,
    ):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        viz.update(
            positions=sample_positions,
            rotations=sample_rotations,
            widths=sample_widths,
            heights=sample_heights,
            refs=sample_refs,
            board_width=100.0,
            board_height=80.0,
            losses=sample_losses,
            epoch=0,
        )

        history = viz.get_loss_history()
        assert len(history.epochs) == 1
        assert history.epochs[0] == 0
        assert history.losses[0] == 1.0  # losses property returns total_loss values

        viz.stop()

    def test_update_multiple_epochs(
        self, sample_positions, sample_rotations, sample_widths, sample_heights, sample_refs
    ):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        for epoch in range(5):
            viz.update(
                positions=sample_positions,
                rotations=sample_rotations,
                widths=sample_widths,
                heights=sample_heights,
                refs=sample_refs,
                board_width=100.0,
                board_height=80.0,
                losses={"total": float(10 - epoch)},
                epoch=epoch,
            )

        history = viz.get_loss_history()
        assert len(history.epochs) == 5
        assert history.epochs == [0, 1, 2, 3, 4]
        assert history.losses == [
            10.0,
            9.0,
            8.0,
            7.0,
            6.0,
        ]  # losses property returns total_loss values

        viz.stop()

    def test_update_not_running_is_noop(
        self,
        sample_positions,
        sample_rotations,
        sample_widths,
        sample_heights,
        sample_refs,
        sample_losses,
    ):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        # Don't start

        viz.update(
            positions=sample_positions,
            rotations=sample_rotations,
            widths=sample_widths,
            heights=sample_heights,
            refs=sample_refs,
            board_width=100.0,
            board_height=80.0,
            losses=sample_losses,
            epoch=0,
        )

        history = viz.get_loss_history()
        assert len(history.epochs) == 0

    def test_update_with_flattened_positions(
        self, sample_rotations, sample_widths, sample_heights, sample_refs, sample_losses
    ):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        # Flattened positions [x0, x1, x2, y0, y1, y2]
        positions = np.array([10.0, 50.0, 80.0, 20.0, 40.0, 60.0])

        viz.update(
            positions=positions,
            rotations=sample_rotations,
            widths=sample_widths,
            heights=sample_heights,
            refs=sample_refs,
            board_width=100.0,
            board_height=80.0,
            losses=sample_losses,
            epoch=0,
        )

        history = viz.get_loss_history()
        assert len(history.epochs) == 1

        viz.stop()


# ============================================================================
# Tests for violation detection
# ============================================================================


class TestViolationDetection:
    """Tests for constraint violation detection."""

    def test_detect_overlap_violation(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        positions = np.array([[10.0, 20.0]])
        rotations = np.array([0.0])
        widths = np.array([10.0])
        heights = np.array([5.0])
        refs = ["U1"]

        # High overlap loss should trigger violation
        viz.update(
            positions=positions,
            rotations=rotations,
            widths=widths,
            heights=heights,
            refs=refs,
            board_width=100.0,
            board_height=80.0,
            losses={"overlap": 0.5, "total": 0.5},
            epoch=0,
        )

        # Check that violation was detected via server state
        assert viz._server.state.last_state is not None
        constraints = viz._server.state.last_state.constraints
        assert constraints.overlap_count > 0

        viz.stop()

    def test_no_violations_when_losses_zero(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        positions = np.array([[10.0, 20.0]])
        rotations = np.array([0.0])
        widths = np.array([10.0])
        heights = np.array([5.0])
        refs = ["U1"]

        # Zero losses should have no violations
        viz.update(
            positions=positions,
            rotations=rotations,
            widths=widths,
            heights=heights,
            refs=refs,
            board_width=100.0,
            board_height=80.0,
            losses={"overlap": 0.0, "boundary": 0.0, "total": 0.0},
            epoch=0,
        )

        constraints = viz._server.state.last_state.constraints
        assert constraints.overlap_count == 0
        assert constraints.boundary_violations == 0  # Note: boundary_violations, not boundary_count

        viz.stop()


# ============================================================================
# Tests for clear_history
# ============================================================================


class TestClearHistory:
    """Tests for clearing loss history."""

    def test_clear_history(
        self,
        sample_positions,
        sample_rotations,
        sample_widths,
        sample_heights,
        sample_refs,
        sample_losses,
    ):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        # Add some data
        for epoch in range(3):
            viz.update(
                positions=sample_positions,
                rotations=sample_rotations,
                widths=sample_widths,
                heights=sample_heights,
                refs=sample_refs,
                board_width=100.0,
                board_height=80.0,
                losses=sample_losses,
                epoch=epoch,
            )

        assert len(viz.get_loss_history().epochs) == 3

        # Clear
        viz.clear_history()
        assert len(viz.get_loss_history().epochs) == 0

        viz.stop()


# ============================================================================
# Tests for update_from_state
# ============================================================================


class TestUpdateFromState:
    """Tests for update_from_state convenience method."""

    def test_update_from_state(self, sample_positions, sample_rotations):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        component_info = {
            "widths": [10.0, 15.0, 12.0],
            "heights": [5.0, 8.0, 6.0],
            "refs": ["U1", "U2", "U3"],
        }
        board_info = {"width": 100.0, "height": 80.0}
        loss_info = {"total": 1.0, "overlap": 0.5}

        viz.update_from_state(
            positions=sample_positions,
            rotations=sample_rotations,
            component_info=component_info,
            board_info=board_info,
            loss_info=loss_info,
            epoch=0,
        )

        history = viz.get_loss_history()
        assert len(history.epochs) == 1
        assert history.losses[0] == 1.0  # losses property returns total_loss values

        viz.stop()


# ============================================================================
# Tests for create_visualizer factory
# ============================================================================


class TestCreateVisualizerFactory:
    """Tests for create_visualizer factory function."""

    def test_create_visualizer_defaults(self):
        from temper_placer.visualization.live import create_visualizer

        viz = create_visualizer()
        assert viz.config.port == 8765
        assert viz.config.headless is False

    def test_create_visualizer_headless(self):
        from temper_placer.visualization.live import create_visualizer

        viz = create_visualizer(headless=True, verbose=False)
        assert viz.config.headless is True

    def test_create_visualizer_custom_port(self):
        from temper_placer.visualization.live import create_visualizer

        viz = create_visualizer(port=9999)
        assert viz.config.port == 9999


# ============================================================================
# Tests for thread safety
# ============================================================================


class TestThreadSafety:
    """Tests for thread-safe operation."""

    def test_concurrent_updates(
        self, sample_positions, sample_rotations, sample_widths, sample_heights, sample_refs
    ):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()

        errors = []

        def update_worker(start_epoch, count):
            try:
                for i in range(count):
                    viz.update(
                        positions=sample_positions,
                        rotations=sample_rotations,
                        widths=sample_widths,
                        heights=sample_heights,
                        refs=sample_refs,
                        board_width=100.0,
                        board_height=80.0,
                        losses={"total": float(start_epoch + i)},
                        epoch=start_epoch + i,
                    )
            except Exception as e:
                errors.append(e)

        # Run updates from multiple threads
        threads = [
            threading.Thread(target=update_worker, args=(0, 10)),
            threading.Thread(target=update_worker, args=(10, 10)),
            threading.Thread(target=update_worker, args=(20, 10)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not have any errors
        assert len(errors) == 0

        # Should have all epochs recorded
        history = viz.get_loss_history()
        assert len(history.epochs) == 30

        viz.stop()


# ============================================================================
# Tests for pause/resume
# ============================================================================


class TestPauseResume:
    """Tests for pause/resume functionality."""

    def test_is_paused_initially_false(self):
        from temper_placer.visualization.live import LiveVisualizer

        viz = LiveVisualizer(headless=True, verbose=False)
        viz.start()
        assert not viz.is_paused
        viz.stop()

    def test_pause_callback(self):
        from temper_placer.visualization.live import LiveVisualizer

        pause_called = []

        def on_pause():
            pause_called.append(True)

        viz = LiveVisualizer(headless=True, verbose=False, on_pause=on_pause)
        assert viz._on_pause is on_pause

    def test_resume_callback(self):
        from temper_placer.visualization.live import LiveVisualizer

        resume_called = []

        def on_resume():
            resume_called.append(True)

        viz = LiveVisualizer(headless=True, verbose=False, on_resume=on_resume)
        assert viz._on_resume is on_resume
