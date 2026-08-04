# Wave-4 Slice Delegation Perf A/B Carve-Out — Evidence Record

**Date:** 2026-08-04
**Plan:** `docs/plans/2026-08-03-003-feat-wave4-phase3-first-pulls-plan.md` (KTD9)
**Branch:** `w4/phase3-first-pulls`

## The carve-out

Pull 1 (netclass/loop loaders) and pull 2 (board/netlist contracts) migrate
pure-delegation surfaces. Per program R2, pure-delegation modules carry the
"no regression beyond noise" perf A/B instead of a speedup claim. This record
states that basis and its trigger condition.

## Noise floor (landed evidence, adopted)

Measured in `docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md` and
cited by the margin comments in `scripts/pr_perf_compare.py`:

- CI wall-clock deltas (n=19 main-branch runs, the gate's own rolling
  arithmetic): sd 4.6%, worst excursion 9.9%; a genuine regression in the
  same series measured +50.7%.
- `perf_ab` ratio metric (n=20 fresh processes): worst excursion 7.72%.

Margins (TIMING_MARGIN 0.20, COMPLETION_MARGIN 0.10, IMPROVEMENT_THRESHOLD
0.10) sit above the measured floor and are not re-tuned by this slice.

## What the slice's perf A/B measures

The landed harness (`benchmarks/perf_ab.py`, dual-arm ratio) runs unchanged on
every PR touching `packages/**`. The migrated surfaces (loaders, delegation
shims) contain no hot loops; their differential suites (behavioral A/B) are
the parity gate. The gate's own noise-floor math above is the calibration the
differential's float bit-parity would surface against if delegation overhead
existed — it cannot, by construction: the shims call the same Rust pyclasses
the previous Python code computed with, and the differential asserts
bit-identical output.

## Trigger condition for extending benchmarks/perf_ab.py

If either pull's differential or CI wall-clock series shows overhead beyond
the measured floor (worst excursion 9.9%) attributable to the migration, the
same PR extends `benchmarks/perf_ab.py` to cover the migrated surface. This
record is the trigger's written threshold; absence of a signal is not a
waiver of the R1b obligation, it is the recorded carve-out basis.

## R6 governance note (required-status-check arm)

The required-status-check arm of program R2 remains blocked-by-governance:
`main` has no branch-protection required status checks (AGENTS.md, verified
2026-07-30). The workflow-level hard gate is live; the required-check
mechanism waits on a repo-governance decision outside this plan.
