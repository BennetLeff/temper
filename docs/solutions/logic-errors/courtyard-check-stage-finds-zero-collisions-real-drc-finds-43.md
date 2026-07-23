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
  - kiutils
last_updated: "2026-07-17"
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

## Second Root Cause (Confirmed and Fixed, 2026-07-17): Courtyard Geometry Extraction Fell Through to Pad-BBox for 142/149 Footprints

Fixing the STRtree bug made the stage's *internal* detection loop actually
work — it now converges to 0 self-reported collisions instead of trivially
starting there. But re-running the full pipeline → export → kicad-cli DRC
sequence after that fix alone showed the **real** violation counts barely
moved (225 → 219 total errors; `courtyards_overlap` and
`pth_inside_courtyard` both unchanged at 27/16). That ruled out the
STRtree bug as the sole cause and pointed at the courtyard **shapes**
themselves being wrong, independent of the (now-correct) collision logic
operating on them.

Root-caused by inspecting the actual production board
(`fresh_deterministic_output.kicad_pcb`) directly with `kiutils` for two
components in a real, kicad-cli-confirmed `courtyards_overlap` pair (D3, a
`Diode_SMD:D_SMA`, and C4, a `Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn`):

- **D3's real courtyard** is drawn as 4 separate `fp_line` graphic items
  forming a rectangle: `(-3.5,-1.75)` to `(3.5,1.75)`.
- **C4's real courtyard** is a single `fp_circle`: center at local
  `(5.0, 0.0)` (offset from the footprint origin, not centered on it),
  radius `17.75mm` (a 35.5mm-diameter circle, reflecting the physical can
  of a large snap-in electrolytic capacitor).

`io/kicad_metadata.py`'s `_extract_courtyards` ("Strategy 1": look for
`F.CrtYd`/`B.CrtYd` graphic items) only recognized items exposing a
`.points` or `.coordinates` attribute — the shape kiutils uses for
`fp_poly` only:

```python
if hasattr(item, "points"):      # kiutils ~1.0
    pts = item.points
elif hasattr(item, "coordinates"):
    pts = item.coordinates
```

`fp_line` (kiutils `FpLine`) exposes `.start`/`.end`, not `.points`.
`fp_circle` (`FpCircle`) exposes `.center`/`.end`, not `.points`.
`fp_rect` (`FpRect`) exposes `.start`/`.end` (opposite corners), not
`.points`. **None of the three shapes real KiCad footprints actually use
to draw courtyards satisfied this check**, so `pts` stayed empty for
every graphic item on both D3 and C4, and extraction silently fell
through to "Strategy 2" (a rectangle from the pad bounding box, centered
on the footprint origin, ignoring courtyard margin entirely).

**Measured blast radius** across all 149 production-board footprints:

| Courtyard graphic type on `F.CrtYd`/`B.CrtYd` | Footprints |
|---|---|
| `fp_rect` | 108 |
| `fp_line` (rectangle drawn as 4 edges) | 28 |
| `fp_circle` | 6 |
| No `F.CrtYd` layer at all (legitimate pad-bbox fallback case) | 7 |
| **Footprints where Strategy 1 actually matched (`fp_poly`)** | **0** |

**142 of 149 footprints (95%)** had real courtyard graphics that
extraction never read, falling through to the pad-bounding-box
approximation for all of them — which is not just imprecise but centered
and sized wrong: C4's pad-bbox fallback was a `15mm × 5mm` box centered at
the origin, versus its real `35.5mm`-diameter circle offset 5mm off
origin. `check_overlap(D3, ..., C4, ...)` returned `False` under the old
(pad-bbox) geometry and `True` under the corrected geometry — directly
reproducing kicad-cli's real finding for this exact pair.

