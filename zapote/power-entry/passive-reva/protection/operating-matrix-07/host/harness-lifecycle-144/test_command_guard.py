#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD = HERE / "command_guard.py"
PYTHON = sys.executable


def run_guard(*args: str, cwd: Path | None = None, timeout: float = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run([PYTHON, str(GUARD), *args], cwd=cwd, text=True, capture_output=True, timeout=timeout)


def wait_gone(pid: int, limit: float = 1.0) -> bool:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid="], capture_output=True, text=True)
        if result.returncode not in (0, 1) or result.stderr.strip():
            raise AssertionError(f"ps failed: {result.stderr}")
        if result.returncode == 1 or not result.stdout.strip():
            return True
        time.sleep(0.02)
    return False


class GuardTests(unittest.TestCase):
    def test_known_hash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "input.txt"
            path.write_bytes(b"guard\n")
            result = run_guard("hash", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(hashlib.sha256(b"guard\n").hexdigest(), result.stdout)

    def test_fifo_hash_rejects_without_writer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fifo = Path(td) / "trace.fifo"
            os.mkfifo(fifo)
            started = time.monotonic()
            result = run_guard("hash", str(fifo), timeout=1)
            self.assertLess(time.monotonic() - started, 1)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-regular", result.stderr)

    def test_old_sha256sum_control_would_block_then_is_forcibly_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fifo = Path(td) / "trace.fifo"
            os.mkfifo(fifo)
            old = subprocess.Popen(["sha256sum", str(fifo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.15)
            self.assertIsNone(old.poll())
            old.terminate()
            old.wait(timeout=1)
            self.assertIsNotNone(old.returncode)

    def test_failing_blocked_producer_is_killed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fifo = root / "trace.fifo"
            pidfile = root / "pid"
            os.mkfifo(fifo)
            sentinel = root / "survived"
            code = "import os,time; open(%r,'w').write(str(os.getpid())); os.open(%r,os.O_WRONLY); time.sleep(30); open(%r,'w').close()" % (str(pidfile), str(fifo), str(sentinel))
            receipt = root / "receipt.json"
            result = run_guard("run", "--timeout", "0.25", "--receipt", str(receipt), "--cwd", str(root), "--", PYTHON, "-c", code)
            self.assertEqual(result.returncode, 124, result.stderr)
            data = json.loads(receipt.read_text())
            self.assertEqual(data["status"], "timeout")
            self.assertTrue(pidfile.exists())
            self.assertTrue(wait_gone(int(pidfile.read_text()), 2))
            self.assertFalse(sentinel.exists())

    def test_leader_failure_reaps_blocked_reader(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fifo = root / "trace.fifo"
            pidfile = root / "reader.pid"
            sentinel = root / "reader-survived"
            os.mkfifo(fifo)
            code = (
                "import os,time; "
                "pid=os.fork(); "
                "(os.open(%r,os.O_RDONLY), os._exit(0)) if pid==0 else "
                "(w:=os.fork()); "
                "(time.sleep(.7), open(%r,'w').close(), os._exit(0)) if w==0 else "
                "(open(%r,'w').write(str(pid)), os._exit(7))"
                % (str(fifo), str(sentinel), str(pidfile))
            )
            receipt = root / "receipt.json"
            result = run_guard("run", "--timeout", "2", "--receipt", str(receipt), "--cwd", str(root), "--", PYTHON, "-c", code)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(json.loads(receipt.read_text())["status"], "failed")
            self.assertTrue(pidfile.exists())
            self.assertTrue(wait_gone(int(pidfile.read_text()), 2))
            self.assertFalse(sentinel.exists())

    def test_timeout_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            result = run_guard("run", "--timeout", "0.1", "--receipt", str(receipt), "--cwd", td, "--", PYTHON, "-c", "import time; time.sleep(30)")
            self.assertEqual(result.returncode, 124)
            self.assertEqual(json.loads(receipt.read_text())["status"], "timeout")

    def test_normal_completion_kills_background_child(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pidfile = Path(td) / "child.pid"
            sentinel = Path(td) / "survived"
            child_code = "import time; time.sleep(1); open(%r,'w').close()" % str(sentinel)
            code = "import subprocess,time; p=subprocess.Popen([%r,'-c',%r]); open(%r,'w').write(str(p.pid)); time.sleep(.05)" % (PYTHON, child_code, str(pidfile))
            receipt = Path(td) / "receipt.json"
            result = run_guard("run", "--timeout", "2", "--receipt", str(receipt), "--cwd", td, "--", PYTHON, "-c", code)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(receipt.read_text())["status"], "completed")
            self.assertTrue(wait_gone(int(pidfile.read_text()), 2))
            self.assertFalse(sentinel.exists())

    def test_external_term_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            child = subprocess.Popen([PYTHON, str(GUARD), "run", "--timeout", "10", "--receipt", str(receipt), "--cwd", td, "--", PYTHON, "-c", "import time; time.sleep(30)"])
            time.sleep(0.15)
            child.send_signal(signal.SIGTERM)
            child.wait(timeout=2)
            self.assertEqual(child.returncode, 143)
            data = json.loads(receipt.read_text())
            self.assertEqual(data["status"], "interrupted")
            self.assertTrue(wait_gone(data["dedicated_process_group"], 2))

    def test_term_ignoring_descendant_is_killed_after_leader_exits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pidfile = root / "child.pid"
            child_code = "import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); open(%r,'w').write(str(os.getpid())); time.sleep(30)" % str(pidfile)
            leader_code = "import subprocess,sys,time,pathlib; subprocess.Popen([sys.executable,'-c',%r]); p=pathlib.Path(%r); exec('while not p.exists(): time.sleep(.01)')" % (child_code, str(pidfile))
            receipt = root / "receipt.json"
            result = run_guard("run", "--timeout", "2", "--receipt", str(receipt), "--cwd", td, "--", PYTHON, "-c", leader_code)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SIGKILL", json.loads(receipt.read_text())["termination"])
            self.assertTrue(wait_gone(int(pidfile.read_text()), 2))

    def test_infinite_timeout_refused_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = run_guard("run", "--timeout", "inf", "--receipt", str(Path(td)/"receipt.json"), "--cwd", td, "--", PYTHON, "-c", "print('must not execute')")
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("must not execute", result.stdout)

    def test_symlink_and_directory_hash_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            regular = root / "regular"
            regular.write_text("test")
            link = root / "link"
            link.symlink_to(regular)
            for path in (root, link):
                result = run_guard("hash", str(path), timeout=1)
                self.assertEqual(result.returncode, 2)

    def test_orchestration_exception_still_cleans_child_and_records_failure(self) -> None:
        spec = importlib.util.spec_from_file_location("guard_fixture", GUARD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            real_sleep = time.sleep
            calls = 0
            def fail_first_sleep(seconds: float) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("injected orchestration failure")
                real_sleep(seconds)
            with patch.object(module.time, "sleep", side_effect=fail_first_sleep):
                code = module.run_command(2, receipt, Path(td), [PYTHON, "-c", "import time; time.sleep(30)"])
            data = json.loads(receipt.read_text())
            self.assertEqual(code, 125)
            self.assertEqual(data["status"], "guard_error")
            self.assertIn("injected orchestration failure", data["error"])
            self.assertTrue(wait_gone(data["dedicated_process_group"], 2))

    def test_missing_executable_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            result = run_guard("run", "--timeout", "1", "--receipt", str(receipt), "--cwd", td, "--", str(Path(td) / "missing"))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(receipt.exists())

    def test_existing_receipt_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            receipt.write_text("evidence")
            result = run_guard("run", "--timeout", "1", "--receipt", str(receipt), "--cwd", td, "--", PYTHON, "-c", "print('bad')")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(receipt.read_text(), "evidence")


if __name__ == "__main__":
    unittest.main()
