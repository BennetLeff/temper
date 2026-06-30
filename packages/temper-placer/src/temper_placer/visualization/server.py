"""
WebSocket server for live visualization updates.

This module provides a lightweight HTTP + WebSocket server for streaming
placement optimization state to browser clients in real-time.

Features:
- HTTP server serves static HTML/JS viewer
- WebSocket endpoint pushes updates to all connected clients
- Support for pause/resume control messages from clients
- Thread-safe for integration with optimizer training loop

Usage:
    server = LiveServer(port=8765)
    server.start()

    # In training loop:
    server.send_update(visualization_state)

    # At end:
    server.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .model import VisualizationState

# Check if websockets is available (optional dependency)
try:
    import websockets
    from websockets.asyncio.server import serve

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    websockets = None  # type: ignore
    serve = None  # type: ignore


logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages sent/received via WebSocket."""

    # Server -> Client
    STATE_UPDATE = "state_update"
    TRAINING_STARTED = "training_started"
    TRAINING_STOPPED = "training_stopped"
    TRAINING_COMPLETE = "training_complete"
    STAGE_CHANGE = "stage_change"
    ERROR = "error"

    # Client -> Server
    PAUSE = "pause"
    RESUME = "resume"
    STEP = "step"
    EXPORT = "export"
    GET_STATE = "get_state"


@dataclass
class ServerConfig:
    """Configuration for the live visualization server."""

    host: str = "localhost"
    port: int = 8765
    static_dir: Path | None = None  # Directory containing HTML/JS files
    update_interval_ms: int = 100  # Minimum time between updates
    max_clients: int = 10
    open_browser: bool = True


@dataclass
class ServerState:
    """Internal state of the server."""

    is_running: bool = False
    is_paused: bool = False
    last_state: VisualizationState | None = None
    connected_clients: set[Any] = field(default_factory=set)
    step_count: int = 0


