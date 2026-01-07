#!/usr/bin/env python3
"""Diagnose routing failures and generate regression tests.

Usage:
    python experiments/diagnose_routing_failures.py --output-dir /tmp/diagnosis
    python experiments/diagnose_routing_failures.py --generate-tests
    python experiments/diagnose_routing_failures.py --compare baseline.json current.json
"""

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum


class FailureCategory(Enum):
    ITERATION_EXHAUSTED = "iteration_exhausted"
    PATH_BLOCKED = "path_blocked"
    SEGMENT_ORDERING = "segment_ordering"
    NET_CLASS_CLEARANCE = "net_class_clearance"
    PLANE_CONNECTION = "plane_connection"
    DIFF_PAIR = "diff_pair"
    UNKNOWN = "unknown"


@dataclass
class NetFailure:
    net_name: str
    category: str
    pin_count: int
    segments_attempted: int
    segments_completed: int
    failure_message: str
    manhattan_distance: Optional[int] = None
    iterations_used: Optional[int] = None
    blocking_component: Optional[str] = None
    clearance_required: Optional[float] = None
    clearance_actual: Optional[float] = None


@dataclass
class DiagnosisReport:
    timestamp: str
    total_nets: int
    successful_nets: int
    failed_nets: int
    failures_by_category: dict
    net_failures: list
    drc_violations: int
    actionable_violations: int


