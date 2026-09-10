"""Real-process controls for the persistent ordinary-Python workspace."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import buck_host
import qualify_buck
import workspace


class FakeSession:
    deadline = time.monotonic() + 1200
    revision = "0" * 64
    actions = 0
    sequence = 0

    def __init__(self) -> None:
        self.deadline = time.monotonic() + 1200
        self.revision = "0" * 64
        self.actions = 0
        self.sequence = 0
        self.terminal_error = None
        self.calls: list[tuple[str, dict]] = []

    def _rust_policy(self, operation: str, arguments: dict) -> dict:
        if operation == "execute" and set(arguments) != {"code"}:
            raise ValueError("bad execute arguments")
        return {"status": "pass", "operation": operation}

    def call(self, operation: str, arguments: dict) -> dict:
        self.sequence += 1
        self.calls.append((operation, arguments))
        if operation in ("place", "replace_copper"):
            if self.actions >= 200:
                return {"status": "invalid", "error": "budget"}
            self.actions += 1
            self.revision = f"{self.actions:064x}"
            return {
                "status": "pass",
                "mutation_committed": True,
                "native_verdict": "pass",
                "revision": self.revision,
            }
        return {"status": "pass", "mutation_committed": False, "native_verdict": None}


class WorkspaceTests(unittest.TestCase):
    def make_workspace(
        self, *, session: FakeSession | None = None, **kwargs: object
    ) -> workspace.Workspace:
        return workspace.Workspace(session or FakeSession(), **kwargs)

    def test_persistent_variables_and_normal_python(self) -> None:
        with self.make_workspace() as worker:
            self.assertEqual(worker.execute("counter = 40")["status"], "pass")
            result = worker.execute("counter += 2\nprint(counter)")
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["stdout"], "42\n")
            proof = worker.liveness()
            self.assertTrue(proof["proof"]["same_pid"])
            self.assertTrue(proof["proof"]["same_nonce"])

    def test_independent_workers_start_with_fresh_globals_and_identity(self) -> None:
        first = self.make_workspace()
        second = self.make_workspace()
        try:
            first.execute("trial_value = 'first'")
            second.execute("assert 'trial_value' not in globals()")
            self.assertNotEqual(first.nonce, second.nonce)
            self.assertNotEqual(first.process.pid, second.process.pid)
        finally:
            first.close()
            second.close()

    def test_composed_pcb_calls_use_same_host_session(self) -> None:
        session = FakeSession()
        with self.make_workspace(session=session) as worker:
            result = worker.execute(
                "a = pcb.call('inspect', {})\n"
                "b = pcb.call('place', {'reference':'C9','x_mm':10,'y_mm':10,'angle_deg':0})\n"
                "assert a['status'] == 'pass'\n"
                "assert b['mutation_committed']\n"
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual([name for name, _ in session.calls], ["inspect", "place"])
            self.assertEqual(session.actions, 1)

    def test_real_full_buck_host_composition_across_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial = Path(tmp) / "trial"
            qualify_buck.prepare(trial, "buck-dev-a")
            session = buck_host.Session(trial, "buck-dev-a")
            try:
                with self.make_workspace(session=session) as worker:
                    first = worker.execute(
                        "seen = pcb.call('inspect', {})\nassert seen['status'] == 'pass'\ncalls = 1"
                    )
                    self.assertEqual(first["status"], "pass")
                    second = worker.execute(
                        "placed = pcb.call('place', {'reference':'C9','x_mm':10,'y_mm':10,'angle_deg':0})\n"
                        "calls += 1\n"
                        "assert placed['mutation_committed']\n"
                        "assert calls == 2"
                    )
                    self.assertEqual(second["status"], "pass")
                    self.assertEqual(session.actions, 1)
                    self.assertEqual(session.sequence, 2)
            finally:
                session.close()

    def test_skills_revision_rebinds_while_alias_remains_old(self) -> None:
        old = "def value():\n    return 'old'\n"
        new = "def value():\n    return 'new'\n"
        with self.make_workspace(skills_source=old) as worker:
            worker.execute("alias = skills.value")
            self.assertTrue(worker.apply_revision("rev2", new, "updated"))
            result = worker.execute(
                "assert alias() == 'old'\nassert skills.value() == 'new'"
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(worker.current_revision, "rev2")

    def test_old_skill_alias_tags_nested_pcb_call_with_old_revision(self) -> None:
        old = "def inspect_old():\n    return pcb.call('inspect', {})\n"
        new = "def inspect_new():\n    return pcb.call('inspect', {})\n"
        session = FakeSession()
        with self.make_workspace(session=session, skills_source=old) as worker:
            worker.execute("alias = skills.inspect_old")
            self.assertTrue(worker.apply_revision("rev2", new))
            result = worker.execute(
                "response = alias()\nassert response['status'] == 'pass'"
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(worker.revision_events[-1]["source_revision"], "base")

    def test_revision_applies_while_worker_waits_for_nested_pcb_call(self) -> None:
        session = FakeSession()
        session.actions = 19
        session.revision = f"{19:064x}"
        original_call = session.call

        def incomplete_call(*args):
            result = original_call(*args)
            result["native_verdict"] = "fail"
            return result

        session.call = incomplete_call

        def hook(actions: int, _result: dict, _deadline: float) -> dict | None:
            if actions == 20:
                return {
                    "revision": "rev20",
                    "skills_source": "def value():\n    return 'updated'\n",
                }
            return None

        with self.make_workspace(
            session=session,
            revision_hook=hook,
            skills_source="def value():\n    return 'base'\n",
        ) as worker:
            result = worker.execute(
                "response = pcb.call('place', {'reference':'C9','x_mm':10,'y_mm':10,'angle_deg':0})\n"
                "assert skills.value() == 'updated'"
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(worker.current_revision, "rev20")

    def test_denied_file_network_and_subprocess_access_are_real(self) -> None:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        try:
            with self.make_workspace() as worker:
                result = worker.execute(
                    "import socket, subprocess\n"
                    "checks = []\n"
                    f"for action in (lambda: open('/etc/hosts').read(), lambda: socket.create_connection(('127.0.0.1', {port}), 0.1), lambda: subprocess.run(['/bin/echo', 'bad'])):\n"
                    "    try:\n"
                    "        action()\n"
                    "    except Exception as error:\n"
                    "        checks.append(type(error).__name__)\n"
                    "assert len(checks) == 3, checks\n"
                    "assert checks == ['PermissionError', 'PermissionError', 'PermissionError'], checks"
                )
                self.assertEqual(result["status"], "pass", result)
        finally:
            listener.close()

    def test_scratch_is_writable_and_symlink_escape_is_denied(self) -> None:
        with self.make_workspace() as worker:
            link = worker.data / "escape"
            link.symlink_to("/etc/hosts")
            code = (
                "from pathlib import Path\n"
                "Path('scratch-ok').write_text('ok')\n"
                f"try:\n    Path({str(link)!r}).read_text()\nexcept Exception as error:\n    assert type(error).__name__ in ('PermissionError', 'OSError')\nelse:\n    raise AssertionError('symlink escaped sandbox')\n"
            )
            result = worker.execute(code)
            self.assertEqual(result["status"], "pass", result)
            self.assertEqual((worker.data / "scratch-ok").read_text(), "ok")

    def test_output_flood_and_infinite_code_are_bounded(self) -> None:
        with self.make_workspace() as worker:
            with self.assertRaises(workspace.WorkspaceError) as context:
                worker.execute("print('x' * 70000)")
            self.assertTrue(context.exception.indeterminate)
        with self.make_workspace() as worker:
            with self.assertRaises(workspace.WorkspaceError) as context:
                worker.execute("import os\nos.write(1, b'x' * 70000)")
            self.assertTrue(context.exception.indeterminate)
        with self.make_workspace() as worker:
            started = time.monotonic()
            with self.assertRaises(workspace.WorkspaceError) as context:
                worker.execute("while True: pass", timeout=0.25)
            self.assertTrue(context.exception.indeterminate)
            self.assertLess(time.monotonic() - started, 3)
            self.assertTrue(worker.indeterminate)

    def test_malformed_frames_fail_closed(self) -> None:
        reader = workspace._Frames()
        with self.assertRaises(workspace.FrameError):
            reader.feed((workspace.MAX_FRAME_BYTES + 1).to_bytes(4, "big"))
        with self.assertRaises(workspace.FrameError):
            reader.feed((3).to_bytes(4, "big") + b"[] ")

    def test_real_malformed_worker_channel_is_indeterminate(self) -> None:
        with self.make_workspace() as worker:
            assert worker.process.stdin is not None
            os.write(worker.process.stdin.fileno(), (3).to_bytes(4, "big") + b"[] ")
            with self.assertRaises(workspace.WorkspaceError) as context:
                worker.liveness(timeout=1)
            self.assertTrue(context.exception.indeterminate)

    def test_nested_calls_cannot_exceed_shared_budget(self) -> None:
        session = FakeSession()
        with self.make_workspace(session=session) as worker:
            result = worker.execute(
                "for _ in range(205):\n"
                "    pcb.call('place', {'reference':'C9','x_mm':10,'y_mm':10,'angle_deg':0})"
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(session.actions, 200)

    def test_nested_budget_uses_real_session_with_native_controlled(self) -> None:
        import buck_host
        import qualify_buck

        with tempfile.TemporaryDirectory() as tmp:
            trial = Path(tmp) / "trial"
            qualify_buck.prepare(trial, "buck-dev-a")
            session = buck_host.Session(trial, "buck-dev-a")
            contract = json.loads(qualify_buck.CONTRACT.read_text())
            measurement = {
                "protected_sha256": contract["variants"][0]["protected_sha256"]
            }
            try:
                with (
                    patch.object(session, "_native", return_value=measurement),
                    patch.object(
                        session,
                        "_check_stage",
                        return_value={
                            "status": "pass",
                            "measurement": measurement,
                            "drc": {},
                            "rust": {"status": "pass"},
                        },
                    ),
                    self.make_workspace(session=session) as worker,
                ):
                    result = worker.execute(
                        "for _ in range(205):\n"
                        "    pcb.call('place', {'reference':'C9','x_mm':10,'y_mm':10,'angle_deg':0})"
                    )
                    self.assertEqual(result["status"], "pass")
                    self.assertEqual(session.actions, buck_host.MAX_ACTIONS)
            finally:
                session.close()

    def test_unsolicited_pong_cannot_complete_execute(self):
        with self.make_workspace() as worker:
            code = "g = pcb.call.__globals__\ng['write_all'](pcb._fd, g['encode_frame']({'kind':'pong','nonce':pcb._nonce,'pid':pcb._pid,'cell_seq':1}))"
            with self.assertRaises(workspace.WorkspaceError):
                worker.execute(code)
            self.assertIsNotNone(worker.process.poll())
            self.assertTrue(worker.indeterminate)

    def test_revision_timeout_kills_worker_and_keeps_old_identity(self):
        with self.make_workspace() as worker:
            with self.assertRaises(workspace.WorkspaceError):
                worker.apply_revision(
                    "broken", "while True: pass", deadline=time.monotonic() + 0.1
                )
            self.assertIsNotNone(worker.process.poll())
            self.assertTrue(worker.indeterminate)
            self.assertEqual(worker.current_revision, "base")

    def test_completed_construction_does_not_refine(self):
        session = FakeSession()
        session.actions = 19
        seen = []
        with self.make_workspace(
            session=session, revision_hook=lambda *args: seen.append(args)
        ) as worker:
            worker.execute("pcb.call('place', {})")
            self.assertEqual(seen, [])

    def test_fresh_liveness_challenges_and_strict_frames(self):
        with self.make_workspace() as worker:
            worker.execute("counter = 42")
            first, second = worker.liveness(), worker.liveness()
            self.assertNotEqual(first["challenge"], second["challenge"])
            self.assertEqual(first["proof"]["host_ack"], worker._host_ack())
        for payload in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(workspace.FrameError):
                workspace._Frames().feed(len(payload).to_bytes(4, "big") + payload)

    def test_capability_receipt_requires_actual_canaries(self):
        with self.make_workspace() as worker:
            self.assertFalse(worker.capability_receipt()["qualified"])
            receipt = worker.qualify_denials()
            self.assertTrue(receipt["qualified"])
            self.assertTrue(receipt["denial_probes"]["outside_write"]["denied"])
            self.assertEqual(len(receipt["python_sha256"]), 64)
            self.assertEqual(worker.execute("print(6 * 7)")["stdout"], "42\n")


if __name__ == "__main__":
    unittest.main()
