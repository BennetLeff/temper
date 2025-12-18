# PCB Manufacturing & DFM Guidelines

**Project:** Temper Induction Cooker  
**Target Process:** prototype PCBA (e.g., JLCPCB, PCBWay)  
**Status:** MANDATORY for PCB Layout  
**Date:** 2025-12-17

---

## 1. Component Spacing & Orientation

To ensure high-yield automated assembly, the following rules must be followed:

### 1.1 SMT Spacing
- **General Min Spacing:** 0.5 mm between component bodies.
- **Passives (0603/0805):** 0.3 mm minimum between pads of adjacent components.
- **Power Path:** 2.0 mm clearance around TO-247 IGBTs to allow for hand-soldering and heatsink mounting.

### 1.2 Component Orientation
- **Polarized Components:** All diodes, electrolytic capacitors, and ICs should be oriented in the same direction (e.g., Pin 1 always Top or Left) where possible.
- **Shadowing:** Avoid placing small components (0603) immediately adjacent to tall components (Electrolytic caps, Relay) to prevent solder shadowing.

---

## 2. Fiducial Mark Strategy

Fiducials are required for pick-and-place machine alignment.

### 2.1 Global Fiducials
- **Quantity:** 3 marks, placed in a non-symmetrical L-pattern near board corners.
- **Location:** At least 5mm from the PCB edge.
- **Design:**
    - **Copper Diameter:** 1.0 mm (Circular).
    - **Solder Mask Opening:** 3.0 mm (Circular).
    - **Keepout:** No copper or silkscreen within the 3.0mm mask opening.

### 2.2 Local Fiducials
- **Required For:** ESP32-S3 module and any fine-pitch ICs (< 0.5mm pitch).
- **Placement:** Two fiducials at diagonal corners of the component footprint.

---

## 3. Test Point Accessibility

To facilitate debugging and factory testing (ICT), test points must be provided for all critical nets.

### 3.1 Design Rules
- **Type:** Surface mount test pad (Gold-plated preferred).
- **Diameter:** 1.0 mm.
- **Spacing:** 2.54 mm (100 mil) center-to-center minimum.
- **Location:** Grouped together on the Bottom layer (B.Cu) where possible.

### 3.2 Required Test Points
| Signal | Net Name | Purpose |
|--------|----------|---------|
| **Power** | +170V, +15V, +5V, +3V3 | Rail verification |
| **Ground** | PGND, CGND | Reference check |
| **Logic** | PWM_H, PWM_L | Gate drive timing |
| **Analog** | I_SENSE, V_BUS | Sensing calibration |
| **Prog** | UART_TX, UART_RX | Firmware update |

---

## 4. THT (Through-Hole) Requirements

The Temper board uses several high-power THT components.

- **Hole Sizing:** Lead Diameter + 0.3 mm minimum for easy insertion.
- **Annular Ring:** 0.5 mm minimum for high-current paths (IGBTs, Connectors).
- **Thermal Relief:** Use 4-spoke thermal reliefs for all THT connections to ground planes to prevent cold solder joints.

---

## 5. Manufacturing Checklist

- [ ] Minimum 3 global fiducials present.
- [ ] No silkscreen on pads or fiducials.
- [ ] 1.0mm test points present for all primary power rails.
- [ ] All polarized components follow consistent orientation.
- [ ] Tooling holes (3.2mm) present in 4 corners for assembly jigs.

---
