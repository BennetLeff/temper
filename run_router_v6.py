#!/usr/bin/env python3
"""
Run Router V6 on temper PCB and generate baseline metrics.
"""

import json
import sys
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from temper_placer.router_v6.pipeline import RouterV6Pipeline


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run Router V6 on temper PCB")
    parser.add_argument("--pcb", type=Path, default=Path("pcb/temper.kicad_pcb"), help="Input PCB file")
    parser.add_argument("--output", type=Path, default=Path("pcb/temper_router_v6_output.kicad_pcb"), help="Output PCB file")
    parser.add_argument("--metrics", type=Path, default=Path("pcb/temper_router_v6_metrics.json"), help="Metrics JSON file")
    parser.add_argument("--theta-star", action="store_true", help="Enable Theta* any-angle routing (Experiment F)")
    parser.add_argument("--smoothing", action="store_true", help="Enable force-directed smoothing (Experiment G)")
    args = parser.parse_args()

    pcb_path = args.pcb
    output_path = args.output
    metrics_path = args.metrics

    if not pcb_path.exists():
        print(f"ERROR: PCB file not found: {pcb_path}")
        sys.exit(1)

    print("=" * 80)
    print("Router V6 - Temper Board Baseline Run")
    print("=" * 80)
    print(f"Input: {pcb_path}")
    print(f"Output: {output_path}")
    if args.theta_star:
        print("Experiment F: Theta* any-angle routing ENABLED")
    if args.smoothing:
        print("Experiment G: Force-directed smoothing ENABLED")
    print()

    # Run Router V6
    try:
        pipeline = RouterV6Pipeline(
            verbose=True,
            enable_theta_star=args.theta_star,
            enable_smoothing=args.smoothing,
        )
        result = pipeline.run(pcb_path)

        # Print results
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        print(f"Runtime: {result.runtime_seconds:.1f}s")
        print(f"Success: {result.success_count}/{result.success_count + result.failure_count} nets")
        print(f"Completion: {result.completion_rate * 100:.1f}%")
        print()

        # Export metrics
        metrics = {
            "runtime_seconds": result.runtime_seconds,
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "completion_rate": result.completion_rate,
            "escape_vias": len(result.escape_vias),
        }

        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        print(f"Metrics written to: {metrics_path}")

        # TODO: Export routed PCB (not implemented in pipeline yet)
        print("\nNote: PCB export not yet implemented in Router V6 pipeline")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
