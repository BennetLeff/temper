# Temper PCB Trace Width Calculations

**Document ID:** REQ-ELEC-02  
**Version:** 1.0  
**Date:** 2025-12-16  
**Status:** Implemented  
**Standard:** IPC-2221B, IPC-2152

## 1. Design Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Ambient Temperature | 60°C | Worst-case kitchen environment |
| Max Temp Rise (traces) | 20°C | IPC-2221B recommendation |
| Max Temp Rise (pours) | 40°C | Acceptable for power zones |
| Outer Copper Weight | 2 oz (70 µm) | JLCPCB capability |
| Inner Copper Weight | 1 oz (35 µm) | Standard for 4-layer |
| Board Thickness | 1.6mm | Standard FR4 |

## 2. IPC-2221B Trace Width Formula

For external layers:
```
I = k × ΔT^0.44 × A^0.725
```
Where:
- I = Current (A)
- k = 0.048 (external) or 0.024 (internal)
- ΔT = Temperature rise (°C)
- A = Cross-sectional area (mils²)

Rearranging for width:
```
W = I / (k × ΔT^0.44 × t^0.725) × 1000
```
Where:
- W = Width (mils)
- t = Thickness (oz) × 1.37 mils/oz

## 3. Trace Width Calculations

### 3.1 DC Bus Path (HighVoltage Class)

**Requirements:**
- Current: 22A peak, 15A RMS
- Design current: 22A (worst-case)
- Layer: External (2 oz copper)
- Temperature rise: 40°C allowed for power

**Calculation (IPC-2221B):**
```
For 22A, 2oz copper, 40°C rise:
A = (22 / (0.048 × 40^0.44))^(1/0.725)
A = (22 / (0.048 × 4.57))^1.38
A = (100.2)^1.38
A = 478 mils²

Width = A / (2 × 1.37) = 478 / 2.74 = 174 mils = 4.4mm
```

**Recommendation:**
- **Minimum trace width: 5.0mm (200 mils)** with copper pour preferred
- Use solid copper pour for DC bus connections
- Multiple parallel traces or zones acceptable

**Verification:**
```
For 5mm (197 mils) × 2oz (2.74 mils):
A = 540 mils²
I = 0.048 × 40^0.44 × 540^0.725 = 24.7A ✓
```

### 3.2 Switch Node (HighVoltage Class)

**Requirements:**
- Current: 22A peak (same as DC bus)
- Frequency: 38 kHz
- Skin depth consideration

**Skin Effect Analysis:**
```
Skin depth δ = √(ρ / (π × f × µ))
For copper at 38 kHz:
δ = √(1.68e-8 / (π × 38000 × 4π×10^-7))
δ = 0.34mm = 340 µm
```

At 38 kHz, skin depth (340 µm) >> copper thickness (70 µm), so skin effect is negligible.

**Recommendation:**
- **Minimum: 5.0mm copper pour**
- Keep switch node AREA minimal (EMI source)
- Wide but short connection to resonant tank

### 3.3 Resonant Tank Connection

**Requirements:**
- Current: 22A peak at 38 kHz
- Minimize inductance (critical for resonance)

**Inductance Consideration:**
```
L_trace ≈ 5 nH/cm for 2mm trace
L_pour ≈ 1 nH/cm for 10mm pour
```

Tank inductance: 47 µH nominal
Trace inductance budget: <1% = 470 nH max

**Recommendation:**
- **Use 10mm+ wide copper pour**
- Maximum length: 47cm (but keep as short as possible)
- Practical target: <5cm connection, 10mm wide = 50 nH

### 3.4 IGBT Gate Drive (GateDrive Class)

**Requirements:**
- Current: 1.5A peak during switching
- Edge rate: <100ns (fast edges)
- Layer: External (2 oz copper)
- Temperature rise: 20°C

**Calculation:**
```
For 1.5A, 2oz copper, 20°C rise:
A = (1.5 / (0.048 × 20^0.44))^1.38
A = (1.5 / 0.15)^1.38 = 10^1.38 = 24 mils²
Width = 24 / 2.74 = 9 mils = 0.23mm
```

**But consider transient di/dt:**
```
V_drop = L × di/dt
For 1.5A in 100ns: di/dt = 15 MA/s
For 5nH trace: V_drop = 75mV (acceptable)
```

**Recommendation:**
- **Minimum: 0.5mm (20 mils)** for current and transient
- Keep gate traces SHORT (<25mm total)
- Route gate and return as differential pair
- Matched length high/low gate paths

### 3.5 Buck Converter Switch Node (600 kHz)

**Requirements:**
- Current: 3A peak
- Frequency: 600 kHz
- EMI-critical high dV/dt node

**Skin Effect at 600 kHz:**
```
δ = √(1.68e-8 / (π × 600000 × 4π×10^-7))
δ = 85 µm > 70 µm copper
```
Skin effect present but manageable.

**Calculation:**
```
For 3A, 2oz copper, 20°C rise:
A = (3 / 0.15)^1.38 = 68 mils²
Width = 68 / 2.74 = 25 mils = 0.6mm
```

**Recommendation:**
- **Minimum: 1.0mm (40 mils)**
- Keep switch node AREA minimal
- Immediate connection to output inductor
- Short loop to input capacitor

### 3.6 5V Distribution (Power Class)

