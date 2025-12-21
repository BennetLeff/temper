# Analysis: Via Count Reduction Study

## 1. Executive Summary
This study analyzes the impact of via count on the reliability, manufacturing cost, and electrical performance of the Temper induction cooker PCB. It identifies strategies for minimizing via usage in high-power and high-speed signal paths.

## 2. The Case for Via Reduction

### 2.1 Reliability
Vias are common failure points in PCBs due to:
- **Thermal Stress**: Differential expansion between the copper barrel and the substrate (CTE mismatch).
- **Manufacturing Defects**: Acid traps, plating voids, and drill registration errors.
- **Current Bottlenecks**: High-current vias can overheat if not properly sized or redundant.

### 2.2 Electrical Performance
- **Inductance**: Each via adds parasitic inductance (~1-2nH), which is detrimental to fast-switching gate drive signals and power loops.
- **Signal Integrity**: Vias create impedance discontinuities in high-speed traces (e.g., SPI bus).
- **Return Path Discontinuity**: Transitioning layers without nearby stitching vias can force return currents to take long, inductive paths.

## 3. Current Via Baseline (Temper-Alpha)
- **Signal Vias**: ~150 (primarily for routing crossovers).
- **Power Vias**: ~200 (redundant arrays for high-current and thermal dissipation).
- **Total**: ~350 vias.

## 4. Reduction Strategies

### 4.1 Topology-Aware Placement
By using the **Topological Phase** in the placer, we can ensure that components on the same net are clustered such that they can be routed primarily on a single layer.
- **Success Metric**: Reduction in signal vias by ~30% through improved net crossing analysis.

### 4.2 Single-Sided High Current Paths
Restricting the resonant tank and main power loop to the bottom layer (thickest copper) eliminates the need for high-current via arrays between layers.
- **Impact**: Removes ~80 power vias.

### 4.3 Redundant Via Optimization
Instead of a generic 10-via array for every high-current transition, use **Current-Density Modeling** to determine the minimum number of vias required for 15A with a 20°C temperature rise.
- **Rule**: 1 via (0.3mm drill) per 1.5A continuous current.

## 5. Cost Impact
Reducing via count from 350 to <250 reduces:
- **Drill Time**: Faster manufacturing.
- **Tool Wear**: Lower cost for small-batch production.
- **Yield**: Higher reliability at assembly.

## 6. Recommendations
1.  Enforce a "Bottom-Layer First" policy for high-power routing.
2.  Add a `ViaCountPenalty` to the routing verification phase.
3.  Use large thermal pads instead of small via arrays where possible for heat transfer to external sinks.
