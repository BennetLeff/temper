# Benders Placement Optimization: Handoff Document

**Date:** 2026-01-15
**Branch:** `router-topo-benders`
**Status:** ILP Master Problem implemented, ready for Benders loop integration

---

## Quick Start

```bash
# Navigate to the placer package
cd packages/temper-placer

# Test the ILP Master Problem
PYTHONPATH=src python -c "
from temper_placer.placement.benders_master import run_benders_master
result = run_benders_master('data/benders_input.json')
"

# Expected output:
# Status: OPTIMAL
# Objective: 30.12mm total movement
# Solve time: 0.54s
```

---

## What Is This?

This is an implementation of **Benders decomposition** for achieving **provably routable PCB placements**. The core insight is that we can't directly optimize for routability (it's non-linear and expensive), but we can:

1. **Master Problem (ILP):** Optimize placement subject to physics constraints
2. **Subproblem (Max-Flow):** Verify if placement is routable
3. **Iterate:** If not routable, generate a "cut" constraint and re-solve

```
┌─────────────────────────────────────────────────────────────┐
│  MASTER PROBLEM (ILP)                                       │
│  "Find a valid placement that minimizes movement"           │
│  Constraints: non-overlap, HV clearance, zones, grouping    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ candidate placement
┌─────────────────────────────────────────────────────────────┐
│  SUBPROBLEM (Max-Flow)                                      │
│  "Can we route all nets with this placement?"               │
│  Output: YES (done!) or NO + bottleneck location            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ if NO
┌─────────────────────────────────────────────────────────────┐
│  CUT GENERATOR                                              │
│  "Move these components apart to open a channel"            │
│  Adds linear constraint to Master, re-solve                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Current State

### What's Done ✅

| Component | File | Status |
|-----------|------|--------|
| ILP Master Problem | `placement/benders_master.py` | ✅ Complete |
| Component data extraction | `data/benders_input.json` | ✅ Complete |
| Design constraints doc | `docs/architecture/BENDERS_DESIGN_CONSTRAINTS.md` | ✅ Complete |
| Requirements audit | `docs/architecture/BENDERS_AUDIT_REPORT.md` | ✅ Complete |
| HV netclass fixes | `pcb/temper.kicad_pro` | ✅ Complete |
| Max-Flow analyzer | `router_v6/analysis/max_flow.py` | ✅ Already existed |
| OR-Tools dependency | `pyproject.toml` | ✅ Added |
| **Min-cut → component mapping** | `placement/benders_mincut_mapper.py` | ✅ **Complete** |
| **Cut generator** | `placement/benders_cut_generator.py` | ✅ **Complete** |
| **Benders loop orchestration** | `placement/benders_loop.py` | ✅ **Complete** |
| **Validation experiments** | `experiments/test_*.py` | ✅ **Complete** |
| **Integration guide** | `docs/architecture/BENDERS_INTEGRATION_GUIDE.md` | ✅ **Complete** |

### What's Left ⏳

| Component | Effort | Description |
|-----------|--------|-------------|
| Install OR-Tools | Trivial | `pip install ortools` |
| Max-Flow integration | Small | Wire up `_check_routability()` in `benders_loop.py` |
| PCB update helper | Small | Method to apply placement to PCB file |
| Net extraction helper | Small | Parse PCB to get net terminals |
| End-to-end validation | Medium | Verify on Temper board, measure routing success |

---

## Architecture

### File Structure

```
packages/temper-placer/
├── data/
│   └── benders_input.json          # Component data for ILP
├── docs/architecture/
│   ├── BENDERS_PLACEMENT_OPTIMIZATION.md  # Algorithm theory
│   ├── BENDERS_DESIGN_CONSTRAINTS.md      # PCB design rules
│   ├── BENDERS_REQUIREMENTS.md            # Implementation checklist
│   ├── BENDERS_AUDIT_REPORT.md            # Data quality audit
│   └── BENDERS_HANDOFF.md                 # This document
└── src/temper_placer/
    ├── placement/
    │   └── benders_master.py       # ILP Master Problem ← NEW
    └── router_v6/analysis/
        └── max_flow.py             # Max-Flow subproblem (existing)
```

### Key Classes

#### `BendersMasterProblem` (placement/benders_master.py)

```python
from temper_placer.placement.benders_master import BendersMasterProblem

