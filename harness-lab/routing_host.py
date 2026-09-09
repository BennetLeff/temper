"""Four-tool routing task, sharing the qualified host's recorder and DRC path."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from pathlib import Path

import harness

ROOT = harness.ROOT
ADAPTER = ROOT / "routing_native.py"
CONTRACT = ROOT / "fixtures/routing-contract.json"
NET_SCHEMA = {"type": "string", "enum": ["+15V", "gnd"]}
TOOLS = [
    {
        "name": "inspect",
        "description": "Read native pad geometry, tracks, physical connectivity, constraints and findings. Coordinates are mm; x right, y down.",
        "inputSchema": harness.EMPTY_SCHEMA,
    },
    {
        "name": "route",
        "description": "Replace one net's tracks with exactly this polyline of 2–12 explicit vertices. Fixed 0.25 mm width on F.Cu. No snapping or routing search. Returns native connectivity and DRC deltas. Maximum ten routing edits including removals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "net": NET_SCHEMA,
                "points_mm": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 12,
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
            },
            "required": ["net", "points_mm"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remove_route",
        "description": "Remove all tracks for the selected net and return native connectivity and DRC deltas. Counts as one routing edit.",
        "inputSchema": {
            "type": "object",
            "properties": {"net": NET_SCHEMA},
            "required": ["net"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check",
        "description": "Reload and check physical copper connectivity, full applicable KiCad DRC, fixed placement, protected state and routing constraints. Finish only after this returns pass.",
        "inputSchema": harness.EMPTY_SCHEMA,
    },
]
INSTRUCTIONS = """You are routing a frozen two-footprint PCB fixture. Only the four PCB tools are available.
Inspect first. Connect C9.1 to U3.3 (+15V) and C9.2 to U3.1 (gnd) with actual copper.
U3.5 is also +15V but must remain disconnected; connect no other pads.
Choose every route vertex yourself from native geometry and feedback. Footprints are fixed.
Tracks are straight, 0.25 mm wide, F.Cu only; no vias, arcs or zones. Keep copper inside the outline with 0.2 mm clearance.
At most ten routing edits (including removals), five minutes. A route replaces all existing tracks on that net.
Refine using introduced/resolved findings. Stop and report any indeterminate measurement. Finish with check returning pass, then briefly report the measured outcome.
A pass covers this tiny routing task only, not electrical or manufacturing approval.
"""
PROMPT = "Route the two capacitor connections in this fixture using the admitted PCB tools and finish with a passing check."


def prepare(directory: Path, start: list) -> None:
    # All three repetitions share geometry; separate sessions test repeatability.
    if start != [6, 10, 90]:
        raise ValueError("Unqualified routing start")
    contract = json.loads(CONTRACT.read_text())
    if (
        harness.file_hash(ROOT / "fixtures/e00r/candidate.kicad_pcb")
        != contract["initial_board_sha256"]
    ):
        raise ValueError("Frozen initial routing board changed")
    shutil.copytree(ROOT / "fixtures/e00r", directory)
    shutil.copyfile(directory / "candidate.kicad_pcb", directory / "initial.kicad_pcb")


def evaluate(directory: Path, contract: dict, evidence: Path) -> dict:
    return harness.evaluate(directory, contract, evidence, adapter=ADAPTER)


class Session(harness.Session):
    tools = TOOLS
    adapter = ADAPTER

    def apply(self, name: str, arguments: dict) -> None:
        if name in ("inspect", "check") and not arguments:
            return
        expected = {"route": {"net", "points_mm"}, "remove_route": {"net"}}
        if name not in expected or set(arguments) != expected[name]:
            raise ValueError("Unknown routing operation or unexpected arguments")
        if arguments["net"] not in ("+15V", "gnd"):
            raise ValueError("Only +15V and gnd routes are admitted")
        points = arguments.get("points_mm", [])
        if name == "route":
            if not isinstance(points, list) or not 2 <= len(points) <= 12:
                raise ValueError("A route needs 2–12 vertices")
            for point in points:
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(
                        type(v) not in (float, int)
                        or not math.isfinite(v)
                        or abs(v) > 100
                        for v in point
                    )
                ):
                    raise ValueError(
                        "Vertices must contain two finite coordinates within native range"
                    )
        if self.edits >= 10:
            raise ValueError("Ten-routing-edit budget exhausted")
        self.edits += 1
        staging = self.directory / "next.kicad_pcb"
        shutil.copyfile(self.board, staging)
        harness.native(
            "route", staging, arguments["net"], json.dumps(points), adapter=ADAPTER
        )
        os.replace(staging, self.board)
        self.last_hash = harness.file_hash(self.board)

    def requirements(self) -> dict:
        return {
            "fixed_footprints": ["U3", "C9"],
            "required_connections": ["C9.1 -> U3.3 (+15V)", "C9.2 -> U3.1 (gnd)"],
            "no_other_pad_connections": True,
            "outline_mm": self.contract["outline_mm"],
            "width_mm": 0.25,
            "layer": "F.Cu",
            "minimum_clearance_mm": 0.2,
            "maximum_tracks": 22,
            "remaining_routing_edits": 10 - self.edits,
        }


class InspectionSession(Session):
    def apply(self, name: str, arguments: dict) -> None:
        if name != "inspect" or arguments:
            raise ValueError("Only inspect is enabled during preflight")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    session_type = InspectionSession if args.inspect_only else Session
    harness.serve(
        session_type(args.directory, json.loads(CONTRACT.read_text()), args.deadline)
    )
