"""Rebuild six provisional mechanical VRML visualizations.

These solids encode published maximum envelopes and footprint pad locations.
They are deliberately not substitutes for vendor CAD or measured hardware.
Coordinates are in millimetres: model X = footprint X, model Y = -footprint Y. KiCad applies a scale of 1/2.54 to VRML.
"""

from __future__ import annotations

from math import cos, pi, sin
from pathlib import Path


OUT = Path(__file__).resolve().parent
BLACK = (0.09, 0.10, 0.12)
DARK = (0.17, 0.19, 0.20)
GREEN = (0.10, 0.42, 0.18)
COPPER = (0.64, 0.34, 0.09)
SILVER = (0.68, 0.69, 0.70)
BLUE = (0.10, 0.25, 0.50)


def header(name: str, note: str) -> list[str]:
    return [
        "#VRML V2.0 utf8",
        f"# Provisional {name} visualization. {note}",
        "# Coordinates in mm; set KiCad model scale to 0.3937008 on all axes.",
        f'WorldInfo {{ title "{name} (provisional)" }}',
    ]


def box(x: float, y: float, z: float, sx: float, sy: float, sz: float, color: tuple[float, float, float]) -> str:
    r, g, b = color
    return (f"Transform {{ translation {x:g} {y:g} {z:g} children [ "
            f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {r:g} {g:g} {b:g} }} }} "
            f"geometry Box {{ size {sx:g} {sy:g} {sz:g} }} }} ] }}")


def cylinder(x: float, y: float, z: float, radius: float, height: float,
             color: tuple[float, float, float], rotation: str = "") -> str:
    r, g, b = color
    return (f"Transform {{ translation {x:g} {y:g} {z:g} {rotation} children [ "
            f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {r:g} {g:g} {b:g} }} }} "
            f"geometry Cylinder {{ radius {radius:g} height {height:g} }} }} ] }}")


def torus(cx: float, cy: float, cz: float, major: float, minor: float,
          color: tuple[float, float, float], start: float = 0.0,
          end: float = 2 * pi, rings: int = 36, sides: int = 12) -> str:
    """Create a torus standing in the X/Z plane, with its axis along Y."""
    vertices: list[str] = []
    faces: list[str] = []
    for i in range(rings + 1):
        a = start + (end - start) * i / rings
        for j in range(sides):
            b = 2 * pi * j / sides
            rr = major + minor * cos(b)
            vertices.append(f"{cx + rr * cos(a):.4f} {cy + minor * sin(b):.4f} {cz + rr * sin(a):.4f}")
    for i in range(rings):
        for j in range(sides):
            q = i * sides + j
            q2 = (i + 1) * sides + j
            faces.append(f"{q}, {q2}, {(i + 1) * sides + (j + 1) % sides}, {i * sides + (j + 1) % sides}, -1")
    r, g, b = color
    return ("Shape { appearance Appearance { material Material { "
            f"diffuseColor {r:g} {g:g} {b:g} }} }} "
            "geometry IndexedFaceSet { solid FALSE coord Coordinate { point [ "
            + ", ".join(vertices) + " ] } coordIndex [ " + ", ".join(faces) + " ] } }")


def save(name: str, parts: list[str]) -> None:
    (OUT / name).write_text("\n".join(parts) + "\n")


# GBJ body is represented at the published 30.3 x 20.3 x 4.8 mm maximum.
# The PCB footprint already fixes the four lead centres at x=0/10/17.5/25.
parts = header("Diodes GBJ2510-F", "Simplified GBJ envelope, no heat-sink screw recess.")
parts += [box(12.5, 0, 11.55, 30.3, 4.8, 17.5, BLACK),
          box(12.5, 0, 20.0, 29.0, 4.3, 0.6, DARK)]
parts += [box(x, 0, 1.4, 1.0, 0.75, 2.8, SILVER) for x in (0, 10, 17.5, 25)]
save("GBJ2510-F_provisional.wrl", parts)

