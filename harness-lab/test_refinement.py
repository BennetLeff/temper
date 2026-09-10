"""Live executable refinement in the real sandbox; no external provider."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import artifacts
import refinement
import workspace
from test_workspace import FakeSession


class RefinementTests(unittest.TestCase):
    def run_case(self, refiner, condition="updating_base"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        session = FakeSession()
        session.directory = root
        original = session.call

        def call(name, args):
            result = original(name, args)
            if result.get("mutation_committed"):
                result.update(status="fail", native_verdict="fail")
            manager.observe(name, args, result)
            return result

        store = artifacts.Store(root / "artifacts")
        initial = store.base("base", "def value():\n    return 1\n")
        worker = workspace.Workspace(session)
        self.addCleanup(worker.close)
        worker.apply_revision(
            initial["revision_sha256"], initial["skills_utf8"], initial["notes_utf8"]
        )
        manager = refinement.Manager(
            session,
            worker,
            store,
            initial,
            condition,
            "attempt-a",
            refiner,
            "Use native measurements.",
        )
        session.call = call
        return worker, manager, session

    @staticmethod
    def proposal(context, deadline, directory):
        return {
            "notes_utf8": "learned control",
            "skills_utf8": "def value():\n    return 2\n",
            "model": artifacts.MODEL,
            "transport": {
                "verified": True,
                "reference": "wire-001.response.txt",
                "software_control": True,
            },
        }

    def test_revision_applies_mid_cell_preserving_variables_alias_and_deadline(self):
        worker, manager, session = self.run_case(self.proposal)
        before = session.deadline
        result = worker.execute(
            "ordinary = 41\nalias = skills.value\nfor _ in range(20): pcb.call('place', {})\nassert skills.value() == 2\nassert alias() == 1\nordinary += 1\nprint(ordinary)"
        )
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["stdout"], "42\n")
        self.assertEqual(session.actions, 20)
        self.assertEqual(session.deadline, before)
        self.assertEqual(manager.receipts[0]["status"], "applied")
        self.assertEqual(worker.current_revision, manager.current["revision_sha256"])
        self.assertEqual(manager.store.read(worker.current_revision), manager.current)

    def test_fixed_condition_and_bad_syntax_retain_old_revision(self):
        worker, manager, _ = self.run_case(
            lambda *_: self.fail("fixed condition called refiner"), "fixed_base"
        )
        worker.execute("for _ in range(20): pcb.call('place', {})")
        self.assertEqual(manager.receipts, [])

        def invalid(*args):
            return {**self.proposal(*args), "skills_utf8": "def broken(:"}

        worker, manager, _ = self.run_case(invalid)
        old = worker.current_revision
        result = worker.execute(
            "for _ in range(20): pcb.call('place', {})\nassert skills.value() == 1"
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(worker.current_revision, old)
        self.assertEqual(manager.receipts[0]["status"], "rejected")

    def test_transport_integrity_failure_is_sticky_and_retains_old_revision(self):
        def failed(*_):
            raise refinement.TransportIntegrityError("incomplete provider response")

        worker, manager, session = self.run_case(failed)
        old = worker.current_revision
        with self.assertRaises(workspace.WorkspaceError):
            worker.execute("for _ in range(20): pcb.call('place', {})")
        self.assertEqual(worker.current_revision, old)
        self.assertEqual(session.actions, 20)
        self.assertTrue(session.terminal_error)
        self.assertEqual(manager.receipts[0]["status"], "indeterminate")
        self.assertIsNotNone(worker.process.poll())

    def test_context_byte_limit_and_complete_pair_hash(self):
        pairs = [
            {"request": {"i": i}, "response": {"blob": "x" * 9000}} for i in range(22)
        ]
        result = artifacts.judge(
            "context.build",
            {
                "notes_utf8": "n",
                "skills_utf8": "x=1",
                "instructions": "i",
                "observation": {},
                "pairs": pairs,
            },
        )
        self.assertLessEqual(len(artifacts.canonical(result["context"])), 131072)
        self.assertLess(result["pair_count"], 20)
        self.assertEqual(
            result["window_sha256"], artifacts.identity(result["context"]["pairs"])
        )

    def test_failed_load_retains_both_artifacts_and_old_binding(self):
        def bad_load(*args):
            return {
                **self.proposal(*args),
                "skills_utf8": "raise RuntimeError('load failed')",
            }

        worker, manager, _ = self.run_case(bad_load)
        old = worker.current_revision
        result = worker.execute(
            "for _ in range(20): pcb.call('place', {})\nassert skills.value() == 1"
        )
        self.assertEqual(result["status"], "pass")
        receipt = manager.receipts[0]
        self.assertEqual(receipt["status"], "rejected")
        self.assertEqual(worker.current_revision, old)
        child = manager.store.read(receipt["child_revision_sha256"])
        self.assertEqual(child["payload"]["parent_revision_sha256"], old)
        self.assertEqual(child["payload"]["source_window"]["pair_count"], 20)
        self.assertEqual(
            child["payload"]["source_window"]["window_sha256"],
            artifacts.identity(child["payload"]["source_pairs"]),
        )

    def test_unchanged_base_cannot_be_promoted_as_learning(self):
        def unchanged(context, _deadline, _directory):
            return {
                "notes_utf8": context["notes_utf8"],
                "skills_utf8": context["skills_utf8"],
                "model": artifacts.MODEL,
                "transport": {
                    "verified": True,
                    "reference": "control.json",
                    "software_control": True,
                },
            }

        worker, manager, _ = self.run_case(unchanged)
        old = worker.current_revision
        worker.execute("for _ in range(20): pcb.call('place', {})")
        self.assertEqual(manager.receipts[0]["status"], "rejected")
        self.assertEqual(worker.current_revision, old)
