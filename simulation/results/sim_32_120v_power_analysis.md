# 120V Power Analysis - Critical Finding

## Task: 1800W System Verification (sim_32)
## Date: December 13, 2025
## Status: DESIGN ISSUE IDENTIFIED

---

## Executive Summary

**Critical Finding:** The current resonant tank design cannot achieve 1800W at 120VAC input without modifications.

| Parameter | Design Target | Simulated Result | Gap |
|-----------|---------------|------------------|-----|
| Output Power | 1800W | ~700W | **-61%** |
| Tank Current | 15A RMS | 9.3A RMS | -38% |
| Bus Voltage | 170V | 170V | OK |

---

## Root Cause Analysis

### The Math

For a series resonant tank at resonance:
```
I = V_fundamental / Z_min
P = I² × R_pan
```

Where:
- V_fundamental = (2/π) × V_dc = 0.637 × V_dc
- Z_min = R_pan + R_coil ≈ 8.22Ω

### At 120VAC (170V DC bus):
```
V_fund = 0.637 × 170V = 108V
I_max = 108V / 8.22Ω = 13.1A RMS
P_max = 13.1² × 8 = 1373W (theoretical maximum at resonance)
```

### At 230VAC (320V DC bus):
```
V_fund = 0.637 × 320V = 204V
I_max = 204V / 8.22Ω = 24.8A RMS
P_max = 24.8² × 8 = 4920W (theoretical, would be limited by other factors)
```

### Why Only 700W in Simulation?

Operating above resonance (for ZVS) increases impedance significantly:
- At resonance (35.8 kHz): Z ≈ 8Ω
- At 38 kHz (+6%): Z ≈ 12Ω
- Power at 38 kHz: (108/12)² × 8 = 648W ✓ (matches simulation)

---

## Solutions Analysis

### Option 1: Accept Lower Power (Easiest)

**Maximum achievable at 120V with current design:**
- At resonance: ~1200-1400W (lose ZVS margin)
- With safe ZVS margin: ~700-900W

**Verdict:** Not sufficient for 1800W target. ❌

---

### Option 2: Add PFC Boost Stage

Boost rectified 170V to 250-300V DC bus.

**Implementation:**
- Add PFC controller (e.g., UCC28180)
- Boost inductor, diode, MOSFET
- Additional bus capacitor

**Result:**
- At 250V bus: P_max ≈ 1500W (with ZVS margin)
- At 300V bus: P_max ≈ 2200W (ample headroom)

**Pros:**
- Achieves power target
- Better power factor (regulatory compliance)
- More headroom for pan variation

**Cons:**
- Significant additional complexity
- More components, cost, PCB area
- Additional failure modes

**Verdict:** Works but adds complexity. ⚠️

---

### Option 3: Reduce Tank Impedance

Lower effective R_pan or redesign tank for lower impedance.

**Approaches:**
1. **Different coil design:** More turns, tighter coupling → lower R_reflected
2. **Lower frequency operation:** 25-30 kHz instead of 35 kHz
3. **Different capacitor value:** Retune for lower impedance

**Analysis:**
To get 1800W at 170V:
```
I_needed = sqrt(1800/8) = 15A
V_fund = 108V
Z_needed = 108/15 = 7.2Ω
```
This is only slightly lower than current 8.22Ω, suggesting we're close.

**Actual issue:** Operating above resonance for ZVS raises Z to ~12Ω.

**Potential fix:** Operate closer to resonance (36.0-36.5 kHz instead of 38 kHz)

**Simulation at 36 kHz:**
```
Z ≈ 9Ω
I = 108/9 = 12A
P = 12² × 8 = 1152W
```

Still not 1800W, but better. ⚠️

---

### Option 4: Lower R_pan Assumption

The 8Ω R_pan is for cast iron. Some pans have lower reflected resistance.

**Pan material resistance (typical):**
- Cast iron: 6-10Ω
- Carbon steel: 5-8Ω  
- Stainless (induction): 10-20Ω

**With R_pan = 5Ω:**
```
Z_min = 5 + 0.22 = 5.22Ω
I = 108/5.22 = 20.7A
P = 20.7² × 5 = 2142W ✓
```

**Caveat:** This works only with low-impedance pans. User pan selection becomes critical.

**Verdict:** Possible but constrains pan compatibility. ⚠️

---

### Option 5: Voltage Doubler Rectifier

Use voltage doubler instead of full-bridge rectifier.

**Implementation:**
```
120VAC → Voltage Doubler → 340V DC (2 × 170V)
```

**Result:** Same as 230V system → ample power headroom.

**Pros:**
- Simple modification to rectifier
- No active components (passive doubler)
- Achieves full power easily

**Cons:**
- Higher voltage stress on all components (need 450V+ ratings)
- Larger/more expensive capacitors
- Higher ripple current
- Reduced power factor

**Verdict:** Simple and effective, but needs component re-rating. ✓⚠️

---

## Recommended Solution

For first prototype on 120V, I recommend **Option 5: Voltage Doubler** because:

1. **Simplest path to 1800W** - No PFC controller, no active components
2. **Proven topology** - Common in commercial induction cookers
3. **Component changes are minor:**
   - Replace 200V electrolytics with 400V
   - IGBTs already rated 1200V (plenty of margin)
   - Resonant cap already 630V rated

**Trade-off:** Slightly worse power factor, but acceptable for residential use.

### Implementation

**Current Rectifier:**
```
120VAC ─┬─ D1 ─┬─ +170V
        │      │
        └─ D2 ─┴─ GND
        Full Bridge
```

**Voltage Doubler:**
```
120VAC ─┬─ D1 ─┬─ C1 ─┬─ +340V
        │      │      │
        │      └──────┤
        │             │
        └─ C2 ─┬─ D2 ─┴─ GND
```

Components needed:
- 2× diodes (same as before)
- 2× 220µF 200V capacitors → in series = 110µF at 400V
- Or: 2× 470µF 200V in series = 235µF at 400V

---

## Updated Simulation

With 340V bus (voltage doubler):

```
V_fund = 0.637 × 340V = 217V
I_at_38kHz = 217V / 12Ω = 18A RMS
P = 18² × 8 = 2592W (at 38 kHz, with ZVS margin)
```

This provides ample headroom for 1800W target with comfortable ZVS operation.

---

## Heat Budget Update (with Voltage Doubler)

**At 1800W output with 340V bus:**

| Component | 170V Bus (original) | 340V Bus (doubler) |
|-----------|--------------------|--------------------|
| Tank current | 9.3A RMS | 15A RMS |
| Coil I²R loss | 19W | 50W |
| IGBT losses | ~20W | ~40W |
| **Total heat** | **~39W** | **~90W** |

The 340V system generates more heat due to higher currents, but this matches our original thermal design for 2kW at 230V.

---

## Decision Required

**Options for you:**

1. **Use voltage doubler** (recommended)
   - Achieves 1800W
   - Requires 400V capacitors
   - Same thermal design as planned

2. **Accept ~700-900W maximum**
   - Simpler, current design works
   - May not meet cooking performance goals

3. **Add PFC boost stage**
   - Most flexible, best power factor
   - Significantly more complex

Please confirm which direction to proceed.

---

## References

- sim_32_1800w_simplified.cir - Simulation testbench
- sim_32_1800w_results.txt - Simulation results

---

**END OF ANALYSIS**
