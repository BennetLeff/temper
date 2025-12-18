# PCB Silkscreen & Marking Requirements

**Project:** Temper Induction Cooker  
**Standard:** IEC 60335-1 / UL 858 Compliance  
**Status:** MANDATORY for PCB Production  
**Date:** 2025-12-17

---

## 1. Safety Markings (Mandatory)

The following markings must be clearly visible on the top-side silkscreen to prevent injury and misuse.

### 1.1 High-Voltage Warnings
- **Symbol:** IEC 60417-5036 (Lightning bolt in triangle).
- **Location:** Near AC Inlet (J_IN), DC Bus Capacitors, and IGBT Switching Stage.
- **Text:** "CAUTION: HIGH VOLTAGE - 170V DC"
- **Boundary Line:** A dotted or dashed line must clearly enclose the "Hot Zone" (Hazardous voltage area).

### 1.2 Earth Ground (PE)
- **Symbol:** IEC 60417-5019 (Ground symbol in circle).
- **Location:** Immediately adjacent to the PE screw terminal/pad.
- **Color:** Contrast with solder mask (White on Black/Green).

### 1.3 Identification
- **Project Name:** "TEMPER Induction Cooker"
- **Version:** "v1.1"
- **Regulatory Placeholder:** "Design targets CE / UL 858" (Optional for proto).

---

## 2. Terminal & Connector Labeling

All connectors must be uniquely identified to prevent incorrect assembly.

| Connector | Label | Pins/Signals |
|-----------|-------|--------------|
| AC Input | **J_IN** | L, N, PE |
| Coil Output | **J_COIL** | COIL_A, COIL_B |
| Pan Sensor | **J_RTD1** | 4-Wire RTD |
| Fan Header | **J_FAN** | +12V, GND, TACH, PWM |
| UI Header | **J_UI** | 3V3, GND, I2C, INT |
| Prog Header | **J_PROG** | UART, BOOT, EN |

---

## 3. Component Markings

1.  **Reference Designators:** All components must have a clear ref des (e.g., Q1, R12, C5).
2.  **Polarity Markers:**
    - **Diodes:** Clear cathode bar.
    - **Electrolytic Caps:** "+" or "-" indicator matching physical part.
    - **LEDs:** "+" or "K" indicator.
3.  **Pin 1 Indicators:** A dot or triangle for all ICs and multi-pin connectors.

---

## 4. Test Point Matrix

Test points must be labeled with their signal name for easier debugging.

- **TP_5V**: 5V Rail
- **TP_3V3**: 3.3V Rail
- **TP_PGND**: Power Ground
- **TP_CGND**: Control Ground
- **TP_SW**: Switch Node (Warning: High Voltage)
- **TP_FAULT**: Fault Status Line

---

## 5. Manufacturing Specifications

- **Text Height:** 1.0 mm minimum.
- **Text Width:** 0.15 mm (6 mil) minimum.
- **Layer:** F.SilkS (Top Silkscreen). B.SilkS (Bottom) used only for logos or licensing info.
- **Over-Pad Check:** No silkscreen text or lines may overlap with any component pads.

---
