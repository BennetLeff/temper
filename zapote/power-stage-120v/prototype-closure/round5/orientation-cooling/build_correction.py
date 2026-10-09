"""CAD adapter for rigid native19 cooling correction, not a qualification solver."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/orientation-cooling"
sys.path.insert(0, str(HERE.parents[1] / "round3/packaging"))
from build_proposal import bounds, box, hits, read_parts  # noqa: E402

sys.path.insert(0, str(HERE.parents[1] / "round2/cooling"))
from build_revision import cylinder, ramp_y  # noqa: E402
from pe_bond import add_pe  # noqa: E402

P = "BASE_BASE_R2_"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def reflect_custom(s):
    # Reflection is a manufacturing definition for bespoke supports, never an installation transform.
    return s.mirror("YZ").translate((19, 0, 0))


def duct(side):
    right = side == "RIGHT"
    x0, x1 = (143.5, 179) if right else (-180, -142.5)
    front0, front1 = (149, 179) if right else (-180, -101)
    rear0, rear1 = (90, 179) if right else (-180, 40)

    def route(p):
        ss = [
            box(
                [front0 - p, 93.9 - p, 13 - p], [front1 - front0 + 2 * p, 60.1 + 2 * p, 58 + 2 * p]
            ),
            box([x0 - p, 154 - p, 13 - p], [x1 - x0 + 2 * p, 196 + 2 * p, 58 + 2 * p]),
            ramp_y(x0 - p, x1 + p, 350 - p, 414 + p, 13 - p, 71 + p, 49 - p, 84 + p),
            box([rear0 - p, 413 - p, 49 - p], [rear1 - rear0 + 2 * p, 25 + 2 * p, 35 + 2 * p]),
        ]
        return ss[0].fuse(*ss[1:])

    air, outer = route(0), route(0.8)
    for y in (190, 330):
        x = 157 if right else -157
        air = air.cut(cylinder(10, 100, [x, y, 0]))
        outer = outer.cut(cylinder(7, 100, [x, y, 0]))
    shell = outer.cut(air)
    mate = 149 if right else -101
    shell = shell.cut(box([mate - 0.8, 93.9, 13], [1.6, 60, 58]))
    shell = shell.cut(box([rear0, 437.5, 49], [rear1 - rear0, 2, 35]))
    shell = shell.cut(box([-200, 437.5, 0], [400, 10, 120]))
    return shell, air


def build():
    source = OUT / "validation-context-pre-pe.step"
    immutable_source = (
        ROOT
        / "output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step"
    )
    base = read_parts(immutable_source)
    validation_context = read_parts(source)
    native_path = ROOT / "output/temper-prototype-closure/pcb/temper-power-native19-candidate.step"
    native = {
        ("SUBSTRATE" if n.startswith("=>") else n): s.rotate((0, 0, 0), (0, 0, 1), 180).translate(
            (129.5, 162, 30.387)
        )
        for n, s in read_parts(native_path).items()
    }
    replacement = {}
    removed = []
    for n, s in base.items():
        short = n.removeprefix(P)
        if n.startswith(P) and (
            short.startswith(("CARRIER_", "L20_PEEK", "L140_PEEK", "R20_PEEK", "R80_PEEK"))
            or short.startswith("ALN_")
        ):
            replacement[n] = reflect_custom(s)
        elif n.startswith(P) and short in (
            "CUSTOM_SINK",
            "RIGHT_PUSH_FAN",
            "LEFT_PULL_FAN",
            "SINK_DUCT_TOP",
        ):
            replacement[n] = s.translate((36, 0, 0))
        elif n.startswith(P) and short.startswith("SINK_M3_"):
            replacement[n] = s.translate((36, 0, 0))
        elif n.startswith(P) and "MEASURED_SHIM" in short:
            removed.append(n)
    replacement[P + "CARRIER_RAIL_-122p5"] = replacement[P + "CARRIER_RAIL_-122p5"].cut(
        box([140.5, 161, 9], [3, 162, 8])
    )
    # Exact STEP proxy gaps are not physical shim specifications; real rear-plane intervals remain separately bounded.
    for ref, x, w, z, h, t in [
        ("Q2", -26.5, 12, 45.3, 10, 0.630),
        ("Q3", -8.5, 12, 45.3, 10, 0.630),
        ("Q5", 31.5, 12, 45.3, 10, 0.630),
        ("Q6", 13.5, 12, 45.3, 10, 0.630),
        ("BR1", 100.7, 24, 37, 14, 1.3),
    ]:
        s = box([x - w / 2, 162.9, z], [w, t, h])
        if ref != "BR1":
            s = s.cut(box([x - 3.7, 162.8, 47.4], [7.4, 2, 7.4]))
        replacement["R5_" + ref + "_CAD_CONTACT_PROXY_NOT_SHIM_ORDER"] = s
    # Revised cradle keeps original PE stud position. Two end flanges attach the translated sink.
    cradle = box([-135, 83.9, 10], [275.5, 79.1, 2])
    for x in (-78, 124):
        flange = box([x, 154.5, 12], [2, 5.5, 60])
        for z in (22, 62):
            flange = flange.cut(cylinder(1.7, 4, [x - 1, 158, z], (1, 0, 0)))
        cradle = cradle.fuse(flange)
    floor = [
        {"center_xy": [x, y], "diameter": 3.4, "role": "carrier rail"}
        for x in (-115.5, 135.5)
        for y in (210, 290)
    ]
    floor += [
        {"center_xy": [x, y], "diameter": 4.4, "role": "sink cradle"}
        for x, y in ((-120, 87), (-120, 158.4), (135, 87), (-65, 87))
    ]
    for i, r in enumerate(floor):
        x, y = r["center_xy"]
        rad = r["diameter"] / 2
        if i < 4:
            # Reflected rails already have their corresponding tapped holes.
            replacement[P + f"FLOOR_MOUNT_SCREW_{i}"] = cylinder(1.5, 8, [x, y, 8]).fuse(
                cylinder(2.75, 1.5, [x, y, 6.5])
            )
        else:
            cradle = cradle.cut(cylinder(rad, 5, [x, y, 9]))
            replacement[P + f"FLOOR_MOUNT_SCREW_{i}"] = cylinder(2, 8, [x, y, 8]).fuse(
                cylinder(3.25, 1.5, [x, y, 6.5])
            )
            replacement[P + f"CRADLE_M4_NUT_{i}"] = cylinder(3.5, 3, [x, y, 12]).cut(
                cylinder(1.65, 3, [x, y, 12])
            )
    for n, s in replacement.items():
        if "CARRIER_RAIL" in n:
            cradle = cradle.cut(s)
    replacement[P + "SINK_CRADLE_CHASSIS_MOUNT"] = cradle
    air = {}
    for side in ("LEFT", "RIGHT"):
        s, air[side] = duct(side)
        replacement[P + side + "_DUCT"] = s.cut(
            replacement[P + ("RIGHT_PUSH_FAN" if side == "RIGHT" else "LEFT_PULL_FAN")]
        )
    # Independent screw-adjusted compression fixtures: metal anchor to sink, insulated pad to body.
    # These replace the unmodeled catalog clip concept. Force/creep/insulation remain prototype acceptance holds.
    clamps = []
    tools = {}
    for label, ref, x, z, front in [
        ("Q2", "Q2", -26.5, 53, 168.545),
        ("Q3", "Q3", -8.5, 53, 168.545),
        ("Q5", "Q5", 31.5, 53, 168.545),
        ("Q6", "Q6", 13.5, 53, 168.545),
        ("BR_L", "BR1", 89.5, 45, 169),
        ("BR_R", "BR1", 111.5, 45, 169),
    ]:
        width = 6 if ref != "BR1" else 5
        bracket = box([x - width / 2, 154, 72], [width, 24, 3]).fuse(
            box([x - width / 2, 175, z - 3], [width, 3, 75 - z + 3])
        )
        bracket = bracket.cut(cylinder(1.25, 5, [x, 174, z], (0, 1, 0))).cut(
            cylinder(1.7, 5, [x, 158, 71])
        )
        bracket = bracket.cut(cylinder(0.8, 4, [x, 155, 71.5]))
        replacement["R5_" + label + "_CLAMP_C_FRAME_6061"] = bracket
        replacement[P + "CUSTOM_SINK"] = replacement[P + "CUSTOM_SINK"].cut(
            cylinder(0.8, 5, [x, 155, 67])
        )
        replacement["R5_" + label + "_ANTI_ROTATION_DOWEL_1P5x8"] = cylinder(0.75, 8, [x, 155, 67])
        replacement[P + "CUSTOM_SINK"] = replacement[P + "CUSTOM_SINK"].cut(
            cylinder(1.25, 10, [x, 158, 62])
        )
        replacement["R5_" + label + "_ANCHOR_M3x12"] = cylinder(1.5, 12, [x, 158, 63]).fuse(
            cylinder(2.75, 3, [x, 158, 75])
        )
        pad = box([x - width / 2 - 1.1, front, z - 2], [width + 2.2, 2, 4])
        for side in (-1, 1):
            ax = x - width / 2 - 1.1 if side < 0 else x + width / 2 + 0.2
            pad = pad.fuse(box([ax, front + 2, z - 2], [0.9, 176.5 - front, 4]))
        rear = box([x - width / 2 - 1.1, 178.5, z - 3], [width + 2.2, 1, 6]).cut(
            cylinder(1.7, 2, [x, 178, z], (0, 1, 0))
        )
        pad = pad.fuse(rear)
        replacement["R5_" + label + "_PEEK_PRESSURE_PAD"] = pad
        replacement["R5_" + label + "_PRESSURE_M3x10"] = cylinder(
            1.5, 10, [x, front + 2, z], (0, 1, 0)
        ).fuse(cylinder(2.75, 3, [x, front + 12, z], (0, 1, 0)))
        tools[label + "_anchor"] = cylinder(2, 45, [x, 158, 78])
        tools[label + "_pressure"] = cylinder(2, 55, [x, front + 15, z], (0, 1, 0))
        clamps.append(
            {
                "label": label,
                "reference": ref,
                "x": x,
                "pressure_axis_z": z,
                "body_front_y": front,
                "anchor_xy": [x, 158],
                "adjustment_mm": [-1, 1],
                "force_N": None,
            }
        )
    # Two rear frame compression caps per fan; posts terminate before native board Y162.
    for side, centres in (("LEFT", (-94.5, -87.5)), ("RIGHT", (132.5, 138.5))):
        for i, x in enumerate(centres):
            y = 158.5
            cap = box([x - 3, 150, 72], [6, 11, 2]).cut(cylinder(1.7, 4, [x, y, 71]))
            post = (
                cylinder(2, 60, [x, y, 12])
                .cut(cylinder(1.25, 8, [x, y, 12]))
                .cut(cylinder(1.25, 8, [x, y, 64]))
            )
            replacement[f"R5_{side}_FAN_POST_{i}"] = post
            replacement[f"R5_{side}_FAN_TOP_M3_{i}"] = cylinder(1.5, 8, [x, y, 66]).fuse(
                cylinder(2.75, 3, [x, y, 74])
            )
            replacement[f"R5_{side}_FAN_BOTTOM_M3_{i}"] = cylinder(1.5, 10, [x, y, 8]).fuse(
                cylinder(2.75, 2, [x, y, 6])
            )
            replacement[f"R5_{side}_FAN_FRAME_CAPTURE_{i}"] = cap
            replacement[P + "SINK_CRADLE_CHASSIS_MOUNT"] = replacement[
                P + "SINK_CRADLE_CHASSIS_MOUNT"
            ].cut(cylinder(1.7, 5, [x, y, 9]))
            floor.append(
                {"center_xy": [x, y], "diameter": 3.4, "role": "fan post to cradle and floor"}
            )
    replacement["R5_RIGHT_FAN_FRAME_CAPTURE"] = replacement.pop(
        "R5_RIGHT_FAN_FRAME_CAPTURE_0"
    ).fuse(replacement.pop("R5_RIGHT_FAN_FRAME_CAPTURE_1"))
    # Replace the front barrier around the sink and stepped left duct; surrounding panels remain.
    front = box([-76, 154, 10], [218, 1.5, 72]).fuse(
        box([-125, 156, 10], [49, 1.5, 72]), box([-77.5, 154, 10], [1.5, 3.5, 72])
    )
    front = front.cut(box([-76.2, 153, 11.8], [200.4, 6, 60.4]))
    for n, shape in replacement.items():
        if any(
            k in n
            for k in (
                "CLAMP_C_FRAME",
                "ANCHOR_M3",
                "SINK_CRADLE",
                "CRADLE_M4_NUT",
                "FLOOR_MOUNT_SCREW",
                "FAN_POST",
                "FAN_FRAME_CAPTURE",
                "FAN_TOP_M3",
            )
        ):
            b = bounds(shape)
            front = front.cut(
                box(
                    [b[0] - 0.2, b[1] - 0.2, b[2] - 0.2],
                    [b[3] - b[0] + 0.4, b[4] - b[1] + 0.4, b[5] - b[2] + 0.4],
                )
            )
    replacement["BASE_PROPOSAL_FRONT_PROFILE"] = front
    replacement["BASE_PROPOSAL_LEFT_WALL"] = (
        base["BASE_PROPOSAL_LEFT_WALL"]
        .cut(box([-126, 153, 9], [4, 3, 75]))
        .cut(base["BASE_PROPOSAL_REAR_WALL"])
        .cut(front)
    )
    pe_tools, pe_interface = add_pe(replacement, base, box, cylinder)
    pre_pe = read_parts(OUT / "checkpoints/pre-pe/cooling-replacements.step")
    owner_cutouts = pre_pe["BASE_PROPOSAL_LEFT_WALL"].cut(
        validation_context["BASE_PROPOSAL_LEFT_WALL"]
    )
    replacement["BASE_PROPOSAL_LEFT_WALL"] = replacement["BASE_PROPOSAL_LEFT_WALL"].cut(
        owner_cutouts
    )
    wall_solids = sorted(
        replacement["BASE_PROPOSAL_LEFT_WALL"].Solids(), key=lambda s: s.Volume(), reverse=True
    )
    pe_interface["discarded_unattached_machining_chip_mm3"] = [s.Volume() for s in wall_solids[1:]]
    assert all(s.Volume() < 0.2 for s in wall_solids[1:]), "Unexpected detached barrier section"
    replacement["BASE_PROPOSAL_LEFT_WALL"] = wall_solids[0]
    tools.update(pe_tools)
    floor.extend(pe_interface["floor_drilling"])
    prior_names = set(
        json.loads((OUT / "checkpoints/pre-pe/checks.json").read_text())["replacement_bounds"]
    )
    removed = sorted(set(removed) | set(replacement).intersection(base) | prior_names)
    for cy in (285, 295):
        replacement[P + "CARRIER_RAIL_-122p5"] = replacement[P + "CARRIER_RAIL_-122p5"].cut(
            cylinder(1.25, 8, [135.5, cy, 9])
        )
    context = {
        n: s
        for n, s in validation_context.items()
        if n not in removed
        and n not in replacement
        and not n.startswith(("BASE_BASE_native19_", "RIGID_NATIVE19_"))
    }
    # Owner cuts the union of all packages' drill changes; this temporary floor is only for collision validation.
    floorname = "BASE_BASE_R4_two_bend_bottom_and_sides"
    for r in floor:
        x, y = r["center_xy"]
        context[floorname] = context[floorname].cut(cylinder(r["diameter"] / 2, 5, [x, y, 7]))
    return (
        replacement,
        removed,
        context,
        native,
        air,
        tools,
        {
            "floor_drilling": floor,
            "dedicated_sink_pe": pe_interface,
            "obsolete_floor_drilling": [
                {"center_xy": [x, y], "diameter": 3.4} for x in (-116.5, 134.5) for y in (210, 290)
            ]
            + [
                {"center_xy": [x, y], "diameter": 4.4}
                for x, y in ((-120, 87), (-120, 158), (120, 87), (120, 160))
            ],
            "floor_process": "NEW floor: remove old cooling hole pattern before combining revised cooling and other package holes; not field-drill overlapping holes",
            "right_rail_name": P + "CARRIER_RAIL_-122p5",
            "left_rail_name": P + "CARRIER_RAIL_128p5",
            "clamps": clamps,
            "source": {
                "path": str(immutable_source.relative_to(ROOT)),
                "sha256": sha(immutable_source),
            },
            "validation_context_source": {
                "path": str(source.relative_to(ROOT)),
                "sha256": sha(source),
            },
            "native_source": {
                "path": str(native_path.relative_to(ROOT)),
                "sha256": sha(native_path),
            },
        },
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    new, removed, context, native, air, tools, data = build()
    print("built replacements", len(new), flush=True)
    native_hits = hits(new, native)
    context_hits = hits(new, context)
    print("context checks complete", flush=True)
    pairs = []
    names = list(new)
    for i, n in enumerate(names):
        pairs += hits({n: new[n]}, {k: new[k] for k in names[i + 1 :]})
    contact = []
    for ref in ("Q2", "Q3", "Q5", "Q6", "BR1"):
        proxy = new["R5_" + ref + "_CAD_CONTACT_PROXY_NOT_SHIM_ORDER"]
        contact.append(
            {
                "reference": ref,
                "proxy_to_source_distance_mm": proxy.distance(native[ref]),
                "source_slice_contact_area_mm2": proxy.translate((0, 0.001, 0))
                .intersect(native[ref])
                .Volume()
                / 0.001,
                "scope": "Generic STEP contact only; not actual part seating or thermal validation",
            }
        )
    pe_paths = [
        (P + "CUSTOM_SINK", "R5_PE_SINK_EXTERNAL_TOOTH_WASHER_ENVELOPE"),
        ("R5_PE_SINK_EXTERNAL_TOOTH_WASHER_ENVELOPE", "R5_PE_SINK_FUSED_COPPER_END_PAD"),
        ("R5_PE_SINK_FUSED_COPPER_END_PAD", "R5_PE_BRAID_MAX_SECTION_ENVELOPE"),
        ("R5_PE_BRAID_MAX_SECTION_ENVELOPE", "R5_PE_CRADLE_FUSED_COPPER_END_PAD"),
        ("R5_PE_CRADLE_FUSED_COPPER_END_PAD", "R5_PE_CRADLE_INTERLUG_SPACER"),
        ("R5_PE_CRADLE_INTERLUG_SPACER", P + "PE_BOND_ROUTE_ALLOCATION"),
        (P + "PE_BOND_ROUTE_ALLOCATION", "R5_PE_CRADLE_CONDUCTIVE_SPACER"),
        ("R5_PE_CRADLE_CONDUCTIVE_SPACER", P + "SINK_CRADLE_CHASSIS_MOUNT"),
    ]
    combined = context | new
    pe_contacts = [
        {"a": a, "b": b, "distance_mm": combined[a].distance(combined[b])} for a, b in pe_paths
    ]
    deferred_keys = {
        (P + "CARRIER_RAIL_-122p5", "PAIRED_POST_M3x60_CS_285"),
        (P + "CARRIER_RAIL_-122p5", "PAIRED_POST_M3x60_CS_295"),
        ("BASE_PROPOSAL_LEFT_WALL", "OUT_FLOOR_M3x6_-126.0"),
        ("BASE_PROPOSAL_LEFT_WALL", "OUT_MACHINED_BRACKET_-128"),
    }
    deferred = [h for h in context_hits if (h["new"], h["context"]) in deferred_keys]
    context_hits = [h for h in context_hits if (h["new"], h["context"]) not in deferred_keys]
    pe_parts = {k: v for k, v in new.items() if k.startswith("R5_PE_")}
    report = data | {
        "packaging_deferred_context_hits": deferred,
        "pe_terminal_contacts": pe_contacts,
        "pe_vs_airway": hits(pe_parts, air),
        "pe_tool_vs_new_parts": hits({k: v for k, v in tools.items() if k.startswith("PE_")}, new),
        "contact_checks": contact,
        "status": "RIGID_ORIENTATION_COOLING_CANDIDATE_NOT_RELEASED",
        "source_sha256": sha(Path(__file__)),
        "pe_adapter_sha256": sha(HERE / "pe_bond.py"),
        "replacement_solid_counts": {n: len(s.Solids()) for n, s in new.items()},
        "replacement_bounds": {n: bounds(s) for n, s in new.items()},
        "native_hits": native_hits,
        "context_hits": context_hits,
        "replacement_pair_hits": pairs,
        "tool_hits": hits(tools, native | context),
        "airway_obstacles": hits(air, native | context),
        "sink_solids": len(new[P + "CUSTOM_SINK"].Solids()),
        "removed_names": removed,
    }
    for name, parts in [
        ("cooling-replacements", new),
        (
            "cooling-rigid-context",
            context | new | {"RIGID_NATIVE19_" + n: s for n, s in native.items()},
        ),
    ]:
        a = cq.Assembly(name=name)
        for n, s in parts.items():
            if not s.isValid():
                raise ValueError("Invalid " + n)
            a.add(s, name=n)
        path = OUT / (name + ".step")
        a.export(str(path))
        loaded = cq.importers.importStep(str(path)).val()
        report[name] = {
            "sha256": sha(path),
            "valid": loaded.isValid(),
            "solids": len(loaded.Solids()),
        }
    (OUT / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT / "removed_names.json").write_text(json.dumps(removed, indent=2) + "\n")
    (OUT / "interface.json").write_text(json.dumps(data, indent=2) + "\n")
    print(
        json.dumps(
            {k: report[k] for k in ["native_hits", "context_hits", "sink_solids", "tool_hits"]},
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
