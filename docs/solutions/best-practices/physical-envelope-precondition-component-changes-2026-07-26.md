---
title: "Physical envelopes are preconditions — two component changes with correct arithmetic and destroyed parts"
date: "2026-07-26"
category: best-practices
module: pcb-hardware-design
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "changing a component value (resistor, shunt, divider) to move a trip point, gain, or threshold"
  - "placing a sense element (shunt, CT, divider tap) on a node whose voltage you inferred from topology rather than measured"
  - "reasoning about a node's voltage or current by analogy to a more familiar circuit topology"
  - "reviewing a design change where the verified math covers only the value being changed, not the part it changes"
tags:
  - physical-envelope
  - precondition
  - current-transformer-saturation
  - voltage-doubler
  - ina240
  - burden-resistor
  - reasoning-by-analogy
  - hardware-precondition
---

# Physical envelopes are preconditions — two component changes with correct arithmetic and destroyed parts

## Context

`docs/METHODOLOGY.md` §3's rule — assert the input, do not assume it — was
written for code and applied only to code until two hardware design changes on
this project showed it applies identically to physical parts. Both changes had
arithmetic that checked out and a physical context that invalidated it:

| Change | Verified | Not verified | Result |
|---|---|---|---|
| **OCP-01**: burden resistor 6.65 Ω → 4.99 Ω to move the trip point | divider math → 50.1 A trip | the current transformer's **47 A** sensed rating | trip placed *above* the CT's range — past 47 A the core saturates and the comparator may never fire |
| **OCP-02**: shunt placed in `DC_BUS_RTN`, reasoning "low side is near ground" | amplifier gain → 2.40 V output | the topology is a **voltage doubler**, whose midpoint is signal ground — so `DC_BUS_RTN` sits at **−170 V** | the INA240 sense amplifier is a −4…+80 V part; it would have been destroyed |

In both cases the number computed was correct. What failed was not checking
whether the part the value gets applied to — the CT core, the amplifier's
input pins — can survive or function at that value. Full write-up:
`docs/METHODOLOGY.md` §5, "Physical envelopes are preconditions."

## Guidance

1. **Before changing any component value, enumerate the operating envelope of
   every part in the signal path** — voltage, current, common mode,
   temperature, frequency — not just the part being changed. A resistor
   change that moves a trip point also moves where every upstream part
   operates; check all of them, not the divider alone.
2. **The trap is reasoning by analogy from a familiar topology.** "Low side is
   near ground" is a true statement about a single-rail bus and a false
   statement about a voltage doubler, where the midpoint is ground and the low
   rail sits at the negative peak — here, −170 V. A topology diagram checked
   once, not re-derived at the moment of placing a sense element, is where
   this fails.
3. **A part's datasheet rating is a precondition on where it can be placed,
   not just how it's driven.** The CT's 47 A sensed-current rating and the
   INA240's −4…+80 V common-mode range are both entries in the same class of
   fact as a function's input precondition in code — assert against them
   before committing the design, not after.
4. **Correct arithmetic does not certify a design change.** Verifying the
   divider equation or the gain equation is necessary and was done correctly
   in both cases; it is not sufficient, because neither equation has a term
   for "and the transformer core stays out of saturation" or "and the
   amplifier's pins stay inside their common-mode range."
5. **Make this a checklist, not a habit.** Per §5's Risk-weighted rigor,
   safety-critical changes (OCP trip timing, isolation-referenced sensing) earn
   full treatment: list every part in the path, list its datasheet limits, and
   check the post-change operating point against each one before layout or
   ordering.

## Why This Matters

Both errors would have shipped a board that either failed to protect against
overcurrent (OCP-01: the trip point sits where the sensor can no longer be
trusted) or destroyed the sensing IC on first power-up (OCP-02: −170 V into a
−4…+80 V part). Neither would have been caught by re-checking the arithmetic
that motivated the change, because the arithmetic was never wrong — the
resistor divider does put the trip at 50.1 A; the amplifier gain equation does
produce 2.40 V for the expected differential. The class of failure is
specifically the boundary between two disciplines — value math and physical
survivability — that a single review pass focused on "does the number come
out right" will not cross.

## When to Apply

- Any resistor, shunt, or divider value change intended to move a trip
  threshold, gain, or setpoint.
- Placing a new sense element (shunt, CT, hall sensor, voltage divider tap) on
  an existing net — verify the net's actual voltage/current range from the
  topology, not from its name (`_RTN`, `_GND`, `_LOW`) or a mental model of a
  similar-looking circuit.
- Any time a design justification says "this is like [familiar topology]" —
  that sentence is the signal to re-derive the actual operating point instead
  of inheriting the analogy's assumptions.
- Before ordering parts or releasing a layout for a change to a protection or
  sensing circuit — safety-critical tier, all applicable envelope checks.

## Examples

The checklist this incident argues for, applied retroactively:

```
Change: OCP-01 burden resistor 6.65 Ω -> 4.99 Ω (target trip: 50.1 A)

Signal path parts and their envelopes:
  - Current transformer: sensed-current rating = 47 A       <- NOT CHECKED
  - Burden resistor: power rating at 50.1 A trip current      checked
  - Comparator: input voltage range at new burden voltage      checked

Verdict: divider arithmetic correct, but trip point (50.1 A) exceeds the
CT's rated range (47 A) -- REJECT, re-derive burden value against 47 A cap.
```

```
Change: OCP-02 shunt placement in DC_BUS_RTN

Topology check:
  - Circuit is a voltage doubler (not a single-rail bus)
  - Midpoint of the doubler = signal ground
  - DC_BUS_RTN (the "low side") = -170 V relative to signal ground  <- NOT
    CHECKED before placement; assumed near-ground by analogy to a
    single-rail design

INA240 datasheet: common-mode input range -4 V ... +80 V

Verdict: -170 V is 90 V beyond the part's rated common-mode range --
REJECT, move sense point or add isolation before this part sees that node.
```

## Related

- `docs/METHODOLOGY.md` §5, "Physical envelopes are preconditions" — the rule
  this doc instantiates, with the same OCP-01/OCP-02 table
- `docs/METHODOLOGY.md` §3, "The Loop Contract" — `input_precondition` as a
  first-class field; this doc is that same discipline applied to hardware
  rather than code
- `docs/hardware/OCP02_DESIGN.md`, `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md` —
  the design documents for the corrected topology
- `docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`
  — the code-side sibling: verifying an input precondition rather than only an
  output metric
