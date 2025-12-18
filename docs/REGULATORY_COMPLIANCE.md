# Regulatory Compliance & Certification Strategy

**Project:** Temper Induction Cooker  
**Version:** 1.0  
**Date:** 2025-12-17

---

## 1. Executive Summary

This document defines the regulatory certification strategy for the Temper induction cooker. The primary target markets are North America (UL/CSA) and Europe (CE). Compliance is a mandatory requirement for product launch to ensure safety and legality.

**Target Certification:**
- **Safety:** IEC/UL 60335-2-6 (Household Cooking Appliances)
- **EMC:** FCC Part 15 / EN 55014-1 (CISPR 14)
- **Environment:** RoHS, REACH, WEEE

---

## 2. Applicable Standards

### 2.1 North America (UL/CSA)

| Standard | Title | Purpose |
|----------|-------|---------|
| **UL 858** | Household Electric Ranges | Primary safety standard for USA |
| **CSA C22.2 No. 64** | Household Cooking & Liquid-Heating Appliances | Primary safety standard for Canada |
| **FCC Part 15 Subpart B** | Unintentional Radiators | EMI emissions limits (Class B - Residential) |
| **FCC Part 18** | Industrial, Scientific, and Medical Equipment | EMI limits specifically for induction cooking |

*Note: Induction cookers fall under FCC Part 18 (ISM) because they generate RF energy for heating, but consumer units must also meet Part 15B for digital logic.*

### 2.2 Europe (CE Mark)

**Low Voltage Directive (LVD) 2014/35/EU:**
- **EN 60335-1:** Household and similar electrical appliances - Safety - Part 1: General requirements
- **EN 60335-2-6:** Particular requirements for stationary cooking ranges, hobs, ovens and similar appliances
- **EN 62233:** Measurement methods for electromagnetic fields of household appliances (Human Exposure)

**EMC Directive 2014/30/EU:**
- **EN 55014-1:** EMC - Requirements for household appliances - Emission
- **EN 55014-2:** EMC - Requirements for household appliances - Immunity
- **EN 61000-3-2:** Limits for harmonic current emissions
- **EN 61000-3-3:** Limitation of voltage changes, voltage fluctuations and flicker

**Other Directives:**
- **RoHS (2011/65/EU):** Restriction of Hazardous Substances
- **REACH (EC 1907/2006):** Chemical substances registration
- **WEEE (2012/19/EU):** Waste Electrical and Electronic Equipment
- **Ecodesign (2009/125/EC):** Standby power consumption limits

---

## 3. Product Labeling Requirements

### 3.1 Main Rating Plate (Back/Bottom)

Must be permanent, legible, and durable (rub test per IEC 60335).

**Required Content:**
1.  **Manufacturer:** Temper Project (or legal entity)
2.  **Model:** Temper v1
3.  **Voltage:** 120 V AC (US) / 230 V AC (EU)
4.  **Frequency:** 60 Hz (US) / 50 Hz (EU)
5.  **Power:** 1800 W (US) / 2000 W (EU)
6.  **Serial Number:** [Barcode/Text]
7.  **Symbols:**
    - Double Insulation (Class II) or Earth Ground (Class I) symbol
    - WEEE Trash Can (EU)
    - CE Mark (EU)
    - UL/CSA Mark (if certified)
    - FCC ID (if applicable)
    - "Household Use Only"
    - "Caution: Hot Surface" symbol

### 3.2 Warning Labels

**Location:** Near cooking surface and user interface.

1.  **Hot Surface:** "CAUTION: Surface remains hot after use."
2.  **Magnetic Field:** "Induction cooking. Persons with pacemakers should consult physician." (Recommended)
3.  **Empty Pan:** "Do not heat empty pans."

---

## 4. User Manual Requirements

The user manual is part of the safety system. It must include specific warnings from IEC 60335.

**Mandatory Sections:**
1.  **Safety Instructions:**
    - "Read all instructions before use."
    - "Do not immerse cord, plug, or appliance in water."
    - "Unplug when not in use."
    - "Do not operate with damaged cord or plug."
    - "Use only on flat, dry surface."
    - "Metallic objects such as knives, forks, spoons and lids should not be placed on the hob surface since they can get hot."
2.  **Installation:** Clearance requirements (10cm from walls), ventilation needs.
3.  **Operation:** How to set power/temp, error codes explanation.
4.  **Cleaning:** "Unplug before cleaning," "Do not use abrasive cleaners."
5.  **Troubleshooting:** Guide for common issues.
6.  **Disposal:** WEEE instructions.

---

## 5. Technical Documentation (Technical File)

Required for CE marking self-declaration and safety agency submission.

1.  **General Description:** Overview, photos, block diagram.
2.  **Design Drawings:** Schematics, PCB layout, BOM, mechanical assembly.
3.  **Component Certifications:** Certificates for critical components (Relays, X/Y Caps, Fuses, Connectors, Switches).
    - *Action:* Ensure all Safety-Critical components in BOM have UL/VDE certs.
4.  **Test Reports:**
    - LVD Safety Report (Internal or Lab)
    - EMC Test Report (Lab)
    - EMF Exposure Report
5.  **Manuals:** User manual and service manual.
6.  **Declaration of Conformity (DoC):** Signed legal document.

---

## 6. Compliance Checklist (Self-Audit)

**Electrical Safety:**
- [ ] Creepage/Clearance distances > 6mm for mains (Reinforced)
- [ ] Protective Earth connection resistance < 0.1 Ω
- [ ] Leakage current < 0.75 mA (Class I) or < 0.25 mA (Class II)
- [ ] Dielectric strength (Hi-Pot) test 1250V / 3000V passed
- [ ] Residual voltage < 34V on plug pins 1s after unplugging (Bleeder resistors)

**Thermal:**
- [ ] Surface temp rise < limits (Knobs: 45K, Sides: 65K)
- [ ] Internal wire temp < insulation rating
- [ ] PCB temp < TI rating (usually 105°C or 130°C)

**Mechanical:**
- [ ] Enclosure rigidity (Impact test)
- [ ] Strain relief pull test (30N for 25 times)
- [ ] Stability (10° tilt test)
- [ ] Ingress protection (Spill test)

---

## 7. Plan of Action

1.  **Pre-Compliance Testing (Internal):**
    - Perform thermal profiling
    - Perform Hi-Pot and Earth continuity tests
    - Check conducted emissions with spectrum analyzer
2.  **Component Verification:**
    - Audit BOM for safety-critical component certifications.
3.  **Documentation:**
    - Draft User Manual based on requirements above.
    - Create Label artwork.
4.  **Third-Party Lab:**
    - Quote for full CE/UL certification.
    - Schedule preliminary EMC scan.

---
