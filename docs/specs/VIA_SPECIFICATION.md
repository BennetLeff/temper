# Temper PCB Via Specification

**Document ID:** REQ-ELEC-03  
**Version:** 1.0  
**Date:** 2025-12-16  
**Status:** Implemented  
**Standard:** IPC-2221B, IPC-4761

## 1. Overview

This document specifies via types, sizes, current ratings, and thermal properties for the Temper induction cooker PCB. All vias are through-hole (PTH) suitable for standard 4-layer fab processes.

## 2. Via Types

### 2.1 Standard Signal Via

| Property | Value | Notes |
|----------|-------|-------|
| Drill Diameter | 0.3mm (12 mil) | Standard PTH |
| Finished Hole | 0.25mm (10 mil) | After plating |
| Pad Diameter | 0.6mm (24 mil) | Outer layers |
| Annular Ring | 0.15mm (6 mil) | IPC Class 2 minimum |
| Current Rating | 1.0A | Per via, 20°C rise |
| Thermal Resistance | ~120°C/W | Open via |

**Usage:**
- Digital signals (SPI, I2C, GPIO)
- Low-current control signals
- Ground stitching between layers

**Net Classes:** Default

### 2.2 Power Via

| Property | Value | Notes |
|----------|-------|-------|
| Drill Diameter | 0.5mm (20 mil) | Medium PTH |
| Finished Hole | 0.45mm (18 mil) | After plating |
| Pad Diameter | 1.0mm (40 mil) | Outer layers |
| Annular Ring | 0.25mm (10 mil) | Enhanced reliability |
| Current Rating | 2.0A | Per via, 20°C rise |
| Thermal Resistance | ~80°C/W | Open via |

**Usage:**
- +5V, +3.3V, +15V distribution
- Moderate current paths (1-3A)
- Power plane connections

**Net Classes:** Power, GateDrive

### 2.3 High-Current Via

| Property | Value | Notes |
|----------|-------|-------|
| Drill Diameter | 0.6mm (24 mil) | Large PTH |
| Finished Hole | 0.55mm (22 mil) | After plating |
| Pad Diameter | 1.2mm (48 mil) | Outer layers |
| Annular Ring | 0.30mm (12 mil) | High reliability |
| Current Rating | 3.0A | Per via, 20°C rise |
| Thermal Resistance | ~60°C/W | Open via |

**Usage:**
- DC bus layer transitions
- AC mains connections
- High-current power paths (>3A)
- IGBT power connections

**Net Classes:** HighVoltage, ACMains

### 2.4 Thermal Via

| Property | Value | Notes |
|----------|-------|-------|
| Drill Diameter | 0.4mm (16 mil) | Optimized for thermal |
| Finished Hole | 0.35mm (14 mil) | After plating |
| Pad Diameter | 0.8mm (32 mil) | Can be tented |
| Annular Ring | 0.20mm (8 mil) | Standard |
| Current Rating | N/A | Thermal purpose only |
| Thermal Resistance | ~70°C/W | Filled/plugged |
| Thermal Resistance | ~40°C/W | Capped with solder |

**Usage:**
- Thermal pad connections (IGBTs, buck converter)
- Heat spreading to internal planes
- Component cooling

**Net Classes:** Any (typically GND or thermal pad nets)

## 3. Via Current Capacity Calculations

### IPC-2221B Via Current Formula

Via current capacity is limited by the barrel plating:
```
I_via = k × (A_barrel)^0.725 × (ΔT)^0.44
```

Where:
- A_barrel = π × d × t_plating = π × drill × 25µm typical plating

### Calculation Examples

**0.3mm Drill (Signal Via):**
```
A_barrel = π × 0.3mm × 0.025mm = 0.0236 mm²
A_barrel = 36.6 mils²
I = 0.048 × 36.6^0.725 × 20^0.44 = 1.03A
```

**0.5mm Drill (Power Via):**
```
A_barrel = π × 0.5mm × 0.025mm = 0.0393 mm²
A_barrel = 60.9 mils²
I = 0.048 × 60.9^0.725 × 20^0.44 = 1.98A
```

**0.6mm Drill (High-Current Via):**
```
A_barrel = π × 0.6mm × 0.025mm = 0.0471 mm²
A_barrel = 73.1 mils²
I = 0.048 × 73.1^0.725 × 20^0.44 = 2.89A
```

## 4. Via Array Requirements

### 4.1 DC Bus Via Array

**Requirements:**
- Total current: 22A peak, 15A RMS
- Design current: 22A (worst case)
- Via type: High-Current (3A each)

**Calculation:**
```
N_vias = I_total / I_via = 22A / 3A = 7.3
With 50% safety margin: N = 11 vias minimum
Recommended: 12 vias (3×4 array)
```

**Array Specification:**
- Pattern: 3×4 rectangular array
- Pitch: 2.0mm × 2.0mm
- Total footprint: 6mm × 8mm
- Via type: 0.6mm drill / 1.2mm pad

### 4.2 AC Mains Via Array

**Requirements:**
- Total current: 15A RMS
- Via type: High-Current (3A each)

**Calculation:**
```
N_vias = 15A / 3A = 5.0
With 50% margin: N = 7.5 vias minimum
Recommended: 9 vias (3×3 array)
```

**Array Specification:**
- Pattern: 3×3 rectangular array
- Pitch: 2.0mm × 2.0mm
- Total footprint: 6mm × 6mm

