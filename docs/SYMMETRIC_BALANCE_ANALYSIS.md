# Analysis: Symmetric Balance in Power Electronics

## 1. Introduction
In high-power switching systems like half-bridge induction cookers, symmetric balance in the physical layout is critical for ensuring equal stress on switching devices and minimizing electromagnetic interference (EMI).

## 2. Importance of Symmetry

### 2.1 Thermal Balance
Uneven layout can lead to one IGBT carrying more current or having poorer heat dissipation, resulting in thermal runaway. Symmetric placement ensures:
- Equal path lengths to the heatsink.
- Equal airflow distribution.
- Balanced power dissipation.

### 2.2 Parasitic Inductance Matching
Difference in trace lengths between the high-side and low-side switching paths causes mismatched parasitic inductances. This leads to:
- Uneven voltage spikes during turn-off ($V = L \cdot di/dt$).
- Different switching speeds, causing timing jitter.
- Common-mode noise injection.

### 2.3 EMI Cancellation
Symmetric current loops (where current flows in opposite directions in adjacent identical circuits) can lead to partial cancellation of magnetic fields, reducing radiated emissions.

## 3. Implementation in Temper Placer

The Temper Placer handles symmetric balance through two primary mechanisms:

### 3.1 MirrorSymmetryLoss
Enforces that components in paired circuits (e.g., Phase A and Phase B, or High-side and Low-side drivers) are placed as mirror images across a central axis.
- **Differentiable**: The loss is the squared distance between the actual position and the ideal mirrored position.
- **Configurable**: Axis and center line can be specified in PCL.

### 3.2 Isomorphic Pair Detection
The placer automatically identifies topologically identical subcircuits (isomorphic subgraphs) and applies symmetry constraints.
- Uses **Weisfeiler-Lehman hashing** to detect identical connectivity patterns.
- Clusters identical "channels" and encourages them to share the same local layout.

## 4. Design Guidelines for Temper
1.  **Gate Drivers**: Place high-side and low-side drivers at equal distances from the IGBT gates.
2.  **DC Link**: Ensure the path from the bus capacitors to both high-side and low-side switches is symmetric.
3.  **Resonant Tank**: Align parallel resonant capacitors to ensure equal current sharing.

## 5. Verification
Symmetry is verified in the **Aesthetic Scoring** module, which calculates the **Symmetry Error (mm)** for all defined pairs. A pass requires $<0.5mm$ deviation from perfect symmetry.
