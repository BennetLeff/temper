# Grounding & EMI Design Strategy

**Project:** Temper Induction Cooker  
**Standard:** EN 55014-1 (Household Appliances)  
**Status:** MANDATORY for PCB Layout  
**Date:** 2025-12-17

---

## 1. Grounding Architecture

To prevent noise coupling between high-power switching and sensitive control logic, a **Split-Plane Grounding Strategy** is used.

### 1.1 Power Ground (PGND)
- **Domain:** DC Bus, IGBTs, Resonant Tank.
- **Implementation:** Large copper pours on Top and Bottom layers.
- **Connection:** Single-point connection to Control Ground at the negative terminal of the DC bus bulk capacitors.

### 1.2 Control Ground (CGND)
- **Domain:** ESP32, ADC, RTD interface, PWM logic.
- **Implementation:** Solid internal ground plane (Layer 2) dedicated to CGND.
- **Requirement:** No high-current return paths may flow through the CGND plane.

---

## 2. Conducted Emissions (150 kHz - 30 MHz)

### 2.1 Mains EMI Filter
- **Location:** Immediately adjacent to the AC Inlet.
- **Components:** Common-mode choke (L_EMI), X2 capacitors (across L-N), Y2 capacitors (L/N to PE).
- **Layout:** Route filter components in a tight group. Maintain 8mm clearance from filtered AC to noisy DC bus.

### 2.2 High-Frequency Bypassing
- Every power IC (LMR51430, XC6220, MAX31865) must have a **100nF X7R** capacitor placed within 2mm of the VCC/GND pins.
- Use via-in-pad or adjacent vias directly to the CGND plane to minimize inductance.

---

## 3. Radiated Emissions (30 MHz - 1 GHz)

### 3.1 Switching Loop Minimization
- **Half-Bridge Loop:** The loop formed by C_BUS -> Q1 -> Q2 -> C_BUS must be minimized to < 500 mm².
- **Gate Drive Loops:** Gate and Emitter traces for each IGBT must be routed as differential pairs (parallel traces) to minimize loop area.

### 3.2 PCB Edge Treatment
- No high-speed signal traces or noisy power traces within 3mm of the PCB edge.
- Implement a **GND Stitching Ring** around the board perimeter (vias every 5mm) to create a Faraday cage effect.

---

## 4. Specific Component Placement Rules

| Component | Rule | Rationale |
|-----------|------|-----------|
| **CST-1005 CT** | Keep ≥20mm from IGBTs | Prevent magnetic field coupling into sense winding. |
| **ESP32-S3** | Keep antenna clear of copper | Maintain WiFi performance. |
| **MAX31865** | Place near RTD header | Minimize analog trace length to reduce noise pickup. |
| **UCC21550** | Straddle the CGND/PGND split | Maintain 8mm isolation barrier. |

---

## 5. Software Mitigations (Firmware)

- **Frequency Jitter:** Implement ±500Hz dither on the 38kHz carrier to spread emission peaks.
- **Slew Rate Control:** (If supported by driver) Use gate resistors to slow down IGBT turn-on to ~50ns.

---
