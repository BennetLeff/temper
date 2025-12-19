#!/usr/bin/env python3
"""
Memory profiling script for temper-placer optimizer (temper-1my.3.6).

Profiles memory usage at different scales (50, 100, 200, 500 components)
to detect memory leaks and validate scalability.

Usage:
    python scripts/profile_memory_scale.py
    python scripts/profile_memory_scale.py --epochs 200
    python scripts/profile_memory_scale.py --components 50 100 200
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from temper_placer.scale.memory_profiler import (
    check_memory_thresholds,
    profile_optimizer_memory,
)


def main():
    parser = argparse.ArgumentParser(
        description="Profile memory usage at different scales"
    )
    parser.add_argument(
        "--components",
        type=int,
        nargs="+",
        default=[50, 100, 200, 500],
        help="Component counts to test (default: 50 100 200 500)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of training epochs (default: 100)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("memory_profile_results.json"),
        help="Output JSON file (default: memory_profile_results.json)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Memory Profiling for temper-placer Optimizer")
    print("=" * 80)
    print(f"Component counts: {args.components}")
    print(f"Epochs per run: {args.epochs}")
    print(f"Random seed: {args.seed}")
    print("=" * 80)
    print()

    profiles = []
    all_passed = True

    for n_components in args.components:
        print(f"\n{'=' * 80}")
        print(f"Profiling {n_components} components")
        print(f"{'=' * 80}")

        try:
            profile = profile_optimizer_memory(
                n_components=n_components,
                epochs=args.epochs,
                seed=args.seed,
            )

            print("\n  Results:")
            print(f"    Peak RSS:        {profile.peak_rss_mb:.1f} MB")
            print(f"    JAX Device:      {profile.jax_device_mb:.1f} MB")
            print(f"    Memory Growth:   {profile.memory_growth_mb_per_100_epochs:.2f} MB/100 epochs")
            print(f"    GC Collections:  {profile.gc_collections}")
            print(f"    Runtime:         {profile.runtime_seconds:.2f} seconds")

            # Check thresholds
            result = check_memory_thresholds(profile)

            if result.passed:
                print("\n  ✓ PASSED - Memory usage within thresholds")
            else:
                print("\n  ✗ FAILED - Memory threshold violations:")
                for violation in result.violations:
                    print(f"      - {violation}")
                all_passed = False

            profiles.append(profile)

        except Exception as e:
            print(f"\n  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    # Save results
    print(f"\n{'=' * 80}")
    print("Summary")
    print(f"{'=' * 80}")

    if profiles:
        print("\n  Component Count  |  Peak RSS (MB)  |  Growth (MB/100ep)  |  Runtime (s)")
        print("  " + "-" * 73)
        for profile in profiles:
            print(
                f"  {profile.n_components:15d}  |  {profile.peak_rss_mb:13.1f}  |  "
                f"{profile.memory_growth_mb_per_100_epochs:17.2f}  |  {profile.runtime_seconds:11.2f}"
            )

        # Save to JSON
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "epochs": args.epochs,
            "seed": args.seed,
            "profiles": [p.to_dict() for p in profiles],
        }

        with open(args.output, "w") as f:
            json.dump(report_data, f, indent=2)

        print(f"\n  Results saved to: {args.output}")

        # Memory leak detection
        if len(profiles) >= 2:
            max_growth = max(p.memory_growth_mb_per_100_epochs for p in profiles)
            if max_growth > 1.0:
                print("\n  ⚠️  WARNING: Potential memory leak detected")
                print(f"      Max growth: {max_growth:.2f} MB/100 epochs")
            else:
                print(f"\n  ✓ No memory leaks detected (max growth: {max_growth:.2f} MB/100 epochs)")

    print()
    print("=" * 80)

    if all_passed:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
