"""Memory delivery integration: selection to retained receipt (P2 U3).

Proves stored knowledge reaches the next agent's runtime path through the
actual construction runtime: the exact selected bytes are materialized
through the existing Store, loaded with ``Workspace.apply_revision``, the
retained model-input capture (not a worker load ack) proves model delivery,
checked helpers run inspect/check through real admitted operations with the
executing revision recorded, and reopening the retained task resolves the
same bytes without absolute temporary paths.

Board correctness and memory-delivery outcomes stay separate: the native
control below asserts delivery/invocation/receipt linkage and runs an
independent board check, but no assertion here converts a delivery receipt
into a board verdict. Software-control provenance remains distinct from
live learned memory (R8). Live MCU attempt delivery evidence comes at P1
U4; this unit proves the path with controls.

P2 owns this file and ``memory.py``. It calls the P1-owned ``workspace``
only through its public interface; it does not edit shared runtime files.
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

import artifacts
import buck_host
import memory
import qualify_buck
import test_memory
import workspace

ROOT = Path(__file__).parent

HELPER_SUFFIX = (
    "\n\ndef inspect_then_check():\n"
    "    findings = pcb.call('inspect', {})  # noqa: F821\n"
    "    verdict = pcb.call('check', {})  # noqa: F821\n"
    "    return {'findings': findings, 'verdict': verdict}\n"
)

FAILING_HELPER_SUFFIX = "\n\nraise RuntimeError('broken helper init')\n"


class FakeSession:
    """Local stand-in for the trusted session (mirrors P1's test shape)."""

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
        if operation in ("inspect", "check"):
            return {
                "status": "pass",
                "mutation_committed": False,
                "native_verdict": None if operation == "inspect" else "pass",
            }
        return {"status": "pass", "mutation_committed": False, "native_verdict": None}


class MemoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            memory.default_judge().is_file(),
            "memory Rust judge is not built; run `cargo build --locked` in harness-lab",
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.loaded = memory.load_catalog()
        self.base_skills = (ROOT / "skills" / "base" / "skills.py").read_text(
            encoding="utf-8"
        )

    def full_selection(self, **kwargs) -> dict:
        return memory.request_selection(
            self.loaded,
            task_capabilities=test_memory.MCU_CAPABILITIES,
            required_ids=[item["descriptor"]["id"] for item in self.loaded["entries"]],
            base_skills_bytes=len(self.base_skills.encode("utf-8")),
            **kwargs,
        )

    def run_pipeline(self, attempt_id: str) -> tuple[dict, dict, Path]:
        store = artifacts.Store(self.root / "revisions")
        selection = self.full_selection()
        record = memory.materialize_selection(
            store, self.loaded, selection, base_skills_source=self.base_skills
        )
        receipt = memory.build_receipt(
            selection=selection,
            loaded=self.loaded,
            revision_sha256=record["revision_sha256"],
            notes_sha256=record["receipt"]["notes_sha256"],
            skills_sha256=record["receipt"]["skills_sha256"],
            attempt_id=attempt_id,
        )
        path = memory.publish_receipt(self.root / attempt_id, receipt)
        return selection, receipt, path

    def test_native_control_selection_delivery_invocation_receipt_check(self):
        """Native control: selection, delivery, invocation, receipt, board check.

        A selected checked helper performs an inspect/check sequence through
        real admitted operations on a real buck fixture; the receipt records
        the executing revision; an independent host-side check re-measures
        the board outside the worker. Delivery and board outcomes stay
        separate assertions.
        """
        trial = self.root / "trial"
        qualify_buck.prepare(trial, "buck-dev-a")
        session = buck_host.Session(trial, "buck-dev-a")
        self.addCleanup(session.close)
        store = artifacts.Store(self.root / "revisions")
        selection = self.full_selection()
        helper_skills = self.base_skills + HELPER_SUFFIX
        with workspace.Workspace(session=session) as worker:
            record, receipt, capture, paths = memory.deliver_selection(
                store,
                worker,
                self.loaded,
                selection,
                base_skills_source=helper_skills,
                attempt_id="mcu-dev-a-001",
                attempt_dir=self.root / "mcu-dev-a-001",
            )
            # Delivery: the worker runs the selected revision.
            self.assertEqual(worker.current_revision, record["revision_sha256"])
            # Invocation: the checked helper nests exactly the admitted
            # inspect + check operations under the executing revision.
            result = worker.execute(
                "outcome = skills.inspect_then_check()\n"
                "assert outcome['findings']['status'] == 'pass'\n"
                "assert outcome['verdict']['status'] in ('pass', 'fail')"
            )
            self.assertEqual(result["status"], "pass", result)
            self.assertEqual(result["revision"], record["revision_sha256"])
            nested = [
                event["operation"] for event in worker.revision_events[-2:]
            ]
            self.assertEqual(nested, ["inspect", "check"])
            for event in worker.revision_events[-2:]:
                self.assertEqual(event["source_revision"], record["revision_sha256"])
            # Receipt: helper execution is attributed; delivery was captured.
            memory.record_helper_call(
                receipt,
                revision_sha256=record["revision_sha256"],
                helper="inspect_then_check",
                operations=["inspect", "check"],
                result_ref=f"worker cell_seq {worker._cell_seq}",
            )
            self.assertEqual(len(receipt["delivery"]["helper_calls"]), 1)
            call = receipt["delivery"]["helper_calls"][0]
            self.assertEqual(call["revision_sha256"], record["revision_sha256"])
            self.assertTrue(memory.model_delivery_proven(capture, record))
            # Independent board check: re-measured on the host, outside the
            # worker, without mutating the board or spending budget.
            actions_before = session.actions
            independent = session.call("check", {})
            self.assertIn(independent["status"], ("pass", "fail"))
            self.assertEqual(independent["after_sha256"], session.revision)
            self.assertEqual(independent["revision"], session.revision)
            self.assertEqual(session.actions, actions_before)
            # Retained evidence binds selection to content hashes.
            reread_receipt = json.loads(paths["receipt"].read_text())
            reread_capture = json.loads(paths["model_input"].read_text())
            self.assertEqual(
                reread_receipt["selection_sha256"], selection["selection_sha256"]
            )
            for entry_id in selection["selected_ids"]:
                content = reread_receipt["entry_content"][entry_id]["content_sha256"]
                self.assertIn(entry_id, record["notes_utf8"])
                self.assertIn(content, record["notes_utf8"])
            self.assertIn(record["notes_utf8"], reread_capture["model_notes"])

    def test_model_input_capture_proves_delivery_ack_alone_does_not(self):
        """The actual model-input capture contains selected notes (scenario 2)."""
        store = artifacts.Store(self.root / "revisions")
        selection = self.full_selection()
        record = memory.materialize_selection(
            store, self.loaded, selection, base_skills_source=self.base_skills
        )
        capture = memory.capture_model_input(
            attempt_id="mcu-dev-a-001",
            selection=selection,
            loaded=self.loaded,
            record=record,
        )
        # The capture carries the exact model-visible notes bytes.
        self.assertEqual(capture["model_notes"], record["notes_utf8"])
        for entry_id in selection["selected_ids"]:
            self.assertIn(entry_id, capture["model_notes"])
        self.assertTrue(memory.model_delivery_proven(capture, record))
        # A worker load acknowledgement alone proves nothing: a receipt with
        # acknowledged=True but no model-visible bytes fails the check.
        ack_only = memory.build_receipt(
            selection=selection,
            loaded=self.loaded,
            revision_sha256=record["revision_sha256"],
            notes_sha256=record["receipt"]["notes_sha256"],
            skills_sha256=record["receipt"]["skills_sha256"],
            attempt_id="mcu-dev-a-001",
        )
        memory.acknowledge_delivery(ack_only)
        self.assertTrue(ack_only["delivery"]["acknowledged"])
        self.assertFalse(memory.model_delivery_proven(ack_only, record))
        # Tampered bytes fail for their intended reason as well.
        tampered = dict(capture)
        tampered["model_notes"] = "replaced notes"
        self.assertFalse(memory.model_delivery_proven(tampered, record))

    def test_failed_helper_load_keeps_previous_revision(self):
        """A failing helper init retains the old revision and reports rejection."""
        store = artifacts.Store(self.root / "revisions")
        selection = self.full_selection()
        with workspace.Workspace(session=FakeSession()) as worker:
            record, _, _, _ = memory.deliver_selection(
                store,
                worker,
                self.loaded,
                selection,
                base_skills_source=self.base_skills,
                attempt_id="mcu-dev-a-001",
                attempt_dir=self.root / "mcu-dev-a-001",
            )
            active = worker.current_revision
            self.assertEqual(active, record["revision_sha256"])
            # Valid syntax but failing initialization: the Store accepts the
            # bytes (syntax check is compile-only) while the worker rejects
            # them at load time. A distinct message from the entry-point
            # rejection below keeps the two Store revisions distinct.
            broken = store.base(
                record["notes_utf8"],
                self.base_skills + FAILING_HELPER_SUFFIX,
            )
            self.assertFalse(memory.apply_to_workspace(worker, broken))
            self.assertEqual(worker.current_revision, active)
            # The P1 entry point reports the rejection instead of keeping a
            # half-loaded revision.
            with self.assertRaises(ValueError):
                memory.deliver_selection(
                    store,
                    worker,
                    self.loaded,
                    selection,
                    base_skills_source=self.base_skills
                    + "\n\nraise RuntimeError('broken helper init at entry point')\n",
                    attempt_id="mcu-dev-a-002",
                    attempt_dir=self.root / "mcu-dev-a-002",
                )
            self.assertEqual(worker.current_revision, active)
            self.assertTrue(worker.execute("print(6 * 7)")["stdout"] == "42\n")

    def test_sandbox_budget_source_and_cross_attempt_controls(self):
        """Helpers cannot escape, reset budget, mutate source, or cross reads."""
        trial = self.root / "trial"
        qualify_buck.prepare(trial, "buck-dev-a")
        context_before = (trial / "source.json").read_bytes()
        other_attempt = self.root / "other-attempt"
        other_attempt.mkdir()
        (other_attempt / "hidden.json").write_text('{"secret": true}')
        store = artifacts.Store(self.root / "revisions")
        selection = self.full_selection()
        session = FakeSession()
        with workspace.Workspace(session=session) as worker:
            record, _, _, _ = memory.deliver_selection(
                store,
                worker,
                self.loaded,
                selection,
                base_skills_source=self.base_skills,
                attempt_id="mcu-dev-a-001",
                attempt_dir=self.root / "mcu-dev-a-001",
            )
            # Sandbox escape is denied inside the memory revision: absolute
            # repository reads, network, and subprocess fail closed.
            result = worker.execute(
                "import socket, subprocess\n"
                "checks = []\n"
                f"for action in (lambda: open({str(ROOT / 'memory' / 'catalog.json')!r}).read(),"
                " lambda: socket.create_connection(('127.0.0.1', 9), 0.2),"
                " lambda: subprocess.run(['/bin/echo', 'bad'])):\n"
                "    try:\n"
                "        action()\n"
                "    except Exception as error:\n"
                "        checks.append(type(error).__name__)\n"
                "assert checks == ['PermissionError', 'PermissionError', 'PermissionError'], checks"
            )
            self.assertEqual(result["status"], "pass", result)
            # Cross-attempt hidden artifacts are unreadable by absolute path.
            hidden = other_attempt / "hidden.json"
            result = worker.execute(
                "from pathlib import Path\n"
                f"try:\n    Path({str(hidden)!r}).read_text()\n"
                "except Exception as error:\n"
                "    assert type(error).__name__ in ('PermissionError', 'OSError')\n"
                "else:\n"
                "    raise AssertionError('cross-attempt read escaped the sandbox')"
            )
            self.assertEqual(result["status"], "pass", result)
            # The budget cannot be reset from a helper: 205 admitted calls
            # commit at most 200 actions and further calls are rejected.
            result = worker.execute(
                "for _ in range(205):\n"
                "    pcb.call('place', {'reference':'C9','x_mm':10,'y_mm':10,'angle_deg':0})"
            )
            self.assertEqual(result["status"], "pass", result)
            self.assertEqual(session.actions, 200)
            # A rejected call spends nothing and changes no revision.
            rejected = session.call("place", {"reference": "C9"})
            self.assertEqual(rejected["status"], "invalid")
            self.assertEqual(session.actions, 200)
            # Host-side inspection gate: the same escapes fail in the adapter
            # even before reaching the sandbox.
            with self.assertRaises(ValueError):
                memory.inspect_evidence(self.root, "/etc/hosts")
            with self.assertRaises(ValueError):
                memory.inspect_evidence(self.root, "../escape.json")
            with self.assertRaises(ValueError):
                memory.inspect_evidence(self.root, "other-attempt/hidden.json".replace("/", "\\"))
            link = self.root / "link.json"
            try:
                link.symlink_to(other_attempt / "hidden.json")
            except OSError:
                pass
            else:
                with self.assertRaises(ValueError):
                    memory.inspect_evidence(self.root, "link.json")
            allowed = memory.inspect_evidence(
                self.root, "mcu-dev-a-001/memory-selection.json"
            )
            self.assertEqual(json.loads(allowed)["delivery"]["attempt_id"], "mcu-dev-a-001")
            _ = record
        # The protected task source is byte-identical after helper execution.
        self.assertEqual((trial / "source.json").read_bytes(), context_before)

    def test_reopen_resolves_same_bytes_without_absolute_paths(self):
        """A retained task reopens portably: no /tmp paths in the receipt."""
        _, receipt, _ = self.run_pipeline("mcu-dev-a-001")
        serialized = json.dumps(receipt)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("/tmp/", serialized)
        self.assertNotIn("/private/", serialized)
        # Reread from a different current directory still verifies, and the
        # catalog re-resolves the same entry bytes by content hash.
        reread = json.loads(
            (self.root / "mcu-dev-a-001" / "memory-selection.json").read_text()
        )
        self.assertEqual(reread["selection_sha256"], receipt["selection_sha256"])
        reopened = memory.load_catalog()
        for entry_id in reread["selected_ids"]:
            first = next(
                item for item in self.loaded["entries"]
                if item["descriptor"]["id"] == entry_id
            )
            second = next(
                item for item in reopened["entries"]
                if item["descriptor"]["id"] == entry_id
            )
            self.assertEqual(
                second["content_sha256"], first["content_sha256"]
            )
            self.assertEqual(
                second["content_sha256"],
                reread["entry_content"][entry_id]["content_sha256"],
            )

    def test_board_correctness_outcome_stays_separate(self):
        """The delivery receipt carries no board verdict."""
        _, receipt, _ = self.run_pipeline("mcu-dev-a-001")
        flat = json.dumps(receipt).lower()
        for claim in ("board_sha256", "native_verdict", "placement_only"):
            self.assertNotIn(claim, flat)

    def test_failed_helper_proposal_keeps_previous_revision(self):
        """A rejected helper proposal produces no child revision (policy gate).

        Complements the runtime load failure above: the promotion policy
        rejects a helper that failed its behavioral test, so nothing new
        becomes selectable and the previously materialized revision stays
        the active one.
        """
        store = artifacts.Store(self.root / "revisions")
        selection = self.full_selection()
        before = memory.materialize_selection(
            store, self.loaded, selection, base_skills_source=self.base_skills
        )
        verdict = memory.review_proposal(
            proposal_id="helper-1",
            claim_kind="procedure",
            basis="complete-valid-passing-attempt",
            evidence_independent=True,
            helper_test="fail",
            source_artifact_match=False,
        )
        self.assertEqual(verdict["outcome"], "rejected")
        self.assertEqual(store.read(before["revision_sha256"]), before)


if __name__ == "__main__":
    unittest.main()
