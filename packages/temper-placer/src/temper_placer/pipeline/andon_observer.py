"""Andon Board — live pipeline station display via HTTP server + SSE."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

_LOGGER = logging.getLogger(__name__)

_ANDON_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Temper Pipeline — Andon Board</title>
<style>
:root {
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #c9d1d9; --dim: #484f58;
  --green: #3fb950; --red: #f85149; --yellow: #d29922; --cyan: #58a6ff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 24px; }
h1 { font-size: 20px; margin-bottom: 8px; }
.subtitle { color: var(--dim); font-size: 13px; margin-bottom: 24px; }
.stations { display: flex; gap: 12px; flex-wrap: wrap; }
.station { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; min-width: 160px; flex: 1; transition: border-color 0.3s; }
.station.idle { border-color: var(--border); opacity: 0.6; }
.station.active { border-color: var(--cyan); opacity: 1; }
.station.done { border-color: var(--green); opacity: 1; }
.station.error { border-color: var(--red); opacity: 1; }
.station.skip { border-color: var(--border); opacity: 0.4; text-decoration: line-through; }
.station-name { font-weight: 600; font-size: 15px; margin-bottom: 8px; }
.station-timer { font-size: 13px; color: var(--dim); }
.station-timer.running { color: var(--cyan); }
.station-metric { font-size: 12px; color: var(--dim); margin-top: 4px; }
.footer { margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 13px; color: var(--dim); }
.light { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; background: var(--dim); }
.light.green { background: var(--green); }
.light.red { background: var(--red); }
.light.yellow { background: var(--yellow); }
.light.cyan { background: var(--cyan); }
</style>
</head>
<body>
<h1>Temper Pipeline — Andon Board</h1>
<p class="subtitle" id="header">Waiting for pipeline...</p>
<div class="stations" id="stations"></div>
<div class="footer" id="footer"></div>
<script>
const LIGHTS = { idle: "", active: "cyan", done: "green", error: "red", skip: "dim" };
function render(state) {
  document.getElementById("header").textContent = state.header || "Pipeline running...";
  const container = document.getElementById("stations");
  container.innerHTML = "";
  (state.stages || []).forEach(s => {
    const div = document.createElement("div");
    div.className = "station " + (s.status || "idle");
    div.innerHTML = '<div class="station-name"><span class="light ' + (LIGHTS[s.status] || "") + '"></span>' + s.name + '</div>'
      + (s.timer ? '<div class="station-timer' + (s.status === "active" ? " running" : "") + '">' + s.timer + '</div>' : '')
      + (s.metric ? '<div class="station-metric">' + s.metric + '</div>' : '');
    container.appendChild(div);
  });
  document.getElementById("footer").textContent = state.footer || "";
}
const es = new EventSource("/events");
es.onmessage = e => render(JSON.parse(e.data));
es.onerror = () => { document.getElementById("header").textContent = "Connection lost — retrying..."; };
</script>
</body>
</html>"""


@dataclass
class AndonObserver:
    """Live Andon board observer with embedded HTTP server and SSE push.

    Parameters
    ----------
    stage_order: Ordered list of stage names from the pipeline DAG.
    port: HTTP server port (0 = auto-select a free port).
    """

    stage_order: list[str]
    port: int = 0

    _server: HTTPServer | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _state: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _clients: list[_SSEClient] = field(default_factory=list)
    _pipeline_start: float = 0.0

    def __post_init__(self) -> None:
        self._state = {"header": "Initializing...", "stages": [
            {"name": n, "status": "idle"} for n in self.stage_order
        ], "footer": ""}
        if self.port == 0:
            self.port = self._find_free_port()

    # -- ProgressObserver protocol ------------------------------------------

    def on_stage_start(self, stage_name: str, iteration: int, context: dict[str, Any]) -> None:  # noqa: ARG002
        if self._pipeline_start == 0.0:
            self._pipeline_start = time.monotonic()
        self._update_stage(stage_name, "active",
                            timer=f"Iteration {iteration}")

    def on_stage_complete(self, stage_name: str, duration_s: float, outputs: dict[str, Any]) -> None:  # noqa: ARG002
        self._update_stage(stage_name, "done", timer=f"{duration_s:.1f}s")

    def on_stage_skip(self, stage_name: str, reason: str) -> None:
        self._update_stage(stage_name, "skip", timer=reason)

    def on_stage_error(self, stage_name: str, error: Exception) -> None:
        self._update_stage(stage_name, "error", timer=str(error))
        self._update_header(f"FAILED: {stage_name} — {error}")

    def on_feedback_triggered(self, contract_name: str, from_stage: str, to_stage: str,  # noqa: ARG002, ARG002
                               attempt: int) -> None:
        self._update_footer(f"Feedback: {contract_name} (attempt {attempt})")

    def on_pipeline_complete(self, success: bool, total_duration_s: float,
                              stage_timings: dict[str, float]) -> None:
        for name, dur in stage_timings.items():
            self._update_stage(name, status=None, timer=f"{dur:.1f}s",
                               overwrite_status=False)
        status = "PASSED" if success else "FAILED"
        self._update_header(f"Pipeline {status} ({total_duration_s:.1f}s)")

    def on_epoch(self, stage_name: str, epoch: int, loss: float) -> None:
        self._update_stage(stage_name, status=None, metric=f"epoch {epoch}, loss {loss:.4f}",
                            overwrite_status=False)

    # -- state updates ------------------------------------------------------

    def _update_stage(self, name: str, status: str | None, *, timer: str = "",
                      metric: str = "", overwrite_status: bool = True) -> None:
        with self._lock:
            for s in self._state["stages"]:
                if s["name"] == name:
                    if overwrite_status and status is not None:
                        s["status"] = status
                    if timer:
                        s["timer"] = timer
                    if metric:
                        s["metric"] = metric
                    break
            self._broadcast()

    def _update_header(self, text: str) -> None:
        with self._lock:
            self._state["header"] = text
            self._broadcast()

    def _update_footer(self, text: str) -> None:
        with self._lock:
            self._state["footer"] = text
            self._broadcast()

    def _broadcast(self) -> None:
        data = json.dumps(self._state)
        dead: list[_SSEClient] = []
        for client in self._clients:
            try:
                client.write(data)
            except Exception:
                dead.append(client)
        for c in dead:
            self._clients.remove(c)

    # -- HTTP server --------------------------------------------------------

    def start(self) -> int:
        """Start the HTTP server in a background thread. Returns the port."""
        observer = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/" or self.path == "/index.html":
                    self._serve_html()
                elif self.path == "/events":
                    self._serve_sse()
                else:
                    self.send_response(404)
                    self.end_headers()

            def _serve_html(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_ANDON_HTML.encode("utf-8"))

            def _serve_sse(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                client = _SSEClient(self.wfile)
                observer._clients.append(client)
                try:
                    while True:
                        time.sleep(30)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    if client in observer._clients:
                        observer._clients.remove(client)

            def log_message(self, format, *args):
                _LOGGER.debug(format, *args)

        self._server = HTTPServer(("127.0.0.1", self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        _LOGGER.info(f"Andon board listening on http://127.0.0.1:{self.port}")
        return self.port

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


class _SSEClient:
    def __init__(self, wfile: Any) -> None:
        self._wfile = wfile

    def write(self, data: str) -> None:
        self._wfile.write(f"data: {data}\n\n".encode())
        self._wfile.flush()
