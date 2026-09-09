"""Routing-specific admission checks at the provider boundary."""

import copy
import unittest

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
