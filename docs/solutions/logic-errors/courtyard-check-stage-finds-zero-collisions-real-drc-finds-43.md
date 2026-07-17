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
root_cause: unknown
resolution_type: workaround
tags:
  - temper-placer
  - courtyard
  - drc
  - deterministic-pipeline
  - self-grading
  - geometry
  - unresolved
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

## Not Yet Root-Caused

The exact reason `_find_collisions()`'s geometry model disagrees with
kicad-cli's is unresolved. Candidates not yet checked:

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
- **`pth_inside_courtyard`** (16 errors) is a category `CourtyardCheckStage`
  likely never checks for at all regardless of the above — it checks
  courtyard-vs-courtyard collisions, not plated-through-hole-vs-courtyard
  proximity. That specific error class may need a different stage
  entirely, not a fix to this one.

## Why This Matters

This is now the third confirmed instance of the deterministic pipeline
(the board's actual production placement path) reporting a clean result
that isn't. Unlike the other two (narrow-but-honest scope, just
mislabeled), this one is a genuine detection bug in the one stage whose
entire purpose is catching exactly this class of problem. A placement
that reports "courtyards resolved" while 27 real overlaps and 16
PTH-in-courtyard violations exist is not safe to hand off to routing or
fab without independent verification — which, per this investigation, the
pipeline currently provides no way to get automatically.

## Resolution

Not fixed — this needs someone to compare `_find_collisions()`'s computed
polygons against kicad-cli's courtyard interpretation directly (e.g., dump
both sets of polygons for one known-conflicting pair and diff them) before
a real fix is possible. Documented here so the gap is known and the
baseline doesn't imply false confidence.

`power_pcb_dataset/baselines/temper_production_baseline.yaml`'s
`placement_violations: 0` field is annotated to point at this doc and the
DRC-oracle doc, rather than either being silently trusted or blamed on the
wrong stage.

## Prevention

- **A stage whose entire purpose is detecting X should be checked against
  an independent X-detector before being trusted**, not just tested for
  internal self-consistency (does the nudge loop converge) — self-
  consistency and correctness are different properties, and this bug is
  exactly the gap between them: the loop *would* converge correctly if
  fed accurate collision data, but the initial detection was wrong.
- **When two independent implementations of "the same check" disagree,
  investigate before trusting either** — don't assume the internal,
  faster, purpose-built one is right just because it's newer or
  more specific to this pipeline.

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