**Fix applied**: rewrote Strategy 1 to build proper `shapely` geometry per
item type — `FpRect` expanded to its 4 corners (its `start`/`end` are
*diagonal* corners, not two points on one edge, so hulling them directly
would degenerate to a line), `FpLine` endpoints collected into a shared
point set and convex-hulled, `FpCircle` turned into a `Point(center).buffer(radius)`
circle polygon, and `FpArc` given a coarse 3-point polyline approximation
(none present on this board, added for robustness) — then unioned via
`shapely.ops.unary_union` and converted back into the `points` list
`Courtyard` expects.

**Verification performed:**
- Direct extraction test: `meta.courtyards['D3'].points` now exactly
  matches the real `fp_line` rectangle; `meta.courtyards['C4'].points` is
  a 32-point polygon approximating the real circle, centroid at
  `(5.0, 0.0)`, area matching `π·17.75²` to within 1%.
- `check_overlap(D3, pos_d3, 0, C4, pos_c4, 0)` now returns `True`
  (previously `False`), matching kicad-cli's real
  `courtyards_overlap` finding for this exact pair.
- New regression test file `test_kicad_metadata_courtyards.py` (4 tests:
  `FpRect`, `FpLine`-rectangle, `FpCircle`, and the legitimate
  no-courtyard-layer fallback) — confirmed as a genuine guard by
  temporarily stashing the fix and re-running: 3 of 4 failed against the
  pre-fix code (each collapsing to the 1mm×1mm ultimate fallback since the
  synthetic test footprints have no pads either), then passed again after
  unstashing.
- Checked the only other courtyard-consuming call site
  (`placement_audit.py`'s `hull.buffer(0.5)`, a different, independent
  courtyard approximation) — out of scope for this fix, not touched.

## Third, Separate Issue: Nudge-Resolution Doesn't Fully Converge on the Real Geometry — RESOLVED (not a software bug), 2026-07-18

**Update:** root-caused in a follow-up investigation — see
[`production-board-courtyard-area-exceeds-usable-board-area.md`](../architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md).
Total real courtyard area for all 149 components (13,670.8 mm²) exceeds
the board's usable area (12,600 mm², 100×150mm minus 5mm margins) —
**108.5% of usable area, before even accounting for real-world packing
inefficiency.** Confirmed this is a genuine geometric infeasibility, not
an algorithm weakness: a 10x iteration budget increase (500 → 5000) only
marginally improved the result (43 → 31 unresolved pairs) and the
unresolved-pair count oscillates in a stable ~26–48 range indefinitely
rather than trending toward zero — the signature of a stable equilibrium
around an unsatisfiable constraint, not slow convergence. **No placement
algorithm can produce zero courtyard overlaps for this component set on
this board size.** The original hypotheses below (rotation assumption,
clearance mismatch, resolution-algorithm weakness) are superseded by this
finding; kept for historical record.

With both bugs above fixed, a full pipeline → export → kicad-cli DRC
re-run was finally possible end-to-end (it was blocked by an unrelated
numba shim bug hit along the way — see
[`njit-fallback-shim-discards-function-on-bare-decorator.md`](njit-fallback-shim-discards-function-on-bare-decorator.md)).
Results:

| | Original baseline | After STRtree fix only | After both fixes |
|---|---|---|---|
| kicad-cli total DRC errors | 225 | 219 | **142** |
| `courtyards_overlap` | 27 | 27 | **29** |
| `pth_inside_courtyard` | 16 | 16 | **18** |

Total DRC errors dropped substantially (225 → 142), consistent with the
courtyard fix correcting many now-larger, more-accurate exclusion zones
that upstream stages route/place around better. But `courtyards_overlap`
and `pth_inside_courtyard` themselves did **not** improve — they are
roughly flat, even slightly higher. This is not a sign the geometry fix
is wrong (`check_overlap` on the known D3/C4 pair now correctly agrees
with kicad-cli — see above); it is the geometry fix **revealing a harder,
real problem** that the smaller/wrong pad-bbox courtyards had been masking.

