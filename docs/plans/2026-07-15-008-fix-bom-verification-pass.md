---
title: "fix: BOM verification pass — MPN/footprint mismatches, connectors, fuse"
type: fix
status: completed
date: 2026-07-15
origin: docs/audits/2026-07-15-atopile-electrical-design-audit.md
depends_on: [2026-07-15-003, 2026-07-15-005]
blocks: []
---

## Shipped

**Merged in [PR #214](https://github.com/BennetLeff/temper/pull/214) on 2026-07-16.** The fix for this plan shipped as part of the comprehensive atopile audit remediation (`fix(elec): resolve 8 P0/P1 electrical design bugs from atopile audit`). See the PR body's per-plan table for the specific changes attributable to this plan.

# fix: BOM Verification Pass

## Summary

Multiple bill-of-materials issues where the specified MPN, footprint, and/or
electrical rating are mutually incompatible. These are individually small
fixes but collectively would block PCB layout or cause assembly failures.
Three items are "verify against datasheet" (the audit couldn't confirm
without access to datasheets). Two items are missing components entirely
(connectors).

## Problem Frame

### Verified mismatches (datasheet-confirmed)

| # | Item | `components.ato` | Issue |
|---|------|------------------|-------|
| B1 | MAX31865ATP+ | footprint = SSOP-20 | ATP = TQFN-20 package. Correct MPN is MAX31865AAP+ (SSOP-20) |
| B2 | r_relay_drop | CRCW060339R0FKEA (0603 SMD, 0.1W) | Footprint is THT axial, power requirement is 1W as noted in ato assertion. Replace with a 1W axial part. |
| B3 | UJ3D1210TS bootstrap diode | 1200V/10A TO-220 SiC | ~50× overkill for charging a 10µF boot cap. 600V/1A SMA ultrafast (ES1J, US1M) is appropriate. |
| B4 | UCC21550 bypass caps | — | No VCCI or VDDB bypass capacitors exist. Add 0.1µF + 1µF at each VCCI and VDDA/VDDB pin. Also add HF film cap (0.1µF-1µF, 630VDC) across the DC bus near the bridge. |
| B5 | Self-asserting checks | `modules.ato:586-588`, etc. | `v_fb`, `p_bleed_actual`, `t_dead_time` validate hardcoded copies of themselves. |

### Needs datasheet verification

| # | Item | Question |
|---|------|----------|
| B6 | CST-1005 | Verify 1:1000 turns ratio claim. Burden math: 50A primary → 50mA secondary → 3.3V across 66.5Ω burden → V_burden = 50mA × 66.5Ω = 3.325V. This depends on exactly 1:1000. If the ratio differs, recalculate R_burden. |
| B7 | EKZE251ELL332MM40S | Verify Chemi-Con KZE series includes 250V 3300µF parts. KZE tops out at lower voltages; 250V 3300µF is typically KMQ, LXQ, or U-series from Chemi-Con. Verify the exact part number exists in the catalog. |
| B8 | Gate R 2.2Ω | Demands 15V/2.2Ω = 6.8A from UCC21550 (4A source/sink). Works (driver current-limits safely), but Rg should be sized to the driver for optimal switching: Rg ≥ 15V/4A = 3.75Ω → 3.9Ω standard. |

### Missing from BOM entirely

| # | Item | Detail |
|---|------|--------|
| B9 | AC inlet / terminal block | No connector for mains input |
| B10 | RTD connector | RTD probe needs a connector on the PCB |
| B11 | Fan + connector | 1.8kW requires forced air — no fan or fan connector exists |
| B12 | Fuse sizing | 15A fuse for 1800W/120V = 15A continuous. Either derate to 1500W or use 20A fuse |

## Scope Boundaries

### In scope
- Correct MPN/footprint mismatches (B1, B2)
- Replace overkill components (B3)
- Add missing decoupling capacitors (B4)
- Verify datasheet-dependent items (B6, B7, B8) — human check, not code change
- Add connectors to BOM (B9, B10, B11)
- Fuse sizing decision (B12)
- Fix self-asserting checks (B5) — replace hardcoded copies with parameter
  derivations

### Deferred
- Full BOM cost optimization (the focus is correctness, not cost)
- Alternate source/second-source qualification
- RoHS/REACH compliance verification

### Out of scope
- PCB footprint creation for connectors (mechanical CAD task, uses .kicad_mod)

## Implementation Units

### U1. MAX31865 MPN fix

**File:** `elec/src/components.ato`

```diff
-    mpn = "MAX31865ATP+"
+    mpn = "MAX31865AAP+"  # SSOP-20 package, matches footprint
```

Verify the footprint pin mapping matches the AAP+ variant (same die, different
package — pinout should be identical).

### U2. Relay drop resistor MPN fix

**File:** `elec/src/components.ato`

Replace `CRCW060339R0FKEA` (0603 SMD, 0.1W) with a 1W axial metal film or
wirewound resistor. Example: `RSF100JB-73-39R` (Yageo 1W axial, 39Ω ±5%) or
`MFR-25FRF52-39R` (Yageo 1/4W — need 1W equivalent).

**Note:** The atopile assertion already checks `p_relay_drop` based on relay
coil current (75mA × 39Ω → 0.22W). A 0.5W part would suffice with 50% derating,
but the existing footprint is THT axial — match the footprint size to the
power rating.

### U3. Bootstrap diode downsize

**File:** `elec/src/components.ato`

```diff
-    # UJ3D1210TS: 1200V 10A SiC Schottky TO-220
+    # ES1J: 600V 1A SMA ultrafast — appropriate for ~10µF boot cap charging
+    # Bootstrap current: ~10mA avg, 1A peak for nanoseconds
+    # 600V > 340V bus with margin; 1A >> actual peak
```

Or add a separate `BootstrapDiode` component entry and keep the SiC diode for
other uses (if any). The UJ3D1210TS can stay as a general HV diode if needed
elsewhere, but the boot diode specifically doesn't need it.

### U4. Gate driver bypass capacitors

**File:** `elec/src/modules.ato` — GateDriveHS / GateDriveLS or HalfBridge module

Add:
- VCCI bypass: 0.1µF + 1µF ceramic (X7R, 16V or 25V) at each VCCI pin
- VDDA/B bypass: 0.1µF + 1µF ceramic at VDDA and VDDB pins
- DC bus HF bypass: 0.1µF-1µF film capacitor (630VDC) across the half-bridge
  DC bus terminals, placed as close as possible to the IGBT + bootstrap diode

**Reference:** UCC21550 datasheet Section 10 "Power Supply Recommendations"
and typical application schematic.

### U5. Self-asserting check cleanup

**File:** `elec/src/modules.ato`

For each hardcoded-copy assertion, replace with a derivation from component
attributes:

```diff
-    v_fb: voltage = 1.0V
+    # Derived from LMR51430 datasheet V_FB typical = 1.0V at 25°C
+    # Datasheet ref: TI SLUSF42, Section 6.5 Electrical Characteristics
+    v_fb: voltage = 1.0V @ 25C

-    p_bleed_actual: power = v_bus^2 / r_bleed.value
-    assert p_bleed_actual < 0.5  # Pre-computed: 170^2 / 100k ≈ 0.289W
+    p_bleed_actual: power = v_bus^2 / r_bleed.value
+    assert p_bleed_actual < r_bleed.power_rating * 0.5  # 50% derating
```

### U6. Datasheet verification tasks (human)

| Task | Action | Owner |
|------|--------|-------|
| CST-1005 ratio | Download datasheet, verify 1:1000 or note actual ratio | TBD |
| EKZE251ELL332MM40S | Verify on Chemi-Con website or DigiKey/Mouser catalog | TBD |
| Gate resistor | Decide: 2.2Ω (current-limited) or 3.9Ω (matched to driver) | TBD |

### U7. Connectors

**File:** `elec/src/components.ato` — add new component entries

| Component | Suggested part | Notes |
|-----------|---------------|-------|
| AC inlet | IEC C14 panel-mount (or terminal block, Phoenix 1757022) | C14 if chassis-mount, terminal block if PCB-mount |
| RTD connector | 3-pin Molex Mini-Fit Jr. or similar | Must be rated for the RTD operating temperature |
| Fan connector | 2-pin 0.1" header or JST XH | 12V or 24V fan, current depends on fan selection |

**File:** `elec/src/main.ato` — instantiate connectors and wire to appropriate
nets.

### U8. Fuse sizing

**Decision needed:** 15A (1800W) or derate to 1500W (realistic for 120V/15A
circuit with continuous load derating)?

Per NEC, continuous loads must be derated to 80% of branch circuit rating:
15A circuit × 80% = 12A continuous → 12A × 120V = 1440W. 1800W exceeds the
80% rule for a 15A circuit.

**Options:**
- Derate target power to 1500W (12.5A), use 15A fuse
- Keep 1800W target, use 20A fuse, require 20A circuit (NEMA 5-20P plug)
- Keep 1800W target with 15A fuse and accept nuisance blowing on hot days

## Test Strategy

1. **BOM export:** Generate BOM from atopile and verify all MPNs resolve to
   valid, purchasable parts on DigiKey/Mouser.
2. **Footprint audit:** Cross-check every ato component's `footprint` field
   against the MPN's datasheet package drawing.
3. **Power derating:** Run all `assert p_* < rating * derating` checks at
   `ato build` time.
4. **Bypass capacitor:** Verify capacitor count matches pin count (each power
   pin gets local bypass).
5. **Gate resistor:** Scope the gate waveform at full load to verify rise/fall
   times are within the IKW40N120H3's safe operating area with the chosen Rg.

## References

- Master audit: `docs/audits/2026-07-15-atopile-electrical-design-audit.md`
- Plan 003: Aux supply may add new BOM entries
- Plan 004: Zener and OVP fix may change component values
- `elec/src/components.ato`: single source of truth for all component MPNs
