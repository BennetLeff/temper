---
title: "A sufficient condition proved unsatisfiable is not the requirement proved unsatisfiable — CP-SAT INFEASIBLE misread as a BOM verdict"
date: "2026-07-28"
category: best-practices
module: temper_placer
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "a solver (CP-SAT, SMT, MILP) returns INFEASIBLE for a constraint that is a geometric or numeric stand-in for a physical/safety requirement"
  - "a gate enforces a requirement as one specific sufficient condition (a straight-line corridor, a fixed threshold, a single formula) rather than the requirement's own definition"
  - "an INFEASIBLE or FAILED result is about to be reported as 'the requirement cannot be met' rather than 'this specific formulation of it cannot'"
  - "a standard or spec permits multiple independent constructions to satisfy the same clause, and the code models only one of them"
tags:
  - sufficient-not-necessary
  - cp-sat
  - infeasibility-misread
  - creepage-vs-clearance
  - over-constrained-gate
  - bom-conclusion
  - falsifier
---

# A sufficient condition proved unsatisfiable is not the requirement proved unsatisfiable

## Context

`scripts/check_isolation_keepout.py` enforces the mains↔SELV creepage
requirement as a straight-line, zero-copper corridor ≥8.0mm wide,
verified by a Shapely negative-buffer erosion test that must hold
everywhere along the barrier. A CP-SAT formulation of the same corridor as
a hard placement constraint
(`packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`,
`docs/evidence/2026-07-28-barrier-constrained-placement.md`) returned
`INFEASIBLE` in ~23s: 7 of the board's 8 mixed-domain "isolator"
components (`C6`, `K1`, `K2`, `K3`, `T1`, `U3`, `U7`) cannot achieve an
8.5mm gap between their own HV-pad cluster and SELV-pad cluster at any of
the 4 axis-aligned rotations — a real, provable geometric fact about
those footprints, independent of where they're placed on the board. The
conclusion drawn from it was that this is "a BOM problem": 7 named
components would need replacement before a compliant placement search was
even worth attempting.

A follow-up brainstorm
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §7)
tested that conclusion against the requirement's own primary text (IEC
60335-1) rather than against the gate that had been built to enforce it,
and found the corridor-width constraint is **sufficient but not
necessary** for creepage:

> "A corridor of width W does guarantee creepage ≥ W across it — so the
> gate is *sufficient*. It is not *necessary*: creepage can equally be
> achieved by lengthening the path (a groove or slot) without widening the
> straight-line gap... Therefore the CP-SAT INFEASIBLE result does not
> carry the weight placed on it. It proves that *one particular sufficient
> condition* is unsatisfiable given these footprints. It does not prove
> the *requirement* is unsatisfiable."

Re-measuring the same 8 parts with a rectangle-aware (not
bounding-circle) pad model — exact here, since every isolator footprint is
rotated by an exact multiple of 90 degrees — and against the correctly
derived figures (clearance 1.5–2.0mm, not 8.0mm; creepage 8.0mm only under
one specific, now clause-cited combination of inputs) collapsed the
finding: **`T1` (9.10mm) and `K1` (8.00mm) pass 8.0mm outright** — the
prior bounding-circle model's 7.0mm and 5.425mm for them were modeling
artifacts, not physical facts. Of the remaining failing set (`C6`, `K2`,
`K3`, `U3`, `U7`), `C6` is an unsourced stub footprint (a sourcing gap,
not a part-choice gap) and `U3`/`U7` are PCB land-pattern shortfalls
against parts whose *packages* are independently rated for reinforced
isolation — a groove lengthens exactly the path that's short for them.
**The genuine sourced-part BOM exposure is `K2` and `K3`** — two
components, not seven, because their shortest creepage path runs across
the relay's own plastic base, a property no board feature can lengthen.

## The pattern

A gate that enforces a requirement via one specific sufficient condition
is a valid, useful gate — the isolation-keepout gate is not wrong to
require a corridor, and 8.5mm is not wrong to model as a hard constraint
when a corridor is the chosen remedy. **The error is in what an
INFEASIBLE result on that formulation is allowed to prove.** `P ⇒ Q`
being false for the specific `P` encoded (a straight corridor of width W)
says nothing about whether some other `P'` also implies `Q` (a grooved
path, an inner-layer earthed screen under clause 3.4.4, an Annex J
conformal coating dropping the pollution degree, a certified component
whose approval carries its own creepage). A solver proving one
formulation UNSAT is doing exactly what it was asked; the mistake is
downstream, in reading "this encoding has no solution" as "this
requirement has no solution."

This is easiest to miss precisely when the solver's answer is crisp and
fast (23.4s, not a timeout) and the per-component evidence is
individually damning (7 of 8 parts each independently fail the corridor).
Both of those make the result *feel* exhaustive. Neither one establishes
that the encoded constraint is the same thing as the requirement it
stands in for.

## Guidance

1. **Before reporting a solver's INFEASIBLE as a requirement-level
   verdict, ask what the encoded constraint assumes away.** Here: that
   creepage can only be achieved by straight-line separation. State that
   assumption explicitly next to the result, the same way a falsifier is
   stated before a run — "this formulation is UNSAT; the requirement is
   UNSAT only if this formulation is the requirement's only satisfying
   construction."
2. **When a spec permits multiple independent constructions for the same
   clause, a gate that encodes only one of them is a lower bound on
   difficulty, not the full requirement.** IEC 60335-1 clause 3.4.4 alone
   names three (basic + protective screening, double insulation,
   reinforced) before groove geometry or coating provisions are even
   considered. A gate is allowed to pick one to enforce; a conclusion
   drawn from that gate is not allowed to forget the others exist.
