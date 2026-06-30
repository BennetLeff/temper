#!/usr/bin/env python3
"""Semantic check: verify the committed .kicad_pcb has exactly 4 copper layers
with canonical KiCad names (F.Cu / In1.Cu / In2.Cu / B.Cu).

Unlike a textual ``git diff`` this tolerates benign KiCad format changes
(e.g. version upgrades that add/remove non-copper layers or reformat
whitespace) while rejecting any change to the copper layer set.

Exit 0 if valid, 1 with diagnostic otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

CANONICAL_COPPER_LAYERS: frozenset[str] = frozenset(
    {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"}
)


def check_pcb(pcb_path: Path) -> int:
    """Verify *pcb_path* has exactly the canonical 4 copper layers."""
    if not pcb_path.is_file():
        print(f"[FAIL] {pcb_path} does not exist or is not a file", file=sys.stderr)
        return 1

    from kiutils.board import Board as KiBoard

    try:
        board = KiBoard.from_file(str(pcb_path))
    except Exception as exc:
        print(f"[FAIL] Could not parse {pcb_path}: {exc}", file=sys.stderr)
        return 1

    copper_names = [
        ly.name for ly in board.layers
        if hasattr(ly, "name") and ly.name.endswith(".Cu")
    ]
    name_set = set(copper_names)

    if len(copper_names) != 4:
        print(
            f"[FAIL] Expected 4 copper layers (canonical: {sorted(CANONICAL_COPPER_LAYERS)}), "
            f"got {len(copper_names)}: {sorted(name_set)}",
            file=sys.stderr,
        )
        return 1

    if name_set != CANONICAL_COPPER_LAYERS:
        print(
            f"[FAIL] Copper layer names must match {sorted(CANONICAL_COPPER_LAYERS)}, "
            f"got {sorted(name_set)}",
            file=sys.stderr,
        )
        return 1

    print(
        f"[PASS] {pcb_path.name}: 4 canonical copper layers — "
        f"{sorted(copper_names)}"
    )
    return 0


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    pcb = repo_root / "pcb" / "temper.kicad_pcb"
    return check_pcb(pcb)


if __name__ == "__main__":
    sys.exit(main())
