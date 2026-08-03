---
title: "Calibration point and design point must be the same point — a pan model solved at 80µH reported as physics at 150µH"
date: "2026-07-28"
category: best-practices
module: simulation
problem_type: best_practice
component: physics_simulation
severity: high
applies_when:
  - "a model's free parameters were solved (calibrated) against one input value, and the model is then swept or evaluated across a range that includes a different, undeclared design value"
  - "a sweep holds calibrated parameters fixed while varying the exact input variable they were calibrated against"
  - "a headline result 'lands inside the literature range' and the calibration point that produced it hasn't been re-checked against the design's actual operating point"
  - "a protection/trip threshold and an expected operating value are being compared, converted, or substituted for one another"
tags:
  - calibration-point
  - design-point
  - pan-load-model
  - tank-current
  - category-error
  - mechanical-artifact
  - protection-threshold-vs-operating-point
---

# Calibration point and design point must be the same point

## Context

`simulation/models/pan_load.sub`'s reflected-impedance model has three free
parameters — coupling `K`, secondary inductance `L2`, and pan resistance
`RPAN` — solved to hit a target effective resistance `R_eff ≈ 2.2Ω` **at
`L1 = 80µH`**, the simulation harness's own pre-existing default, unrelated
to the coil this project is actually building
(`docs/evidence/2026-07-27-pan-model-correction.md` §1: `K = 0.791`,
`L2 = 218.2µH`, both solved holding `L1` fixed at 80µH). The project's
**declared design inductance is `l_tank_assumed = 150µH`**
(`inductance-range-sweep.md`, same day). A later, separate sweep pass then
varied `L1` from 50–250µH — including the 150µH design point — while
holding `K`, `L2`, `RPAN` fixed at their 80µH-calibrated values across the
entire range.

`docs/evidence/2026-07-27-inductance-range-sweep.md (the reconciliation table is reproduced inline in this doc)` recomputed
`R_eff` at every point in that sweep and found `R_eff / L` constant to
within 0.2% across the full 50–250µH range:

| L (µH) | R_eff (Ω) | R_eff / L (Ω/µH) |
|---|---:|---:|
| 70 | 1.957 | 0.02795 |
| 90 | 2.516 | 0.02796 |
| **150** | **4.196** | **0.02797** |
| 250 | 6.994 | 0.02798 |

This is not new physics — it falls directly out of the model's own
closed-form formula (`R_ref = (ωM)²·RPAN / (RPAN² + (ωL2)²)`, and `M² =
K²·L1·L2` is linear in `L1` when `K` and `L2` are held fixed). **The
sweep's headline "R_eff ≈ 4.2Ω at L=150µH, inside the literature's
2.0–4.5Ω range" is mechanically ≈1.9× the 2.2Ω calibration point, because
150µH is ≈1.9× the 80µH the calibration was performed at — not because of
any independent confirmation that R_eff should be 4.2Ω specifically at
150µH.** The figure landing inside the cited literature range at this
particular `L` is a coincidence of where the range happens to sit, not
evidence for the model.

**A second, independent instance of the same category error was found
alongside it in the same reconciliation.** A separate bus-capacitor-ripple
document reported an expected tank current of "35.4–40A." The 35.4A lower
bound is genuinely derivable from committed hardware — CT ratio 1:100,
burden 4.99Ω, comparator reference 2.500V give a secondary trip current
of 0.501A, so a primary trip of 50.1A peak, RMS-equivalent
`50.1/√2 = 35.42A`. **That arithmetic is correct and the hardware values
are real. The category error is using a protection-trip threshold as an
expected operating current** — a design does not, and should not, run at
the edge of tripping its own overcurrent protection at every use, and
nothing in the source document establishes that it does. The 40A "typical"
upper bound traced to no citation at all in either document. Both bounds
are real numbers, correctly transcribed from their own sources, describing
two different kinds of quantity — a threshold and an unsourced guess —
neither of which is a measured or modeled *delivered* current at the
design's actual operating point.

Two different mechanisms, same consequence: a number that reproduces
perfectly on re-derivation and still answers the wrong question.

## The pattern

**A model's free parameters are only valid at the input value they were
solved against.** Extending a model beyond its calibration point by
holding the calibrated parameters fixed silently assumes the physical
relationship between the calibration target and the swept variable is
exactly the one baked into the model's closed form — here, that `R_eff`
scales linearly with `L1` when it may instead be closer to an
`L1`-independent property of the pan material, coil-pan gap, and
frequency. Neither assumption has been bench-verified; the sweep result
does not discriminate between them, it just mechanically reports whichever
one is baked into how `K`/`L2`/`RPAN` were held fixed.

**A protection threshold and an operating point are different physical
quantities that happen to share units.** A trip current answers "how much
current causes a fault to be declared"; an operating current answers "how
much current flows during normal use." Converting one to the other
(peak-to-RMS, RMS-to-peak) preserves the arithmetic and does nothing to
change which question the result answers. Both errors are invisible on
inspection of the arithmetic alone — the divide is correct, the algebra is
correct — because the mistake is entirely in which quantity was measured
relative to which quantity was needed.

## Guidance

1. **State the calibration point explicitly, next to every value a model
   produces.** "R_eff = 4.2Ω" is an incomplete claim; "R_eff = 4.2Ω at
   L=150µH, calibrated at L=80µH, holding K/L2/RPAN fixed across the
   extrapolation" is a complete one, and makes the gap between calibration
   point and evaluation point visible to the next reader instead of buried
   in a script default.
