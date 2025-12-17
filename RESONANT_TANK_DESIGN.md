# Resonant Tank Design Document

## Temper Induction Cooker - LC Resonant Tank and Pan Load

**Document Version:** 1.0  
**Date:** December 13, 2025  
**Status:** Design Complete, Verified by Simulation

---

## 1. Executive Summary

This document describes the design of the series LC resonant tank for the Temper induction cooker. The resonant tank, combined with the half-bridge power stage, delivers power to ferromagnetic cookware through electromagnetic induction.

### Key Design Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Resonant Frequency | 35.8 kHz | Calculated from L and C |
| Operating Frequency | 38-50 kHz | Above resonance for ZVS |
| Coil Inductance | 80 µH (uncoupled) | Litz wire spiral coil |
| Effective Inductance | 54-64 µH | With pan coupled |
| Resonant Capacitor | 330 nF | Polypropylene film |
| Reflected Resistance | 5-20 Ω | Depends on pan material |
| Peak Coil Current | 30-50 A | At 2 kW output |
| Power Range | 200 W - 2 kW | Controlled by frequency |

---

## 2. Induction Cooking Theory

### 2.1 Operating Principle

Induction cooking transfers power to cookware through electromagnetic induction:

1. **AC current** flows through the induction coil
2. **Alternating magnetic field** penetrates the pan bottom
3. **Eddy currents** are induced in the ferromagnetic pan
4. **I²R heating** in the pan material heats the cookware

### 2.2 Equivalent Circuit Model

The induction coil and pan form a loosely-coupled transformer:

```
         INDUCTION COIL (Primary)         PAN (Secondary)
         ┌─────────────────────┐         ┌─────────────────┐
         │                     │         │                 │
    ─────┤  L1 (80µH)  R_coil ├── M ────┤  L2    R_pan   │
         │   ○○○○○     0.1Ω   │  (k)    │  ~1µH  5-50Ω   │
         │                     │         │                 │
         └─────────────────────┘         └────────┬────────┘
                                                  │
                                              (shorted)
```

Where:
- **L1**: Primary inductance (induction coil)
- **L2**: Secondary inductance (pan as single-turn)
- **k**: Coupling coefficient (0.2 to 0.6 typical)
- **R_pan**: Pan equivalent resistance (material dependent)
- **M = k√(L1×L2)**: Mutual inductance

### 2.3 Reflected Impedance

Since the pan acts as a shorted secondary, we can simplify using reflected impedance:

```
Z_reflected = (ω × M)² / (R_pan + jωL2)
            ≈ R_ref + jX_ref
```

At operating frequencies (30-50 kHz) with R_pan >> ωL2:

```
R_ref ≈ k² × ω² × L1² / R_pan
L_eff ≈ L1 × (1 - k²)
```

This gives the simplified model used in simulation:

```
         C_res              L_eff          R_coil    R_ref
    o────||────o────YYYY────o───/\/\/───o───/\/\/───o
    |         330nF       54-64µH       0.1Ω       5-20Ω
    |                                               |
    o───────────────────────────────────────────────o
```

---

## 3. Pan Material Characteristics

### 3.1 Coupling and Resistance by Material

| Pan Material | Coupling (k) | R_pan (Ω) | Power Efficiency | Notes |
|--------------|--------------|-----------|------------------|-------|
| Cast Iron | 0.5 - 0.6 | 5 - 15 | Excellent | Best for induction |
| Carbon Steel | 0.4 - 0.5 | 8 - 20 | Very Good | Woks, paella pans |
| Stainless (magnetic) | 0.3 - 0.4 | 15 - 35 | Good | 430 SS, tri-ply base |
| Stainless (non-mag) | 0.1 - 0.2 | 50 - 200 | Poor | 304 SS, won't heat |
| Aluminum | 0.05 - 0.15 | 100+ | Very Poor | Requires adapter |
| Copper | 0.05 - 0.1 | 50+ | Poor | Requires adapter |
| **No Pan** | ~0 | ∞ | N/A | Detection required |

### 3.2 Effect on Resonant Frequency

Pan presence shifts the effective inductance:

| Condition | L_eff (µH) | f_res (kHz) | Notes |
|-----------|------------|-------------|-------|
| No pan | 80 | 31.0 | Full inductance |
| Cast iron | 54 | 37.9 | k = 0.55 |
| Stainless | 64 | 34.8 | k = 0.35 |

This frequency shift enables **pan detection**: measuring resonant frequency or Q-factor indicates whether a suitable pan is present.

---

## 4. Resonant Tank Design

### 4.1 Component Selection

#### Resonant Capacitor (C_res)

**Requirements:**
- High voltage rating (2× operating voltage minimum)
- Low ESR for high current operation
- High ripple current capability
- Stable over temperature

**Selected:** 330 nF, 800V polypropylene film

