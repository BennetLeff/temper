"""Focused admission and slot controls for the continual buck runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_buck_trials


class RunnerContractTests(unittest.TestCase):
    def test_slots_are_fixed_and_unique(self) -> None:
        development = run_buck_trials.slots_for("development")
        evaluation = run_buck_trials.slots_for("evaluation")
        self.assertEqual(len(development), 4)
        self.assertEqual(len(evaluation), 6)
        self.assertEqual(len({slot.slot for slot in development + evaluation}), 10)
        self.assertEqual(
            [slot.condition for slot in development],
            ["fixed_base", "updating_base", "fixed_base", "updating_base"],
        )
        self.assertEqual(
            [slot.condition for slot in evaluation],
            ["fixed_base", "inherited_frozen", "inherited_updating"] * 2,
        )

    def test_blocked_admission_materializes_every_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = run_buck_trials.run(
                root / "run",
                phase="development",
                qualification=None,
                engineering=None,
                preflight_receipt=None,
                inheritance=None,
            )
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(len(report["slots"]), 4)
            self.assertTrue(
                all(item["status"] == "blocked" for item in report["slots"])
            )

    def test_empty_approved_registry_blocks_even_with_receipt_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            qualification = root / "qualification.json"
            engineering = root / "engineering.json"
            preflight = root / "preflight.json"
            qualification.write_text(json.dumps({"status": "qualified"}))
            engineering.write_text(json.dumps({"status": "pass"}))
            preflight.write_text(json.dumps({"status": "preflight_pass"}))
            with patch.object(
                run_buck_trials,
                "verify_qualification",
                side_effect=ValueError("test qualification"),
            ):
                report = run_buck_trials.run(
                    root / "run",
                    phase="evaluation",
                    qualification=qualification,
                    engineering=engineering,
                    preflight_receipt=preflight,
                    inheritance=root / "inheritance.json",
                )
            self.assertEqual(report["status"], "blocked")
            self.assertTrue(
                any(
                    "test qualification" in item
                    for item in report["admission"]["findings"]
                )
            )
            self.assertEqual(len(report["slots"]), 6)

    def test_admission_drift_retains_completed_and_remaining_slots(self):
        identity = {key: "a" * 64 for key in run_buck_trials.IDENTITIES}
        admitted = {
            "status": "pass",
            "phase": "development",
            "findings": [],
            "identity": identity,
        }
        drifted = {
            **admitted,
            "status": "blocked",
            "findings": ["qualification changed"],
        }
        first = {
            **vars(run_buck_trials.slots_for("development")[0]),
            "status": "fail",
            "attempt_id": "first",
            "slot_consumed": True,
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            with (
                patch.object(
                    run_buck_trials,
                    "inspect_admission",
                    side_effect=[admitted, admitted, drifted],
                ),
                patch.object(
                    run_buck_trials, "run_attempt", return_value=first
                ) as launch,
            ):
                report = run_buck_trials.run(
                    output,
                    phase="development",
                    qualification=None,
                    engineering=None,
                    preflight_receipt=None,
                    inheritance=None,
                )
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(
                [r["status"] for r in report["slots"]],
                ["fail", "blocked", "blocked", "blocked"],
            )
            self.assertEqual(len(report["slots"]), 4)
            self.assertEqual(json.loads((output / "results.json").read_text()), report)

    def test_exporter_exception_cannot_change_results_or_exit_status(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            with patch.object(
                run_buck_trials.telemetry,
                "export",
                side_effect=RuntimeError("backend failed"),
            ):
                report = run_buck_trials.run(
                    output,
                    phase="development",
                    qualification=None,
                    engineering=None,
                    preflight_receipt=None,
                    inheritance=None,
                    export_telemetry=True,
                )
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(json.loads((output / "results.json").read_text()), report)
            self.assertEqual(
                json.loads((output / "telemetry.json").read_text())["status"],
                "unavailable",
            )

    def test_no_override_flag_is_exposed(self) -> None:
        with self.assertRaises(SystemExit):
            run_buck_trials.main(["/tmp/run", "--phase", "development", "--override"])


if __name__ == "__main__":
    unittest.main()


class RunnerIntegrationTests(unittest.TestCase):
    identity = {key: "a" * 64 for key in run_buck_trials.IDENTITIES}

    def wire_driver(self, cells, *, interrupt=False, incomplete=False):
        """Scripted provider bytes; native tools and the sandbox are real."""
        import socket

        def driver(command, private, env, directory, deadline, ordinal):
            del private, env, deadline
            if ordinal == 2:
                self.assertIn("--session", command)
                self.assertEqual(command[command.index("--session") + 1], "ses_control")
            config = json.loads((directory / "config.json").read_text())
            proxy = config["mcp"]["pcb"]["command"]
            endpoint, token = proxy[proxy.index("--proxy") + 1], proxy[-1]
            host, port = endpoint.split(":")
            code = cells[ordinal - 1]
            with socket.create_connection((host, int(port))) as connection:
                connection.settimeout(125)
                stream = connection.makefile("rwb")
                arguments = {"code": code}
                name = "execute"
                if code is None:
                    name, arguments = "inspect", {}
                request = {
                    "jsonrpc": "2.0",
                    "id": ordinal,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
                stream.write(
                    (json.dumps({"token": token, "request": request}) + "\n").encode()
                )
                stream.flush()
                response = json.loads(stream.readline())
            output = response["result"]["content"][0]["text"]
            self.assertEqual(json.loads(output)["status"], "pass", output)
            tools = [
                {
                    "type": "function",
                    "name": "pcb_" + t["name"],
                    "description": t["description"],
                    "parameters": t["inputSchema"],
                }
                for t in run_buck_trials.buck_host.TOOLS
            ]
            call_id = f"call_{ordinal}"
            base = {"model": run_buck_trials.MODEL, "store": False, "tools": tools}
            next_index = len(list(directory.glob("wire-*.request.json"))) + 1
            for index, inputs, outputs in (
                (
                    next_index,
                    [],
                    [
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "name": "pcb_" + name,
                            "arguments": json.dumps(arguments),
                        }
                    ],
                ),
                (
                    next_index + 1,
                    [
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": output,
                        }
                    ],
                    [],
                ),
            ):
                prefix = directory / f"wire-{index:03}"
                Path(str(prefix) + ".request.json").write_text(
                    json.dumps({**base, "input": inputs})
                )
                Path(str(prefix) + ".status.json").write_text('{"status":200}')
                event = {
                    "type": "response.completed",
                    "response": {"model": run_buck_trials.MODEL, "output": outputs},
                }
                Path(str(prefix) + ".response.txt").write_text(
                    "data: " + json.dumps(event) + "\n"
                )
            if incomplete:
                Path(str(prefix) + ".response.txt").write_text("data: {}\n")
            events = [
                {
                    "type": "tool_use",
                    "sessionID": "ses_control",
                    "part": {
                        "callID": call_id,
                        "tool": "pcb_" + name,
                        "state": {
                            "status": "completed",
                            "input": arguments,
                            "output": output,
                        },
                    },
                },
                {
                    "type": "step_finish",
                    "sessionID": "ses_control",
                    "part": {"reason": "stop"},
                },
            ]
            return (130 if interrupt and ordinal == 1 else 0), events

        return driver

    def test_real_driver_resume_retains_python_state_and_native_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = run_buck_trials.run_attempt(
                output,
                run_buck_trials.slots_for("development")[0],
                identity=self.identity,
                driver=self.wire_driver(
                    ["counter=41", "counter+=1\nassert counter==42"], interrupt=True
                ),
            )
            self.assertEqual(result["status"], "fail", result)
            self.assertEqual(result["resume_count"], 1)
            directory = output / result["attempt_id"]
            headers = json.loads((directory / "attempt-header.json").read_text())
            proofs = [
                json.loads(p.read_text()) for p in directory.glob("liveness-*.json")
            ]
            self.assertEqual(len({p["pid"] for p in proofs}), 1)
            self.assertEqual(len({p["nonce"] for p in proofs}), 1)
            self.assertEqual(len({p["proof"]["deadline"] for p in proofs}), 1)
            self.assertTrue(
                all(p["revision"] == headers["revision_sha256"] for p in proofs)
            )
            self.assertTrue((directory / "sandbox-capability.json").is_file())

    def test_incomplete_provider_consumes_slot_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run_buck_trials.run_attempt(
                Path(temp),
                run_buck_trials.slots_for("development")[0],
                identity=self.identity,
                driver=self.wire_driver(
                    ["counter=41"], interrupt=True, incomplete=True
                ),
            )
            self.assertEqual(result["status"], "indeterminate", result)
            self.assertEqual(result["resume_count"], 0)
            self.assertTrue(result["slot_consumed"])

    def refinement_control(self, output: Path):
        def refiner(context, deadline, destination):
            del deadline
            self.assertGreater(len(context["pairs"]), 0)
            self.assertLessEqual(len(context["pairs"]), 20)
            (destination / "transport.json").write_text('{"software_control":true}')
            return {
                "notes_utf8": "Control: changed after measured edit 20.",
                "skills_utf8": "answer=42\n",
                "model": run_buck_trials.FULL_MODEL,
                "transport": {"verified": True, "reference": "transport.json"},
            }

        code = """counter=41
