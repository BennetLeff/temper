#!/usr/bin/env python3
"""R2 (U4) sampling driver — runs N fresh processes of the Rust full-board-pass
benchmark and reports median + full observed range for per-case CPU and peak RSS.

Protocol (from the Phase 0 plan §U4):
  - N = 32 fresh processes (floor 12)
  - Each process is independent (peak RSS resets)
  - Median and full range, never a mean
  - Comparison: exact ≤ 134_217_728 bytes (128 MiB Cloudflare Workers limit)

Usage:
    1. Serialise the board once:
       uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json

    2. Build the benchmark binary:
       cargo build --release --no-default-features \\
         --manifest-path packages/temper-drc-rs/Cargo.toml \\
         --example r2_full_board_pass

    3. Run the sampling driver:
       uv run python3 tools/wasm/r2_sample.py \\
         --binary target/release/examples/r2_full_board_pass \\
         --board /tmp/board.json \\
         --samples 32

Output:
    JSON on stdout with median, range, per-rule stats, and PASS/FAIL verdict.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path


def run_one(binary: str, board_json: str, family: str = "all") -> dict:
    """Run one fresh process and return its parsed --summary JSON output."""
    cmd = [binary, board_json, "--summary"]
    if family != "all":
        cmd += ["--family", family]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        print(f"ERROR: process exited {result.returncode}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON from benchmark: {e}", file=sys.stderr)
        print(result.stdout[:500], file=sys.stderr)
        sys.exit(1)


# Rule families by module (R5's seam). Each maps to the rule-name prefix the
# benchmark filters on; `--all-families` runs one fresh-process batch per
# family so peak RSS is attributable to the family (ru_maxrss is a process
# high-water mark and does not reset between families inside one process).
RULE_FAMILIES = ["drc", "emc", "erc", "safety", "placement", "routing"]


def aggregate(samples: list[dict]) -> dict:
    """Aggregate a batch of fresh-process samples into the report shape."""
    wall_list = [s["wall_ns"] for s in samples]
    rss_list = [s["rss_bytes"] for s in samples]
    error_list = [s["violations_error"] for s in samples]

    # Per-rule aggregation (collect across samples)
    rule_data: dict[str, list[float]] = {}
    rule_category: dict[str, str] = {}
    for s in samples:
        for r in s["rules"]:
            name = r["name"]
            if name not in rule_data:
                rule_data[name] = []
                rule_category[name] = r["category"]
            rule_data[name].append(r["ns_per_case"])

    rule_stats: list[dict] = []
    for name in sorted(rule_data.keys()):
        vals = rule_data[name]
        med = statistics.median(vals)
        rule_stats.append(
            {
                "name": name,
                "category": rule_category[name],
                "median_ns": med,
                "min_ns": min(vals),
                "max_ns": max(vals),
            }
        )

    return {
        "samples": len(samples),
        "rules_run": samples[0]["rules_run"],
        "wall_ns": {
            "median": statistics.median(wall_list),
            "min": min(wall_list),
            "max": max(wall_list),
        },
        "rss_bytes": {
            "median": int(statistics.median(rss_list)),
            "min": min(rss_list),
            "max": max(rss_list),
            "unit": samples[0]["rss_unit"],
        },
        "violations": {
            "errors_median": int(statistics.median(error_list)),
            "errors_range": [min(error_list), max(error_list)],
        },
        "per_rule": rule_stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="R2 full-board-pass cost-model sampling driver"
    )
    parser.add_argument(
        "--binary",
        required=True,
        help="Path to the r2_full_board_pass release binary",
    )
    parser.add_argument(
        "--board",
        required=True,
        help="Path to the serialised BoardState JSON",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=32,
        help="Number of fresh processes per batch (default: 32, floor: 12)",
    )
    parser.add_argument(
        "--family",
        default="all",
        help="Rule-family prefix to measure (drc/emc/erc/safety/placement/"
        "routing), or 'all' for the whole pass",
    )
    parser.add_argument(
        "--all-families",
        action="store_true",
        help="Run one fresh-process batch per R5 rule family and emit a "
        "combined per-family report",
    )
    args = parser.parse_args()

    N = args.samples
    if N < 12:
        print(
            f"WARNING: N={N} is below the reportable floor of 12. Proceeding anyway.",
            file=sys.stderr,
        )

    binary = args.binary
    if not Path(binary).exists():
        print(f"ERROR: binary not found: {binary}", file=sys.stderr)
        return 1

    board_json = args.board
    if not Path(board_json).exists():
        print(f"ERROR: board JSON not found: {board_json}", file=sys.stderr)
        return 1

    # ── Aggregate ──────────────────────────────────────────────────────
    ISOLATE_LIMIT = 134_217_728  # 128 MiB

    def run_batch(family: str) -> tuple[list[dict], dict]:
        print(
            f"Running {N} fresh processes of {binary} (family={family}) ...",
            file=sys.stderr,
        )
        samples: list[dict] = []
        for i in range(N):
            sample = run_one(binary, board_json, family)
            samples.append(sample)
            print(
                f"  [{i+1:2d}/{N}]  family={family:<10}  "
                f"wall={sample['wall_ns']/1e6:.1f}ms  "
                f"RSS={sample['rss_bytes']:,} bytes  "
                f"errors={sample['violations_error']}",
                file=sys.stderr,
            )
        return samples, aggregate(samples)

    if args.all_families:
        per_family: dict[str, dict] = {}
        for fam in RULE_FAMILIES:
            _samples, agg = run_batch(fam)
            rss = agg["rss_bytes"]
            per_family[fam] = {
                "rules_run": agg["rules_run"],
                "wall_ns_median": agg["wall_ns"]["median"],
                "rss_bytes_median": rss["median"],
                "rss_bytes_range": [rss["min"], rss["max"]],
                "pct_of_limit_median": round(rss["median"] / ISOLATE_LIMIT * 100.0, 2),
                "violations_errors_median": agg["violations"]["errors_median"],
            }
        report = {
            "subject": "pcb/temper.kicad_pcb",
            "mode": "all-families",
            "samples_per_family": N,
            "isolate_limit": ISOLATE_LIMIT,
            "families": per_family,
        }
        print(json.dumps(report, indent=2))
        return 0

    family = args.family
    samples, agg = run_batch(family)

    rss_max = agg["rss_bytes"]["max"]
    rss_verdict = "PASS" if rss_max <= ISOLATE_LIMIT else "FAIL"
    pct_of_limit = rss_max / ISOLATE_LIMIT * 100.0

    # Per-family aggregation (by the rules' reported category, whole pass)
    families: dict[str, list[float]] = {}
    for rs in agg["per_rule"]:
        cat = rs["category"]
        families.setdefault(cat, []).append(rs["median_ns"])

    report = {
        "subject": "pcb/temper.kicad_pcb",
        "family": family,
        "samples": N,
        "wall_ns": agg["wall_ns"],
        "rss_bytes": {
            **agg["rss_bytes"],
            "isolate_limit": ISOLATE_LIMIT,
            "verdict": rss_verdict,
            "pct_of_limit": round(pct_of_limit, 1),
        },
        "violations": agg["violations"],
        "per_family_ns": {
            cat: {
                "median": statistics.median(vals),
                "min": min(vals),
                "max": max(vals),
            }
            for cat, vals in families.items()
        },
        "per_rule": agg["per_rule"],
    }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
