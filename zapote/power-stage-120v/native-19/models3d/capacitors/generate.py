"""Generate simple, dimensioned KiCad VRML envelopes for the power capacitors.

These are visual assembly envelopes, not manufacturer CAD or manufacturing
inspection data. KiCad interprets one VRML coordinate unit as 2.54 mm.
"""

from __future__ import annotations

from math import pi
from pathlib import Path

HERE = Path(__file__).resolve().parent
MM_PER_VRML_UNIT = 2.54


def v(mm: float) -> str:
    return f"{mm / MM_PER_VRML_UNIT:.8f}"


def point(x: float, y: float, z: float) -> str:
    return f"{v(x)} {v(y)} {v(z)}"


def shape_box(cx: float, cy: float, cz: float, sx: float, sy: float, sz: float, color: str) -> str:
    return (f"Transform {{ translation {point(cx, cy, cz)} children [\n"
            f"  Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }}\n"
            f"          geometry Box {{ size {point(sx, sy, sz)} }} }}\n"
            f"] }}\n")


def shape_cylinder(cx: float, cy: float, cz: float, radius: float, height: float,
                   axis: str, color: str) -> str:
    rotation = {"x": f"rotation 0 0 1 {pi/2:.8f}",
                "y": "", "z": f"rotation 1 0 0 {pi/2:.8f}"}[axis]
    return (f"Transform {{ translation {point(cx, cy, cz)} {rotation} children [\n"
            f"  Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }}\n"
            f"          geometry Cylinder {{ radius {v(radius)} height {v(height)} }} }}\n"
            f"] }}\n")


def write(name: str, parts: list[str]) -> None:
    (HERE / name).write_text("#VRML V2.0 utf8\n# Dimensioned assembly envelope; see README.md.\n" + "".join(parts))


def cde(diameter: float, lead_d: float, name: str) -> None:
    # Footprint pads at x=0 and 42.5; axial body from x=4.25 to 38.25.
    body_z = diameter / 2 + 0.6
    parts = [shape_cylinder(21.25, 0, body_z, diameter / 2, 34, "x", "0.14 0.30 0.55")]
    for x, run_center in ((0, 2.125), (42.5, 40.375)):
        parts.append(shape_cylinder(x, 0, body_z / 2, lead_d / 2, body_z, "z", "0.70 0.70 0.72"))
        parts.append(shape_cylinder(run_center, 0, body_z, lead_d / 2, 4.25, "x", "0.70 0.70 0.72"))
    write(name, parts)


def film_box(length: float, width: float, height: float, cx: float, cy: float,
             leads: list[tuple[float, float]], lead_d: float, name: str) -> None:
    # The body lower face is 0.5 mm above board; top is the datasheet height.
    parts = [shape_box(cx, cy, (height + 0.5) / 2, length, width, height - 0.5,
                       "0.17 0.25 0.43")]
    for x, y in leads:
        parts.append(shape_cylinder(x, y, 0.35, lead_d / 2, 0.7, "z", "0.72 0.72 0.73"))
    write(name, parts)


def murata() -> None:
    # Disc diameter and thickness are specified; stand-off/bend are illustrative.
    parts = [shape_cylinder(5, 0, 9.5, 4.5, 4, "y", "0.37 0.54 0.75")]
    for x in (0, 10):
        parts.append(shape_cylinder(x, 0, 3.5, 0.3, 7, "z", "0.70 0.70 0.72"))
    write("Murata_DE1E3RA222MA4BP01F.wrl", parts)


def main() -> None:
    cde(26.5, 1.2, "CDE_942C12P22K-F.wrl")
    cde(19.0, 1.0, "CDE_942C12P1K-F.wrl")
    film_box(18, 9, 17.5, 7.5, 0, [(0, 0), (15, 0)], 0.8,
             "TDK_B32652A0104K000.wrl")
    # KiCad model Y grows opposite footprint Y. Four pad rows are y=0 and 20.3.
    film_box(42, 33, 48, 18.75, -10.15,
             [(0, 0), (0, -20.3), (37.5, 0), (37.5, -20.3)], 1.2,
             "TDK_B32656G0275J000.wrl")
    # KEMET R463N410000N1M (C1, C2): page-3 maximum body, centred on the pitch.
    film_box(26.8, 11.2, 20.1, 11.25, 0, [(0, 0), (22.5, 0)], 0.8,
             "KEMET_R463N410000N1M.wrl")
    murata()


if __name__ == "__main__":
    main()
