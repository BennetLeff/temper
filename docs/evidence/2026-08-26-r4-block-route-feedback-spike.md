---
title: R4 bounded block-to-route feedback spike
date: 2026-08-26
status: measured
---

provenance: commit=721ce2b20d09c9855e01d3c1f63c762c23cf2d9c dirty=false

# R4 bounded block-to-route feedback spike

## Outcome

The place-to-route seam now has a finite Rust-owned block-search contract, and
its first production-board run falsified rigid translation as a sufficient
move class for R4. No router run was launched because no candidate passed the
geometric safety preflight. That is the intended fail-closed behavior, not a
missing result.

## Implemented contract

`temper-quality-oracle` owns:

- a deterministic Chebyshev-ring translation schedule with explicit grid,
  ring and candidate limits;
- exclusion of the unchanged origin;
- selection only among candidates that passed the full regional safety
  verdict, with routed pad connectivity ranked before secondary metrics;
- conversion of measured body-collision pairs into deterministic block-
  expansion candidates.

`scripts/search_block_layout.py` is the thin adapter. It writes placements
through the existing Rust KiCad writer, measures exact HV-to-SELV pairs and
F.Fab bodies, calls the production router only for preflight-passing
candidates, and sends routed measurements back to Rust for final selection.
The geometric and routing budgets are independent; the current defaults are
24 generated candidates and at most 3 routed candidates.

## Production-board experiment

Three stages used 10 mm grid translations. Sixty materially distinct
floorplans were evaluated in total:

| block | candidates | result |
|---|---:|---|
| `{R4}` | 24 | zero accepted |
| `{R4, C4}` | 18 | zero accepted |
| `{R4, C4, C7, R46, R8}` | 18 | zero accepted |

For R4 alone, four translations removed the target pairs and introduced no
new cross-domain pair. All four collided with C4. Expanding the block to
include C4 converted that collision into repeated measured blockers: C7,
R46 and R8 each blocked three otherwise safety-clean candidates; K1 blocked
one. This feedback, rather than visual judgment, selected the next block.

After expanding to `{R4, C4, C7, R46, R8}`, none of the 18 translations had
zero new HV-to-SELV pair. Consequently the router budget consumed was 0/3.
A placement that is already unsafe is not made worth routing by a generous
autorouter budget.

## Decision

Rigid block translation is now closed for R4 at this resolution and budget.
The next move class must permit an internal block rearrangement and/or a
discrete block rotation while preserving electrical/physics constraints. It
must use the same preflight and final routed acceptance contract. Finer
coordinate sampling is not the next step.

Certification-lab work remains last, after this internal floorplan work,
routing, and final verification are complete.
