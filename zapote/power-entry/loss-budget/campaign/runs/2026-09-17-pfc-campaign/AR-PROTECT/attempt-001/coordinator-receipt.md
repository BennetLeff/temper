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
| Source / timescale | AC mains, ms | DC bank, **~100 µs** (τ = 94.1 µs) |
| Limiting impedance | line/source — **unknown** | not defensibly modelled |
| Energy | **null** | **179.238 J** |
| Loop | mains → bridge → U8 → shorted U9 → **U12** → back | **caps → shorted U10 → U9 → caps, bypassing U12** |
| Interrupter | F1 (coordination unestablished) | **none** |

A **crowbar diverts, it does not interrupt**. Gate shutdown cannot open the
line loop either: with all drivers off the body diodes conduct, so the stage
reverts to a passive-diode path. And by conducting through channels rather than
~2 diode drops, the active bridge **lowers** the loop impedance and **raises**
the prospective fault current — the protection problem is worse than for the
passive bridge it replaces.

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

## Recommendation

1. Add a **DC-rated, semiconductor-grade interrupting element in series with the
   internal discharge path**, coordinated to carry ~4.5 A and clear a ~100 µs
   multi-kA pulse; or a bus crowbar **plus** a coordinated series interruption
   and energy-handling path.
2. For the line-fed loop, establish **F1's total clearing behaviour** at matching
   conditions and confirm the device stays inside its SOA; otherwise a faster
   line-side element, or an active trip **with a series interrupter**.
3. Do not credit the controller with interruption.

## Single gating input

**The AC source/line impedance at the fault**, jointly with **F1's total
clearing behaviour** at matching conditions. Both are needed before the
line-fed loop can be called protected, and the line impedance is also what would
let the active bridge's survival be assessed rather than left null.

The ~20 W nominal opportunity is unchanged.
