"""Trusted parent for the persistent ordinary-Python buck workspace.

The worker is an untrusted client.  This module owns process lifecycle,
framing, deadlines, scratch staging, nonce/PID identity, and the trusted
``buck_host.Session`` used for every nested PCB operation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import selectors
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import buck_host

MAX_FRAME_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
MAX_PROTOCOL_BYTES = 64 * 1024 * 1024
MAX_EXECUTE_SECONDS = 120.0
MAX_REFINEMENT_SECONDS = 90.0
DYLD_SUPPORT_PROFILE = Path("/System/Library/Sandbox/Profiles/dyld-support.sb")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scheme_quote(path: Path) -> str:
    """Quote a filesystem path as a JSON/Scheme string for sandbox-exec."""
    return json.dumps(str(path))


class WorkspaceError(RuntimeError):
    def __init__(self, message: str, *, indeterminate: bool = False) -> None:
        super().__init__(message)
        self.indeterminate = indeterminate


class FrameError(WorkspaceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, indeterminate=True)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonfinite JSON")


class _Frames:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        self.buffer.extend(data)
        values: list[dict[str, Any]] = []
        while True:
            if len(self.buffer) < 4:
                break
            length = struct.unpack(">I", self.buffer[:4])[0]
            if length > MAX_FRAME_BYTES:
                raise FrameError("frame exceeds maximum size")
            if len(self.buffer) < 4 + length:
                break
            payload = bytes(self.buffer[4 : 4 + length])
            del self.buffer[: 4 + length]
            try:
                value = json.loads(
                    payload,
                    object_pairs_hook=_unique_object,
                    parse_constant=_invalid_constant,
                )
            except (UnicodeDecodeError, ValueError) as error:
                raise FrameError("invalid JSON frame") from error
            if not isinstance(value, dict):
                raise FrameError("frame must contain an object")
            values.append(value)
        return values


def _encode(value: dict[str, Any]) -> bytes:
    try:
        payload = json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise FrameError("frame is not finite JSON") from error
    if len(payload) > MAX_FRAME_BYTES:
        raise FrameError("frame exceeds maximum size")
    return struct.pack(">I", len(payload)) + payload


RevisionHook = Callable[[int, dict[str, Any], float], dict[str, Any] | None]


class Workspace:
    """One persistent interpreter attached to one trusted buck Session."""

    def __init__(
        self,
        session: Any,
        *,
        scratch: Path | None = None,
        profile: Path | None = None,
        python_path: Path | None = None,
        revision_hook: RevisionHook | None = None,
        skills_source: str = "",
        notes: str = "",
    ) -> None:
        self.session = session
        self.base_profile = Path(profile) if profile is not None else None
        self.python_path = python_path or self._resolve_python()
        if self.base_profile is not None and not self.base_profile.is_file():
            raise WorkspaceError(f"sandbox profile unavailable: {self.base_profile}")
        self.scratch = (
            scratch or Path(tempfile.mkdtemp(prefix="temper-python-"))
        ).resolve()
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.data = self.scratch / "data"
        self.data.mkdir(exist_ok=True)
        self.bootstrap = self.scratch / "workspace_worker.py"
        source_path = Path(__file__).with_name("workspace_worker.py")
        self.bootstrap.write_bytes(source_path.read_bytes())
        self.bootstrap.chmod(0o444)
        self.profile = self._make_profile()
        self.nonce = secrets.token_hex(16)
        self.revision_hook = revision_hook
        self.current_revision = "base"
        self._loaded_revisions = {"base"}
        self._refinement_boundaries = set()
        self.revision_events: list[dict[str, Any]] = []
        self._cell_seq = 0
        self._closed = False
        self.indeterminate = False
        self._protocol_bytes = 0
        self._control_reader = _Frames()
        self._pending_events: list[dict[str, Any]] = []
        self._stdout_reader = bytearray()
        self._denial_probes: dict[str, dict[str, Any]] = {}
        parent_fd, child_fd = os.pipe()
        os.set_inheritable(child_fd, True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TMPDIR": str(self.data),
            "PYTHONNOUSERSITE": "1",
            "TEMPER_WORKSPACE_CONTROL_FD": str(child_fd),
            "TEMPER_WORKSPACE_NONCE": self.nonce,
            "TEMPER_PYTHON_SCRATCH": str(self.data),
            "TEMPER_HOST_ACK": json.dumps(self._host_ack()),
        }
        command = [
            "/usr/bin/sandbox-exec",
            "-f",
            str(self.profile),
            str(self.python_path),
            str(self.bootstrap),
        ]
        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.data,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                pass_fds=(child_fd,),
                close_fds=True,
            )
        except OSError as error:
            os.close(parent_fd)
            os.close(child_fd)
            raise WorkspaceError(f"sandbox worker unavailable: {error}") from error
        os.close(child_fd)
        self._control_fd = parent_fd
        os.set_blocking(self._control_fd, False)
        assert self.process.stdout is not None
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            hello = self._wait_for(
                lambda value: value.get("kind") == "hello",
                min(self.session.deadline, time.monotonic() + 10.0),
            )
            self._verify_worker(hello)
            if hello.get("protocol") != 1:
                raise FrameError("unsupported workspace protocol")
        except Exception:
            self.close()
            raise
        if skills_source:
            self.apply_revision("base", skills_source, notes)

    @staticmethod
    def _resolve_python() -> Path:
        override = os.environ.get("TEMPER_PYTHON_PATH")
        if override:
            candidate = Path(override).resolve()
        else:
            candidate = Path(sys.executable).resolve()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise WorkspaceError(f"active Python runtime unavailable: {candidate}")
        return candidate

    def _make_profile(self) -> Path:
        profile = self.scratch / "worker.sb"
        if self.base_profile is not None:
            text = self.base_profile.read_text()
        else:
            if not DYLD_SUPPORT_PROFILE.is_file():
                raise WorkspaceError(
                    f"Apple dyld sandbox profile unavailable: {DYLD_SUPPORT_PROFILE}"
                )
            runtime_prefix = Path(sys.base_prefix).resolve()
            python_prefix = self.python_path.parent.parent.resolve()
            if runtime_prefix == Path("/") or python_prefix == Path("/"):
                raise WorkspaceError("Python runtime has no bounded filesystem prefix")
            if len(runtime_prefix.parts) < 4 or len(python_prefix.parts) < 4:
                raise WorkspaceError("Python runtime prefix is too broad")

            text = "\n".join(
                [
                    "(version 1)",
                    "(deny default)",
                    f"(import {_scheme_quote(DYLD_SUPPORT_PROFILE)})",
                    f"(allow process-exec (literal {_scheme_quote(self.python_path)}))",
                    f"(allow process-exec (subpath {_scheme_quote(python_prefix)}))",
                    f"(allow file-read* file-map-executable (subpath {_scheme_quote(python_prefix)}))",
                    f"(allow file-read* file-map-executable (subpath {_scheme_quote(runtime_prefix)}))",
                    '(allow file-read* file-map-executable (subpath "/System/Library") (subpath "/usr/lib"))',
                    '(allow file-read-metadata (literal "/opt") (literal "/opt/homebrew") (literal "/opt/homebrew/Cellar") (literal "/usr") (literal "/System"))',
                    f"(allow file-read-metadata (subpath {_scheme_quote(python_prefix)}))",
                    f"(allow file-read-metadata (subpath {_scheme_quote(runtime_prefix)}))",
                    "(allow sysctl-read)",
                    '(allow file-read* (literal "/dev/urandom") (literal "/dev/random"))',
                    '(allow file-read* file-write-data (literal "/dev/null") (literal "/dev/zero"))',
                    '(allow file-read-data file-write-data (subpath "/dev/fd"))',
                    "(allow signal (target self))",
                ]
            )
            for path in (python_prefix, *python_prefix.parents):
                if path != Path("/") and len(path.parts) >= 4:
                    text += (
                        f"\n(allow file-read-metadata (subpath {_scheme_quote(path)}))"
                    )
        # Bootstrap is readable but immutable; only data is writable.  The
        # qualified profile retains the Apple dyld-support import from the
        # host canary and never broadens access to the repository or board.
        text += f"\n(allow file-read* (subpath {_scheme_quote(self.scratch)}))\n"
        text += f"(allow file-write* (subpath {_scheme_quote(self.data)}))\n"
        text += f"(allow file-read-metadata (subpath {_scheme_quote(self.scratch)}))\n"
        profile.write_text(text)
        profile.chmod(0o400)
        return profile

    def _send(self, value: dict[str, Any], *, deadline: float | None = None) -> None:
        if self.process.stdin is None:
            raise WorkspaceError("worker stdin is closed", indeterminate=True)
        payload = _encode(value)
        try:
            stdin_fd = self.process.stdin.fileno()
            os.set_blocking(stdin_fd, False)
            view = memoryview(payload)
            deadline = min(deadline or (time.monotonic() + 5.0), self.session.deadline)
            while view:
                try:
                    written = os.write(stdin_fd, view)
                except BlockingIOError:
                    selector = selectors.DefaultSelector()
                    selector.register(stdin_fd, selectors.EVENT_WRITE, "input")
                    selector.register(self._control_fd, selectors.EVENT_READ, "control")
                    assert self.process.stdout is not None
                    selector.register(
                        self.process.stdout.fileno(), selectors.EVENT_READ, "output"
                    )
                    try:
                        timeout = deadline - time.monotonic()
                        ready = selector.select(timeout) if timeout > 0 else []
                        if not ready:
                            raise WorkspaceError(
                                "worker input deadline exceeded", indeterminate=True
                            )
                        for key, _ in ready:
                            if key.data == "input":
                                continue
                            chunk = os.read(key.fd, 65536)
                            if not chunk:
                                continue
                            self._protocol_bytes += len(chunk)
                            if self._protocol_bytes > MAX_PROTOCOL_BYTES:
                                raise WorkspaceError(
                                    "worker protocol output exceeds 64 MiB",
                                    indeterminate=True,
                                )
                            if key.data == "control":
                                self._pending_events.extend(
                                    self._control_reader.feed(chunk)
                                )
                            else:
                                if (
                                    len(self._stdout_reader) + len(chunk)
                                    > MAX_OUTPUT_BYTES
                                ):
                                    raise WorkspaceError(
                                        "worker output exceeds 65536 bytes",
                                        indeterminate=True,
                                    )
                                self._stdout_reader.extend(chunk)
                    finally:
                        selector.close()
                    continue
                if written <= 0:
                    raise WorkspaceError(
                        "worker input made no progress", indeterminate=True
                    )
                view = view[written:]
        except (BrokenPipeError, OSError, WorkspaceError) as error:
            self._terminate("worker input pipe closed")
            if isinstance(error, WorkspaceError):
                raise
            raise WorkspaceError(
                "worker input pipe closed", indeterminate=True
            ) from error

    def _verify_worker(self, value: dict[str, Any]) -> None:
        if value.get("nonce") != self.nonce or value.get("pid") != self.process.pid:
            raise FrameError("worker identity mismatch")

    def _read_events(self, deadline: float) -> list[dict[str, Any]]:
        if self._pending_events:
            events, self._pending_events = self._pending_events, []
            return events
        selector = selectors.DefaultSelector()
        selector.register(self._control_fd, selectors.EVENT_READ, "control")
        assert self.process.stdout is not None
        selector.register(self.process.stdout.fileno(), selectors.EVENT_READ, "output")
        events: list[dict[str, Any]] = []
        try:
            while True:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    raise WorkspaceError(
                        "workspace call deadline exceeded", indeterminate=True
                    )
                ready = selector.select(timeout)
                if not ready:
                    raise WorkspaceError(
                        "workspace call deadline exceeded", indeterminate=True
                    )
                for key, _ in ready:
                    try:
                        chunk = os.read(key.fd, 65536)
                    except OSError as error:
                        raise FrameError(f"worker pipe read failed: {error}") from error
                    if not chunk:
                        raise WorkspaceError(
                            "worker pipe reached EOF", indeterminate=True
                        )
                    self._protocol_bytes += len(chunk)
                    if self._protocol_bytes > MAX_PROTOCOL_BYTES:
                        raise WorkspaceError(
                            "worker protocol output exceeds 64 MiB", indeterminate=True
                        )
                    if (
                        key.data == "output"
                        and len(self._stdout_reader) + len(chunk) > MAX_OUTPUT_BYTES
                    ):
                        raise WorkspaceError(
                            "worker output exceeds 65536 bytes", indeterminate=True
                        )
                    if key.data == "control":
                        events.extend(self._control_reader.feed(chunk))
                    else:
                        self._stdout_reader.extend(chunk)
                if events:
                    return events
        finally:
            selector.close()

    def _wait_for(
        self, predicate: Callable[[dict[str, Any]], bool], deadline: float
    ) -> dict[str, Any]:
        while True:
            events = self._read_events(deadline)
            if len(events) != 1 or not predicate(events[0]):
                raise FrameError("unexpected worker event")
            return events[0]

    def _host_ack(self) -> dict[str, Any]:
        return {
            "revision": self.session.revision,
            "actions": self.session.actions,
            "sequence": self.session.sequence,
            "remaining_actions": buck_host.MAX_ACTIONS - self.session.actions,
        }

    def _maybe_revision(
        self, result: dict[str, Any], deadline: float, cell_seq: int
    ) -> None:
        if (
            self.revision_hook is None
            or self.session.actions not in (20, 60, 100)
            or result.get("mutation_committed") is not True
            or result.get("native_verdict") != "fail"
            or self.session.actions in self._refinement_boundaries
        ):
            return
        refinement_deadline = min(deadline, time.monotonic() + MAX_REFINEMENT_SECONDS)
        if refinement_deadline <= time.monotonic():
            return
        self._refinement_boundaries.add(self.session.actions)
        proposal = self.revision_hook(self.session.actions, result, refinement_deadline)
        if proposal is None:
            return
        self.apply_revision(
            str(proposal["revision"]),
            str(proposal["skills_source"]),
            str(proposal.get("notes", "")),
            deadline=refinement_deadline,
            cell_seq=cell_seq,
        )

    def _handle_nested(
        self, value: dict[str, Any], cell_seq: int, deadline: float
    ) -> None:
        self._verify_worker(value)
        if set(value) != {
            "kind",
            "nonce",
            "pid",
            "cell_seq",
            "nested_seq",
            "source_revision",
            "operation",
            "arguments",
        }:
            raise FrameError("unexpected nested fields")
        if value.get("kind") != "pcb_call" or value.get("cell_seq") != cell_seq:
            raise FrameError("unexpected nested PCB request")
        operation = value.get("operation")
        arguments = value.get("arguments")
        if (
            type(value.get("nested_seq")) is not int
            or not isinstance(operation, str)
            or not isinstance(arguments, dict)
        ):
            raise FrameError("malformed nested PCB request")
        expected = getattr(self, "_expected_nested_seq", 0) + 1
        if value["nested_seq"] != expected:
            raise FrameError("nested call sequence mismatch")
        self._expected_nested_seq = value["nested_seq"]
        source_revision = value.get("source_revision", "working")
        if source_revision not in self._loaded_revisions | {"working"}:
            raise FrameError("nested call revision is invalid")
        self.revision_events.append(
            {
                "cell_seq": cell_seq,
                "nested_seq": value["nested_seq"],
                "source_revision": source_revision,
                "operation": operation,
            }
        )
        if operation == "execute":
            result = {
                "status": "invalid",
                "error": "execute cannot call itself recursively",
            }
        else:
            self.session._active_cell_deadline = deadline
            try:
                result = self.session.call(operation, arguments)
            finally:
                self.session._active_cell_deadline = None
            self._maybe_revision(result, deadline, cell_seq)
        self._send(
            {
                "kind": "pcb_result",
                "nonce": self.nonce,
                "pid": self.process.pid,
                "cell_seq": cell_seq,
                "nested_seq": value["nested_seq"],
                "result": result,
                "source_revision": source_revision,
                "host_ack": self._host_ack(),
            },
            deadline=deadline,
        )

    def _handle_event(
        self, value: dict[str, Any], cell_seq: int, deadline: float
    ) -> dict[str, Any] | None:
        kind = value.get("kind")
        if kind == "pcb_call":
            self._handle_nested(value, cell_seq, deadline)
            return None
        if kind == "cell_result":
            self._verify_worker(value)
            if value.get("cell_seq") != cell_seq:
                raise FrameError("cell sequence mismatch")
            host_ack = value.get("host_ack")
            if host_ack != self._host_ack():
                raise FrameError("host acknowledgement mismatch")
            if value.get("revision") != self.current_revision:
                raise FrameError("worker revision acknowledgement mismatch")
            if value.get("status") not in {"pass", "error"}:
                raise FrameError("invalid cell outcome")
            if len(_encode(value)) + len(self._stdout_reader) > MAX_OUTPUT_BYTES:
                raise FrameError("returned output exceeds 65536 bytes")
            if self._stdout_reader:
                value["raw_output"] = bytes(self._stdout_reader).decode(
                    "utf-8", errors="replace"
                )
            return value
        if kind == "fatal":
            self._verify_worker(value)
            raise WorkspaceError(
                value.get("error", "worker fatal error"), indeterminate=True
            )
        raise FrameError("unexpected worker event")

    def execute(
        self, code: str, *, timeout: float = MAX_EXECUTE_SECONDS
    ) -> dict[str, Any]:
        if self._closed or self.indeterminate or self.process.poll() is not None:
            raise WorkspaceError(
                "workspace is closed", indeterminate=self.indeterminate
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("execute timeout must be finite and positive")
        if (
            not isinstance(code, str)
            or len(code.encode("utf-8")) > buck_host.MAX_EXECUTE_BYTES
        ):
            raise ValueError("code must be UTF-8 and at most 65536 bytes")
        # Rust remains the authority for execute argument shape and byte size.
        self.session._rust_policy("execute", {"code": code})
        self._cell_seq += 1
        cell_seq = self._cell_seq
        self._expected_nested_seq = 0
        cell_deadline = min(
            time.monotonic() + min(float(timeout), MAX_EXECUTE_SECONDS),
            self.session.deadline,
        )
        self._protocol_bytes = 0
        self._stdout_reader.clear()
        self._send(
            {
                "kind": "execute",
                "nonce": self.nonce,
                "pid": self.process.pid,
                "cell_seq": cell_seq,
                "code": code,
                "host_ack": self._host_ack(),
            },
            deadline=cell_deadline,
        )
        try:
            while True:
                events = self._read_events(cell_deadline)
                for index, value in enumerate(events):
                    result = self._handle_event(value, cell_seq, cell_deadline)
                    if result is not None:
                        if index != len(events) - 1:
                            raise FrameError("unsolicited events after cell result")
                        return result
        except WorkspaceError as error:
            if error.indeterminate:
                self.indeterminate = True
                self._terminate(str(error))
            raise

    def apply_revision(
        self,
        revision: str,
        skills_source: str,
        notes: str = "",
        *,
        deadline: float | None = None,
        cell_seq: int | None = None,
    ) -> bool:
        if (
            not revision
            or len(skills_source.encode("utf-8")) > buck_host.MAX_EXECUTE_BYTES
        ):
            raise ValueError("invalid revision source")
        if len(notes.encode("utf-8")) > buck_host.MAX_EXECUTE_BYTES:
            raise ValueError("notes exceed maximum size")
        if (
            len(skills_source.encode("utf-8")) + len(notes.encode("utf-8"))
            > buck_host.MAX_EXECUTE_BYTES
        ):
            raise ValueError("skills source and notes exceed maximum combined size")
        payload = {
            "kind": "apply_revision",
            "nonce": self.nonce,
            "pid": self.process.pid,
            "cell_seq": self._cell_seq if cell_seq is None else cell_seq,
            "revision": revision,
            "skills_source": skills_source,
            "notes": notes,
        }
        until = min(
            deadline or (time.monotonic() + MAX_REFINEMENT_SECONDS),
            self.session.deadline,
        )
        try:
            self._send(payload, deadline=until)
            value = self._wait_for(
                lambda event: event.get("kind")
                in {"revision_applied", "revision_error"},
                until,
            )
            self._verify_worker(value)
            if (
                value.get("revision") != revision
                or value.get("cell_seq") != payload["cell_seq"]
            ):
                raise FrameError("revision acknowledgement mismatch")
            if value["kind"] == "revision_error":
                return False
            self.current_revision = revision
            self._loaded_revisions.add(revision)
            return True
        except WorkspaceError as error:
            self._terminate(str(error))
            raise

    def liveness(self, *, timeout: float = 2.0) -> dict[str, Any]:
        challenge = secrets.token_hex(16)
        deadline = min(self.session.deadline, time.monotonic() + min(timeout, 2.0))
        try:
            if self.process.poll() is not None or self.indeterminate:
                raise FrameError("worker is no longer alive")
            self._send(
                {
                    "kind": "ping",
                    "nonce": self.nonce,
                    "pid": self.process.pid,
                    "cell_seq": self._cell_seq,
                    "challenge": challenge,
                },
                deadline=deadline,
            )
            value = self._wait_for(lambda item: item.get("kind") == "pong", deadline)
            self._verify_worker(value)
            if (
                value.get("cell_seq") != self._cell_seq
                or value.get("challenge") != challenge
            ):
                raise FrameError("liveness challenge or sequence mismatch")
            if (
                value.get("host_ack") != self._host_ack()
                or value.get("revision") != self.current_revision
            ):
                raise FrameError("worker state acknowledgement is stale")
            value["proof"] = {
                "same_pid": True,
                "same_nonce": True,
                "host_ack": self._host_ack(),
                "revision": self.current_revision,
                "deadline": self.session.deadline,
            }
            return value
        except WorkspaceError as error:
            self._terminate(str(error))
            raise

    def qualify_denials(self) -> dict[str, Any]:
        """Run trusted canaries in this actual worker before supplying model code."""
        with tempfile.TemporaryDirectory(prefix="temper-denial-canary-") as tmp:
            canary = Path(tmp) / "private.txt"
            canary.write_text("unchanged")
            board = getattr(self.session, "board", None)
            if board is not None:
                board = Path(board)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                port = listener.getsockname()[1]
                source = "def _sandbox_probe():\n    import socket, subprocess\n"
                actions = [
                    f"lambda: open({str(canary)!r}).read()",
                    f"lambda: open({str(canary)!r}, 'w').write('changed')",
                    f"lambda: socket.create_connection(('127.0.0.1', {port}), 0.2)",
                    "lambda: subprocess.run(['/bin/echo', 'forbidden'])",
                    f"lambda: open({str(self.bootstrap)!r}, 'w').write('changed')",
                    f"lambda: open({str(Path(__file__).resolve())!r}).read()",
                ]
                if board is not None:
                    actions.append(f"lambda: open({str(board)!r}).read()")
                source += "    for action in (" + ",".join(actions) + ",):\n"
                source += "        try: action()\n        except PermissionError: pass\n        else: raise AssertionError('sandbox permitted a forbidden operation')\n"
                source += "_sandbox_probe()\ndel _sandbox_probe\n"
                result = self.execute(source, timeout=5)
                if result.get("status") != "pass" or canary.read_text() != "unchanged":
                    self._terminate("sandbox denial qualification failed")
                    raise WorkspaceError(
                        "sandbox denial qualification failed", indeterminate=True
                    )
                self._denial_probes = {
                    name: {"denied": True}
                    for name in (
                        "outside_read",
                        "outside_write",
                        "network",
                        "subprocess",
                        "bootstrap_write",
                        "repository_read",
                    )
                }
                if board is not None:
                    self._denial_probes["board_read"] = {"denied": True}
                self._denial_probes["probe"] = {
                    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "cell_seq": self._cell_seq,
                }
        return self.capability_receipt()

    def capability_receipt(self) -> dict[str, Any]:
        """Return the runtime/profile identity and recorded boundary probes."""
        return {
            "python_path": str(self.python_path),
            "python_sha256": _sha256(self.python_path),
            "bootstrap_path": str(self.bootstrap),
            "bootstrap_sha256": _sha256(self.bootstrap),
            "profile_path": str(self.profile),
            "profile_sha256": _sha256(self.profile),
            "dyld_support_profile": str(DYLD_SUPPORT_PROFILE),
            "dyld_support_sha256": _sha256(DYLD_SUPPORT_PROFILE),
            "scratch": str(self.scratch),
            "data": str(self.data),
            "sandbox": "sandbox-exec",
            "qualified": bool(self._denial_probes) and not self.indeterminate,
            "denial_probes": dict(self._denial_probes),
        }

    def _terminate(self, reason: str) -> None:
        self.indeterminate = True
        self.session.terminal_error = reason
        if self.process.poll() is None:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            try:
                self._send(
                    {"kind": "shutdown", "nonce": self.nonce, "pid": self.process.pid}
                )
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired, WorkspaceError):
                self._terminate("workspace close")
        try:
            os.close(self._control_fd)
        except OSError:
            pass
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.stdout is not None:
            self.process.stdout.close()

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["Workspace", "WorkspaceError", "FrameError", "MAX_OUTPUT_BYTES"]
