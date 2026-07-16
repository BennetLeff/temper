---
title: "fix: EMI/surge front end and AC safety — S2, S4"
type: fix
status: pending
date: 2026-07-15
origin: docs/audits/2026-07-15-atopile-electrical-design-audit.md
depends_on: [2026-07-15-003]
blocks: []
---

# fix: EMI/Surge Front End and AC Safety

## Summary

The power input stage has no EMI filtering or surge protection despite the
PowerInput module's docstring claiming "AC input with EMI filter"
(`modules.ato:353`). A 1.8kW switching appliance cannot pass conducted
emissions or surge immunity without these components. Additionally, the
bus discharge time constant of 330 seconds (100kΩ × 3300µF × ~4τ ≈ 22
minutes to safe voltage) is a service safety hazard.

Two independent issues in the PowerInput module:

1. **S2:** Zero X2/Y capacitors, zero common-mode chokes, zero MOVs.
   Protective earth (`pe`) declared `required = true` at
   `modules.ato:364-365` but never connected.
2. **S4:** 100kΩ bleeders on 3300µF doubler caps → τ = 330s. To reach
   <34V (IEC 60335 requirement after disconnect): ~4τ ≈ 22 minutes.

## Problem Frame

### S2: Missing EMI/surge front end

**Current state of PowerInput (`modules.ato:353-367`):**
```ato
module PowerInput:
    """AC input with EMI filter and inrush protection"""
    # Fuse
    fuse = new Fuse_356_15A
    # NTC inrush limiter
    ntc_inrush = new NTC_Inrush
    # Relay bypass
    relay = new Relay_G4A_1A_E
    # ... plus signal declarations for ac_n, ac_l, pe, zcd
```

**What's missing:**
- **X2 capacitor(s):** Differential-mode filtering across AC_L and AC_N.
  Typical: 0.1µF-0.47µF X2-rated (305VAC or 310VAC safety-rated).
  Placement: after the fuse, before the bridge rectifier.
- **Common-mode choke (CMC):** Suppresses common-mode noise. Typical:
  10-47mH on a ferrite toroid, bifilar wound, rated for 15A. Placement:
  between the X2 cap and the bridge rectifier.
- **Y capacitor(s):** Line-to-earth common-mode filtering. Requires PE
  connection. Typical: 2.2nF-4.7nF Y1/Y2-rated. Placement: from each
  AC line to PE (after the fuse).
- **MOV (Metal Oxide Varistor):** Surge protection. Clamps line-to-line
  and line-to-earth transients. Typical: 150VAC (for 120V mains) or
  275VAC rating, 10mm or 14mm disc. Placement: directly across AC_L and
  AC_N after the fuse.
- **PE connection:** The `pe` signal must be connected to the earth pin
  of the AC inlet and to chassis ground.

### S4: Bus discharge time

**Current bleeders:**
```
100kΩ × 3300µF per half-bus → τ = 330s
V(t) = 170V × e^(-t/330)
To reach <34V: t = 330 × ln(170/34) = 330 × 1.609 ≈ 531s ≈ 8.9 min per half-bus
For full bus (both caps): ~17.8 min to safe level
```

**IEC 60335-1 requirement:** Accessible live parts must discharge to <34V
peak within a reasonable time after disconnection. While the standard doesn't
specify an exact time for permanently-connected appliances (it defers to
sub-part 2), best practice for serviceable equipment is <5 seconds.

**Fix options:**
- **Active discharge:** A depletion-mode MOSFET (e.g., IXTP08N100D2) with a
  gate-source resistor — conducts when gate voltage collapses at power-off.
  Add series resistance to control discharge rate. More components but no
  standby power dissipation.
- **Smaller bleeders:** 10kΩ 5W resistors give τ = 33s, ~2 minutes to <34V.
  Dissipation: 170²/10k = 2.89W per half-bus — borderline for a 5W resistor
  in a hot enclosure. 15kΩ → 1.93W, τ = 49.5s, ~3.2 minutes.
