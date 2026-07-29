---
title: "Unmasking cascades are expected, not regression — fixing the top of a masking stack reveals the layer beneath it"
date: "2026-07-29"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - "a fix for a crash, collection error, or silent skip lets a test/gate run for the first time in a while and it immediately fails on something unrelated"
  - "deciding whether a newly-surfaced failure was caused by the current change or was already there, hidden"
  - "reviewing a PR that fixes one bug and reports finding a second, independent one 'while tracing'"
  - "a batch of same-day test-repair commits land together after a long CI-blocking failure is cleared"
tags:
  - unmasking-cascade
  - layered-masking
  - not-a-regression
  - expected-pattern
  - ci-rot
  - stale-baseline
---

# Unmasking cascades are expected, not regression

## Context

Two independent fixes landed within the same 24-hour window (2026-07-28 to
2026-07-29), and both produced the same shape: fixing the failure that was
actually reported immediately surfaced a *second*, previously-invisible
failure underneath it — not caused by the fix, but no longer hideable
behind it.

**PR #379.** `_UNRESOLVED_REF_POLICY` moved to `_encoder_core` without a
re-export, so `test_golden_board_drc_regression` died at collection with
`AttributeError` and had been measuring nothing. Fixing the live-binding
issue (see
`docs/solutions/logic-errors/import-time-binding-defeats-monkeypatch-2026-07-29.md`
for the full mechanism) let the gate actually run its classification logic
for the first time in a while, which exposed a second, independent defect
that logic had been hiding: `PLACEMENT_IRREDUCIBLE_TYPES` listed
`lib_footprint_issues` where the real violation type is
`lib_footprint_mismatch`, one character-class off, silently charging 32
library-drift violations against a placement budget the placer cannot
influence.

**PR #386.** `KeyError: 'F.Cu'` crashed every all-pad-tree route on the
production board (see
`docs/solutions/logic-errors/tree-router-layer-selection-must-intersect-grids-2026-07-29.md`).
Fixing it let the regression job proceed past the point where it used to
die, reaching `test_zone_pour_production_measurement` for the first time —
which immediately failed: `enable_zone_pours=True did not reduce
unconnected_items (395 >= 260)`. That failure was itself layered: the 260
baseline was stale (measured on a bare board six days out of date — see
`docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md`),
and the reason nobody had caught the staleness earlier was a *third* layer
underneath that: `_fill_zones_via_pcbnew` hardcoded `/usr/bin/python3`,
which exists on macOS but has no `pcbnew`, so the whole test family had
been silently skipping on every developer machine. **Three layers deep**:
a crash hid a stale-baseline test failure, which had itself been hidden
from ever running by a false-positive existence check.

A distinct, contemporaneous fifth data point that is emphatically **not**
a cascade, for contrast: PR #380 (`1f9d13d9`, merged 25 seconds after PR
#379) rewrote four `test_cp_sat_flag.py` tests asserting a `--placer`
option deliberately removed in `38092d65`. This is a stale test recurring,
not a cascade — the exact same pattern (a CLI option intentionally
retired, its tests never updated) that
`docs/solutions/test-failures/cli-cp-sat-tuning-flags-removed-stale-test.md`
already documented in the same file two weeks earlier, for
`--cp-sat-timeout`/`--cp-sat-workers`/`--cp-sat-grid-scale`. Nothing was
unmasked by fixing something else; a known failure shape simply recurred.
Distinguishing the two matters: a cascade needs its own root-cause trace,
while a recurrence just needs the existing playbook applied again.

## Guidance

1. **When a fix lets a previously-unreachable check run for the first
   time, expect it to fail on something unrelated — that is not evidence
   the fix is wrong.** Both PR #379 and PR #386 found a second bug
   immediately after the first was fixed. In neither case was the second
   bug caused by the fix; both had been sitting, unreachable, for as long
   as the first failure had been blocking the path to them.
2. **Trace each newly-surfaced failure to its own root cause before
   folding it into the original fix's scope or dismissing it as noise.**
   PR #379's `lib_footprint_mismatch` typo and PR #386's stale 260
   baseline are unrelated to the bugs that unmasked them and unrelated to
   each other — each got its own diagnosis rather than being absorbed into
   "well, the golden gate is flaky" or "zone/pour is just broken."
