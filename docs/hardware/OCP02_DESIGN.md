# OCP-02 — Secondary Overcurrent Protection: Design

**Date:** 2026-07-26
**Gate:** OCP-02 — secondary OCP, **55–65 A, <5 µs** (`docs/STRATEGY.md`)
**Status:** designed, **not implemented** — one blocker, stated below.

OCP-02 currently has **no circuit**. `elec/src/*.ato` contains exactly one
`OCPComparator`, which serves OCP-01 via the tank current transformer.
`docs/hardware/BOM.md:129–133` already costs the intended parts — a shunt, an
`INA240` differential amplifier and an `LM393` comparator — for a circuit that
was never wired.

## Topology

Redundancy is the point: OCP-02 must fail independently of OCP-01. It uses a
**different sensing element** (resistive shunt, not a current transformer) at a
**different location** (DC bus return, not the resonant tank), so a single
sensor failure cannot disable both.

```
DC_BUS_RTN ──[ R_SHUNT 2 mΩ ]── GND
                  │  │
                IN+  IN−
              ┌───────────┐
              │  INA240A1 │  G = 20, REF1/REF2 → GND
              └─────┬─────┘
                    │ 2.40 V at 60 A
                 ┌──┴──┐  INP
        3V3 ─[3.74k]─┬─ INN ── comparator ──► fault_any_or (spare input)
                  [10k]
                    │
                   GND
```

## Component values

| Element | Value | Derivation |
|---|---|---|
| `R_SHUNT` | **2 mΩ**, 1%, 2512 | BOM's `WSLP25122L000FEA` |
| `U_DIFF` | **INA240A1**, G = 20 | BOM's `INA240A1QPWRQ1` |
| `r_ref_top` | **3.74 kΩ**, 1% | sets V_ref = 2.402 V |
| `r_ref_bot` | **10 kΩ**, 1% | |

Trip current:

```
V_shunt = I × 2 mΩ          60 A → 120 mV
V_out   = V_shunt × 20      60 A → 2.400 V
V_ref   = 3.3 × 10/13.74  =       2.402 V   →  trip 60.0 A
```

Worst case over ±1% shunt, ±1% divider and INA240A1 gain error: **59.0–61.1 A**,
comfortably inside the 55–65 A window.

## Two constraints that would be fatal if missed

**1. ~~The shunt must be LOW-SIDE.~~ — THIS WAS WRONG. See the correction
below.** The original claim was that placing the shunt in `DC_BUS_RTN` keeps
the INA240's common mode near ground. It does not.

**2. The comparator should be TLV3201, not the LM393 the BOM costs.**

| | Delay | Total with INA240 (0.875 µs rise @ 400 kHz) |
|---|---|---|
| LM393 | ~1.3 µs typ, to ~3 µs | 2.2 – 3.9 µs — **tight against 5 µs** |
| TLV3201 | 40 ns | **0.92 µs — comfortable** |

`TLV3201` is already the comparator for OCP-01, OVP-01 and THM-01/02, and
already exists as a component in `components.ato`. Using it here consolidates
the part count *and* buys 4 µs of margin. The LM393 line in the BOM should be
retired with the rest of the class-A reconciliation.

## Shunt dissipation

| Condition | Power | vs 3 W rating |
|---|---|---|
| 15 A continuous | 0.45 W | fine |
| 60 A at trip | 7.2 W | **2.4× rated — transient only** |

The latch cuts PWM within microseconds, so the 7.2 W is a pulse, not a
steady state. Confirm the part's pulse rating; the WSLP2512 family is designed
for this, but it should be checked rather than assumed.

## Fault integration

`fault_any_or` (`SN74HC4075`, triple 3-input OR) is the natural entry point.
THM-02 has just taken `C1`, which was tied to GND. The remaining spare inputs
on gates 2 and 3 of that package should be surveyed before adding OCP-02 — if
none is free, a fourth OR input is needed, and that is a real part addition
rather than a free one.

## CORRECTION 2026-07-26 — the sensing domain is wrong

**The INA240 pinout blocker cleared, and implementation immediately exposed a
worse error in this document.**

