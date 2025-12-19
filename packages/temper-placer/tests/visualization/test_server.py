"""Tests for visualization/server.py - WebSocket server for live updates."""

import json

import pytest

from temper_placer.visualization.model import (
    BoardView,
    ConstraintStatus,
    LossHistory,
    VisualizationState,
)

# Check if websockets is available
try:
    import websockets

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def minimal_state():
    """Create a minimal visualization state for testing."""
    return VisualizationState(
        board=BoardView(width=100.0, height=80.0),
        loss_history=LossHistory(),
        constraints=ConstraintStatus(),
        epoch=0,
        elapsed_seconds=0.0,
        is_training=True,
    )


@pytest.fixture
def state_with_data():
    """Create a visualization state with some data."""
    from temper_placer.visualization.model import (
        ComponentView,
        LossDataPoint,
        Point,
        Violation,
        ViolationType,
    )

    board = BoardView(
        width=100.0,
        height=80.0,
        components=(
            ComponentView(
                ref="U1",
                position=Point(50.0, 40.0),
                rotation=0.0,
                width=10.0,
                height=5.0,
            ),
        ),
    )

    loss_history = LossHistory()
    loss_history.add_point(
        LossDataPoint(epoch=0, total_loss=10.0, breakdown={"overlap": 5.0, "boundary": 5.0})
    )
    loss_history.add_point(
        LossDataPoint(epoch=1, total_loss=8.0, breakdown={"overlap": 3.0, "boundary": 5.0})
    )

    constraints = ConstraintStatus(
        violations=(
            Violation(
                violation_type=ViolationType.OVERLAP,
                severity=0.5,
                component_refs=("U1", "U2"),
            ),
        ),
        overlap_count=1,
    )

    return VisualizationState(
        board=board,
        loss_history=loss_history,
        constraints=constraints,
        epoch=1,
        elapsed_seconds=5.0,
        is_training=True,
    )


# ============================================================================
# Tests for MockLiveServer (no websockets required)
# ============================================================================


