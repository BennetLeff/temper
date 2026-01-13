# Phase 6: Provable Placement via Geometric Legalization

## Philosophy: "Legal by Construction"
The current placement has physical collisions (`D1` vs `U_GATE`), rendering routing impossible. The Router assumes disjoint components. We must guarantee this property using **Computational Geometry**.

We move from "Penalty-based" placement (where overlaps are minimized) to **Constraint-based** placement (where overlaps are forbidden).

---

## Experiments

### Experiment P1: Courtyard Collision Audit
**Goal**: Mathematically prove the input placement is invalid.
**Method**:
1. Extract component `courtyard` layers (or bounding box of pads + 0.5mm clearance).
2. Compute pairwise intersection of all courtyards.
3. **Metric**: Total Overlap Area ($mm^2$).
4. **Target**: 0.0 $mm^2$.

### Experiment P2: Physics-Based Legalization (The "Shove")
**Goal**: Minimal displacement to resolve collisions.
**Method**:
- **Forces**:
  - **Repulsion**: Between overlapping courtyards (proportional to overlap depth).
  - **Attraction**: Between connected pins (spring force, weak).
  - **Anchor**: Lock critical connectors (USB, AC In) with infinite mass.
- **Solver**: Velocity-Verlet integration with damping.
- **Constraint**: Stop when Total Overlap = 0.

### Experiment P3: VLSI Legalization (Abacus/Tetris)
**Goal**: Global optimality for row-based or region-based placement.
**Method**:
- Use standard ASIC placement algorithms (e.g., **Abacus**) adapted for PCB.
- Align components to a coarse grid while preserving relative order from the "Global Placer" (Spectral/Force).
- **Benefit**: Guarantees zero overlap and aligned rows (better for routing channels).

---

## Implementation Roadmap

### 1. `PlacementAuditor` (`temper_placer.placement.audit`)
- Input: `ParsedPCB`.
- Output: List of colliding pairs + visualization.

### 2. `Legalizer` (`temper_placer.placement.legalization`)
- Input: `ParsedPCB`.
- Action: Modifies `component.initial_position`.
- Output: `ParsedPCB` (Valid).

### 3. Pipeline Integration
- Insert `Legalizer` at **Stage 0.5** (Post-Load, Pre-Route).

## Success Metrics
1. **Placement DRC**: 0 Courtyard Violations.
2. **Routing Success**: Shorts count $\to$ 0 (since pads are separated).