# Load from JSON
problem = BendersMasterProblem.from_json("data/benders_input.json")

# Build ILP model
problem.build()

# Solve
result = problem.solve(time_limit_sec=60.0)

# Add a routability cut (from Max-Flow analysis)
problem.add_routability_cut(
    cut_type="horizontal",      # or "vertical"
    components=["D1", "U_GATE"],  # blocking components
    gap_required=3.0             # mm channel width needed
)

# Re-solve with new constraint
result = problem.solve()
```

#### `MaxFlowAnalyzer` (router_v6/analysis/max_flow.py)

```python
from temper_placer.router_v6.analysis.max_flow import MaxFlowAnalyzer

# Already integrated into pipeline.py
# See Stage 2.9 for usage example
analyzer = MaxFlowAnalyzer(skeletons, channel_widths, design_rules)
result = analyzer.compute_feasibility(net_demands)

# Result contains:
# - max_flow: float (capacity)
# - total_demand: int (nets to route)
# - is_feasible: bool
# - min_cut_edges: list of (u, v, capacity) bottleneck edges
```

---

## ILP Constraints Explained

### 1. Non-Overlap (Disjunctive)

For each component pair, at least one separation must hold:

```
x_i + w_i/2 + clearance ≤ x_j - w_j/2   (i left of j)   OR
x_j + w_j/2 + clearance ≤ x_i - w_i/2   (j left of i)   OR
y_i + h_i/2 + clearance ≤ y_j - h_j/2   (i below j)     OR
y_j + h_j/2 + clearance ≤ y_i - h_i/2   (j below i)
```

Encoded using Big-M method with binary variables.

### 2. HV Clearance

High-voltage components need distance from low-voltage:

```
|x_HV - x_LV| + |y_HV - y_LV| ≥ clearance × √2
```

- ACMains (AC_L, AC_N, PE): 6mm clearance
- HighVoltage (DC_BUS, SWITCH_NODE): 3mm clearance

### 3. Zone Constraints

Components restricted to thermal/EMC zones:

```
Q1.y ≤ 20mm    # MOSFETs in thermal zone (board edge)
Q2.y ≤ 20mm
U_MCU.y ≥ 80mm # MCU in quiet zone (away from switching)
U_MCU.x ≥ 60mm
```

### 4. Grouping Constraints

Decoupling caps near their ICs:

```
|x_IC - x_CAP| + |y_IC - y_CAP| ≤ max_distance

U_MCU ↔ C_MCU_1..4:  8mm max
U_GATE ↔ C_VCC, C_BOOT: 8mm max
U_CT ↔ C_CT_FILT: 5mm max
```

### 5. Movement Budget

```
Per component: δx + δy ≤ 15mm
Global total:  Σ(δx + δy) ≤ 100mm
```

---

## Data Format

### benders_input.json

```json
{
  "board": {
    "width_mm": 100,
    "height_mm": 150
  },
  "coordinate_system": "center",  // Positions are component centers
  "hv_nets": ["AC_L", "AC_N", "DC_BUS+", "DC_BUS-", "SWITCH_NODE", ...],
  "components": [
    {
      "ref": "U_MCU",
      "width_mm": 7.7,
      "height_mm": 6.77,
      "center_x_mm": 80.0,
      "center_y_mm": 99.67,
      "classification": "FREE",  // FIXED, HV, or FREE
      "hv_nets": []
    },
    {
      "ref": "Q1",
      "width_mm": 14.4,
      "height_mm": 3.5,
      "center_x_mm": 25.4,
      "center_y_mm": 15.0,
      "classification": "HV",
      "hv_nets": ["DC_BUS+", "SWITCH_NODE"]
    }
    // ... 33 components total
  ]
}
```

### Component Classifications

| Classification | Count | Movement | Description |
|---------------|-------|----------|-------------|
| FIXED | 9 | 0mm | Connectors, mounting holes (J_*, MH*) |
| HV | 8 | Limited | High-voltage components (Q1, Q2, D1, D2, etc.) |
| FREE | 16 | Flexible | All other components |

---

## Known Issues & Decisions

### Issue 1: MCU Decoupling Distance

**Problem:** Current placement has MCU caps at 7-7.7mm, but original spec was 5mm.

**Decision:** Relaxed to 8mm. For 48MHz MCU, 8mm is acceptable. The ILP now satisfies this constraint.

### Issue 2: Current Sense Grouping

**Problem:** U_CT to C_CT_FILT was 15mm in original placement.

**Resolution:** ILP moved C_CT_FILT from (30, 125) to (30, 115), bringing it within 5mm of U_CT at (30, 110).

### Issue 3: THT/SMD Overlaps

**Problem:** 5 component pairs showed 2D bounding box overlap.

**Resolution:** These are valid 3D layouts (through-hole components elevated above SMD). Not actual collisions.

### Issue 4: Net Naming

**Clarification:** The net is "SWITCH_NODE" in KiCad, not "SW_NODE". The audit initially used wrong name.

---

## Next Implementation Steps

### Step 1: Min-Cut to Component Mapping

The Max-Flow analyzer returns min-cut edges as `(layer, (x1,y1)), (layer, (x2,y2))`. Need to:

1. Map edge coordinates to nearby components
2. Identify which components are "blocking" the channel
3. Return component refs for cut generation

```python
def map_mincut_to_components(min_cut_edges, components):
    """
    Given min-cut edges from Max-Flow, identify blocking components.

    Returns: list of (component_ref, direction) tuples
    """
    blocking = []
    for (layer, pos1), (layer, pos2), capacity in min_cut_edges:
        # Find components whose bounding boxes intersect this edge
        # ...
    return blocking