`CourtyardCheckStage.run()`'s nudge-resolution loop, given the
now-accurate (and therefore mostly larger) courtyard sizes, failed to
converge within its `max_iterations=500` budget on this board — internal
debug output oscillated between roughly 29 and 48 unresolved pairs across
the final ~40 iterations rather than settling toward 0
(`DEBUG: CourtyardCheck Failed to resolve 35 pairs after 500 iterations`).
This looks like a genuine placement-density problem: the upstream stages
place 149 components on a 100×150mm board tightly enough that pairwise
nudging (fixed `nudge_step=0.2mm` per iteration, moving one pair at a
time) cannot find enough free space to separate every real courtyard
overlap, and likely enters limit cycles (small random noise is already
added specifically to break these, per the existing code comment, but
apparently not always enough).

This is a **distinct class of problem from both bugs above** — it is not
a detection-correctness bug (the stage now measures the right things) but
a resolution-algorithm/placement-density limitation, and is **not fixed
in this pass**. Candidates for follow-up, not yet investigated:
- Whether upstream placement stages (before `CourtyardCheckStage` runs)
  are packing components too densely for *any* pairwise nudge algorithm
  to resolve, meaning the real fix belongs earlier in the pipeline, not
  in this stage.
- Whether a stronger resolution strategy (e.g. simulated annealing, a
  proper 2D bin-packing pass, or iterating groups instead of pairs) is
  needed instead of independent pairwise nudges.
- Whether `max_iterations=500` is simply too low once courtyards are
  correctly sized, or whether the loop is genuinely stuck in a limit
  cycle regardless of iteration budget.

(Resolved — see the update above; all three candidates here are
superseded by the board-size-infeasibility finding.)

## Addendum: Hand-Built Footprint Dimensional Accuracy — Checked, Correct

