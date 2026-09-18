# Coordinator receipt — AR-PROTECT attempt-001

Date: 2026-09-18
Attempt: `.../runs/2026-09-17-pfc-campaign/AR-PROTECT/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** All six completion criteria met.

## Admission

Dispatch ADMITTED; handback **NOT COUNTED AS A VALIDATED RUN** (no checker
issued, per `ADMISSION.md`). Retained as evidence.

## The finding that matters

**No adequate protection exists on the current board for the internal
capacitor-discharge loop.** The two fault classes are genuinely different, and
only one of them has an interrupting element:

| | (i) line-fed switch short | (ii) internal cap discharge |
| --- | --- | --- |
| Source / timescale | AC mains, ms class | DC bank; **timescale unresolved** — an illustrative RC calc gives 94.1 µs, but it assumes the normal-device 42 mΩ describes a destructive fault |
| Limiting impedance | line/source — **unknown** | not defensibly modelled |
| Energy | **null** | **179.238 J** |
| Loop | mains → bridge → U8 → shorted U9 → **U12** → back | **caps → shorted U10 → U9 → caps, bypassing U12** |
| Interrupter | F1 (coordination unestablished) | **none** |

A **crowbar diverts, it does not interrupt**. For the line-fed loop, gate
shutdown cannot open it: with all drivers off the bridge's body diodes conduct,
so the stage reverts to a passive-diode path. And by conducting through channels
rather than ~2 diode drops, the active bridge **lowers** the loop impedance and
**raises** the prospective fault current — the protection problem is worse than
for the passive bridge it replaces.

**The internal loop is a separate, device-state-dependent case**, because it
requires `U9` to conduct. Two cases must be kept apart:

- **`U9` healthy:** it may potentially be commanded off after `U10` shorts,
  subject to detection, latency and turn-off stresses — which are unquantified.
  The loop may therefore be interruptible by the controller, on a latency budget
  nobody has established.
- **`U9` already failed short:** it cannot be turned off, and nothing else in the
  loop interrupts it.

The report's blanket claim that shutdown cannot open "a conducting U9" collapsed
those two cases; the receipt repeated it. The shunt's inability to sense the loop
is a real problem in **both** cases and is unaffected by this correction.

## Active-bridge survival: null, correctly

MOSFET survival is **INDETERMINATE**: the reference device has an ID,pulse of
495 A and E_AS 582 mJ but **no I²t and no short-circuit withstand**, and its SOA
diagrams were not digitised. Survival needs the prospective current and duration,
which the unknown line impedance prevents. The GBJ passive bridge's 350 A /
510 A²s were **not** transferred to it.

The TEA2209T has **no overcurrent detection** — gate pull-down, a start-up D-S
protection, a 22 V gate and COMP disable only. It must not be credited with
interruption.

## What was left null, and why

Line impedance; line-fault current, duration and energy; internal-loop peak
current; the U9/U10 dissipation split; F1 total clearing; MOSFET survival;
controller post-fault response. Each is null because an input is not
established, not because the number was inconvenient — which is the stop rule
working.

## The loop-consistency gate

Passing checker output retained, plus a **negative control**: the withdrawn
model (`U9` + `U12`) correctly reports `FAULT LOOP INCONSISTENT` under the
Rust-backed checker. The checker's claim stays narrow — connectivity only, not
a conductive path, device state, direction or distribution.

## Recommendation: the gap is identified, not resolved

AR-PROTECT establishes that **no protection has been demonstrated** for the
internal loop. It does not establish a protection design.

1. "Add a DC-rated, semiconductor-grade interrupting element in series with the
   internal discharge path" is an **architectural proposal, not a result**: no
   device is selected and no coordinated clearing analysis demonstrates
   interruption of a multi-kA pulse.
2. The **~4.5 A average bus current is not a sizing basis** for an element that
   must carry pulsed charging current and clear a fault pulse. Sizing needs the
   pulse waveform and the prospective current, both unresolved above.
3. For the line-fed loop, establishing **F1's total clearing behaviour** at
   matching conditions remains the first step, with a faster line-side element or
   an active trip **with a series interrupter** as alternatives.
4. Do not credit the controller with interruption.

The next step is **one concrete protection circuit with named parts and explicit
fault cases**, not a further proposal list.
3. Do not credit the controller with interruption.

## Single gating input

**The AC source/line impedance at the fault**, jointly with **F1's total
clearing behaviour** at matching conditions. Both are needed before the
line-fed loop can be called protected, and the line impedance is also what would
let the active bridge's survival be assessed rather than left null.

The ~20 W nominal opportunity is unchanged.
