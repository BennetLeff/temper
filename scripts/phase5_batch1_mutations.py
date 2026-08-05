#!/usr/bin/env python3
"""Phase-5 Batch-1 mutation campaign driver (grid_utils + via_placement).

For each mutation: apply a one-line edit to the Rust kernel source, rebuild
the temper-geometry extension, run the four Batch-1 suites, expect FAILURE,
then revert. A mutation that does NOT fail the differential is a survivor —
the campaign either closes it with a discriminating case or records it.

Usage: python3 scripts/phase5_batch1_mutations.py  (run from repo root)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path("/private/tmp/wt5-deterministic")
CARGO = ROOT / "packages/temper-geometry/Cargo.toml"
PLACER = ROOT / "packages/temper-placer"
SUITES = [
    "tests/deterministic/test_grid_utils_rust_differential.py",
    "tests/deterministic/test_via_placement_rust_differential.py",
    "tests/deterministic/test_grid_utils_pbt.py",
    "tests/deterministic/test_via_placement_pbt.py",
]


def run(cmd, cwd=ROOT, timeout=1800):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def rebuild():
    r = subprocess.run(
        ["uv", "run", "--no-sync", "maturin", "develop", "--release",
         "--manifest-path", str(CARGO)],
        cwd=ROOT, capture_output=True, text=True, timeout=1800,
    )
    if r.returncode != 0:
        raise RuntimeError(f"rebuild failed: {r.stdout + r.stderr}"[-2000:])


def run_suites():
    code, out = run(
        ["uv", "run", "--no-sync", "python", "-m", "pytest"] + SUITES
        + ["-p", "no:cacheprovider", "-q", "--tb=line", "--maxfail=5"],
        cwd=PLACER,
    )
    return code, out


MUTATIONS = [
    # (label, file, old, new, expected-to-fail)
    (
        "M1 snap: f64::round (half-away) instead of round-ties-even",
        "packages/temper-geometry/src/host_math.rs",
        "let r = x.round_ties_even();",
        "let r = x.round();",
    ),
    (
        "M2 snap: drop the -0.0 -> +0.0 normalisation",
        "packages/temper-geometry/src/host_math.rs",
        """    let r = x.round_ties_even();
    if r == 0.0 {
        0.0
    } else {
        r
    }""",
        "x.round_ties_even()",
    ),
    (
        "M3 snap: no rounding at all (rx * gs)",
        "packages/temper-geometry/src/grid_utils.rs",
        "Ok((py_round(rx) * grid_size, py_round(ry) * grid_size))",
        "Ok((rx * grid_size, ry * grid_size))",
    ),
    (
        "M4 nudge: threshold >= instead of >",
        "packages/temper-geometry/src/grid_utils.rs",
        "    if dist_start > 1e-4 {",
        "    if dist_start >= 1e-4 {",
    ),
    (
        "M5 nudge: always append the end nudge",
        "packages/temper-geometry/src/grid_utils.rs",
        "    if dist_end > 1e-4 {\n        result.push(actual_end_x);\n        result.push(actual_end_y);\n    }",
        "    result.push(actual_end_x);\n    result.push(actual_end_y);",
    ),
    (
        "M6 distance: x*x instead of pow(x, 2.0)",
        "packages/temper-geometry/src/via_placement.rs",
        "    pow(pow(dx, 2.0) + pow(dy, 2.0), 0.5)",
        "    pow(dx * dx + dy * dy, 0.5)",
    ),
    (
        "M7 is_via_position_valid: <= instead of <",
        "packages/temper-geometry/src/via_placement.rs",
        "        if distance(pos_x, pos_y, pad_x, pad_y) < required_distance {",
        "        if distance(pos_x, pos_y, pad_x, pad_y) <= required_distance {",
    ),
    (
        "M8 place_via_with_clearance: drop the target-valid short-circuit",
        "packages/temper-geometry/src/via_placement.rs",
        """    // 1. Check if target position is already valid.
    if is_via_position_valid(target_x, target_y, pads, via_mask_radius, min_clearance) {
        return Some((target_x, target_y));
    }""",
        "",
    ),
    (
        "M9 place_via_with_clearance: >= instead of > for max_search_radius",
        "packages/temper-geometry/src/via_placement.rs",
        "        if r > max_search_radius {",
        "        if r >= max_search_radius {",
    ),
]


def main() -> int:
    results = []
    for label, rel, old, new in MUTATIONS:
        path = ROOT / rel
        src = path.read_text()
        assert old in src, f"{label}: anchor not found in {rel}"
        src2 = src.replace(old, new, 1)
        assert src2 != src, f"{label}: replace was a no-op"
        path.write_text(src2)
        try:
            rebuild()
            code, out = run_suites()
        except RuntimeError as exc:
            code, out = 2, str(exc)
        finally:
            path.write_text(src)  # revert
        killed = code != 0
        results.append((label, killed, out))
        print(f"{'KILLED' if killed else 'SURVIVED'}: {label}")
        if not killed:
            print(out[-1500:])
    print("\n=== SUMMARY ===")
    for label, killed, _ in results:
        print(f"{'PASS(killed)' if killed else 'SURVIVED'}: {label}")
    return 0 if all(k for _, k, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
