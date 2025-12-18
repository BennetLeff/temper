# PCB Safety Design Rules (Creepage & Clearance)

**Project:** Temper Induction Cooker  
**Standard:** Derived from IEC 60335-1 / 60335-2-6  
**Status:** MANDATORY for PCB Layout  
**Date:** 2025-12-17

---

## 1. Voltage Domain Definitions

| Domain | Voltage (max) | Description | Safety Class |
|--------|---------------|-------------|--------------|
| **MAINS** | 120V AC | AC Input Line and Neutral | Hazardous |
| **DC_BUS** | 170V DC | Rectified DC Bus (+/-) | Hazardous |
| **ISO_GATE** | 170V DC | High-side gate drive (floating) | Hazardous |
| **SELV_LV** | 5V / 3.3V | Control logic, MCU, Sensors | User-Accessible |

---

## 2. Mandatory Isolation Distances

All distances are minimums. Use larger values where space allows.

### 2.1 Reinforced Isolation (Hazardous to SELV)
*Applies to: MAINS to LV, DC_BUS to LV, ISO_GATE to LV*

- **Clearance (Air):** 4.0 mm
- **Creepage (Surface):** 6.5 mm
- **Design Target (PCB):** **8.0 mm** (Provides margin for manufacturing)

### 2.2 Basic Isolation (Hazardous to Hazardous)
*Applies to: ISO_GATE to DC_BUS, Channel A to Channel B*

- **Clearance (Air):** 2.0 mm
- **Creepage (Surface):** 3.0 mm
- **Design Target (PCB):** **4.0 mm**

### 2.3 Functional Isolation (Within same domain)
*Applies to: DC_BUS+ to DC_BUS-, L to N*

- **Clearance (Air):** 1.0 mm
- **Creepage (Surface):** 1.5 mm
- **Design Target (PCB):** **2.0 mm**

---

## 3. PCB Layout Requirements

1.  **Isolation Barriers:**
    - High-voltage domains must be grouped in a distinct "Hot Zone".
    - A clear 8mm "No-Copper" keepout must separate the Hot Zone from the SELV Zone.
    - No components or traces may straddle the isolation barrier except for certified isolation components (UCC21550, ADUM1250).

2.  **V-Grooves and Slots:**
    - For high-pollution areas (near the coil/mains entry), physical slots (cutouts) in the PCB are recommended to increase creepage.
    - Slot width: 1.0 mm minimum.

3.  **Corner Radii:**
    - High-voltage traces should use rounded corners or 45° bends. Avoid sharp 90° corners to prevent corona discharge and localized field stress.

4.  **Solder Mask:**
    - Solder mask is mandatory over all high-voltage traces but does **not** contribute to creepage reduction per IEC 60335.

---

## 4. Certification Checklist

- [ ] All MAINS to SELV distances ≥ 8.0 mm.
- [ ] All DC_BUS to SELV distances ≥ 8.0 mm.
- [ ] Isolation components (UCC21550) have 8mm creepage under the package.
- [ ] No SELV traces routed under High Voltage components.
- [ ] Protective Earth (PE) connection is robust and meets 0.1 Ω continuity.

---