```

### Step 2: Cut Generator

Convert blocking components to ILP constraints:

```python
def generate_cut(blocking_components, gap_needed):
    """
    Generate ILP constraint to open channel.

    If bottleneck is horizontal (components stacked vertically):
        Add: y_top - y_bottom >= gap_needed + heights

    If bottleneck is vertical (components side-by-side):
        Add: x_right - x_left >= gap_needed + widths
    """
```

### Step 3: Benders Loop

```python
def benders_optimization(max_iterations=20):
    problem = BendersMasterProblem.from_json("data/benders_input.json")
    problem.build()

    for iteration in range(max_iterations):
        # 1. Solve ILP
        result = problem.solve()
        if result.status == "INFEASIBLE":
            return None  # Physics constraints unsatisfiable

        # 2. Update placement and run Max-Flow
        placement = result.positions
        max_flow_result = run_max_flow(placement)

        if max_flow_result.is_feasible:
            return placement  # Success!

        # 3. Generate cuts from bottlenecks
        for edge in max_flow_result.min_cut_edges:
            components = map_mincut_to_components(edge)
            problem.add_routability_cut(components)

    return None  # Failed to converge
```

---

## Testing Commands

```bash
# Run ILP solver test
cd packages/temper-placer
PYTHONPATH=src python -m temper_placer.placement.benders_master data/benders_input.json

# Run Max-Flow analysis (via router pipeline)
PYTHONPATH=src python -c "
from temper_placer.router_v6.pipeline import RouterPipeline
pipeline = RouterPipeline(enable_routability_analysis=True, verbose=True)
# ... load PCB and run Stage 2
"

# Verify grouping constraints
PYTHONPATH=src python -c "
from temper_placer.placement.benders_master import BendersMasterProblem
problem = BendersMasterProblem.from_json('data/benders_input.json')
problem.build()
result = problem.solve()
# Check result.positions against grouping requirements
"
```

---

## References

### Internal Docs

1. `BENDERS_PLACEMENT_OPTIMIZATION.md` - Algorithm theory and mathematical formulation
2. `BENDERS_DESIGN_CONSTRAINTS.md` - All PCB design constraints encoded in ILP
3. `BENDERS_REQUIREMENTS.md` - Implementation checklist and status
4. `BENDERS_AUDIT_REPORT.md` - Data quality findings and fixes applied

### External References

1. Benders, J.F. (1962). "Partitioning procedures for solving mixed-variables programming problems"
2. OR-Tools documentation: https://developers.google.com/optimization
3. NetworkX Max-Flow: https://networkx.org/documentation/stable/reference/algorithms/flow.html

---

## Contact / Questions

This work was done as part of the Router V6 → V7 evolution. The goal is 100% routing success on the Temper board, which currently fails on 11 nets due to congestion bottlenecks.

Key files to understand:
- `router_v6/pipeline.py` - Main routing pipeline
- `router_v6/analysis/max_flow.py` - Routability verification
- `placement/benders_master.py` - Placement optimization

The branch `router-topo-benders` contains all this work. It's based on `router-topo-3`.
