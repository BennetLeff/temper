"""CadQuery adapter for declared cold packaging reservations; no safety verdict."""

from __future__ import annotations

import hashlib
import json
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
OUT = ROOT / "output/temper-prototype-closure/round3/packaging"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def box(origin: list[float], size: list[float]) -> cq.Shape:
    return cq.Solid.makeBox(*size, cq.Vector(*origin))


def bounds(shape: cq.Shape) -> list[float]:
    b = shape.BoundingBox()
    return [getattr(b, k) for k in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")]


def hits(parts: dict[str, cq.Shape], context: dict[str, cq.Shape]) -> list[dict]:
    result = []
    cached = {key: bounds(value) for key, value in context.items()}
    for name, shape in parts.items():
        a = bounds(shape)
        for other, body in context.items():
            b = cached[other]
            if any(a[i] >= b[i + 3] - 1e-6 or b[i] >= a[i + 3] - 1e-6 for i in range(3)):
                continue
            volume = shape.intersect(body).Volume()
            if volume > 1e-5:
                result.append({"new": name, "context": other, "volume_mm3": volume})
    return result


def read_parts(path: Path) -> dict[str, cq.Shape]:
    doc = TDocStd_Document(TCollection_ExtendedString("round2"))
    reader = STEPCAFControl_Reader()
    if int(reader.ReadFile(str(path))) != 1 or not reader.Transfer(doc):
        raise ValueError("STEP read/transfer failed")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    if roots.Length() != 1:
        raise ValueError("Expected one root")
    children = TDF_LabelSequence()
    tool.GetComponents_s(roots.Value(1), children)
    result = {}
    for i in range(1, children.Length() + 1):
        label = children.Value(i)
        name = TDataStd_Name()
        if not label.FindAttribute(TDataStd_Name.GetID_s(), name):
            raise ValueError("Unnamed source part")
        key = name.Get().ToExtString()
        if key in result:
            raise ValueError(f"Duplicate source identity: {key}")
        result[key] = cq.Shape.cast(tool.GetShape_s(label))
    return result


def export(name: str, groups: list[tuple[str, dict[str, cq.Shape]]]) -> dict:
    assembly = cq.Assembly(name=name)
    for prefix, parts in groups:
        for key, shape in parts.items():
            if not shape.isValid():
                raise ValueError(f"Invalid solid: {key}")
            assembly.add(shape, name=prefix + key)
    path = OUT / (name + ".step")
    assembly.export(str(path))
    reread = cq.importers.importStep(str(path)).val()
    if not reread.isValid():
        raise ValueError("Invalid exported STEP")
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path),
        "valid": True,
        "solids": len(reread.Solids()),
    }


def draw_layout(data: dict) -> None:
    """Write a dimensioned front-elevation aid from the same pod reservations."""
    from html import escape

    p = data["pod"]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="680" viewBox="0 0 1050 680">',
        '<rect width="1050" height="680" fill="#f8f7f3"/>',
        '<g font-family="Arial,sans-serif" fill="#183b40">',
        '<text x="35" y="35" font-size="24">Temper / engineering inlet pod</text>',
        '<text x="35" y="60" font-size="14">500 W × 500 H × 220 D mm • upright • cold design reservations</text>',
        '<rect x="40" y="100" width="500" height="500" fill="#e6e5df" stroke="#183b40" stroke-width="2"/>',
        '<text x="195" y="625" font-size="14">500 mm outside width</text>',
    ]
    for item in p["parts"]:
        x, _, z = item["min"]
        w, _, h = item["size"]
        hot = item["id"].startswith(("RPRE", "RTEST", "TCO"))
        color = "#e8ac82" if hot else "#a9c8c3"
        svg.append(
            f'<rect x="{40 + x}" y="{600 - z - h}" width="{w}" height="{h}" fill="{color}" stroke="#244c50"/>'
        )
        if not item["id"].startswith("TCO"):
            label = (
                item["id"].replace("_RESERVATION", "").replace("CONTROL_ISOLATED_BOARD", "CONTROL")
            )
            svg.append(
                f'<text x="{44 + x}" y="{616 - z - h}" font-size="10">{escape(label)}</text>'
            )
    notes = [
        "FIRST ENGINEERING UNIT",
        "Fuses and contactors stay accessible.",
        "D22 filter remains inside the cooker.",
        "Proof load stays before D22 in this pod.",
        "",
        "Upper orange zone: captive hot-part guard.",
        "No continuous 200 W heatsink credit.",
        "Each precharge branch has its own cutoff.",
        "",
        "Three fuse holders: 70 mm reservation.",
        "Front removal / service aisle: 300 mm.",
        "PSU: upright; 40 mm above, 20 below,",
        "5 mm each side per manufacturer.",
        "",
        "Body rectangles do not show wire bends,",
        "terminal boots, DIN clips or insulation.",
        "No enclosure or powered-release rating.",
        "",
        "R4 roof: nominal 2.0 mm over capacitor;",
        "1.453 mm below coil-support bounding box.",
        "Tolerance and insulation stack remain open.",
    ]
    for i, note in enumerate(notes):
        svg.append(f'<text x="580" y="{112 + i * 23}" font-size="14">{escape(note)}</text>')
    svg.append("</g></svg>")
    (OUT / "pod-layout.svg").write_text("\n".join(svg) + "\n")


