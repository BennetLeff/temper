---
title: "Check the exception before adopting the default, and the default before adopting the exception — PD3 swings the requirement 6x and nobody had derived it either way"
date: "2026-07-28"
category: best-practices
module: hardware_design
problem_type: best_practice
component: compliance
severity: critical
applies_when:
  - "a compliance standard names a default classification and a named exception that depends on a physical/mechanical fact (enclosure, sealing, pollution exposure) not yet checked against this design's own mechanical documents"
  - "a whole day (or investigation) of downstream numeric work has been scoped to a parameter value that was asserted, by any party, without a citation to primary text or this design's own mechanical documents"
  - "re-deriving a constant after a governing parameter changes, and the re-derivation happens not to change the final verdict"
  - "a design change multiplies through every downstream threshold in a single investigation (a pollution-degree change; a tier/tolerance-class change; any classification the rest of the analysis is conditioned on)"
tags:
  - pollution-degree
  - iec-60335-2-6
  - clause-29-2-exception
  - falsifiable-determination
  - parameter-swing
  - re-derive-dont-carry-across
  - inconvenient-answer
---

# Check the exception before adopting the default, and the default before adopting the exception

## Context

IEC 60335-2-6's clause 29.2 addition states: *"The microenvironment is
pollution degree 3 unless the insulation is enclosed or located so that it
is unlikely to be exposed to pollution during normal use of the
appliance"* (`docs/ENVIRONMENTAL_SPEC.md` §3.1). PD3 is the standard's own
default for this appliance class; PD2 is the exception, and it must be
*earned* by showing the insulation is enclosed or located away from
pollution exposure. **Neither direction of this had been checked against
the design's own mechanical documents before 2026-07-28** — three prior
sessions asserted PD2 with no citation at all, and the exception itself had
never been separately evaluated against `docs/CHASSIS_AIRFLOW_DESIGN.md`,
even though `ENVIRONMENTAL_SPEC.md` §3.1 already gestured toward it. A
whole day's worth of creepage, keepout-gate, slot, and relay-footprint work
had been scoped to whichever pollution degree happened to be assumed, not
derived.

The governing number swings **6.35x** between the two branches: 2.0mm at
PD2 (reinforced clearance, IEC 60335-1 Table 17 row iv) versus 12.6mm at
PD3 — every downstream keepout width, slot length, and footprint pass/fail
verdict in this investigation is conditioned on which one governs.

**The determination, made directly against this design's mechanical
documents, not inherited:**

- `docs/COIL_BRACKET_DESIGN.md` describes an **open, deliberately
  air-permeable structure** — "large triangular cutouts... allow air from
  the bottom intake to flow directly through the Litz wire strands," acting
  as a baffle, not a seal.
- `docs/CHASSIS_AIRFLOW_DESIGN.md`'s own word "enclosed" describes the
  **chassis as a whole** (an appliance case), while its interior is an
  actively vented volume: bottom vents → intake plenum → 80mm PWM fan →
  transition duct → IGBT heatsink → exhaust vent, explicitly drawing
  kitchen air through the same cavity the PCB sits in.
- `docs/ASSEMBLY_GUIDE.md` mounts the PCB via M3 standoffs directly into
  that same chassis cavity — no separate box, no partition wall, no gasket
  described anywhere for the PCB specifically. The assembly's **only**
  gasket (Phase 3, "high-temp silicone gasket to the chassis lip") seals
  the glass-ceramic cooktop to the chassis — a different joint, retaining
  glass, not excluding pollution from the electronics.
- The board's own **IP20** rating does not, by itself, constitute an
  enclosure argument: the second digit (0) is the *liquid*-ingress figure
  and "no liquid ingress protection guaranteed" argues against an
  enclosure claim if anything, and neither IP20 digit speaks to airborne
  grease/steam/cooking aerosol — exactly what the forced-air duct is
  designed to pull across the compartment.

**The exception is not earned on the evidence in this repository today.
PD3 governs; 12.6mm is a real requirement, not a conservative bound.** This
is reported as a determination against the documents that exist, with its
own falsifier stated plainly
(`docs/evidence/2026-07-28-pd3-retarget-keepout.md` §0.4): a future
mechanical revision documenting a genuine sealed, gasketed PCB compartment
— separate from the coil/heatsink airflow path — that the forced-air duct
demonstrably does not cross, would change this. No such document exists
today. **This was the inconvenient answer**: it re-targets a gate to a
stricter number, fails a relay footprint that a prior session had reported
passing, and finds a placement-constrained slot (`U7`) that cannot reach
the new target — none of which a team hoping to close out the day's work
would want the determination to conclude.

## The counter-example worth keeping: a constant that didn't need to change

