# DRC Error Solutions

This document describes the solution space for each type of DRC error encountered during PCB routing.

## Error Types and Solutions

### 1. tracks_crossing (10-20 errors)

**Description**: Two traces cross on the same layer.

**Root Cause**: 
- Grid-based A* routing doesn't check for line-to-line intersection
- Routes can cross at cell boundaries
- Some crossings are unavoidable (power stage signals)

**Solution Space**:

| Solution | Effort | Effectiveness | Description |
|----------|--------|---------------|-------------|
| **Via Insertion** | Medium (1-2 weeks) | High (95%) | Detect crossing during A*, insert via to switch layers |
| **Layer Assignment** | Low (hours) | Medium (50%) | Assign crossing nets to different layers via YAML |
| **Continuous Geometry** | High (3-4 weeks) | Very High (99%) | Replace grid-based A* with RRT* or visibility graph |
| **Post-Route Repair** | Medium (1-2 weeks) | High (90%) | Detect crossings after routing, reroute with vias |
| **Manual Cleanup** | Low (2-4 hours) | 100% | Fix in KiCad manually |

**Implemented**:
- ✅ Layer assignment via YAML config
- ✅ `post_route_drc.py` crossing detection

**Recommended Next Step**:
Implement via insertion during A* routing when crossing is detected.

---

### 2. clearance (40-90 errors)

**Description**: Traces too close to each other (actual clearance < 0.2mm required).

**Root Cause**:
- Grid cell size (0.2mm) equals clearance requirement
- Diagonal cell moves can reduce effective clearance
- Grid quantization creates gaps in blocking

**Solution Space**:

| Solution | Effort | Effectiveness | Description |
|----------|--------|---------------|-------------|
| **Increase C-Space Inflation** | Low (hours) | Medium (60%) | Block more cells around routes |
| **Smaller Cell Size** | Low (hours) | Low (30%) | Use 0.1mm cells (2x slower routing) |
| **Line-Based Clearance Check** | Medium (1 week) | High (90%) | Check clearance along entire line, not just cells |
| **Post-Route Spacing Fix** | Medium (1-2 weeks) | High (85%) | Detect violations, locally reroute |
| **Continuous Geometry** | High (3-4 weeks) | Very High (99%) | Exact clearance checking |

**Implemented**:
- ✅ C-space inflation (+0.1mm extra margin)
- ⚠️ Smaller cell size tested but slower

**Recommended Next Step**:
Add line-segment-to-line-segment distance check during A* neighbor expansion.

---

### 3. shorting_items (45-70 errors)

**Description**: Two nets are physically connected (short circuit).

**Root Cause**:
- Directly caused by `tracks_crossing` errors
- When traces cross on same layer, they short
- Also caused by via placement too close to other traces

**Solution Space**:
Same as `tracks_crossing` - fixing crossings eliminates shorts.

**Note**: Some "shorts" reported by KiCad DRC are actually crossings counted multiple times (one per intersection point).

---

### 4. solder_mask_bridge (60-80 errors)

**Description**: Solder mask openings too close (fab issue, not electrical).

**Root Cause**:
- **NOT a routing issue**
- Caused by pad spacing in footprints
- KiCad design rules setting

**Solution Space**:

| Solution | Effort | Effectiveness | Description |
|----------|--------|---------------|-------------|
| **Adjust KiCad Design Rule** | Low (minutes) | 100% | Increase `solder_mask_bridge` minimum |
| **Modify Footprints** | Medium (hours) | 100% | Increase pad spacing in custom footprints |
| **Ignore** | None | N/A | These are warnings, board can still be fabricated |

**Recommended**: 
Add to KiCad board setup: `solder_mask_bridge: 0.0mm` to suppress these warnings.

---

### 5. hole_clearance (1-5 errors)

**Description**: Via/hole too close to other via/hole or trace.

**Root Cause**:
- Via placement after routing doesn't check spacing
- Fixed via diameter (0.6mm) with fixed drill (0.3mm)

**Solution Space**:

| Solution | Effort | Effectiveness | Description |
|----------|--------|---------------|-------------|
| **Via Spacing Check** | Low (days) | High | Check hole-to-hole distance before placement |
| **Via Size Optimization** | Low (hours) | Medium | Use smaller vias where possible |

---

## Summary Table

| Error Type | Count | Fix Difficulty | Primary Solution |
|------------|-------|----------------|------------------|
| tracks_crossing | 10-20 | **Medium** | Via insertion at crossings |
| clearance | 40-90 | **High** | Continuous geometry checking |
| shorting_items | 45-70 | **Medium** | Fix tracks_crossing |
| solder_mask_bridge | 60-80 | **Low** | Ignore or adjust design rules |
| hole_clearance | 1-5 | **Low** | Via spacing check |

---

## Recommended Implementation Order

1. **Via Insertion at Crossings** (1-2 weeks)
   - Detect crossing during A* path finding
   - Insert via at crossing point
   - Route remaining segment on alternate layer
   - This fixes both `tracks_crossing` and `shorting_items`

2. **Line-Segment Clearance Check** (1 week)
   - During A* neighbor expansion, check if the line to neighbor crosses existing routes
   - If crossing or too close, skip that neighbor
   - This prevents most clearance violations

3. **Suppress solder_mask_bridge** (minutes)
   - Add to board design rules or ignore in DRC report

4. **Via Spacing Validation** (days)
   - After via placement, validate hole-to-hole distance
   - Adjust via positions if needed

---

## Professional Comparison

| Feature | Our Router | Altium | KiCad PNS |
|---------|------------|--------|-----------|
| Grid-based | Yes | No | No |
| Crossing Prevention | ❌ | ✅ | ✅ |
| Exact Clearance | ❌ | ✅ | ✅ |
| Via Insertion | ❌ | ✅ | ✅ |
| DRC Compliance | ~40% | ~99% | ~95% |

**Conclusion**: Achieving professional-grade DRC compliance requires either:
1. Implementing via insertion + line-segment clearance checking (~2-3 weeks)
2. Or using a professional router (KiCad PNS, FreeRouting) for final routing
