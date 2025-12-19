#!/usr/bin/env python3
"""
Automated Routing Tax Collector.

Takes a placed .kicad_pcb file, routes it using FreeRouting,
and measures the actual copper length per net.
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.freerouting import FreeRoutingWrapper


def measure_copper_length(pcb_path: Path) -> dict:
    """Parse a routed PCB and sum up trace lengths per net."""
    result = parse_kicad_pcb(pcb_path)

    net_lengths = {}
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
        "via_count": len(
            result.pads
        ),  # Simplified, should count vias specifically if possible
    }


def main():
    parser = argparse.ArgumentParser(
        description="Route and measure actual PCB wirelength."
    )
    parser.add_argument("input_pcb", type=Path, help="Input placed .kicad_pcb file")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON report file")
    parser.add_argument("--jar", type=Path, help="Path to freerouting.jar")
    parser.add_argument("--keep", action="store_true", help="Keep the routed PCB file")

    args = parser.parse_args()

    jar_path = args.jar or Path(
        os.environ.get("FREEROUTING_JAR", "bin/freerouting.jar")
    )
    if not jar_path.exists():
        print(f"Error: FreeRouting JAR not found at {jar_path}")
        sys.exit(1)

    wrapper = FreeRoutingWrapper(jar_path=jar_path)

    routed_pcb_path = args.input_pcb.with_name(
        args.input_pcb.stem + "_routed.kicad_pcb"
    )

    print(f"Routing {args.input_pcb}...")
    start_time = time.time()

    routed_pcb, metrics = wrapper.route_pcb(args.input_pcb, routed_pcb_path)

    if not routed_pcb:
        print(f"Routing failed: {metrics.error_message}")
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"Routing completed in {elapsed:.1f}s")

    # Now measure the real copper
    print("Measuring copper lengths...")
    measurement = measure_copper_length(routed_pcb)

    report = {
        "input_file": str(args.input_pcb),
        "routing_time_s": elapsed,
        "total_wirelength_mm": measurement["total_wirelength_mm"],
        "via_count": metrics.via_count,  # Use metrics from wrapper if available
        "net_lengths": measurement["net_lengths_mm"],
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report written to {args.output}")
    else:
        print(json.dumps(report, indent=2))

    if not args.keep:
        if routed_pcb.exists():
            routed_pcb.unlink()
            print(f"Deleted temporary routed PCB: {routed_pcb}")


if __name__ == "__main__":
    main()
