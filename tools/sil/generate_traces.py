#!/usr/bin/env python3
"""
Convenience entry point for the SIL fault-injection trace pipeline.

1. Runs plant_model.py for each unique scenario referenced in faults.yaml.
2. Runs perturb.py to apply all fault perturbations.
3. Optionally runs check_coverage.py (--check-coverage).

Usage:
    python3 tools/sil/generate_traces.py \
        --output-dir firmware/test/build/traces
"""

import argparse
import os
import subprocess
import sys
import yaml


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SIL fault-injection traces")
    parser.add_argument("--output-dir", default="firmware/test/build/traces",
                        help="Output directory for traces and manifest")
    parser.add_argument("--faults", default="tools/sil/faults.yaml",
                        help="Path to faults YAML file")
    parser.add_argument("--plant-model", default="tools/sil/plant_model.py",
                        help="Path to plant model script")
    parser.add_argument("--perturb", default="tools/sil/perturb.py",
                        help="Path to perturb script")
    parser.add_argument("--check-coverage", action="store_true",
                        help="Run fault coverage check after generation")
    parser.add_argument("--ticks", type=int, default=500,
                        help="Ticks per scenario")
    parser.add_argument("--dt", type=float, default=0.1,
                        help="Time step in seconds")
    args = parser.parse_args()

    # Ensure output directory structure
    raw_dir = os.path.join(args.output_dir, "raw")
    perturbed_dir = os.path.join(args.output_dir, "perturbed")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(perturbed_dir, exist_ok=True)

    # Read faults YAML to discover which scenarios are needed
    with open(args.faults, "r") as f:
        faults_data = yaml.safe_load(f)

    scenarios = set()
    for fault in faults_data.get("faults", []):
        scenarios.add(fault["trace"])

    # Step 1: Generate baseline traces for each scenario
    for scenario in sorted(scenarios):
        cmd = [
            sys.executable, args.plant_model,
            "--scenario", scenario,
            "--ticks", str(args.ticks),
            "--dt", str(args.dt),
            "--output-dir", raw_dir,
        ]
        print(f"Generate: running plant model for '{scenario}'...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: plant model failed for '{scenario}':", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)
        print(result.stdout.strip())

    # Step 2: Apply perturbations
    cmd = [
        sys.executable, args.perturb,
        "--faults", args.faults,
        "--raw-dir", raw_dir,
        "--output-dir", perturbed_dir,
    ]
    print("Generate: applying perturbations...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: perturb failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    print(result.stdout.strip())

    # Step 3: Optional coverage check
    if args.check_coverage:
        coverage_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "check_coverage.py")
        cmd = [sys.executable, coverage_script]
        print("Generate: running coverage check...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)

    # Verify manifest exists
    manifest_path = os.path.join(args.output_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"ERROR: manifest.json not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\nTraces generated successfully in {args.output_dir}")
    for scenario in sorted(scenarios):
        path = os.path.join(raw_dir, f"{scenario}.csv")
        print(f"  raw/{scenario}.csv")
    for fault in faults_data.get("faults", []):
        name = fault["name"]
        path = os.path.join(perturbed_dir, f"{name}.csv")
        print(f"  perturbed/{name}.csv")
    print(f"  manifest.json")


if __name__ == "__main__":
    main()
