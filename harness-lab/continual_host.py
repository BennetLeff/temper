"""Parent owned MCP bridge for continual buck attempts.

The OpenCode process is deliberately disposable.  This module keeps the
trusted buck session and persistent Python workspace in the runner parent and
exposes a tiny authenticated stdio proxy to OpenCode's local MCP child.  A
driver restart can therefore reconnect to the same owner without recreating
the board, interpreter, or deadline.
"""

from __future__ import annotations

import argparse
import json
import math
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import artifacts
import buck_host

MAX_FRAME_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024
BRIDGE_TIMEOUT_SECONDS = 125.0
REFINER_TOOLS = artifacts.judge("schema", {})["refiner_tools"]


class BridgeError(RuntimeError):
    """A malformed or unavailable parent bridge request."""


def _walk(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def _strict_loads(raw: bytes | str) -> dict[str, Any]:
    def duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise BridgeError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise BridgeError(f"non-finite JSON constant: {value}")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=duplicate_keys,
            parse_constant=invalid_constant,
        )
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BridgeError("invalid JSON frame") from error
    if not isinstance(value, dict):
        raise BridgeError("JSON frame must be an object")
    if any(
        isinstance(item, float) and not math.isfinite(item) for item in _walk(value)
    ):
        raise BridgeError("non-finite JSON number")
    return value


