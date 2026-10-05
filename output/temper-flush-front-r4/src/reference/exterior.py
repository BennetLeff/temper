"""Temper B: parametric, unpowered ergonomic mockup. All dimensions in mm.

Run with CadQuery 2.6.1: python model.py --parameters parameters.json
The JSON is the dimensional source; STEP is a neutral solid-model export.
This standalone CAD artifact does not model production internals or seals.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from math import cos, radians, sin, tan
from pathlib import Path

import cadquery as cq


@dataclass(frozen=True)
class Dimensions:
    width: float
    depth: float
    top_height: float
    foot_height: float
    corner_radius: float
    edge_radius: float
    wall: float
    front_depth: float
    front_angle_deg: float
    glass_width: float
    glass_depth: float
    glass_thickness: float
    glass_front: float
    glass_radius: float
    glass_gap: float
    pan_diameter: float
    pan_base_diameter: float
    pan_height: float
    handle_angle_deg: float
    knob_diameter: float
    knob_projection: float
    knob_gap: float
    knob_flute_count: int
    knob_flute_depth: float
    probe_port_y: float
    probe_port_z: float
    exhaust_width: float
    exhaust_height: float
    exhaust_center_x: float
    exhaust_offset_from_top: float
    exhaust_slot_count: int
    exhaust_slot_width: float
    exhaust_slot_length: float
    exhaust_slot_pitch: float

    @property
    def front_z(self) -> float:
        return self.top_height - self.front_depth * tan(radians(self.front_angle_deg))

    @property
    def pan_y(self) -> float:
        return self.glass_front + self.glass_depth / 2

    def validate(self) -> None:
        if not 2.5 <= self.knob_gap <= 5 or self.knob_projection-self.knob_gap < 15:
            raise ValueError("Knob mockup needs collar clearance and at least 15 mm grip depth")
        if not 24 <= self.knob_flute_count <= 64 or not .2 <= self.knob_flute_depth <= .8:
            raise ValueError("Knob fluting is outside this mockup's shallow-grip range")
        if not 20 <= self.front_angle_deg <= 45:
            raise ValueError("Mockup front angle must be between 20 and 45 degrees")
        if self.front_z < self.foot_height + 12:
            raise ValueError("Insufficient front lip height: increase height or reduce front angle/depth")
        if self.glass_width + 2 * self.glass_gap >= self.width - 2 * self.wall:
            raise ValueError("Glass does not leave enough perimeter support")
        if self.glass_front < self.front_depth + 5:
            raise ValueError("Glass overlaps the rounded front transition")
        if self.glass_front + self.glass_depth > self.depth - 5:
            raise ValueError("Glass extends too close to rear edge")
        if self.pan_diameter > min(self.glass_width, self.glass_depth):
            raise ValueError("Pan rim extends outside the nominal glass envelope")
        if not 0 < self.pan_base_diameter < self.pan_diameter:
            raise ValueError("Pan base diameter must be smaller than rim")
        port_top = min(self.top_height, self.front_z + self.probe_port_y * tan(radians(self.front_angle_deg)))
        if not self.foot_height + 14 < self.probe_port_z < port_top - 14:
            raise ValueError("Probe port does not fit vertically in the side wall")
        vent_z = self.top_height-self.exhaust_offset_from_top
        if vent_z-self.exhaust_height/2 < self.foot_height+8:
            raise ValueError("Rear exhaust extends too close to the base")
        if self.exhaust_offset_from_top-self.exhaust_height/2 < self.glass_thickness+8:
            raise ValueError("Rear exhaust extends into the glass support")
        if ((self.exhaust_slot_count-1)*self.exhaust_slot_pitch+self.exhaust_slot_width
                > self.exhaust_width-8 or self.exhaust_slot_length > self.exhaust_height-6):
            raise ValueError("Exhaust slots extend outside their opening")


@dataclass(frozen=True)
class Component:
    name: str
    shape: cq.Shape
    color: tuple[float, float, float]
    group: str = "cooker"
    printable: bool = False


BODY = (0.79, 0.80, 0.81)
METAL = (0.72, 0.74, 0.74)
GLASS = (0.065, 0.080, 0.085)
DARK = (0.055, 0.060, 0.060)
INK = (0.80, 0.85, 0.83)


def rounded_box(width: float, depth: float, height: float, radius: float,
                center: tuple[float, float, float]) -> cq.Workplane:
    return (cq.Workplane("XY").box(width, depth, height, centered=(True, True, False))
            .edges("|Z").fillet(radius).translate(center))


def sloped_volume(p: Dimensions, inset: float, bottom: float, top: float) -> cq.Workplane:
    front = p.front_z - inset / cos(radians(p.front_angle_deg))
    transition = (top - front) / tan(radians(p.front_angle_deg))
    return (cq.Workplane("YZ").polyline([
        (inset, bottom), (p.depth - inset, bottom),
        (p.depth - inset, top), (transition, top),
        (inset, front + inset * tan(radians(p.front_angle_deg))),
    ]).close().extrude(p.width, both=True))


def build(p: Dimensions) -> list[Component]:
    p.validate()
    parts: list[Component] = []

    def add(name: str, solid: cq.Workplane | cq.Shape,
            color: tuple[float, float, float], group: str = "cooker", printable: bool = False) -> None:
        shape = solid.val() if isinstance(solid, cq.Workplane) else solid
        if not shape.isValid() or shape.Volume() <= 0:
            raise ValueError(f"Invalid or empty CAD component: {name}")
        parts.append(Component(name, shape, color, group, printable))

    outer = rounded_box(p.width, p.depth, p.top_height - p.foot_height,
                        p.corner_radius, (0, p.depth / 2, p.foot_height))
    outer = outer.intersect(sloped_volume(p, 0, p.foot_height, p.top_height)).edges().fillet(p.edge_radius)
    inner = rounded_box(p.width - 2*p.wall, p.depth - 2*p.wall,
                        p.top_height - p.wall + 3, p.corner_radius-p.wall, (0, p.depth/2, -3))
    inner = inner.intersect(sloped_volume(p, p.wall, -3, p.top_height-p.glass_thickness-2))
    shell = outer.cut(inner)
    # A shallow locating recess and a smaller through aperture leave a glass ledge.
    recess = rounded_box(p.glass_width+2*p.glass_gap, p.glass_depth+2*p.glass_gap,
                         12, p.glass_radius+p.glass_gap,
                         (0, p.pan_y, p.top_height-p.glass_thickness))
    aperture = rounded_box(p.glass_width-12, p.glass_depth-12, 25, p.glass_radius-6,
                           (0, p.pan_y, p.top_height-20))
    shell = shell.cut(recess).cut(aperture)

    a = radians(p.front_angle_deg)
    front_plane = cq.Plane(origin=(0, 0, p.front_z), xDir=(1, 0, 0), normal=(0, -sin(a), cos(a)))

    def front_shape(u: float, v: float, width: float, height: float,
                    thickness: float, offset: float = 0, radius: float = 0) -> cq.Workplane:
        local = cq.Workplane("XY").box(width, height, thickness, centered=(True, True, False))
        if radius:
            local = local.edges("|Z").fillet(radius)
        return local.translate((u, v, offset)).rotate((0, 0, 0), (1, 0, 0), p.front_angle_deg).translate((0, 0, p.front_z))

    display_cut = front_shape(-35, 66, 108, 40, 14, -10, 3)
    shell = shell.cut(display_cut)
    add("display_window", front_shape(-35, 66, 107.2, 39.2, 2, -1, 3), GLASS, printable=True)
    for index, u in enumerate((-75, -47, -19, 9)):
        hole = cq.Workplane(front_plane).center(u, 27).circle(6.9).extrude(-12)
        shell = shell.cut(hole)
        add(f"button_{index+1}", cq.Workplane(front_plane).center(u, 27).circle(6.5).extrude(2), METAL, printable=True)
    knob_hole = cq.Workplane(front_plane).center(110, 53).circle(5).extrude(-12)
    shell = shell.cut(knob_hole)
    def knob_world(shape: cq.Workplane | cq.Shape) -> cq.Shape:
        solid = shape.val() if isinstance(shape, cq.Workplane) else shape
        return (solid.translate((110, 53, 0))
                .rotate((0, 0, 0), (1, 0, 0), p.front_angle_deg)
                .translate((0, 0, p.front_z)))

    # Removable-cap study. Local Z is normal to the inclined fascia.
    # The gap is rotational/press clearance, not a cloth-access claim.
    grip_height = p.knob_projection-p.knob_gap
    knob = (cq.Workplane("XY").workplane(offset=p.knob_gap)
            .circle(p.knob_diameter/2).extrude(grip_height).edges().fillet(1.4))
    cutter_radius = 1.4
    flute_radius = p.knob_diameter/2+cutter_radius-p.knob_flute_depth
    low, high = p.knob_gap+4, p.knob_projection-4
    cutters = []
    for i in range(p.knob_flute_count):
        angle = radians(i*360/p.knob_flute_count)
        x, y = flute_radius*cos(angle), flute_radius*sin(angle)
        groove = cq.Solid.makeCylinder(cutter_radius, high-low, cq.Vector(x, y, low))
        groove = groove.fuse(cq.Solid.makeSphere(cutter_radius, cq.Vector(x, y, low), angleDegrees1=-90),
                             cq.Solid.makeSphere(cutter_radius, cq.Vector(x, y, high), angleDegrees1=-90))
        cutters.append(groove)
    knob = knob.cut(cq.Compound.makeCompound(cutters))
    # D-shaped socket and shaft are fit envelopes; retention is not designed.
    socket = cq.Workplane("XY").workplane(offset=p.knob_gap-.1).circle(3.25).extrude(10)
    socket = socket.intersect(cq.Workplane("XY").box(20, 20, 30, centered=(False, True, False)).translate((-2.65, 0, 0)))
    knob = knob.cut(socket)
    add("temperature_knob", knob_world(knob), METAL, printable=True)
    collar = cq.Workplane("XY").circle(9).extrude(1.5).edges(">Z").fillet(.9)
    collar = collar.cut(cq.Workplane("XY").circle(3.9).extrude(3))
    add("knob_fixed_collar", knob_world(collar), METAL, printable=True)
    shaft = cq.Workplane("XY").workplane(offset=-4).circle(3).extrude(15.5)
    shaft = shaft.intersect(cq.Workplane("XY").box(20, 20, 25, centered=(False, True, False)).translate((-2.4, 0, -5)))
    add("knob_shaft_envelope", knob_world(shaft), METAL)
    seal = cq.Workplane("XY").workplane(offset=.7).circle(3.85).circle(3.05).extrude(.7)
    add("knob_seal_envelope", knob_world(seal), DARK)
    # Graphic ink is separate geometry, so the solid-model exports stay inspectable.
    font = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_options = {"fontPath": font} if Path(font).exists() else {}
    for name, text, u, v, size, color in [
        ("brand", "temper", -135, 67, 7, DARK),
        ("target", "180 C", -43, 70, 10, INK),
        ("actual", "PAN 176 C", -43, 56, 4.5, INK),
        ("back_label", "BACK", -75, 14, 3.5, DARK),
        ("minus_label", "-", -47, 14, 4.5, DARK),
        ("plus_label", "+", -19, 14, 4.5, DARK),
        ("stop_label", "STOP", 9, 14, 3.5, DARK),
    ]:
        offset = 1.1 if name in ("target", "actual") else 0.1
        ink = cq.Workplane(front_plane).workplane(offset=offset).center(u, v).text(text, size, .05, combine=False, **font_options)
        add(name, cq.Compound.makeCompound(ink.vals()), color, "graphics")

    port_plane = cq.Plane(origin=(p.width/2, p.probe_port_y, p.probe_port_z), xDir=(0, 1, 0), normal=(1, 0, 0))
    shell = shell.cut(cq.Workplane(port_plane).circle(6.5).extrude(-12))
    add("probe_port_bezel", cq.Workplane(port_plane).circle(9).circle(6).extrude(1.8), METAL)
    add("probe_port_socket", cq.Workplane(port_plane).workplane(offset=-4).circle(6).extrude(.8), DARK)
    # Generic inlet envelope; deliberately not an asserted IEC part/cutout.
    rear_plane = cq.Plane(origin=(p.width/2-50, p.depth, 34), xDir=(1, 0, 0), normal=(0, 1, 0))
    rear_cut = cq.Workplane(rear_plane).rect(34, 24).extrude(-12)
    shell = shell.cut(rear_cut)
    add("rear_power_inlet_envelope", cq.Workplane(rear_plane).rect(39, 29).extrude(1.5), DARK)
    # Actual openings for a provisional airflow arrangement. Fan/duct performance
    # and spill/ingress protection remain unqualified at this mockup stage.
    vent_center = (p.exhaust_center_x, p.depth, p.top_height-p.exhaust_offset_from_top)
    vent_opening = rounded_box(p.exhaust_width, p.exhaust_height, 16, 4, (0, 0, -12))
    vent_opening = vent_opening.rotate((0, 0, 0), (1, 0, 0), -90).translate(vent_center)
    shell = shell.cut(vent_opening)
    grille = rounded_box(p.exhaust_width+6, p.exhaust_height+6, 1.5, 5, (0, 0, 0))
    for i in range(p.exhaust_slot_count):
        u = (i-(p.exhaust_slot_count-1)/2)*p.exhaust_slot_pitch
        slot = (cq.Workplane("XY").workplane(offset=-1).center(u, 0)
                .slot2D(p.exhaust_slot_length, p.exhaust_slot_width, 90).extrude(4))
        grille = grille.cut(slot)
    grille = grille.rotate((0, 0, 0), (1, 0, 0), -90).translate(vent_center)
    add("rear_exhaust_grille", grille, (.14, .15, .14), printable=True)
    add("upper_body", shell, BODY, printable=True)
    base = rounded_box(p.width-9, p.depth-9, 3, p.corner_radius-4.5, (0, p.depth/2, p.foot_height))
    for i in range(6):
        intake = (cq.Workplane("XY").workplane(offset=p.foot_height-1)
                  .center(0, 115+i*9).slot2D(160, 5).extrude(5))
        base = base.cut(intake)
    add("removable_base", base, DARK, printable=True)
    foot_x = p.width/2-35
    for i, (x, y) in enumerate(((-foot_x, 36), (foot_x, 36), (-foot_x, p.depth-36), (foot_x, p.depth-36))):
        add(f"foot_{i+1}", cq.Workplane("XY").center(x, y).circle(13).extrude(p.foot_height), DARK, printable=True)
    glass = rounded_box(p.glass_width, p.glass_depth, p.glass_thickness, p.glass_radius,
                        (0, p.pan_y, p.top_height-p.glass_thickness))
    glass = glass.cut(cq.Workplane("XY").center(0, p.pan_y).circle(6.3).extrude(p.top_height+10))
    add("glass_placeholder", glass, GLASS, printable=True)
    add("contact_sensor", cq.Workplane("XY").workplane(offset=p.top_height-p.glass_thickness)
        .center(0, p.pan_y).circle(6).extrude(p.glass_thickness+.5), METAL, printable=True)
    # Ring is a pan-placement guide only; it does not claim an induction coil diameter.
    add("placement_ring", cq.Workplane("XY").workplane(offset=p.top_height+.03)
        .center(0, p.pan_y).circle(150).circle(149.6).extrude(.02), (.22, .25, .25), "graphics")

    pan = (cq.Workplane("XY").workplane(offset=p.top_height+.6).center(0, p.pan_y)
           .circle(p.pan_base_diameter/2).workplane(offset=p.pan_height)
           .circle(p.pan_diameter/2).loft(combine=True))
    cavity = (cq.Workplane("XY").workplane(offset=p.top_height+3.6).center(0, p.pan_y)
              .circle(p.pan_base_diameter/2-2.5).workplane(offset=p.pan_height-3)
              .circle(p.pan_diameter/2-2.5).loft(combine=True))
    add("skillet_320mm", pan.cut(cavity), METAL, "pan")
    handle = rounded_box(215, 26, 10, 10, (p.pan_diameter/2+87, 0, p.top_height+p.pan_height-5))
    handle = handle.rotate((0, 0, 0), (0, 0, 1), p.handle_angle_deg).translate((0, p.pan_y, 0))
    add("skillet_handle", handle, (.35, .37, .36), "pan")
    # Removable connector and swept cable clearance mockup; not a selected probe design.
    plug = cq.Workplane(port_plane).workplane(offset=1.8).circle(6).extrude(18)
    add("probe_plug_envelope", plug, DARK, "probe")
    cable_points = [cq.Vector(p.width/2+20, p.probe_port_y, p.probe_port_z),
                    cq.Vector(p.width/2+43, 100, 47), cq.Vector(p.width/2+38, 215, 90),
                    cq.Vector(172, p.pan_y+50, p.top_height+p.pan_height+40)]
    cable_edge = cq.Edge.makeSpline(cable_points)
    cable_wire = cq.Wire.assembleEdges([cable_edge])
    cable_plane = cq.Plane(origin=cable_points[0], normal=cable_edge.tangentAt(0))
    cable = cq.Workplane(cable_plane).circle(1.7).sweep(cq.Workplane().newObject([cable_wire]))
    add("probe_cable_envelope", cable, DARK, "probe")
    start = cable_points[-1]
    end = cq.Vector(85, p.pan_y+20, p.top_height+15)
    rod = cq.Solid.makeCylinder(2, (end-start).Length, start, (end-start).normalized())
    add("external_probe_envelope", rod, METAL, "probe")
    return parts


def export_all(parts: list[Component], p: Dimensions, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    stl = out / "stl"
    stl.mkdir(exist_ok=True)
    assembly = cq.Assembly(name="Temper_B_ergonomic_mockup_mm")
    context = cq.Assembly(name="Temper_B_with_cookware_mm")
    report = {"units": "mm", "purpose": "Unpowered ergonomic mockup; not manufacturing release", "components": []}
    mesh_data = []
    for c in parts:
        color = cq.Color(*c.color)
        context.add(c.shape, name=c.name, color=color)
        if c.group in ("cooker", "graphics"):
            assembly.add(c.shape, name=c.name, color=color)
        bb = c.shape.BoundingBox()
        report["components"].append({"name": c.name, "valid": c.shape.isValid(),
            "solids": len(c.shape.Solids()), "volume_mm3": round(c.shape.Volume(), 4),
            "bbox_mm": [round(n, 3) for n in (bb.xlen, bb.ylen, bb.zlen)]})
        vertices, triangles = c.shape.tessellate(.12, .06)
        material = "aluminum"
        if c.name == "upper_body":
            material = "body_aluminum"
        elif c.name == "glass_placeholder":
            material = "glass"
        elif c.name == "display_window":
            material = "screen"
        elif c.name == "temperature_knob":
            material = "knob"
        elif c.name == "rear_exhaust_grille":
            material = "grille"
        elif c.name in ("target", "actual"):
            material = "screen_ink"
        elif c.name == "placement_ring":
            material = "ring"
        elif c.group == "graphics":
            material = "print"
        elif c.name in ("skillet_320mm", "external_probe_envelope"):
            material = "steel"
        elif c.name in ("removable_base", "probe_port_socket", "rear_power_inlet_envelope",
                        "probe_plug_envelope", "probe_cable_envelope", "skillet_handle", "knob_seal_envelope") or c.name.startswith("foot_"):
            material = "rubber"
        mesh_data.append({"name": c.name, "group": c.group, "color": c.color, "material": material,
            "positions": [[round(v.x, 3), round(v.y, 3), round(v.z, 3)] for v in vertices],
            "indices": triangles})
        if c.printable:
            c.shape.exportStl(str(stl / f"{c.name}.stl"), tolerance=.12, angularTolerance=.12, relative=False)
    assembly.export(str(out / "temper-b-assembly.step"))
    context.export(str(out / "temper-b-with-skillet.step"))
    # Reimport the deliverable, rather than trusting export success.
    reimported = cq.importers.importStep(str(out / "temper-b-assembly.step")).val()
    if not reimported.isValid():
        raise ValueError("STEP round-trip produced invalid geometry")
    report["step_roundtrip_valid"] = True
    report["step_roundtrip_solids"] = len(reimported.Solids())
    report["ventilation"] = {"status": "Provisional geometry; no airflow or ingress qualification",
        "rear_opening_mm": [p.exhaust_width, p.exhaust_height],
        "exhaust_slots": p.exhaust_slot_count,
        "slot_width_length_mm": [p.exhaust_slot_width, p.exhaust_slot_length],
        "underside_intake_slots": 6, "intake_slot_width_length_mm": [5, 160]}
    report["dimensions"] = {"width": p.width, "depth": p.depth, "glass_top_above_counter": p.top_height,
        "front_angle_deg": p.front_angle_deg, "front_lip_above_counter": round(p.front_z, 2),
        "knob_diameter": p.knob_diameter, "pan_rim_diameter": p.pan_diameter,
        "pan_front_to_control_transition": round(p.pan_y-p.pan_diameter/2-p.front_depth, 2)}
    # Solid-intersection tests for the key intended clearances (contact sensor excluded).
    lookup = {c.name: c.shape for c in parts}
    report["clearance_checks"] = {}
    for first, second in [("upper_body", "glass_placeholder"), ("upper_body", "temperature_knob"),
                          ("skillet_320mm", "temperature_knob"), ("skillet_320mm", "display_window"),
                          ("upper_body", "removable_base"), ("upper_body", "rear_exhaust_grille"),
                          ("temperature_knob", "knob_fixed_collar"),
                          ("temperature_knob", "knob_shaft_envelope"),
                          ("knob_fixed_collar", "knob_shaft_envelope"),
                          ("rear_exhaust_grille", "rear_power_inlet_envelope")]:
        overlap = lookup[first].intersect(lookup[second]).Volume()
        report["clearance_checks"][f"{first} / {second}"] = round(overlap, 6)
        if overlap > .01:
            raise ValueError(f"Unexpected overlap: {first} / {second}: {overlap} mm3")
    # Six manageable print tiles per large component, with a maximum XY size 185 x 146.7 mm.
    tiles = stl / "tiles"
    tiles.mkdir(exist_ok=True)
    for name in ("upper_body", "removable_base", "glass_placeholder"):
        for ix in range(2):
            for iy in range(3):
                cutter = (cq.Workplane("XY").box(p.width/2, p.depth/3, p.top_height+100,
                          centered=(False, False, False))
                          .translate((-p.width/2+ix*p.width/2, iy*p.depth/3, -1)))
                tile = lookup[name].intersect(cutter.val())
                if tile.Volume() > .01:
                    bb = tile.BoundingBox()
                    tile = tile.translate((-bb.xmin, -bb.ymin, -bb.zmin))
                    if not tile.isValid():
                        raise ValueError(f"Invalid print tile: {name} {ix} {iy}")
                    tile.exportStl(str(tiles/f"{name}_x{ix+1}_y{iy+1}.stl"), tolerance=.12, relative=False)
    (out / "geometry-checks.json").write_text(json.dumps(report, indent=2)+"\n")
    materials = json.loads(Path(__file__).with_name("materials.json").read_text())
    (out / "mesh-data.json").write_text(json.dumps({"parts": mesh_data, "materials": materials,
        "parameters": asdict(p), "pan_center": [0, p.pan_y, 0],
        "handle_angle_deg": p.handle_angle_deg}, separators=(",", ":")))
    print(json.dumps({"components": len(parts), "STEP_valid": True, "output": str(out)}, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parameters", type=Path, default=Path(__file__).with_name("parameters.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    p = Dimensions(**json.loads(args.parameters.read_text()))
    print("Building parametric solids...", flush=True)
    parts = build(p)
    print("Checking and exporting STEP and mockup parts...", flush=True)
    export_all(parts, p, args.output)


if __name__ == "__main__":
    main()
