#!/usr/bin/env python3
"""Small process/hash guard for future campaign commands.

This helper is lifecycle metadata only. It never interprets electrical data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import shutil
import stat
import subprocess
import sys
import time
import shutil
from pathlib import Path
from typing import NoReturn

_CHUNK = 1024 * 1024
_TERM_GRACE = 1.0


def _fail(message: str) -> NoReturn:
    print(f"command_guard: {message}", file=sys.stderr)
    raise SystemExit(2)


def _regular_hash(path: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot open {path}: {exc.strerror}") from exc
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"refusing non-regular file: {path}")
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, _CHUNK)
            if not block:
                return digest.hexdigest()
            digest.update(block)
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc.strerror}") from exc
    finally:
        os.close(fd)


def hash_command(paths: list[str]) -> int:
    if not paths:
        _fail("hash requires at least one file")
    for path in paths:
        try:
            print(f"{_regular_hash(path)}  {path}")
        except ValueError as exc:
            _fail(str(exc))
    return 0


def _resolve_command(command: list[str]) -> str:
    if not command:
        _fail("run requires a command after --")
    candidate = command[0]
    resolved = candidate if os.path.dirname(candidate) else shutil.which(candidate)
    if not resolved:
        _fail(f"command not found before spawn: {candidate}")
    try:
        st = os.stat(resolved)
    except OSError as exc:
        _fail(f"cannot stat command before spawn: {exc.strerror}: {resolved}")
    if not stat.S_ISREG(st.st_mode) or not os.access(resolved, os.X_OK):
        _fail(f"command is not an executable regular file: {resolved}")
    return os.path.abspath(resolved)


def _reserve_receipt(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise RuntimeError(f"receipt already exists: {path}") from exc


def _write_receipt(fd: int, receipt: dict[str, object]) -> None:
    with os.fdopen(fd, "w") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _kill_group(process: subprocess.Popen[object], term_reason: str) -> str:
    """Terminate the dedicated group, escalating after a bounded grace."""
    pgid = process.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return "leader/group already exited"
    deadline = time.monotonic() + _TERM_GRACE
    def group_exists() -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    while (process.poll() is None or group_exists()) and time.monotonic() < deadline:
        time.sleep(0.02)
    if process.poll() is None or group_exists():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return f"{term_reason}; escalated SIGKILL"
    return f"{term_reason}; SIGTERM sufficient"


def run_command(timeout: float, receipt: Path, cwd: Path, command: list[str]) -> int:
    if timeout <= 0 or not math.isfinite(timeout):
        _fail("timeout must be finite and positive")
    if not cwd.is_dir():
        _fail(f"cwd is not a directory: {cwd}")
    resolved = _resolve_command(command)
    command = [resolved, *command[1:]]
    try:
        receipt_fd = _reserve_receipt(receipt)
    except OSError as exc:
        _fail(f"cannot reserve receipt: {exc}")
    except RuntimeError as exc:
        _fail(str(exc))
    started = time.time()
    process: subprocess.Popen[object] | None = None
    status = "spawn_failed"
    returncode: int | None = None
    termination: str | None = None
    error: str | None = None
    interrupted: int | None = None

    def on_signal(signum: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = signum

    old_handlers = {sig: signal.signal(sig, on_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if interrupted is None:
            process = subprocess.Popen(command, cwd=cwd, start_new_session=True)
            deadline = time.monotonic() + timeout
            while True:
                returncode = process.poll()
                if interrupted is not None:
                    status = "interrupted"
                    break
                if returncode is not None:
                    status = "completed" if returncode == 0 else "failed"
                    break
                if time.monotonic() >= deadline:
                    status = "timeout"
                    break
                time.sleep(0.02)
        else:
            status = "interrupted"
    except Exception as exc:
        status = "spawn_failed" if process is None else "guard_error"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        # Cleanup also runs when orchestration itself raises, not just on normal
        # child exits. Keep signal handlers installed until cleanup and receipt finish.
        try:
            if process is not None:
                try:
                    termination = _kill_group(process, status)
                except Exception as exc:
                    status = "guard_error"
                    error = f"cleanup error: {exc}"
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                returncode = process.wait(timeout=2)
            if interrupted is not None:
                status = "interrupted"
            _write_receipt(receipt_fd, {
                "status": status, "returncode": returncode,
                "command": command, "resolved_command": resolved,
                "cwd": str(cwd.resolve()), "timeout_seconds": timeout,
                "started_unix": started, "ended_unix": time.time(),
                "termination": termination, "error": error,
                "interrupted_signal": interrupted,
                "dedicated_process_group": process.pid if process is not None else None,
            })
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
    if status in {"completed", "failed"}:
        code = int(returncode or 0)
        return 128 - code if code < 0 else code
    if status == "timeout":
        return 124
    if status == "interrupted":
        return 128 + int(interrupted or signal.SIGINT)
    return 127 if status == "spawn_failed" else 125


def main(argv: list[str]) -> int:
    if not argv:
        _fail("use hash FILE... or run --timeout SECONDS --receipt PATH --cwd DIR -- COMMAND...")
    if argv[0] == "hash":
        return hash_command(argv[1:])
    if argv[0] != "run":
        _fail("unknown mode")
    parser = argparse.ArgumentParser(prog="command_guard run")
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv[1:])
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run_command(args.timeout, args.receipt, args.cwd, command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
