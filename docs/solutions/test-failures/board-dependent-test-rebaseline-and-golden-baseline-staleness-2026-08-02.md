---
title: "Board-dependent test expectations go stale under board-changing PRs — re-baseline fail-closed in the same PR, and classify CI failures by running them on main first"
date: 2026-08-02
category: test-failures
module: temper-placer
problem_type: stale_expectation
component: ci
severity: medium
applies_when:
  - "A test asserts a number derived from the committed board (violation counts, blocker sets, measured distances) and a PR legitimately changes the board"
  - "A PR branch predates a baseline re-measurement commit on main, and a golden/regression check compares the branch's output against the stale baseline"
  - "CI shows a red job and the question is whether the branch introduced it or main is already red"
  - "A test contains an unguarded all()/any() over a collection that is legitimately empty in the passing state"
symptoms:
  - "Three pre-existing failures on origin/main: test_temper_board_clearance_compliance asserted 0 violations while the documented state is 3/1 all K3-intra; test_the_seven_known_intra_footprint_blockers_are_now_visible asserted K2 was still blocking after PR #524 swapped it to RT314012 (intra cleared); test_checker_copper_distance_is_lower_bound_on_origin_distance encoded a pre-#517 board with 123 inter violations under the PD3/12.6 counterfactual"
  - "Golden Regression Check on a gap-2 PR branch reported drc_errors 1043 vs baseline 1039 (+4) — the branch predated #582's baseline re-measurement; main's own pre-#582 run failed identically, post-#582 main was green"
  - "A vacuity gate flagged all() over the intentionally-empty run-B audit result as vacuously True"
root_cause: stale_expectation
resolution_type: rebaseline
tags:
  - rebaseline
  - board-dependent-tests
  - golden-baseline
  - ci-classification
---

# Board-dependent test expectations: re-baseline fail-closed in the same PR

## The rule

The DRC ceiling already has this rule (`drc_ceiling.json` must be re-measured in
the same PR that touches `pcb/`). Board-dependent **test assertions** are the
same class of artifact: a PR that changes the board must update them in the same
commit, with measured numbers and a reference to the evidence. Leaving them red
on main is how "pre-existing failure" sets accumulate — this session found three
at once, all encoding boards that no longer exist.

## The fail-closed re-baseline pattern (not assertion-weakening)

For each stale assertion:

1. **Reproduce** and confirm the failure message matches the documented cause —
   a mismatch between message and cause is the real-bug signal (R22).
2. **Assert the exact documented reality**: the K3-intra finding is asserted as
   3 records / 1 pair / all `ref_a == ref_b == "K3"`, measured 3.558846mm
   (pytest.approx abs=1e-3), with the (metric, insulation, bar) rows pinned to
   `{(creepage,basic,4.0), (clearance,reinforced,6.0), (creepage,reinforced,8.0)}`
   and `geometry_model == "copper"`.
3. **Assert the invariant direction separately**: `inter == 0` — any *new*
   inter-component violation fails, even though the total is no longer zero.
4. **Injection-verify fail-closedness**: park an LV ref 0.05–0.5mm from K3's HV
   pad and confirm the new assertions catch it (both the inter==0 assert and the
   checker-bound assert fired in testing).
5. **Pin absences too**: K2 asserted *absent* from the blocker set (RT314012
   swap, 12.76mm internal gap, PR #524), so a regression re-adding it fails.
6. Cite the evidence doc + issue in the assertion comments.

The same pattern applied to the checker-invariant test: `assert not inter` plus
the sound bound (`copper ≥ origin − reach`) asserted on **every** measured pair
(114 survivors of the checker's own prune), plus a copper-model-only assertion —
strictly stronger than the old violating-pairs-only sample, non-vacuous on a
clean board.

## Classifying CI failures: run them on main first

Before touching a red job, check whether main is red on the same job. This
session: Requirements Tests and Board & Netlist Gates failed on main's own latest
run; Type Check and the vacuity gate failed only on the branch (both were real
new violations — the branch fixed them); Golden Regression failed on the branch
and on main's pre-#582 run but passed post-#582 — a **baseline staleness** that a
rebase onto current main fixes, not a regression. The three cases need three
different responses: ignore-and-track, fix, and rebase.

## The vacuous-aggregation gate is a friend

`all()`/`any()` over a collection that is legitimately empty is vacuously True —
and "legitimately empty" is exactly the run-B case (the audit returned 0
violations, which was the lie). The anti-vacuity gate caught
`_runb_reproduction_measurement.py:97`; the fix preserves the semantics (an
explicit `len(...) == 0` check) while removing the vacuity. When a measurement's
passing state is an empty collection, write the emptiness check explicitly.

## Evidence

- `docs/evidence/2026-08-01-safety-test-rebaseline.md` — the two test
  re-baselines (108 passed ×3, injection-verified).
- `docs/evidence/2026-08-02-checker-lower-bound-rebaseline.md` — the checker
  triage: stale expectation (category a), invariant sound everywhere (0 of 11,571
  inter pairs below the bound).
- `docs/evidence/2026-08-01-validator-aligned-solve-audit.md` — the golden
  staleness root cause (branch predated #582).
