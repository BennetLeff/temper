# Benders Decomposition for Routability-Aware Placement

## Overview

This document describes a mathematically rigorous approach to achieving **provably routable placements** using Benders decomposition. The key insight is separating the problem into two cooperating solvers:

1. **Master Problem (ILP):** Handles physics constraints (non-overlap, clearances, board bounds)
2. **Subproblem (Max-Flow):** Verifies routability and generates feedback

## Problem Statement

**Given:**
- PCB with components at initial positions
- Net list requiring routing
- Design rules (clearances, trace widths, HV isolation)
- Board dimensions

**Find:**
- Component placement that is:
  1. Physically valid (no overlaps, clearances satisfied)
  2. Provably routable (Max-Flow ≥ net demand)
  3. Minimal movement from initial placement

**Current State (Temper Board):**
- 11 nets failed to route
- Max-Flow analysis: 8/11 capacity (3-net deficit)
- Bottleneck: "3D Wall" at X~50mm, Y~75mm
- Root cause: HV inflation zones + component density

## Mathematical Framework

### Why Not Direct Optimization?

The naive approach:
```
maximize: min_cut_capacity(placement)
subject to: physics_constraints(placement)
```

Fails because `min_cut_capacity()` is:
- **Non-linear:** Capacity depends on gaps between obstacles
- **Non-convex:** Small movements can open/close channels discontinuously
- **Expensive:** Requires running Max-Flow algorithm

### Benders Decomposition

Split into cooperating solvers:

```
┌─────────────────────────────────────────────────────────────┐
│  MASTER PROBLEM (ILP)                                       │
│  Variables: Component positions (x_i, y_i)                  │
│  Constraints: Non-overlap, clearances, bounds, cuts         │
│  Objective: Minimize total movement                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ candidate placement
┌─────────────────────────────────────────────────────────────┐
│  SUBPROBLEM (Max-Flow)                                      │
│  Input: Placement from master                               │
│  Output: FEASIBLE or (INFEASIBLE + min-cut)                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ if infeasible
┌─────────────────────────────────────────────────────────────┐
│  CUT GENERATOR                                              │
│  Input: Min-cut bottleneck + blocking components            │
│  Output: Linear constraint that opens bottleneck            │
│  Action: Add to master, re-solve                            │
└─────────────────────────────────────────────────────────────┘
```

## Master Problem Formulation

### Variables

```python
# Component positions (continuous)
x_i: float  # X position of component i
y_i: float  # Y position of component i

# Movement from initial (for objective)
δx_i = |x_i - x_i⁰|
δy_i = |y_i - y_i⁰|

# Binary variables for disjunctive constraints
b_ij_left, b_ij_right, b_ij_above, b_ij_below: {0, 1}
```

### Constraints

#### 1. Non-Overlap (Disjunctive)

For each component pair (i, j), at least one separation must hold:

```
x_i + w_i ≤ x_j + M(1 - b_ij_left)    # i left of j
x_j + w_j ≤ x_i + M(1 - b_ij_right)   # j left of i
y_i + h_i ≤ y_j + M(1 - b_ij_below)   # i below j
y_j + h_j ≤ y_i + M(1 - b_ij_above)   # j below i

b_ij_left + b_ij_right + b_ij_below + b_ij_above ≥ 1
```

Where M is a large constant (e.g., board diagonal).

#### 2. HV Clearance (6mm for AC Mains)

For each HV component h and LV component l:

```
# L1-norm approximation of Euclidean distance
d_x ≥ x_h - x_l
d_x ≥ x_l - x_h
d_y ≥ y_h - y_l
d_y ≥ y_l - y_h
d_x + d_y ≥ clearance × √2  # 6mm × 1.414 ≈ 8.5mm
```

#### 3. Board Bounds

```
0 ≤ x_i ≤ board_width - w_i
0 ≤ y_i ≤ board_height - h_i
```

#### 4. Fixed Components

```
x_connector = x_connector⁰
y_connector = y_connector⁰
```

#### 5. Routability Cuts (Added Iteratively)

When Max-Flow identifies bottleneck between components A and B:

```
# Horizontal channel bottleneck
x_B - x_A ≥ w_A + required_channel_width

# Vertical channel bottleneck
y_top - y_bottom ≥ h_bottom + required_channel_width
```

### Objective

```
minimize: Σ_i (δx_i + δy_i)  # Total L1 movement
```

## Algorithm

```
BENDERS_PLACEMENT_OPTIMIZATION:

Input:
  - Initial placement P⁰
  - Component dimensions {w_i, h_i}
  - Clearance rules (HV: 6mm, signal: 0.3mm)
  - Net list with terminals
  - Board dimensions

Output:
  - Feasible placement P* or INFEASIBLE proof

Algorithm:
  1. Initialize Master ILP with physics constraints
  2. routability_cuts = ∅

  3. LOOP:
     a. Solve Master ILP → candidate P

     b. IF ILP infeasible:
        RETURN "Physics constraints unsatisfiable"

     c. Build occupancy grids from P
     d. Run 3D Max-Flow analysis

     e. IF max_flow ≥ net_demand:
        RETURN P  # Success!

     f. ELSE:
        - Extract min-cut edges
        - For each min-cut edge (u, v):
            - Identify blocking components
            - Generate linear cut constraint
            - Add to routability_cuts
        - Update Master ILP
        - GOTO 3
```

## Convergence Properties

