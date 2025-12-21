# Component Value Audit - Simulation vs Design

This document tracks the consistency between simulation testbenches (`simulation/testbenches/*.cir`), atopile definitions (`elec/src/modules.ato`), and KiCad schematics (`pcb/*.kicad_sch`).

## Summary Table

| Component | Design Value (ato/pcb) | Simulation Value | Status | Affected Files |
|-----------|------------------------|------------------|--------|----------------|
| CT Burden Resistor | 66.5 Ω | 50 Ω | ❌ MISMATCH | `sim_17a`, `sim_17b` |
| CT Filter Capacitor | 100 nF | 1.6 nF | ❌ MISMATCH | `sim_34` |
| OCP Ref Supply | 3.3 V | 5.0 V | ❌ MISMATCH | `sim_17` |
| OCP Ref Divider | 3.2k / 10k | 10k / 10k | ❌ MISMATCH | `sim_17` |
| Gate Resistor (Strong) | 2.2 Ω | 5.0 Ω | ❌ MISMATCH | `sim_03` |
| Dead-time Capacitor | 5.1 nF | 100p - 1000p | ❌ MISMATCH | `sim_05` |
| Resonant Tank Caps | 2x 150 nF (300n) | 300 nF | ✅ MATCH | `sim_24` |
| RTD Ref Resistor | 430 Ω | - | ✅ MATCH | `modules.ato` |

## Detailed Findings

### 1. Current Transformer Path
- **Burden Resistor**: The design uses **66.5Ω** to achieve 3.325V peak at 50A (1:1000 ratio). Simulation files `sim_17a` and `sim_17b` use a legacy value of **50Ω**.
- **Filter**: `sim_34` uses a 1.6nF filter cap which gives ~100kHz bandwidth. `modules.ato` specifies 100nF, which would result in a much lower (~1.6kHz) bandwidth, likely intended for average current sensing rather than peak detection.

### 2. OCP Logic
- **Supply & Divider**: Hardware uses the 3.3V rail and a 3.2k/10k divider to set a **2.5V** threshold. `sim_17` uses 5V and 10k/10k. While both result in a 2.5V threshold, the component values and supply rails should be updated for accuracy.

### 3. Gate Drive
- **Gate Resistor**: `sim_03` uses 5Ω. The `HalfBridge` module in `modules.ato` uses **2.2Ω** (`rg_on`) to maximize switching speed.
- **Dead-time**: Hardware uses **5.1nF**. Simulation `sim_05` sweeps up to 1nF. The 5.1nF value in the design might be an error or requires specific software dead-time support (as noted in `modules.ato`).

## Recommended Actions
1. Update `R_burden` to 66.5Ω in all CT simulation files.
2. Update OCP simulation to use 3.3V supply and 3.2k/10k divider.
3. Align gate resistor values in `sim_03`.
4. Re-verify dead-time capacitor value requirement and update `sim_05`.
