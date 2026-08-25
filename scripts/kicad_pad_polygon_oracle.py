#!/usr/bin/env python3
"""Compute ground-truth pad **copper-outline corner** positions using
KiCad's own placement engine (``pcbnew``), for the pad-core-polygon
rotation-convention gate ``scripts/check_pad_core_polygon_oracle.py``.

Why this exists (and why the sibling oracle is not enough)
---------------------------------------------------------
``scripts/kicad_pad_rotation_oracle.py`` answers "where does a pad's
*centre* land when its footprint is rotated". That is a point transform.
It says nothing about the second, independent place the same sign
convention appears: the orientation of the pad's own copper **rectangle**
about that centre.

``core/pad_geometry.py::pad_core_polygon`` rotated that rectangle with
``shapely.affinity.rotate(+degrees)`` -- R(+theta) -- while
``scripts/check_board_containment.py::_pad_polygons`` rotated the
identical object with ``kicad_transform.shapely_rotation_angle_deg``
(R(-theta)). Both cannot be right. The disagreement was invisible because
every one of the 527 pads on ``pcb/temper.kicad_pcb`` sits at a multiple
of 90 degrees, where the two conventions produce the *same corner set*
(they differ only in ring order). At any other angle they are mirror
images.

So this oracle asks pcbnew directly: build a rectangular pad of a given
size at a given orientation and read back the corners of the polygon
KiCad itself would fill with copper. No reimplementation of KiCad's
rotation formula is involved anywhere in the answer.

MUST run under a Python interpreter that has the ``pcbnew`` module -- this
is normally NOT the project's ``uv``-managed virtualenv (see
``kicad_pad_rotation_oracle.py``'s docstring for the same constraint and
why no interpreter path is hardcoded here).

Usage:
  python3 scripts/kicad_pad_polygon_oracle.py <input.json> <output.json>

<input.json> is a JSON list of ``[width_mm, height_mm, cx_mm, cy_mm,
angle_deg]`` rows describing a **rectangular** pad: its size in its own
frame, the board-frame position of its centre, and its absolute board
orientation in degrees. Rectangular only, deliberately: for a rect pad
the pad's copper outline IS ``pad_core_polygon``'s core (corner radius
0), so the comparison is exact with no arc approximation on either side.

<output.json> receives a JSON list of ``[[x_mm, y_mm], ...]`` -- the
corners of the pad's copper polygon, in pcbnew's own ring order, exactly
as pcbnew builds them. Each row gets a fresh footprint/pad pair (not a
shared one mutated in place) so results cannot leak state between rows.

Exit codes:
  0 - all rows computed and written
  2 - pcbnew not importable (wrong interpreter)
  3 - input malformed, a row produced an unusable polygon, or output
      failed to write
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"Usage: {argv[0]} <input.json> <output.json>", file=sys.stderr)
        return 1

    input_path, output_path = argv[1], argv[2]

    try:
        import pcbnew
    except ImportError as e:
        print(
            f"pcbnew not importable from this interpreter ({sys.executable}): {e}. "
            "This script must run under a Python interpreter that has KiCad's "
            "pcbnew bindings installed, not the project's uv-managed venv.",
            file=sys.stderr,
        )
        return 2

    try:
        with open(input_path) as f:
            rows = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Failed to read input {input_path}: {e}", file=sys.stderr)
        return 3

    if not isinstance(rows, list) or not rows:
        print(f"Input {input_path} must be a non-empty JSON list", file=sys.stderr)
        return 3

    results: list[list[list[float]]] = []
    board = pcbnew.BOARD()
    for i, row in enumerate(rows):
        try:
            width, height, cx, cy, angle_deg = row
        except (TypeError, ValueError):
            print(f"Row {i} is not [width, height, cx, cy, angle_deg]: {row!r}", file=sys.stderr)
            return 3

        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(f"A{i}")
        board.Add(fp)

        pad = pcbnew.PAD(fp)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(float(width)), pcbnew.FromMM(float(height))))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetFPRelativePosition(pcbnew.VECTOR2I(0, 0))
        fp.Add(pad)

        # The footprint is left unrotated at the pad's own centre and the
        # ORIENTATION is set on the PAD. KiCad stores a placed pad's `at`
        # angle ABSOLUTELY (already composed with its footprint's), which
        # is exactly the number `pad_core_polygon` receives as
        # `rotation_rad` -- see this repo's parser, and the T1/T2 evidence
        # (one shared library footprint, footprint-rotations 90/0, stored
        # pad angles 90/0).
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(float(cx)), pcbnew.FromMM(float(cy))))
        fp.SetOrientationDegrees(0.0)
        pad.SetOrientationDegrees(float(angle_deg))

        shape = pad.GetEffectivePolygon(pcbnew.F_Cu)
        if shape.OutlineCount() != 1:
            print(
                f"Row {i}: pcbnew produced {shape.OutlineCount()} outlines for a "
                "rectangular pad; expected exactly 1",
                file=sys.stderr,
            )
            return 3
        outline = shape.Outline(0)
        if outline.PointCount() != 4:
            print(
                f"Row {i}: pcbnew produced a {outline.PointCount()}-point outline for a "
                "rectangular pad; expected exactly 4",
                file=sys.stderr,
            )
            return 3

        corners = []
        for k in range(outline.PointCount()):
            pt = outline.CPoint(k)
            corners.append([pcbnew.ToMM(pt.x), pcbnew.ToMM(pt.y)])
        results.append(corners)
        board.Remove(fp)

    try:
        with open(output_path, "w") as f:
            json.dump(results, f)
    except OSError as e:
        print(f"Failed to write output {output_path}: {e}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
