---
title: "fix: P0 wiring bugs — gate-driver zener and OVP comparator"
type: fix
status: completed
date: 2026-07-15
origin: docs/audits/2026-07-15-atopile-electrical-design-audit.md
depends_on: [2026-07-15-003]
blocks: []
---

## Shipped

**Merged in [PR #214](https://github.com/BennetLeff/temper/pull/214) on 2026-07-16.** The fix for this plan shipped as part of the comprehensive atopile audit remediation (`fix(elec): resolve 8 P0/P1 electrical design bugs from atopile audit`). See the PR body's per-plan table for the specific changes attributable to this plan.

# fix: P0 Wiring Bugs — Zener Bias and OVP Comparator

## Summary

Two self-contained schematic wiring bugs in `elec/src/modules.ato` that would
destroy hardware or prevent operation independently of the grounding
architecture:

1. **P0-2:** The high-side gate-driver "negative bias" zener clamp is wired
   backwards — the source code comments explicitly acknowledge this at
   line 177 ("This is definitely NOT negative bias"). The off-state gate is
   held at +5.1V, which is within the IKW40N120H3 V_GE(th) range
   (4.1-5.7V) → guaranteed shoot-through.
2. **P0-4:** The OVP comparator inputs are swapped (divider on INN, reference
   on INP) and the reference is scaled for full-bus while sensing only
   half-bus. Result: the SHUTDOWN latch is permanently set at power-up —
   the system can never leave fault state.

Both bugs are confined to `elec/src/modules.ato` and do not depend on the
grounding architecture changes (plan 003), though plan 003 should land first
to avoid merge conflicts on the same module.

## Problem Frame

### P0-2: GateDriveHS zener orientation

**File:** `modules.ato`, lines 169-192

**Current connections (backwards):**
```ato
# Comment at line 177: "This is definitely NOT negative bias."
# Comment at line 179: "I will preserve the existing connections..."
neg_bias_zener.A ~ drive.vss       # anode to switch node (IGBT emitter)
neg_bias_zener.K ~ driver.VSSA     # cathode to VSSA
boot_cap.p2 ~ driver.VSSA          # VSSA is boot-cap negative terminal
drive.vss ~ switch_node            # emitter/source of the power switch
```

**How it fails:**
- VSSA = switch_node + V_zener (+5.1V)
- When driver output is LOW: gate = VSSA = emitter + 5.1V
- Off-state V_GS = +5.1V — the IGBT is biased at threshold
- Boot cap charges to VDD - V_zener ≈ 15V - 5.1V = ~9.9V (minus diode drop)
- Gate drive is starved even if shoot-through doesn't occur first

**Correct connections (negative bias):**
```ato
neg_bias_zener.A ~ driver.VSSA     # anode to VSSA
neg_bias_zener.K ~ drive.vss       # cathode to switch node (IGBT emitter)
```

**How it works:**
- VSSA = switch_node - V_zener (-5.1V)
- When driver output is LOW: gate = VSSA = emitter - 5.1V
- Off-state V_GS = -5.1V — true negative bias, IGBT solidly off
- Boot cap charges to VDD (full 15V available)

### P0-4: OVPComparator polarity and scaling

**File:** `modules.ato`, lines 1018-1032

**Current connections:**
```ato
# Divider: v_bus → 3×430k → 10k → comp.INN → gnd
v_bus.line ~ r_div_top1.p1
r_div_top1.p2 ~ r_div_top2.p1
r_div_top2.p2 ~ r_div_top3.p1
r_div_top3.p2 ~ comp.INN          # BUS SENSE → INVERTING INPUT
comp.INN ~ r_div_bot.p1
r_div_bot.p2 ~ power.gnd

# Reference: vcc → 1k → comp.INP → 10k → gnd
power.vcc ~ r_ref_top.p1
r_ref_top.p2 ~ comp.INP            # REFERENCE → NON-INVERTING INPUT
comp.INP ~ r_ref_bot.p1
r_ref_bot.p2 ~ power.gnd
```

**Two independent failures:**

1. **Polarity inversion:** TLV3201: OUT = HIGH when INP > INN. With bus
   sense on INN and reference on INP, the output is HIGH when bus is *below*
   threshold — the opposite of an OVP trip. At normal operating voltage,
   OUT is permanently HIGH. The set-dominant latch (`modules.ato:1087-1144`)
   holds SHUTDOWN forever.

2. **Half-bus scaling:** The divider chain faces the *half-bus* (+170V
   nominal from the doubler), but the reference divider is sized for a full
   ~390V trip. At 170V: V_INN = 170 / 130 ≈ 1.31V. V_INP ≈ 3.0V (from
   1k/(1k+10k) of 3.3V). Even with correct polarity, 1.31V < 3.0V means
   the trip never fires — the OVP is effectively disabled.

## Implementation Units

### U1. Flip the high-side zener

**File:** `elec/src/modules.ato`

**Change 1 — lines 190-191:**
```diff
-    neg_bias_zener.A ~ drive.vss
-    neg_bias_zener.K ~ driver.VSSA
+    neg_bias_zener.A ~ driver.VSSA
+    neg_bias_zener.K ~ drive.vss
```

**Change 2 — Remove or update the misleading comments at lines 169-184:**
Replace the comment block with accurate documentation of the negative-bias
circuit: "Zener cathode to switch node (emitter), anode to VSSA. When driver
output is LOW, VSSA = emitter - 5.1V, providing -5.1V off-bias to the gate."

### U2. Fix the OVP comparator

**File:** `elec/src/modules.ato`

**Change 1 — Swap inputs (lines 1021-1031):**
```diff
-    r_div_top3.p2 ~ comp.INN
-    comp.INN ~ r_div_bot.p1
+    r_div_top3.p2 ~ comp.INP
+    comp.INP ~ r_div_bot.p1

-    r_ref_top.p2 ~ comp.INP
-    comp.INP ~ r_ref_bot.p1
+    r_ref_top.p2 ~ comp.INN
+    comp.INN ~ r_ref_bot.p1
```

**Change 2 — Adjust reference divider for half-bus trip ~195V:**
- For a 340V bus, each doubler cap sees ~170V nominal.
- Trip at ~195V half-bus (≈390V full bus, 15% margin).
- V_INP at trip = 195 / 130 ≈ 1.50V
- Current reference: 3.3V × (10k/(1k+10k)) ≈ 3.0V — too high
- New reference: 3.3V × (r_bot/(r_top+r_bot)) ≈ 1.50V
  - If r_top = 10k, r_bot = (1.50/1.80)×10k ≈ 8.2k (or 1.50/1.80 ≈ 0.833, standard 8.2k gives ~1.49V)
  - Verify: r_top = 12k, r_bot = 10k → 3.3 × 10/(12+10) = 1.50V ✓

**Change 3 — Add an assertion that prevents inverted comparator wiring:**
```ato
# Assertion: OVP output must be LOW at normal operating voltage
# (This is a design intent check — can be validated in simulation)
```

## Test Strategy

1. **Atopile build:** `ato build` must succeed.
2. **Zener fix verification:**
   - In the `.ato` model, verify that when driver OUTA = LOW, VSSA < switch_node
     (VSSA should be switch_node - V_zener, not switch_node + V_zener).
   - Physical scope check (pre-HV): apply a low-voltage gate-drive test signal
     and verify negative V_GS during off-time.
3. **OVP fix verification:**
   - Verify with a DC bench supply: at <195V on the half-bus, OVP output must
     be LOW. At >195V, OVP output must assert HIGH.
   - Verify the SHUTDOWN latch clears at power-up (was permanently latched).
4. **Integration:** After both fixes land, verify no combinatorial effect —
   the zener fix shouldn't affect OVP, and vice versa.
5. **Re-run:** Atopile build + connectivity tracer on the full netlist.

## References

- Master audit: `docs/audits/2026-07-15-atopile-electrical-design-audit.md`
- UCC21550 datasheet: VDDA/B-VSSA/B abs max ratings
- IKW40N120H3 datasheet: V_GE(th) range
- TLV3201 datasheet: push-pull output polarity
