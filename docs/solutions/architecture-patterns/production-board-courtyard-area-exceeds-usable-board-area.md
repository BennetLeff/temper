---
title: "The production board's total component courtyard area (13,670.8 mm^2) exceeds its usable area (12,600 mm^2) -- zero courtyard overlaps is geometrically impossible at the current board size"
date: "2026-07-18"
category: architecture-patterns
module: temper_placer
problem_type: architecture_pattern
component: service_object
severity: critical
applies_when:
  - "Investigating why CourtyardCheckStage's nudge-resolution loop fails to converge to zero collisions even after its detection logic and courtyard geometry extraction are both confirmed correct"
  - "Deciding whether a placement algorithm improvement can close the remaining courtyards_overlap/pth_inside_courtyard gap against kicad-cli, or whether the constraint is unsatisfiable at the current board size/component set"
  - "Evaluating whether pcb/temper.kicad_pcb (100mm x 150mm, 149 components) can ever reach a genuinely DRC-clean courtyard state without a board or BOM change"
tags:
  - temper-placer
  - courtyard
  - placement-density
  - packing
  - board-size
  - feasibility
---

# Production board's total courtyard area exceeds usable board area -- zero overlaps is not achievable at 100x150mm

## Context

Follow-up to
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md),
which fixed two real bugs (a Shapely STRtree indexing bug, then a
courtyard-geometry-extraction bug that made 142/149 footprints use a
wrong pad-bounding-box approximation) and left a third finding open:
even with both fixes applied, `CourtyardCheckStage`'s pairwise
nudge-resolution loop does not converge to zero collisions on the real
production board, oscillating between roughly 26 and 48 unresolved pairs
regardless of iteration budget.

This doc investigates *why* the resolution loop can't converge, to
determine whether it's an algorithm weakness (fixable in software) or a
structural constraint (not fixable by any placement algorithm at the
current board size).

## Investigation

**Does more iteration budget help?** Ran the resolution loop directly
against the real 149-component pre-courtyard-check placement snapshot
(captured mid-pipeline, right before `CourtyardCheckStage` runs) at two
budgets:

| `max_iterations` | Final unresolved pairs |
|---|---|
| 500 (current default) | 43 |
| 5000 (10x) | 31 |

A 10x iteration budget increase only marginally improved the result, and
inspecting the last 20 iterations of the 5000-iteration run shows the
unresolved-pair count oscillating between roughly 26 and 44 with no
downward trend -- a **stable dynamic equilibrium, not slow convergence**.
More iterations would not close this gap; this rules out "just needs a
bigger iteration budget" as the fix.

**Is a zero-overlap packing even geometrically possible?** Summed the
real (now-correctly-extracted) courtyard polygon area for all 149
components and compared against the board's usable area:

- Real board size (verified directly from the `Edge.Cuts` `GrPoly` in
  `pcb/temper.kicad_pcb`: exact corners `(0,0)` to `(100,150)`): **100mm x
  150mm = 15,000 mm^2**.
- Usable area after `CourtyardCheckStage`'s own 5mm edge margin:
  **(100-10) x (150-10) = 12,600 mm^2**.
- **Total component courtyard area: 13,670.8 mm^2.**

**13,670.8 / 12,600 = 108.5% of usable board area**, *before* accounting
for the fact that real-world packing of irregularly-sized
rectangles/circles never achieves 100% area efficiency (only identical
squares tile perfectly). At realistic packing efficiencies for a mixed
rectangle/circle component set (50-80%, generously), the board would need
136%-217% of its current usable area to fit these components with zero
courtyard overlap -- i.e. **the board would need to be roughly 1.4x to
2.2x larger** (e.g. something in the range of 120x170mm to 150x220mm,
depending on assumed packing efficiency), or the component footprint
count/size would need to shrink by a comparable factor.

**Where the area actually goes:** the 8 largest components account for
57.5% of total courtyard area (7,860.1 of 13,670.8 mm^2) despite being
~5% of the component count:

| Ref | Courtyard area (mm^2) | Likely role |
|---|---|---|
| L1 | 1428.0 | largest inductor |
| PS1 | 1196.6 | power supply module |
| C2 | 989.4 | bulk capacitor |
| C3 | 989.4 | bulk capacitor |
| C4 | 989.4 | bulk capacitor (the 35mm radial cap from the sibling doc) |
| C5 | 989.4 | bulk capacitor |
| K1 | 716.8 | relay/contactor |
| U22 | 561.2 | large IC/module |

