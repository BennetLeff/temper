"""PR1 CadQuery adaptation of the frozen study input. No physical qualification.

Mechanical/thermal parameters come from selected.rs's generated JSON. Python
only constructs CAD, checks intersections and writes CAD/geometry outputs.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import ModuleType
import cadquery as cq

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / "inputs" / "mechanism.py.txt"
base = ModuleType("frozen_mechanism")
base.__file__ = str(SOURCE)
sys.modules[base.__name__] = base
exec(compile(SOURCE.read_text(), str(SOURCE), "exec"), base.__dict__)
base.OUT = OUT
P = json.loads((OUT / "cad-parameters.json").read_text())


def build(travel: float, maximum_chip: bool = False) -> list:
    """Retain carrier datum/fasteners; replace moving stack and spring seats."""
    parts = base.build(travel)
    changed = []
    chip = P["chip_max_mm"] if maximum_chip else P["chip_mm"]
    roof = 0.20 if maximum_chip else P["roof_mm"]
    bond = 0.15 if maximum_chip else P["bond_mm"]
    underside = P["height_mm"] - roof
    for part in parts:
        name, shape, envelope = part.name, part.shape, part.envelope
        if name == "contact_cap":
            shape = (cq.Workplane("XY").workplane(offset=underside).circle(5).extrude(roof)
                     .union(base.ring(5, 4.6, -1.4, underside + 1.4))).val()
            name = "PR1_custom_316L_cap"
        elif name == "dielectric_bond":
            shape = cq.Workplane("XY").box(2.7, 2.5, bond).translate((0, 0, underside-bond/2)).val()
            name = "PR1_Resbond908_bond_process_candidate"
        elif name == "PT100_element":
            shape = cq.Workplane("XY").box(*chip).translate((0, 0, underside-bond-chip[2]/2)).val()
            name = "Yageo_M222_32208550_body"
        elif name == "hollow_insulating_plunger_with_capture_groove":
            stem = base.ring(3, 1.4, -15, 13).union(base.ring(1.8, 1.4, -19, 4))
            stem = stem.union(base.ring(4.8, 1.4, -2, .6))
            stem = stem.cut(base.ring(3.1, 2.7, -14.75, .75))
            # Worst-case chip bottoms at -0.95; head top -1.4 leaves 0.45mm.
            shape = stem.val()
            name = "PR1_plunger_lower_stem3p6"
        elif name == "lower_spring_cap":
            # Existing central pedestal top was -28; lower it 0.45 to seat exact spring.
            cutter = cq.Workplane("XY").workplane(offset=-28.45).circle(5.3).extrude(.46)
            shape = shape.cut(cutter.val())
            name = "PR1_lower_cap_spring_seat_z_minus28p45"
        elif name == "four_wire_slack_and_exit_ENVELOPE":
            lead = cq.Workplane("XY").workplane(offset=-19-travel).circle(.5).extrude(17.8)
            curve = cq.Workplane("XZ").moveTo(0, -19-travel).spline([(.7, -22), (-.7, -25), (0, -28)], includeCurrent=True).val()
            loop = cq.Workplane("XY").workplane(offset=-19-travel).circle(.5).sweep(cq.Wire.assembleEdges([curve]), isFrenet=True)
            shape = lead.union(loop).union(cq.Workplane("XY").workplane(offset=-49).circle(.5).extrude(21)).val()
            name = "PR1_four_wire_slack_ENVELOPE_1mm_bundle"
        elif name == "compression_spring_ENVELOPE":
            length = P["spring_installed_mm"] - travel
            shape = base.ring(2.3, 2.0, P["spring_bottom_z_mm"], length).val()
            name = "C01800120560X_INSTALLED_ENVELOPE_not_wire"
            envelope = True
        if name != part.name and part.moving:
            shape = shape.translate((0, 0, -travel))
        changed.append(base.Part(name, shape, part.color, part.moving, envelope))
    return changed


def main() -> None:
    report = {"status": "nominal fit and selected chip maximum only; custom seal not qualified", "states": {}, "spring_seat_z_mm": [-28.45, -15.0], "spring_installed_mm": 13.45, "maximum_chip_body_mm": P["chip_max_mm"], "spring_wire_geometry": "manufacturer envelope only; supplier turns/end geometry not available", "lead_routing": "reserved envelope only; M222 lead forming/welding procedure unqualified", "detector": "no selected detector added; lower spring seat optional FORCE CHARACTERIZATION fixture only; jam can spoof contact"}
    for tag, travel, maximum in [("rest", 0., False), ("flat_pan", .6, False), ("full_stroke", 1.2, False), ("max_chip_full_stroke", 1.2, True)]:
        parts = build(travel, maximum)
        report["states"][tag] = base.save(parts, "PR1-"+tag, individual=(tag == "rest"))
        cap = next(p for p in parts if p.name == "PR1_custom_316L_cap")
        report["states"][tag]["cap_volume_mm3"] = cap.shape.Volume()
        spring = next(p for p in parts if p.name.startswith("C018"))
        wire = next(p for p in parts if p.name.startswith("PR1_four_wire"))
        stem = next(p for p in parts if p.name.startswith("PR1_plunger"))
        report["states"][tag]["spring_wire_overlap_mm3"] = spring.shape.intersect(wire.shape).Volume()
        report["states"][tag]["spring_stem_overlap_mm3"] = spring.shape.intersect(stem.shape).Volume()
    section_box = cq.Workplane("XY").box(80, 40, 160, centered=(True, False, True)).val()
    sections = []
    for part in build(0.):
        shape = part.shape.intersect(section_box)
        if shape.Volume() > 1e-7:
            sections.append(base.Part(part.name, shape, part.color, part.moving, part.envelope))
    report["section"] = base.save(sections, "PR1-section")
    (OUT / "geometry-checks.json").write_text(json.dumps(report, indent=2)+"\n")
    # SVG is an actual OCC projection of the selected assembly section.
    compound = cq.Compound.makeCompound([p.shape for p in sections])
    cq.exporters.export(compound, str(OUT / "PR1-section.svg"), opt={"width": 650, "height": 800, "projectionDir": (0, -1, 0), "showAxes": False, "showHidden": False})
    for path in [*OUT.glob("*.step"), *OUT.glob("parts/*.step"), OUT / "PR1-section.svg", OUT / "results/tests.txt"]:
        if path.exists():
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()).rstrip()+"\n")
    print(json.dumps(report, indent=2))
    assert all(s["all_valid"] and s["roundtrip_all_valid"] and not s["rigid_overlaps"] and s["spring_wire_overlap_mm3"] < 1e-6 and s["spring_stem_overlap_mm3"] < 1e-6 for s in report["states"].values())


if __name__ == "__main__":
    main()