Re-deriving from primary text is not merely a defensive ritual — it is
supposed to sometimes report "no change needed," and here it did, cleanly.
IEC 60664-1 clause 4.2's minimum groove width `X` is **1.0mm at PD2** and
**1.5mm at PD3** (`docs/evidence/2026-07-28-pd3-retarget-slots.md` §1,
re-fetched and independently re-read this session rather than carried
across from the PD2-era design). The PD2-era `U3`/`U7` slot designs used a
5.0mm/6.0mm groove width — **3.3x and 4.0x the PD3 minimum respectively** —
so the correct, larger PD3 figure changes neither slot's verdict: the
groove-width floor was never what bound either design, at either pollution
degree. **The discipline paid off even though the answer was "no change
needed."** Re-deriving `X` cost one clause lookup; *not* re-deriving it and
assuming 1.0mm carried across at PD3 would have been exactly the kind of
stale-constant error this project's history is full of — it simply
happened not to matter this time, and that is worth recording precisely
because it is easy to skip a re-derivation once its answer starts to feel
predictable.

## The pattern

**A standard's default and its named exception are two different claims,
and each needs its own evidence — "PD2, because the enclosure exception
obviously applies" and "PD3, because that's the default" are both
assertions until one is checked against this design's actual mechanical
documents.** The failure mode runs in both directions: three prior
sessions here asserted PD2 with zero citation (adopting the exception
without checking whether it was earned), while a team eager to close out a
long investigation could just as easily assert PD3-forever to avoid
re-opening a settled-feeling question (adopting the default without
checking whether the exception genuinely fails to apply). Symmetry is the
point: neither direction gets to be the default assumption; both need the
same mechanical-document check this session finally ran.

A parameter this central — one that scales every downstream creepage
figure by 6.35x — deserves the re-derivation discipline applied to *every*
constant that depends on it, not just the headline threshold. The
groove-width minimum is the same clause family as the reinforced-clearance
figure and could plausibly have changed enough to matter; checking it and
finding it didn't matter is itself evidence the re-derivation habit is
doing its job, not evidence the habit was unnecessary.

## Guidance

1. **When a standard states "X is the default unless Y," treat both "Y
   applies" and "Y does not apply" as claims requiring evidence from this
   design's own documents — never assume either direction from familiarity
   or from whichever one the current investigation would prefer.** Read
   the actual mechanical/environmental documents (here: coil bracket,
   airflow ducting, assembly guide, sensor mount, connectors — five
   documents, all read directly, none of them previously cross-checked
   against clause 29.2 specifically) before deciding which branch governs.
2. **A word like "enclosed" in one document does not automatically satisfy
   a different document's use of the same word for a narrower claim.**
   `CHASSIS_AIRFLOW_DESIGN.md`'s "enclosed RCA 12A3 chassis" describes the
   appliance case, not a sealed PCB compartment; clause 29.2 needs the
   latter. Reading the word without checking what it is describing is how
   an exception gets adopted that was never actually earned.
3. **Report a determination with its own falsifier, not as a closed
   question.** "The exception does not apply on the evidence available
   today; it would if a future document established X" is a stronger,
   more honest claim than either "PD2 is fine" or "PD3 is settled forever"
   — it names exactly what would change the finding and confirms nothing
   currently in the repository does.
4. **When a governing parameter changes, re-derive every constant that
   depends on it from primary text — don't carry a PD2-era figure forward
   under the assumption it scales the same way or doesn't matter.** Do
   this even when (especially when) the re-derivation is expected to be a
   formality; the groove-width check here cost one clause lookup and
   confirmed a real, board-specific margin (3.3x/4.0x) rather than an
   assumption.
5. **Report the inconvenient answer as the answer.** A PD3 determination
   that re-targets a gate stricter, fails a footprint a prior session
   called passing, and surfaces a new placement-constrained shortfall is
   exactly the outcome a day's work would not want at its end — report it
   anyway, with the falsifier that could reopen it, rather than quietly
   preferring whichever branch keeps the day's other work intact.
6. **A parameter change that swings the governing number by an order of
   magnitude (or close to it) deserves to be checked *first*, before any
   downstream design work is scoped to a value nobody has derived.** The
   6.35x swing here means every keepout width, slot length, and footprint
   verdict produced before this determination was provisional on an
   unresolved question — worth stating explicitly rather than discovering
   after the fact how much of a day's work depended on it.

## Why This Matters

