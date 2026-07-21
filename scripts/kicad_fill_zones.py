#!/usr/bin/env python3
"""Fill zones in a KiCad PCB file using KiCad's own pcbnew Python API.

kicad-cli's ``pcb drc --refill-zones`` flag doesn't exist before a
certain KiCad CLI version (confirmed absent in CI's KiCad 8.0.9) --
without it, a zone emitted with only an outline polygon (no computed
``filled_polygon`` geometry) reads as zero copper to DRC's connectivity
check, regardless of any ``(fill yes ...)`` declaration in the file.
``pcbnew.ZONE_FILLER`` is the same underlying fill algorithm, callable
directly and version-independent, so this script pre-fills zones and
saves the board before DRC ever runs.

MUST run under a Python interpreter that has the ``pcbnew`` module --
this is normally NOT the project's ``uv``-managed virtualenv. On
Ubuntu, ``apt-get install kicad`` installs pcbnew bindings for the
system ``python3``; invoke this script with that interpreter, not
``uv run python``.

Usage:
  python3 scripts/kicad_fill_zones.py <input.kicad_pcb> <output.kicad_pcb>

Exit codes:
  0 - zones filled and board saved
  2 - pcbnew not importable (wrong interpreter)
  3 - board failed to load or save
"""

import sys


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"Usage: {argv[0]} <input.kicad_pcb> <output.kicad_pcb>", file=sys.stderr)
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
        board = pcbnew.LoadBoard(input_path)
    except Exception as e:
        print(f"Failed to load board {input_path}: {e}", file=sys.stderr)
        return 3

    zones = board.Zones()
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(zones)

    try:
        pcbnew.SaveBoard(output_path, board)
    except Exception as e:
        print(f"Failed to save filled board to {output_path}: {e}", file=sys.stderr)
        return 3

    print(f"Filled {len(zones)} zones, saved to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
