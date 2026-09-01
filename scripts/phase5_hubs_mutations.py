#!/usr/bin/env python3
"""Phase-5 deterministic-hubs mutation campaign driver.

For each mutation: apply a one-line edit to the Rust kernel source, rebuild
the temper-design-bundle extension, run the six hubs suites, expect FAILURE,
then revert. A mutation that does NOT fail the differential is a survivor —
the campaign either closes it with a discriminating case or records it
(provable-equivalent mutants are recorded, per the phase guide's precedent).

Usage: python3 scripts/phase5_hubs_mutations.py  (run from repo root)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path("/private/tmp/wt5-hubs")
CARGO = ROOT / "packages/temper-design-bundle/Cargo.toml"
PLACER = ROOT / "packages/temper-placer"
RS = ROOT / "packages/temper-design-bundle/src/deterministic_hubs.rs"
SUITES = [
    "tests/deterministic/test_channels_rust_differential.py",
    "tests/deterministic/test_bottleneck_map_rust_differential.py",
    "tests/deterministic/test_seed_filter_rust_differential.py",
    "tests/deterministic/test_violation_mapper_rust_differential.py",
    "tests/deterministic/test_zone_adjuster_rust_differential.py",
    "tests/deterministic/test_drc_parser_rust_differential.py",
    "tests/deterministic/test_channels_pbt.py",
    "tests/deterministic/test_violation_mapper_pbt.py",
    "tests/deterministic/test_zone_adjuster_pbt.py",
    "tests/deterministic/test_drc_parser_pbt.py",
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
        + ["-p", "no:cacheprovider", "-q", "--tb=line", "--maxfail=4"],
        cwd=PLACER,
    )
    return code, out


MUTATIONS = [
    # (label, old, new, expected-to-fail)
    (
        "M1 py_floor_div: drop the fmod subtraction (div = a / b)",
        "    let mut div = (a - m) / b;",
        "    let mut div = a / b;\n    let _ = m;",
        True,
    ),
    (
        "M2 py_floor_div: drop the > 0.5 snap-to-integer correction",
        """        if div - floordiv > 0.5 {
            floordiv + 1.0
        } else {
            floordiv
        }""",
        "        floordiv",
        True,
    ),
    (
        "M3 channels penalty: LOW weight 0.05 -> 0.1",
        "Severity::Low => 0.05,",
        "Severity::Low => 0.1,",
        True,
    ),
    (
        "M4 channels penalty: off-by-one upper bound (gx > width instead of >=",
        "if gx < 0 || gx >= self.width || gy < 0 || gy >= self.height {",
        "if gx < 0 || gx > self.width || gy < 0 || gy > self.height {",
        True,
    ),
    (
        "M5 bottleneck_score_at: drop the non-finite guard (as i64 saturates)",
        """        if !qx.is_finite() || !qy.is_finite() {
            // Python: `int(rel_x // cell_size)` raises OverflowError with the
            // exact "infinity"/"NaN" message; replicate rather than silently
            // saturating the `as i64` cast.
            return Err(float_to_int_overflow(if !qx.is_finite() { qx } else { qy }));
        }
        let col = qx as i64;""",
        "        let col = qx as i64;",
        True,
    ),
    (
        "M6 seed_filter: score >= limit -> score > limit (equality accepts)",
        "            if score >= limit {",
        "            if score > limit {",
        True,
    ),
    (
        "M7 zone_adjuster: excess = count - threshold (off-by-one)",
        "            let excess = count - violation_threshold + 1;",
        "            let excess = count - violation_threshold;",
        True,
    ),
    (
        "M8 violation_mapper: components sorted ascending -> sorted descending",
        """        Ok((
            components.into_iter().collect(),
            zone,""",
        """        Ok((
            components.into_iter().rev().collect(),
            zone,""",
        True,
    ),
    (
        "M9 drc_parser: try TDD pattern 1 BEFORE the KiCad pattern 2",
        """        if let Some(caps) = clearance_regex(0).captures(&desc_str)
            && let (Some(r), Some(a)) = (caps.get(1), caps.get(2))
        {
            required = Some(parse_float_group(py, r.as_str())?);
            actual = Some(parse_float_group(py, a.as_str())?);
        } else if let Some(caps) = clearance_regex(1).captures(&desc_str)""",
        """        if let Some(caps) = clearance_regex(1).captures(&desc_str)
            && let (Some(a), Some(r)) = (caps.get(1), caps.get(2))
        {
            actual = Some(parse_float_group(py, a.as_str())?);
            required = Some(parse_float_group(py, r.as_str())?);
        } else if let Some(caps) = clearance_regex(0).captures(&desc_str)""",
        True,
    ),
    (
        "M10 channels penalty: drop the non-finite guard (NaN -> cell 0,0)",
        """        if !qx.is_finite() || !qy.is_finite() {
            // Python: math.floor(nan) raises ValueError, math.floor(inf) raises
            // OverflowError — replicate rather than letting `as i64` saturate
            // (NaN would silently land in cell (0, 0)).
            return Err(float_to_int_overflow(if !qx.is_finite() { qx } else { qy }));
        }
        let gx = qx.floor() as i64;""",
        "        let gx = qx.floor() as i64;",
        True,
    ),
    (
        "M11 channels index build: tie-break score > -> score >= (kept score)",
        "            if new_w > existing_w || (new_w == existing_w && score > entry.1) {",
        "            if new_w > existing_w || (new_w == existing_w && score >= entry.1) {",
        False,  # provable equivalent: penalty reads only the kept severity
    ),
]


def apply(patch, pristine: str):
    text = RS.read_text()
    (old, new) = (patch[1], patch[2])
    if old not in text:
        raise RuntimeError(f"mutation anchor not found: {patch[0]!r}")
    if text.count(old) != 1:
        raise RuntimeError(f"mutation anchor ambiguous ({text.count(old)} hits): {patch[0]!r}")
    RS.write_text(text.replace(old, new, 1))


def revert(pristine: str):
    RS.write_text(pristine)


def main():
    if not RS.is_file():
        print(f"deterministic_hubs.rs not found at {RS}", file=sys.stderr)
        return 2
    pristine = RS.read_text()  # working-tree state (my NaN-fidelity fixes included)
    results = []
    for (label, _old, _new, expected) in MUTATIONS:
        apply((label, _old, _new, expected), pristine)
        rebuild()
        code, out = run_suites()
        caught = code != 0
        status = "CAUGHT" if caught else "SURVIVED"
        verdict = "as expected" if caught == expected else "UNEXPECTED"
        results.append((label, status, verdict))
        print(f"[{status}] {label} ({verdict})", file=sys.stderr)
        if not caught:
            tail = out.strip().splitlines()[-6:]
            print("    suite tail:", " | ".join(tail), file=sys.stderr)
        revert(pristine)
    rebuild()
    code, out = run_suites()
    if code != 0:
        print("FATAL: suites still failing after reverting every mutation", file=sys.stderr)
        print(out[-2000:], file=sys.stderr)
        return 1
    print("---", file=sys.stderr)
    for (label, status, verdict) in results:
        print(f"{status:8s} {verdict:12s} {label}", file=sys.stderr)
    n_caught = sum(1 for _l, s, _v in results if s == "CAUGHT")
    print(f"{n_caught}/{len(results)} mutations caught; tree restored to green", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
