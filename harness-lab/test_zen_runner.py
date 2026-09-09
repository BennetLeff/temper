"""Boundary checks; recorded native action-chain coverage remains in qualify.py."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

import harness
from run_zen_trials import MODEL, normalize, validate_request, verify_wire


class ZenBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = {
            "model": MODEL,
            "store": False,
            "input": [],
            "tools": [
                {
                    "type": "function",
                    "name": "pcb_" + t["name"],
                    "parameters": t["inputSchema"],
                    "description": t["description"],
                }
                for t in harness.TOOLS
            ],
        }

    def test_exact_catalog_is_admitted(self) -> None:
        validate_request(self.packet)

    def test_model_fallback_is_rejected(self) -> None:
        self.packet["model"] = "muse-spark-1.3"
        with self.assertRaises(ValueError):
            validate_request(self.packet)

    def test_extra_or_missing_tools_are_rejected(self) -> None:
        for tools in (
            self.packet["tools"][:-1],
            self.packet["tools"] + [{"type": "web_search"}],
            self.packet["tools"] + [{"type": "function", "name": "bash"}],
        ):
            with self.subTest(tools=tools), self.assertRaises(ValueError):
                validate_request({**self.packet, "tools": tools})

    def test_changed_tool_schema_is_rejected(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["tools"][1]["parameters"]["properties"]["reference"] = {"type": "string"}
        with self.assertRaises(ValueError):
            validate_request(packet)

    def test_stateful_references_are_rejected(self) -> None:
        self.packet["input"] = [{"type": "item_reference", "id": "missing"}]
        with self.assertRaises(ValueError):
            validate_request(self.packet)

    def test_only_completed_admitted_calls_are_normalized(self) -> None:
        event = {
            "type": "tool_use",
            "part": {
                "tool": "pcb_inspect",
                "state": {
                    "status": "completed",
                    "input": {},
                    "output": '{"status":"fail"}',
                },
            },
        }
        self.assertEqual(normalize([event])[0]["item"]["arguments"], {})
        event["part"]["tool"] = "bash"
        with self.assertRaises(ValueError):
            normalize([event])
        with self.assertRaises(ValueError):
            normalize([{"type": "error"}])

    def test_wire_matches_calls_and_rejects_tampered_observation(self) -> None:
        call = {
            "type": "function_call",
            "name": "pcb_inspect",
            "call_id": "call1",
            "arguments": "{}",
        }
        observation = {"status": "fail", "sequence": 1}
        events = [
            {
                "type": "tool_use",
                "part": {
                    "tool": "pcb_inspect",
                    "callID": "call1",
                    "state": {
                        "status": "completed",
                        "input": {},
                        "output": json.dumps(observation),
                    },
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            packets = [
                self.packet,
                {
                    **self.packet,
                    "input": [
                        call,
                        {
                            "type": "function_call_output",
                            "call_id": "call1",
                            "output": json.dumps(observation),
                        },
                    ],
                },
            ]
            for index, packet in enumerate(packets, 1):
                prefix = directory / f"wire-{index:03}"
                prefix.with_suffix(".request.json").write_text(json.dumps(packet))
                prefix.with_suffix(".status.json").write_text('{"status":200}')
                prefix.with_suffix(".response.txt").write_text(
                    "data: "
                    + json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "model": MODEL,
                                "output": [call] if index == 1 else [],
                            },
                        }
                    )
                    + "\n"
                )
            self.assertEqual(verify_wire(directory, events)["request_count"], 2)
            packets[1]["input"][1]["output"] = '{"status":"pass"}'
            (directory / "wire-002.request.json").write_text(json.dumps(packets[1]))
            with self.assertRaises(ValueError):
                verify_wire(directory, events)


if __name__ == "__main__":
    unittest.main()
