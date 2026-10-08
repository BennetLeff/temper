"""Crop KiCad STEP copper with a gmsh/OpenCASCADE box; no meshing or solve."""

import argparse
import json
import time
from pathlib import Path

import gmsh

BBOX = {
    "A": (125.865, 164.6, -41.125, -4.215),
    "B": (88.4, 127.135, -41.125, -4.215),
}


def crop(step: Path, leg: str, margin: float, output: Path) -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Geometry.OCCFixDegenerated", 1)
        gmsh.option.setNumber("Geometry.OCCFixSmallEdges", 1)
        gmsh.option.setNumber("Geometry.OCCFixSmallFaces", 1)
        gmsh.option.setNumber("Geometry.OCCSewFaces", 0)
        gmsh.model.add(f"leg_{leg}_M{margin}")
        start = time.monotonic()
        copper = gmsh.model.occ.importShapes(str(step))
        if len(copper) != 84 or any(dim != 3 for dim, _ in copper):
            raise ValueError(f"unexpected native-17 solid count: {len(copper)}")
        xlo, xhi, ylo, yhi = BBOX[leg]
        box = gmsh.model.occ.addBox(xlo - margin, ylo - margin, -1.0,
                                    xhi - xlo + 2 * margin,
                                    yhi - ylo + 2 * margin, 3.0)
        cut, _ = gmsh.model.occ.intersect(copper, [(3, box)],
                                          removeObject=True, removeTool=True)
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if not volumes or any(dim != 3 for dim, _ in cut):
            raise ValueError(f"crop returned no solid copper: {cut}")
        output.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(output))
        return {"input": str(step), "leg": leg, "margin_mm": margin,
                "bbox_step_mm": [xlo-margin, ylo-margin, -1, xhi+margin, yhi+margin, 2],
                "solid_count": len(volumes), "surface_count": len(gmsh.model.getEntities(2)),
                "seconds": round(time.monotonic()-start, 3), "output": str(output)}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", type=Path)
    parser.add_argument("leg", choices=sorted(BBOX))
    parser.add_argument("margin", type=float)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(crop(args.step, args.leg, args.margin, args.output), indent=2))
