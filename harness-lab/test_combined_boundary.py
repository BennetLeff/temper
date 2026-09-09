"""Combined profile admission and experiment-evidence boundaries."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import combined_host as task
import harness
import routing_host
from run_zen_trials import MODEL, configuration, validate_request


class CombinedBoundaryTests(unittest.TestCase):
    def test_only_the_five_combined_tools_and_host_are_admitted(self):
        config = configuration(
            Path("/unused"), 1234, 9999, combined=True, preflight=True
        )
        command = config["mcp"]["pcb"]["command"]
        self.assertIn(str(task.ROOT / "combined_host.py"), command)
        self.assertIn("--inspect-only", command)
        self.assertNotIn("--fixture", command)
        self.assertEqual(
            {k for k in config["permission"] if k != "*"},
            {"pcb_inspect", "pcb_place", "pcb_route", "pcb_remove_route", "pcb_check"},
        )
        packet = {
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
                for t in task.TOOLS
            ],
        }
        validate_request(packet, task.TOOLS)
        for catalog in [harness.TOOLS, routing_host.TOOLS]:
            with self.assertRaises(ValueError):
                validate_request(packet, catalog)
        packet["tools"].pop()
        with self.assertRaises(ValueError):
            validate_request(packet, task.TOOLS)

    def test_initial_boards_are_pinned_and_unknown_starts_rejected(self):
        c = json.loads(task.CONTRACT.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, start in enumerate(c["starts"]):
                d = root / str(i)
                task.prepare(d, start)
                self.assertEqual(
                    harness.file_hash(d / "candidate.kicad_pcb"),
                    c["initial_boards_sha256"][i],
                )
            with self.assertRaises(ValueError):
                task.prepare(root / "bad", [6, 10, 90])
            source = root / "fixtures/e00pr/1"
            shutil.copytree(task.ROOT / "fixtures/e00pr/1", source)
            (source / "candidate.kicad_pcb").write_text("tampered")
            with patch.object(task, "ROOT", root), self.assertRaises(ValueError):
                task.prepare(root / "tampered", c["starts"][0])
            self.assertFalse((root / "tampered").exists())

    def test_audit_requires_both_kinds_of_edit_after_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "initial.kicad_pcb").write_text("initial")
            start = [22, 15, 0]
            c = {
                "starts": [start],
                "initial_boards_sha256": [harness.file_hash(d / "initial.kicad_pcb")],
            }
            events = [
                {},
                {"operation": "inspect"},
                {"result": {"status": "fail"}},
                {"operation": "place"},
                {},
                {"operation": "route"},
                {},
            ]

            def write(a):
                (d / "actions.jsonl").write_text("\n".join(json.dumps(v) for v in a))

            write(events)
            self.assertEqual(
                task.audit_combined(d, start, c)["edit_counts"],
                {"place": 1, "route": 1, "remove_route": 0},
            )
            for index, replacement in [
                (1, {"operation": "check"}),
                (2, {"result": {"status": "pass"}}),
                (3, {"operation": "route"}),
                (5, {"operation": "place"}),
            ]:
                a = copy.deepcopy(events)
                a[index] = replacement
                write(a)
                with self.assertRaises(ValueError):
                    task.audit_combined(d, start, c)

    def test_non_json_coordinate_is_rejected_without_mutation(self):
        contract = json.loads(task.CONTRACT.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "trial"
            task.prepare(directory, contract["starts"][0])
            session = task.Session(directory, contract)
            before = harness.file_hash(session.board)
            try:
                with self.assertRaises(ValueError):
                    session.call(
                        "place", {"x_mm": float("nan"), "y_mm": 10, "angle_deg": 90}
                    )
                self.assertEqual(harness.file_hash(session.board), before)
                self.assertEqual(session.edits, 0)
            finally:
                session.log.close()