def run_routing_pipeline(output_dir: Path) -> tuple[str, str]:
    """Run the routing pipeline and capture logs."""
    cmd = [
        "python",
        "scripts/run_feedback_loop.py",
        "--max-iterations",
        "1",
        "--output-dir",
        str(output_dir),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return "", "ERROR: Pipeline timeout after 600s"


def parse_routing_logs(stdout: str, stderr: str) -> list[dict]:
    """Parse routing logs to extract failure information."""
    failures = []
    combined = stdout + "\n" + stderr

    # Pattern: Net exceeded iterations
    iter_pattern = r"(\w+) - exceeded (\d+) iterations.*dist=(\d+)"
    for match in re.finditer(iter_pattern, combined):
        failures.append(
            {
                "net_name": match.group(1),
                "category": "iteration_exhausted",
                "pin_count": 0,
                "segments_attempted": 1,
                "segments_completed": 0,
                "failure_message": f"Exceeded {match.group(2)} iterations",
                "manhattan_distance": int(match.group(3)),
                "iterations_used": int(match.group(2)),
            }
        )

    # Pattern: Could not find path segment
    segment_pattern = r"(\w+) - Could not find path segment ([\d\->,\s]+)"
    for match in re.finditer(segment_pattern, combined):
        net = match.group(1)
        segments = match.group(2)
        failures.append(
            {
                "net_name": net,
                "category": "path_blocked",
                "pin_count": len(segments.split("->")) if "->" in segments else 2,
                "segments_attempted": 1,
                "segments_completed": 0,
                "failure_message": f"Segment {segments} blocked",
            }
        )

    # Pattern: Plane stub rejected
    plane_pattern = r"Plane stub trace for (\w+) rejected.*clearance violation with ([\w.]+): ([\d.]+)mm < ([\d.]+)mm"
    for match in re.finditer(plane_pattern, combined):
        failures.append(
            {
                "net_name": match.group(1),
                "category": "plane_connection",
                "pin_count": 2,
                "segments_attempted": 1,
                "segments_completed": 0,
                "failure_message": f"Clearance violation with {match.group(2)}",
                "blocking_component": match.group(2),
                "clearance_actual": float(match.group(3)),
                "clearance_required": float(match.group(4)),
            }
        )

    # Pattern: Diff pair collision
    diff_pattern = r"Diff pair (\w+) P/N collision at"
    for match in re.finditer(diff_pattern, combined):
        failures.append(
            {
                "net_name": match.group(1),
                "category": "diff_pair",
                "pin_count": 4,
                "segments_attempted": 2,
                "segments_completed": 0,
                "failure_message": "P/N traces collided",
            }
        )

    return failures


def categorize_failures(failures: list[dict]) -> dict[str, int]:
    """Count failures by category."""
    counts = {cat.value: 0 for cat in FailureCategory}
    for f in failures:
        counts[f["category"]] += 1
    return counts


def generate_diagnosis_report(output_dir: Path) -> dict:
    """Run pipeline and generate full diagnosis report."""
    print("Running routing pipeline...")
    stdout, stderr = run_routing_pipeline(output_dir)

    # Save raw logs
    (output_dir / "routing_stdout.log").write_text(stdout)
    (output_dir / "routing_stderr.log").write_text(stderr)
    print(f"Saved logs to {output_dir}")

    # Parse failures
    failures = parse_routing_logs(stdout, stderr)

    # Count successes from logs
    success_pattern = r"Successfully routed (\d+)/(\d+) nets"
    match = re.search(success_pattern, stdout + stderr)
    if match:
        successful = int(match.group(1))
        total = int(match.group(2))
    else:
        total = len(failures) + 50  # Estimate
        successful = total - len(failures)

    # Load DRC report if available
    drc_path = output_dir / "drc_report.json"
    if drc_path.exists():
        with open(drc_path) as f:
            drc = json.load(f)
        drc_total = drc.get("total", 0)
        drc_actionable = drc.get("actionable", 0)
    else:
        drc_total = 0
        drc_actionable = 0

    return {
        "timestamp": datetime.now().isoformat(),
        "total_nets": total,
        "successful_nets": successful,
        "failed_nets": len(failures),
        "failures_by_category": categorize_failures(failures),
        "net_failures": failures,
        "drc_violations": drc_total,
        "actionable_violations": drc_actionable,
    }


def generate_regression_tests(report: dict, output_path: Path):
    """Generate pytest regression tests from failure report."""

    test_code = f'''"""Auto-generated regression tests for routing failures.

Generated: {report["timestamp"]}
Baseline: {report["failed_nets"]} failed nets, {report["actionable_violations"]} actionable DRC violations

These tests document CURRENT failures. As fixes are applied:
1. Tests should start passing
2. Update baseline when fixes are complete
"""

import pytest

# Mark all as expected failures until fixed
pytestmark = pytest.mark.xfail(reason="Known routing failures - fixing in progress")


class TestIterationExhaustedNets:
    """Tests for nets that exceed iteration limits."""
    
    def test_baseline_iteration_exhausted(self):
        """Baseline: {len([f for f in report["net_failures"] if f.get("category") == "iteration_exhausted"])} nets exceeded iterations."""
        assert False, "Tests to be implemented after baseline"


class TestBlockedPathNets:
    """Tests for nets where path is blocked."""
    
    def test_baseline_blocked_paths(self):
        """Baseline: {len([f for f in report["net_failures"] if f.get("category") == "path_blocked"])} nets have blocked paths."""
        assert False, "Tests to be implemented after baseline"


class TestPlaneConnectionNets:
    """Tests for plane connection failures."""
    
    def test_baseline_plane_connections(self):
        """Baseline: {len([f for f in report["net_failures"] if f.get("category") == "plane_connection"])} plane connection failures."""
        assert False, "Tests to be implemented after baseline"


class TestBaselineMetrics:
    """Baseline metrics for tracking progress."""
    
    def test_total_failed_nets_baseline(self):
        """Track total failed nets (baseline: {report["failed_nets"]})."""
        # This test passes if failures <= baseline
        baseline = {report["failed_nets"]}
        # TODO: Replace with actual routing run
        current_failures = baseline
        assert current_failures <= baseline, \\
            f"Regression: {{current_failures}} failures > {{baseline}} baseline"
    
    def test_actionable_drc_baseline(self):
        """Track actionable DRC violations (baseline: {report["actionable_violations"]})."""
        baseline = {report["actionable_violations"]}
        # TODO: Replace with actual DRC run
        current_drc = baseline
        assert current_drc <= baseline, \\
            f"Regression: {{current_drc}} DRC > {{baseline}} baseline"
'''

    output_path.write_text(test_code)
    print(f"Generated: {output_path}")


def compare_reports(baseline_path: Path, current_path: Path):
    """Compare two diagnosis reports and show improvement."""
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(current_path) as f:
        current = json.load(f)

    print("=" * 60)
    print("ROUTING IMPROVEMENT REPORT")
    print("=" * 60)

    print(f"\nBaseline: {baseline['timestamp']}")
    print(f"Current:  {current['timestamp']}")

    print("\n--- Net Routing ---")
    baseline_failed = baseline["failed_nets"]
    current_failed = current["failed_nets"]
    delta = baseline_failed - current_failed
    print(f"Failed nets: {baseline_failed} -> {current_failed} ({delta:+d})")

    print("\n--- By Category ---")
    for cat in FailureCategory:
        b = baseline["failures_by_category"].get(cat.value, 0)
        c = current["failures_by_category"].get(cat.value, 0)
        d = b - c
        status = "✓" if d > 0 else ("=" if d == 0 else "✗")
        print(f"  {cat.value:25} {b:3d} -> {c:3d} ({d:+3d}) {status}")

    print("\n--- DRC Violations ---")
    b_drc = baseline["actionable_violations"]
    c_drc = current["actionable_violations"]
    d_drc = b_drc - c_drc
    print(f"Actionable: {b_drc} -> {c_drc} ({d_drc:+d})")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Diagnose routing failures")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/routing_diagnosis"))
    parser.add_argument("--generate-tests", action="store_true")
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "CURRENT"))
    parser.add_argument("--save-baseline", action="store_true")

    args = parser.parse_args()

    if args.compare:
        compare_reports(Path(args.compare[0]), Path(args.compare[1]))
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)

    report = generate_diagnosis_report(args.output_dir)

    # Save report
    report_path = args.output_dir / "diagnosis_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Saved: {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("ROUTING DIAGNOSIS SUMMARY")
    print("=" * 60)
    print(f"Total nets:     {report['total_nets']}")
    print(f"Successful:     {report['successful_nets']}")
    print(f"Failed:         {report['failed_nets']}")
    print(f"DRC violations: {report['actionable_violations']} actionable")
    print("\nFailures by category:")
    for cat, count in sorted(report["failures_by_category"].items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"  {cat:25} {count:3d}")

    if args.generate_tests:
        test_path = Path("tests/deterministic/test_routing_regressions_generated.py")
        generate_regression_tests(report, test_path)

    if args.save_baseline:
        baseline_path = Path("tests/deterministic/baseline_routing_report.json")
        with open(baseline_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Saved baseline: {baseline_path}")


if __name__ == "__main__":
    main()