**Theorem:** The algorithm terminates in finite iterations.

**Proof sketch:**
1. Each iteration adds at least one cut
2. Each cut eliminates at least one infeasible placement configuration
3. The set of placement configurations is finite (bounded positions)
4. Therefore, algorithm terminates

**Complexity:**
- Worst case: O(C²) iterations where C = number of components
- Typical: 5-20 iterations for practical boards

## Implementation Requirements

### Phase 1: Data Collection

| Requirement | Source | Status |
|-------------|--------|--------|
| Component list with dimensions | KiCad parser | ✅ Available |
| Initial positions | Current placement | ✅ Available |
| Fixed component list | Manual specification | ⚠️ Need to define |
| HV component classification | Net class assignments | ✅ Available |
| Board dimensions | KiCad board outline | ✅ Available |
| Net terminal positions | KiCad parser | ✅ Available |

### Phase 2: Master Problem (ILP)

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| ILP solver | OR-Tools / PuLP | ❌ Not started |
| Non-overlap constraints | Big-M formulation | ❌ Not started |
| HV clearance constraints | L1-norm linearization | ❌ Not started |
| Board bounds | Linear inequalities | ❌ Not started |
| Cut constraint interface | Dynamic constraint addition | ❌ Not started |

### Phase 3: Subproblem (Max-Flow)

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Max-Flow analyzer | MaxFlowAnalyzer class | ✅ Implemented |
| 3D flow network | Multi-layer graph | ✅ Implemented |
| Min-cut extraction | From Max-Flow result | ⚠️ Partial |
| Bottleneck → component mapping | Spatial query | ❌ Not started |

### Phase 4: Cut Generator

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Min-cut to constraint conversion | Geometric analysis | ❌ Not started |
| Horizontal bottleneck cuts | x_B - x_A ≥ threshold | ❌ Not started |
| Vertical bottleneck cuts | y_T - y_B ≥ threshold | ❌ Not started |
| HV inflation cuts | Distance constraints | ❌ Not started |

## Experiments

### Experiment B1: Baseline Feasibility

**Goal:** Verify current placement is infeasible

**Method:**
1. Run Max-Flow on current Temper placement
2. Document capacity deficit
3. Identify all min-cut locations

**Expected Result:** Max-Flow = 8/11 (already confirmed)

### Experiment B2: Single Bottleneck Resolution

**Goal:** Verify cut generation opens capacity

**Method:**
1. Take the primary bottleneck (50mm, 75mm)
2. Manually generate cut constraint
3. Add to ILP, solve
4. Run Max-Flow on new placement

**Success Criteria:** Max-Flow increases by ≥1

### Experiment B3: Full Benders Loop

**Goal:** Achieve provably routable placement

**Method:**
1. Run full Benders algorithm
2. Track iterations and cuts added
3. Verify final placement with Max-Flow

**Success Criteria:** Max-Flow ≥ 11, all physics constraints satisfied

### Experiment B4: Router Validation

**Goal:** Confirm router achieves 100% on feasible placement

**Method:**
1. Take feasible placement from B3
2. Run Router V6
3. Run DRC

**Success Criteria:** 100% routing completion, 0 DRC violations (excluding known exclusions)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ILP solver too slow | Low | High | Use warm starting, reduce precision |
| Too many iterations | Medium | Medium | Add multiple cuts per iteration |
| Physics infeasibility | Medium | High | Relax constraints or increase board size |
| Cut constraints too weak | Medium | Medium | Use generalized cuts |
| Numerical precision issues | Low | Low | Use 0.1mm position resolution |

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Max-Flow capacity | ≥ 11 nets | Max-Flow analyzer |
| Physics violations | 0 | ILP feasibility |
| Routing completion | 100% | Router V6 |
| DRC violations | < 10 (connector exclusions) | KiCad DRC |
| Total movement | < 20mm cumulative | ILP objective |
| Algorithm iterations | < 20 | Counter |
| Runtime | < 5 minutes | Timer |

## References

1. Benders, J.F. (1962). "Partitioning procedures for solving mixed-variables programming problems"
2. Caldwell, A.E. et al. (2000). "Can Linear Programming Help Solve Routing Problems?"
3. Spindler, P. et al. (2008). "Fast and Accurate Routing Demand Estimation for Efficient Routability-driven Placement"

## Appendix: Temper Board Specifics

### Component Categories

**Fixed (Connectors):**
- J_USB: USB-C connector (board edge)
- J_AC_IN: AC input terminal
- J_OUT: Output terminal
- Mounting holes (4x)

**HV Components (6mm clearance):**
- AC_L, AC_N, PE terminals
- DC_BUS+, DC_BUS- nodes
- D1, D2 (rectifier diodes)
- Q1, Q2 (MOSFETs)

**Anchored (From previous work):**
- U_GATE: (25.8, 30.7) - can move if needed
- C_BOOT, C_VCC: Flexible placement

**Free (Optimizable):**
- All other components

### Known Bottlenecks

| Location | Cause | Components Involved |
|----------|-------|---------------------|
| (50, 75) | HV inflation + pins | D2, AC_L zone |
| (53, 74) | Component density | U_GATE, C_BOOT |
| (18, 33) | Through-hole connector | J1 (fixed) |

### SCC Conflict Group

Nets that mutually block regardless of order:
- USB_D+
- +5V
- I_SENSE
- GATE_L
- PWM_L

These require either spatial separation or layer assignment to resolve.