3. **Count the layers, don't stop at the first one revealed.** PR #386's
   cascade was three deep (crash → stale baseline → silent-skip existence
   check), and each layer was independently necessary to explain why the
   one above it had gone unnoticed. Stopping at "the baseline is stale"
   would have left the `/usr/bin/python3` false-positive in place to hide
   the *next* stale baseline the same way.
4. **Distinguish a cascade from a recurrence.** A cascade is a
   previously-unreachable failure becoming reachable. A recurrence (PR
   #380) is the same known failure shape happening again in a different
   spot. The fix for a recurrence is "apply the existing playbook"; the
   fix for a cascade requires a fresh root-cause trace, because by
   definition nothing already explains it.
5. **A batch of same-day test-repair commits is a signal, not a
   coincidence.** PR #379 and PR #380 merged 25 seconds apart, both test
   fixes in the CP-SAT/placer test suites. When several fixes land
   together after a long-blocked CI path clears, treat the batch as one
   excavation of accumulated drift rather than several unrelated
   coincidences — that framing is what makes it obvious to look for a
   *fourth* layer, not just stop at the first newly-visible one.

## Why This Matters

Mistaking an unmasking cascade for a regression caused by the fix leads to
exactly the wrong response: reverting or narrowing a correct fix to make a
newly-visible, pre-existing failure disappear again — which puts the
masking layer back. Both instances here resisted that: PR #379's
diagnosis explicitly separates "the re-export/live-read fix" from "the
`lib_footprint_mismatch` reclassification" as two independent changes with
two independent justifications, and PR #386's PR description labels its
zone/pour finding "un-masked, not caused, by this branch" in its own
commit message. Naming the distinction in the commit message is itself
part of the fix — a reviewer or future archaeologist reading `git log`
should not have to re-derive which of two bugs in one diff caused which
symptom.

This pattern is not new to this session —
`docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`
documents an equivalent three-layer stack (a build failure hiding a test
failure hiding an install failure) found eleven days earlier. What's worth
recording here is that the same shape recurred with entirely different
root causes (a Python import-binding trap and a router `KeyError`, versus
whatever the 07-18 incident's specific layers were) — this is evidently a
durable property of any codebase with long-blocked CI paths, not a
one-time artifact of a particular refactor.

## When to Apply

- Whenever fixing a crash, `AttributeError`, or collection-time error lets
  a test or gate proceed further than it has recently — budget time to
  triage whatever it hits next as a possible independent finding, not an
  artifact of the fix.
- Before reverting or scoping down a fix because "it broke something else"
  — check whether the "something else" was already broken and simply
  unreachable before the fix, per `git log -S`/`git blame` on the newly-
  failing assertion.
- When a fix's own description says "found while tracing" or "exposed a
  second bug" — treat that as two fixes needing two separate
  justifications and two separate verifications, not one combined patch.
- When several test-repair commits land in a tight time window after a
  long CI-blocking failure clears — read them as one excavation and check
  for a next layer, rather than closing the investigation at the first
  newly-visible failure.

## Related

- `docs/solutions/logic-errors/import-time-binding-defeats-monkeypatch-2026-07-29.md`
  — the PR #379 cascade in full technical detail
- `docs/solutions/logic-errors/tree-router-layer-selection-must-intersect-grids-2026-07-29.md`
  — the PR #386 cascade in full technical detail
- `docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md`
  — the middle layer of PR #386's three-deep stack
- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md` —
  mechanism 3 ("an uninvoked code path") describes the static shape a
  masked check has; this document covers what happens dynamically the
  moment the mask is removed
- `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`
  — an earlier, independent three-layer masking stack (build/test/install)
- `docs/solutions/test-failures/cli-cp-sat-tuning-flags-removed-stale-test.md`
  — the pattern PR #380 recurred, included here for contrast with a true
  cascade
- PR #379 (`e4e5e976`), PR #380 (`1f9d13d9`), PR #386 (`b39b382d`)