| Parameter | Specification |
|-----------|---------------|
| Capacitance | 330 nF ±5% |
| Voltage Rating | 800 VDC minimum (1000V preferred) |
| Dielectric | Polypropylene (PP) |
| ESR | < 10 mΩ |
| Ripple Current | > 15 A RMS |
| Package | WIMA MKP4 or equivalent |

**Voltage stress calculation:**
```
V_cap_peak_steady = I_peak × X_C
                  = 40A × (1 / (2π × 38kHz × 330nF))
                  = 40A × 12.7Ω
                  = 508V peak (steady-state)

V_cap_peak_transient = 648V (observed in startup simulation)
```

**Voltage rating justification:**
- Steady-state: 508V peak
- Transient: 648V peak (startup overshoot)
- 800V rating provides 23% margin over worst-case transient
- 1000V rating provides 54% margin (preferred for production)

#### Induction Coil (L1)

**Requirements:**
- 80 µH uncoupled inductance
- Low AC resistance (Litz wire)
- Flat spiral geometry for uniform heating
- High temperature tolerance

**Specifications:**

| Parameter | Value |
|-----------|-------|
| Inductance | 80 µH ±10% |
| Wire Type | Litz wire (100 × 0.1mm strands) |
| Turns | 20-25 turns |
| Diameter | 160-200 mm |
| AC Resistance | < 100 mΩ at 40 kHz |
| Insulation | Silicone or high-temp enamel |

### 4.2 Resonant Frequency Calculation

```
f_res = 1 / (2π√(L_eff × C_res))

With cast iron pan (L_eff = 60µH, C = 330nF):
f_res = 1 / (2π√(60µH × 330nF))
f_res = 1 / (2π × 4.45µs)
f_res = 35.8 kHz
```

### 4.3 Quality Factor

```
Q = ω × L_eff / R_total
  = 2π × 35.8kHz × 60µH / 8.1Ω
  = 1.67
```

**Low Q is intentional!** High Q would mean low power transfer. The power delivered to the pan is:

```
P_pan = I_rms² × R_ref
      = (30A)² × 8Ω
      = 7200W (peak)
      = ~2000W (average at 47% duty)
```

---

## 5. Operating Modes

### 5.1 Zero Voltage Switching (ZVS)

Operating above resonance ensures inductive mode where current lags voltage:

```
Operating Region:
                    │
                    │       ZVS Region
           ┌────────┼──────────────────►
           │        │      (inductive)
     P     │        │
     o     │        │
     w  ───┼────────┼───────────────────
     e     │    f_res
     r     │        │
           │        │
           │        │
           └────────┼──────────────────►
                    │                  f
```

**ZVS Benefits:**
- Near-zero turn-on losses
- Reduced EMI (soft switching)
- No snubbers required
- Higher efficiency (>95% achievable)

**ZVS Conditions:**
1. f_sw > f_res (operate above resonance)
2. Dead-time allows voltage transition
3. Tank current sufficient to discharge Coss

### 5.2 Power Control

Power is controlled by varying switching frequency:

| Frequency | Power Level | Mode |
|-----------|-------------|------|
| 35 kHz | Maximum (~2.5 kW) | Near resonance |
| 38 kHz | High (2 kW) | Optimal ZVS |
| 45 kHz | Medium (1 kW) | Safe ZVS |
| 55 kHz | Low (500 W) | Deep ZVS |
| 70 kHz | Simmer (200 W) | Light load |

### 5.3 Phase Relationship

```
                 ZVS Turn-On
                     │
    V_switch ────────┼──┐     ┌──────
                     │  │     │
                     │  └─────┘
                     │
    I_tank   ────────┼────────┐
                     │     ┌──┘
                     │─────┘
                     │
                 Current lags (inductive)
                 Diode conducts before gate
```

---

## 6. Simulation Results

### 6.1 AC Analysis (sim_24)

**Resonant frequency measurement:**

| Parameter | Designed | Simulated |
|-----------|----------|-----------|
| Resonant frequency | 35.8 kHz | 35.7 kHz |
| Impedance at resonance | 8.1 Ω | 8.2 Ω |
| Q-factor | 1.67 | 1.65 |

**Impedance vs Frequency:**

```
|Z| (Ω)
   50 │
      │    ╲              ╱
   40 │     ╲            ╱
      │      ╲          ╱
   30 │       ╲        ╱
      │        ╲      ╱
   20 │         ╲    ╱
      │          ╲  ╱
   10 │           ╲╱ ← f_res = 35.8 kHz
      │            
    0 └────────────────────────────
      20   30   40   50   60  f(kHz)
```

### 6.2 ZVS Verification (sim_25)

**Operating at 38 kHz (above resonance):**

| Measurement | Value | Target | Status |
|-------------|-------|--------|--------|
| V_ce at turn-on | < 5V | < 10V | ✓ PASS |
| Current phase | -12° | Negative | ✓ PASS |
| Dead-time used | 500 ns | 500 ns | ✓ PASS |
| ZVS achieved | Yes | Yes | ✓ PASS |

