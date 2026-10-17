"""CadQuery adapter for a contact-bearing cold cooling mockup, not release CAD.

Dimensions live in interface.json. Imports existing native18/R4 models and
preserves their identities. This creates no PCB geometry or new placer logic.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT / "output/temper-prototype-closure/cooling"
R4 = ROOT / "output/temper-flush-front-r4"
INVENTORY = ROOT / "output/temper-manufacture-readiness/pcb/native18-geometry.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def box(origin: list[float], size: list[float]) -> cq.Shape:
    return cq.Solid.makeBox(*size, cq.Vector(*origin))


def bounds(shape: cq.Shape) -> list[float]:
    b = shape.BoundingBox()
    return [getattr(b, key) for key in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")]


def overlapping(a: list[float], b: list[float]) -> bool:
    return all(a[i] < b[i + 3] - 1e-6 and b[i] < a[i + 3] - 1e-6 for i in range(3))


def main() -> None:
    data = json.loads((HERE / "interface.json").read_text())
    inventory = json.loads(INVENTORY.read_text())
    if digest(R4 / "STEP/assembly.step") != data["r4_assembly_sha256"]:
        raise ValueError("R4 identity drift")
    if inventory["board_sha256"] != data["native18_board_sha256"]:
        raise ValueError("Native18 inventory identity drift")
    native = (
        Path(inventory["footprints"][0]["models"][0]["resolved"]).parent.parent.parent
        / "native-18/section.kicad_pcb"
    )
    if digest(native) != data["native18_board_sha256"]:
        raise ValueError("Native18 board identity drift")
    if inventory["kicad_board_thickness_mm"] != data["board_thickness"]:
        raise ValueError("Board thickness drift")
    OUT.mkdir(parents=True, exist_ok=True)
    shapes: dict[str, cq.Shape] = {}
    model_cache: dict[str, cq.Shape] = {}
    hashes: dict[str, str] = {}
    x0, y0 = data["board_origin_xy"]
    top = data["board_top_z"]
    shapes["native18_BARE_BOARD"] = box(
        [x0, y0, top - data["board_thickness"]], [240, 160, data["board_thickness"]]
    )
    for footprint in inventory["footprints"]:
        if footprint["layer"] != "F.Cu":
            raise ValueError("Back-side transform not supplied by this study")
        for index, model in enumerate(footprint["models"]):
            if (
                any(model["rotation_deg"])
                or any(model["offset_mm"])
                or model["scale"] != [1.0, 1.0, 1.0]
            ):
                raise ValueError("Non-identity model transform must be reviewed")
            filename = model["resolved"]
            if filename not in model_cache:
                model_cache[filename] = cq.importers.importStep(filename).val()
                hashes[filename] = digest(Path(filename))
            # Model +Y is opposite KiCad board +Y; footprint children use R(-theta).
            shape = (
                model_cache[filename]
                .mirror("XZ")
                .rotate((0, 0, 0), (0, 0, 1), -footprint["rotation_deg"])
            )
            px, py = footprint["position_mm"]
            shapes[f"native18_{footprint['reference']}_{index}"] = shape.translate(
                (x0 + px, y0 + py, top)
            )
    sx, sy, sz = data["sink_min"]
    length, depth, height = data["sink_size"]
    base = data["sink_base_thickness"]
    shapes["CUSTOM_200mm_SINK_BASE"] = box([sx, sy + depth - base, sz], [length, base, height]).cut(
        box(data["sink_board_relief"]["min"], data["sink_board_relief"]["size"])
    )
    for i in range(20):
        shapes[f"CUSTOM_SINK_FIN_{i:02}"] = box([sx, sy, sz + i * 3], [length, depth - base, 1.6])
    # The board recess must not sever the base or leave detached fin roots.
    connected_sink = shapes["CUSTOM_200mm_SINK_BASE"]
    for i in range(20):
        connected_sink = connected_sink.fuse(shapes[f"CUSTOM_SINK_FIN_{i:02}"])
    if not connected_sink.isValid() or len(connected_sink.Solids()) != 1:
        raise ValueError("Sink base/fin continuity lost")
    for entry in data["allocations"]:
        shape = box(entry["min"], entry["size"])
        if "vertical_hole" in entry:
            hole = entry["vertical_hole"]
            shape = shape.cut(
                cq.Solid.makeCylinder(
                    hole["radius"],
                    entry["size"][2] + 2,
                    cq.Vector(*hole["center_xy"], entry["min"][2] - 1),
                )
            )
        shapes[entry["name"]] = shape
    # Each lower shoe/post is one machined piece, with a separate removable cap.
    for label in ("L20", "L140", "R20", "R80"):
        post = shapes.pop(label + "_PEEK_POST")
        lip = shapes.pop(label + "_PEEK_UNDERSIDE_LIP")
        shapes[label + "_PEEK_LOWER_SHOE"] = post.fuse(lip)
        if label.startswith("L"):
            for suffix in ("_PEEK_DATUM_ARM", "_PEEK_EDGE_STOP"):
                shapes[label + "_PEEK_LOWER_SHOE"] = shapes[label + "_PEEK_LOWER_SHOE"].fuse(
                    shapes.pop(label + suffix)
                )
    for i, (x, y) in enumerate(data["retention"]["fastener_centres_world_xy"]):
        for name in tuple(shapes):
            if name.startswith("CARRIER_RAIL_"):
                shapes[name] = shapes[name].cut(cq.Solid.makeCylinder(1.25, 8, cq.Vector(x, y, 9)))
        # Purchased M3x25 envelope: no modeled thread/drive. Spacer sets nominal engagement.
        shapes[f"RETAINER_M3x25_{i}"] = cq.Solid.makeCylinder(1.5, 25, cq.Vector(x, y, 10.6)).fuse(
            cq.Solid.makeCylinder(2.75, 3, cq.Vector(x, y, 35.6))
        )
        shapes[f"RETAINER_1p5_SPACER_{i}"] = cq.Solid.makeCylinder(
            3, 1.5, cq.Vector(x, y, 34.1)
        ).cut(cq.Solid.makeCylinder(1.7, 1.5, cq.Vector(x, y, 34.1)))
    # Cold fixture includes a realistic removable top duct wall only; no claimed rear vent path.
    shapes["CUSTOM_DUCT_TOP_1mm"] = box([sx, sy, sz + height], [length + 25, depth - base, 1])
    assembly = cq.Assembly(name="CONTACT_STUDY_NOT_RELEASED")
    for name, shape in shapes.items():
        if not shape.isValid():
            raise ValueError(f"Invalid solid {name}")
        assembly.add(
            shape,
            name=name,
            color=cq.Color(0.72, 0.73, 0.75) if "SINK" in name else cq.Color(0.25, 0.55, 0.45),
        )
    included = []
    collisions = []
    excluded = []
    catalog = json.loads((R4 / "catalog.json").read_text())
    shape_bounds = {name: bounds(shape) for name, shape in shapes.items()}
    for entry in catalog:
        if entry["name"].startswith(tuple(data["omitted_r4_prefixes"])):
            excluded.append(entry["name"])
            continue
        path = R4 / entry["file"]
        context = cq.importers.importStep(str(path)).val()
        hashes[entry["file"]] = digest(path)
        included.append(entry["name"])
        assembly.add(context, name="R4_" + entry["name"], color=cq.Color(0.65, 0.65, 0.65, 0.2))
        cb = bounds(context)
        for name, shape in shapes.items():
            if overlapping(shape_bounds[name], cb):
                volume = shape.intersect(context).Volume()
                if volume > 1e-5:
                    collisions.append(
                        {"new_part": name, "r4_part": entry["name"], "volume_mm3": volume}
                    )
    contact = []
    for ref in ("Q5", "Q6", "Q3", "Q2", "BR1"):
        shape = shapes[f"native18_{ref}_0"]
        # Record faces on the rear-most plane; designation as metal remains unverified.
        rear = min(bounds(face)[1] for face in shape.Faces())
        faces = [
            face
            for face in shape.Faces()
            if abs(bounds(face)[1] - rear) < 1e-5 and abs(bounds(face)[4] - rear) < 1e-5
        ]
        contact.append(
            {
                "reference": ref,
                "modeled_rear_plane_y": rear,
                "planar_face_areas_mm2": [face.Area() for face in faces],
                "plane_evidence": "KiCad library / provisional model; NOT manufacturer metal-face proof",
                "bounds_mm": shape_bounds[f"native18_{ref}_0"],
            }
        )
    # Check new cooling solids against populated models; retain failures (no exclusion laundering).
    internal_hits = []
    for name, shape in shapes.items():
        if name.startswith("native18_"):
            continue
        for other, component in shapes.items():
            if other.startswith("native18_") and overlapping(
                shape_bounds[name], shape_bounds[other]
            ):
                volume = shape.intersect(component).Volume()
                if volume > 1e-5:
                    internal_hits.append(
                        {"cooling_part": name, "pcb_part": other, "volume_mm3": volume}
                    )
    output = OUT / "contact-bearing-cold-study.step"
    assembly.export(str(output))
    reimport = cq.importers.importStep(str(output)).val()
    if not reimport.isValid():
        raise ValueError("STEP reimport invalid")
    report = {
        "status": data["status"],
        "inputs_sha256": {
            "interface.json": digest(HERE / "interface.json"),
            "build_study.py": digest(Path(__file__)),
            "inventory": digest(INVENTORY),
            "catalog": digest(R4 / "catalog.json"),
            "models_and_parts": hashes,
        },
        "board_transform": {"origin_xy": [x0, y0], "top_z": top, "rotation_degrees": 0},
        "r4_parts_included": len(included),
        "r4_parts_omitted": excluded,
        "new_parts": len(shapes),
        "part_bounds_mm": shape_bounds,
        "r4_collisions": collisions,
        "cooling_to_pcb_collisions": internal_hits,
        "contacts": contact,
        "sink_continuity": {"valid_fused_solid_count": len(connected_sink.Solids())},
        "step": {
            "path": str(output.relative_to(ROOT)),
            "sha256": digest(output),
            "valid_reimport": True,
            "solid_count": len(reimport.Solids()),
        },
        "limits": data["not_modeled"],
    }
    (OUT / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "r4_collisions": collisions,
                "cooling_to_pcb_collisions": internal_hits,
                "contacts": contact,
                "step": report["step"],
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
