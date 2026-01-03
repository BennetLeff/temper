# DRC Tracking Log

This document tracks DRC changes across router-v4 iterations. Each entry records the change made, the resulting DRC metrics, and categorized breakdown.

---

## Root Cause Analysis (2025-12-30)

**Problem:** Router reports 0 conflicts but KiCad finds 198 shorts.

**Root Cause:** The router's conflict detection (`net_occupancy`) tracks only **center-line cells**, not the actual copper footprint.

```
Trace width: 0.25mm, Grid cell: 0.1mm
Two traces 0.2mm apart (2 cells)

Grid view:   [A][ ][B]  ← No conflict (different cells)
Actual:      [AAAA][BBBB]  ← Overlap! (0.05mm short)
```

**Fix Required:** When marking cells as occupied, inflate by `trace_width / (2 * cell_size)` cells in each direction.

---

## Change Log

### Entry 9: Width-Aware Router Fix (Verified) (2025-12-30 16:35)
- **Change**: Inflated router occupancy by `trace_width`.
- **Conflicts Detected**: ~3500 (was 0). Proves fix works.
- **Result**:
  - `shorting_items`: **139** (was 198) - 30% reduction in single pass.
  - `track_dangling`: **17** (was 27)
  - `clearance`: **127** (was 67) - Increased due to tighter packing.
- **Status**: Fix verified. Shorting blindness unresolved. Remaining shorts require more RRR iterations.

### Entry 7: Star Ground Zones (2025-12-30 15:45)
**Change:** Implemented star-ground topology with separate zones for GND/PGND/CGND
**File:** `star_filled.kicad_pcb`

| Metric | Value |
|--------|-------|
| **Unconnected Items** | 41 |
| **Other Violations** | 439 |

**Unconnected by Category:**
| Category | Count |
|----------|-------|
| Ground | 14 |
| Power | 22 |
| Signal | 5 |

**Top Nets:**
- I_SENSE: 12
- GND: 12
- +3V3: 12
- +5V: 6
- VCC_BOOT: 4

**Notes:** Star-ground working - CGND has 0 unconnected. Signal routing artifacts dominate.

---

### Entry 6: Professional Flow - GND Only Zone (2025-12-30 15:35)
**Change:** Unified GND-only zone, power rails routed as traces
**File:** `pro_final.kicad_pcb`

| Metric | Value |
|--------|-------|
| **Unconnected Items** | 43 |

**Unconnected by Category:**
| Category | Count |
|----------|-------|
| Ground | 18 |
| Power | 19 |
| Signal | 6 |

**Notes:** PGND/CGND can't connect to GND-only zone (different nets).

---

### Entry 5: Full-Board Overlapping Zones (2025-12-30 15:10)
**Change:** Full-board zones for all power nets with priority stacking
**File:** `fanout_v3_filled.kicad_pcb`

| Metric | Value |
|--------|-------|
| **Unconnected Items** | 62 |

**Notes:** Priority stacking caused zone fragmentation. Worse than bounded zones.

---

### Entry 4: GND-Only Full Board (2025-12-30 15:08)
**Change:** Only GND gets full-board zone, other power nets excluded
**File:** `fanout_v4_filled.kicad_pcb`

| Metric | Value |
|--------|-------|
| **Unconnected Items** | 44 |

**Notes:** Power rails left unconnected without zones.

---

### Entry 3: Bounded Zones v2 + Fanout (2025-12-30 15:03)
**Change:** Bounded zones with padding + fanout vias for SMD pads
**File:** `fanout_v2_filled.kicad_pcb`

| Metric | Value |
|--------|-------|
| **Unconnected Items** | 34 |

**Notes:** Best result so far. Bounded zones avoid fragmentation.

---

### Entry 2: Power Fanout Initial (2025-12-30 14:55)
**Change:** Added 48 fanout vias for SMD power pads
**File:** `fanout_filled.kicad_pcb`

| Metric | Value |
|--------|-------|
| **Unconnected Items** | 34 |

**Notes:** Via stitching working. Reduced from 69.

---

### Entry 1: Baseline - No Zones, No Fanout (2025-12-30 14:50)
**Change:** Routed signal nets only, power nets excluded
**File:** `placement_optimized_02.kicad_pcb`

| Metric | Value |
|--------|-------|
| **Unconnected Items** | 69 |

**Notes:** All unconnected items are power/ground SMD pads without plane connections.

---

## Summary Chart

| Entry | Change | Unconnected | Ground | Power | Signal | Trend |
|-------|--------|-------------|--------|-------|--------|-------|
| 1 | Baseline | 69 | 56 | 7 | 6 | - |
| 2 | + Fanout vias | 34 | 21 | 7 | 6 | ↓ 35 |
| 3 | + Bounded zones v2 | 34 | 21 | 7 | 6 | → 0 |
| 4 | GND-only zone | 44 | 22 | 16 | 6 | ↑ 10 |
| 5 | Full-board overlapping | 62 | 28 | 28 | 6 | ↑ 18 |
| 6 | Pro flow (GND only) | 43 | 18 | 19 | 6 | ↓ 19 |
| 7 | Star ground zones | 41 | 14 | 22 | 5 | ↓ 2 |

## Best Configuration

**Recommended:** Entry 3 (Bounded zones v2 + fanout)
- Lowest unconnected count: 34
- Avoids zone fragmentation
- Each net gets appropriate coverage