**Requirements:**
- Current: 1.5A maximum (ESP32 + peripherals)
- Voltage drop budget: <100mV (2%)
- Layer: Can use internal

**Calculation:**
```
For 1.5A, 1oz internal copper, 20°C rise:
A = (1.5 / (0.024 × 20^0.44))^1.38
A = (1.5 / 0.075)^1.38 = 58 mils²
Width = 58 / 1.37 = 42 mils = 1.1mm
```

**Voltage Drop Check:**
```
R = ρL / A
For 1.1mm × 35µm copper, 100mm length:
R = (1.68e-8 × 0.1) / (1.1e-3 × 35e-6)
R = 43.6 mΩ
V_drop = 1.5A × 43.6mΩ = 65mV ✓
```

**Recommendation:**
- **Minimum: 1.0mm (40 mils)** on internal layers
- **Minimum: 0.8mm (32 mils)** on external 2oz layers
- Use via arrays (3+ vias) for layer transitions

### 3.7 3.3V Distribution (Power Class)

**Requirements:**
- Current: 500mA typical, 1A peak
- Voltage drop budget: <50mV (1.5%)

**Recommendation:**
- **Minimum: 0.5mm (20 mils)** on external layers
- Distribute from LDO output with star topology
- Local 100nF + 10µF decoupling at MCU

### 3.8 Gate Driver Supply (15V)

**Requirements:**
- Current: 100mA quiescent + gate charge bursts
- Peak: 500mA during simultaneous switching

**Calculation:**
```
For 0.5A, 2oz copper, 20°C rise:
A = (0.5 / 0.15)^1.38 = 8 mils²
Width = 8 / 2.74 = 3 mils (too thin for manufacturing)
```

**Recommendation:**
- **Minimum: 0.5mm (20 mils)** for manufacturability
- Heavy local decoupling (10µF + 100nF) at UCC21550
- Short connection from LMR51430 output

## 4. Summary Table

| Path | Current | Copper | ΔT | Min Width | Net Class |
|------|---------|--------|-----|-----------|-----------|
| DC Bus+ | 22A pk | 2 oz ext | 40°C | 5.0mm pour | HighVoltage |
| DC Bus- | 22A pk | 2 oz ext | 40°C | 5.0mm pour | HighVoltage |
| Switch Node | 22A pk | 2 oz ext | 40°C | 5.0mm pour | HighVoltage |
| Resonant Tank | 22A pk | 2 oz ext | 40°C | 10mm pour | HighVoltage |
| Gate H | 1.5A pk | 2 oz ext | 20°C | 0.5mm | GateDrive |
| Gate L | 1.5A pk | 2 oz ext | 20°C | 0.5mm | GateDrive |
| Buck SW | 3A pk | 2 oz ext | 20°C | 1.0mm | Power |
| +5V | 1.5A | 1 oz int | 20°C | 1.0mm | Power |
| +3.3V | 1A pk | 2 oz ext | 20°C | 0.5mm | Power |
| +15V | 0.5A | 2 oz ext | 20°C | 0.5mm | Power |
| AC Mains | 15A | 2 oz ext | 40°C | 4.0mm pour | ACMains |

## 5. Via Requirements

Layer transitions for power paths require multiple vias:

| Current | Via Size | Via Current | Vias Required |
|---------|----------|-------------|---------------|
| 22A | 0.6mm drill | 3A each | 8+ vias (array) |
| 15A | 0.6mm drill | 3A each | 6+ vias (array) |
| 3A | 0.5mm drill | 2A each | 2 vias |
| 1.5A | 0.4mm drill | 1.5A each | 2 vias |
| 0.5A | 0.3mm drill | 1A each | 1 via |

Via current capacity based on IPC-2221B with 20°C rise.

## 6. Thermal Considerations

**High-Current Zones:**
- DC bus copper pours act as heat spreaders
- Connect to internal planes for additional thermal mass
- Thermal relief on ground connections under power components

**Power Dissipation in Traces:**
```
P = I²R = I² × (ρL / A)
For 22A in 5mm × 70µm × 50mm trace:
R = (1.68e-8 × 0.05) / (5e-3 × 70e-6) = 2.4 mΩ
P = 22² × 0.0024 = 1.16W
```
This is acceptable with 40°C rise allowance.

## 7. Design Rules for KiCad

Based on these calculations, the following design rules are configured in the project:

```
Track Widths Available:
  0.2mm - Default signals
  0.3mm - Low-current signals
  0.5mm - Gate drive, 3.3V
  0.8mm - Moderate power
  1.0mm - 5V, buck converter
  1.5mm - Power distribution
  2.0mm - Heavy power
  2.5mm - AC mains
  3.0mm - DC bus minimum
```

## 8. Verification Checklist

- [x] DC bus trace width verified (≥5mm pour)
- [x] Switch node minimized for EMI
- [x] Gate drive paths matched and short
- [x] Buck converter loop minimized
- [x] 5V voltage drop <100mV verified
- [x] Via arrays sized for current
- [x] Thermal dissipation acceptable

## 9. References

- IPC-2221B: Generic Standard on Printed Board Design
- IPC-2152: Standard for Determining Current Carrying Capacity
- PCB_SPECIFICATION.md: Board stack-up and copper weights
- NET_CLASS_SPECIFICATION.md: Net class definitions
- LMR51430 Thermal Design Guide (TI)
- UCC21550 Layout Guidelines (TI)

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Agent | Initial calculations |
