#!/usr/bin/env python3
"""Measure the router-output DRC constants where the gate is actually enforced.

`PRODUCTION_ROUTER_OUTPUT_*` in tests/placer/cp_sat/test_regression_drc.py is a
ratchet. Its provenance blocks record measurements taken on macOS arm64, but the
gate runs inside ghcr.io/bennetleff/temper-ci on ubuntu-latest -- and kicad-cli's
geometric counts are environment-dependent. Measuring in one environment and
enforcing in another is what made the gate red without anything regressing (see
docs/evidence/2026-08-04-router-output-rebaseline-interim.md).

This script exists so a re-baseline can be measured in the enforcing environment.
It asserts nothing and writes no constants -- it reports, and a human lands the
numbers with attribution per AGENTS.md's same-PR re-measurement rule.

Usage:
    python3 scripts/measure_router_output_baseline.py [--drc-runs 15] [--route-runs 2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages/temper-placer"))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages/temper-placer/tests"))


def kicad_version() -> str:
    try:
        out = subprocess.run(
            ["kicad-cli", "version"], capture_output=True, text=True, timeout=60
        )
        return out.stdout.strip() or out.stderr.strip() or "unknown"
    except Exception as exc:  # noqa: BLE001 - reporting tool, never fail on this
        return f"unavailable ({exc})"


def route_once() -> tuple[str, float]:
    from tests.conftest import make_parsed_pcb_stub
    from tests.placer.cp_sat.test_regression_drc import (
        PRODUCTION_BOARD_PATH,
        RULES_PATH,
    )

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.router_v6.adapter import route_pcb

    rules = load_netclass_rules(RULES_PATH)
    netlist = parse_kicad_pcb(PRODUCTION_BOARD_PATH).netlist
    stub = make_parsed_pcb_stub(PRODUCTION_BOARD_PATH, netlist)

    t0 = time.time()
    result = route_pcb(stub, {}, design_rules=rules.design_rules)
    elapsed = time.time() - t0
    if result.routed_pcb_content is None:
        raise SystemExit("routing produced no output")
    return result.routed_pcb_content, elapsed


def stats(xs: list[int]) -> dict[str, int]:
    return {
        "median": int(statistics.median(xs)),
        "min": min(xs),
        "max": max(xs),
        "spread": max(xs) - min(xs),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc-runs", type=int, default=15, help="N for the DRC sample (>=11)")
    ap.add_argument("--route-runs", type=int, default=2, help="fresh routes, to prove determinism")
    ap.add_argument("--json-out", default="", help="write the report as JSON here")
    args = ap.parse_args()

    from tests.placer.cp_sat._parallel_drc import run_drc_samples

    env = {
        "kicad_cli_version": kicad_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
    }
    print(f"environment: {env['platform']}, python {env['python']}")
    print(f"kicad-cli: {env['kicad_cli_version']}\n")

    hashes, times, content = [], [], None
    for i in range(args.route_runs):
        content, elapsed = route_once()
        hashes.append(hashlib.sha256(content.encode()).hexdigest())
        times.append(elapsed)
        print(f"  route {i + 1}/{args.route_runs}: {elapsed:6.1f}s  sha256={hashes[-1][:16]}")

    deterministic = len(set(hashes)) == 1
    print(f"  router output byte-identical: {deterministic}\n")

    tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False)
    tmp.write(content)
    tmp.close()
    try:
        samples = run_drc_samples(tmp.name, n=args.drc_runs, timeout=120, label="baseline")
    finally:
        os.unlink(tmp.name)

    totals, shorting, unconnected = [], [], []
    for d in samples:
        v = d.get("violations", [])
        totals.append(len(v))
        shorting.append(sum(1 for x in v if x.get("type") == "shorting_items"))
        unconnected.append(len(d.get("unconnected_items", [])))

    metrics = {
        "total": stats(totals),
        "shorting_items": stats(shorting),
        "unconnected_items": stats(unconnected),
    }
    report = {
        "environment": env,
        "router_deterministic": deterministic,
        "router_sha256": hashes[0],
        "route_seconds_median": round(statistics.median(times), 1),
        "drc_runs": args.drc_runs,
        "metrics": metrics,
        "raw": {"total": totals, "shorting_items": shorting, "unconnected_items": unconnected},
    }

    lines = [
        "## Router-output DRC measurement",
        "",
        f"- environment: `{env['platform']}`",
        f"- kicad-cli: `{env['kicad_cli_version']}`",
        f"- router output byte-identical over {args.route_runs} runs: **{deterministic}** "
        f"(`{hashes[0][:16]}`)",
        f"- DRC sample: N={args.drc_runs}",
        "",
        "| metric | median | min | max | spread |",
        "|---|---|---|---|---|",
    ]
    for name, m in metrics.items():
        lines.append(
            f"| `{name}` | **{m['median']}** | {m['min']} | {m['max']} | {m['spread']} |"
        )
    lines += [
        "",
        "These are measurements, not thresholds. Landing them as "
        "`PRODUCTION_ROUTER_OUTPUT_*` requires a provenance block naming this "
        "environment, per AGENTS.md.",
    ]
    body = "\n".join(lines)
    print("\n" + body)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(body + "\n")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
