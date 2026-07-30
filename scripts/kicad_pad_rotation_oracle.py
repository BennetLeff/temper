#!/usr/bin/env python3
"""Compute ground-truth pad world positions using KiCad's own placement
engine (``pcbnew``), for the rotation-convention differential tests in
``packages/temper-placer/tests/requirements/safety/
test_rotation_convention_oracle.py``.

Why this exists
----------------
KiCad rotates a footprint's pad local offsets **clockwise**, ``R(-theta)``.
This repo used the standard-math CCW ``R(+theta)`` in 12 places (see
``docs/evidence/2026-07-29-rotation-convention-sign-fix-cpsat-rerun.md``),
including ``requirements/validators/_copper.py::_rotate`` -- the function
REQ-SAFE-01 (the mains-safety clearance/creepage check) uses to compute
copper positions. The wrong sign concealed real clearance hazards.

A test that only checks this repo's own code against itself cannot catch a
*consistent but wrong* convention -- parser and validator agreed with each
other and both disagreed with KiCad. This script is the actual oracle:
it asks ``pcbnew`` (KiCad's own footprint-placement engine, not a
reimplementation of KiCad's rotation formula) where a pad really ends up.

MUST run under a Python interpreter that has the ``pcbnew`` module -- this
is normally NOT the project's ``uv``-managed virtualenv. On Ubuntu,
``apt-get install kicad`` installs pcbnew bindings for the system
``python3``; on macOS they live inside KiCad.app's bundled Python. See
``_resolve_pcbnew_python`` in
``packages/temper-placer/tests/placer/cp_sat/
test_zone_pour_production_measurement.py`` for interpreter resolution --
a hardcoded ``/usr/bin/python3`` that *exists but lacks pcbnew* is exactly
how a whole test family silently skipped for a week on this project, so
this script itself does not hardcode a path; it is invoked with whatever
interpreter the caller resolved.

Usage:
  python3 scripts/kicad_pad_rotation_oracle.py <input.json> <output.json>

<input.json> is a JSON list of ``[dx_mm, dy_mm, angle_deg]`` triples: a
pad's local offset from its footprint's origin, and the footprint's
absolute board rotation in degrees. <output.json> receives a JSON list of
``[x_mm, y_mm]`` -- the pad's real board-frame position, exactly as
``pcbnew`` places it. Each triple gets a fresh footprint/pad pair (not a
shared one mutated in place) so results cannot leak state between rows.

Exit codes:
  0 - all rows computed and written
  2 - pcbnew not importable (wrong interpreter)
  3 - input malformed or output failed to write
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

    results: list[list[float]] = []
    board = pcbnew.BOARD()
    for i, (dx, dy, angle_deg) in enumerate(rows):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(f"A{i}")
        board.Add(fp)

        pad = pcbnew.PAD(fp)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        # Local offset from the footprint's own origin -- set BEFORE the
        # footprint's position/orientation, per pcbnew's own semantics
        # (SetFPRelativePosition stores the pad's position relative to
        # whatever the footprint's transform is at the time of the *later*
        # SetPosition/SetOrientationDegrees calls; there is no separate
        # SetPos0 on this pcbnew.PAD binding).
        pad.SetFPRelativePosition(pcbnew.VECTOR2I(pcbnew.FromMM(dx), pcbnew.FromMM(dy)))
        fp.Add(pad)

        # Footprint position/orientation set AFTER the pad is added, so
        # pcbnew's own placement transform is what moves the pad -- not an
        # accumulated offset we computed ourselves.
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        fp.SetOrientationDegrees(float(angle_deg))

        pos = pad.GetPosition()
        results.append([pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)])
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
