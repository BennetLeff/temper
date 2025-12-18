# Critical Switching Loop Identification & Minimization

**Project:** Temper Induction Cooker  
**Standard:** EN 55014-1 (Radiated EMI)  
**Status:** MANDATORY for PCB Layout  
**Date:** 2025-12-17

---

## 1. Overview

Radiated EMI is primarily caused by large current loops ($dI/dt$) and high-voltage nodes ($dV/dt$). This document identifies the 3 most critical loops in the Temper design and provides specific layout constraints.

---

## 2. Loop #1: Half-Bridge Power Loop (Highest dI/dt)

- **Path:** DC Bus Capacitors ($C_{BUS}$) → High-Side IGBT ($Q_1$) → Low-Side IGBT ($Q_2$) → Ground Return.
- **Signal:** 38 kHz Square Wave, 50A Peak.
- **EMI Impact:** Magnetic field radiation ($H$-field).
- **Target Area:** **< 500 mm²**
- **Layout Strategy:**
    - Place $C_{BUS}$ bulk capacitors as close as possible to the TO-247 IGBTs.
    - Use wide copper pours (not traces) for the DC+ and GND rails.
    - Overlay the DC+ and GND pours on adjacent layers (Top/Layer 2) to benefit from flux cancellation.

---

## 3. Loop #2: Gate Drive Loops (High dV/dt)

- **Path:** Gate Driver ($U_{GD}$) → Gate Resistor ($R_G$) → IGBT Gate/Emitter ($Q_{G/E}$) → Return.
- **Signal:** 15V Logic, 50V/ns transition.
- **EMI Impact:** Electric field coupling ($E$-field) and ringing.
- **Target Area:** **< 100 mm²**
- **Layout Strategy:**
    - Route Gate and Emitter (Return) traces as a close-coupled differential pair (6 mil spacing).
    - Minimize the distance between $U_{GD}$ and the IGBTs (< 20mm).
    - Avoid vias in the gate drive path if possible.

---

## 4. Loop #3: Buck Converter Loop (High Frequency)

- **Path:** Input Cap ($C_{IN}$) → Buck Switch ($U_{BUCK}$) → Inductor ($L_{BUCK}$) → Output Cap ($C_{OUT}$).
- **Signal:** 600 kHz switching.
- **EMI Impact:** High-frequency radiated noise.
- **Target Area:** **< 200 mm²**
- **Layout Strategy:**
    - Follow "Power Loop First" rule: Place $C_{IN}$, $U_{BUCK}$, and $D_{FREEWHEEL}$ in a tight cluster before routing the inductor.
    - Use a single solid ground plane directly under the buck stage.

---

## 5. Summary Table for PCB Placer

| Loop | Components | Constraint | Priority |
|------|------------|------------|----------|
| **Power** | C_BUS, Q1, Q2 | Dist < 30mm | P0 |
| **Gate HS** | U_GD, Q1 | Dist < 20mm | P0 |
| **Gate LS** | U_GD, Q2 | Dist < 20mm | P0 |
| **Buck** | C_IN, U_BUCK, L_BUCK | Dist < 15mm | P1 |

---
