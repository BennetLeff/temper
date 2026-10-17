"""Check the nominal top-first control-lid service sequence on saved R4 solids."""
from __future__ import annotations

import json
import sys
from math import cos, radians, sin
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import baseline_engine as b  # noqa: E402 -- local CAD module needs the path above.


def main() -> None:
    catalog = {p["name"]: p for p in json.loads((ROOT / "catalog.json").read_text())}

    def part(name: str) -> cq.Shape:
        return cq.importers.importStep(str(ROOT / catalog[name]["file"])).val()

    chamber = {
        name: part(name)
        for name in ("covered_PCB_tray_allocation", "PCB_chamber_lid_allocation")
    }
    chamber["historical_PCB_export"] = b.historical_pcb_world(
        cq.importers.importStep(str(ROOT / "inputs/current-pcb.step")).val()
    )
    moving = {
        name: part(name)
        for name in (
            "three_bend_front_top_rear_cover",
            "front_carrier_and_closed_sidewalls",
            "front_rear_lid",
        )
    }
    checked = []
    for travel in (1, 5, 26):
        hits = [
            {"moving": name, "stationary": other, "mm3": vol}
            for name, shape in moving.items()
            for other, obstacle in chamber.items()
            if (vol := b.base.overlap(shape.translate((0, 0, travel)), obstacle)) > 1e-4
        ]
        checked.append({"cover_lift_mm": travel, "hits": hits})

    rear_lid = moving["front_rear_lid"]
    travel = 5
    directly_pulled = rear_lid.translate(
        (0, travel * sin(radians(35)), -travel * cos(radians(35)))
    )
    direct_hits = [
        {"stationary": other, "mm3": vol}
        for other, obstacle in chamber.items()
        if (vol := b.base.overlap(directly_pulled, obstacle)) > 1e-4
    ]
    result = {
        "scope": "Saved nominal rigid geometry; sampled cover lift only. Disconnect, tools, hands, wires and seals require a mockup.",
        "top_first_cover_lift": checked,
        "direct_rear_lid_pull_5mm_hits": direct_hits,
        "status": "PASS_COMPUTED" if all(not item["hits"] for item in checked) and direct_hits else "FAIL",
    }
    (ROOT / "evidence/service-access.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS_COMPUTED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
