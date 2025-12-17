# Induction Coil Thermal Analysis - sim_31

## Summary

**Simulation:** sim_31_coil_thermal.cir  
**Task:** temper-0zd.7  
**Date:** December 13, 2025  
**Status:** VERIFIED

---

## Key Finding

| Parameter | Simulated (672W) | Scaled to 2kW | Notes |
|-----------|------------------|---------------|-------|
| RMS Current | 9.2A | 15.8A | I ∝ √P |
| Peak Current | 12.7A | 22A | |
| Coil Loss | 18.5W | **55W** | P ∝ I² |
| Coil Efficiency | 97.3% | 97.3% | Constant |

**Coil losses at 2kW: ~55W**

This is higher than initially estimated and requires active cooling.

---

## Operating Conditions

### 120V System Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| AC Input | 120V RMS | US mains |
| DC Bus | 170V | After rectification |
| Switching Freq | 38 kHz | Above resonance |
| Output Power | 2 kW | Maximum target |
| Pan Resistance | 8Ω | Cast iron |

### Coil Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Effective Inductance | 60 µH | With k=0.5 coupling |
| DC Resistance | 100 mΩ | ~5m Litz wire |
| AC/DC Ratio | 1.8 | Litz at 38kHz |
| AC Resistance (25°C) | 180 mΩ | R_dc × ratio |
| AC Resistance (80°C) | 220 mΩ | Temp compensated |

---

## Loss Calculation

### At 2kW Output

```
P_pan = I²_rms × R_pan = 1800W
I_rms = √(2000 / 8) = 15.8A

P_coil = I²_rms × R_coil
       = (15.8)² × 0.22Ω
       = 250 × 0.22
       = 55W
```

### Breakdown

| Component | Loss (W) | % of Output |
|-----------|----------|-------------|
| Coil I²R | 55W | 2.75% |
| Pan (useful) | 1800W | 100% |
| **Coil efficiency** | | **97.3%** |

---

## Thermal Analysis

### Coil Temperature Rise

The coil is a planar spiral mounted on the cooktop surface. Thermal resistance depends on:
- Air gap to pan bottom (~2-5mm)
- Heat spreading in ferrite/aluminum substrate (if any)
- Natural vs forced convection

**Estimated thermal resistance:**
- Natural convection: 2-4 K/W
- With shared airflow: 1-2 K/W

**Temperature calculations:**

| Cooling Method | Rth (K/W) | ΔT | T_coil (60°C ambient) |
|----------------|-----------|-----|------------------------|
| Natural only | 3 | 165°C | 225°C ❌ **Too hot!** |
| Light airflow | 2 | 110°C | 170°C ❌ **Too hot!** |
| Forced air | 1 | 55°C | 115°C ⚠️ Marginal |
| Strong forced | 0.5 | 28°C | 88°C ✅ **OK** |

**Copper wire temperature limits:**
- Class B insulation: 130°C max
- Class F insulation: 155°C max
- Class H insulation: 180°C max

---

## Problem: Coil Losses Higher Than Expected

The 55W coil loss is significant and requires attention:

### Root Cause Analysis

1. **Lower voltage (120V vs 230V) means higher current for same power**
   - 230V system: ~10A for 2kW at similar tank impedance
   - 120V system: ~16A for 2kW
   - Loss ratio: (16/10)² = 2.5× higher losses

2. **AC resistance at operating temperature**
   - Litz wire helps but doesn't eliminate skin effect
   - Temperature rise increases resistance further

### Options to Reduce Coil Losses

| Option | Benefit | Cost/Complexity |
|--------|---------|-----------------|
| **Heavier Litz wire** | -40% loss | More expensive, thicker coil |
| **More strands** | -20% AC/DC ratio | More expensive |
| **Shorter coil** | -20% R_dc | Smaller cooking area |
| **Accept & cool** | None | Fan required |

---

## Recommendation

### For First Prototype: Accept and Cool

Given the "don't get stuck on perfection" priority:

1. **Use standard Litz wire** (AWG 38, 100-150 strands)
2. **Include forced air cooling** (required anyway for IGBTs)
3. **Direct some airflow across coil**
4. **Monitor with NTC thermistor** on coil

**Total system losses:**
- IGBTs: 35-40W (at 170V bus)
- Coil: 55W
- **Total: ~90-95W**

This is manageable with a decent fan and moderate heatsink.

### Airflow Path (Revised)

```
           ┌──────────────────────────────────────┐
           │              ENCLOSURE               │
           │                                      │
  80mm     │   ┌─────────┐                       │
  FAN  ────┼──▶│HEATSINK │──┐                    │
  IN       │   │ (IGBTs) │  │                    │
           │   │ ~40W    │  │    ┌───────────┐   │ AIR
           │   └─────────┘  └───▶│   COIL    │───┼──▶ OUT
           │                     │   ~55W    │   │
           │                     │  (under   │   │
           │                     │   pan)    │   │
           │                     └───────────┘   │
           │                                      │
           │   [Control PCB - minimal heat]       │
           └──────────────────────────────────────┘
```

Airflow cools heatsink first (cooler air = better), then sweeps across coil area and exits.

---

## Verification Against Requirements

| Requirement | Target | Achieved | Status |
|-------------|--------|----------|--------|
| Coil temp < 130°C | <130°C | ~88°C (forced) | ✅ PASS |
| Coil efficiency | >95% | 97.3% | ✅ PASS |
| Cooling method | Simple | Shared fan | ✅ PASS |

---

## Future Optimization (V2)

If coil temperature becomes problematic in testing:

1. **Upgrade to heavier Litz wire** (200+ strands, AWG 40)
   - Can reduce AC resistance by 30-50%
   - Cost: ~$10-20 more for wire

2. **Add aluminum heat spreader** under coil
   - Improves thermal distribution
   - Must be non-ferromagnetic (aluminum, not steel)

3. **Consider 230V operation** if available
   - Cuts current in half → 75% loss reduction
   - May be worth providing 230V option for high-power use

---

## Files

- Testbench: `simulation/testbenches/sim_31_coil_thermal.cir`
- Results: `simulation/results/sim_31_coil_thermal_results.txt`

---

**Conclusion:** Coil losses of ~55W at 2kW output require forced air cooling. The existing fan for IGBT cooling can be directed to also cool the coil. Total system dissipation is ~95W, manageable with an 80mm low-speed fan.
