"""Audit the spatially constant 1 A Elmer plate-port source on a Gmsh mesh."""

import argparse
import json
import re
from pathlib import Path

import gmsh


def check(mesh: Path, sif: Path, z_min: float = 0, z_max: float = .5) -> dict:
    text = sif.read_text()
    matches = re.findall(r"Magnetic Field Strength 3 = Real ([0-9.]+)", text)
    if len(matches) != 1:
        raise ValueError("expected one constant z-directed port load")
    density_a_per_m = float(matches[0])
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh))
        port = gmsh.model.getEntitiesForPhysicalGroup(2, 3)
        if len(port) != 1:
            raise ValueError(f"expected one port sheet, found {port}")
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, int(port[0]))
        if (abs(ymax - ymin) > 1e-8 or abs(zmin - z_min) > 1e-8 or
                abs(zmax - z_max) > 1e-8):
            raise ValueError("port sheet is not the intended x-z rectangle")
        width_m = (xmax - xmin) / 1000
        cut_z_mm = tuple(z_min + fraction * (z_max-z_min)
                         for fraction in (.2, .5, .8))
        if any(not zmin < z < zmax for z in cut_z_mm):
            raise ValueError("sampled cut lies outside port sheet")
        cuts = {f"z{z:g}_mm_A": density_a_per_m * width_m for z in cut_z_mm}
        return {
            "mesh": str(mesh),
            "sif": str(sif),
            "port_surface_tag": int(port[0]),
            "port_bbox_mm": [xmin, ymin, zmin, xmax, ymax, zmax],
            "constant_source_density_A_per_m": density_a_per_m,
            "sampled_cut_currents_A": cuts,
            "sampled_cut_spread_A": max(cuts.values()) - min(cuts.values()),
            "scope": "source-sheet current from pinned Elmer boundary load; not an H-field contour integral",
        }
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("sif", type=Path)
    parser.add_argument("--z-min", type=float, default=0)
    parser.add_argument("--z-max", type=float, default=.5)
    args = parser.parse_args()
    print(json.dumps(check(args.mesh, args.sif, args.z_min, args.z_max), indent=2))
