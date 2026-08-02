"""Geometric staircase (1-bend polyline) corridor feasibility.

Cheap test of the re-scope plan (2026-08-01-003) Option 2 hypothesis BEFORE
building any CP-SAT polyline encoder: does a non-straight full-height corridor
materially lower the displacement floor vs the straight corridor (measured
floor: no budget <= 100 mm is feasible anywhere)?

Corridor model: a 1-bend staircase path spanning the board full-height —
vertical at x=c1 from bottom to y=yb, horizontal at y=yb from c1 to c2,
vertical at x=c2 from yb to top — with width W (half-width hw). HV components
must be clean on the left, SELV clean on the right. Displacement is rigid-body
x-translation only (matching the straight-corridor convention), so the numbers
are directly comparable to the straight floor. The staircase helps when the
HV/SELV boundary is itself a staircase: an HV component below the bend only
needs to clear c1, one above only c2.

Usage: uv run --no-sync python docs/evidence/2026-08-01-staircase-corridor-feasibility.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

# Load the committed feasibility module (importable via importlib; name starts
# with a digit so it cannot be `import`ed directly).
_FEAS = Path(__file__).parent / "2026-08-01-isolation-barrier-feasibility.py"
_spec = importlib.util.spec_from_file_location("feas", _FEAS)
feas = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["feas"] = feas
_spec.loader.exec_module(feas)

Pad = feas.Pad
load_manifest = feas.load_manifest
load_pads = feas.load_pads
BOARD_PATH = feas.BOARD_PATH
MANIFEST_PATH = feas.MANIFEST_PATH
BOARD_INSET = feas.BOARD_INSET

W = 8.0
HW = W / 2.0
TARGET_MAX = 25.0


def pad_stair_shift_x(p, c1, yb, c2):
    """x-shift (positive = move right) needed for a pad to clear the staircase
    to a given side. Returns (shift_left, shift_right): the minimal rigid-x
    shift to put the pad cleanly left, and cleanly right."""
    hw = HW
    # Below the bend: clear vertical c1. Above: clear vertical c2.
    if p.y < yb:
        need_left = (c1 + hw + p.radius) - p.x          # px' must be <= c1-hw-r
        need_right = p.x - (c1 - hw - p.radius)          # px' must be >= c1+hw+r
    elif p.y > yb:
        need_left = (c2 + hw + p.radius) - p.x
        need_right = p.x - (c2 - hw - p.radius)
    else:
        # Pad center exactly on the bend line: treat like the stricter below.
        need_left = (c1 + hw + p.radius) - p.x
        need_right = p.x - (c1 - hw - p.radius)
    return max(0.0, need_left), max(0.0, need_right)


def staircase_drift(pads, hv_nets, selv_nets, c1, yb, c2, board_rect, exclude_refs=None):
    """Rigid-x displacement per component to put HV left / SELV right of the
    staircase corridor. Returns (drift_by_ref, total, movers, max_drift)."""
    x0, y0, x1, y1 = board_rect
    by_ref: dict[str, list[Pad]] = {}
    for p in pads:
        by_ref.setdefault(p.ref, []).append(p)

    drift_by_ref: dict[str, float] = {}
    for ref, comp_pads in by_ref.items():
        if exclude_refs and ref in exclude_refs:
            continue
        comp_pads = [p for p in comp_pads if x0 <= p.x <= x1 and y0 <= p.y <= y1]
        if not comp_pads:
            continue
        hv = [p for p in comp_pads if p.net in hv_nets]
        sv = [p for p in comp_pads if p.net in selv_nets]
        if hv and not sv:
            # HV: all pads must be clean LEFT (shift left by max need_left).
            need = max(pad_stair_shift_x(p, c1, yb, c2)[0] for p in comp_pads)
        elif sv and not hv:
            need = max(pad_stair_shift_x(p, c1, yb, c2)[1] for p in comp_pads)
        elif hv and sv:
            # Mixed (isolator-like): clear the corridor to the nearer side.
            lo = max(pad_stair_shift_x(p, c1, yb, c2)[0] for p in comp_pads)
            hi = max(pad_stair_shift_x(p, c1, yb, c2)[1] for p in comp_pads)
            need = min(lo, hi)
        else:
            # Unclassified: clear the corridor to the nearer side.
            lo = max(pad_stair_shift_x(p, c1, yb, c2)[0] for p in comp_pads)
            hi = max(pad_stair_shift_x(p, c1, yb, c2)[1] for p in comp_pads)
            need = min(lo, hi)
        if need > 0.01:
            drift_by_ref[ref] = need

    total = sum(drift_by_ref.values())
    return drift_by_ref, total, len(drift_by_ref), max(drift_by_ref.values(), default=0.0)


def main():
    hv_nets, selv_nets = load_manifest(MANIFEST_PATH)
    pads, board_rect = load_pads(BOARD_PATH)
    x0, y0, x1, y1 = board_rect
    print(f"board {x1-x0:.0f}x{y1-y0:.0f}mm; {len(pads)} pads; W={W}mm; target max<={TARGET_MAX}mm")

    t0 = time.monotonic()
    best_max = None
    best_total = None
    for c1 in [v for v in range(int(x0 + 6), int(x1 - 6), 6)]:
        for c2 in [v for v in range(c1 + int(W) + 6, int(x1 - 6), 6)]:
            for yb in [v for v in range(int(y0 + 10), int(y1 - 10), 12)]:
                _d, total, movers, mx = staircase_drift(
                    pads, hv_nets, selv_nets, float(c1), float(yb), float(c2), board_rect
                )
                if best_max is None or mx < best_max[0]:
                    best_max = (mx, c1, yb, c2, total, movers)
                if best_total is None or total < best_total[0]:
                    best_total = (total, c1, yb, c2, mx, movers)

    print(f"sweep took {time.monotonic()-t0:.1f}s")
    print("\n=== best staircase corridors ===")
    print(f"min-MAX  : max={best_max[0]:.1f}mm  c1={best_max[1]} yb={best_max[2]} c2={best_max[3]}  total={best_max[4]:.0f}mm movers={best_max[5]}")
    print(f"min-TOTAL: total={best_total[0]:.0f}mm  c1={best_total[1]} yb={best_total[2]} c2={best_total[3]}  max={best_total[4]:.1f}mm movers={best_total[5]}")
    print(f"\nwithin {TARGET_MAX}mm budget? "
          f"{'YES' if best_max and best_max[0] <= TARGET_MAX else 'NO — min-max floor is %.1fmm (straight corridor floor: no budget <=100mm)' % (best_max[0] if best_max else float('nan'))}")


if __name__ == "__main__":
    main()
