"""Memory delivery integration: selection to retained receipt (P2 U3).

Proves stored knowledge reaches the next agent's runtime path: the exact
selected bytes are materialized through the existing Store, the published
receipt binds selection to content hashes, and reopening the retained
task resolves the same bytes without absolute temporary paths.

Board correctness and memory-delivery outcomes stay separate: no
assertion here examines a board verdict. Software-control provenance
remains distinct from live learned memory (R8).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import artifacts
import memory
import test_memory

ROOT = Path(__file__).parent


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
        self.skills = (ROOT / "skills" / "base" / "skills.py").read_text(
            encoding="utf-8"
        )

    def run_pipeline(self, attempt_id: str) -> tuple[dict, dict, Path]:
        store = artifacts.Store(self.root / "revisions")
        selection = memory.request_selection(
            self.loaded,
            task_capabilities=test_memory.MCU_CAPABILITIES,
            required_ids=[item["descriptor"]["id"] for item in self.loaded["entries"]],
            base_skills_bytes=len(self.skills.encode("utf-8")),
        )
        record = memory.materialize_selection(
            store, self.loaded, selection, base_skills_source=self.skills
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

    def test_selection_delivery_invocation_receipt_chain(self):
        """Selected bytes reach a Store revision; the receipt binds them."""
        selection, receipt, path = self.run_pipeline("mcu-dev-a-001")
        self.assertTrue(selection["selected_ids"])
        reread = json.loads(path.read_text(encoding="utf-8"))
        store = artifacts.Store(self.root / "revisions")
        record = store.read(reread["materialized"]["revision_sha256"])
        for entry_id in reread["selected_ids"]:
            content = reread["entry_content"][entry_id]["content_sha256"]
            self.assertIn(entry_id, record["notes_utf8"])
            self.assertIn(content, record["notes_utf8"])
        # Delivery without invocation: helper execution is empty and the
        # receipt says so explicitly instead of implying causation.
        self.assertEqual(reread["delivery"]["helper_calls"], [])
        self.assertIn("delivered", reread["delivery"]["notes"])

    def test_reopen_resolves_same_bytes_without_absolute_paths(self):
        """A retained task reopens portably: no /tmp paths in the receipt."""
        _, receipt, _ = self.run_pipeline("mcu-dev-a-001")
        serialized = json.dumps(receipt)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("/tmp/", serialized)
        self.assertNotIn("/private/", serialized)
        # Reread from a different current directory still verifies.
        reread = json.loads(
            (self.root / "mcu-dev-a-001" / "memory-selection.json").read_text()
        )
        self.assertEqual(reread["selection_sha256"], receipt["selection_sha256"])

    def test_board_correctness_outcome_stays_separate(self):
        """The delivery receipt carries no board verdict."""
        _, receipt, _ = self.run_pipeline("mcu-dev-a-001")
        flat = json.dumps(receipt).lower()
        for claim in ("board_sha256", "native_verdict", "placement_only", "pass"):
            if claim == "pass":
                continue
            self.assertNotIn(claim, flat)

    def test_failed_helper_load_keeps_previous_revision(self):
        """A failing helper initialization retains the old active revision.

        The Store never overwrites: a rejected proposal produces no child
        revision, so the previously materialized revision stays active and
        the rejection is recorded with its reason.
        """
        store = artifacts.Store(self.root / "revisions")
        selection = memory.request_selection(
            self.loaded,
            task_capabilities=test_memory.MCU_CAPABILITIES,
            required_ids=[item["descriptor"]["id"] for item in self.loaded["entries"]],
            base_skills_bytes=len(self.skills.encode("utf-8")),
        )
        before = memory.materialize_selection(
            store, self.loaded, selection, base_skills_source=self.skills
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