def _encode(value: dict[str, Any]) -> bytes:
    try:
        raw = (
            json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise BridgeError("response is not strict JSON") from error
    if len(raw) > MAX_FRAME_BYTES:
        raise BridgeError("bridge frame exceeds maximum size")
    return raw


class BuckBridge:
    """MCP-facing adapter around one persistent session and workspace."""

    tools = buck_host.TOOLS

    def __init__(
        self,
        manager: Any,
        workspace: Any,
        session: Any,
        *,
        inspection_only: bool = False,
    ):
        self.manager = manager
        self.workspace = workspace
        self.session = session
        self.inspection_only = inspection_only
        self._lock = threading.Lock()
        self._preflight_seen = False

    def call(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        arguments = {} if arguments is None else arguments
        with self._lock:
            if not isinstance(arguments, dict):
                return {"status": "invalid", "error": "arguments must be an object"}
            if self.inspection_only:
                if name != "inspect":
                    return {
                        "status": "invalid",
                        "error": "operation disabled during preflight",
                    }
                if self._preflight_seen:
                    return {
                        "status": "invalid",
                        "error": "preflight inspection already consumed",
                    }
                self._preflight_seen = True
            if name == "execute":
                # Validate the complete Rust command contract before touching
                # the code field.  In particular, malformed policy metadata
                # must not reach the persistent workspace executor.
                self.session._rust_policy("execute", arguments)
                result = self.workspace.execute(arguments["code"])
                # Direct execute has no Session.call wrapper to report it.
                self.manager.observe(name, arguments, result)
                return result
            # The runner installs an observing Session.call wrapper.  This
            # covers direct MCP calls and nested calls made by the worker.
            return self.session.call(name, arguments)


class RefinerBridge:
    """MCP surface for a refiner; it has exactly one non-PCB operation."""

    tools = REFINER_TOOLS

    def __init__(self, destination: Path):
        destination = destination.resolve()
        self.directory = destination.parent if destination.suffix else destination
        self.directory.mkdir(parents=True, exist_ok=True)
        self.proposal_path = self.directory / "provider-proposal.json"
        self.proposal: dict[str, str] | None = None

    def call(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if name != "update_artifacts" or not isinstance(arguments, dict):
            return {"status": "invalid", "error": "only update_artifacts is admitted"}
        if set(arguments) != {"notes_utf8", "skills_utf8"}:
            return {"status": "invalid", "error": "complete artifact pair required"}
        notes, skills = arguments["notes_utf8"], arguments["skills_utf8"]
        if not isinstance(notes, str) or not isinstance(skills, str):
            return {"status": "invalid", "error": "artifact contents must be text"}
        if self.proposal is not None:
            return {"status": "invalid", "error": "artifact pair already submitted"}
        notes_bytes = notes.encode("utf-8")
        skills_bytes = skills.encode("utf-8")
        if (
            "\x00" in notes
            or "\x00" in skills
            or len(notes_bytes) > MAX_ARTIFACT_BYTES
            or len(skills_bytes) > MAX_ARTIFACT_BYTES
            or len(notes_bytes) + len(skills_bytes) > MAX_ARTIFACT_BYTES
        ):
            return {"status": "invalid", "error": "artifact pair exceeds bounds"}
        proposal = {"notes_utf8": notes, "skills_utf8": skills}
        try:
            artifacts.write_once(self.proposal_path, proposal)
        except FileExistsError:
            return {"status": "invalid", "error": "provider proposal already exists"}
        except OSError as error:
            return {
                "status": "indeterminate",
                "error": f"proposal write failed: {error}",
            }
        self.proposal = proposal
        return {"status": "pass", "artifact_pair_recorded": True}


class BridgeOwner:
    """Authenticated loopback owner that survives OpenCode restarts.

    A loopback socket keeps this usable under macOS's restricted test runner;
    the random bearer token and loopback-only bind provide the process-local
    ownership boundary without exposing an external service.
    """

    def __init__(self, bridge: BuckBridge, directory: Path):
        self.bridge = bridge
        self.directory = directory.resolve()
        self.socket_path: str = ""
        self.token = secrets.token_hex(24)
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state = threading.Condition()
        self._closing = False
        self._active = 0
        self._paused = False
        self._connections: set[socket.socket] = set()
        self._connection_threads: list[threading.Thread] = []

    def start(self) -> tuple[str, str]:
        with self._state:
            if self._closing:
                raise BridgeError("bridge owner is closed")
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.bind(("127.0.0.1", 0))
        except Exception:
            server.close()
            raise
        server.listen(4)
        server.settimeout(0.2)
        self._server = server
        host, port = server.getsockname()
        self.socket_path = f"{host}:{port}"
        self._thread = threading.Thread(target=self._accept, name="buck-mcp-owner")
        self._thread.start()
        return self.socket_path, self.token

    def _accept(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._state:
                if self._closing:
                    conn.close()
                    break
                self._connections.add(conn)
            thread = threading.Thread(target=self._connection, args=(conn,))
            with self._state:
                self._connection_threads.append(thread)
            thread.start()

    def _connection(self, conn: socket.socket) -> None:
        try:
            with conn:
                conn.settimeout(BRIDGE_TIMEOUT_SECONDS)
                stream = conn.makefile("rwb")
                try:
                    while True:
                        raw = stream.readline(MAX_FRAME_BYTES + 1)
                        if not raw:
                            break
                        request: dict[str, Any] | None = None
                        notification = False
                        try:
                            if len(raw) > MAX_FRAME_BYTES:
                                raise BridgeError("bridge frame exceeds maximum size")
                            envelope = _strict_loads(raw)
                            if envelope.get("token") != self.token:
                                raise BridgeError("bridge identity mismatch")
                            request = envelope.get("request")
                            if not isinstance(request, dict):
                                raise BridgeError("request must be an object")
                            notification = "id" not in request
                            self._begin_call()
                            try:
                                response = self._dispatch(request)
                            finally:
                                self._end_call()
                        except Exception as error:
                            response = {
                                "jsonrpc": "2.0",
                                "id": None if request is None else request.get("id"),
                                "error": {
                                    "code": -32000,
                                    "message": f"{type(error).__name__}: {error}",
                                },
                            }
                        if notification or response is None:
                            continue
                        stream.write(_encode(response))
                        stream.flush()
                except (OSError, TimeoutError, ValueError):
                    # A client restart or owner shutdown closes the stream
                    # while a bounded read is pending.  The operation has
                    # already drained (or was never admitted), so retire the
                    # connection without leaving an orphan thread traceback.
                    pass
                finally:
                    stream.close()
        finally:
            with self._state:
                self._connections.discard(conn)
                self._state.notify_all()

    def _begin_call(self) -> None:
        with self._state:
            if self._closing or self._paused:
                raise BridgeError("bridge owner is not accepting calls")
            if self._active:
                raise BridgeError("concurrent bridge calls are not admitted")
            self._active += 1

    def _end_call(self) -> None:
        with self._state:
            self._active -= 1
            self._state.notify_all()

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "temper-buck-continual", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": self.bridge.tools}
        elif method == "tools/call":
            params = request.get("params")
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                raise BridgeError("malformed tools/call")
            value = self.bridge.call(params["name"], params.get("arguments", {}))
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(value, allow_nan=False)}
                ],
                "isError": value.get("status") in {"invalid", "indeterminate"},
            }
        elif method == "ping":
            result = {}
        else:
            if "id" not in request:
                return None
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        if "id" not in request:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def quiesce(self, deadline: float) -> None:
        """Pause tool admission and wait for the one owned operation to settle."""
        with self._state:
            self._paused = True
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BridgeError("tool operation did not settle before deadline")
                self._state.wait(timeout=remaining)

    def resume(self) -> None:
        with self._state:
            if self._closing or self._active:
                raise BridgeError("owner cannot resume")
            self._paused = False

    def close(self) -> None:
        with self._state:
            if self._closing:
                return
            self._closing = True
        self._stop.set()
        if self._server is not None:
            self._server.close()
        deadline = time.monotonic() + BRIDGE_TIMEOUT_SECONDS
        with self._state:
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._state.wait(timeout=remaining)
            connections = list(self._connections)
            threads = list(self._connection_threads)
        # Once active calls have drained, wake idle readers and let every
        # connection thread finish before returning ownership to the caller.
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
        self.socket_path = ""


def proxy(socket_path: str, token: str) -> int:
    """Forward OpenCode's stdio MCP stream to the persistent owner."""
    host, separator, port = socket_path.rpartition(":")
    if not separator or host != "127.0.0.1" or not port.isdigit():
        raise BridgeError("invalid parent bridge endpoint")
    with socket.create_connection(
        (host, int(port)), timeout=BRIDGE_TIMEOUT_SECONDS
    ) as conn:
        conn.settimeout(BRIDGE_TIMEOUT_SECONDS)
        stream = conn.makefile("rwb")
        while True:
            raw = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1)
            if not raw:
                break
            if len(raw) > MAX_FRAME_BYTES:
                raise BridgeError("bridge frame exceeds maximum size")
            request = _strict_loads(raw)
            stream.write(_encode({"token": token, "request": request}))
            stream.flush()
            if "id" not in request:
                continue
            response = stream.readline(MAX_FRAME_BYTES + 1)
            if not response:
                raise BridgeError("parent bridge closed")
            if len(response) > MAX_FRAME_BYTES:
                raise BridgeError("bridge response exceeds maximum size")
            sys.stdout.buffer.write(_encode(_strict_loads(response)))
            sys.stdout.buffer.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy")
    parser.add_argument("--token")
    args = parser.parse_args(argv)
    if args.proxy is None or not args.token:
        parser.error("--proxy and --token are required")
    return proxy(args.proxy, args.token)


if __name__ == "__main__":
    raise SystemExit(main())