### 4.3 Buck Converter Input Via Array

**Requirements:**
- Total current: 3A peak
- Via type: Power (2A each)

**Calculation:**
```
N_vias = 3A / 2A = 1.5
With margin: N = 3 vias minimum
```

**Array Specification:**
- Pattern: 1×3 linear or triangle
- Pitch: 1.5mm

### 4.4 5V Distribution Via Array

**Requirements:**
- Total current: 1.5A
- Via type: Power (2A each)

**Specification:**
- Minimum: 2 vias per layer transition
- Pattern: Adjacent pair

## 5. Thermal Via Arrays

### 5.1 IGBT Thermal Pad

**Thermal Requirements:**
- Power dissipation: 20W per IGBT
- Target thermal resistance: <5°C/W to copper pour

**Via Thermal Resistance:**
```
R_via ≈ 70°C/W (filled 0.4mm via)
R_array = R_via / N
For R_array < 5°C/W: N > 14 vias
```

**Array Specification:**
- Via count: 16 minimum (4×4 array)
- Via type: Thermal (0.4mm drill)
- Pitch: 1.2mm (minimum = 3 × drill diameter)
- Fill: Solder paste capping recommended
- Pattern: Cover entire thermal pad area

### 5.2 LMR51430 Buck Converter Thermal Pad

**Thermal Requirements:**
- Power dissipation: 2W
- Target thermal resistance: <20°C/W

**Array Specification:**
- Via count: 6 minimum (2×3 array)
- Via type: Thermal (0.4mm drill)
- Pitch: 1.0mm
- Connect to internal GND plane

### 5.3 UCC21550 Thermal Pad

**Thermal Requirements:**
- Power dissipation: 0.5W
- Exposed pad for heat dissipation

**Array Specification:**
- Via count: 4 minimum (2×2 array)
- Via type: Thermal (0.4mm drill)
- Connect to isolated GND or heat spreading copper

## 6. Via Placement Guidelines

### 6.1 Signal Vias

- **Minimum spacing:** 0.6mm center-to-center (for 0.3mm drill)
- **Placement:** Adjacent to pads, not under components
- **Ground stitching:** Every 10mm along board edges
- **High-speed signals:** Ground via within 1mm of signal via

### 6.2 Power Vias

- **Minimum spacing:** 1.2mm center-to-center (for 0.5mm drill)
- **Placement:** Near power pins, distributed along traces
- **Decoupling:** Via from cap pad directly to ground plane
- **Array placement:** Centered on copper pour connections

### 6.3 Thermal Vias

- **Minimum spacing:** 3× drill diameter (1.2mm for 0.4mm via)
- **Placement:** Within thermal pad footprint
- **Pattern:** Fill thermal pad area uniformly
- **Tenting:** Solder mask tent on bottom (prevent solder wicking)
- **Capping:** Solder paste on top (improves thermal contact)

### 6.4 Via-in-Pad Considerations

For fine-pitch components where via-in-pad is required:
- Use 0.3mm drill maximum
- Filled and planarized (IPC-4761 Type VII)
- Additional cost - use only where necessary

## 7. KiCad Configuration

### Via Sizes in Project

```json
"via_dimensions": [
  { "diameter": 0.6, "drill": 0.3 },  // Signal
  { "diameter": 0.8, "drill": 0.4 },  // Thermal
  { "diameter": 1.0, "drill": 0.5 },  // Power
  { "diameter": 1.2, "drill": 0.6 }   // High-Current
]
```

### Design Rules

| Rule | Value |
|------|-------|
| Min via drill | 0.3mm |
| Min via pad | 0.6mm |
| Min annular ring | 0.15mm |
| Via-to-via clearance | 0.3mm |
| Via-to-track clearance | 0.2mm |
| Via-to-pad clearance | 0.2mm |

## 8. Manufacturing Notes

### Standard Fab House Capabilities (JLCPCB/PCBWay)

| Parameter | Standard | Advanced |
|-----------|----------|----------|
| Min drill | 0.3mm | 0.2mm |
| Min annular ring | 0.15mm | 0.1mm |
| Drill tolerance | ±0.05mm | ±0.03mm |
| Via fill | No | Optional ($$) |
| Via plug | No | Optional ($$) |

### Recommendations

1. **Standard vias (0.3-0.6mm):** No special process needed
2. **Thermal vias:** Request solder mask tenting on bottom
3. **Via-in-pad:** Request filled & capped (significant cost increase)
4. **Via arrays:** Verify drill-to-drill spacing meets fab minimum

## 9. Verification Checklist

- [ ] Via types defined for all net classes
- [ ] Via current ratings verified for all power paths
- [ ] Via arrays sized for DC bus (12+ vias)
- [ ] Via arrays sized for AC mains (9+ vias)
- [ ] Thermal via arrays cover IGBT pads (16+ vias each)
- [ ] Thermal via arrays for buck converter (6+ vias)
- [ ] Via spacing meets DRC minimums
- [ ] Via-in-pad used only where necessary

## 10. References

- IPC-2221B: Generic Standard on Printed Board Design
- IPC-4761: Design Guide for Protection of PTH Vias
- IPC-2152: Standard for Determining Current Carrying Capacity
- TRACE_WIDTH_CALCULATIONS.md: Companion trace document
- NET_CLASS_SPECIFICATION.md: Net class definitions
- THERMAL_DESIGN_GUIDE.md: Thermal budget and requirements

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Agent | Initial specification |
