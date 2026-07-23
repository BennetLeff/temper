---
title: "fix: Auxiliary power supply design — P0-3, P0-7, P0-8"
type: fix
status: completed
date: 2026-07-15
origin: docs/audits/2026-07-15-atopile-electrical-design-audit.md
depends_on: [2026-07-15-003]
blocks: []
---

## Shipped

**Merged in [PR #214](https://github.com/BennetLeff/temper/pull/214) on 2026-07-16.** The fix for this plan shipped as part of the comprehensive atopile audit remediation (`fix(elec): resolve 8 P0/P1 electrical design bugs from atopile audit`). See the PR body's per-plan table for the specific changes attributable to this plan.

# fix: Auxiliary Power Supply Design

## Summary

The +15V rail has no source and the downstream LDO would be destroyed if it
did. Three related failures:

1. **P0-3:** `power_in_hv` (the buck converter's input) is declared in
   `modules.ato:634` but never connected at the top level of `main.ato`.
   The comment at `main.ato:229-230` acknowledges the gap: "In real design,
   15V comes from auxiliary winding." Nothing powers the gate driver, relay,
   MCU, or any downstream circuit.
2. **P0-7:** The XC6220 LDO (Vin max = 6.0V) is powered from the 15V rail.
   Even if the 15V rail existed, the LDO would be destroyed at first power-on.
3. **P0-8:** The LMR51430's feedback reference voltage (`v_fb = 1.0V` at
   `modules.ato:586`) may or may not match the actual device — the self-
   asserting check at line 588 passes regardless because it validates a
   hardcoded copy of itself. **Requires human datasheet verification** before
   accepting the current 140k/10k feedback divider as correct.

Item 3 is the lowest priority of these three and may be a false alarm from the
audit — the LMR51430 datasheet specifies V_FB = 1.0V typical, which would make
the current resistor values correct (15.0V output).

## Problem Frame

### P0-3: Missing aux supply

The current design has a `BuckConverter15V` module (LMR51430, 36V max input)
fed from `power_in_hv` — but `power_in_hv` is a floating `ElectricPower` port
with no top-level connection. The buck's `enable` line is hardwired to its own
(potentially floating) VCC, which would not work even if VCC were present.

**What's needed:** An offline auxiliary power supply that:
- Takes rectified AC (~170VDC from half-bus, or 340VDC from full bus, or
  directly from the AC line)
- Produces a regulated 15V rail
- Can supply: gate driver (peak ~100mA switching), relay coil (~75mA),
  ESP32-S3 (500mA peak during WiFi), MAX31865, comparators, fan (if added)
  — budget ~5-8W total
- Provides isolation if the grounded-isolated architecture (plan 003 Option A)
  is chosen

**Realistic options:**
- **Aux winding on the main coil:** Tapped from the resonant tank — simplest,
  lowest BOM cost, but only works when the coil is active (no standby power).
  Not viable as the sole supply.
- **Offline flyback converter:** LinkSwitch-TN (LNK304/306), VIPer, or similar
  buck/flyback regulator from the rectified AC bus. Standard approach for
  induction cooker aux supplies. Provides isolation.
- **Capacitive dropper + linear regulator:** For low-power standby only —
  insufficient for 5-8W.

Recommended: LinkSwitch-TN or VIPer-based flyback from the rectified AC bus,
with an auxiliary winding on the transformer if isolated gate-driver supplies
are needed (see plan 003).

### P0-7: XC6220 LDO overvoltage

| Parameter | XC6220 rating | Actual condition |
|-----------|---------------|------------------|
| Vin max | 6.0V | 15V |
| Pd max (SOT-23-5) | ~0.5W | (15-3.3)×0.35A = 4.1W |
| Iout max | 300mA | ESP32 WiFi peaks ~350mA+ |

**Fix options:**
- **Buck converter to 3.3V:** LMR51420 (if LMR51430 is kept for 15V), TPS62933,
  AP63203, or similar 3.3V fixed-output buck. Lower dissipation, higher
  efficiency. This is the recommended approach for >2W.
- **Buck to 5V, then LDO to 3.3V:** Two-stage for cleaner 3.3V analog supply.
  Only justified if the 3.3V rail noise is a problem for ADC measurements.
- **Higher-voltage LDO:** XC6216 (28V Vin max) could survive 15V input but
  still cannot dissipate 4W — not a real solution, only works with a
  pre-regulator.

### P0-8: LMR51430 v_fb verification

The audit claims the LMR51430 reference is 0.6V, which would give 9.0V output
with the 140k/10k divider. However, the LMR51430 datasheet specifies V_FB =
1.0V typical (0.985V-1.015V), which gives the expected 15.0V output.

**Required action:** A human must verify the exact part number variant against
the datasheet. If V_FB = 1.0V, this is a false alarm — mark the finding
resolved. If V_FB = 0.6V, recalculate the divider for 15V output: R_top =
R_bot × ((15/0.6) - 1) = 10k × 24 = 240k (standard value).

Additionally, replace the self-asserting check with a derivation from the
component's actual datasheet parameter:
```diff
-    v_fb: voltage = 1.0V
+    # v_fb derived from LMR51430 datasheet V_FB typical = 1.0V
+    v_fb: voltage = 1.0V @ 25C
     v_out_calculated: voltage = v_fb * (1 + r_fb_top.value / r_fb_bot.value)
     assert v_out_calculated within 14.5V to 15.5V
```

## Scope Boundaries

### In scope
- Design and add the offline auxiliary power supply to `elec/src/modules.ato`
  and instantiate in `elec/src/main.ato`.
- Replace the XC6220 with a 3.3V buck converter (or buck+LDO chain).
- Verify and document the LMR51430 v_fb value against the datasheet.
- Update the BOM with new power supply components.
- Add relevant atopile assertions for supply sequencing and power-on behavior.

### Deferred
- Transformer winding specification (flyback transformer design is a
  magnetics task — this plan provides the electrical interface and power
  budget; the actual transformer part number or winding spec is deferred).

### Out of scope
- Gate-driver isolated supply design (if needed, covered by plan 003).
- Fan power (if fan is added, its power budget is additive to this design).

## Implementation Units

### U1. Offline aux supply design

**File:** `elec/src/modules.ato` — new `AuxSupply` module

**Required ports:**
- `ac_line_in` — tap from after the fuse/before the bridge rectifier
  (or from the DC bus after rectification, with appropriate voltage rating)
- `gnd_ref` — reference to the doubler midpoint
- `vcc_15v` — 15V output
- `gnd` — output ground (may be isolated from gnd_ref in isolated designs)

**Required assertion:** `ato build` must fail if the aux supply is not
instantiated at the top level.

### U2. Top-level wiring

**File:** `elec/src/main.ato`

Wire `aux_supply.ac_line_in` to the AC input (post-fuse, post-NTC),
`aux_supply.vcc_15v` to the existing `vcc_15v` rail, and
`aux_supply.gnd` to the appropriate ground domain per plan 003.

Remove the floating `power_mgmt.power_in_hv` connection or repurpose it
if the buck converter is retained as a post-regulator.

### U3. Replace XC6220 with 3.3V buck

**File:** `elec/src/modules.ato` — PowerManagement module

Add a 3.3V buck converter (e.g., LMR51420, AP63203, TPS62933) powered from
the 15V rail. Remove the XC6220 instance. Update the `power_3v3` output.

If 5V intermediate is needed (e.g., for I2C pull-ups, USB), add a 5V buck
first, then an LDO or second buck to 3.3V.

### U4. Verify LMR51430 v_fb

**Action:** Human reviews the specific LMR51430 variant datasheet for V_FB.
- If V_FB = 1.0V: resolved — add a comment citing the datasheet page/table.
- If V_FB ≠ 1.0V: recalculate FB divider and update `modules.ato:586-588`.

**File:** `elec/src/modules.ato` — BuckConverter15V module

### U5. Self-asserting check cleanup

**Goal:** Replace hardcoded-copy assertions with parameter derivations.

**Files:** `elec/src/modules.ato` — audit all `assert` statements in
BuckConverter15V and PowerManagement for circular self-validation. Add
datasheet-derived parameters as comments next to each hardcoded constant.

## Test Strategy

1. **Atopile build:** `ato build` with all new modules must succeed.
2. **Power budget:** Verify the aux supply is rated for the sum of all
   downstream loads. Add an assertion that total downstream power ≤ aux
   supply rating.
3. **Pre-HV bench:** Power the aux supply from a DC bench supply at reduced
   voltage (e.g., 50VDC) and verify 15V and 3.3V rails are in regulation.
4. **Load step:** Switch a 500mA load on the 3.3V rail and verify no sag
   below ESP32 brownout threshold.
5. **v_fb verification:** Measure actual 15V rail output voltage with the
   assembled circuit and compare to calculated value. Flag if >5% deviation.

## Open Questions

1. Should the aux supply run from the AC side (pre-bridge) or DC side
   (post-bridge, from one half of the doubler)? AC side needs a bridge
   rectifier in the aux supply; DC side can run from ~170VDC but must
   handle the 340V peak during inrush.
2. Is an isolated flyback preferred (for safety) or a non-isolated buck
   (simpler, fewer components)? This depends on plan 003's architecture
   decision.
3. Should we use the LMR51430 for 15V (if v_fb checks out) or replace it
   entirely with the aux supply?

## References

- Master audit: `docs/audits/2026-07-15-atopile-electrical-design-audit.md`
- Plan 003: Grounding and isolation architecture
- LMR51430 datasheet: TI SLUSF42
- XC6220 datasheet: Torex
- LinkSwitch-TN: Power Integrations LNK304/306 datasheet
