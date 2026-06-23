---
date: 2026-06-23
type: addendum
amends: docs/brainstorms/2026-06-23-seed-filtering-requirements.md
topic: seed-filtering-by-channel-bottleneck-map
status: active
authors: doc-review pipeline (2026-06-23)
---

# Addendum: SC1 Acceptance Criteria Reframed

This addendum amends the Success Criteria section of
`docs/brainstorms/2026-06-23-seed-filtering-requirements.md` to make the
SC1 acceptance check explicit and machine-checkable.

## SC1 (Amended)

**SC1 acceptance: t-test with effect-size lower bound `d_min` when 10-run
stddev > 5pp; otherwise fixed-threshold comparison.**

Concretely, the 10 unfiltered baseline runs on `main` recorded in
`docs/solutions/measurements/seed-filter-baseline.md` produce
`mean_baseline` and `stddev_baseline` for `routing_completion_pct` on
the temper board. The plan-implementation runs (also 10, also on the
temper board, with `seed_filter_enabled=True`) produce
`mean_filtered` and `stddev_filtered`. SC1 is satisfied if **either**:

1. **Low-variance branch (stddev_baseline ≤ 5pp).**
   `mean_filtered - mean_baseline ≥ 10.0` percentage points.

2. **High-variance branch (stddev_baseline > 5pp).**
   Welch's one-sided t-test on the two samples yields
   `p < 0.05` **and** the lower bound of the 95% confidence interval on
   the effect size (Cohen's `d` with Hedges' correction) is
   `d_lower ≥ d_min`, where `d_min = 0.5` (a "medium" effect per
   Cohen's conventions). The CI for `d` is computed by noncentral-t
   approximation; a Python implementation is acceptable (e.g.
   `scipy.stats` + `pingouin.compute_effsize` or a hand-rolled
   noncentral-t loop).

## Why This Amendment

The original SC1 sentence (`"If baseline stddev > 5pp, SC1 is reframed as
a one-sided t-test with effect-size lower bound, not a fixed delta."`)
is condition-dependent but underspecified: it does not name the
statistical test, the alpha level, the effect-size metric, or the
`d_min` threshold. The implementation plan needed an unambiguous,
machine-checkable acceptance gate to wire into `tools/measurements/seed_filter_baseline.py`
and the `test_sc1_acceptance_against_baseline` closure test (plan U5d).
This addendum pins all four values.

## Disposition

- The original 10pp fixed-delta target is preserved for the low-variance
  branch (K1's intent is unchanged).
- The high-variance branch defers the magnitude question to effect-size,
  which is the standard statistical remedy for noisy metric comparisons
  in benchmark-style gates (cf. `docs/plans/*perf*-plan.md` precedent).
- `d_min = 0.5` matches the "medium effect" threshold commonly used in
  empirical software engineering; tighten to `0.8` ("large") if a later
  measurement shows 0.5 produces too many false positives on the temper
  board.
- Plan U5d's `test_sc1_acceptance_against_baseline` test loads the
  baseline JSON, dispatches to the correct branch by
  `stddev_baseline`, and asserts the corresponding condition.

## Cross-References

- Plan: `docs/plans/2026-06-23-004-feat-seed-filtering-plan.md`
- Original brainstorm: `docs/brainstorms/2026-06-23-seed-filtering-requirements.md`
  (SC1, line 115)
- Baseline file (produced by plan pre-step A):
  `docs/solutions/measurements/seed-filter-baseline.md`
