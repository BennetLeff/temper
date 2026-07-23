---
title: "fix: Grounding architecture and isolation barrier — P0-1, S1, S3"
type: fix
status: completed
date: 2026-07-15
origin: docs/audits/2026-07-15-atopile-electrical-design-audit.md
depends_on: []
blocks: [2026-07-15-004, 2026-07-15-005, 2026-07-15-006, 2026-07-15-007]
---

## Shipped

**Merged in [PR #214](https://github.com/BennetLeff/temper/pull/214) on 2026-07-16.** The fix for this plan shipped as part of the comprehensive atopile audit remediation (`fix(elec): resolve 8 P0/P1 electrical design bugs from atopile audit`). See the PR body's per-plan table for the specific changes attributable to this plan.

# fix: Grounding Architecture and Isolation Barrier

## Summary

The current design has three grounding bugs that share a root cause — system
logic/signal ground is directly connected to AC neutral through the
voltage-doubler midpoint. This causes:

1. **P0-1:** 185V across the UCC21550 low-side driver VDDB-VSSB pins (25V abs
   max) because VDDB is referenced to logic ground (+15V) while VSSB is tied to
   hv_minus (-170V ref logic ground).
2. **S1:** The user-touchable RTD food probe rides on logic ground = AC neutral.
   A reversed AC plug or broken neutral puts line potential on the probe.
3. **S3:** 25A resonant tank return current flows through the logic-ground
   netlist net, giving the autorouter permission to merge power and signal
   returns.

The ADUM1250 I2C isolator was defined (`components.ato:267-284`) and imported
(`modules.ato:47`) but never instantiated — the isolation barrier was planned
and dropped.

## Problem Frame

### Current net chain (the root of all three bugs)

```
modules.ato:489     ac_n ~ dc_bus.gnd_ref
main.ato:223        power_in.dc_bus.gnd_ref ~ gnd
main.ato:341        mcu.power.gnd ~ gnd
main.ato:266        tank.out ~ gnd
main.ato:247-248    hb.power_15v.gnd ~ gnd
```

AC_N = gnd_ref = gnd = MCU.GND = tank return = 15V rail return.

### What the architecture must become

```
AC Neutral ──┬── dc_bus.gnd_ref (midpoint of doubler caps)  ← high-current node
             │
             └── [Y-cap / isolation barrier] ── PE (earth)
                                                  │
              (NO direct DC connection to signal/logic ground)
              
Signal/logic ground (gnd) ── isolated SELV domain ── MCU, sensors, relays
              
Tank return ─── dc_bus.gnd_ref (dedicated high-current return)
              
Gate driver low-side ─── supply referenced to hv_minus, NOT to logic gnd
```

## Scope Boundaries

### In scope
- Decide the grounding architecture: whether the control side becomes an
  isolated SELV domain (recommended) or the RTD probe gets reinforced
  isolation at the sensor interface.
- Redesign the low-side gate-driver supply to be referenced to hv_minus
  (isolated aux winding, bootstrap from hv_minus, or isolated DC-DC module).
- Separate the tank return from logic ground in the netlist — route to
  dc_bus.gnd_ref with a single star-point join if needed.
- Instantiate the isolation barrier (ADUM1250 or equivalent) between the MCU
  and any user-accessible circuits if keeping the non-isolated topology.
- Add PE (protective earth) bonding through Y-cap or direct connection at the
  doubler midpoint.

### Deferred
- Full IEC 60335-1 compliance certification (this plan designs the compliant
  architecture; a certified lab must sign off).

### Out of scope
- EMI/surge front-end component selection (separate plan 007).
- Individual BOM part number fixes (separate plan 008).

## Implementation Units

### U1. Grounding architecture decision

**Goal:** Pick the isolation strategy and document it as a one-page decision
that drives all subsequent edits.

**Options to evaluate:**
- **A — Isolated SELV control domain:** An isolated flyback/LinkSwitch aux
  supply powers the entire control side (15V, 3.3V, MCU, gate driver
  secondaries). The RTD probe is on the isolated SELV side. The high-voltage
  side has its own ground reference (doubler midpoint). This is the standard
  approach for consumer induction cookers.
- **B — Non-isolated with sensor isolation:** Keep logic ground = neutral,
  but add reinforced isolation at the RTD probe interface (isolated DC-DC +
  isolated I2C/SPI for MAX31865). Lower component count but riskier — the
  entire MCU still floats at line potential.

**Decision criteria:** Safety (IEC 60335 Class I/II), component count, cost,
complexity. Option A is the standard approach for consumer induction cookers
and recommended as the starting assumption.

### U2. Low-side gate-driver supply fix

**Goal:** VDDB and VSSB must be separated by ≤25V. With VSSB tied to hv_minus
(-170V ref doubler midpoint), VDDB must be referenced to hv_minus, not to
logic ground.

**Implementation:**
- If Option A (isolated SELV): the 15V rail is already isolated from the HV
  side. Add an isolated gate-driver supply (e.g., an auxiliary winding on
  the flyback transformer, or an isolated DC-DC module like R1S-0515) that
  floats on hv_minus for the low-side driver supply.
- If Option B: add a dedicated bootstrap or isolated supply for the low-side
  driver, similar to how the high-side gets its bootstrap.

**File:** `elec/src/modules.ato` — modify the HalfBridge module's low-side
  supply connections. `elec/src/main.ato` — wire the isolated supply.

### U3. Tank return separation

**Current:** `main.ato:266` — `tank.out ~ gnd`

**Fix:** Create a dedicated high-current return net (e.g., `power_return`) that
ties to `dc_bus.gnd_ref`. Join `power_return` to signal `gnd` at exactly one
star-point location (near the doubler capacitor midpoint), with the join
clearly marked in both `.ato` source and as a layout constraint.

### U4. RTD isolation barrier

**Goal:** The user-touchable RTD probe must not ride on line potential.

**If Option A:** MCU is on isolated SELV side — the isolation barrier is
between the HV power domain and the SELV control domain, not at the RTD.
Single isolation barrier covers everything (MCU, sensors, gate driver control
side).

**If Option B:** Instantiate the already-defined ADUM1250 for isolated I2C
to MAX31865, plus an isolated 3.3V supply (e.g., R1SE-0505 or similar) for
the isolated side.

### U5. PE bonding

**Goal:** Connect protective earth to the doubler midpoint through appropriate
impedance, providing a fault current path.

**Implementation:** Add a Y-cap (or direct bond, depending on Class I/II
decision) from `dc_bus.gnd_ref` to `pe`. The `pe` signal is already declared
`required = true` at `modules.ato:364-365` but never connected — wire it to
the actual PE terminal.

## Test Strategy

1. **Atopile build:** `ato build` must succeed with all nets connected and no
   required signals floating.
2. **Netlist audit:** Run the connectivity tracer to verify:
   - No DC path between AC line/neutral and any user-accessible net
   - Tank return is on a dedicated net separate from signal ground
   - VDDB-VSSB < 25V for all gate driver instances
3. **Creepage/clearance:** Verify the isolation barrier meets IEC 60335
   requirements for the selected working voltage.
4. **Bench test (pre-HV):** With only the aux supply powered, verify:
   - No continuity between AC input and RTD probe
   - Gate driver supply voltages are correct and referenced correctly
   - Low-side VDDB-VSSB voltage is within UCC21550 spec

## Open Questions

1. Class I (earthed) or Class II (double-insulated)? The answer determines PE
   bonding requirements and creepage distances. Consumer induction cooktops are
   typically Class I.
2. Isolated gate-driver supply topology: dedicated aux winding on the flyback
   transformer, or a separate isolated DC-DC module? Aux winding is cheaper and
   more common in production but requires transformer design. DC-DC module is
   quicker for prototypes.
3. Should the doubler midpoint be hard-grounded to PE (Class I) or
   Y-cap-coupled? Hard ground simplifies EMI but may couple noise.

## References

- Master audit: `docs/audits/2026-07-15-atopile-electrical-design-audit.md`
- Creepage/clearance constraints: `elec/src/constraints.ato`
- IEC 60335-1, Clause 8 (protection against electric shock), Clause 29
  (clearances, creepage distances, solid insulation)
