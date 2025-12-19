#!/usr/bin/env python3
"""
Wrapper script for FreeRouting CLI.
"""

import os
import sys
from pathlib import Path

from temper_placer.routing.freerouting import FreeRoutingWrapper


def main():
    if len(sys.argv) < 3:
        print("Usage: route.py <input_pcb> <output_pcb>")
        sys.exit(1)

    pcb_path = Path(sys.argv[1])
    output_pcb = Path(sys.argv[2])

    # Path to FreeRouting JAR - should be provided by environment or standard location
    jar_path = Path(os.environ.get("FREEROUTING_JAR", "bin/freerouting.jar"))

    if not jar_path.exists():
        print(f"Error: FreeRouting JAR not found at {jar_path}")
        print("Please set FREEROUTING_JAR environment variable.")
        sys.exit(1)

    wrapper = FreeRoutingWrapper(jar_path=jar_path)
    print(f"Routing {pcb_path} -> {output_pcb}...")

    routed_pcb, metrics = wrapper.route_pcb(pcb_path, output_pcb)

    if routed_pcb:
        print(f"Routing successful!")
        print(f"Completion rate: {metrics.completion_rate * 100:.1f}%")
        print(f"Wirelength: {metrics.wirelength_mm:.1f} mm")
        print(f"Vias: {metrics.via_count}")
    else:
        print(f"Routing failed: {metrics.error_message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
