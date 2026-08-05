---
title: "When two branches fix the same defect differently, check what target each was aimed at before choosing"
date: "2026-07-29"
category: best-practices
module: hardware_design
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "two branches independently fix the same reported defect with visibly different approaches (different footprint vs. different geometry, different config vs. different code path)"
  - "a merge conflict or fork between two fixes looks like a taste/preference choice that could be resolved by picking either side"
  - "a fix's own commit message states the numeric target it was verified against, and that target has since been re-derived to a different value"
  - "reviewing whether a land-pattern, clearance, or threshold fix is 'done' by checking it against the requirement it cites, not the requirement current at merge time"
tags:
  - fork-resolution
  - requirement-drift
  - creepage
  - measurement-before-preference
  - placement-vs-footprint
  - pd-classification
---

# When two branches fix the same defect differently, check what target each was aimed at before choosing

## Context

`origin/main` (commit `4696427a`) and a feature branch (`f81317e5`/
`5ef309d8`) each independently fixed the same defect — insufficient
HV-to-SELV creepage at isolators U3 and U7 — with visibly different
approaches: `main` enlarged the isolators' land patterns (new footprints,
wider pads); the feature branch cut routed creepage slots through the
board around the same stock pads. On the surface this reads as a taste
conflict git would need a human to resolve by picking a side.

Measuring both against the *current* requirement dissolved the apparent
conflict, and the dissolution came from a mismatch in **target**, not
approach:

- `main`'s fix was dimensioned and verified against
  `MIN_BARRIER_WIDTH_MM = 8.0` — the PD2 (pollution degree 2) figure. Its
  own commit message says so directly: *"against the 8.0mm
  MIN_BARRIER_WIDTH_MM ... All three clear 8.0mm."* It never mentions PD3.
- The requirement had since been re-derived to PD3's `12.6mm` (IEC 60335-1
  Table 17 row iv, doubled per clause 29.2.3 for reinforced insulation),
  documented in `docs/ENVIRONMENTAL_SPEC.md`: *"PD2 is not earned on this
  design today."*

Measured directly from real pad/slot geometry
(`docs/evidence/2026-07-30-pollution-degree-determination.md §5.3`):

| Approach | U3 | U7 |
|---|---:|---:|
| `main`, enlarged pads | 8.56mm — **FAILS** (−4.04mm vs. 12.6mm) | 8.10mm — **FAILS** (−4.50mm) |
| feature branch, slots | 14.058mm — **PASSES** (+11.6%) | 8.627mm — **FAILS** (−3.97mm) |

`main`'s fix, correctly verified against the number it cited, is
non-viable against the number that actually governs today. The feature
branch's slots are strictly better at both parts and close U3 outright —
but do not close U7 either.

**The second finding inside the same measurement:** U7 fails under *both*
approaches, for a reason neither approach could have fixed. The branch's
own prior analysis (`ae2753f5`) had already shown U7 sits close enough to
the board's left edge that no achievable slot length reaches 12.6mm — even
the unmanufacturable zero-edge-clearance limit only reaches 9.167mm. U7's
gap is a **placement** ceiling, not a footprint problem. The fork between
two footprint-only fixes was hiding a defect neither fix's approach could
address.

## The pattern

**A fork between two fixes for the same defect can look like a choice
between equally valid approaches when it is actually a choice between two
answers to different questions.** Both branches' authors did real,
correct work relative to the target each was measuring against; the
apparent disagreement was manufactured by the requirement moving between
when `main`'s fix landed and when it was being evaluated for merge. Git
sees two conflicting diffs and offers no signal that they were aimed at
different numbers — that context lives only in commit prose and
`docs/ENVIRONMENTAL_SPEC.md`'s revision history, not in the diff itself.

