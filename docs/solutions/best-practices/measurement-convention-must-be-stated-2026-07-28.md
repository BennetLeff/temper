---
title: "Measurement conventions must be stated, because mixing them is invisible — centre-to-centre pad pitch reported as edge-to-edge creepage"
date: "2026-07-28"
category: best-practices
module: temper_placer
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "comparing a measured gap, distance, or spacing figure against a threshold without checking what convention (centre-to-centre vs edge-to-edge, peak vs RMS, package vs board) produced the figure"
  - "a table mixes distances measured different ways across different rows without a column stating which"
  - "a component reference in a violation report was resolved by a heuristic (pin-count match, name-similarity match) rather than a direct netlist/footprint lookup"
  - "a distance figure exactly matches a component's own datasheet pitch or pin spacing rather than its physical copper-edge gap"
tags:
  - measurement-convention
  - centre-to-centre-vs-edge-to-edge
  - creepage-measurement
  - component-misattribution
  - pin-matching-heuristic
  - unit-consistency
---

# Measurement conventions must be stated, because mixing them is invisible

## Context

`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §6
re-measured the board's 8 mains↔SELV isolator footprints using a
rectangle-aware, axis-aligned pad model — exact here, since every isolator
footprint is rotated by an exact multiple of 90 degrees — and found that
three of the figures already circulating for this same task mixed two
different measurement conventions without saying so:

| Ref | Reported figure | What it actually is | Real edge-to-edge gap |
|---|---|---|---:|
| `U3` | "7.62mm pad gap" | **centre-to-centre** — exactly the 300-mil DIP row pitch | **6.02mm** |
| `U7` | "7.25mm" | edge-to-edge (correct as reported) | 7.25mm |
| `K2`/`K3` | "6.32mm" | **centre-to-centre** | **3.50mm** |

Creepage is, by definition, a surface distance measured between
conductive parts — i.e. between copper edges, not pad centres. `U3`'s
7.62mm figure is not a measurement error; it is a real, correctly
transcribed number (the datasheet's own 300-mil row spacing) applied to
the wrong question. Substituting it for the copper-edge gap changes the
pass/fail verdict outright: at the disputed 6.5mm creepage figure, `U3`
reported as 7.62mm **passes** (7.62 ≥ 6.5); measured edge-to-edge at
6.02mm it **fails**, missing by 0.48mm. The same substitution at 8.0mm
changes a 0.38mm margin into a 1.98mm shortfall.

The same document notes this is the same class of error as an earlier
incident from a prior session in the same investigation: a 1.27mm gap
figure attributed to component `U27` — the board's MCU — that the prior
session found and debunked. `U27` was reached via a heuristic that
matched on pin number rather than resolving the actual net/footprint from
the board file, and it returned a plausible-looking but wrong component
instead of failing when the direct lookup it should have used was
available. A wrong component reference and a wrong measurement basis are
different mechanisms with the same shape: both substitute a
plausible-looking number for the one the question actually needs, and
both pass every sanity check that doesn't re-derive the number from the
primary artifact.

## The pattern

**Two numbers with the same unit are not automatically the same
quantity.** "7.62mm" and "6.02mm" are both, trivially, lengths in
millimetres; only one of them is the copper-edge gap creepage is defined
against, and nothing about a bare number reveals which convention
produced it. A table that reports distances from several components
without a column stating centre-to-centre vs edge-to-edge (or peak vs
RMS, or package-path vs board-path — the same failure shape recurs across
units, not just this one pair) is not simply incomplete; it is silently
answering two different questions with the same-looking column, and nobody
downstream can tell which answer they received without re-deriving it.

The convention mismatch is especially easy to miss when the wrong-basis
figure happens to equal a real, independently-meaningful number — here,
the component's own datasheet pin pitch. A number that traces cleanly to
a datasheet reads as *more* trustworthy, not less, precisely because it
is real and correctly transcribed; the error is entirely in which
question it was asked to answer.

## Guidance

1. **State the measurement convention in the column header or field name,
   not just in prose once, somewhere upstream.** `gap_centre_to_centre_mm`
   and `gap_edge_to_edge_mm` as two explicit fields prevents exactly this
   substitution; a bare `gap_mm` column does not, regardless of how
   carefully the accompanying text explains which one it is.
2. **When a measured distance exactly equals a component's own datasheet
   pitch or pin spacing, treat that as a signal to check which quantity
   was actually measured**, not as confirmation the figure is correct. A
   DIP's 300-mil row pitch (7.62mm) recurring as a "pad gap" figure is the
   fingerprint of a centre-to-centre measurement, not a coincidence to
   wave past.
3. **Creepage and clearance are edge-to-edge, always — recompute rather
   than reuse a centre-based figure "because it's close enough."** The
   0.48mm and 1.60mm deltas found here were each large enough to flip a
   pass/fail verdict at the candidate thresholds in play; there is no
   creepage/clearance context where the difference between the two
   conventions is safe to ignore.
4. **Resolve component references from the artifact directly (netlist,
   footprint, pad-to-net mapping), never from a heuristic keyed on an
   incidental property like pin count.** A pin-number-matching heuristic
   can return a real, plausible component that is simply the wrong one —
   `U27` (the MCU) instead of whatever component the 1.27mm gap actually
   belonged to — and a plausible wrong answer is more dangerous than an
   explicit lookup failure, because nothing about it looks like an error.
5. **When re-deriving a table that mixes conventions, rebuild every row
   from the same measurement method rather than patching only the rows
   known to be wrong.** The correction here rebuilt all 8 isolators with
   one rectangle-aware, edge-to-edge method, including the two rows
   (`C6`, `PS1`) that turned out unchanged — confirming the method agrees
   with the prior figures where they were already right, not just
   replacing the ones known to be wrong.

## Why This Matters

`U3`'s verdict inverted at the exact threshold under live dispute (6.5mm)
because of a convention mismatch alone — no new physics, no re-measurement
of the actual board, just resolving centre-to-centre against edge-to-edge
for the same physical part. A safety determination built on a table that
silently mixes measurement bases can be internally consistent, arithmetic
ally correct at every step, and still deliver a wrong pass/fail verdict
for a component sitting exactly at the threshold the whole determination
hinges on. This is the same shape as the `U27` misattribution the prior
session already caught: a plausible, correctly-computed number, attached
to the wrong referent (a component, or a measurement basis), passing every
check that doesn't independently re-derive it from the primary artifact.

## When to Apply

- Before trusting any distance/gap/spacing figure against a
  creepage/clearance threshold — confirm it is edge-to-edge, not
  centre-to-centre, package pitch, or any other convention that shares
  units without sharing meaning.
- When building or reviewing a table that reports the same kind of
  quantity (distance, current, voltage) across multiple components or
  measurements — check that every row was produced by the same method,
  not just that every row has a plausible-looking number.
- When a measured figure exactly matches a component's own datasheet
  pitch, pin spacing, or another documented "nearby" number — treat the
  match as a prompt to verify which quantity was actually measured.
- Before trusting a component reference in a violation or measurement
  report that was resolved by a heuristic (pin-count, name-similarity)
  rather than a direct lookup against the netlist or footprint data.
- Whenever a pass/fail verdict sits close to a threshold — re-derive the
  input figure from the primary artifact rather than trusting whatever
  value is already in the table.

## Examples

```
# WRONG — reported without stating the convention, and silently wrong
# for two of three rows in the same table:
U3:    7.62mm   # <- centre-to-centre (300-mil DIP row pitch), NOT the
                #    copper-edge gap creepage requires
