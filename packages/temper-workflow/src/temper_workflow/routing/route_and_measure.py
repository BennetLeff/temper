#!/usr/bin/env python3
"""
Automated Routing Tax Collector.

Takes a placed .kicad_pcb file, routes it using the internal maze router,
and measures the actual copper length per net using the internal maze router.

Wave-4 Phase-5 delegation shim: the per-trace accumulation compute of
``measure_copper_length`` (Euclidean segment lengths via
``math.sqrt(dx**2 + dy**2)`` — libm ``pow`` for ``** 2`` — the falsy-net
skip, the per-net first-seen accumulation and the naive total) is
implemented in Rust in the ``temper-orchestration`` crate
(``temper_orchestration.measure_copper_length``), pinned bit-identically by
``tests/test_route_and_measure_rust_differential.py`` against the VERBATIM
pre-migration oracle ``tests/_route_and_measure_py_oracle.py``. The parse
step stays Python (``temper_placer.io.kicad_parser`` is a Phase-3 surface,
not this slice's) and the script ``main()`` (argparse surface, exit codes,
file handling) stays byte-identical.
"""

import argparse
import json
import sys
from pathlib import Path

import temper_orchestration as _to
from temper_placer.io.kicad_parser import parse_kicad_pcb


def _measure_from_segments(segments: list, via_count: int) -> dict:
    """Assemble the copper-length report from flattened trace segments.

    ``segments`` is ``[(net, start_x, start_y, end_x, end_y), ...]`` (the
    shim's flatten of ``result.traces``); ``via_count`` is
    ``len(result.pads)``. The Rust kernel returns the total and the per-net
    lengths in first-seen order; the dict is assembled here so its insertion
    order IS the first-seen order (part of the contract, pinned by the
    differential).
    """
    total_length, net_length_pairs = _to.measure_copper_length(segments)
    return {
        "total_wirelength_mm": total_length,
        "net_lengths_mm": dict(net_length_pairs),
        "via_count": via_count,
    }


def measure_copper_length(pcb_path: Path) -> dict:
    """Parse a routed PCB and sum up trace lengths per net."""
    result = parse_kicad_pcb(pcb_path)

    # The falsy-net skip runs BEFORE the start/end index accesses, in the
    # oracle's statement order: `if not trace.net: continue` precedes
    # `trace.end[0] - trace.start[0]`, so a falsy-net trace with a
    # non-indexable start/end must be skipped, not raised on.
    segments = [
        (trace.net, trace.start[0], trace.start[1], trace.end[0], trace.end[1])
        for trace in result.traces
        if trace.net
    ]
    return _measure_from_segments(segments, len(result.pads))


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
