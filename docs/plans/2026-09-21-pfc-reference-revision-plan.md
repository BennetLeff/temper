---
title: PFC reference revision after campaign closeout
type: project
status: completed
date: 2026-09-21
---

# PFC reference revision

## Objective

Turn the completed custom-model assessment into a source-bound, reference-informed
next candidate without treating simulation completion as hardware qualification.
The user authorized this work and bounded Luna delegation on 2026-09-21.

## Deliverables and acceptance

1. **Record the completed assessment.** Preserve accepted, failed and incomplete
   results and the runtime incident. Link original receipts, rather than rewrite
   them. Owner: parent. Output: the linked closeout evidence document.
2. **Set the power budget.** Use 1800 W appliance input as the comparison target,
   15 A RMS as the retained screen, and explicit PF, conversion and auxiliary
   assumptions. Show 108/120/132 V allocations. Owner: Luna budget, parent review.
3. **Choose the next architecture.** Retain UCC28180 for this revision, grounded
   in EVM-573/TIDA-00779 wiring; distinguish PMP10948's different controller and
   separate outputs. Reconsider on demonstrated low-line/thermal limitations.
   Owner: Luna reference, parent review.
4. **Reconcile source authority and test one electrical change.** Distinguish
   the restored 54-part baseline, rejected 133-part source-build-07, separate
   protection experiments and accepted SPICE model. Create a new candidate with
   only controller feedback moved VB→VD. Run a short old/new OVP fixture against
   the unchanged authored controller. Owner: Luna fixture/protection inventory;
   parent source audit, candidate and review.

Success for step 4 means source identities, a one-line electrical delta and a
reproducible functional result with explicit limits. It does not require, or
justify claiming, a rebuilt protected board or a full converter qualification.

## Constraints

- Preserve all frozen campaign evidence and the retained CAD/source baseline.
- F2 is a proposed fuse; keep the healthy modeled path closed. Default-off and
  fresh-arm semantics apply to gate enable, not an invented F2 actuator.
- Do not add an ideal source disconnect as a claimed failed-switch solution.
  F1 already exists; dynamic fuse clearing and coordination remain unresolved.
- Keep independent external bank overvoltage protection in the candidate.
- Model clamp and physical BAT54H polarity/location are different; leave this
  explicit and block broad acceptance until resolved.
- Use the tested command guard with fresh receipts and ≤60 s solver timeout.
  No new full matrix, raw archive processing or hardware energization in this unit.
- New numerical checks use standalone Rust, not a parallel Python authority.

## Next gates after this unit

All four deliverables above are complete for their stated scope. The parent
rebuilt the fixture checker with warnings denied and verified the retained
35,138-row trace plus five deliberate negative mutations. The 500 µs solver
run completed in 1.321 seconds. Full converter and hardware acceptance remain
outside this completed unit.

Resolve clamp topology/part bounds; reconcile the reduced protection subcircuit
with the retained source; define the power allocation and source/fuse models
needed for a specific next experiment. Then run a bounded startup/normal check
on the changed feedback topology before selecting a broader operating matrix.

## Evidence

- [Campaign closeout](../evidence/2026-09-21-pfc-campaign-closeout-and-next-revision.md)
- [Revision 08](../../zapote/power-entry/passive-reva/protection/reference-revision-08/README.md)