def main() -> None:
    data = json.loads((HERE / "interface.json").read_text())
    source = ROOT / data["source_step"]["path"]
    if digest(source) != data["source_step"]["sha256"]:
        raise ValueError("Pinned round2 STEP changed")
    OUT.mkdir(parents=True, exist_ok=True)
    old = read_parts(source)
    if sum(len(s.Solids()) for s in old.values()) != data["source_step"]["solids"]:
        raise ValueError("Source solid count changed")
    removed = data["r4"]["removed_for_proposal"]
    if any(name not in old for name in removed):
        raise ValueError("Requested removal not found")
    context = {name: shape for name, shape in old.items() if name not in removed}
    c = data["r4"]["cover"]
    roof = box([*c["min_xy"], c["roof_z"][0]], [*c["size_xy"], 1.5])
    aperture = box([-25, 235, 59], [50, 52, 30])
    roof = roof.cut(aperture)
    well = box(c["sensor_well_outer_min"], c["sensor_well_outer_size"]).cut(
        box([-23.5, 236.5, 61.5], [47, 49, 25])
    )
    cable = c["sensor_cable_aperture"]
    well = well.cut(box(cable["min"], cable["size"]))
    barrier = {
        "ROOF": roof,
        "SENSOR_WELL": well,
        "LEFT_WALL": box([-125, 154, 10], [1.5, 173, 72]),
        "RIGHT_WALL": box([141, 162, 10], [1, 165, 72]),
        "REAR_WALL": box([-125, 325.5, 10], [267, 1.5, 72]),
        "FRONT_PROFILE": box([-125, 154, 10], [267, 1.5, 72]),
    }
    # Exact nominal profile contacts only, NOT arbitrary cutouts around live parts.
    mates = [
        "R2_CUSTOM_SINK",
        "R2_SINK_CRADLE_CHASSIS_MOUNT",
        "R2_RIGHT_DUCT",
        "R2_PE_BOND_ROUTE_ALLOCATION",
        "R2_SINK_M3_LEFT_22",
        "R2_SINK_M3_LEFT_62",
        "R2_SINK_M3_RIGHT_22",
        "R2_SINK_M3_RIGHT_62",
        "R2_CRADLE_M4_NUT_5",
    ]
    profile_contacts = []
    for name in ("LEFT_WALL", "REAR_WALL", "FRONT_PROFILE"):
        for mate in mates:
            if mate not in context:
                raise ValueError(f"Missing contact part: {mate}")
            intersection = hits({name: barrier[name]}, {mate: context[mate]})
            if intersection:
                profile_contacts.extend(intersection)
                barrier[name] = barrier[name].cut(context[mate])
    # Proposal apertures: remain open until an actual insulated feedthrough is qualified.
    for name, origin, size in (
        ("REAR_WALL", [75, 324, 35], [20, 5, 15]),
        ("REAR_WALL", [15, 324, 55], [20, 5, 12]),
    ):
        barrier[name] = barrier[name].cut(box(origin, size))
    adapter = data["r4"]["mains_adapter"]
    plate = box(adapter["plate_min"], adapter["plate_size"])
    hole = cq.Solid.makeCylinder(
        adapter["gland_cutout_nominal_diameter"] / 2, 5, cq.Vector(135, 435, 34), cq.Vector(0, 1, 0)
    )
    plate = plate.cut(hole)
    for hx, hz in adapter["mounting_hole_centres_xz"]:
        plate = plate.cut(cq.Solid.makeCylinder(1.7, 5, cq.Vector(hx, 435, hz), cq.Vector(0, 1, 0)))
    barrier["MAINS_ADAPTER"] = plate
    # Close the vacated switch hole with a separate internal service plate.
    barrier["ROCKER_BLANK"] = box(
        data["r4"]["rocker_blank"]["min"], data["r4"]["rocker_blank"]["size"]
    )
    catch = data["r4"]["catch_conditional_reservation"]
    reservations = {"CONDITIONAL_CATCH": box(catch["min"], catch["size"])}
    p = data["pod"]
    components = {item["id"]: box(item["min"], item["size"]) for item in p["parts"]}
    case = {
        "CASE": box([0, 0, 0], p["outside_size_xyz"]).cut(box([1.5, -1, 1.5], [497, 219.5, 497])),
        "TOOL_REMOVABLE_DOOR": box([0, -1.5, 0], [500, 1.5, 500]),
        "BACKPLATE": box(p["backplate"]["min"], p["backplate"]["size"]),
        "HOT_PLATE": box(p["hot_plate"]["min"], p["hot_plate"]["size"]),
        "HOT_ZONE_GUARD": box(
            p["service"]["thermal_zone_guard_min"], p["service"]["thermal_zone_guard_size"]
        ),
    }
    source_hits = hits(barrier, context)
    catch_hits = hits(reservations, context | barrier)
    component_pairs = []
    names = list(components)
    for i, name in enumerate(names):
        component_pairs.extend(
            hits({name: components[name]}, {n: components[n] for n in names[i + 1 :]})
        )
    report = {
        "status": data["status"],
        "source_sha256": digest(source),
        "script_sha256": digest(Path(__file__)),
        "interface_sha256": digest(HERE / "interface.json"),
        "source_parts": len(old),
        "source_solids": 565,
        "removed_parts": removed,
        "profile_contacts_not_qualified": profile_contacts,
        "barrier_vs_retained_parts_collisions": source_hits,
        "conditional_catch_vs_installed_collisions": catch_hits,
        "pod_component_pair_collisions": component_pairs,
        "barrier_bounds": {k: bounds(v) for k, v in barrier.items()},
        "exports": [
            export("pod-reservations-design-only", [("CASE_", case), ("PART_", components)]),
            export("r4-barrier-design-only", [("BASE_", context), ("PROPOSAL_", barrier)]),
            export("barrier-parts-design-only", [("PROPOSAL_", barrier)]),
        ],
        "limits": [
            "No claim of insulation, access-probe, contact pressure, thermal or structural qualification",
            "Profile mates, cable apertures and sensor aperture need qualified closures",
            "R4 source includes provisional packages; harnesses and cover fasteners not represented",
            "Catch box is a checked reservation only and is excluded from assembly STEP",
            "Pod parts are rectangular body reservations; no terminal, wire, clamp or DIN mount reconstruction",
            "No source native19 or round2 file modified",
        ],
    }
    draw_layout(data)
    report["layout_svg_sha256"] = digest(OUT / "pod-layout.svg")
    (OUT / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "barrier_vs_retained_parts_collisions",
                    "conditional_catch_vs_installed_collisions",
                    "pod_component_pair_collisions",
                    "exports",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
