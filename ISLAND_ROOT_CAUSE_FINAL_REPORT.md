# Investigation Complete: Root Cause of Routing Islands

## Executive Summary

Completed full investigation into why routing fails with "disconnected islands." The root cause is **zone constraint mismatch** between design intent (`temper_constraints.yaml`) and implementation (`benders_master.py`), combined with overly strict zone boundaries that don't account for bridge components.

---

## Key Findings

### Finding 1: Zone Constraints Are Hardcoded and Out of Sync

**Problem:** Zone constraints exist in TWO places with DIFFERENT values:

| Source | Q1/Q2 (Power) | U_GATE (Driver) | U_MCU (Control) |
|--------|---------------|-----------------|-----------------|
| `temper_constraints.yaml` (Design) | Y ≥ 110mm | Y = 70-110mm | Y < 70mm |
| `benders_master.py` (Code) | Y = 90-140mm | Y = 100-140mm | Y = 60-110mm |

**Impact:** The Benders optimizer enforces wrong zones, allowing violations of design intent.

### Finding 2: Strict Zones Create Routing Gaps

**Experiment:** Applied strict zone compliance manually:
- Moved 25 components to match `temper_constraints.yaml`
- U_MCU: Y=85 → Y=50 (-35mm)
- C_BUS1/C_BUS2: Y=65-85 → Y=108 (+23-43mm)
- U_GATE: Y=117 → Y=95 (-22mm)

**Result:**
- Before: 28mm island gap, 72% routing (13/18 nets)
- After: **103mm island gap**, 73% routing (11/15 nets) - WORSE!

**Root Cause:** Moving C_BUS capacitors from Y=65-85 to Y=108 broke the routing bridge between control and driver zones.

### Finding 3: Some Components MUST Bridge Zones

**Bridge Components** that naturally span multiple zones:

| Component | Function | Natural Position | Why It Bridges |
|-----------|----------|------------------|----------------|
| C_BUS1/C_BUS2 | DC bus caps | Y = 75-90mm | Connects rectifier (Y=60-75) to IGBTs (Y>110) |
| D1/D2 | Rectifier | Y = 60-75mm | Connects AC input (Y=25) to DC bus |
| U_GATE | Gate driver | Y = 90-105mm | Connects control signals (Y<70) to IGBTs (Y>110) |

These components create the **routing backbone** that connects zones. Forcing them into single zones breaks connectivity.

### Finding 4: Zone Separation Rationale

From `temper_constraints.yaml` comments:
- **power_zone**: "340V/40A switching components" - HV safety
- **driver_zone**: "isolated from MCU" - noise immunity
- **control_zone**: "separated from power stage" - protect low-voltage logic

**Key observation:** Zones are for EMC/safety, NOT strict physical barriers. There's no mention of specific creepage/clearance requirements that would prevent overlap.

---

## Proposed Solution: Overlapping Zones

### Rationale for Overlap

**Electrical Safety:** 
- The 3.0mm clearance for HV nets is enforced by routing rules, not zone boundaries
- EMC isolation achieved through proper grounding and layout, not physical separation
- No IEC 60950-1 requirement for zone gaps (creepage is per-net, not per-zone)

**Routing Feasibility:**
- Bridge components need freedom to span boundaries
- 10-20mm overlap allows smooth transitions
- Prevents artificial gaps in routing skeleton

### Recommended Zone Boundaries

```yaml
zones:
  - name: "control_zone"
    bounds: [0, 0, 100, 80]  # Was 70, now 80 (+10mm overlap into driver)
    description: "MCU and low-voltage control"
  
  - name: "driver_zone"  
    bounds: [0, 60, 100, 120]  # Was 70-110, now 60-120 (±10mm overlap)
    description: "Gate drivers, sensing, DC bus caps - BRIDGE ZONE"
  
  - name: "power_zone"
    bounds: [0, 100, 100, 150]  # Was 110, now 100 (-10mm overlap with driver)
    description: "IGBTs and HV switching"
```

**Overlap regions:**
- Y = 60-70mm: Control/Driver overlap (for power supplies, CT circuits)
- Y = 100-110mm: Driver/Power overlap (for gate driver, DC bus caps)

### Bridge Component Assignments

Allow specific components in multiple zones:

```yaml
bridge_components:
  - ref: "C_BUS1"
    allowed_zones: ["driver_zone", "power_zone"]
    preferred_y: 90  # Nominal position in overlap region
    
  - ref: "C_BUS2"
    allowed_zones: ["driver_zone", "power_zone"]
    preferred_y: 90
    
  - ref: "U_GATE"
    allowed_zones: ["driver_zone", "power_zone"]
    preferred_y: 105
    
  - ref: "D1"
    allowed_zones: ["control_zone", "driver_zone"]
    preferred_y: 65
    
  - ref: "D2"
    allowed_zones: ["control_zone", "driver_zone"]
    preferred_y: 75
```

---

## Answer to "Should We Increase max_gap_mm?"

**NO** - not yet. The real problem is zone enforcement, not gap estimation.

**Sequence:**
1. **First:** Fix zone constraint sync (update `benders_master.py` to match YAML)
2. **Second:** Add overlapping zones (±10mm at boundaries)
3. **Third:** Re-run Benders and check if it converges
4. **Only if still failing:** Consider increasing `max_gap_mm` from 10mm to 12mm

The 10mm gaps Benders requested are trying to compensate for broken zone enforcement. Fix the root cause first.

---

## Implementation Plan

### Phase 1: Zone Constraint Sync (HIGH PRIORITY)

**Option A:** Update `benders_master.py` to load zones from YAML
- Create `load_zones_from_yaml()` function
- Parse `temper_constraints.yaml` zones
- Convert to ILP constraints

**Option B:** Generate `benders_input.json` from YAML (BETTER)
- Create `export_benders_input.py` script
- Auto-generate from `temper_constraints.yaml`
- Single source of truth

### Phase 2: Implement Overlapping Zones

Update `temper_constraints.yaml`:
```yaml
zones:
  - name: "control_zone"
    bounds: [0, 0, 100, 80]
    hard_bounds: [0, 0, 100, 70]  # Strict limit for pure control components
    
  - name: "driver_zone"
    bounds: [0, 60, 100, 120]
    hard_bounds: [0, 70, 100, 110]  # Core zone
    
  - name: "power_zone"
    bounds: [0, 100, 100, 150]
    hard_bounds: [0, 110, 100, 150]  # Strict limit for pure power components
```

### Phase 3: Validate with Test Run

1. Apply new overlapping zones
2. Re-run Benders optimization
3. Check routing success rate
4. Verify island elimination

**Success criteria:**
- Routing islands ≤ 10mm gaps (bridgeable)
- ≥ 85% net routing success
- Benders converges (not infeasible)

---

## Conclusion

The routing island problem is caused by **configuration mismatch** and **overly strict zone boundaries**, not by inadequate gap sizes.

**Next Action:** Implement zone constraint sync (Phase 1) to ensure Benders uses the correct design intent from `temper_constraints.yaml`.

**Hold on max_gap_mm increase** until after zone fixes are validated.
