"""Sample the discretized nominal 1 A radial coax current-sheet source.

Elmer's boundary load interpolates the vector at triangle vertices.  The
area integral of radial sheet current divided by annulus width equals I for
the analytic K_r = I/(2*pi*r) distribution.  For the interpolated FEM source,
that number is only an area average, not a conserved branch current.  Four
sampled circular cuts expose the interpolation's continuity error.
"""

import argparse
import json
import math
from pathlib import Path

import gmsh


def integrated_current(mesh_path: Path) -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))
        surface_tags = gmsh.model.getEntitiesForPhysicalGroup(2, 3)
        if len(surface_tags) != 1:
            raise ValueError(f"expected one coax port surface, got {surface_tags}")
        tags, coords, _ = gmsh.model.mesh.getNodes()
        points = {int(tag): coords[3 * i : 3 * i + 3] for i, tag in enumerate(tags)}
        radial_integral = 0.0
        area_total = 0.0
        faces = 0
        triangles = []
        for surface in surface_tags:
            element_types, _, connectivity = gmsh.model.mesh.getElements(2, int(surface))
            for element_type, nodes in zip(element_types, connectivity, strict=True):
                if element_type != 2:
                    raise ValueError(f"expected first-order triangles, got type {element_type}")
                for offset in range(0, len(nodes), 3):
                    vertices = [points[int(node)] for node in nodes[offset : offset + 3]]
                    area = abs((vertices[1][0] - vertices[0][0]) * (vertices[2][1] - vertices[0][1])
                               - (vertices[1][1] - vertices[0][1]) * (vertices[2][0] - vertices[0][0])) / 2
                    cx = sum(vertex[0] for vertex in vertices) / 3
                    cy = sum(vertex[1] for vertex in vertices) / 3
                    r = math.hypot(cx, cy)
                    kx = sum(vertex[0] / (2 * math.pi * (vertex[0] ** 2 + vertex[1] ** 2))
                             for vertex in vertices) / 3
                    ky = sum(vertex[1] / (2 * math.pi * (vertex[0] ** 2 + vertex[1] ** 2))
                             for vertex in vertices) / 3
                    radial_integral += area * (kx * cx + ky * cy) / r
                    area_total += area
                    faces += 1
                    triangles.append(vertices)
        cuts = {}
        for radius in (0.6, 1.0, 1.5, 1.9):
            samples = 720
            radial_sum = 0.0
            for i in range(samples):
                angle = 2 * math.pi * i / samples
                px, py = radius * math.cos(angle), radius * math.sin(angle)
                for triangle in triangles:
                    (x0, y0, _), (x1, y1, _), (x2, y2, _) = triangle
                    if px < min(x0, x1, x2) or px > max(x0, x1, x2):
                        continue
                    if py < min(y0, y1, y2) or py > max(y0, y1, y2):
                        continue
                    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                    w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / denom
                    w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / denom
                    w2 = 1 - w0 - w1
                    if min(w0, w1, w2) < -1e-10:
                        continue
                    kx = sum(weight * vertex[0] / (2 * math.pi * (vertex[0] ** 2 + vertex[1] ** 2))
                             for weight, vertex in zip((w0, w1, w2), triangle, strict=True))
                    ky = sum(weight * vertex[1] / (2 * math.pi * (vertex[0] ** 2 + vertex[1] ** 2))
                             for weight, vertex in zip((w0, w1, w2), triangle, strict=True))
                    radial_sum += kx * math.cos(angle) + ky * math.sin(angle)
                    break
                else:
                    raise ValueError(f"circular cut {radius} mm has no triangle at angle {angle}")
            cuts[f"r{radius:g}_mm_A"] = 2 * math.pi * radius * radial_sum / samples
        cut_values = list(cuts.values())
        return {"mesh": str(mesh_path), "triangles": faces, "port_area_mm2": area_total,
                "radial_source_integral_A_mm": radial_integral,
                "area_average_current_A": radial_integral / (2.0 - 0.5),
                "circular_cuts": cuts,
                "sampled_cut_spread_A": max(cut_values) - min(cut_values)}
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    args = parser.parse_args()
    print(json.dumps(integrated_current(args.mesh), indent=2))