- **Dual bleeders:** Two 50kΩ in parallel (100kΩ equivalent for normal
  operation, one switched in at power-off via relay NC contact). Only
  acceptable if the relay has an NC contact (G4A-1A-E is SPST-NO — doesn't).

**Recommended:** Active discharge with depletion-mode MOSFET. For a
prototype, 15kΩ 5W bleeders (τ ≈ 50s per half-bus, ~5.3 min to safe level)
are acceptable as an interim measure with clear safety labeling.

## Scope Boundaries

### In scope
- Design and add the EMI filter components (X2 cap, CMC, Y caps, MOV) to
  the PowerInput module in `elec/src/modules.ato`
- Wire `pe` to the AC inlet earth terminal
- Add atopile assertions for EMI component voltage ratings matching the
  120VAC/170VDC operating points
- Address bus discharge: implement active discharge circuit or reduce
  bleeder resistance with power derating verification

### Deferred
- Full pre-compliance EMC testing (conducted emissions, radiated emissions,
  surge immunity) — this plan provides the circuit; a test lab does the
  measurement
- Line impedance stabilization network (LISN) selection — deferred to EMC
  test planning

### Out of scope
- PCB layout for EMC (trace routing, ground planes, component placement
  for minimal loop area) — covered by layout guidelines and the placer
  constraints

## Implementation Units

### U1. EMI filter components

**File:** `elec/src/modules.ato` — PowerInput module

Add to the signal chain (in order from AC inlet to bridge rectifier):
```ato
fuse → MOV (L-N) → X2 cap (L-N) → CMC → Y caps (L-PE, N-PE) → NTC → relay → bridge
```

**Component specifications:**

| Component | Suggested Part | Rating | Notes |
|-----------|---------------|--------|-------|
| X2 cap | 0.22µF 310VAC X2 | DE2E3KH221MA3B or similar | After fuse, before CMC |
| CMC | 10-20mH, >15A rated | Custom or B82725J2152N1 | Toroid or E-core |
| Y caps (2×) | 2.2nF Y1 500VAC | DE1E3KX222MA4B or similar | L-PE and N-PE, after CMC |
| MOV | 150VAC 10mm disc | V150LA10AP or similar | After fuse, L-N |

**Assertions to add:**
```ato
assert emi_x2_cap.v_rated >= 310VAC
assert emi_y_cap.v_rated >= 250VAC  # Y1 rated
assert emi_mov.v_clamp > 120VAC * 1.1  # above nominal + tolerance
```

### U2. PE connection

**File:** `elec/src/main.ato`

Wire `power_in.pe` to the AC inlet earth terminal. Add a chassis ground
symbol at the top level.

### U3. Bus discharge fix

**File:** `elec/src/modules.ato` — DCBus module or PowerInput module

**Option A (active discharge — recommended):**
```ato
# Depletion-mode MOSFET (e.g., IXTP08N100D2) across each doubler cap
# Gate tied to ground through 100k, source to cap negative
# When aux supply is off, V_GS = 0 → MOSFET conducts → discharges cap
# When aux supply is on, a negative bias (or isolated supply) turns it off
```

**Option B (reduced bleeders — interim):**
```ato
# Replace 100kΩ bleeders with 15kΩ 5W
assert p_bleed_actual < r_bleed.power_rating * 0.5  # 50% derating
# τ = 15kΩ × 3300µF ≈ 50s per half-bus
# Discharge to <34V: ~2.5 minutes per half-bus
```

### U4. Documentation

Add a warning comment in `elec/src/main.ato` and/or `docs/`:
```ato
# WARNING: Bus capacitors store hazardous energy.
# Discharge time with current bleeders: ~XX minutes to <34V.
# Do not touch bus nodes until verified discharged.
```

## Test Strategy

1. **EMI filter:**
   - Verify component voltage ratings with assertions at `ato build` time
   - Continuity check: AC inlet earth to PCB PE trace
   - Pre-compliance conducted emissions scan (if equipment available)

2. **Surge protection:**
   - Verify MOV clamping voltage is above nominal +10% line tolerance
   - Verify MOV is placed before any components that could be damaged by
     surge (correct signal chain order)

3. **Bus discharge:**
   - Charge bus to 170VDC (half-bus) from a current-limited supply
   - Disconnect and measure discharge time to <34V
   - Verify measurement against τ calculation
   - For active discharge: verify MOSFET conducts when aux supply is off
     and is fully off (no standby dissipation) when aux supply is on

## Open Questions

1. **CMC selection:** Custom-wound toroid (lower cost, requires winding
   spec) vs. off-the-shelf (higher cost, simpler BOM)? For a one-off
   prototype, an off-the-shelf CMC is practical.
2. **Class I vs Class II:** If plan 003 selects Class II (double-insulated),
   Y caps go to a floating ground plane, not PE. This changes the EMI
   topology.
3. **Active discharge:** Does the depletion-mode MOSFET solution need a
   negative gate bias (adds complexity) or can a 0V gate-source work
   at the available drain voltage?

## References

- Master audit: `docs/audits/2026-07-15-atopile-electrical-design-audit.md`
- Plan 003: Grounding architecture (PE bonding decision)
- IEC 60335-1, Clause 22.5: discharge of capacitors
- CISPR 14-1: conducted emissions for household appliances
- IEC 61000-4-5: surge immunity test
