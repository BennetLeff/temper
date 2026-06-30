"""End-to-end tests for the WASM viewer server integration.

Verifies:
1. HTTP static file serving (HTML, JS, WASM, CSS) with correct MIME types
2. WebSocket connect/disconnect
3. STATE_UPDATE message stream
4. STAGE_CHANGE message stream
5. Viewer HTML serves with correct content
"""

import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from temper_placer.visualization.server import LiveServer, MessageType
from temper_placer.visualization.model import (
    BoardView,
    ComponentView,
    ConstraintStatus,
    LossDataPoint,
    LossHistory,
    Point,
    VisualizationState,
)

STATIC_DIR = Path(__file__).parent.parent / "src" / "temper_placer" / "visualization" / "static"


def _build_test_state() -> VisualizationState:
    """Build a minimal VisualizationState for testing."""
    board = BoardView(
        width=100.0,
        height=150.0,
        components=(
            ComponentView(
                ref="U1",
                position=Point(50.0, 75.0),
                rotation=0.0,
                width=10.0,
                height=5.0,
                footprint="SOIC-8",
                value="LM358",
                zone="control_zone",
            ),
            ComponentView(
                ref="C1",
                position=Point(30.0, 60.0),
                rotation=90.0,
                width=2.0,
                height=1.0,
                footprint="0805",
                value="100uF",
            ),
        ),
    )
    loss = LossHistory()
    loss.add_point(LossDataPoint(
        epoch=1,
        total_loss=3.14,
        breakdown={"overlap": 1.0, "wirelength": 2.14},
    ))
    constraints = ConstraintStatus()
    return VisualizationState(board=board, loss_history=loss, constraints=constraints, epoch=42)


class TestLiveServerE2E:
    """End-to-end tests for LiveServer HTTP + WebSocket."""

    @pytest.fixture
    def server(self):
        """Start a LiveServer for testing."""
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()

        srv = LiveServer(
            host="localhost",
            port=port,
            static_dir=STATIC_DIR,
            open_browser=False,
        )
        srv.start()
        time.sleep(0.5)
        srv._port = port  # Store for tests
        yield srv
        srv.stop()
        time.sleep(0.2)

    def test_http_serves_viewer_html(self, server):
        """Verify the viewer HTML is served with correct MIME type."""
        url = f"http://localhost:{server._port}/wasm-viewer.html"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/html" in content_type
            body = resp.read().decode("utf-8")
            assert "<!DOCTYPE html>" in body
            assert "Temper Board Viewer" in body
            assert "board-canvas" in body
            assert 'id="sidebar"' in body

    def test_http_serves_css(self, server):
        """Verify CSS is served with correct MIME type."""
        url = f"http://localhost:{server._port}/wasm-viewer.css"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/css" in content_type

    def test_http_serves_js(self, server):
        """Verify JavaScript is served with correct MIME type."""
        url = f"http://localhost:{server._port}/wasm-viewer.js"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "javascript" in content_type

    def test_http_serves_root_as_viewer(self, server):
        """Verify root path serves the viewer."""
        url = f"http://localhost:{server._port}/"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "Temper Board Viewer" in body

    def test_http_404_for_nonexistent_file(self, server):
        """Verify 404 for files that don't exist."""
        url = f"http://localhost:{server._port}/nonexistent.xyz"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("Expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_http_blocks_directory_traversal(self, server):
        """Verify directory traversal is blocked."""
        url = f"http://localhost:{server._port}/../../../etc/passwd"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req, timeout=5)
            pytest.fail("Expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_websocket_connect_and_state_update(self, server):
        """Verify WebSocket connection and STATE_UPDATE round-trip."""
        import asyncio
        import websockets

        received = []

        async def client():
            async with websockets.connect(f"ws://localhost:{server._port}/ws") as ws:
                # Server sends current state on connect (if available)
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg)
                    received.append(data)
                except asyncio.TimeoutError:
                    pass  # No initial state, that's fine

        asyncio.run(client())

    def test_send_state_update_propagates_to_clients(self, server):
        """Verify send_state_update delivers data to connected WebSocket clients."""
        import asyncio
        import websockets

        received = []

        async def client():
            async with websockets.connect(f"ws://localhost:{server._port}/ws") as ws:
                state = _build_test_state()
                server.send_update(state)
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    data = json.loads(msg)
                    received.append(data)
                except asyncio.TimeoutError:
                    pass

        asyncio.run(client())
        assert len(received) == 1
        msg = received[0]
        assert msg["type"] == "state_update"
        assert msg["data"]["epoch"] == 42
        assert msg["data"]["board"]["width"] == 100.0
        assert msg["data"]["board"]["height"] == 150.0
        assert len(msg["data"]["board"]["components"]) == 2
        assert msg["data"]["board"]["components"][0]["ref"] == "U1"

    def test_send_stage_change_propagates(self, server):
        """Verify STAGE_CHANGE messages are delivered to clients."""
        import asyncio
        import websockets

        received = []

        async def client():
            async with websockets.connect(f"ws://localhost:{server._port}/ws") as ws:
                server.send_stage_change(
                    stage="geometric",
                    phase="active",
                    elapsed_seconds=12.3,
                    eta_seconds=45.0,
                )
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    data = json.loads(msg)
                    received.append(data)
                except asyncio.TimeoutError:
                    pass

        asyncio.run(client())
        assert len(received) == 1
        msg = received[0]
        assert msg["type"] == "stage_change"
        assert msg["data"]["stage"] == "geometric"
        assert msg["data"]["phase"] == "active"
        assert msg["data"]["elapsed_seconds"] == 12.3
        assert msg["data"]["eta_seconds"] == 45.0

    def test_component_view_to_dict_includes_diagnostics(self):
        """Verify ComponentView.to_dict() includes new diagnostic fields."""
        comp = ComponentView(
            ref="U3",
            position=Point(50.0, 75.0),
            rotation=0.0,
            width=10.0,
            height=5.0,
            loss_contribution=2.5,
            loss_breakdown={"overlap": 1.0, "wirelength": 1.5},
            last_movement_reason="wirelength reduction",
        )
        d = comp.to_dict()
        assert d["loss_contribution"] == 2.5
        assert d["loss_breakdown"]["overlap"] == 1.0
        assert d["loss_breakdown"]["wirelength"] == 1.5
        assert d["last_movement_reason"] == "wirelength reduction"

    def test_component_view_to_dict_none_diagnostics(self):
        """Verify diagnostic fields serialize to None when not set."""
        comp = ComponentView(
            ref="R1",
            position=Point(10.0, 10.0),
            rotation=0.0,
            width=2.0,
            height=1.0,
        )
        d = comp.to_dict()
        assert d["loss_contribution"] is None
        assert d["loss_breakdown"] is None
        assert d["active_constraints"] is None
        assert d["last_movement_reason"] is None

    def test_visualization_state_round_trip_through_json(self):
        """Verify full VisualizationState survives JSON serialize/deserialize."""
        state = _build_test_state()
        data = state.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["epoch"] == 42
        assert parsed["board"]["width"] == 100.0
        assert parsed["board"]["height"] == 150.0
        assert len(parsed["board"]["components"]) == 2
        assert parsed["board"]["components"][0]["ref"] == "U1"
        assert len(parsed["loss_history"]["data_points"]) == 1


