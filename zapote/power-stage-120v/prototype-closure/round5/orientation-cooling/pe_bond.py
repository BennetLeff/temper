"""Dimensioned custom PE jumper CAD adapter; electrical ratings remain unqualified."""

from __future__ import annotations

import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "round4/catch"))
from build_carrier import rounded_route  # noqa: E402

P = "BASE_BASE_R2_"


def add_pe(new, base, box, cylinder):
    sx, sy = -66, 157.9

    def ring(ro, ri, z, h, x=sx, y=sy):
        return cylinder(ro, h, [x, y, z]).cut(cylinder(ri, h, [x, y, z]))

    new[P + "CUSTOM_SINK"] = new[P + "CUSTOM_SINK"].cut(cylinder(1.65, 10, [sx, sy, 62]))
    new["R5_PE_SINK_EXTERNAL_TOOTH_WASHER_ENVELOPE"] = ring(4, 2.15, 72, 0.5)
    lug = box([sx - 5, sy - 3.5, 72.5], [10, 7, 1]).cut(cylinder(2.15, 1, [sx, sy, 72.5]))
    new["R5_PE_SINK_FUSED_COPPER_END_PAD"] = lug
    new["R5_PE_SINK_FLAT_WASHER"] = ring(4.5, 2.15, 73.5, 0.8)
    new["R5_PE_SINK_SPRING_WASHER_ENVELOPE"] = ring(4, 2.15, 74.3, 1)
    new["R5_PE_SINK_M4x12_BOLT"] = cylinder(2, 12, [sx, sy, 63.3]).fuse(
        cylinder(3.5, 4, [sx, sy, 75.3])
    )
    # Conductive spacer seats existing cradle braid at its modeled16mm plane.
    new["R5_PE_CRADLE_CONDUCTIVE_SPACER"] = ring(4.5, 2.15, 12, 4, -128, 160)
    new["R5_PE_CRADLE_FUSED_COPPER_END_PAD"] = box([-133, 156.5, 19], [10, 7, 1]).cut(
        cylinder(2.15, 1, [-128, 160, 19])
    )
    new["R5_PE_CRADLE_FLAT_WASHER"] = ring(4.5, 2.15, 20, 0.8, -128, 160)
    new["R5_PE_CRADLE_EXTERNAL_TOOTH_WASHER_ENVELOPE"] = ring(4, 2.15, 20.8, 0.5, -128, 160)
    new["R5_PE_CRADLE_M4_NUT_ENVELOPE"] = ring(4.05, 1.65, 21.3, 3.2, -128, 160)
    new["R5_PE_CRADLE_INTERLUG_SPACER"] = ring(4.5, 2.15, 17, 2, -128, 160)
    new[P + "SINK_DEDICATED_PE_STUD"] = base[P + "SINK_DEDICATED_PE_STUD"]
    points = [
        [-66, 161.4, 73],
        [-66, 169, 73],
        [-128, 169, 73],
        [-128, 169, 19.5],
        [-128, 163.5, 19.5],
    ]
    path, plane, margins = rounded_route(points, 3)
    envelope = cq.Workplane(plane).circle(2.2).sweep(path, isFrenet=False).val()
    # Fused tails are flattened to1mm inZ at both horizontal ring-pad landings.
    envelope = envelope.cut(box([-70, 160, 60], [8, 4.8, 12.5])).cut(
        box([-70, 160, 73.5], [8, 4.8, 10])
    )
    envelope = envelope.cut(box([-132, 163, 10], [8, 3, 9])).cut(box([-132, 163, 20], [8, 3, 10]))
    # Circular4.4mm swept allocation bounds a4x1.5mm braid; terminal pads touch itsendplane.
    new["R5_PE_BRAID_MAX_SECTION_ENVELOPE"] = envelope
    # Swaged tinned-copper stop collars bear against both faces of the lower split guide.
    # They provide a positive axial restraint; swage pull strength remains unqualified.
    for z in (25, 33):
        new[f"R5_PE_BRAID_SWAGED_STOP_{z}"] = cylinder(3, 2, [-128, 169, z]).cut(
            cylinder(2.2, 2, [-128, 169, z])
        )
    # Two floor-fixed halves surround the braid without threading its fused end pads through a hole.
    rail = box([-141, 165, 12], [9, 10, 57])
    for z in (30, 60):
        arm = box([-139, 166, z - 3], [11, 6, 6]).fuse(cylinder(3.2, 6, [-128, 169, z - 3]))
        rail = rail.fuse(arm).cut(cylinder(2.3, 8, [-128, 169, z - 4]))
    rail = rail.cut(box([-137.2, 164, 15.8], [7, 12, 1.4]))
    foot = box([-142, 161.5, 10], [15, 15.5, 2])
    new[P + "SINK_CRADLE_CHASSIS_MOUNT"] = new[P + "SINK_CRADLE_CHASSIS_MOUNT"].fuse(foot)
    holes = []
    for y in (167, 173):
        x = -139
        rail = rail.cut(cylinder(1.25, 8, [x, y, 12]))
        new[P + "SINK_CRADLE_CHASSIS_MOUNT"] = new[P + "SINK_CRADLE_CHASSIS_MOUNT"].cut(
            cylinder(1.7, 4, [x, y, 9])
        )
        new[f"R5_PE_STRAIN_BASE_M3_{y}"] = cylinder(1.5, 10, [x, y, 8]).fuse(
            cylinder(2.75, 2, [x, y, 6])
        )
        holes.append(
            {
                "center_xy": [x, y],
                "diameter": 3.4,
                "role": "PE split strain guide dedicated attachment",
            }
        )
    new["R5_PE_STRAIN_SUPPORT_FRONT"] = rail.intersect(box([-150, 160, 0], [30, 9, 80]))
    new["R5_PE_STRAIN_SUPPORT_REAR"] = rail.intersect(box([-150, 169, 0], [30, 10, 80]))
    wall = new["BASE_PROPOSAL_LEFT_WALL"].cut(box([-126, 154.5, 11.8], [6, 13, 17.2]))
    pocket = box([-122.8, 154.5, 11.8], [1, 13, 17.2]).fuse(
        box([-125, 154.5, 11.8], [3.2, 1.5, 17.2]), box([-125, 166, 11.8], [3.2, 1.5, 17.2])
    )
    wall = wall.fuse(pocket).cut(new["BASE_PROPOSAL_FRONT_PROFILE"])
    for z in (30, 60):
        wall = wall.cut(box([-126, 165.6, z - 3.2], [6, 6.8, 6.4]))
    wall = wall.cut(cylinder(3, 5, [-127, 169, 73], (1, 0, 0)))
    grommet = (
        cylinder(3, 1.5, [-125, 169, 73], (1, 0, 0))
        .fuse(
            cylinder(4, 0.5, [-125.5, 169, 73], (1, 0, 0)),
            cylinder(4, 0.5, [-123.5, 169, 73], (1, 0, 0)),
        )
        .cut(cylinder(2.5, 3, [-126, 169, 73], (1, 0, 0)))
    )
    new["R5_PE_WALL_SPLIT_BUSH_FRONT"] = grommet.intersect(box([-127, 164, 68], [5, 5, 10]))
    new["R5_PE_WALL_SPLIT_BUSH_REAR"] = grommet.intersect(box([-127, 169, 68], [5, 5, 10]))
    for n in ("SINK_CRADLE_CHASSIS_MOUNT", "CRADLE_M4_NUT_5", "FLOOR_MOUNT_SCREW_5", "LEFT_DUCT"):
        wall = wall.cut(new[P + n])
    new["BASE_PROPOSAL_LEFT_WALL"] = wall
    new["BASE_PROPOSAL_FRONT_PROFILE"] = new["BASE_PROPOSAL_FRONT_PROFILE"].cut(
        box([-71.2, 153, 71.8], [10.4, 10, 7.7])
    )
    tools = {
        "PE_sink_socket": cylinder(2, 40, [sx, sy, 79.3]),
        "PE_cradle_socket": cylinder(4.5, 70, [-128, 160, 27]),
    }
    data = {
        "status": "DIMENSIONED_CUSTOM_PE_CANDIDATE_NOT_FAULT_QUALIFIED",
        "sink_terminal_xyz": [sx, sy, 72],
        "cradle_terminal_xyz": [-128, 160, 12],
        "route_centerline_vertices": points,
        "route_centerline_bend_radius_mm": 3,
        "route_tangent_margins_mm": margins,
        "max_braid_section_mm": [4, 1.5],
        "swept_conservative_diameter_mm": 4.4,
        "effective_copper_area_mm2_min": 2.5,
        "conductor": "Fine-strand tinned copper braid, custom fused copperM4 end pads10x7x1 with4.3mmholes; no strand count/ampacity/faultwithstand qualification implied",
        "process": "Bare masked sink terminal; independentM4 bolt, externaltooth/flat/springwasher locking stack; cradle existingdedicatedweldedstud requires qualifiedweld; spacer supports existingbraid belownewpad; no coolingmountbolt is electricalbond",
        "holds": [
            "supplier braid bend/twist/termination manufacturing confirmation",
            "mechanical torque/locking/thermalcycling/corrosion",
            "measured PE resistance and fault-current withstand",
            "material recognition and retained strain clamp strength",
        ],
        "floor_drilling": holes,
    }
    return tools, data
