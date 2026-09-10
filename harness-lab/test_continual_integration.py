"""Real local controls for the parent-owned MCP bridge and U12 manager seam."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from continual_host import REFINER_TOOLS, BridgeOwner, BuckBridge, RefinerBridge


class FakeManager:
    def __init__(self) -> None:
        self.observed: list[tuple[str, dict, dict]] = []

    def observe(self, operation: str, arguments: dict, result: dict) -> None:
        self.observed.append((operation, arguments, result))


class FakeWorkspace:
    def execute(self, code: str) -> dict:
        return {"status": "pass", "stdout": code}


class FakeSession:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or Path(
            tempfile.mkdtemp(prefix="temper-fake-session-")
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        self.deadline = 1e12
        self.actions = 0
        self.revision = "a" * 64
        self.calls: list[tuple[str, dict]] = []

    def _rust_policy(self, name: str, arguments: dict) -> dict:
        if name == "execute" and set(arguments) != {"code"}:
            raise ValueError("invalid execute arguments")
        return {"status": "pass"}

    def call(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        return {"status": "pass", "operation": name}


class FakeRevisionWorkspace:
    def __init__(self) -> None:
        self.applied: list[str] = []

    def apply_revision(
        self, revision: str, skills: str, notes: str, *, deadline: float
    ) -> bool:
        del skills, notes, deadline
        self.applied.append(revision)
        return True


class ContinualBridgeTests(unittest.TestCase):
    def test_owner_survives_two_proxy_connections_and_preserves_manager(self) -> None:
        manager = FakeManager()
        session = FakeSession()
        bridge = BuckBridge(manager, FakeWorkspace(), session)
        with tempfile.TemporaryDirectory() as temp:
            owner = BridgeOwner(bridge, Path(temp))
            path, token = owner.start()
            self.addCleanup(owner.close)

            def request(value: dict) -> dict:
                process = subprocess.run(
                    [
                        sys.executable,
                        "continual_host.py",
                        "--proxy",
                        str(path),
                        "--token",
                        token,
                    ],
                    input=json.dumps(value) + "\n",
                    text=True,
                    capture_output=True,
                    check=True,
                )
                return json.loads(process.stdout)

            self.assertEqual(
                request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"][
                    "tools"
                ],
                bridge.tools,
            )
            first = request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "inspect", "arguments": {}},
                }
            )
            self.assertEqual(first["result"]["isError"], False)
            second = request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "execute", "arguments": {"code": "x = 1"}},
                }
            )
            self.assertEqual(second["result"]["isError"], False)
            self.assertEqual([item[0] for item in session.calls], ["inspect"])
            self.assertEqual([item[0] for item in manager.observed], ["execute"])

    def test_preflight_inspection_is_single_use_and_authenticated(self) -> None:
        manager = FakeManager()
        session = FakeSession()
        bridge = BuckBridge(manager, FakeWorkspace(), session, inspection_only=True)
        first = bridge.call("inspect", {})
        second = bridge.call("inspect", {})
        mutation = bridge.call("place", {})
        self.assertEqual(first["status"], "pass")
        self.assertEqual(second["status"], "invalid")
        self.assertEqual(mutation["status"], "invalid")
        self.assertEqual([item[0] for item in session.calls], ["inspect"])

    def test_execute_policy_rejects_before_code_extraction(self) -> None:
        manager = FakeManager()
        session = FakeSession()
        bridge = BuckBridge(manager, FakeWorkspace(), session)
        with self.assertRaises(ValueError):
            bridge.call("execute", {"code": "x = 1", "unexpected": True})
        self.assertEqual(manager.observed, [])

    def test_refiner_uses_rust_tool_catalog_and_writes_one_provider_proposal(
        self,
    ) -> None:
        import artifacts

        self.assertEqual(REFINER_TOOLS, artifacts.judge("schema", {})["refiner_tools"])
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "proposal.json"
            bridge = RefinerBridge(destination)
            result = bridge.call(
                "update_artifacts",
                {"notes_utf8": "note", "skills_utf8": "skill"},
            )
            self.assertEqual(result["status"], "pass")
            self.assertTrue((Path(temp) / "provider-proposal.json").is_file())
            self.assertFalse(destination.is_file())
            again = bridge.call(
                "update_artifacts",
                {"notes_utf8": "other", "skills_utf8": "other"},
            )
            self.assertEqual(again["status"], "invalid")

    def test_loopback_refiner_tools_call_and_notification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bridge = RefinerBridge(Path(temp) / "manager-proposal.json")
            owner = BridgeOwner(bridge, Path(temp))
            path, token = owner.start()
            self.addCleanup(owner.close)

            def request(value: dict) -> dict:
                process = subprocess.run(
                    [
                        sys.executable,
                        "continual_host.py",
                        "--proxy",
                        path,
                        "--token",
                        token,
                    ],
                    input=json.dumps(value) + "\n",
                    text=True,
                    capture_output=True,
                    check=True,
                )
                return json.loads(process.stdout)

            listed = request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertEqual(listed["result"]["tools"], REFINER_TOOLS)
            called = request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "update_artifacts",
                        "arguments": {"notes_utf8": "n", "skills_utf8": "s"},
                    },
                }
            )
            self.assertFalse(called["result"]["isError"])
            self.assertTrue((Path(temp) / "provider-proposal.json").is_file())
            notification = subprocess.run(
                [
                    sys.executable,
                    "continual_host.py",
                    "--proxy",
                    path,
                    "--token",
                    token,
                ],
                input=json.dumps({"jsonrpc": "2.0", "method": "ping"}) + "\n",
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(notification.stdout, "")

    def test_preflight_bridge_rejects_mutation(self) -> None:
        manager = FakeManager()
        session = FakeSession()
        bridge = BuckBridge(manager, FakeWorkspace(), session, inspection_only=True)
        result = bridge.call(
            "place", {"reference": "C9", "x_mm": 1, "y_mm": 1, "angle_deg": 0}
        )
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(session.calls, [])


class U12IntegrationTests(unittest.TestCase):
    def test_manager_records_native_pair_and_applies_bounded_revision(self) -> None:
        import artifacts
        import refinement

        with tempfile.TemporaryDirectory() as temp:
            session = FakeSession(Path(temp) / "attempt")
            store = artifacts.Store(session.directory / "artifacts")
            initial = store.base("base", "value = 'base'\n")
            workspace = FakeRevisionWorkspace()
            session.actions = 20

            def refiner(context: dict, deadline: float, destination: Path) -> dict:
                del context, deadline
                wire_path = destination / "wire.json"
                wire_path.write_text("verified local scripted provider\n")
                return {
                    "notes_utf8": "refined",
                    "skills_utf8": "value = 'refined'\n",
                    "model": artifacts.MODEL,
                    "transport": {"verified": True, "reference": "wire.json"},
                }

            manager = refinement.Manager(
                session,
                workspace,
                store,
                initial,
                "updating_base",
                "attempt-1",
                refiner,
                "instructions",
            )
            result = {
                "status": "fail",
                "mutation_committed": True,
                "native_verdict": "fail",
            }
            manager.observe(
                "place",
                {"reference": "C9", "x_mm": 1, "y_mm": 1, "angle_deg": 0},
                result,
            )
            self.assertEqual(len(manager.receipts), 1)
            self.assertEqual(manager.receipts[0]["status"], "applied")
            self.assertEqual(len(workspace.applied), 1)
            self.assertEqual(
                result["learned_revision"], manager.current["revision_sha256"]
            )


if __name__ == "__main__":
    unittest.main()