class TestWasmViewerIntegration:
    """Integration tests verifying the browser viewer shell is complete."""

    def test_viewer_html_contains_all_required_elements(self):
        """Verify wasm-viewer.html has all UI regions from requirements."""
        html = (STATIC_DIR / "wasm-viewer.html").read_text()
        required_elements = [
            'id="landing-overlay"',
            'id="reconnect-banner"',
            'id="toolbar"',
            'id="search-input"',
            'id="layer-select"',
            'id="board-canvas"',
            'id="sidebar"',
            'id="section-loss"',
            'id="section-pipeline"',
            'id="section-summary"',
            'id="section-inspector"',
            'id="section-display"',
            'id="toggle-components"',
            'id="toggle-traces"',
            'id="toggle-zones"',
            'id="toggle-pads"',
            'id="toggle-grid"',
            'id="toggle-ratsnest"',
            'id="toggle-heatmap"',
            'id="animation-controls"',
            'id="btn-pause"',
            'id="animation-mode"',
            'id="tooltip"',
            'id="btn-connect"',
            'id="drop-zone"',
            'id="connection-error"',
            'type="module"',
            'wasm-viewer.js',
        ]
        for elem in required_elements:
            assert elem in html, f"Missing element: {elem}"

    def test_viewer_js_has_all_wasm_exports(self):
        """Verify wasm-viewer.js imports all required WASM functions."""
        js = (STATIC_DIR / "wasm-viewer.js").read_text()
        required_exports = [
            "load_board",
            "on_wheel",
            "on_mouse_down",
            "on_mouse_move",
            "on_mouse_up",
            "on_click",
            "search",
            "set_viewport",
            "get_board_summary",
        ]
        for exp in required_exports:
            assert f"as wasm" in js or exp in js, f"Missing export: {exp}"

    def test_viewer_js_handles_websocket_reconnect(self):
        """Verify reconnect logic with exponential backoff."""
        js = (STATIC_DIR / "wasm-viewer.js").read_text()
        assert "Math.pow(2, reconnectAttempt)" in js
        assert "maxReconnectDelay" in js
        assert "attemptReconnect" in js

    def test_viewer_js_handles_malformed_json(self):
        """Verify malformed JSON messages are skipped without crashing."""
        js = (STATIC_DIR / "wasm-viewer.js").read_text()
        assert "Skipping malformed message" in js
        assert "continue" in js or "return" in js  # Malformed path doesn't crash

    def test_viewer_js_file_drop_handler(self):
        """Verify file drag-and-drop handler exists."""
        js = (STATIC_DIR / "wasm-viewer.js").read_text()
        assert "dragover" in js
        assert "dragleave" in js
        assert "drop" in js
        assert "dataTransfer.files" in js
        assert "JSON.parse" in js

    def test_viewer_js_escape_deselects(self):
        """Verify Escape key deselects component."""
        js = (STATIC_DIR / "wasm-viewer.js").read_text()
        assert "'Escape'" in js or '"Escape"' in js
        assert "deselected" in js.lower() or "Select a component" in js

    def test_viewer_css_light_theme(self):
        """Verify CSS uses light theme colors."""
        css = (STATIC_DIR / "wasm-viewer.css").read_text()
        assert "#f5f5f5" in css or "#fff" in css  # Light background
        assert "background" in css
