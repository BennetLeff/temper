"""Export a small, named STEP scene for the R4 chamber cross-section render."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import baseline_engine as b  # noqa: E402 -- local CAD module needs the path above.


def main() -> None:
    catalog = {p["name"]: p for p in json.loads((ROOT / "catalog.json").read_text())}
    assembly = cq.Assembly(name="r4_front_chamber_section")
    parts = (
        ("formed_front_sheet", "three_bend_front_top_rear_cover", (.72, .75, .73)),
        ("control_carrier", "front_carrier_and_closed_sidewalls", (.12, .16, .18)),
        ("control_rear_lid", "front_rear_lid", (.17, .23, .27)),
        ("pcb_chamber_walls", "covered_PCB_tray_allocation", (.48, .59, .67)),
        ("sloped_pcb_chamber_roof", "PCB_chamber_lid_allocation", (.55, .72, .80)),
    )
    for scene_name, source_name, color in parts:
        shape = cq.importers.importStep(str(ROOT / catalog[source_name]["file"])).val()
        assembly.add(shape, name=scene_name, color=cq.Color(*color))
    pcb = cq.importers.importStep(str(ROOT / "inputs/current-pcb.step")).val()
    board = b.historical_pcb_world(pcb.Solids()[-1])
    assembly.add(board, name="historical_pcb_substrate", color=cq.Color(.15, .38, .27))
    target = ROOT / "STEP/r4-chamber-section.step"
    assembly.export(str(target))
    print(target)


if __name__ == "__main__":
    main()
