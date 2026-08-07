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


def run_one(binary: str, board_json: str) -> dict:
    """Run one fresh process and return its parsed --summary JSON output."""
    result = subprocess.run(
        [binary, board_json, "--summary"],
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
        help="Number of fresh processes (default: 32, floor: 12)",
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

    print(f"Running {N} fresh processes of {binary} ...", file=sys.stderr)

    samples: list[dict] = []
    for i in range(N):
        sample = run_one(binary, board_json)
        samples.append(sample)
        print(
            f"  [{i+1:2d}/{N}]  wall={sample['wall_ns']/1e6:.1f}ms  "
            f"RSS={sample['rss_bytes']:,} bytes  "
            f"errors={sample['violations_error']}",
            file=sys.stderr,
        )

    # ── Aggregate ──────────────────────────────────────────────────────
    wall_list = [s["wall_ns"] for s in samples]
    rss_list = [s["rss_bytes"] for s in samples]
    error_list = [s["violations_error"] for s in samples]

    wall_median = statistics.median(wall_list)
    wall_min = min(wall_list)
    wall_max = max(wall_list)

    rss_median = int(statistics.median(rss_list))
    rss_min = min(rss_list)
    rss_max = max(rss_list)

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

    # Per-family aggregation
    families: dict[str, list[float]] = {}
    for rs in rule_stats:
        cat = rs["category"]
        families.setdefault(cat, []).append(rs["median_ns"])

    # ── Verdict ────────────────────────────────────────────────────────
    ISOLATE_LIMIT = 134_217_728  # 128 MiB
    rss_verdict = "PASS" if rss_max <= ISOLATE_LIMIT else "FAIL"
    pct_of_limit = rss_max / ISOLATE_LIMIT * 100.0

    # ── Output ─────────────────────────────────────────────────────────
    report = {
        "subject": "pcb/temper.kicad_pcb",
        "samples": N,
        "wall_ns": {
            "median": wall_median,
            "min": wall_min,
            "max": wall_max,
        },
        "rss_bytes": {
            "median": rss_median,
            "min": rss_min,
            "max": rss_max,
            "unit": samples[0]["rss_unit"],
            "isolate_limit": ISOLATE_LIMIT,
            "verdict": rss_verdict,
            "pct_of_limit": round(pct_of_limit, 1),
        },
        "violations": {
            "errors_median": int(statistics.median(error_list)),
            "errors_range": [min(error_list), max(error_list)],
        },
        "per_family_ns": {
            cat: {
                "median": statistics.median(vals),
                "min": min(vals),
                "max": max(vals),
            }
            for cat, vals in families.items()
        },
        "per_rule": rule_stats,
    }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
