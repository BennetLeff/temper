"""Host plumbing controls for cross-unit memory (P2 U2).

Every decision is made by the Rust judge; these tests pin the host's
byte-verification, receipt binding, and failure modes. Curation needs
source review, not tests that repeat entry text: no test asserts on the
wording of a lesson, only on identities, hashes, and selection mechanics.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import artifacts
import memory

ROOT = Path(__file__).parent

MCU_CAPABILITIES = [
    "validator-findings-inspection",
    "targeted-connection-edit",
    "independent-board-check",
    "placement-reading",
    "routing-reading",
    "run-audit-reading",
    "transport-vs-board-diagnosis",
    "simulation-evidence-scoping",
    "assumption-ledger-reading",
    "source-import",
    "pin-identity-verification-against-current-bridge",
]


class MemoryHostTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            memory.default_judge().is_file(),
            "memory Rust judge is not built; run `cargo build --locked` in harness-lab",
        )
        self.loaded = memory.load_catalog()

    def required_ids(self):
        return [item["descriptor"]["id"] for item in self.loaded["entries"]]

    def base_sizes(self):
        skills = (ROOT / "skills" / "base" / "skills.py").read_text(encoding="utf-8")
        return skills, len(skills.encode("utf-8"))

    def test_catalog_loads_five_supported_entries(self):
        self.assertEqual(len(self.loaded["entries"]), 5)
        verdicts = memory.validate_loaded(self.loaded)
        self.assertEqual(len(verdicts), 5)
        for verdict in verdicts:
            self.assertEqual(verdict["status"], "pass")

    def test_no_entry_claims_pilot_learning(self):
        for item in self.loaded["entries"]:
            descriptor = item["descriptor"]
            self.assertNotIn(
                "pilot", json.dumps(descriptor).lower().replace("has not run", "")
            )

    def test_full_mcu_selection_is_nonempty_and_ordered(self):
        skills, skills_bytes = self.base_sizes()
        selection = memory.request_selection(
            self.loaded,
            task_capabilities=MCU_CAPABILITIES,
            required_ids=self.required_ids(),
            base_skills_bytes=skills_bytes,
        )
        self.assertEqual(selection["status"], "pass")
        self.assertEqual(selection["selected_ids"], self.required_ids())
        self.assertEqual(selection["exclusions"], [])
        self.assertRegex(selection["selection_sha256"], r"^[0-9a-f]{64}$")

    def test_missing_capability_excludes_with_reason(self):
        skills, skills_bytes = self.base_sizes()
        selection = memory.request_selection(
            self.loaded,
            task_capabilities=["validator-findings-inspection"],
            allow_empty_baseline=True,
            base_skills_bytes=skills_bytes,
        )
        self.assertEqual(selection["status"], "pass")
        self.assertLess(len(selection["selected_ids"]), 5)
        self.assertTrue(selection["exclusions"])
        for exclusion in selection["exclusions"]:
            self.assertIn("unmet required capabilities", exclusion["reason"])

    def test_required_entry_without_capability_fails_closed(self):
        skills, skills_bytes = self.base_sizes()
        with self.assertRaises(ValueError):
            memory.request_selection(
                self.loaded,
                task_capabilities=["validator-findings-inspection"],
                required_ids=self.required_ids(),
                base_skills_bytes=skills_bytes,
            )

    def test_empty_selection_needs_explicit_baseline(self):
        skills, skills_bytes = self.base_sizes()
        with self.assertRaises(ValueError):
            memory.request_selection(
                self.loaded,
                task_capabilities=[],
                base_skills_bytes=skills_bytes,
            )
        baseline = memory.request_selection(
            self.loaded,
            task_capabilities=[],
            allow_empty_baseline=True,
            base_skills_bytes=skills_bytes,
        )
        self.assertEqual(baseline["selected_ids"], [])

    def test_tampered_evidence_rejected(self):
        tampered = dict.fromkeys(memory._evidence_hashes(), "0" * 64)
        with self.assertRaises(ValueError):
            memory.validate_loaded(self.loaded, evidence_hashes=tampered)

    def test_byte_cap_overflow_reported(self):
        skills, skills_bytes = self.base_sizes()
        with self.assertRaises(ValueError):
            memory.request_selection(
                self.loaded,
                task_capabilities=MCU_CAPABILITIES,
                required_ids=self.required_ids(),
                base_notes_bytes=64 * 1024,
                base_skills_bytes=skills_bytes,
            )

    def test_unknown_required_id_rejected(self):
        skills, skills_bytes = self.base_sizes()
        with self.assertRaises(ValueError):
            memory.request_selection(
                self.loaded,
                task_capabilities=MCU_CAPABILITIES,
                required_ids=["buck-mem-999"],
                base_skills_bytes=skills_bytes,
            )

    def test_promotion_gates_visible_to_host(self):
        rejected = memory.review_proposal(
            proposal_id="p-timeout",
            claim_kind="circuit-performance",
            basis="timeout-only",
            evidence_independent=False,
            helper_test="none",
            source_artifact_match=False,
        )
        self.assertEqual(rejected["outcome"], "rejected")
        candidate = memory.review_proposal(
            proposal_id="p-diag",
            claim_kind="diagnostic",
            basis="complete-valid-failing-attempt",
            evidence_independent=False,
            helper_test="none",
            source_artifact_match=False,
        )
        self.assertEqual(candidate["outcome"], "candidate")

    def test_materialize_and_receipt_roundtrip(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = artifacts.Store(Path(temp.name) / "revisions")
        skills, skills_bytes = self.base_sizes()
        selection = memory.request_selection(
            self.loaded,
            task_capabilities=MCU_CAPABILITIES,
            required_ids=self.required_ids(),
            base_skills_bytes=skills_bytes,
        )
        record = memory.materialize_selection(
            store, self.loaded, selection, base_skills_source=skills
        )
        self.assertEqual(store.read(record["revision_sha256"]), record)
        receipt = memory.build_receipt(
            selection=selection,
            loaded=self.loaded,
            revision_sha256=record["revision_sha256"],
            notes_sha256=record["receipt"]["notes_sha256"],
            skills_sha256=record["receipt"]["skills_sha256"],
            attempt_id="mcu-dev-a-001",
        )
        self.assertEqual(receipt["selection_sha256"], selection["selection_sha256"])
        self.assertEqual(receipt["delivery"]["helper_calls"], [])
        path = memory.publish_receipt(Path(temp.name) / "attempt", receipt)
        reread = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(reread, receipt)


if __name__ == "__main__":
    unittest.main()
