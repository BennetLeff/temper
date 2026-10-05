"""Dimensioned R7 bench fixtures; geometry is not a hot-seal or load rating."""

from __future__ import annotations

import json
import math
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parent


def cylinder(radius: float, z: float, height: float, x: float = 0, y: float = 0) -> cq.Shape:
    return cq.Solid.makeCylinder(radius, height, cq.Vector(x, y, z))


def box(dx: float, dy: float, dz: float, x: float, y: float, z: float) -> cq.Shape:
    return (
        cq.Workplane("XY").box(dx, dy, dz, centered=(True, True, False)).translate((x, y, z)).val()
    )


def pipe_x(radius: float, start: float, end: float, z: float) -> cq.Shape:
    return cq.Solid.makeCylinder(radius, end - start, cq.Vector(start, 0, z), cq.Vector(1, 0, 0))


def export(parts: dict[str, cq.Shape], name: str) -> dict[str, object]:
    assembly = cq.Assembly(name=name)
    details: dict[str, object] = {}
    for label, shape in parts.items():
        if not shape.isValid():
            raise ValueError(f"Invalid solid: {label}")
        assembly.add(shape, name=label)
        bounds = shape.BoundingBox()
        details[label] = {
            "volume_mm3": shape.Volume(),
            "bounds_mm": [
                bounds.xmin,
                bounds.xmax,
                bounds.ymin,
                bounds.ymax,
                bounds.zmin,
                bounds.zmax,
            ],
            "valid": True,
        }
    intersections = []
    labels = list(parts)
    for i, left in enumerate(labels):
        for right in labels[i + 1 :]:
            overlap = parts[left].intersect(parts[right]).Volume()
            if overlap > 1e-6:
                intersections.append({"left": left, "right": right, "volume_mm3": overlap})
    if intersections:
        raise ValueError(f"Unexpected fixture intersections: {intersections}")
    dest = ROOT / f"{name}.step"
    assembly.save(str(dest))
    dest.write_text("\n".join(line.rstrip() for line in dest.read_text().splitlines()) + "\n")
    restored = cq.importers.importStep(str(dest)).val()
    if not restored.isValid():
        raise ValueError(f"Invalid STEP round trip: {name}")
    return {
        "parts": details,
        "step_roundtrip_valid": True,
        "all_pair_solid_intersections_over_1e_minus6_mm3": intersections,
    }


def frame() -> dict[str, cq.Shape]:
    parts = {
        "base_plate_120x100x10": box(120, 100, 10, 0, 0, -65),
        "left_upright": box(10, 80, 155, -50, 0, -55),
        "right_upright": box(10, 80, 155, 50, 0, -55),
        "crossbeam": box(110, 40, 10, 0, 0, 100),
        "translation_stage_ENVELOPE_UNSELECTED": box(32, 30, 20, 0, 0, 80),
        "force_transducer_ENVELOPE_UNSELECTED": box(20, 20, 15, 0, 0, 65),
        "thermal_standoff_D4": cylinder(2, 3.6, 61.4),
        "cap_force_coupon_D6x3": cylinder(3, 0.6, 3),
        "mock_glass_D50_hole18": cylinder(25, -4, 4).cut(cylinder(9, -4, 4)),
    }
    plate = box(90, 80, 8, 0, 0, -12).cut(cylinder(15, -12, 8))
    clamp = box(70, 60, 10, 0, 0, -22).cut(cylinder(14.1, -22, 10))
    clamp = clamp.cut(box(1, 30, 10, 0, 15, -22))
    for x in [-35, 35]:
        for y in [-30, 30]:
            clamp = clamp.cut(cylinder(3.25, -22, 10, x, y))
    parts["datum_plate_D30_clearance"] = plate
    parts["split_housing_clamp_D28p2_UNQUALIFIED"] = clamp
    for x in [-35, 35]:
        for y in [-30, 30]:
            parts[f"support_post_{x}_{y}"] = cylinder(3, -55, 43, x, y)
    # Dashed drawing region, not a solid: cartridge and optical heads are separate.
    return parts


