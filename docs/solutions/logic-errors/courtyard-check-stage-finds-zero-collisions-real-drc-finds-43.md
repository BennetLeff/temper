---
title: "CourtyardCheckStage finds zero courtyard collisions on the real board; kicad-cli DRC finds 43 (27 overlaps + 16 PTH-in-courtyard) on the identical export"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
severity: critical
symptoms:
  - "CourtyardCheckStage's own collision detector (_find_collisions) reports 0 collisions on the first pass -- 'courtyard_check moved 0 components', no nudging ever triggered"
  - "Real kicad-cli DRC on the exact same exported board (same run, same script, no staleness) reports 27 courtyards_overlap errors and 16 pth_inside_courtyard errors"
  - "All 149 components have courtyard geometry available (metadata.courtyards is complete) -- this rules out the stage silently skipping components for lack of data"
root_cause: logic_error
resolution_type: code_fix
tags:
  - temper-placer
  - courtyard
  - drc
  - deterministic-pipeline
  - self-grading
  - geometry
  - shapely
  - strtree
---

# CourtyardCheckStage finds 0 collisions; real DRC finds 43 on the identical board

## Problem

`CourtyardCheckStage` (`deterministic/stages/courtyard_check.py`) exists
specifically to detect and resolve component courtyard overlaps before
export. Running the full 22-stage pipeline against the real production
board (`pcb/temper.kicad_pcb`, 149 components,
`configs/temper_production_config.yaml`) in a single uninterrupted script
— pipeline run → export → DRC, no intermediate files, no staleness — the
stage's own collision detector never finds anything to fix
(`courtyard_check moved 0 components`, meaning zero collisions on the very
first `_find_collisions()` pass). Real `kicad-cli` DRC
(`temper_placer.validation._drc_api.run_drc`) on the exact board this
stage just certified clean finds:

- **27 `courtyards_overlap` errors**
- **16 `pth_inside_courtyard` errors**

This is a distinct bug from the two other self-grading gaps found the same
day (`docs/solutions/logic-errors/deterministic-pipeline-drc-oracle-only-checks-routing-not-real-drc.md`
and `PlacementValidationStage`'s narrow declared-constraint-only scope —
see the baseline annotation). Those two are *scope* mismatches: a
correctly-working check whose name overpromises what it covers. This one
is different — `CourtyardCheckStage`'s entire job is exactly what
`courtyards_overlap`/`pth_inside_courtyard` measure, and it is
**getting the wrong answer**, not skipping the check.

## What Was Ruled Out

- **Not a staleness/comparison artifact.** Ran pipeline execution, export,
  and DRC in one continuous script against one in-memory `state` — no
  chance of comparing two different runs.