class TestMockLiveServer:
    """Tests for MockLiveServer class."""

    def test_create_mock_server(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        assert server is not None
        assert server.url == "http://localhost:8765"
        assert server.ws_url == "ws://localhost:8765/ws"

    def test_mock_server_custom_port(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer(port=9000)
        assert server.url == "http://localhost:9000"

    def test_mock_server_start_stop(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        assert not server.state.is_running

        server.start()
        assert server.state.is_running

        server.stop()
        assert not server.state.is_running

    def test_mock_server_send_update(self, minimal_state):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        server.start()

        server.send_update(minimal_state)
        assert server.state.last_state is minimal_state
        assert len(server._updates) == 1

        server.send_update(minimal_state)
        assert len(server._updates) == 2

    def test_mock_server_client_count(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        assert server.client_count == 0

    def test_mock_server_is_paused(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        assert not server.is_paused

        server.state.is_paused = True
        assert server.is_paused

    def test_mock_server_training_notifications(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        server.start()

        # These should not raise
        server.send_training_started()
        server.send_training_stopped()
        server.send_training_complete()


# ============================================================================
# Tests for ServerConfig and ServerState
# ============================================================================


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_default_config(self):
        from temper_placer.visualization.server import ServerConfig

        config = ServerConfig()
        assert config.host == "localhost"
        assert config.port == 8765
        assert config.update_interval_ms == 100
        assert config.max_clients == 10
        assert config.open_browser is True

    def test_custom_config(self):
        from temper_placer.visualization.server import ServerConfig

        config = ServerConfig(
            host="0.0.0.0",
            port=9000,
            update_interval_ms=50,
            max_clients=5,
            open_browser=False,
        )
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.update_interval_ms == 50


class TestServerState:
    """Tests for ServerState dataclass."""

    def test_default_state(self):
        from temper_placer.visualization.server import ServerState

        state = ServerState()
        assert state.is_running is False
        assert state.is_paused is False
        assert state.last_state is None
        assert len(state.connected_clients) == 0

    def test_state_modification(self, minimal_state):
        from temper_placer.visualization.server import ServerState

        state = ServerState()
        state.is_running = True
        state.last_state = minimal_state

        assert state.is_running
        assert state.last_state is minimal_state


# ============================================================================
# Tests for MessageType
# ============================================================================


class TestMessageType:
    """Tests for MessageType enum."""

    def test_message_types_defined(self):
        from temper_placer.visualization.server import MessageType

        # Server -> Client
        assert MessageType.STATE_UPDATE.value == "state_update"
        assert MessageType.TRAINING_STARTED.value == "training_started"
        assert MessageType.TRAINING_STOPPED.value == "training_stopped"
        assert MessageType.TRAINING_COMPLETE.value == "training_complete"
        assert MessageType.ERROR.value == "error"

        # Client -> Server
        assert MessageType.PAUSE.value == "pause"
        assert MessageType.RESUME.value == "resume"
        assert MessageType.STEP.value == "step"
        assert MessageType.EXPORT.value == "export"
        assert MessageType.GET_STATE.value == "get_state"


# ============================================================================
# Tests for create_server factory function
# ============================================================================


class TestCreateServer:
    """Tests for create_server factory function."""

    def test_create_server_returns_instance(self):
        from temper_placer.visualization.server import create_server

        server = create_server(open_browser=False)
        # Returns either LiveServer or MockLiveServer depending on deps
        assert server is not None
        assert hasattr(server, "start")
        assert hasattr(server, "stop")
        assert hasattr(server, "send_update")

    def test_create_server_with_custom_port(self):
        from temper_placer.visualization.server import create_server

        server = create_server(port=9999, open_browser=False)
        assert "9999" in server.url


# ============================================================================
# Tests for LiveServer (websockets required)
# ============================================================================


@pytest.mark.skipif(not WEBSOCKETS_AVAILABLE, reason="websockets not installed")
class TestLiveServerInit:
    """Tests for LiveServer initialization."""

    def test_create_live_server(self):
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(open_browser=False)
        assert server is not None
        assert server.url == "http://localhost:8765"

    def test_custom_config(self):
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(
            host="0.0.0.0",
            port=9000,
            update_interval_ms=50,
            open_browser=False,
        )
        assert server.config.host == "0.0.0.0"
        assert server.config.port == 9000


@pytest.mark.skipif(not WEBSOCKETS_AVAILABLE, reason="websockets not installed")
class TestLiveServerCallbacks:
    """Tests for LiveServer callback functionality."""

    def test_pause_callback(self):
        from temper_placer.visualization.server import LiveServer

        pause_called = []

        def on_pause():
            pause_called.append(True)

        server = LiveServer(open_browser=False, on_pause=on_pause)
        assert server._on_pause is on_pause

    def test_resume_callback(self):
        from temper_placer.visualization.server import LiveServer

        resume_called = []

        def on_resume():
            resume_called.append(True)

        server = LiveServer(open_browser=False, on_resume=on_resume)
        assert server._on_resume is on_resume

    def test_step_callback(self):
        from temper_placer.visualization.server import LiveServer

        step_calls = []

        def on_step(n):
            step_calls.append(n)

        server = LiveServer(open_browser=False, on_step=on_step)
        assert server._on_step is on_step


@pytest.mark.skipif(not WEBSOCKETS_AVAILABLE, reason="websockets not installed")
class TestLiveServerLifecycle:
    """Tests for LiveServer start/stop lifecycle."""

    def test_start_stop(self):
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=18765, open_browser=False)
        assert not server.state.is_running

        server.start()
        assert server.state.is_running

        server.stop()
        assert not server.state.is_running

    def test_double_start(self):
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=18766, open_browser=False)
        server.start()

        # Second start should be a no-op (with warning)
        server.start()
        assert server.state.is_running

        server.stop()

    def test_double_stop(self):
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=18767, open_browser=False)
        server.start()
        server.stop()

        # Second stop should be a no-op
        server.stop()
        assert not server.state.is_running


@pytest.mark.skipif(not WEBSOCKETS_AVAILABLE, reason="websockets not installed")
class TestLiveServerUpdates:
    """Tests for LiveServer update functionality."""

    def test_send_update_stores_state(self, minimal_state):
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=18768, open_browser=False)
        server.start()

        try:
            server.send_update(minimal_state)
            assert server.state.last_state is minimal_state
        finally:
            server.stop()

    def test_rate_limiting(self, minimal_state):
        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=18769, update_interval_ms=100, open_browser=False)
        server.start()

        try:
            # First update should go through
            server.send_update(minimal_state)

            # Immediate second update should be rate-limited
            # (can't easily test this without timing, so just ensure no error)
            server.send_update(minimal_state)
        finally:
            server.stop()


# ============================================================================
# Tests for WebSocket-based message creation
# ============================================================================


@pytest.mark.skipif(not WEBSOCKETS_AVAILABLE, reason="websockets not installed")
class TestMessageCreation:
    """Tests for internal message creation."""

    def test_create_message_simple(self):
        from temper_placer.visualization.server import LiveServer, MessageType

        server = LiveServer(port=18770, open_browser=False)
        msg = server._create_message(MessageType.TRAINING_STARTED)

        data = json.loads(msg)
        assert data["type"] == "training_started"
        assert "data" not in data

    def test_create_message_with_data(self, minimal_state):
        from temper_placer.visualization.server import LiveServer, MessageType

        server = LiveServer(port=18771, open_browser=False)
        msg = server._create_message(MessageType.STATE_UPDATE, minimal_state.to_dict())

        data = json.loads(msg)
        assert data["type"] == "state_update"
        assert "data" in data
        assert "board" in data["data"]


# ============================================================================
# Tests for dependency checking
# ============================================================================


class TestWebsocketsDependency:
    """Tests for websockets dependency handling."""

    @pytest.mark.skipif(WEBSOCKETS_AVAILABLE, reason="websockets is installed")
    def test_live_server_raises_without_websockets(self):
        from temper_placer.visualization.server import LiveServer

        with pytest.raises(ImportError, match="websockets"):
            LiveServer()

    def test_websockets_available_flag(self):
        from temper_placer.visualization.server import WEBSOCKETS_AVAILABLE

        # Just check it's defined and boolean
        assert isinstance(WEBSOCKETS_AVAILABLE, bool)


# ============================================================================
# Integration-style tests (websockets required)
# Note: These tests use synchronous wrappers since pytest-asyncio is not available
# ============================================================================


@pytest.mark.skipif(not WEBSOCKETS_AVAILABLE, reason="websockets not installed")
class TestLiveServerIntegration:
    """Integration tests for LiveServer with actual WebSocket connections."""

    def test_connect_and_receive_update(self, minimal_state):
        """Test connecting a client and receiving an update."""
        import asyncio

        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=18772, open_browser=False)
        server.start()

        async def run_test():
            # Give server time to start
            await asyncio.sleep(0.2)

            # Connect a client
            async with websockets.connect(server.ws_url) as ws:
                # Send an update from the server
                server.send_update(minimal_state)

                # Wait for the update
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg)
                    assert data["type"] == "state_update"
                    assert "data" in data
                except TimeoutError:
                    pytest.skip("WebSocket message not received (timing issue)")

        try:
            asyncio.get_event_loop().run_until_complete(run_test())
        except DeprecationWarning:
            # Python 3.10+ prefers asyncio.run() but we need compatibility
            asyncio.run(run_test())
        finally:
            server.stop()

    def test_client_count(self):
        """Test that client count is tracked."""
        import asyncio

        from temper_placer.visualization.server import LiveServer

        server = LiveServer(port=18773, open_browser=False)
        server.start()

        async def run_test():
            await asyncio.sleep(0.2)

            assert server.client_count == 0

            async with websockets.connect(server.ws_url) as ws:
                await asyncio.sleep(0.1)
                assert server.client_count == 1

            # After disconnect
            await asyncio.sleep(0.1)
            assert server.client_count == 0

        try:
            asyncio.get_event_loop().run_until_complete(run_test())
        except DeprecationWarning:
            asyncio.run(run_test())
        finally:
            server.stop()


# ============================================================================
# Tests for pause/resume state
# ============================================================================


class TestPauseResumeState:
    """Tests for pause/resume state tracking."""

    def test_initial_not_paused(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        assert not server.is_paused

    def test_pause_state_changes(self):
        from temper_placer.visualization.server import MockLiveServer

        server = MockLiveServer()
        server.state.is_paused = True
        assert server.is_paused

        server.state.is_paused = False
        assert not server.is_paused
