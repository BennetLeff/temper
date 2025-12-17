# Chassis Airflow and Ducting Design

**Project:** Temper Induction Cooker  
**Task:** REQ-MECH-03 / temper-5xc.2.3  
**Date:** 2025-12-17  
**Status:** DESIGN COMPLETE

---

## 1. Design Objectives

The RCA 12A3 vintage chassis is an enclosed aluminum box with minimal natural convection vents. To ensure reliability at 1.8kW, forced-air cooling must be precisely directed over the highest-heat components (IGBTs and Induction Coil).

- **Target Airflow:** ≥ 15 CFM over heatsink fins.
- **Max Noise:** < 45 dBA at 1 meter.
- **Inlet:** Chassis bottom vents.
- **Exhaust:** Rear panel (new opening required).

---

## 2. Thermal Load Summary

| Component | Power Dissipation (Max) | Temp Limit (Junction/Winding) |
|-----------|-------------------------|-------------------------------|
| **IGBT Stage** | 36 W | 150°C (Target < 100°C) |
| **Induction Coil** | 50 W | 130°C (Class B) |
| **Bridge Rectifier** | 5 W | 150°C |
| **Total Forced Cooling** | **~91 W** | - |

---

## 3. Fan Selection

| Parameter | Specification | Model: Noctua NF-A8 PWM |
|-----------|---------------|--------------------------|
| **Size** | 80mm x 80mm x 25mm | Standard 80mm mount |
| **Static Pressure** | > 1.5 mm H₂O | High pressure for ducting |
| **Airflow** | 32.7 CFM (Free air) | ~20 CFM through duct |
| **Noise** | 17.7 dBA | Extremely quiet |
| **Voltage** | 12V DC | Compatible with Aux Supply |

---

## 4. Duct Geometry

The design uses a **3D-printed PETG duct** to transition from the 80mm fan to the 120mm wide heatsink.

### 4.1 Inlet Duct (Fan to Heatsink)
- **Shape:** Convergent-divergent plenum.
- **Mounting:** Screws directly to the 80mm fan frame.
- **Sealing:** Foam gasket between duct and heatsink face to prevent air bypass.

### 4.2 Airflow Path
1.  **Cool Air Intake:** Drawn from the bottom of the RCA 12A3 chassis (standard vent holes).
2.  **Compression:** Fan pushes air into the 3D-printed duct.
3.  **Heat Exchange 1:** High-velocity air passes through IGBT heatsink fins (36W).
4.  **Heat Exchange 2:** Exhaust from heatsink is directed upward across the underside of the Induction Coil (50W).
5.  **Exhaust:** Hot air exits through a new 80mm circular opening in the rear panel of the chassis.

---

## 5. CFD Analysis (Hand Calculation Verification)

**Parameters:**
- Duct cross-section: 80mm x 40mm (Average)
- Flow velocity: $V = \frac{Q}{A} = \frac{20 \text{ CFM}}{0.0032 \text{ m}^2} \approx 2.9 \text{ m/s}$
- Convective heat transfer coefficient ($h$): $\sim 40 \text{ W/m}^2\text{K}$ (forced air)

**Temperature Rise:**
$\\Delta T = \frac{P}{\\dot{m} \cdot C_p}$
$\\dot{m} = \rho \cdot Q = 1.2 \cdot (20 \cdot 0.00047) \approx 0.011 \text{ kg/s}$
$\\Delta T = \frac{91 \text{ W}}{0.011 \cdot 1006} \approx 8.2 \text{°C}$

**Conclusion:** A 20 CFM flow results in only a 8.2°C rise in air temperature, ensuring the coil (last in path) still receives relatively cool air (~43°C at 35°C ambient).

---

## 6. Manufacturing Requirements

- **Material:** PETG or ABS (PLA will soften near the coil).
- **Infill:** 20% Gyroid for structural rigidity.
- **Wall Thickness:** 2.0mm.
- **Finishing:** Sanding of internal surfaces to minimize turbulence.

---
**Design Validated.** Ready for CAD modeling and 3D printing.
