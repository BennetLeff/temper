#!/usr/bin/env python3
"""Hard gate on a placed-and-routed board before it may be landed as
``pcb/temper.kicad_pcb``.

Why this exists
---------------
PR #1049 was closed for landing a board with **0 track segments and 0 copper
zones** behind correct-looking paperwork and a ``Ceiling-Approval:`` trailer.
Every human-readable artifact in that PR looked right; the board itself had no
copper. Nothing in the repo mechanically asserted otherwise, so nothing caught
it -- the review had to.

This script is that missing assertion. It is deliberately blunt and runs on the
board file itself, not on a report *about* the board:

  1. **Anti-#1049 invariant** (absolute, no tolerance):
         segments > 0  AND  zones > 0  AND  footprints == 168
     A board that fails this is not a routed board, whatever else is true of it.

  2. **Baseline-agreement check** (tolerance-bounded): segments / vias / zones
     must land within ``--tolerance-pct`` of the verified recipe baseline
     (3,349 / 56 / 70), so a board that is *nonzero* but bears no relation to
     what the documented recipe produces also stops here.

The verified baseline comes from
``docs/evidence/2026-08-12-board-recipe-reproducibility.md`` sec 6, which
established it five independent ways on a fixed commit and fixed inputs.
**PR #1050's 4,228 segments / 74 vias does not reproduce and is not the
baseline** -- see sec 5-6 of that document.

Counting is by the SAME cheap-regex method
``tests/placer/cp_sat/test_regression_drc.py::_board_shape`` uses, so this
gate and that module's own ``_assert_baseline_board_shape`` can never disagree
about what "shape" means.

Usage:
    python3 scripts/check_landed_board_shape.py [--board PATH]
                                                [--tolerance-pct FLOAT]
Exit status: 0 = may land, 1 = MUST NOT land.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# docs/evidence/2026-08-12-board-recipe-reproducibility.md sec 6.
VERIFIED_BASELINE = {"footprints": 168, "segments": 3349, "vias": 56, "zones": 70}
REQUIRED_FOOTPRINTS = 168
DEFAULT_TOLERANCE_PCT = 5.0


def board_shape(pcb_path: Path) -> dict[str, int]:
    """Count the board elements the DRC baselines are sensitive to.

    Byte-for-byte the same regex counting as
    ``test_regression_drc.py::_board_shape`` -- intentionally not a full
    s-expression parse.
    """
    text = pcb_path.read_text(encoding="utf-8")
    return {
        f"{token}s": len(re.findall(r"\(\s*" + token + r"\b", text))
        for token in ("footprint", "segment", "via", "zone")
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", type=Path, default=REPO_ROOT / "pcb" / "temper.kicad_pcb")
    ap.add_argument("--tolerance-pct", type=float, default=DEFAULT_TOLERANCE_PCT)
    args = ap.parse_args()

    if not args.board.exists():
        print(f"FAIL: board not found: {args.board}")
        return 1

    shape = board_shape(args.board)
    failures: list[str] = []

    print(f"board: {args.board}")
    print(f"tolerance: +/-{args.tolerance_pct:.1f}% of the verified recipe baseline\n")

    # ---- Gate 1: the anti-#1049 invariant, no tolerance -------------------
    print("GATE 1 -- anti-#1049 copper invariant (absolute)")
    checks = [
        ("segments > 0", shape["segments"] > 0, f"segments={shape['segments']}"),
        ("zones > 0", shape["zones"] > 0, f"zones={shape['zones']}"),
        (f"footprints == {REQUIRED_FOOTPRINTS}", shape["footprints"] == REQUIRED_FOOTPRINTS,
         f"footprints={shape['footprints']}"),
    ]
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<24} {detail}")
        if not ok:
            failures.append(f"{name} ({detail})")

    # ---- Gate 2: agreement with the verified baseline ---------------------
    print("\nGATE 2 -- agreement with the verified recipe baseline (3,349 / 56 / 70)")
    print(f"  {'metric':<12}{'measured':>10}{'baseline':>10}{'delta':>9}{'delta%':>9}   verdict")
    for key in ("segments", "vias", "zones"):
        got, want = shape[key], VERIFIED_BASELINE[key]
        delta = got - want
        pct = (delta / want) * 100.0 if want else 0.0
        ok = abs(pct) <= args.tolerance_pct
        print(f"  {key:<12}{got:>10}{want:>10}{delta:>+9}{pct:>+8.2f}%   {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"{key} {got} is {pct:+.2f}% from baseline {want} (tolerance +/-{args.tolerance_pct:.1f}%)")

    got, want = shape["footprints"], VERIFIED_BASELINE["footprints"]
    print(f"  {'footprints':<12}{got:>10}{want:>10}{got - want:>+9}{'':>9}   {'PASS' if got == want else 'FAIL'}")

    print()
    if failures:
        print("RESULT: DO NOT LAND -- " + str(len(failures)) + " check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: OK TO LAND -- all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
