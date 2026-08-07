#!/usr/bin/env python3
"""R19 verdict comparison: wasm32 vs native ``cargo test --no-default-features``.

Produces the per-test pass/fail matrix at a named commit comparing the wasm32
run against the same commit's native ``cargo test`` output.

Usage:
    python3 tools/wasm/r19_compare.py \\
        --native-json /tmp/native_results.json \\
        --wasm-json /tmp/wasm_results.json \\
        --expected-failures tools/wasm/wasm_expected_failures.json \\
        --output /tmp/r19_baseline.json \\
        --commit <sha>

The native JSON can be produced by piping the text output of ``cargo test``
through the parser in this module. The wasm32 JSON is the output of
``node tools/wasm/run_wasm_tests.mjs --json ...``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def parse_native_output(lines: list[str]) -> list[dict[str, str]]:
    """Parse ``cargo test`` text output into per-test results.

    The native ``cargo test`` output looks like::

        test dfm::tests::calculate_angle_cardinal_values ... ok
        test pymath::tests::host_libm_symbols_actually_resolve ... ok

    We strip the leading ``test `` and map ``ok`` / ``FAILED`` to ``pass`` / ``fail``.
    """
    results: list[dict[str, str]] = []
    for line in lines:
        line = line.strip()
        # Lines have the form: test <name> ... <status>
        if not line.startswith("test "):
            continue
        parts = line[5:].rsplit(" ... ", 1)
        if len(parts) != 2:
            continue
        name, raw_status = parts
        name = name.strip()
        raw_status = raw_status.strip()
        if raw_status == "ok":
            status = "pass"
        elif raw_status.startswith("FAILED"):
            status = "fail"
        else:
            status = raw_status
        results.append({"name": name, "status": status})
    return results


def load_expected_failures(path: str) -> dict[str, dict[str, str]]:
    """Load the expected-failure manifest, returning the inner dict keyed by test name."""
    with open(path) as f:
        manifest = json.load(f)
    return manifest.get("expected_failures", {})


def run_comparison(
    native_results: list[dict[str, str]],
    wasm_results: list[dict[str, Any]],
    expected_failures: dict[str, dict[str, str]],
    commit_sha: str,
) -> dict[str, Any]:
    """Join native and wasm32 results on test name and produce the comparison matrix.

    Native names are prefixed with ``test `` (from ``cargo test`` output); we strip that.
    The wasm32 registry uses the bare module path (e.g., ``dfm::tests::foo``).
    Both are normalized by stripping whitespace and ensuring they match.
    """
    # Build lookup maps. Native values are status strings; wasm32 values are full
    # result objects from run_wasm_tests.mjs --json.
    native_map: dict[str, str] = {}
    for r in native_results:
        name = r["name"].strip()
        native_map[name] = r["status"]

    wasm_raw_map: dict[str, dict[str, Any]] = {}
    for r in wasm_results:
        name = r["name"]
        wasm_raw_map[name] = r

    native_names = set(native_map.keys())
    wasm_names = set(wasm_raw_map.keys())

    # Classify each test that appears in either set
    agree_pass: list[dict[str, str]] = []
    agree_fail: list[dict[str, str]] = []
    disagree: list[dict[str, Any]] = []
    expected_fail_list: list[dict[str, Any]] = []
    unexpected_pass_list: list[dict[str, Any]] = []
    native_only: list[dict[str, str]] = []
    wasm32_only: list[dict[str, Any]] = []
    in_both: list[str] = []

    for name in sorted(native_names | wasm_names):
        native_status = native_map.get(name)
        wasm_raw = wasm_raw_map.get(name)
        is_expected_fail = name in expected_failures

        if native_status is None:
            wasm32_only.append({"name": name, "wasm32_status": wasm_raw.get("status") if wasm_raw else None})
            continue
        if wasm_raw is None:
            native_only.append({"name": name, "native_status": native_status})
            continue

        in_both.append(name)
        # The .mjs already reclassifies manifest entries:
        #   fail -> expected-fail, pass -> unexpected-pass
        wasm_status = wasm_raw.get("status", "unknown")

        if is_expected_fail:
            if wasm_status == "expected-fail":
                expected_fail_list.append({
                    "name": name,
                    "native_status": native_status,
                    "wasm32_status": "expected-fail",
                    "expectedClass": expected_failures[name].get("class", ""),
                    "reason": expected_failures[name].get("reason", ""),
                })
            elif wasm_status == "unexpected-pass" or wasm_status == "pass":
                unexpected_pass_list.append({
                    "name": name,
                    "native_status": native_status,
                    "wasm32_status": wasm_status,
                    "expectedClass": expected_failures[name].get("class", ""),
                })
            else:
                # fail / bad-index / host-error — something went wrong and it's
                # not in the expected-fail bucket. Treat as disagreement.
                disagree.append({
                    "name": name,
                    "native_status": native_status,
                    "wasm32_status": wasm_status,
                })
            continue

        if native_status == "pass" and wasm_status == "pass":
            agree_pass.append({"name": name, "native_status": native_status, "wasm32_status": wasm_status})
        elif native_status == "fail" and wasm_status == "fail":
            agree_fail.append({"name": name, "native_status": native_status, "wasm32_status": wasm_status})
        else:
            disagree.append({
                "name": name,
                "native_status": native_status,
                "wasm32_status": wasm_status,
            })

    # Compute agreement rate per the plan's formula
    numerator = len(agree_pass) + len(agree_fail) + len(expected_fail_list)
    denominator = numerator + len(disagree) + len(unexpected_pass_list)
    agreement_rate = numerator / denominator if denominator > 0 else 1.0

    return {
        "commit": commit_sha,
        "timestamp": datetime.now(UTC).isoformat(),
        "native": {
            "total": len(native_map),
            "passed": sum(1 for v in native_map.values() if v == "pass"),
            "failed": sum(1 for v in native_map.values() if v == "fail"),
        },
        "wasm32": {
            "total": len(wasm_raw_map),
            "passed": sum(1 for r in wasm_results if r.get("status") == "pass"),
            "failed": sum(1 for r in wasm_results if r.get("status") == "fail"),
            "expected_fail": sum(1 for r in wasm_results if r.get("status") == "expected-fail"),
            "unexpected": sum(1 for r in wasm_results if r.get("status") == "unexpected-pass"),
        },
        "comparison": {
            "agree_pass": len(agree_pass),
            "agree_fail": len(agree_fail),
            "disagree": len(disagree),
            "expected_fail": len(expected_fail_list),
            "unexpected_pass": len(unexpected_pass_list),
            "native_only": len(native_only),
            "wasm32_only": len(wasm32_only),
            "total_in_both": len(in_both),
            "agreement_rate": round(agreement_rate, 6),
            "disagreements": disagree,
            "expected_fail_detail": expected_fail_list,
            "unexpected_pass_detail": unexpected_pass_list,
            "native_only_detail": native_only,
            "wasm32_only_detail": wasm32_only,
        },
        "expected_failure_manifest": "tools/wasm/wasm_expected_failures.json",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="R19 verdict comparison: wasm32 vs native cargo test")
    ap.add_argument("--native-json", help="JSON file with native test results")
    ap.add_argument("--native-file", help="Text file of `cargo test` output (or read from stdin)")
    ap.add_argument("--wasm-json", required=True, help="JSON file from run_wasm_tests.mjs --json")
    ap.add_argument("--expected-failures", required=True, help="Path to wasm_expected_failures.json")
    ap.add_argument("--output", "-o", required=True, help="Output JSON path for the comparison matrix")
    ap.add_argument("--commit", required=True, help="Git commit SHA")
    args = ap.parse_args()

    # Load native results
    native_results: list[dict[str, str]]
    if args.native_json:
        with open(args.native_json) as f:
            raw = json.load(f)
            if "native" in raw and "tests" in raw["native"]:
                native_results = raw["native"]["tests"]
            else:
                print("error: --native-json does not contain expected 'native.tests' key", file=sys.stderr)
                return 1
    elif args.native_file:
        with open(args.native_file) as f:
            native_results = parse_native_output(f.readlines())
    else:
        print("reading native test output from stdin (end with Ctrl+D)", file=sys.stderr)
        native_results = parse_native_output(sys.stdin.readlines())

    if not native_results:
        print("error: no native test results found", file=sys.stderr)
        return 1

    # Load wasm32 results
    with open(args.wasm_json) as f:
        wasm_data = json.load(f)
    wasm_results = wasm_data.get("results", [])

    # Load expected failures
    expected_failures = load_expected_failures(args.expected_failures)

    # Run comparison
    matrix = run_comparison(native_results, wasm_results, expected_failures, args.commit)

    with open(args.output, "w") as f:
        json.dump(matrix, f, indent=2)
        f.write("\n")

    # Summary to stdout
    c = matrix["comparison"]
    print(f"R19 Baseline at commit {matrix['commit']}")
    print(f"  Native  : {matrix['native']['passed']} pass, {matrix['native']['failed']} fail "
          f"({matrix['native']['total']} tests)")
    print(f"  WASM32  : {matrix['wasm32']['passed']} pass, {matrix['wasm32']['failed']} fail, "
          f"{matrix['wasm32']['expected_fail']} expected-fail, {matrix['wasm32']['unexpected']} unexpected")
    print(f"  Agree   : {c['agree_pass']} agree-pass, {c['agree_fail']} agree-fail, "
          f"{c['expected_fail']} expected-fail")
    print(f"  Disagree: {c['disagree']} disagreements")
    print(f"  Scope   : {c['native_only']} native-only, {c['wasm32_only']} wasm32-only")
    print(f"  Agreement rate: {c['agreement_rate']:.6f}")
    if c["disagree"]:
        print("  DISAGREEMENTS:")
        for d in c["disagreements"]:
            print(f"    {d['name']}: native={d['native_status']}, wasm32={d['wasm32_status']}")
    if c["unexpected_pass"]:
        print(f"  WARNING: {c['unexpected_pass']} unexpected pass(es)")

    matrix_path = Path(args.output)
    print(f"\nWrote {matrix_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
