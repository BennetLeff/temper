# Routing Strategy Report for temper_optimized.kicad_pcb

This report provides explicit instructions for routing the Temper PCB based on the current optimized placement.

## 1. Net Class Specifications
| Net Class | Trace Width | Min Clearance | Layer Preference |
| :--- | :--- | :--- | :--- |
| **HighVoltage** | 2.0 mm | 10.0 mm | Top (2oz Copper) |
| **Power** | 1.0 mm | 0.5 mm | Any |
| **Signal** | 0.25 mm | 0.25 mm | Bottom |

## 2. High Voltage & Power Section (HV_ZONE)
The HV section contains the voltage doubler and the half-bridge. Use thick traces and respect creepage.

**Key Instructions:**
- **DC_BUS+ / DC_BUS-**: Route with 2.0mm minimum width. Keep these paths as short as possible between C_BUS1, C_BUS2, and the IGBTs (Q1, Q2).
- **SW_NODE**: This is the most electrically noisy net. Keep its area minimal. Connect Q1-Emitter, Q2-Collector, and J_COIL using a wide copper pour if possible.
- **Isolation Barrier**: Maintain a clear 10mm gap between any HighVoltage net and the Signal nets in MCU_ZONE. Do not cross the barrier with any copper except for the isolated gate driver signals.

## 3. Critical Gate Drive Loops
Minimizing the area of these loops is critical for EMI and switching stability.

### Loop: gate_drive_high
**Description:** High-side gate drive loop - critical for switching noise
**Target Area:** < 100 mm²
**Nets to keep together:** GATE_H, SW_NODE, VCC_15V, GND_ISO
**Instruction:** Route the GATE and Return (GND_ISO/SW_NODE) traces as a differential pair or stacked on Top/Bottom layers to cancel inductance.

### Loop: gate_drive_low
**Description:** Low-side gate drive loop
**Target Area:** < 100 mm²
**Nets to keep together:** GATE_L, GND_POWER, VCC_15V
**Instruction:** Route the GATE and Return (GND_ISO/SW_NODE) traces as a differential pair or stacked on Top/Bottom layers to cancel inductance.

### Loop: power_commutation
**Description:** Main power commutation loop
**Target Area:** < 500 mm²
**Nets to keep together:** DC_BUS+, SW_NODE, DC_BUS-
**Instruction:** Route the GATE and Return (GND_ISO/SW_NODE) traces as a differential pair or stacked on Top/Bottom layers to cancel inductance.

### Loop: bootstrap_charge
**Description:** Bootstrap capacitor charging loop
**Target Area:** < 150 mm²
**Nets to keep together:** VCC_BOOT, SW_NODE, VCC_15V
**Instruction:** Route the GATE and Return (GND_ISO/SW_NODE) traces as a differential pair or stacked on Top/Bottom layers to cancel inductance.

## 4. Grounding & Split Planes
This design uses a split ground strategy (PGND and CGND).

- **PGND (Power Ground)**: Keep localized to the HV_ZONE. Use a solid copper plane on the bottom layer if possible.
- **CGND (Control Ground)**: Use a solid copper plane in the LV_ZONE and MCU_ZONE.
- **Star Point**: Connect PGND and CGND at EXACTLY one point: (50, 40). Use a 0-ohm resistor or a narrow bridge.
- **GND_ISO**: This is the floating ground for the high-side gate driver. It must be isolated from all other grounds. Route it locally around U_GATE and Q1.

## 5. Explicit Point-to-Point Instructions
Follow these paths strictly:
- **High-Side Gate**: Route U_GATE (at (26.89713478088379, 101.02508544921875)) to Q1 (at (13.771469116210938, 136.8843994140625)). Use a 0.5mm trace. Keep the return path (SW_NODE) directly underneath on the Bottom layer.
- **Low-Side Gate**: Route U_GATE (at (26.89713478088379, 101.02508544921875)) to Q2 (at (29.161699295043945, 130.919189453125)). Use a 0.5mm trace. Keep the return path (PGND) directly underneath.

## 6. Finishing and Optimization
- **Vias**: Minimize vias on HighVoltage and Power paths. Each via adds inductance and resistance.
- **Teardrops**: Use teardrops on all pad-to-trace connections to improve mechanical reliability.
- **Thermal Relief**: Use thermal relief for all pads connected to large copper planes to facilitate soldering.