- **Not a stage-ordering bug.** The pipeline explicitly re-runs
  `ApplyPlacementsStage()` after `CourtyardCheckStage` (commented
  "DRC-FIX-5: Re-apply placements after clamping to sync
  component.initial_position") — this ordering already accounts for and
  fixes an earlier version of a similar-sounding bug. It is not the cause
  here since the stage itself never detects any collisions to begin with,
  before ordering could even matter.
- **Not missing courtyard data.** All 149 components have courtyard
  polygons in `metadata.courtyards` — the collision loop has geometry to
  check for every component.
- **Not a `CourtyardCheckStage` convergence failure** (exhausting
  `max_iterations` with residual collisions). The stage's own
  post-resolution check (`final_collisions`) would `print("DEBUG:
  CourtyardCheck Failed to resolve...")` if that happened — it never did.
  The bug is upstream of the resolution loop: the *initial* detection
  pass already disagrees with reality.

## Root Cause (Confirmed and Fixed, 2026-07-17)

`_find_collisions()` builds a `shapely.strtree.STRtree` over all component
courtyard polygons and, for each polygon, calls `tree.query(poly)` to get
candidate overlaps. The original code matched each candidate back to its
component ref via Python object identity:

```python
for poly, ref1 in polys_with_refs:
    candidates = tree.query(poly)
    for candidate_poly in candidates:
        ref2 = None
        for p, r in polys_with_refs:
            if p is candidate_poly:   # <-- BUG
                ref2 = r
                break
        if ref2 is None or ref1 == ref2:
            continue
        ...
```

`shapely` 2.x changed `STRtree.query()` to return an `ndarray` of integer
**indices** into the array the tree was built from, not geometry objects
(a breaking API change from Shapely 1.x, which this code was apparently
written against). Verified directly: `shapely.__version__ == '2.1.2'`,
`type(tree.query(polys[0])[0]) == numpy.int64`. Because `if p is
candidate_poly` compares a `Polygon` to a `numpy.int64`, it can never be
`True` — `ref2` was always `None`, every candidate was skipped via the
`continue`, and the stage detected **zero collisions on any board,
unconditionally**, regardless of real overlaps.

**Fix applied** in `courtyard_check.py`'s `_find_collisions`: index
`polys_with_refs` directly with the returned integer, instead of
re-searching for object identity:

```python
checked_pairs = set()
for poly, ref1 in polys_with_refs:
    candidate_indices = tree.query(poly)
    for idx in candidate_indices:
        candidate_poly, ref2 = polys_with_refs[idx]
        if ref1 == ref2:
            continue
        pair = tuple(sorted([ref1, ref2]))
        if pair in checked_pairs:
            continue
        checked_pairs.add(pair)
        if poly.intersects(candidate_poly) and not poly.touches(candidate_poly):
            collisions.append((ref1, ref2))
```

(This also incidentally fixes an O(n) duplicate-pair bug — each unordered
pair was previously eligible to be checked and appended twice, once from
each direction — by tracking `checked_pairs`.)

**Verification performed:**
- Minimal repro (3 points, one expected colliding pair): old code found 0
  collisions, new code found exactly 1, matching the geometric expectation.
- New regression test file `test_courtyard_check.py` (4 tests) — confirmed
  as a genuine regression guard by temporarily stashing the fix and
  re-running: 2 of 4 tests (`test_find_collisions_detects_real_overlap`,
  `test_find_collisions_scales_beyond_two_components`) failed against the
  old code, then passed again after unstashing.
- Full pipeline re-run against the real production board: the stage's
  debug output went from constant `courtyard_check moved 0 components` to
  genuinely iterating — "Found 33 overlapping pairs" on iteration 0,
  decreasing to "Found 1 overlapping pairs" by iteration 17 — a complete
  behavioral change confirming the detector is now live.
- Full `temper-placer` deterministic test suite: 306 passed (same 2
  pre-existing, unrelated errors as before the change) — no regressions.

## Second, Separate, Still-Open Bug: Geometry Model Disagrees With kicad-cli

Fixing the STRtree bug made the stage's *internal* detection loop actually
work — it now converges to 0 self-reported collisions instead of trivially
starting there. But re-running the full pipeline → export → kicad-cli DRC
sequence after the fix shows the **real** violation counts barely moved:

| | Before fix | After fix |
|---|---|---|
| kicad-cli total DRC errors | 225 | 219 |
| `courtyards_overlap` | 27 | 27 (unchanged) |
| `pth_inside_courtyard` | 16 | 16 (unchanged) |

This confirms the STRtree bug was not the (or not the only) source of the
27/16 discrepancy against kicad-cli. The stage's own geometry model — even
with correct index resolution — still disagrees with kicad-cli's real
courtyard interpretation. This is a **distinct, unresolved bug**, not
covered by the fix above. Candidates not yet checked:

- **Rotation assumption.** `_find_collisions()` hardcodes rotation=0 in
  `self.courtyards[ref].get_global_polygon(pos[0], pos[1], 0)` (comment:
  "Assume rotation = 0 (as per pipeline comment)"). This matches the
  deterministic pipeline's own behavior (it never modifies rotation — see
  `docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md`'s
  warm-start section for the same fact established independently), but it
  was not verified whether every INPUT footprint on `pcb/temper.kicad_pcb`
  is actually at 0° before the pipeline runs. If any aren't, this
  assumption is wrong for those parts.
- **Polygon extraction correctness.** Whether `Courtyard.get_global_polygon`
  (and wherever `metadata.courtyards` itself is built) produces
  dimensionally-correct courtyard polygons for every footprint, especially
  the several hand-built footprints added this arc (CST2010, CMC_B82726S,
  the G5LE-1 relay, the IRM-10-15 module) — not cross-checked against the
  real courtyard silkscreen layer kicad-cli reads.
- **Clearance/tolerance definition mismatch.** Whether `_find_collisions`
  treats "overlap" as strict polygon intersection while kicad-cli's DRC
  rule includes a clearance margin (or vice versa), which would make the
  internal check systematically more permissive.
- **`pth_inside_courtyard`** (16 errors, unchanged by this fix) is a
  category `CourtyardCheckStage` likely never checks for at all regardless
  of the above — it checks courtyard-vs-courtyard collisions, not
  plated-through-hole-vs-courtyard proximity. That specific error class
  may need a different stage entirely, not a fix to this one.

