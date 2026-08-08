#!/usr/bin/env python3
"""Measure Pumpkin's real time-to-optimum on the one objective-bearing
corpus (`medium`, 12 components, real ``minimize_displacement_to``
objective) for ``docs/evidence/2026-08-07-cpsat-objective-frequency.md``.

# provenance: commit=<filled in at run time, see the doc's Sec 3>

The 2026-08-07 Pumpkin differential
(``docs/evidence/2026-08-07-pumpkin-engine-differential.md`` Sec 3/6)
established two points: FAIL at 5s (feasible, not proven optimal, spread
23926) and PASS at a 60s probe (reaches the exact proven optimum 2220,
independently verified). This script fills in the curve between those two
points -- not just pass/fail at the endpoints -- by re-solving the SAME
`medium` corpus at a sweep of timeouts and recording the returned objective
value and status at each one, across the harness's own seed list.

This imports the existing harness + Pumpkin-engine modules UNCHANGED (same
discipline as ``2026-08-07-pumpkin-equivalence-run.py``): no new solver
code, no change to the model encoding, only a different sequence of
``PumpkinEngine.solve()`` calls.

Usage:
    (cd docs/evidence/2026-08-07-pumpkin-engine && cargo build --release)
    cd packages/temper-placer
    uv run --no-sync python ../../docs/evidence/2026-08-07-pumpkin-time-to-optimum.py

Writes ``docs/evidence/2026-08-07-pumpkin-time-to-optimum-summary.json``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = Path(__file__).resolve().parent / "2026-08-07-cpsat-equivalence-harness.py"
RUN_PATH = Path(__file__).resolve().parent / "2026-08-07-pumpkin-equivalence-run.py"

spec = importlib.util.spec_from_file_location("cpsat_equivalence_harness", HARNESS_PATH)
assert spec is not None and spec.loader is not None
harness = importlib.util.module_from_spec(spec)
sys.modules["cpsat_equivalence_harness"] = harness
sys.path.insert(0, str(HARNESS_PATH.parent))
spec.loader.exec_module(harness)

run_spec = importlib.util.spec_from_file_location("pumpkin_equivalence_run", RUN_PATH)
assert run_spec is not None and run_spec.loader is not None
pumpkin_run = importlib.util.module_from_spec(run_spec)
sys.modules["pumpkin_equivalence_run"] = pumpkin_run
run_spec.loader.exec_module(pumpkin_run)

PLACER_SRC = REPO_ROOT / "packages" / "temper-placer" / "src"
if str(PLACER_SRC) not in sys.path:
    sys.path.insert(0, str(PLACER_SRC))

# The proven optimum on `medium`, established by OR-Tools 18/18 runs in the
# 2026-08-07 equivalence harness self-differential (objective=2220 units on
# every run, spread 0.0) and independently reconfirmed by Pumpkin's own 60s
# probe in the Pumpkin differential doc Sec 3.
KNOWN_OPTIMUM = 2220.0

# Sweep from below the 5s FAIL point to above the 60s PASS point, geometric
# spacing so the curve's shape (a cliff vs. a gradual approach) is visible,
# not just two endpoints.
TIMEOUTS_MS = [2_000, 5_000, 8_000, 12_000, 18_000, 25_000, 35_000, 50_000, 65_000]
SEEDS = [0, 1, 7]  # the harness's own seed list


def main() -> None:
    # NOTE: this worktree's cargo config redirects all crates' build output
    # to a shared `target-shared/` directory at the repo root (not each
    # crate's own `target/`) -- `pumpkin_equivalence_run.py`'s hardcoded
    # `PUMPKIN_BIN` default assumes the per-crate path, so it is overridden
    # here rather than editing that file.
    binary = REPO_ROOT / "target-shared" / "release" / "pumpkin_engine"
    engine = pumpkin_run.PumpkinEngine(binary=binary)
    medium = harness.build_medium_corpus()
    print(f"=== medium corpus: {len(medium.verification_model.sizes_mm)} components, "
          f"{len(medium.verification_model.constraints)} constraints, "
          f"known optimum={KNOWN_OPTIMUM} ===")

    runs = []
    for timeout_ms in TIMEOUTS_MS:
        for seed in SEEDS:
            t0 = time.monotonic()
            outcome = engine.solve(medium, seed=seed, timeout_ms=timeout_ms, num_workers=1)
            wall_s = time.monotonic() - t0
            at_optimum = (
                outcome.status in ("optimal", "feasible")
                and abs(outcome.objective_value - KNOWN_OPTIMUM) < 1e-6
            )
            row = {
                "timeout_ms": timeout_ms,
                "seed": seed,
                "status": outcome.status,
                "objective_value": outcome.objective_value,
                "at_known_optimum": at_optimum,
                "solve_time_ms_reported": outcome.solve_time_ms,
                "wall_s_measured": round(wall_s, 3),
            }
            runs.append(row)
            print(
                f"  timeout={timeout_ms:>6}ms seed={seed} -> status={outcome.status:<10} "
                f"objective={outcome.objective_value:>10.1f} "
                f"at_optimum={at_optimum} wall={wall_s:.2f}s"
            )

    # Verify every claimed-optimum result independently, same discipline as
    # every other tier in this evidence chain -- do not accept "at_optimum"
    # on the objective-value match alone without also checking the returned
    # assignment is a genuine feasible point (IndependentVerifier).
    verifier = harness.IndependentVerifier()

    # Re-run once more per (timeout, seed) that claimed optimum, capturing
    # positions/rotations for verification (the loop above discarded them
    # to keep the row JSON small).
    verified_optimum_count = 0
    checked = 0
    for timeout_ms in TIMEOUTS_MS:
        for seed in SEEDS:
            matching = [r for r in runs if r["timeout_ms"] == timeout_ms and r["seed"] == seed]
            if not matching or not matching[0]["at_known_optimum"]:
                continue
            outcome = engine.solve(medium, seed=seed, timeout_ms=timeout_ms, num_workers=1)
            checked += 1
            result = verifier.verify(medium.verification_model, outcome.positions, outcome.rotations)
            if result.ok and abs(outcome.objective_value - KNOWN_OPTIMUM) < 1e-6:
                verified_optimum_count += 1
            else:
                print(f"    [VERIFY FAIL] timeout={timeout_ms} seed={seed} violations={result.violations}")

    # First timeout at which EVERY seed reaches the known optimum, and the
    # first timeout at which ANY seed does -- both are useful: the latter
    # is the best case, the former is what a fixed-budget caller could rely
    # on across the harness's own seed spread.
    by_timeout: dict[int, list[dict]] = {}
    for r in runs:
        by_timeout.setdefault(r["timeout_ms"], []).append(r)
    first_any = next((t for t in TIMEOUTS_MS if any(r["at_known_optimum"] for r in by_timeout[t])), None)
    first_all = next((t for t in TIMEOUTS_MS if all(r["at_known_optimum"] for r in by_timeout[t])), None)

    summary = {
        "provenance": {"commit": "<fill in>", "dirty": False},
        "known_optimum": KNOWN_OPTIMUM,
        "timeouts_ms": TIMEOUTS_MS,
        "seeds": SEEDS,
        "runs": runs,
        "first_timeout_ms_any_seed_at_optimum": first_any,
        "first_timeout_ms_all_seeds_at_optimum": first_all,
        "verification": {
            "checked": checked,
            "verified_optimum_count": verified_optimum_count,
        },
    }

    print(f"\nFirst timeout where ANY seed reaches {KNOWN_OPTIMUM}: {first_any} ms")
    print(f"First timeout where ALL seeds reach {KNOWN_OPTIMUM}: {first_all} ms")
    print(f"Independent verification of optimum claims: {verified_optimum_count}/{checked} PASS")

    out_path = Path(__file__).resolve().parent / "2026-08-07-pumpkin-time-to-optimum-summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