2. **Before trusting a swept model result at a design's stated operating
   point, check whether the model's free parameters were solved at that
   same point.** If they weren't, the swept result is an extrapolation
   under a specific, usually-implicit assumption (here: linear scaling of
   the reflected resistance with `L1`) — state the assumption, and check
   whether the physically standard treatment of the quantity agrees with
   it. Here it plausibly does not: the literature treats coil-pan coupling
   resistance as closer to an `L1`-independent property of the pan and
   frequency, not the coil's own turn count.
3. **A quantity computed as `R_eff / L` (or any calibration-target /
   swept-variable ratio) being constant across a wide sweep is itself the
   diagnostic, not a reassurance.** Constancy to within 0.2% across a 3.6×
   range of the swept variable is a strong signal that the sweep isn't
   independently confirming anything at each point — it's replaying one
   ratio, fixed at calibration time, at every point.
4. **Before comparing or substituting a protection-trip figure and an
   expected-operating figure, name which one each number actually is.**
   "Trip current, converted to RMS" and "expected operating current at
   rated power" look identical once both are expressed in amps RMS; only
   tracing each back to its own derivation reveals they're not
   interchangeable.
5. **When two independently-reasoned figures for the same physical
   quantity disagree, check whether either was ever independently
   validated, or whether both are artifacts of different assumptions
   applied to the same underlying uncertainty.** Here, neither the sweep's
   20.7A nor the bus-cap doc's 35.4–40A is a bench measurement; the honest
   synthesis is a bracket (20.7–30A) with the open question named — *does
   R_eff scale with L1, or is it closer to an L1-independent pan/frequency
   property* — not a false confidence that either endpoint is correct.

## Why This Matters

Both errors independently reached the same downstream artifacts — OCP-01
trip-margin claims and bus-capacitor ripple-headroom claims — and both
were internally consistent, reproducible, and individually well-cited
before being reconciled. The sweep's "R_eff ≈ 4.2Ω, inside the 2.0–4.5Ω
literature range" reads as confirmation; it is instead a restatement of a
calibration performed at a different inductance, mechanically rescaled.
The bus-cap doc's "35.4–40A" reads as an operating-current estimate; the
lower bound is instead a trip threshold wearing an operating-current
label. Neither number is wrong as arithmetic — both would reproduce
exactly on a second calculation — and neither answers the question a
downstream margin calculation needs answered. The reconciliation's own
verdict states this plainly: the design point is under-specified, and
what would close it is a bench measurement of R_eff at the coil's actual
committed operating band, not a sharper rerun of either existing
spreadsheet.

## When to Apply

- Before trusting any model result at a design's stated operating point —
  confirm the model's free parameters were solved (calibrated) at that
  same point, not at a harness default or an earlier design revision's
  value.
- When a sweep varies the exact variable a model's parameters were
  calibrated against — check whether the parameters were re-solved at
  each swept point or held fixed from the original calibration.
- Before citing "the result falls inside the literature's range" as
  confirmation — check whether the result's position inside that range is
  itself a consequence of where the calibration was performed, not
  independent agreement.
- Before using a protection/trip threshold as a stand-in for an expected
  operating value (or vice versa) — trace each figure back to what it was
  actually derived to answer.
- When two independently-reasoned figures for the same physical quantity
  disagree — check whether either is a bench measurement before assuming
  the truth lies between them.

## Examples

```
# The calibration-point mismatch, in the model's own terms:
K, L2, RPAN solved for R_eff = 2.2Ω  AT  L1 = 80µH   (harness default)
                                          ^^^^^^^^^^ never re-solved
Design's own declared L1 = 150µH     (l_tank_assumed, same-day doc)

Sweep holds K, L2, RPAN fixed -> R_eff(150µH) = 4.196Ω
  R_eff / L1 = 0.02797 Ω/µH at EVERY point from 70µH to 250µH (±0.2%)
  -> the sweep is reporting the calibration ratio, not new information
     at each point
```

```
# The protection-threshold / operating-point conflation:
CT ratio 1:100, burden 4.99Ω, V_ref 2.500V
  -> secondary trip current = 2.500 / 4.99 = 0.501 A
  -> primary trip current   = 0.501 x 100  = 50.1 A (peak)   [TRIP THRESHOLD]
  -> RMS-equivalent          = 50.1 / sqrt(2) = 35.4 A       [still a threshold]

# WRONG: treat 35.4A as the expected tank current at 1800W
# RIGHT: derive the expected operating current from P = I^2 * R_eff at
#         the design's own R_eff, and compare THAT to the 50.1A trip
#         separately, as a margin question -- not as the same number.
```

## Related

- `docs/METHODOLOGY.md` §11, "Calibration inversion" — the standing rule
  this incident sharpens: every model should carry a machine-readable
  `calibrated: true|false` tag and the point it was calibrated at, so a
  sweep across an uncalibrated range is visible as such rather than
  looking like independently confirmed physics at every point.
- `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
  — a sibling category error from the same project: a declared label
  (a net's name; here, a trip threshold) outranking the actual quantity
  (a node's real voltage; here, an operating current) in a downstream
  calculation.
- `docs/evidence/2026-07-27-inductance-range-sweep.md (the reconciliation table is reproduced inline in this doc)` — the full
  reconciliation: the R_eff/L linearity table, the closed-form
  cross-check, the trip-threshold-vs-operating-current analysis, and the
  20.7–30A bracket with its stated falsifier and open question.
- `docs/evidence/2026-07-27-pan-model-correction.md` §1 — the original
  K/L2/RPAN calibration at L1=80µH.
- `docs/evidence/2026-07-27-inductance-range-sweep.md` — the sweep that
  held the 80µH-calibrated parameters fixed across 50–250µH, including the
  150µH design point.
