"""Reproducible Temper packaging study; millimetres, not a manufacturing release.

Uses the exported production PCB as evidence, and labels proposed parts/envelopes.
Run with CadQuery 2.6.1 after the sensor and knob mechanism scripts exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
from itertools import permutations
from math import cos, radians, sin
import cadquery as cq

ROOT = Path(__file__).resolve().parents[2]


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


@dataclass(frozen=True)
class Part:
    name: str
    shape: cq.Shape
    color: tuple[float, float, float]
    group: str
    evidence: str = "proposed geometry"


def box(w: float, d: float, h: float, x: float, y: float, z: float) -> cq.Shape:
    return cq.Workplane("XY").box(w, d, h, centered=(True, True, False)).translate((x, y, z)).val()


def cylinder(radius: float, height: float, x: float, y: float, z: float) -> cq.Shape:
    return cq.Solid.makeCylinder(radius, height, cq.Vector(x, y, z))


def bounds(shape: cq.Shape) -> dict:
    b = shape.BoundingBox()
    return {"min": [round(v, 4) for v in (b.xmin, b.ymin, b.zmin)],
            "max": [round(v, 4) for v in (b.xmax, b.ymax, b.zmax)],
            "size": [round(v, 4) for v in (b.xlen, b.ylen, b.zlen)]}


def intersection(a: cq.Shape, b: cq.Shape) -> float:
    ba, bb = a.BoundingBox(), b.BoundingBox()
    if any(getattr(ba, k+"max") <= getattr(bb, k+"min") or
           getattr(bb, k+"max") <= getattr(ba, k+"min") for k in ("x", "y", "z")):
        return 0.0
    return round(a.intersect(b).Volume(), 5)


def export_step(parts: list[Part], name: str) -> dict:
    assembly = cq.Assembly(name=name.replace("-", "_"))
    for part in parts:
        if not part.shape.isValid() or part.shape.Volume() <= 0:
            raise ValueError(f"Invalid or empty {part.name}")
        assembly.add(part.shape, name=part.name, color=cq.Color(*part.color))
    path = ROOT / (name + ".step")
    assembly.export(str(path))
    reimported = cq.importers.importStep(str(path)).val()
    if not reimported.isValid():
        raise ValueError(f"Invalid STEP roundtrip: {name}")
    return {"file": path.name, "valid_reimport": True, "parts": len(parts),
            "solids": len(reimported.Solids()), "bbox_mm": bounds(reimported)}


def main() -> None:
    exterior = module("temper_exterior", ROOT / "src/reference/exterior.py")
    knob = module("temper_knob", ROOT / "src/reference/knob_original.py")
    sensor = module("temper_sensor", ROOT / "src/reference/sensor_original.py")
    p = exterior.Dimensions(**json.loads((ROOT / "inputs/exterior-parameters.json").read_text()))
    def front(s: cq.Shape) -> cq.Shape:
        return s.translate((110, 53, 0)).rotate((0, 0, 0), (1, 0, 0), 35).translate((0, 0, p.front_z))
    print("Building exterior", flush=True)
    parts: list[Part] = []
    removed = {"temperature_knob", "knob_fixed_collar", "knob_shaft_envelope", "knob_seal_envelope", "contact_sensor", "removable_base"}
    for old in exterior.build(p):
        if old.name in removed or old.group in ("pan", "probe"):
            continue
        shape = old.shape
        group = "exterior"
        if old.name == "upper_body":
            # Restore an uninterrupted outside face, then pocket from behind only.
            shape = shape.fuse(front(cylinder(5.01, 3.5, 0, 0, -3.5))).cut(front(knob.fascia_pocket()))
            group = "shell"
        elif old.name == "glass_placeholder":
            shape = shape.cut(cylinder(9, 12, 0, p.pan_y, 99))
            group = "glass"
        elif old.group == "graphics":
            group = "graphics"
        parts.append(Part(old.name, shape, old.color, group))
    # New base: the intake feeds the cooling compartment instead of the PCB chamber.
    base = exterior.rounded_box(361, 431, 3, 23.5, (0, 220, 8)).val()
    for y in (301, 312, 323, 334, 345, 356):
        slot = cq.Workplane("XY").workplane(offset=7).center(-45, y).slot2D(110, 6).extrude(5).val()
        base = base.cut(slot)
    base = base.cut(cylinder(22, 5, 0, 261, 7))
    cover = cylinder(27, 2, 0, 261, 6)
    for x in (-24.5, 24.5):
        hole = cylinder(1.7, 8, x, 261, 5)
        cover = cover.cut(hole)
        base = base.cut(hole)
    parts += [Part("base_with_rear_intake_and_sensor_hatch", base, (.18, .20, .21), "base"),
              Part("sensor_service_hatch", cover, (.30, .32, .33), "base")]
    print("Importing actual PCB geometry", flush=True)
    pcb_path = ROOT / "inputs/current-pcb.step"
    pcb = cq.importers.importStep(str(pcb_path)).val()
    pcb_normal = pcb.translate((-90, 137, 0))
    def board_at(s: cq.Shape, angle: float, y: float) -> cq.Shape:
        return s.rotate((0, 0, 0), (0, 0, 1), angle).translate((0, y, 30.25))
    # Missing PS1 export model: manufacturer body envelope, separate from actual export.
    # PCB export top surface is Z=0; body is allowed a conservative 1.6 mm seat offset.
    ps1 = box(25.4, 45.7, 21.5, 105.575-90, -105.78+137, 1.6)
    actual = board_at(pcb_normal, 90, 154)
    for i, solid in enumerate(pcb_normal.Solids()):
        b = solid.BoundingBox()
        is_board = b.xlen > 150 and b.ylen > 220 and b.zlen < 2
        color = (.12, .32, .23) if is_board else ((.28, .30, .31) if solid.Volume() > 150 else (.62, .65, .64))
        parts.append(Part(f"pcb_export_{i:03}", board_at(solid, 90, 154), color, "pcb", "KiCad source export"))
    parts.append(Part("PS1_datasheet_body_envelope", board_at(ps1, 90, 154), (.39, .48, .51), "pcb", "missing model: official body dimensions only"))

    # A closed packaging allocation around the PCB; wire glands, mounting and thermal
    # interface still require component selection. No pollution-degree claim is made.
    chamber = box(265, 177, 59, 9.5, 154, 13).cut(box(262, 174, 60, 9.5, 154, 14.5))
    lid = box(265, 177, 1.5, 9.5, 154, 72)
    # A shallow folded front roof follows the underside of the flush control
    # cassette. It leaves the chamber covered over the imported historical PCB,
    # instead of removing the front wall or omitting its lid to hide collisions.
    # Y here precedes baseline_engine's -4 mm PCB/barrier placement correction.
    # At y=100 the roof joins the original z=72..73.5 lid without a step.
    front_y, join_y = 65.5, 100.0
    def roof_top(y: float) -> float:
        return .7*y + 3.5
    def yz_prism(points):
        return cq.Workplane('YZ', origin=(-123,0,0)).polyline(points).close().extrude(265).val()
    trim = yz_prism([(front_y,roof_top(front_y)-1.5),
                     (join_y,72), (join_y,75), (front_y,75)])
    chamber = chamber.cut(trim)
    lid = lid.cut(box(267,join_y-front_y,4,9.5,(front_y+join_y)/2,71))
    front_roof = yz_prism([(front_y,roof_top(front_y)-1.5),
                            (join_y,72), (join_y,73.5),
                            (front_y,roof_top(front_y))])
    lid = lid.fuse(front_roof).clean()
    parts += [Part("covered_PCB_tray_allocation", chamber, (.47, .55, .59), "barrier", "Folded front roof and sidewalls nominally enclose historical PCB; seams, mounts, glands and material unresolved"),
              Part("PCB_chamber_lid_allocation", lid, (.47, .55, .59), "barrier", "Nominal shallow front roof joined to original lid; fold/seam process and protection unqualified")]
    # Coil OD from issued specification; ID, height, ferrites and bracket are envelopes.
    coil = cylinder(100, 5, 0, 261, 93).cut(cylinder(22, 7, 0, 261, 92))
    ferrite = cylinder(100, 5, 0, 261, 88).cut(cylinder(22, 7, 0, 261, 87))
    bracket = cylinder(104, 3, 0, 261, 85).cut(cylinder(19, 5, 0, 261, 84))
    # Flange top is Z=86. It bolts upward into this independent support ring.
    support = cylinder(20, 5, 0, 261, 86).cut(cylinder(10.2, 7, 0, 261, 85))
    for angle in (0, 120, 240):
        x, y = 12.5*cos(radians(angle)), 261+12.5*sin(radians(angle))
        support = support.cut(cylinder(1.25, 7, x, y, 85))
    bracket = bracket.fuse(support)
    parts += [Part("coil_200OD_44ID_envelope", coil, (.61, .32, .16), "coil", "OD<=200 specified; ID/height provisional"),
              Part("ferrite_allocation", ferrite, (.21, .23, .25), "coil", "provisional ferrite volume"),
              Part("coil_support_with_bolted_sensor_carrier", bracket, (.56, .59, .51), "coil", "proposed G10 support allocation; three M2.5 holes on 25 mm circle")]
    # Fan orientation and the proposed compact sink are geometry, not a thermal result.
    fan = box(60, 25, 60, -45, 411, 22)
    bore = cq.Solid.makeCylinder(27, 27, cq.Vector(-45, 397.5, 52), cq.Vector(0, 1, 0))
    fan = fan.cut(bore)
    hub = cq.Solid.makeCylinder(11, 22, cq.Vector(-45, 400, 52), cq.Vector(0, 1, 0))
    parts += [Part("Sunon_60x60x25_frame_envelope", fan, (.16, .18, .19), "cooling", "BOM size; mounting details illustrative"),
              Part("fan_hub_envelope", hub, (.21, .23, .24), "cooling", "illustrative hub")]
    sink = box(120, 100, 5, -45, 336, 20)
    for x in range(-102, 13, 8):
        sink = sink.fuse(box(1.5, 100, 35, x, 336, 25))
    parts.append(Part("compact_sink_candidate_120x100x40", sink, (.55, .58, .60), "cooling", "unselected thermal candidate; no connection to PCB power devices"))
    duct = box(128, 151, 68, -45, 358.5, 12).cut(box(125, 153, 66.5, -45, 358.5, 12))
    # Keep a top; open the lower face onto intake slots. A reducer mates to rear grille.
    duct = duct.cut(box(62, 30, 65, -45, 411, 21))
    parts.append(Part("separate_rear_cooling_duct", duct, (.48, .57, .61), "duct", "packaging envelope; pressure/spill behavior untested"))
    # Conservative service cylinder, including extraction below the case.
    service = cylinder(18, 126, 0, 261, -40)
    parts.append(Part("sensor_downward_service_keepout", service, (.27, .68, .61), "keepout", "reserved extraction volume; fastener access separately required"))
    rejected = box(120, 125, 135.8, -45, 344, 12)
    parts.append(Part("BOM_HS1_392_120AB_rejected_envelope", rejected, (.80, .25, .18), "rejected", "BOM + manufacturer dimensional envelope"))

    return parts
