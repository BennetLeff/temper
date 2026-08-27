---
title: R4 discrete block-layout search
date: 2026-08-26
status: measured
---

# R4 discrete block-layout search

## Question

Could a bounded structural move solve the R4 creepage cluster after rigid
translation failed, without turning placement into an indefinite sequence of
coordinate nudges?

## Search contract

The move vocabulary is finite and Rust-owned:

- an internal pivot component can occupy four body-dimension-derived slots
  around a named anchor;
- pivot and whole-block orientation are quarter turns only;
- whole-block translation remains a finite Chebyshev-ring schedule;
- Rust composes those axes, excludes only the unchanged board, establishes
  deterministic order, and applies the hard total-candidate cap;
- the canonical `kicad_transform` kernel supplies KiCad's `R(-theta)` rotation.

Python only maps those typed moves onto KiCad footprints, invokes the existing
pair/body instruments, and runs the production router for the highest-ranked
preflight candidates under a separate routing cap.

## Production-board preflight

The 64-candidate experiment used block `{R4, C4, C7, R46, R8}`, anchored at
C4, with R4 as the internal pivot. It covered four whole-block quarter turns,
two R4 quarter turns, four R4 orbit slots, the as-is arrangement, and a capped
10 mm translation ring.

One candidate passed the geometric safety preflight:

| candidate | move | removed exact HV↔SELV pairs | new pairs | new/worsened F.Fab collisions |
|---:|---|---:|---:|---:|
| 4 | R4 right of C4, R4 q0, block q0, translation (0, 0) | 3 | 0 | 0 |

This is qualitatively different from the failed nudge loop. The selected
coordinate is derived once from the two physical body envelopes plus a 1 mm
gap. There is no continuously adjustable direction or step size inside the
internal arrangement vocabulary.

## Routed verdict

The single capped production-router run rejected candidate 4:

| metric | result |
|---|---:|
| route completion | 13.33% |
| pad-connected nets | 38 |
| unrouted nets | 91 |
| candidate DRC errors | 980 |
| exact `track_width` count | 199 (reporting cap, not a count) |

The routed board increased every hard-veto DRC family measured by the regional
gate (`shorting_items`, `clearance`, `hole_clearance`, and
`copper_edge_clearance`). It therefore fails independently of the reporting
cap and cannot become acceptable through a tolerance or a ceiling update.

The first evaluation also named a stale `temper_quality_oracle` extension
because this branch's Rust schedule was edited while the long route was
running. That instrument error is recorded rather than hidden, but it is not
needed for the verdict: each hard-veto increase independently rejects the
candidate. The extension was rebuilt before the final focused test run.

The route exposed a separate production-router defect on two gate-driver nets:
combining multiple creepage-halo entries flattened exterior rings but retained
an extra list axis around their holes. The Rust pyo3 binding consequently
received a list where it required a floating-point coordinate and declined
both nets fail-closed. The adapter now flattens exterior and hole axes in the
same way, with a two-entry regression that reproduces the formerly failing
shape.

## Decision

The bounded structural search is worth keeping: it found a geometric solution
that rigid translation could not. That solution is not a routed-board solution,
so R4 does not move. The next engineering target is routing feasibility around
the accepted floorplan, beginning with the now-fixed multi-halo marshalling
defect and then the reported incomplete connectivity; it is not finer placement
sampling.

Certification-lab work remains the final project step and was not performed.
