"""CAD adapter for round5 declared geometry; labels preserve unresolved interfaces."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/protection"
sys.path.insert(0, str(HERE.parents[1] / "round3/packaging"))
from build_proposal import bounds, box, hits, read_parts  # noqa: E402

sys.path.insert(0, str(HERE.parents[1] / "round4/catch"))
from build_carrier import rounded_route  # noqa: E402


def cylinder(a: list[float], b: list[float], radius: float) -> cq.Shape:
    start, end = cq.Vector(*a), cq.Vector(*b)
    d = end - start
    return cq.Solid.makeCylinder(radius, d.Length, start, d.normalized())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(name: str, parts: dict[str, cq.Shape]) -> dict:
    asm = cq.Assembly(name=name)
    for key, shape in parts.items():
        if not shape.isValid():
            raise ValueError(f"invalid part {key}")
        asm.add(shape, name=key)
    path = OUT / f"{name}.step"
    asm.export(str(path))
    shape = cq.importers.importStep(str(path)).val()
    if not shape.isValid():
        raise ValueError("STEP reimport failed")
    if name == "catch-power-interposer":
        cq.exporters.export(
            shape,
            str(OUT / f"{name}.svg"),
            opt={"width": 900, "height": 600, "showAxes": False, "projectionDir": (0, -1, 1)},
        )
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path),
        "solids": len(shape.Solids()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    receipt = OUT / "hardware-geometry.json"
    receipt.write_text('{"status":"INCOMPLETE"}\n')
    pod_file = (
        ROOT / "output/temper-prototype-closure/round3/packaging/pod-reservations-design-only.step"
    )
    catch_file = (
        ROOT / "output/temper-prototype-closure/round4/catch/r4-catch-carrier-routed-design.step"
    )
    pod = read_parts(pod_file)
    replaced = [
        k
        for k in pod
        if k
        in ("PART_RPRE1", "PART_RPRE2", "PART_TCO1_CLAMP_AND_SLEEVE", "PART_TCO2_CLAMP_AND_SLEEVE")
    ]
    if len(replaced) != 4:
        raise ValueError("unexpected pod identities")
    for key in replaced:
        del pod[key]
    mount = pod.pop("CASE_HOT_PLATE")
    hot = {}
    # Drawing axes: L1=182, flange height55.5max; base4.3; body30max deep.
    # Stack vertically to fit existing340x210 plate, instead of two182mm bodies side by side.
    holes = []
    for i, z in enumerate((345.0, 410.0), 1):
        flange = box([70, 189.7, z], [182, 4.3, 55.5])
        # Top-view drawing specifies 45 mm transverse centre pitch. Locate
        # the pattern about the authored envelope centre; 5.4 is the hole
        # diameter, not an edge datum. Supplier edge tolerances remain open.
        centre_z = z + 55.5 / 2
        for x in (111.0, 211.0):
            for hz in (centre_z - 22.5, centre_z + 22.5):
                h = cylinder([x, 188, hz], [x, 201, hz], 2.7)
                if x == 111.0:
                    # Supplier left pair are 8 mm overall longitudinal slots,
                    # 5.4 mm wide; the plate retains centred round drill holes.
                    slot = cylinder([x - 1.3, 188, hz], [x - 1.3, 201, hz], 2.7)
                    slot = slot.fuse(
                        cylinder([x + 1.3, 188, hz], [x + 1.3, 201, hz], 2.7)
                    ).fuse(box([x - 1.3, 188, hz - 2.7], [2.6, 13, 5.4]))
                    flange = flange.cut(slot)
                else:
                    flange = flange.cut(h)
                mount = mount.cut(h)
                holes.append([x, hz, 5.4])
        hot[f"RP{i}_HS400_FLANGE_DRAWING"] = flange
        hot[f"RP{i}_HS400_BODY_MAX_ENVELOPE"] = box([70, 164, z + 5.25], [182, 25.7, 45])
        hot[f"TF{i}_INSULATED_CONTACT_COUPON_HOLD"] = box([150, 158, z + 19], [25, 6, 12])
        # Flying leads are included as straight first sections only; later bend/cut length is not released.
        for n, hz in enumerate((z + 21.25, z + 34.25), 1):
            hot[f"RP{i}_LEAD{n}_LOCAL_EXIT_ENVELOPE"] = cylinder(
                [252, 173, hz], [285, 173, hz], 1.75
            )
    pod["CASE_HOT_PLATE_PC125_DRILLED"] = mount
    collision = hits(hot, pod)
    # Catch power interposer: one-mm machined copper, mechanically retained on unplated carrier.
    catch = read_parts(catch_file)
    local = {}
    old_carrier = catch.pop("DC1_LOCAL_CARRIER")
    carrier = old_carrier
    anode = box([42.04, 337.4, 45.6], [14.96, 2.8, 1])
    # Broaden only the remote M4 landing, away from the diode lead pair.
    anode = anode.fuse(box([49, 334.3, 45.6], [9, 9, 1]))
    anode = anode.cut(cylinder([43.44, 338.8, 44], [43.44, 338.8, 48], 1.0))
    anode = anode.cut(cylinder([53.5, 338.8, 44], [53.5, 338.8, 48], 2.15))
    cathode = box([35.5, 336.3, 45.6], [5, 10.7, 1])
    cathode = cathode.fuse(catch.pop("CATHODE_FORMED_COPPER_LINK"))
    cathode = cathode.cut(box([39.4, 334, 45], [3, 10, 3]))
    cathode = cathode.cut(cylinder([38, 338.8, 44], [38, 338.8, 49], 1.0))
    # One custom machined conductor replaces two impossible overlapping pieces.
    for x, y in ((53.5, 338.8), (38, 344.0)):
        carrier = carrier.cut(cylinder([x, y, 43], [x, y, 48], 2.15))
    local["DC1_UNPLATED_POWER_CARRIER"] = carrier
    local["DC1_ANODE_C110_TINNED_1MM"] = anode
    local["DC1_CATHODE_C110_MACHINED_LINK"] = cathode
    route_source = ROOT / "output/temper-prototype-closure/round4/catch/route-geometry.json"
    routes = json.loads(route_source.read_text())["routes"]
    updated = next(r for r in routes if r["name"] == "FUSED_P_TO_ANODE")
    updated["control_points_mm"][-1] = [53.5, 338.8, 48]
    path, plane, margins = rounded_route(updated["control_points_mm"], 22)
    catch["FUSED_P_TO_ANODE_INSULATED_WIRE_MAX"] = (
        cq.Workplane(plane)
        .circle(3.937 / 2)
        .sweep(cq.Workplane().newObject([path]), isFrenet=True)
        .val()
    )
    updated["sampled_centerline_mm"] = [
        list(path.positionAt(i / 400).toTuple()) for i in range(401)
    ]
    updated["length_mm"] = path.Length()
    updated["straight_tangent_margins_mm"] = margins
    (OUT / "route-geometry.json").write_text(
        json.dumps(
            {
                "routes": routes,
                "source_sha256": digest(route_source),
                "status": "UPDATED_EXTERNAL_WIRES_NOT_INTERNAL_CURRENT_DISTRIBUTION",
            },
            indent=2,
        )
        + "\n"
    )
    # No common fastener joins anode and cathode. NC lead receives only an isolated clearance hole.
    local["DC1_ANODE_TERMINATION_ACCESS"] = cylinder([53.5, 338.8, 46.6], [53.5, 338.8, 51], 3.5)
    # Access is a visible reservation, excluded from the material-only export below.
    physical = {k: v for k, v in local.items() if not k.endswith("ACCESS")}
    overlap = hits(physical, catch)
    # Separate exact authored external geometry from unverified internal closures.
    bus = next(r for r in routes if r["name"] == "BUS_P")["sampled_centerline_mm"]
    ret = next(r for r in routes if r["name"] == "HV_RET")["sampled_centerline_mm"]
    fused = updated["sampled_centerline_mm"]
    segments = [
        {"id": "wire_bus", "points_mm": bus, "basis": "AUTHORED_ROUTE"},
        {
            "id": "holder_fuse_internal",
            "points_mm": [bus[-1], fused[0]],
            "basis": "UNRESOLVED_SURROGATE_NOT_VENDOR_INTERNAL_PATH",
        },
        {"id": "wire_fused", "points_mm": fused, "basis": "AUTHORED_ROUTE"},
        {
            "id": "anode_terminal_copper",
            "points_mm": [fused[-1], [53.5, 338.8, 46.1], [43.44, 338.8, 46.1], [43.44, 338.8, 52]],
            "basis": "AUTHORED_COPPER_CENTERLINE_PLUS_LEAD",
        },
        {
            "id": "diode_internal",
            "points_mm": [[43.44, 338.8, 52], [38, 338.8, 52]],
            "basis": "UNRESOLVED_DIE_BOND_INTERNAL_PATH",
        },
        {
            "id": "cathode_link",
            "points_mm": [
                [38, 338.8, 52],
                [38, 338.8, 46.5],
                [38, 347.5, 46.5],
                [27.5, 347.5, 46.5],
                [27.5, 347.5, 60],
                [27.5, 351.6, 60],
            ],
            "basis": "AUTHORED_LINK_CENTERLINE",
        },
        {
            "id": "capacitor_internal",
            "points_mm": [[27.5, 351.6, 60], [27.5, 355, 60], [80, 355, 60], [80, 349, 60]],
            "basis": "UNRESOLVED_DISTRIBUTED_FOUR_PIN_CAPACITOR_NOT_CONDUCTING_DC_LINK",
        },
        {"id": "wire_return", "points_mm": list(reversed(ret)), "basis": "AUTHORED_ROUTE"},
        {
            "id": "native19_bus_closure",
            "points_mm": [ret[0], bus[0]],
            "basis": "PORT_CLOSURE_ONLY_NOT_NATIVE_COPPER_EXTRACTION",
        },
    ]
    for a, b in zip(segments, segments[1:] + segments[:1], strict=True):
        if (
            max(abs(x - y) for x, y in zip(a["points_mm"][-1], b["points_mm"][0], strict=True))
            > 1e-6
        ):
            raise ValueError(f"open geometric topology {a['id']} -> {b['id']}")
    (OUT / "closed-loop-topology.json").write_text(
        json.dumps(
            {
                "status": "CONNECTED_GEOMETRIC_SCAFFOLD_NOT_COMPLETE_FIELD_GEOMETRY",
                "segments": segments,
                "prohibitions": [
                    "Do not extract surrogate paths and label the resulting inductance installed or bounded",
                    "Do not treat capacitor dielectric port closure as a solid conductor",
                ],
            },
            indent=2,
        )
        + "\n"
    )
    material_distance = anode.distance(cathode)
    if material_distance < 2.63:
        raise ValueError(f"anode/cathode copper separation changed: {material_distance}")
    # Native sensor geometry comes from its sole owner, never an invented populated-card model.
    sensor_mount = {
        "board_size_mm": [60, 35],
        "local_to_world": "[x,y] -> [103,348+x,43+y]",
        "npth_local_mm": [[17, 32, 2.7], [57, 32, 2.7], [57, 3, 2.7]],
        "hv_pads_local_mm": [[3, 3], [3, 28]],
        "jst_origin_local_mm": [53, 10],
        "status": "OWNER_INTERFACE_READY; populated STEP join and mounts not yet incorporated",
    }
    exports = [
        export("pc125-pod-layout", pod | hot),
        export("catch-power-interposer", physical),
        export("catch-with-power-interposer-review", catch | physical),
    ]
    result = {
        "status": "DESIGN_GEOMETRY_WITH_EXPLICIT_HOLDS",
        "inputs": {
            str(p.relative_to(ROOT)): digest(p)
            for p in (pod_file, catch_file, HERE / "interface.json", Path(__file__))
        },
        "exports": exports,
        "precharge_mount_holes_xz_d_mm": holes,
        "precharge_mount_datum": {
            "transverse_pitch_mm": 45.0,
            "longitudinal_pitch_mm": 100.0,
            "transverse_location": "Symmetric about authored 55.5 mm maximum flange envelope centre; supplier edge tolerance not established",
            "longitudinal_location": "First column 41 mm from drawing L1 end; second column at L3+L2",
            "mount_plate_holes": "5.4 mm circular holes; resistor supplier 8 mm slots are not plate holes",
        },
        "precharge_context_collisions": collision,
        "catch_contacts_and_collisions": overlap,
        "power_copper_edge_separation_mm": material_distance,
        "clearance_disposition": "Local diode anode/cathode copper gap is UNACCEPTED pending actual insulation/voltage rule; does not pass8mm general screen. Narrow solder-pin neck intentionally widens only away from lead pair.",
        "power_part_bounds_mm": {k: bounds(v) for k, v in physical.items()},
        "sensor_interface": sensor_mount,
        "holds": [
            "Anode wire now ends at new M4 landing; lug/crimp/stripped-wire termination remains unmodeled",
            "No manufactured thermal interface, clamp or US141 internal terminal geometry is implied",
            "Flying leads have manufacturer300mm minimum supplied length; final routing/trim processing remains open",
            "Catch contacts in report are not blanket-accepted; machined conductor and solder joint require process review",
            "Cold geometry does not establish thermal capacity, insulation or pulse survival",
        ],
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"exports": exports, "pod_collisions": collision, "catch_contacts": overlap}, indent=2
        )
    )


if __name__ == "__main__":
    main()
