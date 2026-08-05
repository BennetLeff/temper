#!/usr/bin/env python3
"""VERBATIM pre-migration oracle for ``temper_workflow/routing/route_and_measure.py``.

Wave 4, Phase 5 (cli/adapters/temper-workflow slice). Pinned from
``packages/temper-workflow/src/temper_workflow/routing/route_and_measure.py``
at the dispatch base (origin/main 15110fecc). The pre-migration file's
shebang (``#!/usr/bin/env python3``) is preserved at the very top and its
own one-line docstring is replaced by this header; every statement below is
byte-identical to the pinned commit. DO NOT EDIT THE SEMANTICS: this is the
oracle the Rust compute (``temper_orchestration``) must reproduce
bit-identically; any edit here silently weakens the differential proof.

The compute this oracle pins is ``measure_copper_length``: the per-trace
Euclidean segment length (``math.sqrt(dx**2 + dy**2)`` -- libm ``pow`` via
``** 2``, correctly-rounded ``math.sqrt``), the falsy-net skip, the per-net
accumulation (``net_lengths.get(net, 0.0) + length`` in first-seen order)
and the naive ``total_length += length``. The differential
(``test_route_and_measure_rust_differential.py``) extracts that loop body
mechanically and drives it against the Rust
``temper_orchestration.measure_copper_length``.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb


def measure_copper_length(pcb_path: Path) -> dict:
    """Parse a routed PCB and sum up trace lengths per net."""
    result = parse_kicad_pcb(pcb_path)

    net_lengths: dict[str, float] = {}
    total_length = 0.0

    for trace in result.traces:
        if not trace.net:
            continue

        # Calculate Euclidean length of the segment
        dx = trace.end[0] - trace.start[0]
        dy = trace.end[1] - trace.start[1]
        length = math.sqrt(dx**2 + dy**2)

        net_name = trace.net
        net_lengths[net_name] = net_lengths.get(net_name, 0.0) + length
        total_length += length

    return {
        "total_wirelength_mm": total_length,
        "net_lengths_mm": net_lengths,
        "via_count": len(result.pads),  # Simplified, should count vias specifically if possible
    }


def main():
    parser = argparse.ArgumentParser(description="Route and measure actual PCB wirelength.")
    parser.add_argument("input_pcb", type=Path, help="Input placed .kicad_pcb file")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON report file")
    parser.add_argument("--jar", type=Path, help="Path to freerouting.jar")
    parser.add_argument("--keep", action="store_true", help="Keep the routed PCB file")

    args = parser.parse_args()

    # MazeRouter logic would go here
    print(f"Routing {args.input_pcb} using MazeRouter...")
    # placeholder for maze router execution
    routed_pcb = args.input_pcb.with_name(args.input_pcb.stem + "_routed.kicad_pcb")
    # For now, just simulate success if routed_pcb exists or print error
    if not routed_pcb.exists():
        # Was "Run internal_route.py first." That script was deleted on
        # 2026-08-04 as import-dead; scripts/route_board.py is the live
        # routing entry point (and what `make route` invokes).
        print(
            f"Error: Routed PCB not found at {routed_pcb}. "
            f"Run: python scripts/route_board.py --pcb {args.input_pcb} --output {routed_pcb}"
        )
        sys.exit(1)

    elapsed = 0.0  # Placeholder

    # Now measure the real copper
    print("Measuring copper lengths...")
    measurement = measure_copper_length(routed_pcb)

    report = {
        "input_file": str(args.input_pcb),
        "routing_time_s": elapsed,
        "total_wirelength_mm": measurement["total_wirelength_mm"],
        "via_count": measurement["via_count"],
        "net_lengths": measurement["net_lengths_mm"],
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report written to {args.output}")
    else:
        print(json.dumps(report, indent=2))

    if not args.keep and routed_pcb.exists():
        routed_pcb.unlink()
        print(f"Deleted temporary routed PCB: {routed_pcb}")


if __name__ == "__main__":
    main()