A whole day's creepage-related work — the isolation-keepout gate's minimum
width, the U3/U7 slot designs, the K2/K3 relay footprint's verdict — had
been scoped to whichever pollution degree happened to be assumed, and no
prior session had actually earned that assumption in either direction.
Resolving it correctly required reading five mechanical documents that had
never been cross-checked against this one clause, and it produced the
answer nobody hoping to close out the investigation wanted: PD3 governs,
12.6mm is real, and it makes the relay footprint fail by 7.3mm instead of
passing by 1.2mm. The groove-width re-derivation is the necessary
complement to that story — it shows the same discipline applied to a less
dramatic constant, correctly re-derived, and correctly found not to change
anything. A team that only tells the story where re-deriving matters will
eventually skip the re-derivation on the constant that quietly does.

## When to Apply

- Before adopting either a standard's stated default or its named
  exception — check the exception's own conditions against this design's
  actual mechanical/environmental documents, regardless of which branch
  feels more convenient or more familiar.
- When a single classification (pollution degree, tolerance class,
  material group) governs multiple downstream numeric thresholds — resolve
  it first, explicitly, before scoping design work to any one branch.
- When a governing parameter changes, re-derive every dependent constant
  from primary text — including the ones expected to be unaffected — and
  report the re-derivation even when the verdict doesn't change.
- Before reporting a compliance determination as settled — state what
  would change it (the falsifier), and confirm nothing in the repository
  currently satisfies that condition.
- When a determination produces the outcome that costs the most downstream
  work to accept — report it as the finding, not as a reason to re-examine
  the determination until a more convenient answer appears.

## Examples

```
# The clause, and the two claims each need their own evidence for:
"pollution degree 3 UNLESS the insulation is enclosed or located so that
 it is unlikely to be exposed to pollution during normal use"
        ^ PD3 (default)              ^ PD2 (exception -- must be earned)

# WRONG (either direction), unless checked against this design's own docs:
"PD2, obviously the electronics are enclosed"          # adopts exception, no evidence
"PD3, that's just the appliance-class default"         # adopts default, no evidence

# RIGHT: check the exception's actual conditions against the mechanical docs
COIL_BRACKET_DESIGN.md:    "triangular cutouts... allow air... to flow
                            directly through" -- air-permeable, not a seal
CHASSIS_AIRFLOW_DESIGN.md: bottom vents -> plenum -> fan -> duct -> exhaust,
                           "enclosed" describes the CASE, not a PCB compartment
ASSEMBLY_GUIDE.md:         PCB standoff-mounted in the same vented cavity;
                           the only gasket seals glass to chassis, not PCB
IP20:                      "no liquid ingress protection guaranteed" --
                           argues against, not for, an enclosure claim
  => exception NOT earned on the evidence available -> PD3 governs, 12.6mm
```

```
# The counter-example: re-derived, and the verdict didn't change
IEC 60664-1 cl. 4.2, dimension X minimum:
  PD2 = 1.0mm   PD3 = 1.5mm   (1.5x, re-fetched and re-read, not assumed)

U3 groove width: 5.0mm  -- 3.3x the PD3 floor either way
U7 groove width: 6.0mm  -- 4.0x the PD3 floor either way
  => neither slot's verdict changes; the floor was never the binding
     constraint at either pollution degree. Re-derived anyway.
```

## Related

- `docs/solutions/best-practices/measurement-convention-must-be-stated-2026-07-28.md`
  — the sibling same-week lesson on this exact creepage investigation:
  once PD3 is settled, the numbers being compared against it must also be
  measured on a consistent, correctly-stated basis (see also its
  2026-07-28 update on the relay footprint below).
- `docs/solutions/best-practices/calibration-point-must-equal-design-point-2026-07-28.md`
  — a sibling category error from the same week: trusting a figure that
  answers a different, related question (a calibration point; a PD2-era
  constant) instead of re-deriving the one the design actually needs.
- `docs/solutions/best-practices/sufficient-condition-infeasible-is-not-requirement-infeasible-2026-07-28.md`
  — the CP-SAT corridor-model INFEASIBLE result this determination directly
  feeds: widening the corridor to 12.6mm does not change which isolators
  are infeasible under that model, for reasons independent of this
  determination.
- `docs/ENVIRONMENTAL_SPEC.md` §3.1 — the clause chain and the prior
  gesture toward `CHASSIS_AIRFLOW_DESIGN.md` this session finally checked
  directly.
- `docs/evidence/2026-07-28-pd3-retarget-keepout.md` §0 — the full
  five-document determination, its falsifier, and the consequence measured
  against the real board (152 sub-12.6mm cross-domain pad pairs; K1 and T1
  newly failing at 12.6mm having passed 8.0mm).
- `docs/evidence/2026-07-28-pd3-retarget-slots.md` §1 — the groove-width
  re-derivation (1.0mm → 1.5mm) and the margin check confirming it changes
  neither `U3` nor `U7`'s verdict.
- `scripts/check_isolation_keepout.py` — `MIN_BARRIER_WIDTH_MM`, re-targeted
  8.0mm → 12.6mm with the full clause chain in its own docstring.