The second finding generalizes further: even after resolving which
approach to keep, a fork audit is not complete until you check whether the
kept approach's own residual gap has a *different* root cause than the
metric it was framed against suggests. "Neither fix reaches 12.6mm at U7"
looks, before the placement analysis, like "the slot approach needs a
bigger slot." It is not — no slot size fixes it. Conflating "this
approach's number is short" with "a bigger version of this approach would
close it" would have sent the next iteration down a dead end.

## What to do

1. **Before choosing between two fixes for the same defect, find each
   fix's own stated target — not just its stated result.** `main`'s commit
   named its target explicitly (`MIN_BARRIER_WIDTH_MM = 8.0`); reading only
   the achieved figures (8.56mm, 8.10mm) without the target they were
   checked against would have looked like a plausible, if imperfect, fix.
2. **Re-verify both fixes against the requirement current at review time,
   not the requirement current when either fix was written.** A
   requirement that has been re-derived since a fix landed (PD2 → PD3 here)
   invalidates that fix's own verification section even though nothing in
   the fix itself is wrong.
3. **When a residual gap survives every approach tried, check whether the
   gap has a different governing variable than the one the fixes vary.**
   Both isolator fixes varied footprint/geometry; U7's gap was governed by
   *placement*, a variable neither fix touched. Discovering this required
   measuring the geometric maximum achievable at U7's fixed position, not
   just comparing the two fixes' numbers to each other.
4. **State results with explicit units against the explicit target**, the
   way the resolution commit does (`8.56mm FAILS (−4.04)` against 12.6mm,
   not just "8.56mm"), so a future reader can re-check the verdict the
   moment the target changes again without re-deriving the geometry.

## Why This Matters

Merging `main` as-is would have shipped a defect its own author correctly
closed — against a superseded number. Recognizing the fork as a
target-mismatch rather than a preference call is what made the slot
approach's superiority measurable rather than a matter of opinion, and it
is what surfaced that U7's real defect (placement) was never going to be
fixed by either branch's actual changes. A resolution that had "picked a
side" without this measurement would have shipped a mains-adjacent
isolator barrier several millimeters short of its reinforced-insulation
requirement, with no signal in the code review that either number was
wrong.

## When to Apply

- Resolving any merge conflict or fork between two fixes for the same
  reported defect — find and compare each side's stated verification
  target before comparing their results.
- Reviewing a land-pattern, clearance, or threshold fix that cites a
  specific numeric requirement — confirm that requirement is still the
  live one, not one already superseded by a later re-derivation.
- When a fix falls short of its target — check whether a different,
  larger version of the same approach would close the gap, or whether the
  governing variable is something the approach never touched (placement,
  a different physical constraint) before iterating on the approach taken.

## Examples

```
main's own commit, verbatim:
  "Re-measured HV<->SELV separations ... against the 8.0mm
   MIN_BARRIER_WIDTH_MM ... All three clear 8.0mm."
  -> correct relative to what it cites; the cite itself is stale (PD2, not PD3)

Feature branch's docstring:
  MIN_BARRIER_WIDTH_MM = 12.6   # IEC 60335-1 Table 17 row iv, PD3, doubled
                                 # for reinforced insulation (cl. 29.2.3)
```

## Related

- `docs/evidence/2026-07-30-pollution-degree-determination.md §5.3` — full
  measurement: pad/slot geometry sourced independently from both branches'
  files, IEC 60664-1 cl. 4.2 groove-width citation re-fetched from primary
  source, U3/U7 courtyard-clearance figures reproduced from raw geometry.
- `docs/solutions/best-practices/verify-the-binding-axis-not-the-headline-rating-2026-07-28.md`
  — a sibling lesson from the same isolator-barrier work: a lead-form fix
  that raised clearance while leaving creepage (the axis that actually
  binds) unchanged.
- Commit `dfa2cc8a` — `docs(evidence): resolve U3/U7 isolator-creepage fork
  -- enlarged pads vs routed slots`.
- Commit `87050a8e` — `decision: keep the routed-slot approach; U7 is a
  PLACEMENT defect, not a footprint one`.