Pinout, verified from two TI datasheets read directly (SBOS662A for the INA240,
SBOS808E for the `-Q1` grade matching `INA240A1QPWRQ1`), identical in both:

| Pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| | NC | IN+ | IN− | GND | VS | REF2 | REF1 | OUT |

**The design's core assumption is false.** This document claimed a low-side
shunt in `DC_BUS_RTN` keeps common mode near ground. This is a
**voltage-doubler** topology:

- `main.ato:247` — `power_return ~ power_in.dc_bus.gnd_ref  # Doubler midpoint = power return`
- `main.ato:283` — `power_return ~ gnd  # Single-star-point ground join near doubler caps`
- `main.ato:254` — `dc_bus_plus` is the **+170 V half-bus**

Signal ground **is** the doubler midpoint. `DC_BUS_RTN` therefore sits at
roughly **−170 V** with respect to it, not ~0 V. An INA240 referenced to signal
ground would see ~170 V of common mode against a **−4 V to +80 V** limit and be
destroyed.

"Low side" on a doubler is not "near ground". That was the error.

**Current state.** `component INA240A1` and `module SecondaryOCPComparator` are
committed with the verified pinout and the correct values — the electrical
design (2 mΩ, G=20, 3.74 k/10 k, 60.0 A, 59.0–61.1 A worst case) is unchanged
and still correct. **Neither is instantiated**, and the shunt splice has been
removed from `main.ato`, so nothing destructive is buildable.

**Options for the sensing domain**, all topology decisions rather than value
changes:

| Option | Trade |
|---|---|
| Shunt at the doubler midpoint (`power_return`) | Common mode ~0 V, INA240 works as designed — **but that node is the tank return, which erodes the independence from OCP-01 that is OCP-02's whole purpose** |
| Isolated amplifier (`AMC1300`, `ACPL-C79A` class) | Preserves the sensing location and the independence; adds an isolated bias rail and cost |
| High-common-mode current-shunt monitor | Needs a part rated well beyond ±170 V; check availability before assuming one exists |

> **SUPERSEDED 2026-07-27 (`15b9a33b`) — capacity only.** The "no spare OR
> input" finding below was true of the then-two fan-in packages. A third
> `SN74HC4075DR` (`SafetyInterlock.fault_or3`) has since been added and
> `fault_or3.B1` is a real, reachable SET-path input **reserved for
> OCP-02** — see `docs/hardware/UVL02_DESIGN.md` SS7.2. OCP-02 is still not
> wired, but the reason is now solely the sensing-domain blocker above, not
> fault-tree capacity. Wiring OCP-02 into working aggregation logic while
> its upstream INA240 cannot work would look connected on inspection while
> never being able to assert.

**Second finding: there is no spare OR input for the fault.** Every input on
`fault_or` and `fault_any_or` in the latch SET path is occupied. `fault_or`
gate 3 is free but its output drives nothing; `fault_any_or` C2 looks free but
sits on the reset-qualifier path, so using it would block reset without ever
tripping the latch — worse than leaving it unwired. Adding OCP-02 to the fault
chain therefore needs a real logic addition, which is a decision for a human.

## The original blocker (now cleared)

**The INA240 pinout could not be verified.** The TI datasheet PDF fetch timed
out and SnapEDA reports "No pinout data available" for the part. Writing a
component definition with guessed pin numbers would produce a board that
cannot work, so no `component INA240A1` has been added.

To finish this: open the TI INA240 datasheet, read the 8-pin TSSOP (PW)
pin-configuration table, and add the component. Everything else above —
topology, values, tolerances, timing budget, the low-side constraint — is
settled and does not depend on it.

## Verification once built

Extend `simulation/harness/` following the OCP-01 pattern: ramp the shunt
current 0 → 80 A, measure the comparator trip, hand-check against
`V_ref / (G × R_shunt)`. The `TLV3201_ngspice.lib` model has no timing model,
so the <5 µs budget stays **UNMEASURED** in simulation and must come from
datasheet delays summed across the chain, then confirmed on the bench.
