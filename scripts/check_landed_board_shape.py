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
     must land within ``--tolerance-pct`` of the verified recipe baseline in
     ``scripts/board_shape_baseline.json``, so a board that is *nonzero* but
     bears no relation to what the documented recipe produces also stops here.

BASELINE PROVENANCE -- this constant moved out of this file on purpose.
------------------------------------------------------------------------
The board-shape baseline used to be a hardcoded dict here (``VERIFIED_BASELINE
= {"segments": 3349, "vias": 56, "zones": 70}``). That number was wrong -- it
was measured against an unpinned, untracked ``pumpkin_engine`` build, not
reproducible from any binary anyone could later identify -- and it kept
company with FOUR other wrong numbers before it (4,228/74/66; 3,314/40/58;
4,140/70/66; 3,505/26/76 -- the last two additionally written 20mm off the
board outline by a write-path bug). Every one of those looked like "the
baseline" when it was written down. A constant living in a script is exactly
how that kind of drift goes unnoticed: nothing forces whoever regenerates the
board to also touch this file, and a stale number silently keeps passing (or
silently starts rejecting everything) with no diff to review.

The baseline now lives in ``scripts/board_shape_baseline.json``, alongside a
``_march`` log of every value it has held and why each one was replaced --
the same pattern ``power_pcb_dataset/drc_ceiling.json`` already uses for the
DRC error ceiling. Updating the baseline is a data change with a paper trail,
not a code change that has to be spotted in a diff. This does not, by itself,
stop the baseline from going stale the moment the recipe or its engine
changes again -- only re-running the recipe and updating the JSON does that
-- but it does mean the next correction leaves a record instead of silently
overwriting the last one.

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
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "board_shape_baseline.json"


def _load_verified_baseline() -> dict[str, int]:
    """Load the current board-shape baseline from its JSON sidecar.

    See ``scripts/board_shape_baseline.json``'s own ``_march`` log for the
    five prior values this one replaced and why each was wrong.
    """
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return data["baseline"]


VERIFIED_BASELINE = _load_verified_baseline()
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
    baseline_str = (
        f"{VERIFIED_BASELINE['segments']} / {VERIFIED_BASELINE['vias']} / "
        f"{VERIFIED_BASELINE['zones']}"
    )
    print(f"\nGATE 2 -- agreement with the verified recipe baseline ({baseline_str}, "
          f"see scripts/board_shape_baseline.json)")
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