# Body length and diameter come from Microchip DS00005551B Fig. 5-1.
# The P20 formed lead span is a local footprint choice, not a vendor drawing.
parts = header("Microchip MRT130KP295CV", "Axial body/formed leads are schematic approximations.")
parts += [cylinder(10, 0, 4.1, 3.937, 12.954, BLACK, "rotation 0 0 1 -1.5707963")]
parts += [box(x, 0, 4.1, 3.55, 0.8, 0.8, SILVER) for x in (1.75, 18.25)]
parts += [cylinder(x, 0, 2.05, 0.4, 4.1, SILVER, "rotation 1 0 0 1.5707963") for x in (0, 20)]
parts += [box(4.35, 0, 4.1, 0.8, 7.9, 7.9, SILVER)]
save("MRT130KP295CV_provisional.wrl", parts)

# Phoenix gives 5.08 x 27 x 25 mm installed body and two solder pins 15.24 mm apart.
parts = header("Phoenix KDS 3 1704004", "Terminal cavity and screw are visually approximate.")
parts += [box(0, -9.4, 12.5, 5.08, 27, 25, GREEN),
          box(0, 3.0, 12.7, 3.6, 1.0, 5.0, DARK),
          cylinder(0, -9.4, 25.25, 1.35, 0.5, SILVER, "rotation 1 0 0 1.5707963")]
parts += [box(0, y, -1.75, 1.1, 0.8, 3.5, SILVER) for y in (0, -15.24)]
save("KDS3_1704004_provisional.wrl", parts)

# Littelfuse gives a 23 mm max disc, 9 mm max thickness and 28 mm seated height.
# Its leads need forming to the 7.5 mm footprint pitch.
parts = header("Littelfuse TMOV20RP175E", "Formed-lead orientation and exact case shape unverified.")
parts += [cylinder(3.75, 0, 16.5, 11.5, 9.0, BLUE),
          box(3.75, 0, 26.5, 7.0, 9.2, 1.0, DARK)]
parts += [cylinder(x, 0, 2.5, 0.6, 5.0, SILVER, "rotation 1 0 0 1.5707963") for x in (0, 7.5)]
save("TMOV20RP175E_provisional.wrl", parts)

# Published TDK maximum dimensions: 45 x 25.5 x 41 mm. The open ring is a
# visual approximation; its exact winding geometry and pin-seat offsets need
# the manufacturer CAD or a sample.
parts = header("TDK B82726S2203A020", "Maximum envelope; open-ring winding depiction approximate.")
parts += [box(5, -12.5, 1.5, 45, 25.5, 3, DARK),
          torus(5, -12.5, 20.5, 12.5, 6.5, BLACK)]
parts += [torus(5, -12.5, 20.5, 12.5, 7.0, COPPER, 0.25, 2.9, 19),
          torus(5, -12.5, 20.5, 12.5, 7.0, COPPER, 3.4, 6.05, 19)]
parts += [cylinder(x, y, -1.75, 1.0, 3.5, SILVER, "rotation 1 0 0 1.5707963")
          for x, y in ((0, 0), (10, 0), (10, -25), (0, -25))]
save("B82726S2203A020_provisional.wrl", parts)

# Coilcraft drawing and authored footprint define 23 x 30 x 15.2 mm envelope
# with primary/secondary rows at y=-11.55 and +13.75 mm respectively.
parts = header("Coilcraft CST3015-100ED", "Bobbin and core geometry approximate within maximum envelope.")
parts += [box(0, 0, 1.25, 23, 30, 2.5, BLACK),
          box(0, 1.5, 8.85, 22.0, 22.0, 12.7, DARK),
          box(0, 1.5, 15.0, 21.0, 20.0, 0.4, BLACK)]
parts += [box(x, 11.55, 0.45, 4.8, 9.0, 0.9, COPPER) for x in (-5.58, 5.58)]
parts += [box(x, -13.75, 0.45, 3.0, 4.6, 0.9, SILVER) for x in (-6.88, 6.88)]
save("CST3015-100ED_provisional.wrl", parts)