class LiveServer:
    """
    WebSocket server for streaming visualization updates.

    The server runs in a background thread and provides:
    - HTTP server for serving static viewer files
    - WebSocket server for real-time updates
    - Thread-safe methods for sending updates from the training loop
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        static_dir: Path | None = None,
        update_interval_ms: int = 100,
        open_browser: bool = True,
        on_pause: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
        on_step: Callable[[int], None] | None = None,
    ):
        """
        Initialize the live server.

        Args:
            host: Host to bind to.
            port: Port number for WebSocket server.
            static_dir: Directory containing static files (HTML, JS, CSS).
            update_interval_ms: Minimum milliseconds between updates.
            open_browser: Whether to open browser on start.
            on_pause: Callback when client requests pause.
            on_resume: Callback when client requests resume.
            on_step: Callback when client requests N steps.
        """
        self._check_dependencies()

        self.config = ServerConfig(
            host=host,
            port=port,
            static_dir=static_dir or self._default_static_dir(),
            update_interval_ms=update_interval_ms,
            open_browser=open_browser,
        )

        self.state = ServerState()

        # Callbacks for training control
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_step = on_step

        # Threading
        self._server_thread: threading.Thread | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._ws_server: Any | None = None
        self._stop_event = threading.Event()

        # Rate limiting
        self._last_update_time = 0.0

        # Connected clients (weakref set for automatic cleanup)
        self._clients: set[Any] = set()
        self._clients_lock = threading.Lock()

    def _check_dependencies(self) -> None:
        """Check if required dependencies are available."""
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets is required for live visualization. "
                "Install with: pip install websockets"
            )

    def _default_static_dir(self) -> Path:
        """Get the default static files directory."""
        return Path(__file__).parent / "static"

    @property
    def url(self) -> str:
        """Get the URL for the viewer."""
        return f"http://{self.config.host}:{self.config.port}"

    @property
    def ws_url(self) -> str:
        """Get the WebSocket URL."""
        return f"ws://{self.config.host}:{self.config.port}/ws"

    def start(self) -> None:
        """Start the server in a background thread."""
        if self.state.is_running:
            logger.warning("Server already running")
            return

        self._stop_event.clear()
        self._server_thread = threading.Thread(
            target=self._run_server,
            name="VisualizationServer",
            daemon=True,
        )
        self._server_thread.start()

        # Wait for server to start
        import time

        for _ in range(50):  # 5 second timeout
            if self.state.is_running:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Server failed to start within 5 seconds")

        logger.info(f"Visualization server started at {self.url}")

        if self.config.open_browser:
            self._open_browser()

    def stop(self) -> None:
        """Stop the server."""
        if not self.state.is_running:
            return

        logger.info("Stopping visualization server...")
        self._stop_event.set()

        # Cancel the event loop
        if self._event_loop:
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)

        # Wait for thread to finish
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5.0)

        self.state.is_running = False
        logger.info("Visualization server stopped")

    def send_update(self, state: VisualizationState) -> None:
        """
        Send a state update to all connected clients.

        This method is thread-safe and can be called from the training loop.
        Updates are rate-limited based on update_interval_ms.

        Args:
            state: Current visualization state to send.
        """
        import time

        # Rate limiting
        current_time = time.time() * 1000
        if current_time - self._last_update_time < self.config.update_interval_ms:
            return

        self._last_update_time = current_time
        self.state.last_state = state

        # Send to all clients
        if self._event_loop and self.state.is_running:
            message = self._create_message(MessageType.STATE_UPDATE, state.to_dict())
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._event_loop)

    def send_training_started(self) -> None:
        """Notify clients that training has started."""
        if self._event_loop and self.state.is_running:
            message = self._create_message(MessageType.TRAINING_STARTED)
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._event_loop)

    def send_training_stopped(self) -> None:
        """Notify clients that training has stopped (paused)."""
        if self._event_loop and self.state.is_running:
            message = self._create_message(MessageType.TRAINING_STOPPED)
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._event_loop)

    def send_training_complete(self, final_state: VisualizationState | None = None) -> None:
        """Notify clients that training is complete."""
        if self._event_loop and self.state.is_running:
            data = final_state.to_dict() if final_state else None
            message = self._create_message(MessageType.TRAINING_COMPLETE, data)
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._event_loop)

    def send_stage_change(
        self, stage: str, phase: str = "active",
        elapsed_seconds: float = 0.0, eta_seconds: float | None = None,
    ) -> None:
        """Notify clients of a pipeline stage change."""
        if self._event_loop and self.state.is_running:
            data = {
                "stage": stage,
                "phase": phase,
                "elapsed_seconds": elapsed_seconds,
                "eta_seconds": eta_seconds,
            }
            message = self._create_message(MessageType.STAGE_CHANGE, data)
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._event_loop)

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        with self._clients_lock:
            return len(self._clients)

    @property
    def is_paused(self) -> bool:
        """Check if training is paused."""
        return self.state.is_paused

    def _run_server(self) -> None:
        """Run the WebSocket server (in background thread)."""
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)

        try:
            self._event_loop.run_until_complete(self._start_servers())
            self.state.is_running = True
            self._event_loop.run_forever()
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self._event_loop.close()
            self._event_loop = None

    async def _start_servers(self) -> None:
        """Start both HTTP and WebSocket servers."""
        from websockets.http11 import Response
        from websockets.datastructures import Headers

        static_dir = self.config.static_dir or self._default_static_dir()

        async def http_handler(connection: Any, request: Any) -> Response | None:
            """Handle HTTP requests by serving static files. Return None for WebSocket upgrade."""
            if request.path is None:
                return Response(404, "Not Found", Headers())

            # Let WebSocket upgrade requests through
            if request.path == "/ws" or request.headers.get("Upgrade", "").lower() == "websocket":
                return None

            path = request.path.lstrip("/")
            if path in ("", "index.html"):
                file_path = static_dir / "wasm-viewer.html"
            else:
                # Prevent directory traversal
                file_path = (static_dir / path).resolve()
                if not str(file_path).startswith(str(static_dir.resolve())):
                    return Response(404, "Not Found", Headers())

            if not file_path.is_file():
                return Response(404, "Not Found", Headers())

            content_type = _guess_mime_type(file_path)
            try:
                body = file_path.read_bytes()
                headers = Headers({
                    "Content-Type": content_type,
                    "Content-Length": str(len(body)),
                })
                return Response(200, "OK", headers, body=body)
            except OSError:
                return Response(500, "Internal Server Error", Headers())

        self._ws_server = await serve(
            self._handle_client,
            self.config.host,
            self.config.port,
            process_request=http_handler,
        )
        logger.debug(f"Server listening on {self.url} (ws: {self.ws_url})")

    async def _handle_client(self, websocket: Any) -> None:
        """Handle a WebSocket client connection."""
        # Register client
        with self._clients_lock:
            if len(self._clients) >= self.config.max_clients:
                await websocket.close(1013, "Server at maximum capacity")
                return
            self._clients.add(websocket)

        logger.info(f"Client connected ({self.client_count} total)")

        try:
            # Send current state if available
            if self.state.last_state:
                message = self._create_message(
                    MessageType.STATE_UPDATE, self.state.last_state.to_dict()
                )
                await websocket.send(message)

            # Handle incoming messages
            async for raw_message in websocket:
                await self._handle_message(websocket, raw_message)

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            # Unregister client
            with self._clients_lock:
                self._clients.discard(websocket)
            logger.info(f"Client disconnected ({self.client_count} remaining)")

    async def _handle_message(self, websocket: Any, raw_message: str) -> None:
        """Handle an incoming message from a client."""
        try:
            data = json.loads(raw_message)
            msg_type = data.get("type")

            if msg_type == MessageType.PAUSE.value:
                self.state.is_paused = True
                if self._on_pause:
                    self._on_pause()
                await self._broadcast(self._create_message(MessageType.TRAINING_STOPPED))

            elif msg_type == MessageType.RESUME.value:
                self.state.is_paused = False
                if self._on_resume:
                    self._on_resume()
                await self._broadcast(self._create_message(MessageType.TRAINING_STARTED))

            elif msg_type == MessageType.STEP.value:
                steps = data.get("steps", 1)
                if self._on_step:
                    self._on_step(steps)

            elif msg_type == MessageType.GET_STATE.value:
                if self.state.last_state:
                    message = self._create_message(
                        MessageType.STATE_UPDATE, self.state.last_state.to_dict()
                    )
                    await websocket.send(message)

            elif msg_type == MessageType.EXPORT.value:
                # Export functionality would be handled by LiveVisualizer
                pass

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from client: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _broadcast(self, message: str) -> None:
        """Send a message to all connected clients."""
        with self._clients_lock:
            clients = list(self._clients)

        if not clients:
            return

        # Send to all clients, removing dead ones
        dead_clients = []
        for client in clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                dead_clients.append(client)
            except Exception as e:
                logger.debug(f"Error sending to client: {e}")
                dead_clients.append(client)

        # Clean up dead clients
        if dead_clients:
            with self._clients_lock:
                for client in dead_clients:
                    self._clients.discard(client)

    def _create_message(self, msg_type: MessageType, data: dict[str, Any] | None = None) -> str:
        """Create a JSON message."""
        message: dict[str, Any] = {"type": msg_type.value}
        if data is not None:
            message["data"] = data
        return json.dumps(message)

    def _open_browser(self) -> None:
        """Open the viewer in a web browser."""
        import webbrowser

        try:
            webbrowser.open(self.url)
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")


class MockLiveServer:
    """
    Mock server for testing without websockets dependency.

    Provides the same interface as LiveServer but doesn't actually
    start any servers or send any messages.
    """

    def __init__(self, **kwargs: Any):
        self.config = ServerConfig(
            **{k: v for k, v in kwargs.items() if k in ServerConfig.__dataclass_fields__}
        )
        self.state = ServerState()
        self._updates: list[VisualizationState] = []

    @property
    def url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.config.host}:{self.config.port}/ws"

    def start(self) -> None:
        self.state.is_running = True

    def stop(self) -> None:
        self.state.is_running = False

    def send_update(self, state: VisualizationState) -> None:
        self.state.last_state = state
        self._updates.append(state)

    def send_training_started(self) -> None:
        pass

    def send_training_stopped(self) -> None:
        pass

    def send_training_complete(self, final_state: VisualizationState | None = None) -> None:
        pass

    @property
    def client_count(self) -> int:
        return 0

    @property
    def is_paused(self) -> bool:
        return self.state.is_paused


def create_server(**kwargs: Any) -> LiveServer | MockLiveServer:
    """
    Create a visualization server.

    Returns a MockLiveServer if websockets is not installed,
    or a real LiveServer otherwise.

    Args:
        **kwargs: Arguments passed to server constructor.

    Returns:
        Server instance.
    """
    if WEBSOCKETS_AVAILABLE:
        return LiveServer(**kwargs)
    else:
        logger.warning(
            "websockets not installed, using mock server. Install with: pip install websockets"
        )
        return MockLiveServer(**kwargs)


def _guess_mime_type(file_path: Path) -> str:
    """Guess MIME type from file extension."""
    ext = file_path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".wasm": "application/wasm",
        ".json": "application/json",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }.get(ext, "application/octet-stream")