One candidate hypothesis for the geometry mismatch (see "Second Root
Cause" above) was that the several hand-built footprints added this arc
might have dimensionally-incorrect courtyard/pad geometry as originally
authored, independent of the extraction bug. Checked directly against
real datasheets:

- **CST2010** (hand-built, Coilcraft inductor): pad dimensions, pitch,
  body envelope, and lead-tip span all verified exactly against Coilcraft
  datasheet 1100-2 (the same document cited in the footprint's own
  `descr` field). Courtyard sits ~0.3mm outside the pad envelope,
  consistent with its own "pads + 0.25mm margin" comment. **Matches.**
- **CMC_B82726S** (hand-built, TDK common-mode choke): pin pitches (top
  row 18mm, bottom row 38mm, row-to-row 23mm) and body envelope (50×49mm
  max) verified exactly against TDK datasheet b82726s2163.pdf. The
  footprint also correctly captures a subtle, easy-to-invert detail —
  TDK's real drawing mirrors the bottom-row pin order relative to the top
  row. **Matches.**
- **G5LE-1** and **IRM-10-15** — turned out to **not be hand-built at
  all**: both are official, community-maintained `kicad-footprints`
  submodule library footprints (`Relay_SPDT_Omron-G5LE-1.kicad_mod`,
  `Converter_ACDC_MeanWell_IRM-10-xx_THT.kicad_mod`). Correcting the
  original hypothesis framing — the earlier assumption that all four
  were hand-authored was itself wrong. Both are physically plausible on
  a lighter check; not deep-verified against datasheets since they carry
  the lower risk profile of externally-vetted library content rather
  than this investigation's original "hand-built dimensional error"
  target.

**Conclusion:** footprint authoring accuracy is not a contributing factor
to any of the findings in this doc. The geometry mismatch was entirely
explained by the extraction-strategy bug (Second Root Cause); the
remaining overlap gap is entirely explained by board-size infeasibility
(Third, Separate Issue).

## Why This Matters

This is now the third confirmed instance of the deterministic pipeline
(the board's actual production placement path) reporting a clean result
that isn't. Unlike the two scope-mismatch findings in the sibling doc,
this one required two independent, stacked fixes (detection logic, then
detection accuracy) before the stage's *self-report* could be trusted at
all — and even now, with both fixed, the stage's honest self-report is
"I found real overlaps and could not fully resolve them," not "0
violations." The corrected numbers (142 total kicad-cli errors, down from
225) prove the fixes are real and load-bearing, not cosmetic — but
`courtyards_overlap`/`pth_inside_courtyard` specifically remain non-zero,
so this board is still not safe to hand off to routing or fab without
independent kicad-cli verification.

## Resolution

**Both correctness bugs fixed, 2026-07-17; the third issue root-caused
(not a software bug) 2026-07-18.**

1. STRtree index-vs-object-identity bug (see "Root Cause" above): fixed,
   verified via `test_courtyard_check.py` (4 tests, 2/4 fail on old code).
2. Courtyard geometry extraction only recognizing `fp_poly` (see "Second
   Root Cause" above): fixed, verified via `test_kicad_metadata_courtyards.py`
   (4 tests, 3/4 fail on old code) plus the direct D3/C4 `check_overlap`
   reproduction of kicad-cli's real finding.
3. Nudge-resolution convergence (see "Third, Separate Issue" above):
   **not a bug — the constraint is geometrically unsatisfiable** at the
   board's current 100×150mm size for its current 149-component BOM
   (total courtyard area is 108.5% of usable board area). No further
   software fix applies; see
   [`production-board-courtyard-area-exceeds-usable-board-area.md`](../architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md)
   for the board-size/BOM-level options going forward.

`power_pcb_dataset/baselines/temper_production_baseline.yaml`'s
`placement_violations: 0` field is annotated to point at this doc and the
DRC-oracle doc, rather than either being silently trusted or blamed on the
wrong stage. That annotation remains accurate post-fix: `0` is still not
a trustworthy number for real courtyard safety — now for a resolution
(not detection) reason.

## Prevention

- **A stage whose entire purpose is detecting X should be checked against
  an independent X-detector before being trusted**, not just tested for
  internal self-consistency (does the nudge loop terminate) — self-
  consistency and correctness are different properties, and this bug
  family sits exactly in that gap: fixing detection logic (bug 1) does not
  imply fixing detection accuracy (bug 2), and fixing both does not imply
  the resolution algorithm can actually clear what it now correctly sees
  (issue 3). Each is a separate claim requiring separate proof — treat
  "detects correctly," "measures correctly," and "resolves what it finds"
  as three independent properties to verify, not one.
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
- **A geometry-extraction "Strategy 1: look for the real graphic layer"
  is only as good as the set of shape types it recognizes.** This one
  silently matched 0 of 149 real footprints on the production board (it
  only ever handled `fp_poly`) while still "succeeding" via Strategy 2's
  pad-bbox fallback often enough to look plausible. When a strategy has a
  fallback, its match rate is invisible unless someone explicitly measures
  it — log or assert a minimum match rate for "should usually succeed"
  extraction strategies instead of silently falling through every time.

## Related Issues

- [`docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`](../architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md)
  — the follow-up investigation that root-caused the "Third, Separate
  Issue" above as a genuine geometric infeasibility (total courtyard area
  exceeds usable board area), not a resolvable software bug.
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
  — regression test file for the STRtree fix; confirmed to fail 2/4
  tests against the pre-fix code.
- `packages/temper-placer/tests/io/test_kicad_metadata_courtyards.py` —
  regression test file for the geometry-extraction fix; confirmed to fail
  3/4 tests against the pre-fix code.
- [`docs/solutions/logic-errors/njit-fallback-shim-discards-function-on-bare-decorator.md`](njit-fallback-shim-discards-function-on-bare-decorator.md)
  — an unrelated bug hit and fixed while re-running the pipeline to verify
  the geometry fix above; blocked end-to-end verification until fixed.
- [`docs/solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md`](drc-api-wrapper-components-and-location-always-empty.md)
  — found while manually pulling real component refs out of kicad-cli DRC
  results for this investigation's D3/C4 verification; the wrapper's
  `.components`/`.location` fields were always empty/zero for every
  violation type, forcing a raw-JSON workaround at the time.
