"""Independently re-read exported STEP contact faces against thermal scalar inputs."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parent


def main() -> None:
    mechanical = ROOT / "mechanical"
    rows = list(csv.DictReader((mechanical / "thermal_geometry.csv").open(newline="")))
    checked = []
    for row in rows:
        variant = row["variant"]
        path = mechanical / f"R5-{variant}-cap.step"
        shape = cq.importers.importStep(str(path)).val()
        if not shape.isValid():
            raise ValueError(f"{variant}: invalid cap STEP")
        z_top = shape.BoundingBox().zmax
        top_area = sum(
            face.Area()
            for face in shape.Faces()
            if abs(face.Center().z - z_top) < 1e-7 and abs(face.normalAt().z - 1) < 1e-7
        )
        target_area = math.pi * float(row["head_radius_mm"]) ** 2
        if not math.isclose(top_area, target_area, rel_tol=1e-8):
            raise ValueError(f"{variant}: STEP top face {top_area} != modeled face {target_area}")
        volume = shape.Volume()
        if not math.isclose(volume, float(row["cap_volume_mm3"]), rel_tol=1e-8):
            raise ValueError(f"{variant}: cap volume differs from thermal input")
        checked.append(
            {
                "variant": variant,
                "step_contact_face_area_mm2": top_area,
                "modeled_contact_face_area_mm2": target_area,
                "step_cap_volume_mm3": volume,
                "modeled_cap_volume_mm3": float(row["cap_volume_mm3"]),
                "status": "EXPORTED_STEP_SCALAR_PARITY",
            }
        )
    (ROOT / "cad-parity.json").write_text(
        json.dumps(
            {
                "checks": checked,
                "scope": "Independent STEP reimport and face/volume extraction; does not verify physical properties or contact behavior.",
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(checked, indent=2))


if __name__ == "__main__":
    main()
