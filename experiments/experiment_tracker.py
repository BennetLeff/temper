#!/usr/bin/env python3
"""
Experiment Tracker for Routing Optimization

Tracks the full pipeline: placement -> DSN export -> routing result
with rich metadata to understand WHY configurations work or fail.

Usage:
    # Record an experiment
    python experiments/experiment_tracker.py record \
        --dsn pcb/temper_ordered.dsn \
        --placement-source "temper-placer seed=42 loss=congestion+wirelength" \
        --notes "Testing net ordering by span"

    # Query best results
    python experiments/experiment_tracker.py best --top 5

    # Show experiment history
    python experiments/experiment_tracker.py history --limit 20
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional


EXPERIMENTS_FILE = Path("experiments/routing_experiments.jsonl")


@dataclass
class RoutingExperiment:
    """Complete record of a routing experiment."""

    # Identity
    id: str  # Hash of DSN content for deduplication
    timestamp: str

    # Placement context
    placement_source: str  # e.g., "temper-placer", "manual", "kicad"
    placement_seed: Optional[int] = None
    placement_loss: Optional[str] = None  # e.g., "congestion+wirelength"
    placement_params: dict = field(default_factory=dict)

    # DSN configuration
    dsn_file: str = ""
    clearance: Optional[int] = None
    trace_width: Optional[int] = None
    via_diameter: Optional[int] = None
    layer_restrictions: bool = False  # True if use_layer directives present
    net_classes: list = field(default_factory=list)

    # Routing result
    unrouted: int = -1
    total_nets: int = 0
    completion_pct: float = 0.0
    passes: int = 0
    routing_time_sec: float = 0.0

    # Failed nets for analysis
    failed_nets: list = field(default_factory=list)

    # Notes
    notes: str = ""
    git_commit: str = ""


def compute_dsn_hash(dsn_path: Path) -> str:
    """Compute hash of DSN content for experiment deduplication."""
    content = dsn_path.read_text()
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def extract_dsn_config(dsn_path: Path) -> dict:
    """Extract configuration from DSN file."""
    content = dsn_path.read_text()
    config = {
        "clearance": None,
        "trace_width": None,
        "via_diameter": None,
        "layer_restrictions": False,
        "net_classes": [],
    }

    # Extract clearance
    match = re.search(r'\(clearance (\d+)\)', content)
    if match:
        config["clearance"] = int(match.group(1))

    # Extract trace width
    match = re.search(r'\(width (\d+)\)', content)
    if match:
        config["trace_width"] = int(match.group(1))

    # Extract via diameter
    match = re.search(r'\(via_padstack.*?diameter (\d+)', content, re.DOTALL)
    if match:
        config["via_diameter"] = int(match.group(1))

    # Check for layer restrictions
    config["layer_restrictions"] = "(use_layer" in content

    # Extract net classes
    for match in re.finditer(r'\(class (\w+)', content):
        config["net_classes"].append(match.group(1))

    return config


def parse_freerouter_output(output: str) -> dict:
    """Parse FreeRouter output for detailed routing stats."""
    result = {
        "unrouted": -1,
        "total_nets": 0,
        "passes": 0,
        "failed_nets": [],
    }

    # Parse final unrouted count
    for line in reversed(output.split("\n")):
        if "unrouted" in line.lower():
            match = re.search(r'\((\d+) unrouted\)', line)
            if match:
                result["unrouted"] = int(match.group(1))
                break

    # Parse pass count
    for line in output.split("\n"):
        if "pass #" in line.lower():
            match = re.search(r'pass #(\d+)', line, re.IGNORECASE)
            if match:
                result["passes"] = max(result["passes"], int(match.group(1)))

    # Try to find failed net names
    for match in re.finditer(r"Unable to route.*?net[:\s]+['\"]?(\w+)['\"]?", output, re.IGNORECASE):
        if match.group(1) not in result["failed_nets"]:
            result["failed_nets"].append(match.group(1))

    return result


def run_routing_experiment(
    dsn_path: Path,
    placement_source: str,
    notes: str = "",
    max_passes: int = 100,
    **placement_params
) -> RoutingExperiment:
    """Run FreeRouter and record the complete experiment."""

    # Get DSN configuration
    dsn_config = extract_dsn_config(dsn_path)
    dsn_hash = compute_dsn_hash(dsn_path)

    # Get git commit
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except:
        git_commit = ""

    # Create experiment record
    exp = RoutingExperiment(
        id=dsn_hash,
        timestamp=datetime.now().isoformat(),
        placement_source=placement_source,
        placement_seed=placement_params.get("seed"),
        placement_loss=placement_params.get("loss"),
        placement_params=placement_params,
        dsn_file=str(dsn_path),
        clearance=dsn_config["clearance"],
        trace_width=dsn_config["trace_width"],
        via_diameter=dsn_config["via_diameter"],
        layer_restrictions=dsn_config["layer_restrictions"],
        net_classes=dsn_config["net_classes"],
        notes=notes,
        git_commit=git_commit,
    )

    # Run FreeRouter
    jar_path = Path("~/tools/freerouting.jar").expanduser()
    if not jar_path.exists():
        print(f"ERROR: FreeRouter not found at {jar_path}")
        return exp

    print(f"Running FreeRouter on {dsn_path}...")
    start_time = datetime.now()

    # Create a temp file for the SES output (required for headless mode)
    # We use .ses extension so FreeRouter knows to write a session file
    with tempfile.NamedTemporaryFile(suffix='.ses', delete=False) as ses_file:
        ses_path = ses_file.name
    # We don't need to keep the file open
    
    cmd = [
        "java",
        "-Djava.awt.headless=true",
        "-jar", str(jar_path),
        "-de", str(dsn_path),
        "-do", str(ses_path),
        "-mp", str(max_passes),
        "-mt", "1",
        "--gui.enabled=false",
    ]

    # Use tee to capture output while still displaying it
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as log_file:
        log_path = log_file.name

    # Run with output to both console and file
    full_cmd = f"{' '.join(cmd)} 2>&1 | tee {log_path}"
    result = subprocess.run(full_cmd, shell=True, timeout=600)

    # Read captured output
    with open(log_path) as f:
        output = f.read()
    os.unlink(log_path)
    
    # Clean up SES file
    if os.path.exists(ses_path):
        os.unlink(ses_path)

    end_time = datetime.now()
    exp.routing_time_sec = (end_time - start_time).total_seconds()

    # Parse results
    routing_result = parse_freerouter_output(output)
    exp.unrouted = routing_result["unrouted"]
    exp.passes = routing_result["passes"]
    exp.failed_nets = routing_result["failed_nets"]

    # Calculate completion
    if exp.total_nets > 0:
        exp.completion_pct = (exp.total_nets - exp.unrouted) / exp.total_nets * 100

    return exp


def save_experiment(exp: RoutingExperiment):
    """Append experiment to JSONL file."""
    EXPERIMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(EXPERIMENTS_FILE, "a") as f:
        f.write(json.dumps(asdict(exp)) + "\n")

    print(f"Experiment {exp.id} saved: {exp.unrouted} unrouted")


def load_experiments() -> list[RoutingExperiment]:
    """Load all experiments from JSONL file."""
    if not EXPERIMENTS_FILE.exists():
        return []

    experiments = []
    with open(EXPERIMENTS_FILE) as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                experiments.append(RoutingExperiment(**data))

    return experiments


def show_best(top: int = 10):
    """Show best routing results."""
    experiments = load_experiments()
    if not experiments:
        print("No experiments recorded yet.")
        return

    # Sort by unrouted (ascending), then by time
    valid = [e for e in experiments if e.unrouted >= 0]
    valid.sort(key=lambda e: (e.unrouted, e.routing_time_sec))

    print(f"\n{'='*70}")
    print(f"TOP {min(top, len(valid))} ROUTING RESULTS")
    print(f"{'='*70}")

    for i, exp in enumerate(valid[:top], 1):
        layers = "restricted" if exp.layer_restrictions else "all layers"
        print(f"\n{i}. {exp.unrouted} unrouted | {exp.dsn_file}")
        print(f"   Source: {exp.placement_source}")
        print(f"   Config: clearance={exp.clearance}, width={exp.trace_width}, {layers}")
        if exp.notes:
            print(f"   Notes: {exp.notes}")
        print(f"   Time: {exp.routing_time_sec:.1f}s | {exp.timestamp[:10]}")


def show_history(limit: int = 20):
    """Show recent experiment history."""
    experiments = load_experiments()
    if not experiments:
        print("No experiments recorded yet.")
        return

    print(f"\n{'='*70}")
    print(f"EXPERIMENT HISTORY (last {limit})")
    print(f"{'='*70}")

    for exp in experiments[-limit:]:
        status = f"{exp.unrouted} unrouted" if exp.unrouted >= 0 else "FAILED"
        layers = "L2" if exp.layer_restrictions else "L4"
        print(f"\n[{exp.id}] {status} | {exp.dsn_file}")
        print(f"  {exp.placement_source} | clr={exp.clearance} w={exp.trace_width} {layers}")
        if exp.notes:
            print(f"  Note: {exp.notes}")


def record_experiment(args):
    """Record a new routing experiment."""
    dsn_path = Path(args.dsn)
    if not dsn_path.exists():
        print(f"ERROR: DSN file not found: {dsn_path}")
        sys.exit(1)

    exp = run_routing_experiment(
        dsn_path=dsn_path,
        placement_source=args.placement_source,
        notes=args.notes or "",
        max_passes=args.passes,
        seed=args.seed,
        loss=args.loss,
    )

    save_experiment(exp)

    print(f"\n{'='*50}")
    print(f"RESULT: {exp.unrouted} unrouted nets")
    print(f"{'='*50}")
    if exp.failed_nets:
        print(f"Failed nets: {', '.join(exp.failed_nets)}")


def batch_experiment(args):
    """Run routing on all DSN files matching a pattern."""
    from glob import glob

    dsn_files = glob(args.pattern)
    if not dsn_files:
        print(f"No files matching pattern: {args.pattern}")
        return

    print(f"\nRunning batch experiment on {len(dsn_files)} DSN files...")
    print("=" * 60)

    results = []
    for dsn_file in sorted(dsn_files):
        dsn_path = Path(dsn_file)
        print(f"\n>>> Processing: {dsn_path.name}")

        exp = run_routing_experiment(
            dsn_path=dsn_path,
            placement_source=args.placement_source or "batch",
            notes=args.notes or f"Batch run: {args.pattern}",
            max_passes=args.passes,
        )

        save_experiment(exp)
        results.append((dsn_path.name, exp.unrouted))

    # Summary
    print("\n" + "=" * 60)
    print("BATCH RESULTS")
    print("=" * 60)
    for name, unrouted in sorted(results, key=lambda x: x[1]):
        print(f"  {unrouted:3d} unrouted | {name}")

    best = min(results, key=lambda x: x[1])
    print(f"\nBest: {best[0]} with {best[1]} unrouted")


def main():
    parser = argparse.ArgumentParser(description="Track routing experiments")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Record command
    record_parser = subparsers.add_parser("record", help="Record a routing experiment")
    record_parser.add_argument("--dsn", required=True, help="Path to DSN file")
    record_parser.add_argument("--placement-source", required=True,
                               help="How placement was created (e.g., 'temper-placer', 'manual')")
    record_parser.add_argument("--notes", help="Notes about this experiment")
    record_parser.add_argument("--passes", type=int, default=100, help="Max routing passes")
    record_parser.add_argument("--seed", type=int, help="Placement seed if applicable")
    record_parser.add_argument("--loss", help="Loss function used if applicable")

    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Run batch experiments on multiple DSNs")
    batch_parser.add_argument("pattern", help="Glob pattern for DSN files (e.g., 'pcb/*.dsn')")
    batch_parser.add_argument("--placement-source", help="Source description")
    batch_parser.add_argument("--notes", help="Notes about this batch")
    batch_parser.add_argument("--passes", type=int, default=100, help="Max routing passes")

    # Best command
    best_parser = subparsers.add_parser("best", help="Show best results")
    best_parser.add_argument("--top", type=int, default=10, help="Number of results to show")

    # History command
    history_parser = subparsers.add_parser("history", help="Show experiment history")
    history_parser.add_argument("--limit", type=int, default=20, help="Number of entries")

    args = parser.parse_args()

    if args.command == "record":
        record_experiment(args)
    elif args.command == "batch":
        batch_experiment(args)
    elif args.command == "best":
        show_best(args.top)
    elif args.command == "history":
        show_history(args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