U7:    7.25mm   # <- edge-to-edge (this one happens to be right)
K2/K3: 6.32mm   # <- centre-to-centre

# RIGHT — every row from the same, explicitly-named method:
U3:    gap_edge_to_edge_mm = 6.02   (gap_centre_to_centre_mm = 7.62)
U7:    gap_edge_to_edge_mm = 7.25   (gap_centre_to_centre_mm = 9.30)
K2/K3: gap_edge_to_edge_mm = 3.50   (gap_centre_to_centre_mm = 6.32)
```

```
# Why it changes the verdict, at the 6.5mm candidate creepage figure:
U3 @ 7.62mm (centre-to-centre, misread as the gap)  -> PASS  (7.62 >= 6.5)
U3 @ 6.02mm (real edge-to-edge copper gap)          -> FAIL  (6.02 <  6.5, by 0.48mm)
```

## Update, 2026-07-28 (later the same day): a designed number reported as a measured one, retracted

A different creepage figure in this same investigation turned out to have a
sharper defect than a convention mismatch: it was never a measurement at
all. The K2/K3 relay footprint's 9.2mm coil-to-contact creepage (Finder
40.52.7.012.0000, the prior session's own reported figure) was, by that
session's own words, *"a deliberate design choice, not a trace of the
manufacturer's own recommended PCB pattern"* — adopted because the
catalog's dimension drawing "rendered ambiguously" under `pdftotext`
extraction, since the drawing's dimension digits are vector-drawn glyphs
that never entered the PDF's text layer at all (confirmed by grepping the
extracted text for the exact tokens — none appear). **A number designed by
this footprint's own author was relayed onward and reported as verified.**

Resolving it properly needed a different extraction method entirely: the
catalog page (Finder cat. S40EN, p.3) was rendered at 300dpi and
pixel-calibrated two independent ways (two labelled reference-dimension
chains anchored to the same datum; a joint solve against three
independently-detected pin-position pixel lines), agreeing to 11.415
px/mm against a theoretical 300dpi/25.4 = 11.811 px/mm. Both methods
recovered the real pin positions to within 0.5mm of each other.

**Real coil-to-nearest-contact spacing: 5.3mm edge-to-edge** (7.5mm
center-to-center, MEASURED — not the invented 11mm the prior footprint
used), a **2.7mm shortfall against the already-superseded 8.0mm/PD2 target**
and a **7.3mm shortfall against 12.6mm/PD3**
(`docs/solutions/best-practices/check-the-exception-before-the-default-2026-07-28.md`).
The same re-measurement also caught two independent physical defects the
invented geometry had been hiding: the real pin order is **NC–COM–NO**,
not the COM–NC–NO the prior footprint placed (a genuine pad transposition,
not just a distance error), and the real 1.5mm pin diameter needs a 1.7mm
drill — the prior footprint specified a **1.0mm drill that cannot
physically accept this part's real leads at all**.

**This retracts a positive finding rather than confirming one** — the
falsifier here ("the Finder 40.52 can reach the target within its fixed
pinout") did not fire in the part's favor, and the retraction stands
regardless of which pollution degree ultimately governs: 5.3mm fails both
8.0mm and 12.6mm. It is the same family of error this doc already
documents (a number that is real, correctly transcribed, and answers the
wrong question) at one further remove: not two conventions for the same
measurement, but a designed value standing in for a measurement that was
never taken, because the artifact it should have been read from rendered
ambiguously under the first extraction method tried. Full writeup:
`docs/evidence/2026-07-28-pd3-retarget-relay.md`.

## Related

- `docs/solutions/best-practices/check-the-exception-before-the-default-2026-07-28.md`
  — the same-day determination (PD3 governs, 12.6mm is real) that this
  update's retracted relay figure fails against either way.
- `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
  — the sibling lesson: a label (a net's name; here, a bare distance
  figure) that shares surface form with the quantity actually needed, but
  isn't it.
- `docs/solutions/best-practices/calibration-point-must-equal-design-point-2026-07-28.md`
  — a sibling category error from the same week: two numbers agreeing in
  units and arithmetic while answering different questions (a calibration
  target vs. a design point; a trip threshold vs. an operating current;
  here, a centre pitch vs. a copper-edge gap).
- `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §6, §8 —
  the full rectangle-aware re-measurement, the three-row convention-mixing
  table, and the corrected pass/fail table at every candidate threshold.
- `docs/evidence/2026-07-27-creepage-burndown.md` — the wider investigation
  this measurement basis belongs to.
- `docs/evidence/2026-07-27-placement-resolve-after-0805.md` — records a
  same-session designator collision on this board (`safety.latch`
  `U25`→`U26`; `mcu.mcu` `U26`→`U27`) that is exactly the kind of
  reference churn that makes resolving a component by pin-number or
  designator-similarity, instead of a direct netlist lookup, risky here.
