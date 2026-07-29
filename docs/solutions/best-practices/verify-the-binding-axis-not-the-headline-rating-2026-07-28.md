---
title: "A part verified on every axis you checked can still be wrong -- identify which axis binds before calling the selection correct"
date: "2026-07-28"
category: best-practices
module: hardware_design
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "selecting or replacing a component and checking it against its datasheet's headline ratings"
  - "a part is used outside the application its datasheet's front page assumes -- high frequency, continuous duty, resonant current, elevated ambient"
  - "a correction changes a component or footprint and reports the electrical parameters as 'unchanged' or 'now true'"
  - "a datasheet figure carries a footnote qualifying the conditions it was measured under"
  - "a lead form, package option, or land pattern is chosen to fix a clearance/creepage/isolation problem"
  - "an agent or engineer reports a part 'verified' without naming which parameter was the constraint"
tags:
  - component-selection
  - binding-constraint
  - datasheet-footnotes
  - ac-current-rating
  - creepage-vs-clearance
  - thermal-not-dielectric
  - verification-scope
---

# A part verified on every axis you checked can still be wrong -- identify which axis binds before calling the selection correct

## Context

On 2026-07-28 the resonant tank capacitors (`c_tank1`, `c_tank2`) were found
to carry an MPN encoding **0.015 uF** where the circuit requires **0.15 uF**
each -- a 10x error, with the land pattern drawn to match the wrong MPN
rather than the design. The correction (PR #401) replaced the part with
`FKP1T031507G00JSSD`, read verbatim from WIMA's FKP 1 ordering table, and
reported:

> Value, tolerance, dielectric and 1600 V rating unchanged -- the rating is
> now true rather than contradicted.

Every word of that is correct. The capacitance is right, the voltage rating
is right, the dimensions match the assigned land, and the MPN is a real
catalogue row. A follow-up verification pass (PR #402) then found the part
is **~1.7x over its permissible AC current** at the operating frequency.

Nothing in the first pass was wrong. It verified capacitance, DC voltage,
package dimensions, and catalogue existence -- and stopped, because those are
the fields a capacitor selection normally turns on. It never asked which
parameter was actually the constraint here.

## The measurement

At the committed 1.8 kW operating point, from this repo's own simulation:

- tank current **20.74 A RMS**, two capacitors in parallel -> **10.37 A RMS
  each**
- WIMA's permissible-AC-current chart for 0.15 uF / PCM 37.5 at 47 kHz:
  **~6 A**
- **~1.73x over**, and ~2.7x at the pre-correction 35 kHz operating point

Cross-checked two ways: `I = V * 2*pi*f*C` reproduces the simulator's
331.05 V peak to 0.08%, and the same ratio falls out independently on the
voltage axis (234.2 Vrms against 135.5 Vrms permissible), as it must.

The failure mode is **thermal, not dielectric**. The part will not flash
over -- it will run hot. FKP 1 in this case size is a *pulse* capacitor; a
1.8 kW induction tank is continuous high-frequency duty.

## Why the checked axes did not bind

**The DC rating had 4.8x margin.** 1600 VDC against a ~331 V peak. Verifying
it produced a large, reassuring number that described a constraint nowhere
near active.

**The AC rating on the datasheet's front page was unusable, and said so.**
The headline "650 VAC" figure carries the footnote `* AC voltages:
f <= 1000 Hz`. At 47 kHz it does not apply. A footnote that narrows the
conditions of a headline figure is the datasheet telling you the figure is
not for your application; reading the number and skipping the footnote
inverts that.

**The binding parameter was on a chart, not in a table.** Permissible AC
current versus frequency is published as a curve. It requires knowing the
operating frequency and the RMS current before you can read it -- that is,
it requires having identified it as the constraint first. Table values invite
verification; curves require intent.

## The same shape, twice more, the same day

This is not a one-off. Two other corrections in the same 24 hours fixed a
parameter that was not the one under test:

1. **`H11L1` -> `H11L1TVM` (PR #401).** The `T` lead form was chosen to fix
   an isolation-barrier shortfall. It raises **clearance** from 7 mm to
   10 mm -- and leaves **creepage** at >=7 mm, because creepage runs over the
   package body surface that a lead bend does not alter.
   `check_isolation_keepout.py` requires **8.0 mm creepage**. The board
   geometry after the change measures 8.560 mm, but the component standing on
   it guarantees only 7 mm. *After the fix, the weakest element in the barrier
   is the component, not the board.*

2. **The 1600 V rating reported as "now true".** True, and irrelevant. A
   correction that restores accuracy on a non-binding axis reads as
   reassurance and carries none.

Three instances, one shape: a parameter was verified, improved, or corrected,
and it was not the parameter that decides the outcome.

## What to do instead

**Name the binding constraint before verifying anything.** For a passive in a
resonant tank that is RMS current at the operating frequency, not voltage. For
an isolator crossing a safety barrier it is creepage, not clearance. For a
part in continuous service it is dissipation, not peak withstand. Write the
constraint down first; then the verification has a target.

**Treat a datasheet footnote that narrows conditions as a redirect.** If the
headline figure is qualified `f <= 1000 Hz` and you operate at 47 kHz, the
headline figure is not merely inapplicable -- its existence is a signal that
the relevant figure lives elsewhere in the document, usually as a curve.

**Report which axis was checked, not just that the part was verified.**
"Verified: capacitance, DC voltage, dimensions, catalogue existence" is an
honest and useful claim. "Verified" alone is not, because it reads as
covering the axis that mattered whether or not anyone looked at it.

**A part's series encodes its duty.** Pulse-rated, general-purpose, and
continuous-duty variants of the same value and voltage exist precisely
because the current and thermal envelopes differ. Matching value and voltage
selects a *row*; matching duty selects the *table*.

## What this does NOT invalidate

The **300 nF total** tank value is settled and was established
independently -- both simulation harnesses commit to `C_TANK_F = 300e-9` as
fixed, and the 47 kHz switching plan follows from it. The current finding
concerns the part *family and case size*, not the value. Conflating the two
would reopen a question that is closed.

The **land-pattern corrections stand**: C6, U3 and U7's isolator separations
moved from 3.200/6.020/7.250 mm to 8.000/8.560/8.100 mm against an 8.0 mm
requirement. Those were real fixes on the axis that binds for board geometry.
U3's remaining exposure is the *component's* creepage, a different quantity
measured on a different object.

## Detection

There is no gate for this today, and a naive one would be worse than none:
checking every part against every datasheet parameter requires machine-readable
datasheets this project does not have, and would produce noise that gets the
check disabled.

What is tractable, and what this project already does elsewhere, is to record
the **operating point** alongside the selection -- the tank's RMS current and
frequency live in `simulation/harness/run_zvs_sweep.py` and were what made
this finding possible in an afternoon. A selection rationale that cites the
operating point invites the next reader to check the right axis; one that
cites only value and voltage does not.

## Caveat on this finding's own evidence

The ~6 A permissible-current figure was **read off a rendered chart**, not a
table. The agent that produced it named that as its weakest link: +/-1 A does
not change the verdict, +/-5 A would. Before re-sourcing on the strength of
it, confirm the figure from a table or from the manufacturer directly. The
lesson above does not depend on the exact number; the part decision does.
