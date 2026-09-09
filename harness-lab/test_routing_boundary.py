"""Routing-specific admission checks at the provider boundary."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import harness
import routing_host
from run_zen_trials import MODEL, configuration, normalize, validate_request


class RoutingBoundaryTests(unittest.TestCase):
    def test_routing_catalog_cannot_expand_or_fall_back_to_placement(self):
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
                for t in routing_host.TOOLS
            ],
        }
        validate_request(packet, routing_host.TOOLS)
        for changed in [
            packet["tools"][:-1],
            packet["tools"] + [packet["tools"][0]],
            [{"type": "function", "name": "pcb_place"}],
            [],
        ]:
            with self.subTest(catalog=changed), self.assertRaises(ValueError):
                validate_request({**packet, "tools": changed}, routing_host.TOOLS)
        with self.assertRaises(ValueError):
            validate_request(packet, harness.TOOLS)
        changed = copy.deepcopy(packet)
        changed["tools"][1]["parameters"]["properties"]["width_mm"] = {"type": "number"}
        with self.assertRaises(ValueError):
            validate_request(changed, routing_host.TOOLS)

    def test_routing_profile_has_no_placement_permissions_or_host(self):
        config = configuration(
            harness.ROOT / "unused", 1234, 9999, preflight=True, routing=True
        )
        self.assertEqual(
            config["permission"],
            {"*": "deny", **{"pcb_" + t["name"]: "allow" for t in routing_host.TOOLS}},
        )
        self.assertIn(
            str(harness.ROOT / "routing_host.py"), config["mcp"]["pcb"]["command"]
        )
        self.assertIn("--inspect-only", config["mcp"]["pcb"]["command"])
        event = {
            "type": "tool_use",
            "part": {
                "tool": "pcb_remove_route",
                "state": {
                    "status": "completed",
                    "input": {"net": "gnd"},
                    "output": "{}",
                },
            },
        }
        self.assertEqual(
            normalize([event], routing_host.TOOLS)[0]["item"]["tool"], "remove_route"
        )
        with self.assertRaises(ValueError):
            normalize([event])


class ObstacleProfileTests(unittest.TestCase):
    def test_obstacle_profile_selects_only_the_new_fixture(self):
        config = configuration(
            harness.ROOT / "unused",
            1234,
            9999,
            preflight=True,
            routing=True,
            routing_fixture="e00r-obstacle",
        )
        command = config["mcp"]["pcb"]["command"]
        self.assertEqual(command[command.index("--fixture") + 1], "e00r-obstacle")
        self.assertIn("--inspect-only", command)
        self.assertEqual(
            {name for name in config["permission"] if name != "*"},
            {"pcb_inspect", "pcb_route", "pcb_remove_route", "pcb_check"},
        )


class RepairProfileTests(unittest.TestCase):
    def test_each_start_copies_only_its_pinned_board(self):
        contract = json.loads(routing_host.CONTRACTS["e00r-repair"].read_text())
        with tempfile.TemporaryDirectory() as tmp:
            for start in contract["starts"]:
                directory = Path(tmp) / start
                routing_host.prepare(directory, start, fixture="e00r-repair")
                self.assertEqual(
                    harness.file_hash(directory / "candidate.kicad_pcb"),
                    contract["repair_cases"][start]["initial_board_sha256"],
                )
                self.assertEqual(
                    harness.context_hash(directory), contract["context_sha256"]
                )
                self.assertFalse((directory / "a").exists())
            for invalid in ["../a", "d", [6, 10, 90], None]:
                with self.subTest(start=invalid), self.assertRaises(ValueError):
                    routing_host.prepare(
                        Path(tmp) / "bad", invalid, fixture="e00r-repair"
                    )

    def test_changed_initial_bytes_are_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fixtures/e00r-repair/a"
            shutil.copytree(harness.ROOT / "fixtures/e00r-repair/a", source)
            with (source / "candidate.kicad_pcb").open("a") as stream:
                stream.write("\n")
            with (
                patch.object(routing_host, "ROOT", root),
                self.assertRaises(ValueError),
            ):
                routing_host.prepare(root / "trial", "a", fixture="e00r-repair")
            self.assertFalse((root / "trial").exists())

    def test_repair_audit_requires_observed_defect_route_and_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "initial.kicad_pcb").write_text("test fixture")
            contract = {
                "repair_cases": {
                    "a": {
                        "initial_board_sha256": harness.file_hash(
                            directory / "initial.kicad_pcb"
                        ),
                        "required_finding_prefix": "kicad:clearance:",
                    }
                }
            }
            defect = "kicad:clearance:track:pad"
            events = [
                {"kind": "session"},
                {"operation": "inspect"},
                {"result": {"status": "fail", "findings": [{"id": defect}]}},
                {"operation": "route"},
                {"result": {"resolved": [defect]}},
            ]

            def write(items):
                (directory / "actions.jsonl").write_text(
                    "\n".join(json.dumps(item) for item in items)
                )

            write(events)
            self.assertEqual(
                routing_host.audit_repair(directory, "a", contract)[
                    "resolved_defect_ids"
                ],
                [defect],
            )
            for index, replacement in [
                (1, {"operation": "check"}),
                (2, {"result": {"status": "pass", "findings": [{"id": defect}]}}),
                (2, {"result": {"status": "fail", "findings": []}}),
                (3, {"operation": "remove_route"}),
                (4, {"result": {"resolved": []}}),
            ]:
                changed = copy.deepcopy(events)
                changed[index] = replacement
                write(changed)
                with (
                    self.subTest(replacement=replacement),
                    self.assertRaises(ValueError),
                ):
                    routing_host.audit_repair(directory, "a", contract)
