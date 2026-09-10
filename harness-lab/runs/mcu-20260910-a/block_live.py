"""P1 U4 live block construction driver (run-local apparatus).

Thin live driver modeled on ``harness-lab/run_zen_trials.py``: one isolated
OpenCode process, one declared model (``opencode/muse-spark-1.3-contributor-free``),
a local relay that retains complete wire evidence, and telemetry disabled.

Two modes:
  * ``--serve <trial>`` serves the block MCP tool catalog over stdio. This is
    the process OpenCode launches as the ``pcb`` MCP server; it owns the
    trusted :class:`run_block.BlockSession` and the sandboxed
    :class:`workspace.Workspace`, freezes + delivers the P2 memory selection
    before the first construction call, and routes ``execute`` /
    ``request_generation``.
  * ``--run <out>`` starts the relay + OpenCode and records one attempt.

The runner never backgrounds a long attempt; it is invoked in the foreground
and its ``run.jsonl``/``model.jsonl`` are polled directly.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(RUN))

import runlib  # noqa: E402
import run_block  # noqa: E402
import workspace  # noqa: E402

UPSTREAM_HOST = "opencode.ai"
UPSTREAM_PATH = "/zen/v1/responses"
CLIENT_PATH = "/responses"
IDLE_STREAMS = {"wire-*.request.json", "wire-*.status.json", "wire-*.response.txt"}

REQUEST_GENERATION_TOOL = {
    "name": "request_generation",
    "description": (
        "File a bounded operator request for a fresh source-derived board. "
        "Non-mutating: it never generates anything; the operator fulfills it "
        "out of band. Use only if the saved board is unusable at its source."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
        "additionalProperties": False,
    },
}

INSTRUCTIONS = """You are constructing one routed ESP32-S3 MCU block on a real KiCad
board. Work ONLY through the provided PCB tools. Inspect exact geometry and
current findings, choose placement coordinates and orientations yourself, commit
explicit edits, and check the saved board. Inspect the board, move the ten
movable footprints out of the reserved antenna keepout and into manufacturable
positions, then route every required connection with explicit copper. Use
`replace_copper` to set the complete copper for one admitted net (segments,
through vias, and zones). The required internal connectivity is vcc and gnd;
any other net with two or more pads is also reported as an open unless routed.
Call `check` to reload and independently evaluate the saved board. Do not invent
coordinates: derive them from inspect output. When the board passes, stop.
"""

PROMPT = "Construct the routed MCU block on the saved board. Inspect first, then place and route."


class Recorder(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, directory: Path):
        super().__init__(("127.0.0.1", 0), Relay)
        self.directory = directory
        self.sequence = 0
        self.lock = threading.Lock()
        self.deadline = time.monotonic() + 300
        self.busy = False
        self.failed = False
        self.upstream_socket = None

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("trial deadline reached")
        return remaining

    def server_close(self) -> None:
        with self.lock:
            self.failed = True
            if self.upstream_socket is not None:
                try:
                    self.upstream_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        super().server_close()


class Relay(BaseHTTPRequestHandler):
    server: Recorder

    def log_message(self, *_: object) -> None:
        pass

    def do_POST(self) -> None:
        with self.server.lock:
            self.server.sequence += 1
            prefix = self.server.directory / f"wire-{self.server.sequence:03}"
        connection = None
        admitted = False
        sent_headers = False
        started = last_chunk = time.monotonic()
        maximum_gap = 0.0
        telemetry = {"started_unix_s": time.time(), "upstream_attempted": False}
        try:
            if self.path != CLIENT_PATH:
                raise ValueError(f"unexpected endpoint {self.path}")
            self.connection.settimeout(self.server.remaining())
            length = int(self.headers.get("Content-Length", "0"))
            if not (0 < length <= 2_000_000):
                raise ValueError("invalid request size")
            body = self.rfile.read(length)
            packet = json.loads(body)
            prefix.with_suffix(".request.json").write_bytes(body)
            if packet.get("model") != runlib.MODEL:
                raise ValueError("unapproved model")
            if packet.get("store") not in (False, None):
                raise ValueError("stateless conversation required")
            with self.server.lock:
                if self.server.failed:
                    raise ValueError("trial transport already failed; retry blocked")
                if self.server.busy:
                    raise ValueError("concurrent upstream request blocked")
                self.server.remaining()
                self.server.busy = admitted = True
            connection = http.client.HTTPSConnection(
                UPSTREAM_HOST, timeout=self.server.remaining()
            )
            connection.connect()
            upstream_socket = connection.sock
            with self.server.lock:
                self.server.upstream_socket = upstream_socket
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "connection", "accept-encoding"}
            }
            headers["Accept-Encoding"] = "identity"
            upstream_socket.settimeout(self.server.remaining())
            telemetry["upstream_attempted"] = True
            connection.request("POST", UPSTREAM_PATH, body, headers)
            upstream_socket.settimeout(self.server.remaining())
            response = connection.getresponse()
            prefix.with_suffix(".status.json").write_text(
                json.dumps(
                    {
                        "status": response.status,
                        "headers": {
                            key.lower(): value
                            for key, value in response.getheaders()
                            if key.lower()
                            in {
                                "content-type",
                                "date",
                                "retry-after",
                                "x-request-id",
                                "x-ratelimit-remaining-requests",
                                "x-ratelimit-reset-requests",
                            }
                        },
                    }
                )
            )
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type"))
            self.send_header("Connection", "close")
            self.end_headers()
            sent_headers = True
            with prefix.with_suffix(".response.txt").open("wb") as evidence:
                while not response.isclosed():
                    upstream_socket.settimeout(self.server.remaining())
                    chunk = response.read1(65536)
                    now = time.monotonic()
                    maximum_gap = max(maximum_gap, now - last_chunk)
                    last_chunk = now
                    if not chunk:
                        break
                    evidence.write(chunk)
                    evidence.flush()
                    self.connection.settimeout(self.server.remaining())
                    self.wfile.write(chunk)
                    self.wfile.flush()
            if response.status != 200:
                raise ValueError(f"provider request failed with status {response.status}")
        except Exception as error:  # noqa: BLE001 - recorded, then reported
            with self.server.lock:
                self.server.failed = True
            prefix.with_suffix(".error.json").write_text(
                json.dumps({"error": f"{type(error).__name__}: {error}"})
            )
            if not sent_headers:
                self.send_error(400, "request rejected by experiment boundary")
        finally:
            if connection is not None:
                connection.close()
            telemetry.update(
                {
                    "elapsed_s": time.monotonic() - started,
                    "maximum_read_gap_s": max(
                        maximum_gap, time.monotonic() - last_chunk
                    ),
                }
            )
            prefix.with_suffix(".timing.json").write_text(json.dumps(telemetry))
            with self.server.lock:
                if admitted:
                    self.server.upstream_socket = None
                    self.server.busy = False
            self.close_connection = True


def serve(trial: Path, attempt: Path, store: Path, attempt_id: str, deadline: float) -> None:
    """Block MCP server: answer the handshake immediately, deliver memory
    before the first board call, then serve explicit board tools."""
    session = run_block.BlockSession(trial, deadline=deadline)
    worker = workspace.Workspace(session=session)
    state: dict = {"delivery": None}

    def ensure_delivery() -> None:
        if state["delivery"] is not None:
            return
        frozen = runlib.freeze_selection(store)
        delivery = runlib.deliver(
            frozen,
            worker,
            attempt_id=attempt_id,
            attempt_dir=attempt,
            store_root=store,
        )
        runlib.write_json(attempt / "delivery-proof.json", {
            "attempt_id": attempt_id,
            "model_delivery_proven": delivery["model_delivery_proven"],
            "selection_sha256": delivery["selection"]["selection_sha256"],
            "selected_ids": delivery["selection"]["selected_ids"],
            "revision_sha256": delivery["record"]["revision_sha256"],
        })
        state["delivery"] = delivery

    try:
        tools = [
            *run_block.TOOLS,
            REQUEST_GENERATION_TOOL,
        ]
        for line in sys.stdin:
            request = json.loads(line)
            if "id" not in request:
                continue
            method = request["method"]
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "temper-mcu-block", "version": "0.1.0"},
                }
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "tools/call":
                ensure_delivery()
                params = request["params"]
                name = params["name"]
                arguments = params.get("arguments", {})
                if name == "execute":
                    response = worker.execute(arguments["code"])
                    response.setdefault("status", "indeterminate")
                elif name == "request_generation":
                    path = run_block.request_generation(
                        trial, arguments["reason"], attempt_id=attempt_id
                    )
                    response = {"status": "pass", "path": str(path)}
                else:
                    response = session.call(name, arguments)
                result = {
                    "content": [{"type": "text", "text": json.dumps(response)}],
                    "isError": response.get("status") == "indeterminate",
                }
            elif method == "ping":
                result = {}
            else:
                print(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request["id"],
                            "error": {"code": -32601, "message": "Method not found"},
                        }
                    ),
                    flush=True,
                )
                continue
            print(
                json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}),
                flush=True,
            )
    finally:
        worker.close()
        session.close()


def environment(private: Path, config: dict) -> dict[str, str]:
    env = {
        key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR") if key in os.environ
    }
    for kind in ("CONFIG", "DATA", "CACHE", "STATE"):
        env[f"XDG_{kind}_HOME"] = str(private / kind.lower())
    for flag in (
        "CLAUDE_CODE",
        "EXTERNAL_SKILLS",
        "DEFAULT_PLUGINS",
        "PROJECT_CONFIG",
        "AUTOUPDATE",
        "SHARE",
        "AUTOCOMPACT",
        "LSP_DOWNLOAD",
    ):
        env["OPENCODE_DISABLE_" + flag] = "1"
    if "TEMPER_E00_JUDGE" in os.environ:
        env["TEMPER_E00_JUDGE"] = os.environ["TEMPER_E00_JUDGE"]
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
    return env


def configuration(trial: Path, attempt: Path, store: Path, port: int, deadline: float) -> dict:
    model = runlib.FULL_MODEL
    return {
        "model": model,
        "small_model": model,
        "enabled_providers": ["opencode"],
        "share": "disabled",
        "autoupdate": False,
        "snapshot": False,
        "plugin": [],
        "instructions": [],
        "compaction": {"auto": False},
        "permission": {
            "*": "deny",
            **{
                name: "allow"
                for name in [
                    *("pcb_" + tool["name"] for tool in run_block.TOOLS),
                    "pcb_request_generation",
                ]
            },
        },
        "agent": {
            "pcb": {
                "mode": "primary",
                "prompt": INSTRUCTIONS,
                "model": model,
            },
            "title": {"disable": True},
            "summary": {"disable": True},
        },
        "provider": {
            "opencode": {
                "npm": "@ai-sdk/openai",
                "options": {"baseURL": f"http://127.0.0.1:{port}", "maxRetries": 0},
                "models": {
                    runlib.MODEL: {
                        "name": "Muse Spark 1.3 Contributor Free",
                        "options": {"store": False},
                        "limit": {"context": 1048576, "output": 131072},
                        "cost": {"input": 0, "output": 0},
                    }
                },
            }
        },
        "mcp": {
            "pcb": {
                "type": "local",
                "command": [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--serve",
                    str(trial),
                    "--attempt",
                    str(attempt),
                    "--store",
                    str(store),
                    "--attempt-id",
                    attempt.name,
                    "--deadline",
                    str(deadline),
                ],
                "enabled": True,
                "timeout": 60000,
            }
        },
    }


def run(output: Path, trial: Path, attempt: Path, store: Path, budget_s: float) -> dict:
    if output.exists():
        raise ValueError(f"output {output} already exists")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "model": runlib.FULL_MODEL,
        "runner_sha256": runlib.sha256(Path(__file__).resolve()),
        "opencode_version": subprocess.check_output(
            [shutil.which("opencode"), "--version"], text=True
        ).strip(),
        "opencode_sha256": runlib.sha256(Path(shutil.which("opencode")).resolve()),
        "trial": str(trial),
        "attempt": str(attempt),
        "budget_s": budget_s,
        "transport_policy": {
            "trial_budget_s": budget_s,
            "max_concurrent_upstream_requests": 1,
            "after_incomplete_or_failed_response": "block all further upstream requests",
            "telemetry": "disabled",
            "data_use": "Zen/Meta Contributor terms approved 2026-09-09",
        },
    }
    runlib.write_json(output / "manifest.json", manifest)
    executable = shutil.which("opencode")
    if executable is None:
        raise ValueError("OpenCode unavailable")
    deadline = time.monotonic() + budget_s
    recorder = Recorder(output)
    recorder.deadline = deadline
    thread = threading.Thread(target=recorder.serve_forever, daemon=True)
    thread.start()
    returncode = 124
    events: list[dict] = []
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="temper-mcu-live-") as tmp:
            private = Path(tmp)
            empty = private / "workspace"
            empty.mkdir()
            config = configuration(
                trial, attempt, store, recorder.server_port, time.time() + budget_s
            )
            runlib.write_json(output / "config.json", config)
            command = [
                executable,
                "run",
                "--format",
                "json",
                "--agent",
                "pcb",
                "--model",
                runlib.FULL_MODEL,
                "--title",
                "Temper MCU U4",
                PROMPT,
            ]
            runlib.write_json(output / "invocation.json", command)
            with (
                (output / "model.jsonl").open("w") as out,
                (output / "model.stderr").open("w") as err,
            ):
                process = subprocess.Popen(
                    command,
                    cwd=empty,
                    env=environment(private, config),
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
                try:
                    returncode = process.wait(
                        timeout=max(0, deadline - time.monotonic())
                    )
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    returncode = 124
    finally:
        elapsed = time.monotonic() - started
        recorder.shutdown()
        recorder.server_close()
        thread.join(timeout=5)
    for line in (output / "model.jsonl").read_text().splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    requests = sorted(output.glob("wire-*.request.json"))
    statuses = []
    errors = []
    for request in requests:
        prefix = request.name.removesuffix(".request.json")
        status_path = output / f"{prefix}.status.json"
        retry_after = None
        if status_path.is_file():
            status = json.loads(status_path.read_text())
            statuses.append(status.get("status"))
            retry_after = status.get("headers", {}).get("retry-after")
        error_path = output / f"{prefix}.error.json"
        if error_path.is_file():
            errors.append(json.loads(error_path.read_text()))
        if retry_after is not None:
            errors.append({"retry_after_s": retry_after})
    tool_calls = [
        event["part"]["tool"]
        for event in events
        if event.get("type") == "tool_use" and "part" in event
    ]
    result = {
        "schema": "temper.mcu-live-attempt.v1",
        "status": "complete" if returncode == 0 and not errors else "transport_blocked"
        if errors
        else "fail",
        "returncode": returncode,
        "elapsed_s": elapsed,
        "model": runlib.FULL_MODEL,
        "wire_requests": len(requests),
        "http_statuses": statuses,
        "errors": errors,
        "tool_calls": tool_calls,
        "events": len(events),
    }
    runlib.write_json(output / "result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=Path)
    parser.add_argument("--attempt", type=Path)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--attempt-id", default="")
    parser.add_argument("--deadline", type=float, default=0.0)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--trial", type=Path)
    parser.add_argument("--budget", type=float, default=1200.0)
    args = parser.parse_args()
    if args.serve is not None:
        serve(
            args.serve.resolve(),
            args.attempt.resolve(),
            args.store.resolve(),
            args.attempt_id or args.attempt.name,
            args.deadline,
        )
        return
    if args.run is not None:
        result = run(
            args.run.resolve(),
            args.trial.resolve(),
            args.attempt.resolve(),
            args.store.resolve(),
            args.budget,
        )
        print(json.dumps(result, sort_keys=True))
        return
    parser.error("one of --serve or --run is required")


if __name__ == "__main__":
    main()