def pressure_cell() -> tuple[dict[str, cq.Shape], dict[str, object]]:
    throat_volume = math.pi * 4**2 * 2
    chamber_height = (1000 - throat_volume) / (math.pi * 6**2)
    main = cylinder(6, -2 - chamber_height, chamber_height).fuse(cylinder(4, -2.001, 2.001))
    plenum_height = 10000 / (math.pi * 10**2)
    plenum_low = -6 - plenum_height / 2
    fluid = main.fuse(pipe_x(0.75, -25, 120, -6))
    fluid = fluid.fuse(cylinder(10, plenum_low, plenum_height, 120))
    fluid = fluid.fuse(
        cylinder(1, plenum_low + plenum_height - 0.01, 20 - plenum_low - plenum_height + 0.01, 120)
    )
    fluid = fluid.fuse(cylinder(0.75, -6, 26, 20))
    outer = cylinder(10, -12, 12).fuse(pipe_x(1.5, -25, 112, -6))
    outer = outer.fuse(cylinder(12, plenum_low - 2, plenum_height + 4, 120))
    outer = outer.fuse(
        cylinder(2, plenum_low + plenum_height, 20 - plenum_low - plenum_height, 120)
    )
    outer = outer.fuse(cylinder(1.5, -6, 26, 20))
    outer = outer.fuse(box(10, 10, 6, 20, 0, 20))
    shell = outer.cut(fluid)
    if len(fluid.Solids()) != 1:
        raise ValueError("Pressure fluid topology must be one connected solid")
    if shell.intersect(fluid).Volume() > 1e-6:
        raise ValueError("Fluid and shell intersect")
    parts = {
        "connected_pressure_shell_GEOMETRY_ONLY": shell,
        "flat_test_membrane_ENVELOPE_UNQUALIFIED": cylinder(10, 0, 0.1),
        "membrane_clamp_ring_D8_aperture": cylinder(10, 0.1, 3).cut(cylinder(4, 0.1, 3)),
        "membrane_load_button_D6": cylinder(3, 0.1, 4),
    }
    cq.exporters.export(fluid, str(ROOT / "pressure-fluid-domain.step"))
    fluid_path = ROOT / "pressure-fluid-domain.step"
    fluid_path.write_text(
        "\n".join(line.rstrip() for line in fluid_path.read_text().splitlines()) + "\n"
    )
    fluid_roundtrip = cq.importers.importStep(str(fluid_path)).val()
    if not fluid_roundtrip.isValid() or len(fluid_roundtrip.Solids()) != 1:
        raise ValueError("Invalid connected fluid STEP round trip")
    return parts, {
        "connected_fluid_solids": 1,
        "fluid_roundtrip_valid": True,
        "total_fluid_volume_mm3": fluid.Volume(),
        "main_nominal_void_mm3": main.Volume(),
        "remote_plenum_void_mm3": 10000,
        "pressure_path_ID_mm": 1.5,
        "path_main_to_plenum_centers_mm": 120,
        "tube_uniform_span_between_chamber_walls_mm": 104,
        "pressure_tap_x_mm": 20,
        "pressure_tap_closed_instrument_envelope": True,
        "reference_vent_x_mm": 120,
        "reference_vent_ID_mm": 2,
        "reference_vent_top_z_mm": 20,
        "generator_port_open_interface_x_mm": -25,
        "diaphragm_aperture_mm": 8,
        "effective_area_status": "NOT_MEASURED_APERTURE_NOT_EFFECTIVE_AREA",
        "physical_result": "NOT_RUN",
    }


def main_build() -> None:
    data: dict[str, object] = {
        "status": "DRY_BENCH_PREPARATION_NOT_A_RELEASED_SEAL",
        "frame": export(frame(), "force-displacement-frame"),
    }
    data["pan_accessory"] = export(
        {"pan_coupon_D36x3_SEPARATE_NOT_FORCE_SWEEP": cylinder(18, 0.6, 3)}, "pan-coupon-accessory"
    )
    parts, dims = pressure_cell()
    data["pressure_cell"] = export(parts, "connected-pressure-cell")
    data["pressure_geometry"] = dims
    data["frame_interfaces"] = {
        "glass_top_z_mm": 0,
        "glass_thickness_mm": 4,
        "glass_aperture_mm": 18,
        "housing_OD_mm": 28,
        "clamp_bore_mm": 28.2,
        "clamp_z_mm": [-22, -12],
        "datum_plate_aperture_mm": 30,
        "expected_lowest_wire_endpoint_z_mm": -47,
        "base_top_z_mm": -55,
        "nominal_wire_endpoint_clearance_mm": 8,
        "cartridge_included": False,
        "fasteners_guides_and_clamp_stress": "NOT_ENGINEERED",
    }
    (ROOT / "geometry.json").write_text(json.dumps(data, indent=2) + "\n")
    print(
        json.dumps(
            {"valid_step_files": 4, "pressure_fluid_connected": True, "physical_result": "NOT_RUN"}
        )
    )


if __name__ == "__main__":
    main_build()
