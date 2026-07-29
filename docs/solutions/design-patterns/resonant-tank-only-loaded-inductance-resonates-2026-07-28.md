---
title: "In a coupled resonant tank only the LOADED inductance resonates -- so a wrong coil value and a wrong coupling factor can cancel, and checking either alone proves nothing"
date: "2026-07-28"
category: design-patterns
module: hardware_design
problem_type: design_pattern
component: hardware_design
severity: critical
applies_when:
  - "an induction-heating, wireless-power, or transformer-coupled resonant tank has its operating frequency derived from a coil inductance"
  - "a design comment marks a value as ASSUMED and downstream numbers are computed from it"
  - "evidence cites 'N independent sources converging' on a component value"
  - "a switching frequency, PLL range, or ZVS margin is asserted against a resonance the design never measured"
  - "a coil, transformer, or coupled inductor is still a placeholder component in the schematic"
  - "deciding whether a component discrepancy invalidates a downstream frequency plan"
tags:
  - resonant-tank
  - coupled-inductance
  - loaded-vs-unloaded
  - error-cancellation
  - citation-provenance
  - zvs
  - assumed-values
---

# In a coupled resonant tank only the LOADED inductance resonates -- so a wrong coil value and a wrong coupling factor can cancel, and checking either alone proves nothing

## Context

`elec/src/main.ato:80` states the switching frequency plan and marks its own
input as an assumption:

> at an ASSUMED coil L=150uH ... ratio~=1.25 over that assumption's K=0.79
> loaded resonance (37.58kHz) ... **This number is CONTINGENT on L=150uH**

`elec/src/modules.ato:463` shows why it is an assumption: the coil is
`inductor_conn = new Resistor`, `mpn = "CUSTOM_LITZ_COIL"`. A placeholder, not
a specified part.

On 2026-07-28 an investigation found `docs/evidence/2026-07-27-inductance-range-sweep.md`
asserting that three independent sources measure **47-50 uH**, and concluding
"the design is not fab-ready on the L=150uH assumption". Taken at face value
that is a 3x error in the quantity the entire frequency plan rests on -- and it
was taken at face value, including by this author, and reported upward as a
finding before the citations were checked.

Both halves of that turned out to be wrong, in opposite directions, and the
combination is the lesson.

## Half one: only the loaded inductance resonates

A flat induction coil with a ferrite-backed pan on it is a coupled system. The
inductance that sets `f_res = 1/(2*pi*sqrt(L*C))` is not the coil's free-air
inductance -- it is the **loaded** inductance after the workpiece couples in.

Both candidate models produce the same loaded value:

| model | L unloaded | coupling factor | L loaded | f_res @ 300 nF |
|---|---|---|---|---|
| `main.ato` assumption | 150 uH | 0.399 | **59.9 uH** | **37.6 kHz** |
| candidate real coil | 88 uH | 0.68 | **59.8 uH** | **37.6 kHz** |

`main.ato` states `f_res_loaded = 37.58 kHz`. Both reproduce it to within 0.2%.

The coil assumption is ~1.7x too high and the assumed coupling is ~1.7x too
strong in the other direction. **The errors cancel**, because only their product
enters the physics. A reviewer who checked the coil value alone would report a
1.7x error and be right about the number and wrong about the consequence. A
reviewer who checked the coupling alone would do the same. Only the product is
falsifiable against the design's own stated resonance.

This also dissolved a second alarm: the same sweep document reported "ZVS lost
below 97 uH". That threshold was computed with a coupling ratio taken from a
90-150 kHz characterization and applied to a 47 kHz design.

## Half two: the three independent sources were one

Read against the primary datasheets:

1. **Infineon AN235020** -- a genuine 2 kW cooktop coil, but characterized
   **only at 90-150 kHz**, for a 100-140 kHz inverter. Not this design's band.
2. **Wurth 760308101303** -- read verbatim from Wurth's own datasheet: a
   **WE-WPCC Wireless Power Transfer Receiver Coil**, 26.3 mm diameter,
   1.31 mm thick, **1.5 A max, 20 W typical**, inductance specified at
   125 kHz / 10 mA. A Qi charging-pad coil. It is off by roughly **90x in
   power** and **7x in diameter** from a 2 kW cooktop coil.
