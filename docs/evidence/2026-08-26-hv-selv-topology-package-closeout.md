---
title: HV-to-SELV body-free topology and package closeout
date: 2026-08-26
status: measured
---

# HV-to-SELV body-free topology and package closeout

## Decision

Move R43 once, from the fault-source region to the input it serves at U24. Do
not continue searching for local R4 positions. R4 now requires a floorplan or
topology change, and certification-lab review remains the final step after
that internal design work is complete.

This is not an open-ended placement campaign. Each candidate had to improve
the exact cross-domain pair set without adding a DRC category, a body overlap,
or routed-pad endpoint drift. R43 passed that contract. The R4 candidates did
not.

## Accepted: place the R43 pull-up at its consumer

R43 is the +3V3 pull-up for `RTD_HW_FAULT`. Replacing the open-drain fault
interface with push-pull would weaken the fail-safe/Ioff behavior, so the
topology was retained. Moving the pull-up from `(41.54, 187.57)` to
`(27.0, 197.4)` places the SELV bias at its consumer-side interface near U24.

The regional evaluator measured, before acceptance:

| metric | baseline | candidate |
|---|---:|---:|
| exact HV-to-SELV pairs below 12.6 mm | 90 | 86 |
| KiCad DRC errors | 406 | 405 |
| KiCad DRC warnings | 402 | 402 |
| new exact pair | 0 | 0 |
| routed-pad endpoint drift | 0 | 0 |

The four removed exact pairs all involved R43. No different cross-domain pair
replaced them.

## Rejected: package-only R4 replacement

The official Vishay PR02 axial family supplies the required 22 kohm, 2 W,
500 V class in a roughly 9.9 x 3.9 mm body. Both tested horizontal footprints
failed the regional contract:

- 15.24 mm pitch at the original region overlapped U5 and added a warning.
- A shifted 15.24 mm placement introduced a new cross-domain pair.
- 12.70 mm pitch also overlapped U5.

The larger package can provide useful terminal spacing, but the present local
floorplan has no collision-free site for it. Package substitution alone is
therefore rejected, not left as another nudge to try.

## Rejected locally: split R4 chain

A source-level experiment replaced R4 with a 10 kohm + 12 kohm series chain,
using active TE CRGP 2512 2 W parts and an explicit HighVoltageSignal
midpoint. The electrical build and assertions passed with 169 components.

Two deliberately distinct regions were evaluated:

- `(115, 180)` / `(123, 180)` removed seven exact pairs and added none, but
  collided with `discharge.r_dis2a` and added clearance debt.
- `(76, 110)` / `(84, 110)` removed seven exact pairs and added none, but
  collided with tank capacitor C26 and added warnings.

The two-region search budget was then exhausted. Continuing to sample nearby
coordinates would be the ad-infinitum nudge pattern this work is intended to
avoid. The split-chain concept remains viable only as part of a full
floorplan/routing change with the surrounding functional block in scope.

## Instrument correction found during the experiment

The first split-chain build renumbered references, making unchanged pad pairs
look removed and newly introduced when compared by refdes. Refdes is not a
stable component identity across a netlist rebuild. The evaluator now maps
board references through KiCad `Sheetpath` before the Rust-owned Pareto
comparison. Tests pin both single-pad and two-sided pair normalization.

This changes only the thin board-format adapter. Candidate acceptance remains
owned by `temper-quality-oracle` in Rust.

## Remaining internal work

R43 is closed by a bounded, functional relocation. R4 is explicitly escalated
to a floorplan/topology redesign; it is not permission for further isolated
placement attempts. The certification package must not be sent until that
redesign, routing, and internal verification are complete.
