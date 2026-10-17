"""Build a reviewed cold packaging revision from the actual native19 STEP.

This adapter preserves source part identities. Its allocations, modified rear
openings and excluded historical chambers are reported explicitly.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import cadquery as cq
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round2/cooling"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def box(origin: list[float], size: list[float]) -> cq.Shape:
    return cq.Solid.makeBox(*size, cq.Vector(*origin))


@lru_cache(maxsize=2048)
def bounds(shape: cq.Shape) -> list[float]:
    b = shape.BoundingBox()
    return [getattr(b, key) for key in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")]


def intersects(a: cq.Shape, b: cq.Shape) -> float:
    aa, bb = bounds(a), bounds(b)
    if any(aa[i] >= bb[i + 3] - 1e-6 or bb[i] >= aa[i + 3] - 1e-6 for i in range(3)):
        return 0.0
    return a.intersect(b).Volume()


def cylinder(radius: float, length: float, start: list[float], axis=(0, 0, 1)) -> cq.Shape:
    return cq.Solid.makeCylinder(radius, length, cq.Vector(*start), cq.Vector(*axis))


def ramp_y(
    x0: float, x1: float, y0: float, y1: float, low0: float, high0: float, low1: float, high1: float
) -> cq.Shape:
    wires = []
    for y, low, high in ((y0, low0, high0), (y1, low1, high1)):
        wires.append(
            cq.Wire.makePolygon(
                [
                    cq.Vector(x0, y, low),
                    cq.Vector(x1, y, low),
                    cq.Vector(x1, y, high),
                    cq.Vector(x0, y, high),
                ],
                close=True,
            )
        )
    return cq.Solid.makeLoft(wires, ruled=True)


def import_native(path: Path, data: dict) -> tuple[dict[str, cq.Shape], dict]:
    doc = TDocStd_Document(TCollection_ExtendedString("native19"))
    reader = STEPCAFControl_Reader()
    if int(reader.ReadFile(str(path))) != 1 or not reader.Transfer(doc):
        raise ValueError("Native19 STEP read/transfer failed")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    if roots.Length() != 1:
        raise ValueError("Expected one native19 root")
    children = TDF_LabelSequence()
    tool.GetComponents_s(roots.Value(1), children)
    board = data["board"]
    x, y = board["origin_xy"]
    z = board["model_top_datum_z"] - board["export_model_top_datum_z"]
    shapes = {}
    source_bounds = {}
    for i in range(1, children.Length() + 1):
        label = children.Value(i)
        attribute = TDataStd_Name()
        label.FindAttribute(TDataStd_Name.GetID_s(), attribute)
        name = attribute.Get().ToExtString()
        if name.startswith("=>"):
            name = "SUBSTRATE"
        shape = cq.Shape.cast(tool.GetShape_s(label))
        source_bounds[name] = bounds(shape)
        shapes[name] = shape.mirror("XZ").translate((x, y, z))
    inventory = json.loads((ROOT / data["sources"]["native19_model_inventory"]["path"]).read_text())
    expected = {row["reference"] for row in inventory["models"]}
    if set(shapes) != expected | {"SUBSTRATE"} or len(expected) != 142:
        raise ValueError("Actual STEP reference inventory differs")
    # Independent model anchor: BR1's provisional body sits at the exporter model datum.
    if abs(source_bounds["BR1"][2] - board["export_model_top_datum_z"]) > 1e-6:
        raise ValueError("Exporter component datum changed")
    return shapes, {
        "source_bounds_mm": source_bounds,
        "transform": [x, y, z],
        "references": sorted(expected),
    }


def make_duct(
    side: str, wall: float, sleeve_inner: float, sleeve_outer: float
) -> tuple[cq.Shape, cq.Shape]:
    """Closed sheet allocation with continuous air volume and sealed leg sleeves."""
    right = side == "RIGHT"
    x0, x1 = (143.5, 179) if right else (-180, -142.5)
    front_x0, front_x1 = (113, 179) if right else (-180, -137)
    rear_x0, rear_x1 = (90, 179) if right else (-180, 40)

    def route(pad: float) -> cq.Shape:
        sections = [
            box(
                [front_x0 - pad, 93.9 - pad, 13 - pad],
                [front_x1 - front_x0 + 2 * pad, 61.1 + 2 * pad, 58 + 2 * pad],
            ),
            box([x0 - pad, 154 - pad, 13 - pad], [x1 - x0 + 2 * pad, 196 + 2 * pad, 58 + 2 * pad]),
            ramp_y(
                x0 - pad, x1 + pad, 350 - pad, 414 + pad, 13 - pad, 71 + pad, 49 - pad, 84 + pad
            ),
            box(
                [rear_x0 - pad, 413 - pad, 49 - pad],
                [rear_x1 - rear_x0 + 2 * pad, 25 + 2 * pad, 35 + 2 * pad],
            ),
        ]
        shape = sections[0]
        for section in sections[1:]:
            shape = shape.fuse(section)
        return shape

    air, outer = route(0), route(wall)
    leg_x = 157 if right else -157
    for y in (190, 330):
        air = air.cut(cylinder(sleeve_outer, 100, [leg_x, y, 0]))
        outer = outer.cut(cylinder(sleeve_inner, 100, [leg_x, y, 0]))
    shell = outer.cut(air)
    # Open only the fan mate and rear panel mate; sleeves remain closed to the airflow.
    fan_x = 113 if right else -137
    shell = shell.cut(box([fan_x - wall, 93.9, 13], [2 * wall, 60, 58]))
    shell = shell.cut(box([rear_x0, 437.5, 49], [rear_x1 - rear_x0, 2, 35]))
    shell = shell.cut(box([-200, 437.5, 0], [400, 10, 120]))
    if not air.isValid() or len(air.Solids()) != 1 or not shell.isValid():
        raise ValueError(f"{side} duct disconnected or invalid")
    return shell, air


def main() -> None:
    data = json.loads((HERE / "interface.json").read_text())
    for name, source in data["sources"].items():
        if digest(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"Source identity drift: {name}")
    OUT.mkdir(parents=True, exist_ok=True)
    native, native_receipt = import_native(ROOT / data["sources"]["native19_step"]["path"], data)
    new = {}
    sink = data["sink"]
    x, y, z = sink["min"]
    length, depth, height = sink["size"]
    base = sink["base_thickness"]
    solid = box([x, y + depth - base, z], [length, base, height]).cut(
        box(sink["board_relief"]["min"], sink["board_relief"]["size"])
    )
    for i in range(sink["fin_count"]):
        solid = solid.fuse(
            box([x, y, z + i * sink["fin_pitch"]], [length, depth - base, sink["fin_thickness"]])
        )
    if not solid.isValid() or len(solid.Solids()) != 1:
        raise ValueError("Sink must remain one connected solid")
    new["CUSTOM_SINK"] = solid
    for ceramic in data["contact"]["ceramics"]:
        new[ceramic["name"]] = box(ceramic["min"], ceramic["size"])
    for contact in data["contact"]["shim_contacts"]:
        ref = contact["reference"]
        shim = box(
            [contact["x_center"] - contact["width"] / 2, 162.9, contact["z_min"]],
            [
                contact["width"],
                data["contact"]["shim_nominal_midpoints_mm"][ref],
                contact["height"],
            ],
        )
        if "hole_relief" in contact:
            relief = contact["hole_relief"]
            shim = shim.cut(
                box(
                    [contact["x_center"] - relief["x_width"] / 2, 162.8, relief["z_min"]],
                    [relief["x_width"], 2, relief["z_height"]],
                )
            )
        new[f"{ref}_MEASURED_SHIM_MIDPOINT_PLACEHOLDER"] = shim
    for fan in data["airflow"]["fans"]:
        new[fan["name"]] = box(fan["min"], fan["size"])
    new["SINK_DUCT_TOP"] = box([x, y, z + height], [length, depth - base, 0.8])
    for item in data["retention_allocations"]:
        shape = box(item["min"], item["size"])
        if "vertical_hole" in item:
            hole = item["vertical_hole"]
            shape = shape.cut(
                cylinder(
                    hole["radius"], item["size"][2] + 2, [*hole["center_xy"], item["min"][2] - 1]
                )
            )
        new[item["name"]] = shape
    for label in ("L20", "L140", "R20", "R80"):
        shape = new.pop(label + "_PEEK_POST").fuse(new.pop(label + "_PEEK_UNDERSIDE_LIP"))
        if label.startswith("L"):
            for suffix in ("_PEEK_DATUM_ARM", "_PEEK_EDGE_STOP"):
                shape = shape.fuse(new.pop(label + suffix))
        idx = ("L20", "L140", "R20", "R80").index(label)
        fx, fy = data["retention"]["fastener_centres_world_xy"][idx]
        new[label + "_PEEK_LOWER_SHOE"] = shape.cut(cylinder(1.7, 20, [fx, fy, 15]))
    for i, (fx, fy) in enumerate(data["retention"]["fastener_centres_world_xy"]):
        for name in tuple(new):
            if name.startswith("CARRIER_RAIL_"):
                new[name] = new[name].cut(cylinder(1.25, 8, [fx, fy, 9]))
        new[f"CARRIER_M3x25_{i}"] = cylinder(1.5, 25, [fx, fy, 10.6]).fuse(
            cylinder(2.75, 3, [fx, fy, 35.6])
        )
        new[f"CARRIER_SPACER_{i}"] = cylinder(3, 1.5, [fx, fy, 34.1]).cut(
            cylinder(1.7, 1.5, [fx, fy, 34.1])
        )
    cradle = box([-135, 83.9, 10], [260, 79.1, 2])
    for fx in (-114, 88):
        flange = box([fx, 154.5, 12], [2, 5.5, 60])
        for fz in (22, 62):
            flange = flange.cut(cylinder(1.7, 4, [fx - 1, 158, fz], (1, 0, 0)))
        cradle = cradle.fuse(flange)
    floor_holes = [(fx, fy, 1.7) for fx in (-116.5, 134.5) for fy in (210, 290)]
    floor_holes += [(fx, fy, 2.2) for fx, fy in ((-120, 87), (-120, 158), (120, 87), (120, 160))]
    for fx, fy, radius in floor_holes:
        if radius == 2.2:
            cradle = cradle.cut(cylinder(radius, 5, [fx, fy, 9]))
        else:
            for name in tuple(new):
                if name.startswith("CARRIER_RAIL_"):
                    new[name] = new[name].cut(cylinder(1.25, 8, [fx, fy, 9]))
    new["SINK_CRADLE_CHASSIS_MOUNT"] = cradle.cut(new["CARRIER_RAIL_-122p5"])
    for side, fx, axis in (("LEFT", -117, (1, 0, 0)), ("RIGHT", 93, (-1, 0, 0))):
        for fz in (22, 62):
            # Thread engagement is deliberately reported as positive volume below.
            new["CUSTOM_SINK"] = new["CUSTOM_SINK"].cut(cylinder(1.25, 12, [fx, 158, fz], axis))
            new[f"SINK_M3_{side}_{fz}"] = cylinder(1.5, 11, [fx, 158, fz], axis).fuse(
                cylinder(2.75, 3, [fx, 158, fz], axis)
            )
    for i, (fx, fy, radius) in enumerate(floor_holes):
        shaft = 1.5 if radius == 1.7 else 2
        new[f"FLOOR_MOUNT_SCREW_{i}"] = cylinder(shaft, 8, [fx, fy, 8]).fuse(
            cylinder(shaft + 1.25, 1.5, [fx, fy, 6.5])
        )
        if radius == 2.2:
            new[f"CRADLE_M4_NUT_{i}"] = cylinder(3.5, 3, [fx, fy, 12]).cut(
                cylinder(1.65, 3, [fx, fy, 12])
            )
    air = {}
    for side in ("LEFT", "RIGHT"):
        new[side + "_DUCT"], air[side] = make_duct(
            side,
            data["airflow"]["side_duct_wall"],
            data["airflow"]["leg_sleeve_inner_radius"],
            data["airflow"]["leg_sleeve_outer_radius"],
        )
        fan_name = "RIGHT_PUSH_FAN" if side == "RIGHT" else "LEFT_PULL_FAN"
        new[side + "_DUCT"] = new[side + "_DUCT"].cut(new[fan_name])
    emi = data["emi"]
    mx, my, mz = emi["module_min"]
    new["FILTER_CARRIER_ALLOCATION"] = box([mx + 1, my + 1, mz + 3], [108, 78, 1.6])
    module = json.loads((ROOT / data["sources"]["filter_packing"]["path"]).read_text())
    heights = [41, 29.5, 31, 31, 11, 11, 9, 9, 7.5, 10]
    for (label, (px, py, pw, pd)), ph in zip(
        module["local_body_boxes_xywh_mm"].items(), heights, strict=True
    ):
        new["FILTER_" + label.replace(" ", "_")] = box([mx + px, my + py, mz + 4.6], [pw, pd, ph])
    cover = box([mx, my, mz], emi["module_size"]).cut(box([mx + 1, my + 1, mz], [108, 78, 49]))
    new["FILTER_INSULATING_COVER_ALLOCATION"] = cover
    new["LPSC0001Z_CLOSED_BODY_ENVELOPE"] = box(emi["holder_min"], emi["holder_closed_size"])
    # TS35/7.5 allocation: exact holder clip/rail mating datum remains unverified.
    new["DIN35_7P5_RAIL_ENVELOPE"] = box([1.75, 341, 16.5], [35, 25.78, 1]).fuse(
        box([7.75, 341, 10], [1, 25.78, 6.5]),
        box([29.75, 341, 10], [1, 25.78, 6.5]),
        box([7.75, 341, 10], [23, 25.78, 1]),
    )
    cx, cz = emi["rocker_panel_center_xz"]
    panel_y = emi["rocker_panel_outer_y"]
    bw, bd, bh = emi["rocker_body_size"]
    new["SCHURTER_4435_BODY_ENVELOPE"] = box([cx - bw / 2, panel_y - bd, cz - bh / 2], [bw, bd, bh])
    new["SCHURTER_4435_TAB_ENVELOPE"] = box(
        [cx - bw / 2, panel_y - bd - emi["rocker_terminal_depth"], cz - bh / 2],
        [bw, emi["rocker_terminal_depth"], bh],
    )
    new["SCHURTER_4435_BEZEL_ENVELOPE"] = box([cx - 18, panel_y, cz - 14.5], [36, 1.7, 29])
    new["SCHURTER_4435_ACTUATOR_ENVELOPE"] = box(
        [cx - 18, panel_y + 1.7, cz - 14.5],
        [36, emi["rocker_external_projection"] - 1.7, 29],
    )
    new["CORD_PORT_BLANK_ADAPTER"] = box([115, 436.5, 18], [40, 1.5, 30])
    for name, (px, py) in (
        ("MAIN", data["pe"]["main_stud_world_xy"]),
        ("SINK", data["pe"]["sink_cradle_stud_world_xy"]),
    ):
        new[name + "_DEDICATED_PE_STUD"] = cylinder(2, 15, [px, py, 10 if name == "MAIN" else 12])
    pe_path = data["pe"]["bond_path_world_xyz"]
    bond_segments = []
    for a, b in zip(pe_path, pe_path[1:], strict=False):
        width = data["pe"]["bond_width_allocation"]
        origin = [min(a[0], b[0]), min(a[1], b[1]), a[2]]
        size = [abs(a[0] - b[0]), abs(a[1] - b[1]), 1]
        axis = 1 if size[0] else 0
        origin[axis] -= width / 2
        size[axis] = width
        bond_segments.append(box(origin, size))
    bond = bond_segments[0].fuse(*bond_segments[1:])
    for px, py in (data["pe"]["main_stud_world_xy"], data["pe"]["sink_cradle_stud_world_xy"]):
        bond = bond.fuse(cylinder(5, 1, [px, py, 16])).cut(cylinder(2.2, 3, [px, py, 15]))
    new["PE_BOND_ROUTE_ALLOCATION"] = bond
    context, omissions, modifications = {}, [], []
    r4 = ROOT / "output/temper-flush-front-r4"
    catalog = json.loads((r4 / "catalog.json").read_text())
    part_identities = [
        {"name": item["name"], "file": item["file"], "sha256": digest(r4 / item["file"])}
        for item in catalog
    ]
    identity = hashlib.sha256(json.dumps(part_identities, sort_keys=True).encode()).hexdigest()
    if identity != data["r4_part_identity_sha256"]:
        raise ValueError("Individual R4 source part identity drift")
    for item in catalog:
        name = item["name"]
        if name.startswith(tuple(data["omitted_r4_prefixes"])):
            omissions.append(name)
            continue
        shape = cq.importers.importStep(str(r4 / item["file"])).val()
        if name == "three_bend_front_top_rear_cover":
            width, height = emi["rocker_cutout_size"]
            shape = shape.cut(box([cx - width / 2, 436, cz - height / 2], [width, 6, height]))
            for sx in data["airflow"]["rear_inlet_slot_centers_x"]:
                cutter = cq.Workplane("XZ", origin=(sx, 441, 67)).slot2D(36, 5, 90).extrude(5).val()
                shape = shape.cut(cutter)
            modifications.append(
                {
                    "part": name,
                    "changes": "rear rocker aperture and nine right intake slots; front/exterior envelope unchanged",
                }
            )
        if name == "two_bend_bottom_and_sides":
            for fx, fy, radius in floor_holes:
                shape = shape.cut(cylinder(radius, 5, [fx, fy, 7]))
            modifications.append(
                {"part": name, "changes": "eight dedicated carrier/cradle floor mounting holes"}
            )
        context[name] = shape
    native_hits, context_hits = [], []
    for name, shape in new.items():
        for ref, component in native.items():
            volume = intersects(shape, component)
            if volume > 1e-5:
                native_hits.append({"new": name, "reference": ref, "volume_mm3": volume})
        for ref, component in context.items():
            volume = intersects(shape, component)
            if volume > 1e-5:
                context_hits.append({"new": name, "r4": ref, "volume_mm3": volume})
    environment_hits = []
    for ref, component in native.items():
        for name, shape in context.items():
            volume = intersects(shape, component)
            if volume > 1e-5:
                environment_hits.append({"reference": ref, "r4": name, "volume_mm3": volume})
    new_hits = []
    new_names = list(new)
    for i, name in enumerate(new_names):
        for other in new_names[i + 1 :]:
            volume = intersects(new[name], new[other])
            if volume > 1e-5:
                new_hits.append({"a": name, "b": other, "volume_mm3": volume})
    air_hits = []
    for side, volume_shape in air.items():
        for ref, component in {**native, **context}.items():
            volume = intersects(volume_shape, component)
            if volume > 1e-5:
                air_hits.append({"duct": side, "obstacle": ref, "volume_mm3": volume})
    airway_sections = {
        side: {
            str(y): shape.intersect(box([-200, y - 0.05, 0], [400, 0.1, 120])).Volume() / 0.1
            for y in (190, 330, 380, 430)
        }
        for side, shape in air.items()
    }
    # The catalogue's open projection is an envelope, not a reconstructed hinge sweep.
    door = box(emi["holder_min"], [*emi["holder_closed_size"][:2], emi["holder_open_projection"]])
    service_hits = []
    for name, shape in {**native, **context}.items():
        volume = intersects(door, shape)
        if volume > 1e-5:
            service_hits.append({"obstacle": name, "volume_mm3": volume})
    assembly = cq.Assembly(name="ROUND2_COLD_NOT_RELEASED")
    for prefix, group in (("native19", native), ("R4", context), ("R2", new)):
        for name, shape in group.items():
            if not shape.isValid():
                raise ValueError(f"Invalid shape: {prefix}:{name}")
            assembly.add(shape, name=prefix + "_" + name)
    step = OUT / "native19-r4-round2-cold.step"
    assembly.export(str(step))
    reimport = cq.importers.importStep(str(step)).val()
    if not reimport.isValid():
        raise ValueError("Reimport failed")
    report = {
        "status": data["status"],
        "source_sha256": digest(Path(__file__)),
        "interface_sha256": digest(HERE / "interface.json"),
        "r4_part_identity_sha256": identity,
        "native": native_receipt,
        "native_parts": len(native) - 1,
        "retained_r4_parts": len(context),
        "omitted_r4_parts": omissions,
        "modified_r4_parts": modifications,
        "new_parts": {name: bounds(shape) for name, shape in new.items()},
        "native_collisions": native_hits,
        "r4_collisions": context_hits,
        "native_vs_r4_collisions": environment_hits,
        "new_pair_intersections": new_hits,
        "airway_obstacles": air_hits,
        "airway_slice_area_mm2": airway_sections,
        "fuse_open_projection_vs_installed_context": service_hits,
        "sink_connected_solids": len(new["CUSTOM_SINK"].Solids()),
        "step": {"sha256": digest(step), "valid": True, "solids": len(reimport.Solids())},
        "limits": [
            "Source142models include24provisional packages",
            "Measured shim dimensions, clamp forces, final insulation and physical qualification absent",
            "Precharge and cord/terminaltransition not selected",
            "New-new intersections include deliberate thread engagements and are separately reviewed",
        ],
    }
    (OUT / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "native_parts",
                    "native_collisions",
                    "r4_collisions",
                    "airway_obstacles",
                    "step",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