### 6.3 Full Power Stage (sim_26)

**Operating at 38 kHz, 320V DC bus:**

| Parameter | Value | Target | Status |
|-----------|-------|--------|--------|
| Peak coil current | 42 A | 30-50 A | ✓ PASS |
| RMS coil current | 28 A | - | OK |
| Power to pan | 1.9 kW | 2 kW | ✓ PASS |
| Efficiency | 93% | >90% | ✓ PASS |

---

## 7. Component Stress Analysis

### 7.1 Resonant Capacitor

| Stress | Value | Rating | Margin |
|--------|-------|--------|--------|
| Voltage (peak steady) | 508 V | 800 V | 58% |
| Voltage (peak transient) | 648 V | 800 V | 23% |
| Voltage (RMS) | ~340 V | 500 V AC | 47% |
| Current (RMS) | 28 A | 15 A | **NEED 2 CAPS** |

**CRITICAL SAFETY NOTE:** Initial design with 630V rated capacitors had NEGATIVE margin during startup transients (648V on 630V rated part = -2.9% margin). This is a fire hazard and has been corrected to 800V minimum rating.

**Recommendation:** Use 2× 150nF/800V (or 1000V) capacitors in parallel to:
1. Share ripple current (28A / 2 = 14A per cap)
2. Provide redundancy
3. Ensure adequate voltage margin on transients

### 7.2 Induction Coil

| Stress | Value | Notes |
|--------|-------|-------|
| Current (peak) | 42 A | Well below wire limit |
| Current (RMS) | 28 A | Litz wire handles easily |
| Temperature rise | < 50°C | With airflow |
| Voltage | < 50 V | No HV insulation needed |

### 7.3 IGBTs (IKW40N120H3)

| Stress | Value | Rating | Margin |
|--------|-------|--------|--------|
| Voltage | 320 V | 1200 V | 73% |
| Current (peak) | 42 A | 80 A | 47% |
| Current (avg) | 14 A | 40 A | 65% |

With ZVS, switching losses are minimal. Total IGBT loss ≈ 25W each.

---

## 8. Pan Detection

### 8.1 Detection Methods

1. **Resonant frequency shift**: No pan = lower f_res
2. **Q-factor measurement**: No pan = higher Q (less damping)
3. **Current magnitude**: No pan = higher peak current
4. **Phase angle**: No pan = more reactive

### 8.2 Recommended Approach

Monitor resonant tank current during low-power pulse:

| Condition | I_peak @ 100W | Action |
|-----------|---------------|--------|
| Cast iron pan | 5-8 A | Normal operation |
| Stainless pan | 8-12 A | Normal operation |
| No pan | > 20 A | Inhibit, display error |
| Small object | < 3 A | Inhibit (insufficient loading) |

### 8.3 Implementation

```
1. Apply low-power test pulse (f = 50 kHz, 100 ms)
2. Measure I_peak via current transformer
3. If 3A < I_peak < 15A: Pan detected, proceed
4. If I_peak > 15A: No pan, display error
5. If I_peak < 3A: Unsuitable pan, display error
```

---

## 9. Design Files Reference

### Simulation Models

| File | Description |
|------|-------------|
| `simulation/models/pan_load.sub` | Pan/coil equivalent circuit models |
| `simulation/models/IKW40N120H3.lib` | IGBT SPICE model |

### Simulation Testbenches

| File | Description |
|------|-------------|
| `sim_24_resonant_tank_ac.cir` | AC frequency sweep analysis |
| `sim_25_zvs_verification.cir` | Zero voltage switching verification |
| `sim_26_full_power_stage.cir` | Complete power stage integration |

### Related Documentation

| File | Description |
|------|-------------|
| `HALF_BRIDGE_VERIFICATION_REPORT.md` | Power stage verification |
| `SAFETY_INTERLOCK_DESIGN.md` | Protection systems |

---

## 10. Bill of Materials (Power Stage)

| Item | Part Number | Qty | Notes |
|------|-------------|-----|-------|
| Resonant capacitor | WIMA MKP4 150nF/1000V (FKP4T021505D00) | 2 | In parallel for current sharing |
| Resonant capacitor (alt) | KEMET R76 150nF/800V (R76MR3150AA00M) | 2 | Alternative if 1000V unavailable |
| Induction coil | Custom | 1 | 80µH Litz wire |
| High-side IGBT | IKW40N120H3 | 1 | With heatsink |
| Low-side IGBT | IKW40N120H3 | 1 | With heatsink |
| Gate driver | UCC21550 | 1 | Isolated |
| Bootstrap diode | UF4007 | 1 | Fast recovery |
| Bootstrap cap | 10µF/25V | 1 | Ceramic X7R |
| Bus capacitor | 470µF/450V | 1 | Electrolytic |
| Film bus cap | 1µF/630V | 1 | PP film |

---

## 11. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-13 | Initial release |

---

**END OF DOCUMENT**
