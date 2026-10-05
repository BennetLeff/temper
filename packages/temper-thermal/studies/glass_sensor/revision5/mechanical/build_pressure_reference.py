"""Unconnected dry apparatus dimension reference; no cartridge seal assertion."""

from __future__ import annotations

import json
import math
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent


def main() -> None:
    cavity_height = 10000 / (math.pi * 10**2)
    # Cold chamber displayed away from cartridge coordinates, not mounted to it.
    cavity = cq.Solid.makeCylinder(10, cavity_height, cq.Vector(40, 0, -cavity_height))
    shell = cq.Solid.makeCylinder(11, cavity_height + 2, cq.Vector(40, 0, -cavity_height - 1))
    shell = shell.cut(cavity)
    tube_bore = cq.Solid.makeCylinder(0.75, 100, cq.Vector(40, 0, 1))
    tube = cq.Solid.makeCylinder(1.5, 100, cq.Vector(40, 0, 1)).cut(tube_bore)
    # The central inlet connects tube to chamber; separate open dry-reference port.
    inlet = cq.Solid.makeCylinder(0.75, 1, cq.Vector(40, 0, 0))
    dry_reference = cq.Solid.makeCylinder(1, 1, cq.Vector(45, 0, 0))
    shell = shell.cut(inlet).cut(dry_reference)
    reference = cq.Compound.makeCompound([tube, shell])
    target = OUT / "R5-pressure-reference.step"
    cq.exporters.export(reference, str(target))
    imported = cq.importers.importStep(str(target)).solids().vals()
    checks = {
        "status": "REFERENCE_ONLY_UNCONNECTED_DRY_APPARATUS",
        "cold_chamber_cavity_volume_mm3": cavity.Volume(),
        "cold_chamber_cavity_volume_ml": cavity.Volume() / 1000,
        "tube_inner_diameter_mm": 1.5,
        "tube_outer_diameter_mm": 3,
        "tube_developed_length_mm": 100,
        "tube_bore_volume_mm3": tube_bore.Volume(),
        "open_dry_reference_port_diameter_mm": 2,
        "solid_valid": all(s.isValid() for s in (tube, shell)),
        "step_roundtrip_valid": bool(imported) and all(s.isValid() for s in imported),
        "tube_shell_overlap_mm3": tube.intersect(shell).Volume(),
        "cartridge_connection": "UNCONNECTED; placement and enclosure clearance not designed",
        "hot_cavity_volume": "NOT CAD ESTABLISHED; 1mL remains pressure-model assumption",
        "liquid_boundary": "NONE; dry reference port is open; not a selected or qualified liquid seal",
    }
    assert abs(cavity.Volume() - 10000) < 1e-7
    assert abs(tube_bore.Volume() - math.pi * 0.75**2 * 100) < 1e-7
    assert checks["solid_valid"] and checks["step_roundtrip_valid"]
    assert checks["tube_shell_overlap_mm3"] < 1e-7
    (OUT / "pressure_reference.json").write_text(json.dumps(checks, indent=2) + "\n")
    target.write_text("\n".join(line.rstrip() for line in target.read_text().splitlines()) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
