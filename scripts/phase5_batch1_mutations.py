#!/usr/bin/env python3
"""Phase-5 Batch-1 mutation campaign driver (grid_utils + via_placement).

For each mutation: apply a one-line edit to the Rust kernel source, rebuild
the temper-geometry extension, run the four Batch-1 suites, expect FAILURE,
then revert. A mutation that does NOT fail the differential is a survivor —
the campaign either closes it with a discriminating case or records it.
After the last mutant the driver rebuilds from pristine source and re-runs
the suites, so the campaign ends bit-exact (the per-mutant revert alone
would leave the installed .so carrying the final mutant — the revert does
not recompile).

Only a SUITE FAILURE counts as a kill (pytest exit 1). Rebuild or pytest
infra failures (rebuild errors, timeouts, exit 2/3/4/5) are counted as
ERROR, not kills, and fail the driver — a spurious infra failure cannot
inflate the kill count.

Usage: python3 scripts/phase5_batch1_mutations.py  (run from repo root)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Resolve the repo root from this file's own location so the driver is
# reproducible from any checkout (not just the original worktree path).
ROOT = Path(__file__).resolve().parent.parent
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
EXPECTED: dict[str, str] = {label: "KILLED" for label, *_ in MUTATIONS}
EXPECTED["M6 distance: x*x instead of pow(x, 2.0)"] = "EQUIVALENT"


# `EXPECTED`'s values ("KILLED" / "EQUIVALENT") are a *verdict* vocabulary,
# distinct from the `status` a run actually produces ("SURVIVED" / "KILLED"
# / "ERROR"). An EQUIVALENT mutant is expected to SURVIVE (its behaviour
# change is not observable by the suites) -- the two vocabularies are not
# the same strings by coincidence, so a bare `status == expected[label]`
# can never match the EQUIVALENT case even when the run went exactly as
# designed.
_EXPECTED_VERDICT_TO_STATUS = {"KILLED": "KILLED", "EQUIVALENT": "SURVIVED"}


def campaign_passed(
    results: list[tuple[str, str, str]], expected: dict[str, str]
) -> bool:
    """True iff every mutation's outcome matches its ``expected`` verdict.

    Two independent fixes live here:

    1. ``assert results`` -- ``results`` accumulates exactly one entry per
       ``MUTATIONS`` row (the driving loop has no break/skip path), and
       ``MUTATIONS`` is a non-empty literal today, but ``all()`` over an
       empty collection is vacuously True. Without this guard, a future
       ``MUTATIONS = []`` edit (or any refactor that lets the loop run zero
       times) would make this function silently report a clean campaign
       with zero mutations actually tested -- exactly the failure class
       ``scripts/check_vacuous_gates.py`` exists to catch.
    2. Compared against ``expected`` (translated through
       ``_EXPECTED_VERDICT_TO_STATUS``), not a bare ``status == "KILLED"``:
       M6 is a documented EQUIVALENT mutant (see the ``EXPECTED`` override
       above) that the campaign does not expect to kill -- it expects it to
       SURVIVE. The previous ``all(s == "KILLED" for _, s, _ in results)``
       ignored ``EXPECTED`` entirely, so a fully-successful run (M6
       SURVIVED as designed, every other mutation KILLED) reported failure
       -- a real bug independent of the vacuous-``all()`` question, caught
       while fixing it.
    """
    assert results, "no mutations were run -- MUTATIONS is empty"
    return all(
        status == _EXPECTED_VERDICT_TO_STATUS[expected[label]]
        for label, status, _ in results
    )


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
            status, out = "ERROR", f"rebuild failed: {exc}"
        except subprocess.TimeoutExpired as exc:
            status, out = "ERROR", f"suite run timed out: {exc}"
        else:
            # pytest exit codes: 0 = all passed (SURVIVED), 1 = tests ran
            # and failed (KILL), 2/3/4/5 = interrupted / internal error /
            # usage error / no-tests-collected — infra failures, counted as
            # ERROR so a spurious rebuild/pytest failure cannot inflate the
            # kill count.
            if code == 0:
                status = "SURVIVED"
            elif code == 1:
                status = "KILLED"
            else:
                status = "ERROR"
                out = f"pytest infra failure (exit {code}): {out}"
        finally:
            path.write_text(src)  # revert
        results.append((label, status, out))
        print(f"{status}: {label}")
        if status != "KILLED":
            print(out[-1500:])
    print("\n=== SUMMARY ===")
    for label, status, _ in results:
        print(f"{status}: {label}")
    # The LAST mutation's rebuild happens while the mutant is still applied
    # (the revert in `finally` does not recompile), so the installed .so
    # still carries the final mutant afterwards. Rebuild from pristine
    # source and re-run the suites so the campaign ends bit-exact.
    rebuild()
    code, out = run_suites()
    print(f"PRISTINE REBUILD + SUITES: exit={code}")
    if code != 0:
        print(out[-2000:])
        return 1
    return 0 if campaign_passed(results, EXPECTED) else 1


if __name__ == "__main__":
    sys.exit(main())
