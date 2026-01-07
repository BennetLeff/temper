#!/usr/bin/env python3.11
"""Debug script to check differential pair path continuity."""

import sys
from pathlib import Path

sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.io.kicad_parser import parse_kicad_pcb


def main():
    # Parse the board
    board = parse_kicad_pcb(Path("output/test_adaptive_fixed/iteration_1.kicad_pcb"))

    # Find USB_D+ traces
    usb_dp = [t for t in board.traces if t.net == "USB_D+"]

    print(f"Total USB_D+ traces: {len(usb_dp)}")

    # Group by layer
    by_layer = {}
    for t in usb_dp:
        if t.layer not in by_layer:
            by_layer[t.layer] = []
        by_layer[t.layer].append(t)

    for layer in sorted(by_layer.keys()):
        traces = by_layer[layer]
        traces.sort(key=lambda t: (t.start[0], t.start[1]))

        print(f"\n{layer}: {len(traces)} traces")

        # Check for gaps (trace end doesn't match next trace start)
        gaps = []
        for i in range(len(traces) - 1):
            t1 = traces[i]
            t2 = traces[i + 1]

            # Check if t1.end is near t2.start or t2.end
            dist_to_start = ((t1.end[0] - t2.start[0]) ** 2 + (t1.end[1] - t2.start[1]) ** 2) ** 0.5
            dist_to_end = ((t1.end[0] - t2.end[0]) ** 2 + (t1.end[1] - t2.end[1]) ** 2) ** 0.5

            # If neither endpoint is within 0.01mm, there's a gap
            if dist_to_start > 0.01 and dist_to_end > 0.01:
                gaps.append(
                    {
                        "t1_end": t1.end,
                        "t2_start": t2.start,
                        "t2_end": t2.end,
                        "dist": dist_to_start,
                        "i": i,
                    }
                )

        if gaps:
            print(f"  ⚠️  Found {len(gaps)} gaps:")
            for g in gaps[:5]:  # Show first 5
                print(
                    f"    Gap {g['i']}: trace ends at {g['t1_end']}, next starts at {g['t2_start']}, dist={g['dist']:.4f}mm"
                )
        else:
            print(f"  ✓ No gaps detected")


if __name__ == "__main__":
    main()