old=skills.inspect_board
for i in range(20):
    result=pcb.call('place', {'reference':'C9','x_mm':10+i%2,'y_mm':10,'angle_deg':0})
    assert result['mutation_committed']
counter+=1
assert counter==skills.answer==42
assert callable(old)
"""
        result = run_buck_trials.run_attempt(
            output,
            run_buck_trials.slots_for("development")[1],
            identity=self.identity,
            driver=self.wire_driver([code]),
            refiner=refiner,
        )
        self.assertEqual(result["status"], "fail", result)
        self.assertEqual(len(result["refinements"]), 1)
        self.assertEqual(result["refinements"][0]["status"], "applied")
        self.assertNotEqual(
            result["initial_revision_sha256"], result["revision_sha256"]
        )
        events = [
            json.loads(p.read_text())
            for p in sorted((output / result["attempt_id"]).glob("event-*.json"))
        ]
        self.assertEqual(events[-1]["state_after"]["action_count"], 20)
        self.assertEqual(events[-1]["state_after"]["refinement_count"], 1)

        # Freeze only artifact bytes from development; a reserved attempt
        # imports those bytes into a fresh interpreter without its globals.
        run_buck_trials.artifacts.write_once(
            output / "results.json",
            {"phase": "development", "identity": self.identity, "slots": [result]},
        )
        run_buck_trials.freeze_inheritance(
            output, [result], self.identity, software_control=True
        )
        selected = run_buck_trials.verify_inheritance(
            output / "inheritance.json", self.identity, software_control=True
        )
        self.assertEqual(selected["revision_sha256"], result["revision_sha256"])
        with self.assertRaisesRegex(ValueError, "software controls"):
            run_buck_trials.verify_inheritance(
                output / "inheritance.json", self.identity
            )
        inherited = run_buck_trials.run_attempt(
            output,
            run_buck_trials.slots_for("evaluation")[1],
            identity=self.identity,
            initial=selected,
            driver=self.wire_driver(
                [
                    "assert skills.answer==42\nassert 'counter' not in globals()\nassert 'old' not in globals()"
                ]
            ),
            refiner=lambda *args: self.fail("frozen evaluation must not refine"),
        )
        self.assertEqual(inherited["status"], "fail", inherited)
        self.assertEqual(
            inherited["initial_revision_sha256"], selected["revision_sha256"]
        )
        fixed = run_buck_trials.run_attempt(
            output,
            run_buck_trials.slots_for("evaluation")[0],
            identity=self.identity,
            driver=self.wire_driver(
                [
                    "assert not hasattr(skills, 'answer')\nassert 'counter' not in globals() "
                ]
            ),
        )
        self.assertEqual(fixed["status"], "fail", fixed)
        self.assertNotEqual(
            fixed["initial_revision_sha256"], inherited["initial_revision_sha256"]
        )

        return {"development": result, "inherited": inherited, "fixed": fixed}

    def test_real_native_twenty_edit_refinement_continues_same_cell(self):
        with tempfile.TemporaryDirectory() as temp:
            self.refinement_control(Path(temp))

    def test_worker_crash_retains_completed_native_edit(self):
        code = "pcb.call('place', {'reference':'C9','x_mm':10,'y_mm':10,'angle_deg':0})\nimport os\nos._exit(1)"
        with tempfile.TemporaryDirectory() as temp:
            result = run_buck_trials.run_attempt(
                Path(temp),
                run_buck_trials.slots_for("development")[0],
                identity=self.identity,
                driver=self.wire_driver([code]),
            )
            self.assertEqual(result["status"], "indeterminate", result)
            self.assertEqual(result["successful_mutations"], 1)
            self.assertTrue(result["slot_consumed"])
            directory = Path(temp) / result["attempt_id"]
            self.assertEqual(
                run_buck_trials._hash(directory / "candidate.kicad_pcb"),
                result["board_sha256"],
            )
            self.assertFalse((directory / "invocation-1.json").exists())

    def test_preflight_requires_admission_and_one_inspect(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with patch.object(run_buck_trials, "run_attempt") as launch:
                report = run_buck_trials.run(
                    output / "blocked",
                    phase="preflight",
                    qualification=None,
                    engineering=None,
                    preflight_receipt=None,
                    inheritance=None,
                )
                self.assertEqual(report["status"], "blocked")
                launch.assert_not_called()
            result = run_buck_trials.run_attempt(
                output,
                run_buck_trials.slots_for("preflight")[0],
                identity=self.identity,
                driver=self.wire_driver([None]),
            )
            self.assertEqual(result["status"], "preflight_pass", result)
            self.assertEqual(
                len(list((output / result["attempt_id"]).glob("check-*"))), 0
            )
