"""Process-level controls for the Rust continual contract boundary."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import harness

D = "a" * 64
MODEL = "opencode/muse-spark-1.3-contributor-free"
ROOT = Path(__file__).parent


class ContinualContractTests(unittest.TestCase):
    def run_judge(self, payload: str | dict) -> dict:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run(
            [str(harness.JUDGE)], input=raw, text=True, capture_output=True, check=False
        )
        self.assertTrue(proc.stdout, proc.stderr)
        return json.loads(proc.stdout)

    def header(self) -> dict:
        return {
            "run_id": "run-1",
            "attempt_id": "development-buck-dev-a-fixed-base",
            "phase": "development",
            "slot": 0,
            "condition": "fixed_base",
            "variant": "buck-dev-a",
            "model": MODEL,
            "board_sha256": D,
            "revision_sha256": D,
            "started_unix_ms": 1_000,
            "deadline_unix_ms": 1_201_000,
            "edit_budget": 200,
            "engineering_inventory_sha256": D,
        }

    def classify(self, **overrides: object) -> dict:
        payload: dict[str, object] = {
            "attempt_id": "attempt-1",
            "provider_complete": True,
            "provider_verified": True,
            "process_status": "complete",
            "measurement_present": True,
            "driver_status": "complete",
            "worker_alive": True,
            "worker_owned": True,
            "state_ack_matches": True,
            "reconstructed_globals": False,
            "native_status": "pass",
            "remaining_ms": 10,
            "resume_count": 0,
            "deadline_unix_ms": 1000,
            "expected_deadline_unix_ms": 1000,
            "now_unix_ms": 990,
        }
        payload.update(overrides)
        return self.run_judge(
            {"schema": "continual/v1", "command": "attempt.classify", "input": payload}
        )

    def test_final_classification_rejects_known_state_conflicts(self):
        for overrides in (
            {"state_ack_matches": False},
            {"reconstructed_globals": True},
            {"board_sha256": D, "expected_board_sha256": "b" * 64},
            {"revision_sha256": D, "expected_revision_sha256": "b" * 64},
            {"action_count": 1, "expected_action_count": 0},
            {"expected_deadline_unix_ms": 2000},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(
                    self.classify(**overrides)["decision"], "record_indeterminate"
                )

    def test_optional_statuses_cannot_hide_transport_or_worker_failure(self):
        for overrides in (
            {"provider_status": False},
            {"measurement_status": False},
            {"construction_status": "fail"},
        ):
            self.assertEqual(self.classify(**overrides)["status"], "invalid")
        for overrides in (
            {"provider_status": "complete", "transport_status": "failed"},
            {"worker_status": "crash"},
            {"measurement_status": "missing"},
        ):
            self.assertEqual(
                self.classify(**overrides)["decision"], "record_indeterminate"
            )

    def test_inheritance_current_identities_must_be_real_digests(self):
        keys = (
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
        )
        manifest = {
            "frozen": True,
            "source_phase": "development",
            "revisions": [],
            **{key: D for key in keys},
        }
        result = self.run_judge(
            {
                "schema": "continual/v1",
                "command": "inheritance.select",
                "input": {
                    "manifest": manifest,
                    "engineering_admission": "pass",
                    **{key: False for key in keys},
                },
            }
        )
        self.assertEqual(result["status"], "invalid")

    def test_history_cannot_forge_revision_without_refinement(self):
        import copy

        initial = {
            "board_sha256": D,
            "revision_sha256": D,
            "action_count": 0,
            "successful_mutations": 0,
            "refinement_count": 0,
            "deadline_unix_ms": 1000,
            "edit_budget": 200,
        }
        packet = {
            "schema": "continual/v1",
            "command": "attempt.event",
            "input": {
                "attempt_id": "control",
                "sequence": 1,
                "kind": "inspect",
                "state": initial,
                "history": [],
            },
        }
        first = self.run_judge(packet)
        self.assertEqual(first["status"], "pass")
        history = copy.deepcopy(first["history"])
        history[0]["state_after"]["revision_sha256"] = "b" * 64
        packet["input"].update(
            sequence=2, history=history, state=history[0]["state_after"]
        )
        self.assertEqual(self.run_judge(packet)["status"], "invalid")

    def test_start_and_envelope_are_rust_owned(self) -> None:
        result = self.run_judge(
            {
                "schema": "continual/v1",
                "command": "attempt.start",
                "input": self.header(),
            }
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["schema"], "continual/v1")
        self.assertEqual(result["command"], "attempt.start")

    def test_unknown_and_duplicate_fields_fail_closed(self) -> None:
        unknown = {
            "schema": "continual/v1",
            "command": "attempt.start",
            "input": self.header(),
        }
        unknown["input"]["extra"] = True
        self.assertEqual(self.run_judge(unknown)["status"], "invalid")
        duplicate = (
            '{"schema":"continual/v1","command":"attempt.start","input":'
            + json.dumps(self.header())[:-1]
            + ',"run_id":"other"}}'
        )
        self.assertNotEqual(self.run_judge(duplicate)["status"], "pass")

    def test_provider_failure_stays_indeterminate_when_worker_lives(self) -> None:
        result = self.classify(
            provider_complete=False, provider_verified=False, provider_status="failed"
        )
        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["decision"], "record_indeterminate")

    def test_native_pass_and_fail_are_model_outcomes(self) -> None:
        self.assertEqual(
            self.classify(native_status="pass")["decision"], "record_passed"
        )
        self.assertEqual(
            self.classify(native_status="fail")["decision"], "record_failed"
        )

    def test_resume_requires_matching_owned_live_state(self) -> None:
        result = self.classify(
            driver_status="interrupt",
            board_sha256=D,
            expected_board_sha256=D,
            action_count=2,
            expected_action_count=2,
            revision_sha256=D,
            expected_revision_sha256=D,
        )
        self.assertEqual(result["decision"], "resume_same_attempt")
        self.assertEqual(
            self.classify(driver_status="interrupt")["decision"], "record_indeterminate"
        )
        self.assertEqual(
            self.classify(driver_status="interrupt", slot_consumed=True)["decision"],
            "record_indeterminate",
        )

    def test_context_trims_whole_pairs_to_last_twenty(self) -> None:
        pairs = [
            {"request": {"sequence": i}, "response": {"status": "pass"}}
            for i in range(25)
        ]
        result = self.run_judge(
            {
                "schema": "continual/v1",
                "command": "context.build",
                "input": {
                    "notes_utf8": "# notes\n",
                    "skills_utf8": "x = 1\n",
                    "observation": {},
                    "instructions": "route",
                    "pairs": pairs,
                },
            }
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["supplied_pair_count"], 25)
        self.assertEqual(result["pair_count"], 20)
        self.assertEqual(result["trimmed_pair_count"], 5)
        self.assertEqual(result["context"]["pairs"][0]["request"]["sequence"], 5)

    def test_timeout_label_cannot_pass_with_conflicting_flags(self):
        self.assertEqual(
            self.classify(provider_status="timeout")["decision"], "record_indeterminate"
        )

    def test_history_is_flat_and_rejects_state_reset(self):
        state = {
            "board_sha256": D,
            "revision_sha256": D,
            "action_count": 0,
            "successful_mutations": 0,
            "refinement_count": 0,
            "deadline_unix_ms": 1200000,
            "edit_budget": 200,
        }
        history = []
        for sequence in range(1, 13):
            event = {
                "attempt_id": "a",
                "sequence": sequence,
                "kind": "inspect",
                "history": history,
                "state": state,
            }
            result = self.run_judge(
                {"schema": "continual/v1", "command": "attempt.event", "input": event}
            )
            self.assertEqual(result["status"], "pass", result)
            history, state = result["history"], result["state"]
        self.assertLess(len(json.dumps(history)), 50000)
        state["board_sha256"] = "b" * 64
        result = self.run_judge(
            {
                "schema": "continual/v1",
                "command": "attempt.event",
                "input": {**event, "sequence": 13, "history": history, "state": state},
            }
        )
        self.assertEqual(result["status"], "invalid")

    def test_uncommitted_admission_failure_does_not_consume_mutations(self):
        state = {
            "board_sha256": D,
            "revision_sha256": D,
            "action_count": 0,
            "successful_mutations": 0,
            "refinement_count": 0,
            "deadline_unix_ms": 1200000,
            "edit_budget": 200,
        }
        event = {
            "attempt_id": "a",
            "sequence": 1,
            "kind": "mutation",
            "history": [],
            "state": state,
            "operation": "place",
            "request_sha256": D,
            "response_status": "invalid",
            "mutation_committed": False,
            "native_verdict": None,
            "board_sha256": D,
            "successful_mutations": 0,
        }
        result = self.run_judge(
            {"schema": "continual/v1", "command": "attempt.event", "input": event}
        )
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["action_count"], 0)

    def test_inheritance_is_current_development_only_and_ranked(self):
        names = [
            "engineering_inventory_sha256",
            "qualification_sha256",
            "source_sha256",
            "approved_evidence_sha256",
            "native_judge_sha256",
        ]
        identities = dict.fromkeys(names, D)
        candidate = {
            **identities,
            "revision_sha256": "c" * 64,
            "source_attempt_id": "development-a",
            "source_phase": "development",
            "source_variant": "buck-dev-a",
            "condition": "updating_base",
            "applied": True,
            "qualified": True,
            "complete_construction": False,
            "total_elapsed_ms": 100,
            "source_owned": True,
            "notes_sha256": "b" * 64,
            "skills_sha256": D,
            "base_notes_sha256": D,
            "base_skills_sha256": D,
        }
        faster = {**candidate, "revision_sha256": "d" * 64, "total_elapsed_ms": 10}
        complete = {
            **candidate,
            "revision_sha256": "e" * 64,
            "complete_construction": True,
            "total_elapsed_ms": 1000,
        }
        manifest = {
            **identities,
            "frozen": True,
            "source_phase": "development",
            "revisions": [candidate, faster, complete],
        }
        payload = {
            **identities,
            "manifest": manifest,
            "engineering_admission": "software_control",
        }

        def decide(value):
            return self.run_judge(
                {
                    "schema": "continual/v1",
                    "command": "inheritance.select",
                    "input": value,
                }
            )

        self.assertEqual(decide(payload)["selected"], complete["revision_sha256"])
        manifest["revisions"] = [candidate, faster]
        self.assertEqual(decide(payload)["selected"], faster["revision_sha256"])
        self.assertEqual(decide({"manifest": manifest})["status"], "invalid")
        for patch in (
            {"source_variant": "buck-res-a"},
            {"notes_sha256": D},
            {"total_elapsed_ms": "bad"},
        ):
            manifest["revisions"] = [{**candidate, **patch}]
            self.assertEqual(decide(payload)["status"], "invalid")

    def test_refinement_policy_and_global_slot_catalog(self):
        schema = self.run_judge(
            {"schema": "continual/v1", "command": "schema", "input": {}}
        )
        self.assertEqual([slot["slot"] for slot in schema["slots"]], list(range(10)))
        for condition, passed, expected in [
            ("updating_base", False, True),
            ("fixed_base", False, False),
            ("inherited_updating", True, False),
        ]:
            result = self.run_judge(
                {
                    "schema": "continual/v1",
                    "command": "refinement.eligible",
                    "input": {
                        "successful_mutations": 20,
                        "measurement_complete": True,
                        "construction_passed": passed,
                        "deadline_expired": False,
                        "refinement_count": 0,
                        "condition": condition,
                    },
                }
            )
            self.assertEqual(result["eligible"], expected)


if __name__ == "__main__":
    unittest.main()
