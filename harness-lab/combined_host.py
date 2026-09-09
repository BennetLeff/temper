"""Five-tool placement/routing profile with one shared edit budget."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import harness
import routing_host
from run_trials import require

ROOT = harness.ROOT
CONTRACT = ROOT / "fixtures/combined-contract.json"
ADAPTER = ROOT / "combined_native.py"
TOOLS = [dict(t) for t in routing_host.TOOLS]
TOOLS.insert(
    1,
    {
        **harness.TOOLS[1],
        "description": "Move only C9 to x_mm/y_mm and its native orientation. Existing tracks stay in place; no copper follows, disappears or is repaired. Returns native state and DRC deltas. Placement, routing and removal share ten total edits.",
    },
)
TOOLS[2]["description"] = TOOLS[2]["description"].replace(
    "Maximum ten routing edits including removals.",
    "Maximum ten total edits including placement and removals.",
)
TOOLS[-1]["description"] = (
    "Reload and check placement constraints, physical copper connectivity, all applicable KiCad DRC and protected state. Finish only after this returns pass."
)
INSTRUCTIONS = """Place and route this two-footprint PCB using only the five PCB tools.
Inspect first. Only C9's position and orientation (0,90,180,270) may move; U3 stays fixed.
Keep footprints inside the outline, without courtyard overlap. Both mapped pad-center distances must be at most 5 mm.
Connect C9.1 to U3.3 (+15V) and C9.2 to U3.1 (gnd) with actual copper. U3.5 shares +15V but must remain disconnected; connect no other pads.
Choose all poses and route vertices from native geometry and feedback. A place leaves all existing tracks in place: it does not move, remove or repair copper. A route replaces that net's tracks with exactly your polyline.
Honor the protected native track keepout. Tracks are straight, 0.25 mm F.Cu only, at most 22; no vias, arcs or zones. Keep copper inside the outline with 0.2 mm clearance.
There is ONE total budget of ten edits shared by place, route and remove_route, and five minutes for the whole task.
Use introduced/resolved findings to refine. Stop on indeterminate measurements. Finish with check returning pass and briefly report the measured outcome.
A pass covers this tiny placement and routing fixture only, not electrical or manufacturing approval.
"""
PROMPT = "Place C9 and route both required connections in this fixture using the admitted PCB tools. Start with inspect and finish with a passing check."


def prepare(directory: Path, start: list) -> None:
    contract = json.loads(CONTRACT.read_text())
    require(start in contract["starts"], "Unqualified combined start")
    index = contract["starts"].index(start)
    source = ROOT / "fixtures/e00pr" / str(index + 1)
    require(
        harness.file_hash(source / "candidate.kicad_pcb")
        == contract["initial_boards_sha256"][index],
        "Frozen combined board changed",
    )
    shutil.copytree(source, directory)
    shutil.copyfile(directory / "candidate.kicad_pcb", directory / "initial.kicad_pcb")


def evaluate(directory: Path, contract: dict, evidence: Path) -> dict:
    return harness.evaluate(directory, contract, evidence, adapter=ADAPTER)


def audit_combined(directory: Path, start: list, contract: dict) -> dict:
    events = [
        json.loads(line)
        for line in (directory / "actions.jsonl").read_text().splitlines()
    ]
    requests = events[1::2]
    index = contract["starts"].index(start)
    require(
        harness.file_hash(directory / "initial.kicad_pcb")
        == contract["initial_boards_sha256"][index],
        "Wrong combined start",
    )
    require(
        requests[0]["operation"] == "inspect"
        and events[2]["result"]["status"] == "fail",
        "Inspect the failing combined start first",
    )
    counts = {
        name: sum(r["operation"] == name for r in requests)
        for name in ("place", "route", "remove_route")
    }
    require(
        counts["place"] > 0 and counts["route"] > 0,
        "Both placement and routing must occur",
    )
    return {"start": start, "edit_counts": counts}


class Session(routing_host.Session):
    tools = TOOLS
    adapter = ADAPTER

    def apply(self, name: str, arguments: dict) -> None:
        if name == "place":
            harness.Session.apply(self, name, arguments)
        else:
            super().apply(name, arguments)

    def requirements(self) -> dict:
        result = super().requirements()
        result.pop("remaining_routing_edits")
        result.update(
            fixed_footprints=["U3"],
            editable="C9 position/orientation and admitted copper",
            maximum_mapped_pad_distance_mm=self.contract["max_pad_distance_mm"],
            remaining_total_edits=10 - self.edits,
            placement_leaves_tracks_unchanged=True,
        )
        return result


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