## Conclusion

**`CourtyardCheckStage`'s nudge-resolution loop not converging is not a
software bug.** Detection is now correct (STRtree fix) and the geometry
it operates on is now correct (extraction fix), and the loop is doing
exactly what it should with the data it has: trying to find a
zero-overlap arrangement that **does not exist** for this component set
on a 100x150mm board. No placement algorithm -- pairwise nudging,
simulated annealing, ILP-based bin packing, or anything else -- can
produce zero real courtyard overlaps here, because the raw area
requirement alone (before even accounting for packing inefficiency,
routing channels, connector accessibility, or mechanical mounting
clearance) already exceeds what's available.

This reframes the remaining `courtyards_overlap`/`pth_inside_courtyard`
kicad-cli gap (29/18 errors after both software fixes, from the sibling
doc) as a genuine **board-level design constraint**, not a placement
pipeline defect: the current 100x150mm board cannot physically
accommodate the current 149-component BOM without some courtyard overlap,
regardless of how good the placement software gets.

## Why This Matters

This closes out (with a definitive, non-software answer) the "Third,
Separate, Still-Open Issue" left open in the sibling courtyard doc. It
also means: **any future work aimed at eliminating real courtyard
violations on this exact board+BOM combination is working toward an
unsatisfiable goal**, and should instead target one of:

1. **Increase board size** -- roughly 1.4x-2.2x the current usable area,
   per the packing-efficiency estimate above, would give a real
   algorithm room to find a valid non-overlapping arrangement.
2. **Reduce component footprint area** -- the 8 largest components (57.5%
   of total area) are the highest-leverage targets: smaller-package
   alternatives for L1, PS1, C2-C5, K1, U22 would disproportionately
   shrink the total area requirement.
3. **Accept and explicitly document some courtyard overlap as a known,
   reviewed design tradeoff** (common in dense power electronics where a
   courtyard margin is deliberately conservative and some "overlaps" are
   not real physical collisions) -- but this requires a human engineering
   review of which specific overlaps are acceptable, not a placement
   algorithm decision.

Any of these is a legitimate engineering call, but none of them are a
software fix -- so no further time should be spent trying to make
`CourtyardCheckStage`'s resolution loop "work harder" on the current
board.

## Related Finding: Board Dimensions Are Hardcoded, Not Parsed

While verifying board size for this calculation,
`io/kicad_metadata.py:extract_kicad_metadata` was found to hardcode
`board_width = 100.0` / `board_height = 150.0` with a
`# TODO: Parse from edge cuts - for now use defaults` comment, rather
than reading the real `Edge.Cuts` polygon. For `pcb/temper.kicad_pcb`
specifically this happens to be correct (verified: the real `Edge.Cuts`
`GrPoly` is exactly `(0,0)` to `(100,150)`), so it did not affect this
finding's numbers. But this is a latent bug for any other board: it would
silently mis-measure board area/margins for a board of any other size,
with no error or warning. Not fixed in this pass (out of scope -- flagged
here since it was directly relevant to trusting this doc's own area
calculation).

## Prevention

- **Before concluding an iterative resolution algorithm "isn't good
  enough," check whether a solution exists at all.** A stable oscillation
  around a non-zero count across a 10x iteration budget increase is a
  strong signal of infeasibility, not slow convergence -- a genuinely
  convergent algorithm trends toward its fixed point; a genuinely
  infeasible problem oscillates around some equilibrium density
  indefinitely. This distinction is checkable directly (sum required
  area vs. available area) far more cheaply than tuning an algorithm
  against an unsatisfiable target.
- **A placement pipeline's DRC-cleanliness ceiling is bounded by the
  board+BOM's physical feasibility, not just software quality.** Any
  future "why isn't this board DRC-clean" investigation on
  `pcb/temper.kicad_pcb` at its current size/BOM should check this doc
  first before re-investigating the placement algorithm.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the sibling investigation this doc's "Third, Separate, Still-Open
  Issue" section referred to; this doc resolves that open question.
- `power_pcb_dataset/baselines/temper_production_baseline.yaml` —
  `placement_violations: 0` annotation should be read alongside this
  doc: the remaining courtyard violations are a board-design constraint,
  not a pending software fix.
