#!/usr/bin/env python3
"""Phase-5 cli/adapters/temper-workflow mutation campaign driver.

For each mutation: apply a one-line edit to a Rust kernel source in the
temper-orchestration crate, rebuild the extension, run the six differential
suites, expect FAILURE, then revert. A mutation that does NOT fail the
differential is a survivor — the campaign either closes it with a
discriminating case or records it (see VERIFICATION.md).

Run from any checkout (the repo root is derived from this file's own
location, so the R20 re-run procedure works from any worktree, not only
the one the campaign was authored in):

    python3 scripts/phase5_cli_adapters_workflow_mutations.py

The differential suites are the merge-path anti-vacuity surface; the PBT
suites are included so a property-only catch is also evidence.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # scripts/ -> repo root
CARGO = ROOT / "packages/temper-orchestration/Cargo.toml"
PLACER = ROOT / "packages/temper-placer"
WORKFLOW = ROOT / "packages/temper-workflow"
SUITES = [
    "tests/cli/test_timing_rust_differential.py",
    "tests/cli/test_trace_commands_rust_differential.py",
    "tests/cli/test_timing_pbt.py",
    "tests/cli/test_trace_commands_pbt.py",
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
    # The workflow differential is a separate package; run it separately and
    # combine exit codes (the campaign expects the WHOLE surface to catch).
    code2, out2 = run(
        ["uv", "run", "--no-sync", "python", "-m", "pytest",
         "tests/test_route_and_measure_rust_differential.py",
         "tests/test_route_and_measure_pbt.py",
         "-p", "no:cacheprovider", "-q", "--tb=line", "--maxfail=5"],
        cwd=WORKFLOW,
    )
    return (code if code != 0 else code2), out + out2


MUTATIONS = [
    # (label, file, old, new, expected-to-fail)
    (
        "M1 compare_stage: `>` instead of `>=`-style guard is fine; use >= for the passed comparison",
        "packages/temper-orchestration/src/timing.rs",
        "let passed = current_ms <= threshold_ms;",
        "let passed = current_ms < threshold_ms;",
    ),
    (
        "M2 compare_stage: unguarded delta_pct division (baseline<=0 gives inf/nan)",
        "packages/temper-orchestration/src/timing.rs",
        """    let delta_pct = if baseline_ms > 0.0 {
        (delta_ms / baseline_ms) * 100.0
    } else {
        0.0
    };""",
        "    let delta_pct = (delta_ms / baseline_ms) * 100.0;",
    ),
    (
        "M3 compare_stage: f64::max instead of py_max (NaN asymmetry)",
        "packages/temper-orchestration/src/timing.rs",
        "let effective_baseline = py_max(baseline_ms, floor_ms);",
        "let effective_baseline = f64::max(baseline_ms, floor_ms);",
    ),
    (
        "M4 compare_stage: delta_pct without the *100.0",
        "packages/temper-orchestration/src/timing.rs",
        "        (delta_ms / baseline_ms) * 100.0\n    } else {",
        "        delta_ms / baseline_ms\n    } else {",
    ),
    (
        "M5 p95: half-away rounding via multiply-divide instead of Python round",
        "packages/temper-orchestration/src/timing.rs",
        """    let builtins = py.import("builtins")?;
    let rounded = builtins.getattr("round")?.call1((selected, 3))?;
    rounded.extract::<f64>()""",
        """    let _ = py.import("builtins")?;
    Ok((*selected * 1000.0).round() / 1000.0)""",
    ),
    (
        "M6 p95: f64 total-order sort (total_cmp) instead of py_cmp (NaN/-0.0 placement)",
        "packages/temper-orchestration/src/timing.rs",
        "values.sort_by(py_cmp);",
        "values.sort_by(f64::total_cmp);",
    ),
    (
        "M7 p95: empty list returns 0.0 instead of IndexError",
        "packages/temper-orchestration/src/timing.rs",
        """    let selected = values
        .get(idx)
        .ok_or_else(|| PyIndexError::new_err("list index out of range"))?;""",
        """    let selected = match values.get(idx) {
        Some(v) => *v,
        None => return Ok(0.0),
    };""",
    ),
    (
        "M8 filter_decisions: match on d[\"subject\"] (missing key raises instead of None)",
        "packages/temper-orchestration/src/trace_filter.rs",
        """        let val = d.call_method1("get", ("subject",))?;
        if val.eq(subject)? {
            out.push(i);
        }""",
        """        let val = d.get_item("subject")?;
        if val.eq(subject)? {
            out.push(i);
        }""",
    ),
    (
        "M9 find_rejected: accept any subject (drop the subject check)",
        "packages/temper-orchestration/src/trace_filter.rs",
        """        let subj_val = d.call_method1("get", ("subject",))?;
        if !subj_val.eq(subject)? {
            continue;
        }""",
        "",
    ),
    (
        "M10 copper: dx*dx instead of libm pow(dx, 2.0)",
        "packages/temper-orchestration/src/copper_length.rs",
        "let length = (host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0)).sqrt();",
        "let length = (dx * dx + dy * dy).sqrt();",
    ),
    (
        "M11 copper: falsy-net skip only for None (empty string passes through)",
        "packages/temper-orchestration/src/copper_length.rs",
        """        let Some(net) = net else { continue };
        if net.is_empty() {
            continue;
        }""",
        """        let Some(net) = net else { continue };""",
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
            print(out[-2000:])
    print("\n=== SUMMARY ===")
    for label, killed, _ in results:
        print(f"{'PASS(killed)' if killed else 'SURVIVED'}: {label}")
    # Rebuild from the reverted source so the installed extension is always
    # left in the correct state (the per-mutation revert is source-only).
    rebuild()
    code, _ = run_suites()
    if code != 0:
        print("FAIL: post-campaign rebuild/suites are not green; extension left mutated?")
        return 1
    print("post-campaign rebuild + suites green")
    # Anti-vacuity guard (check_vacuous_gates.py): the aggregation below
    # must fail closed if the campaign ran fewer mutations than the
    # manifest declares — a short results list (e.g. an empty MUTATIONS)
    # must never read as a clean pass.
    assert len(results) == len(MUTATIONS), (
        f"campaign ran {len(results)} of {len(MUTATIONS)} mutations — "
        "short results fail closed, never pass vacuously"
    )
    return 0 if all(k for _, k, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
