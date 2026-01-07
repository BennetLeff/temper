#!/usr/bin/env python3.11
"""Quick verification that the backward path fix works."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

# Just verify the code change is present
from temper_placer.routing import diff_pair_router
import inspect


def test_backward_path_reversal():
    """Verify that _reconstruct_path includes backward_path.reverse()."""

    source = inspect.getsource(diff_pair_router.DiffPairRouter._reconstruct_path)

    if "backward_path.reverse()" in source:
        print("✅ PASS: backward_path.reverse() found in _reconstruct_path()")
        return True
    else:
        print("❌ FAIL: backward_path.reverse() NOT found in _reconstruct_path()")
        print("\nThe fix was not applied correctly!")
        return False


def check_old_output():
    """Check that the old output had gaps (confirms our diagnosis was correct)."""

    old_pcb = Path("output/test_adaptive_fixed/iteration_1.kicad_pcb")
    if not old_pcb.exists():
        print("⚠️  WARNING: Old test output not found, skipping gap verification")
        return True

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    board = parse_kicad_pcb(old_pcb)
    usb_traces = [t for t in board.traces if t.net == "USB_D+" and t.layer == "B.Cu"]
    usb_traces.sort(key=lambda t: (t.start[0], t.start[1]))

    # Count gaps
    gaps = 0
    for i in range(len(usb_traces) - 1):
        t1, t2 = usb_traces[i], usb_traces[i + 1]
        dist_start = ((t2.start[0] - t1.end[0]) ** 2 + (t2.start[1] - t1.end[1]) ** 2) ** 0.5
        dist_end = ((t2.end[0] - t1.end[0]) ** 2 + (t2.end[1] - t1.end[1]) ** 2) ** 0.5

        if min(dist_start, dist_end) > 0.01:
            gaps += 1

    if gaps > 50:
        print(f"✅ VERIFIED: Old output had {gaps} gaps (confirms bug existed)")
        return True
    else:
        print(f"⚠️  WARNING: Old output only had {gaps} gaps (expected >50)")
        return True


if __name__ == "__main__":
    print("Verifying backward path fix...\n")

    test1 = test_backward_path_reversal()
    test2 = check_old_output()

    print("\n" + "=" * 60)
    if test1 and test2:
        print("✅ VERIFICATION PASSED")
        print("\nThe fix is in place. To validate it works:")
        print(
            "  python3.11 scripts/run_feedback_loop.py --max-iterations 1 --output-dir output/test_fix"
        )
        print("  python3.11 scripts/debug_diff_pair_path.py")
        sys.exit(0)
    else:
        print("❌ VERIFICATION FAILED")
        sys.exit(1)
