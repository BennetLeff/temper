#!/usr/bin/env python3
"""Coverage report: per-family pass/fail counts from a wasm test run.

Uses `tools/wasm/test_family_map.json` to map each of the 95 registered tests
to the rule family (or families) it exercises, then joins against a wasm32 run
results JSON (from `run_wasm_tests.mjs --json`) to produce per-family coverage.

Usage:
    python3 tools/wasm/coverage_report.py \\
        --family-map tools/wasm/test_family_map.json \\
        --results wasm_results.json \\
        --output coverage.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_family_map(path: str) -> dict[str, list[str]]:
    """Load the per-test family mapping, returning a dict of test_name -> [family, ...]."""
    with open(path) as f:
        data = json.load(f)
    per_test = data.get("per_test", {})
    return dict(per_test)


def load_results(path: str) -> list[dict[str, Any]]:
    """Load wasm32 run results and return the first repetition's results.

    In repeat mode, the results array is flattened across all repetitions.
    We use the first N entries (N = registered test count) as the canonical set,
    since verdicts are deterministic across repetitions.
    """
    with open(path) as f:
        data = json.load(f)
    results = data.get("results", [])
    registered = data.get("summary", {}).get("registered", 0)
    if registered and len(results) >= registered:
        # Use first repetition only for the classification
        return results[:registered]
    return results


def coverage_report(
    family_map: dict[str, list[str]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute per-family pass/fail/expected-fail/unexpected-pass counts."""
    per_family: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "total": 0, "pass": 0, "fail": 0,
        "expected_fail": 0, "unexpected_pass": 0, "other": 0,
        "tests": [],
    })

    unmapped: list[str] = []

    for r in results:
        name = r["name"]
        status = r.get("status", "unknown")
        families = family_map.get(name)
        if not families:
            unmapped.append(name)
            families = ["unmapped"]

        for family in families:
            f = per_family[family]
            f["total"] += 1
            if status == "pass":
                f["pass"] += 1
            elif status == "fail":
                f["fail"] += 1
            elif status == "expected-fail":
                f["expected_fail"] += 1
            elif status == "unexpected-pass":
                f["unexpected_pass"] += 1
            else:
                f["other"] += 1
            f["tests"].append({"name": name, "status": status})

    # Compute coverage metrics
    families_report = {}
    for family, stats in sorted(per_family.items()):
        total = stats["total"]
        passing = stats["pass"] + stats["expected_fail"]
        failing = stats["fail"] + stats["unexpected_pass"]
        can_catch = failing + stats["expected_fail"] > 0
        families_report[family] = {
            "total": total,
            "pass": stats["pass"],
            "fail": stats["fail"],
            "expected_fail": stats["expected_fail"],
            "unexpected_pass": stats["unexpected_pass"],
            "other": stats["other"],
            "coverage_ratio": round(passing / total, 4) if total else 0,
            "active_coverage": round(stats["pass"] / total, 4) if total else 0,
            "can_catch_failures": failing + stats["expected_fail"] > 0,
        }

    return {
        "families": families_report,
        "unmapped_tests": unmapped,
        "total_tests": len(results),
        "mapped_tests": len(results) - len(unmapped),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the coverage report as Markdown tables."""
    lines = [
        "# WASM Test Coverage Report",
        "",
        f"- **Total tests:** {report['total_tests']}",
        f"- **Mapped to families:** {report['mapped_tests']}",
        f"- **Unmapped:** {len(report['unmapped_tests'])}",
        "",
        "## Per-Family Coverage",
        "",
        "| Family | Tests | Pass | Expected-Fail | Fail | Coverage % | Can Catch Failures? |",
        "|--------|-------|------|---------------|------|------------|---------------------|",
    ]

    families = report["families"]
    for family in sorted(families.keys()):
        f = families[family]
        can_catch = "**YES**" if f["can_catch_failures"] else "VACUOUS ⚠️"
        pct = f"{f['coverage_ratio'] * 100:.1f}%"
        lines.append(
            f"| {family} | {f['total']} | {f['pass']} | {f['expected_fail']} "
            f"| {f['fail']} | {pct} | {can_catch} |"
        )

    lines.append("")
    lines.append("## R7/R8 Non-Vacuity Assessment")
    lines.append("")

    for family in sorted(families.keys()):
        f = families[family]
        if f["can_catch_failures"]:
            lines.append(f"- **`{family}`**: Non-vacuous — {f['fail']} failing + "
                          f"{f['expected_fail']} expected-fail tests exercise the failure path.")
        else:
            lines.append(f"- **`{family}`**: ⚠️ Potentially vacuous — all {f['total']} "
                          f"tests pass with no demonstrated failure case.")

    if report["unmapped_tests"]:
        lines.append("")
        lines.append("## Unmapped Tests")
        lines.append("")
        for name in report["unmapped_tests"]:
            lines.append(f"- `{name}`")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Coverage report: per-family pass/fail from wasm test run"
    )
    ap.add_argument(
        "--family-map",
        required=True,
        help="Path to test_family_map.json",
    )
    ap.add_argument(
        "--results",
        required=True,
        help="Path to wasm results JSON (from run_wasm_tests.mjs --json)",
    )
    ap.add_argument(
        "--output", "-o",
        help="Output path for Markdown report (default: stdout)",
    )
    args = ap.parse_args()

    family_map = load_family_map(args.family_map)
    results = load_results(args.results)
    report = coverage_report(family_map, results)
    md = render_markdown(report)

    if args.output:
        Path(args.output).write_text(md)
        print(f"Wrote {args.output}")
    else:
        sys.stdout.write(md)

    # Exit non-zero if any family is vacuous
    for family, f in report["families"].items():
        if not f["can_catch_failures"]:
            print(f"WARNING: family '{family}' has no demonstrated failure case (vacuous)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
