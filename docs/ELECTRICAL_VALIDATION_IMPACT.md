# Electrical Validation: Impact on PCB Quality

This document explains how the **Level 3 (Electrical Validity)** infrastructure in `temper-placer` produces functionally superior PCBs compared to pure geometric optimization.

## 1. Thermal Safety: Beyond "Fits on Board"

### The Problem
Pure geometric optimizers often minimize total wirelength by clustering components. In power electronics, this creates "Thermal Hotspots." Placing two 50W IGBTs side-by-side might be geometrically optimal but causes catastrophic thermal runaway because their heat plumes overlap.

### The Solution: Calibrated $R_{\theta}$ Network
We replaced simple distance heuristics with a calibrated **Thermal Resistance Network** ($R_{\theta JC} + R_{\theta CH} + R_{\theta HA}$):
*   **Physics Grounding**: Uses actual datasheet values (e.g., 0.6 K/W for IKW40N120H3).
*   **Mounting Sensitivity**: Models the increase in thermal resistance ($R_{\theta HA}$) as components move away from board edges (0.2 K/W per mm).
*   **Result**: The placer now "understands" the cooling capacity of the board. If $T_j > 150^° C$, the orchestrator automatically triggers refinement to push heat-sources toward edges or further apart.

## 2. Switching Stability: The "Miller Killer"

### The Problem
In high-speed switching (25kHz half-bridge), parasitic gate inductance ($L_g$) is the primary cause of failure. High $L_g$ causes gate voltage ringing. If the ringing exceeds the threshold voltage during the off-state, the IGBT turns on unexpectedly (Miller Turn-On), causing a dead-short across the 340V DC bus.

### The Solution: PEEC Inductance Model
The placer now calculates parasitic inductance in real-time using a **Partial Element Equivalent Circuit (PEEC)** approximation (~0.8 nH/mm):
*   **Geometric Awareness**: It treats the 3D loop formed by the Driver, Gate, and Emitter as a physical object.
*   **Constraint Enforcement**: It sets a hard target of ≤10 nH. This forces the gate driver to be placed directly adjacent to the IGBT, regardless of other wirelength objectives.
*   **Result**: Reliable switching at high power without shoot-through risks.

## 3. Pre-Fabrication Confidence: The Virtual Oscilloscope

### The Problem
Traditionally, a designer discovers switching instability *after* receiving the PCB from the factory and probing it with an oscilloscope. If it rings, the board is scrapped.

### The Solution: Automated SPICE Loop
We integrated `ngspice` directly into the refinement callback:
*   **Transient Analysis**: Every 100 epochs, the system generates a SPICE netlist using the placement's extracted parasitics.
*   **Overshoot Detection**: It measures peak $V_{ge}$ and calculates overshoot %.
*   **Result**: You get a "Virtual Oscilloscope" reading of your gate drive signal before you ever send the files to the fab. If overshoot > 20%, the placement is flagged as electrically invalid.

## Summary: Pictures vs. Systems

| Feature | Level 2 (Geometric) | Level 3 (Electrical) |
| :--- | :--- | :--- |
| **Logic** | "Do the parts fit?" | "Will the circuit work?" |
| **Primary Metric** | Overlap Area (mm²) | Junction Temp (°C) & Inductance (nH) |
| **Failure Mode** | Mechanical collision | Thermal runaway / Shoot-through |
| **PCB Outcome** | A pretty picture of a layout | A proven, safe power system |
