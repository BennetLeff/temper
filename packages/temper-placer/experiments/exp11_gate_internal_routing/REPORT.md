# EXP-11: Internal Layer Routing for GATE Signals - Analysis Report

## Status: ANALYSIS COMPLETE - Implementation Deferred

## Root Cause Analysis

### The HV Clearance Problem

The routing failures for GATE_H/GATE_L, PWM_H/PWM_L, and I_SENSE are caused by
**IEC 60335 high-voltage clearance requirements** (6mm) between signal traces
and HV pads on the power MOSFETs (Q1, Q2) and diodes (D1, D2).

#### Physical Layout Constraints

```
GATE_H routing path:
  U_GATE.15 (39.5, 31.8) → R_GATE_H (24-26, 25) → Q1.1 (20.0, 15.0)
  
  Obstacles:
  - Q1.2 (DC_BUS+) at (25.4, 15.0) - 5.4mm from Q1.1
  - Q1.3 (SW_NODE) at (30.9, 15.0)
  
  6mm clearance is IMPOSSIBLE - Q1 gate pin is only 5.4mm from Q1 collector pin
```

This is a **fundamental PCB design constraint**, not a routing algorithm bug.

### Why Internal Layers Don't Fully Solve This

The 6mm clearance is for **creepage** (surface distance through air). On internal
layers, the PCB dielectric provides isolation. However:

1. **Q1/Q2 are PTH components** - their pads exist on ALL layers
2. **Internal layer routing** still sees PTH pads in DRC checks
3. **Safety clearance** must still be maintained around the barrel of the via/pad

### Attempted Solution

Modified `drc_oracle.py` to apply reduced clearance (0.25-0.5mm) on internal layers
when routing near HV nets. Results:

- Clearance reduced from 6.163mm to 0.413-0.663mm required
- Routes still fail because they try to pass THROUGH the physical pad
- The A* router finds paths that intersect the 3.5mm diameter PTH pads

### Why It Made Things Worse

The reduced clearance allowed the router to attempt more aggressive paths that
ultimately fail at the pad boundary. Net result: more partial routes, more
dangling tracks.

## Current Violation Analysis (94 total)

| Net | Violations | Root Cause |
|-----|------------|------------|
| I_SENSE | 15 | Routes near Q2.3 (DC_BUS-) on B.Cu surface layer |
| GATE_H | 12 | Must reach Q1.1 past Q1.2/Q1.3 (HV pads) |
| GATE_L | 12 | Must reach Q2.1 past Q2.2/Q2.3 (HV pads) |
| SPI_MISO | 11 | Congestion on In1.Cu |
| PWM_L | 9 | Routes near Q1.2/Q1.3 |
| SPI_CLK | 8 | Congestion |
| PWM_H | 7 | Routes near Q1.2/Q1.3 |

## Recommendations

### Option A: PCB Layout Modification (Recommended)

1. **Move U_GATE closer to Q1/Q2** - reduce routing distance
2. **Add gate driver breakout pads** near Q1/Q2 gate pins with F.Cu traces
3. **Use kelvin sensing** for gate connections (separate sense and drive paths)

### Option B: Routing Algorithm Enhancement

1. **Implement multi-start routing** - try different approach angles
2. **Add obstacle-aware waypoint generation** - route around HV zone
3. **Rip-up-and-retry** for nets that fail initial routing

### Option C: Accept Partial Completion

For prototype boards, some nets may need manual routing in KiCad:
- GATE_H, GATE_L: Manual F.Cu traces with proper creepage
- I_SENSE: Manual B.Cu trace with shielding

## Files Modified (Not Committed)

- `drc_oracle.py` - Layer-aware HV clearance (reverted)

## Conclusion

The HV clearance constraint is a physical design issue, not a routing algorithm
limitation. The gate drive signals MUST reach MOSFET gate pins that are physically
adjacent to high-voltage collector/emitter pads. No routing algorithm can violate
physics - either the PCB layout must change, or manual intervention is needed.