Recommended next step (not yet performed): dump the actual computed
Shapely polygon for one known-conflicting pair from kicad-cli's raw DRC
JSON (e.g. a pair implicated in a `courtyards_overlap` violation) and diff
it directly against `Courtyard.get_global_polygon()`'s output for the same
pair/position, to determine whether the discrepancy is in size, position,
or rotation.

## Why This Matters

This is now the third confirmed instance of the deterministic pipeline
(the board's actual production placement path) reporting a clean result
that isn't. Unlike the other two (narrow-but-honest scope, just
mislabeled), this one was a genuine detection bug in the one stage whose
entire purpose is catching exactly this class of problem — and fixing it
was necessary but not sufficient. Even with detection logic working
correctly, the stage's internal geometry model still disagrees with
kicad-cli's real interpretation on the exact same violations (27
`courtyards_overlap`, 16 `pth_inside_courtyard`, both unchanged by the
fix). A placement that reports "courtyards resolved" is still not safe to
hand off to routing or fab without independent kicad-cli verification.

## Resolution

**Partially fixed, 2026-07-17.** The STRtree index-vs-object-identity bug
(see "Root Cause" above) is fixed and verified: `courtyard_check.py`'s
`_find_collisions` now correctly resolves `STRtree.query()`'s integer
indices back to polygons/refs instead of a never-true identity check. A
new regression test file, `test_courtyard_check.py` (4 tests), guards
against this specific regression and was confirmed to fail 2/4 against the
pre-fix code.

This fix makes the stage's detection loop genuinely functional (it now
iterates and converges against real internal collision data, rather than
trivially reporting zero from the first pass). **It does not close the
gap against kicad-cli** — see "Second, Separate, Still-Open Bug" above.
That part needs someone to compare `_find_collisions()`'s computed
polygons against kicad-cli's courtyard interpretation directly (e.g., dump
both sets of polygons for one known-conflicting pair and diff them) before
a further fix is possible.

`power_pcb_dataset/baselines/temper_production_baseline.yaml`'s
`placement_violations: 0` field is annotated to point at this doc and the
DRC-oracle doc, rather than either being silently trusted or blamed on the
wrong stage. That annotation remains accurate post-fix: `0` is still not
a trustworthy number for real courtyard safety, just for a different
(narrower) reason now.

## Prevention

- **A stage whose entire purpose is detecting X should be checked against
  an independent X-detector before being trusted**, not just tested for
  internal self-consistency (does the nudge loop converge) — self-
  consistency and correctness are different properties, and this bug
  family sits exactly in that gap: the loop *does* converge correctly
  once fed accurate collision data (fixed), but "accurate" here still
  means accurate relative to this stage's own geometry model, not
  necessarily to kicad-cli's. Fixing detection logic does not imply
  fixing detection accuracy — treat them as two separate claims requiring
  two separate proofs.
- **When two independent implementations of "the same check" disagree,
  investigate before trusting either** — don't assume the internal,
  faster, purpose-built one is right just because it's newer or
  more specific to this pipeline.
- **`shapely>=2.0`'s `STRtree.query()` returns integer indices, not
  geometry objects.** Any code in this codebase still written against the
  Shapely 1.x object-returning API is a candidate for the exact same
  silent-no-op bug class. Checked the only other `STRtree` call site in
  the codebase (`router_v6/constraints_design_rules.py`'s
  `ZoneManager.get_zone_at`) as part of this investigation — it already
  correctly indexes `self._polygons[idx]`, so it is not affected. This
  bug was isolated to `courtyard_check.py`.

## Related Issues

- [`docs/solutions/logic-errors/deterministic-pipeline-drc-oracle-only-checks-routing-not-real-drc.md`](deterministic-pipeline-drc-oracle-only-checks-routing-not-real-drc.md)
  — sibling self-grading finding from the same investigation, different
  root cause (narrow scope vs. wrong detection).
- `docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md`
  — the warm-start investigation that independently established the
  deterministic pipeline never modifies component rotation, relevant to
  the rotation-assumption hypothesis above.
- `power_pcb_dataset/baselines/temper_production_baseline.yaml` —
  `placement_violations: 0` annotated with this finding.
- `packages/temper-placer/tests/deterministic/stages/test_courtyard_check.py`
  — regression test file added alongside the fix; confirmed to fail 2/4
  tests against the pre-fix code.
