"""Untrusted persistent Python side of the buck workspace protocol.

The parent owns the board and the operation budget.  This process only owns
ordinary Python globals and communicates with the parent through a framed
pipe.  The worker is deliberately useful without pretending that Python
language restrictions constitute a sandbox; the host launches it under the
qualified OS profile.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import struct
import sys
import types
from typing import Any

MAX_FRAME_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
MAX_CODE_BYTES = 64 * 1024


class ProtocolError(RuntimeError):
    """The peer sent an invalid or unbounded protocol message."""


class OutputLimit(ProtocolError):
    """Captured Python output exceeded the cell limit."""


def encode_frame(value: dict[str, Any]) -> bytes:
    payload = json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("frame exceeds maximum size")
    return struct.pack(">I", len(payload)) + payload


def read_frame(stream: io.BufferedIOBase) -> dict[str, Any]:
    header = stream.read(4)
    if not header:
        raise EOFError("peer closed protocol")
    if len(header) != 4:
        raise ProtocolError("truncated frame header")
    (length,) = struct.unpack(">I", header)
    if length > MAX_FRAME_BYTES:
        raise ProtocolError("frame exceeds maximum size")
    payload = stream.read(length)
    if len(payload) != length:
        raise ProtocolError("truncated frame payload")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("invalid JSON frame") from error
    if not isinstance(value, dict):
        raise ProtocolError("frame must contain an object")
    return value


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except OSError as error:
            raise ProtocolError(f"protocol write failed: {error}") from error
        if written <= 0:
            raise ProtocolError("protocol write made no progress")
        view = view[written:]


class LimitedWriter(io.TextIOBase):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self.parts: list[str] = []

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        encoded = text.encode("utf-8", errors="replace")
        if self.used + len(encoded) > self.limit:
            raise OutputLimit("cell output exceeds 65536 bytes")
        self.used += len(encoded)
        self.parts.append(text)
        return len(text)

    def getvalue(self) -> str:
        return "".join(self.parts)


class _RPCState:
    def __init__(self) -> None:
        self.cell_seq = 0
        self.nested_seq = 0
        self.last_ack: dict[str, Any] | None = json.loads(os.environ["TEMPER_HOST_ACK"])


class PCBProxy:
    def __init__(
        self,
        control_fd: int,
        nonce: str,
        pid: int,
        source_revision: str = "working",
        *,
        enabled: bool = True,
        state: _RPCState | None = None,
    ) -> None:
        self._fd = control_fd
        self._nonce = nonce
        self._pid = pid
        self._source_revision = source_revision
        self._enabled = enabled
        self._state = state or _RPCState()

    def begin_cell(self, cell_seq: int) -> None:
        self._state.cell_seq = cell_seq
        self._state.nested_seq = 0

    def call(
        self, operation: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._enabled:
            raise RuntimeError("pcb is unavailable while loading a skills revision")
        if operation == "execute":
            raise ValueError("execute cannot call itself recursively")
        if not isinstance(operation, str):
            raise TypeError("operation must be a string")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise TypeError("arguments must be an object")
        self._state.nested_seq += 1
        request = {
            "kind": "pcb_call",
            "nonce": self._nonce,
            "pid": self._pid,
            "cell_seq": self._state.cell_seq,
            "nested_seq": self._state.nested_seq,
            "source_revision": self._source_revision,
            "operation": operation,
            "arguments": arguments,
        }
        write_all(self._fd, encode_frame(request))
        while True:
            response = read_frame(sys.stdin.buffer)
            kind = response.get("kind")
            if kind == "ping":
                self._check_identity(response)
                write_all(
                    self._fd,
                    encode_frame(
                        {
                            "kind": "pong",
                            "nonce": self._nonce,
                            "pid": self._pid,
                            "cell_seq": self._state.cell_seq,
                            "nested_seq": self._state.nested_seq,
                            "host_ack": self._state.last_ack,
                        }
                    ),
                )
                continue
            if kind == "apply_revision":
                self._check_identity(response)
                try:
                    _apply_revision(response)
                except Exception as error:
                    write_all(
                        self._fd,
                        encode_frame(
                            {
                                "kind": "revision_error",
                                "nonce": self._nonce,
                                "pid": self._pid,
                                "cell_seq": self._state.cell_seq,
                                "revision": response.get("revision"),
                                "error": f"{type(error).__name__}: {error}",
                            }
                        ),
                    )
                else:
                    write_all(
                        self._fd,
                        encode_frame(
                            {
                                "kind": "revision_applied",
                                "nonce": self._nonce,
                                "pid": self._pid,
                                "cell_seq": self._state.cell_seq,
                                "revision": response.get("revision"),
                            }
                        ),
                    )
                continue
            if kind != "pcb_result":
                raise ProtocolError("unexpected message while awaiting PCB result")
            self._check_identity(response)
            if (
                response.get("cell_seq") != self._state.cell_seq
                or response.get("nested_seq") != self._state.nested_seq
            ):
                raise ProtocolError("PCB result sequence mismatch")
            self._state.last_ack = response.get("host_ack")
            return response.get("result", response)

    def _check_identity(self, value: dict[str, Any]) -> None:
        if value.get("nonce") != self._nonce or value.get("pid") != self._pid:
            raise ProtocolError("worker identity mismatch")


_CONTROL_FD = int(os.environ["TEMPER_WORKSPACE_CONTROL_FD"])
_NONCE = os.environ["TEMPER_WORKSPACE_NONCE"]
_PID = os.getpid()
_BASE_GLOBALS: dict[str, Any] = {
    "__name__": "__temper_workspace__",
    "__package__": None,
}
_SKILLS = types.ModuleType("skills_revision_base")
_SKILLS.revision = "base"
_SKILLS.notes = ""
_BASE_GLOBALS["skills"] = _SKILLS
_PCB = PCBProxy(_CONTROL_FD, _NONCE, _PID)
_BASE_GLOBALS["pcb"] = _PCB


def _check_identity(value: dict[str, Any]) -> None:
    if value.get("nonce") != _NONCE or value.get("pid") != _PID:
        raise ProtocolError("worker identity mismatch")


def _apply_revision(value: dict[str, Any]) -> None:
    revision = value.get("revision")
    source = value.get("skills_source")
    notes = value.get("notes", "")
    if not isinstance(revision, str) or not revision:
        raise ProtocolError("revision identity is required")
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_CODE_BYTES:
        raise ProtocolError("skills source exceeds maximum size")
    if not isinstance(notes, str) or len(notes.encode("utf-8")) > MAX_CODE_BYTES:
        raise ProtocolError("notes exceeds maximum size")
    if len(source.encode("utf-8")) + len(notes.encode("utf-8")) > MAX_CODE_BYTES:
        raise ProtocolError("skills source and notes exceed maximum combined size")
    module = types.ModuleType(f"skills_revision_{revision}")
    module.revision = revision
    module.notes = notes
    module.pcb = PCBProxy(
        _CONTROL_FD, _NONCE, _PID, revision, enabled=False, state=_PCB._state
    )
    exec(
        compile(source, f"<skills:{revision}>", "exec"),
        module.__dict__,
        module.__dict__,
    )
    module.pcb = PCBProxy(_CONTROL_FD, _NONCE, _PID, revision, state=_PCB._state)
    module.revision = revision
    module.notes = notes
    _BASE_GLOBALS["skills"] = module


def _execute(value: dict[str, Any]) -> dict[str, Any]:
    _check_identity(value)
    cell_seq = value.get("cell_seq")
    code = value.get("code")
    if type(cell_seq) is not int or cell_seq <= 0:
        raise ProtocolError("invalid cell sequence")
    if not isinstance(code, str) or len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ProtocolError("code exceeds maximum size")
    _PCB.begin_cell(cell_seq)
    _PCB._state.last_ack = value["host_ack"]
    output = LimitedWriter(MAX_OUTPUT_BYTES)
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exec(
                compile(code, f"<cell:{cell_seq}>", "exec"),
                _BASE_GLOBALS,
                _BASE_GLOBALS,
            )
    except OutputLimit:
        raise
    except Exception as error:
        return {
            "kind": "cell_result",
            "nonce": _NONCE,
            "pid": _PID,
            "cell_seq": cell_seq,
            "status": "error",
            "error": f"{type(error).__name__}: {error}",
            "stdout": output.getvalue(),
            "output_bytes": output.used,
            "revision": getattr(_BASE_GLOBALS.get("skills"), "revision", "base"),
            "host_ack": _PCB._state.last_ack,
        }
    return {
        "kind": "cell_result",
        "nonce": _NONCE,
        "pid": _PID,
        "cell_seq": cell_seq,
        "status": "pass",
        "stdout": output.getvalue(),
        "output_bytes": output.used,
        "revision": getattr(_BASE_GLOBALS.get("skills"), "revision", "base"),
        "host_ack": _PCB._state.last_ack,
    }


def main() -> int:
    write_all(
        _CONTROL_FD,
        encode_frame(
            {
                "kind": "hello",
                "nonce": _NONCE,
                "pid": _PID,
                "protocol": 1,
            }
        ),
    )
    while True:
        value = read_frame(sys.stdin.buffer)
        kind = value.get("kind")
        if kind == "shutdown":
            _check_identity(value)
            return 0
        if kind == "ping":
            _check_identity(value)
            write_all(
                _CONTROL_FD,
                encode_frame(
                    {
                        "kind": "pong",
                        "nonce": _NONCE,
                        "pid": _PID,
                        "cell_seq": _PCB._state.cell_seq,
                        "challenge": value.get("challenge"),
                        "revision": _BASE_GLOBALS["skills"].revision,
                        "host_ack": _PCB._state.last_ack,
                    }
                ),
            )
            continue
        if kind == "apply_revision":
            _check_identity(value)
            try:
                _apply_revision(value)
            except Exception as error:
                write_all(
                    _CONTROL_FD,
                    encode_frame(
                        {
                            "kind": "revision_error",
                            "nonce": _NONCE,
                            "pid": _PID,
                            "cell_seq": value.get("cell_seq"),
                            "revision": value.get("revision"),
                            "error": f"{type(error).__name__}: {error}",
                        }
                    ),
                )
            else:
                write_all(
                    _CONTROL_FD,
                    encode_frame(
                        {
                            "kind": "revision_applied",
                            "nonce": _NONCE,
                            "pid": _PID,
                            "cell_seq": value.get("cell_seq"),
                            "revision": value.get("revision"),
                        }
                    ),
                )
            continue
        if kind != "execute":
            raise ProtocolError("unknown worker request")
        result = _execute(value)
        write_all(_CONTROL_FD, encode_frame(result))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, BrokenPipeError):
        raise SystemExit(2)
    except Exception as error:
        try:
            write_all(
                _CONTROL_FD,
                encode_frame(
                    {
                        "kind": "fatal",
                        "nonce": _NONCE,
                        "pid": _PID,
                        "error": f"{type(error).__name__}: {error}",
                    }
                ),
            )
        except Exception:
            pass
        raise SystemExit(2)