3. **A bench demonstration coil** -- which was itself *cross-checked against
   source 2*. It validates that source rather than corroborating it
   independently.

One partially-applicable source, presented as three converging ones. The
convergence was an artifact of the sources sharing an ancestor and of a
wireless-charging part being admitted to a cooktop comparison on the strength
of its inductance value alone.

## Why this shape is dangerous

Neither half is detectable by reading the conclusion. The evidence document was
well-written, cited real datasheets, and reached a plausible verdict. The defect
was that **a value was compared across applications where it means different
things** -- 47 uH in a 20 W Qi receiver and 47 uH in a 2 kW cooktop coil are
the same number describing incomparable objects -- and that **a compensating
pair of errors was audited one factor at a time**.

The failure mode is confident wrongness in *both* directions: first the design
looks broken when it is not, then the "fix" (a 3x capacitance change) would
have broken it.

## What to do instead

**Check the product, not the factors.** In any coupled resonant system, derive
and verify the quantity that actually appears in the resonance -- `L_loaded`,
or equivalently `f_res` itself. Verifying `L_unloaded` or `k` in isolation
proves nothing about the design, and each in isolation can look alarming while
the system is fine.

**Require the frequency band with the inductance.** A coil inductance without
the frequency it was measured at is not a specification. AN235020's 48 uH is
real and correct for 90-150 kHz; quoting it at 47 kHz imports a number from a
regime where the coupling, skin depth, and pan impedance all differ.

**Check whether cited sources share an ancestor.** "Three independent sources"
is a strong claim that mostly gets asserted rather than tested. Two of three
here traced to the same part. The test is cheap: read what each source actually
measured, not what value it reported.

**Match the application before the parameter.** A part is admissible to a
comparison when its *application* is comparable, not when one of its numbers
is. Power class, physical scale, and operating frequency are the gates; the
inductance is what you read afterwards.

**Prefer a spec plus an acceptance test over a part number** when the class has
no published parts. No orderable coil in this class publishes an inductance.
The workable form is `L = 88 uH +/-10% @ 40 kHz` **with** `L_loaded >= 0.60 *
L_unloaded` as an incoming test -- because the loaded ratio is the parameter
that actually matters and no vendor will state it.

## Current recommendation (2026-07-28), and its contingency

- **Coil**: specify `L = 88 uH +/-10% @ 40 kHz`, acceptance test
  `L_loaded >= 0.60 * L_unloaded`.
- **Tank capacitance**: **keep 300 nF** (committed in both simulation
  harnesses), or move to 470 nF to absorb a wider coil tolerance.
- **PLL floor**: raise it -- `PLL_MIN_FREQ_HZ = 30 kHz` sits 7.6 kHz *below*
  loaded resonance, so the firmware's legal range includes a capacitive,
  hard-switching region. The floor should be derived from `f_res`, not
  hand-set.
- **Tank capacitor**: re-source. The present part is ~2.0x over its permissible
  AC current at 47 kHz; see
  `docs/solutions/best-practices/verify-the-binding-axis-not-the-headline-rating-2026-07-28.md`.

**This recommendation is contingent and should be re-derived when the coil is
real.** The 88 uH and the 0.68 loaded ratio are both **chart readings of a coil
with no published part number**. If 0.68 is wrong, the cancellation argument
above fails and the frequency plan genuinely does need revisiting. The
recommendation is the best-supported position available today, not a settled
one.

## Detection

There is no gate for "these two assumptions cancel", and there should not be --
it is a review discipline, not a mechanical check.

What *is* mechanizable, and is being added, is the downstream invariant: the
PLL's minimum frequency must be derived from the declared `L`, `C`, and
coupling rather than hand-set, so it cannot drift below resonance silently. A
constant that encodes a physical relationship should be checked against that
relationship, not maintained by hand -- that is what turned a 7.6 kHz
hard-switching window into something nobody noticed until an unrelated
investigation walked past it.