3. **Re-derive the requirement's own governing quantity before trusting a
   borrowed number wearing the requirement's label.** The corridor gate's
   8.0mm is a genuine reinforced-creepage figure; it is not a clearance
   figure, and clearance (1.5–2.0mm here) was never the binding
   constraint on this board at all — every isolator failure found was a
   creepage failure. A model can be internally consistent and still be
   answering a stricter question than the one being asked.
4. **A conservative geometric model (bounding-circle vs rectangle-aware
   pad shape) can turn "marginal" into "infeasible" for parts whose real
   geometry would pass.** Two of seven initially-failing parts (`T1`,
   `K1`) passed outright once measured against their actual rectangular
   pad extent instead of a worst-case circle. Re-measure with the least
   conservative model that is still correct before finalizing a BOM
   conclusion drawn from a geometric proof.
5. **State what the narrower, supported conclusion actually is.** Not "7
   components need BOM changes" but "an 8.0mm straight-corridor
   formulation is infeasible for 7 named footprints on this board"; not
   "the design needs new parts" but "K2/K3's coil-to-contact creepage runs
   across the relay's own case and is a genuine part-level gap; the other
   five are addressable by a groove, a wider land pattern, or a coating
   decision a human still needs to make." The narrower statement is
   strictly more useful, because it names which remedies are still open.

## Why This Matters

The initial reading turned a geometric proof about one encoding into a
procurement decision about seven real components — `C6`, `K1`, `K2`,
`K3`, `T1`, `U3`, `U7` — several of which are parts whose datasheets
already claim near- or at-8mm reinforced isolation along their own
package surface (`T1`: ">=8mm creepage/clearance" per its footprint
description; `U7`: pins deliberately omitted "for isolation
creepage/clearance"). Acting on the wider conclusion would have meant
respecifying and re-sourcing parts that were never actually the problem,
while the framing that would have found the real, narrower remedy (a PCB
groove, a laminate change, an Annex J coating decision) was available in
the same standard the whole time. The CP-SAT solver did its job exactly
right; the failure was entirely in what got inferred from a correct,
fast, crisp UNSAT.

## When to Apply

- Before reporting any solver INFEASIBLE/UNSAT result as evidence that an
  underlying physical or business requirement cannot be met — confirm the
  encoding is the requirement, not a sufficient stand-in for it.
- When a gate enforces a safety/compliance requirement via geometry
  (a keepout, a clearance corridor, a fixed distance) — check the
  governing standard for alternative constructions before treating the
  gate's specific shape as the only way to satisfy the clause.
- When a proof of infeasibility leads directly to a procurement,
  respecification, or re-architecture conclusion — re-derive the
  requirement's own governing number from primary text before accepting a
  borrowed figure's label.
- When a geometric feasibility check uses a conservative approximation
  (bounding circles, worst-case envelopes) — re-check failing cases
  against the least conservative model that remains correct before
  finalizing a downstream decision.

## Examples

```
# WRONG — solver UNSAT reported as requirement UNSAT
CP-SAT(corridor_width=8.5mm) -> INFEASIBLE (7 of 8 isolators)
  => "7 components need BOM changes"

# RIGHT — the encoding is named, and only its own conclusion is drawn
CP-SAT(corridor_width=8.5mm) -> INFEASIBLE (7 of 8 isolators)
  => "a straight-line ≥8.5mm corridor cannot be drawn through these 7
      footprints on this board — creepage can also be satisfied by a
      groove, a screening layer, or a coating decision, none of which
      this formulation can express; re-derive against the requirement
      before concluding a BOM change is needed"

# Re-measurement with the correct pad model changed the supported set:
T1: bounding-circle gap 7.000mm (FAIL @ 8.0mm) -> rectangle-aware 9.100mm (PASS)
K1: bounding-circle gap 5.425mm (FAIL @ 8.0mm) -> rectangle-aware 8.000mm (PASS, 0 margin)
# Genuine sourced-part exposure: K2, K3 only — 3.500mm either way,
# because their COM-to-coil path runs across the relay's own case.
```

## Related

- `docs/solutions/best-practices/claimed-isolation-vs-actual-connectivity-2026-07-26.md`
  — the 2026-07-28 update to that doc covers the prior step in this same
  investigation: the mains↔SELV barrier existed in three declarations and
  zero copper before this CP-SAT attempt was even made.
- `docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
  — a sibling lesson from the same week: a rigorously correct diagnosis
  (there, of a phantom layer; here, of an infeasible corridor) does not by
  itself license the conclusion drawn from it.
- `docs/evidence/2026-07-28-barrier-constrained-placement.md` — the CP-SAT
  formulation, the INFEASIBLE result, the per-isolator feasibility table,
  and the original seven-component BOM conclusion.
- `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §4, §7,
  §8 — the clearance-vs-creepage derivation from primary IEC 60335-1 text,
  the "gate measures the wrong thing" analysis, and the corrected
  pass/fail table that collapses the exposure to `K2`/`K3`.
- `docs/evidence/2026-07-28-discharge-relay-isolation.md` — the follow-on
  research into real replacement parts for the two components this
  narrower conclusion actually implicates.
- `scripts/check_isolation_keepout.py` — the gate whose corridor-width
  enforcement is a correct, useful, but partial (sufficient-not-necessary)
  encoding of the creepage requirement.
