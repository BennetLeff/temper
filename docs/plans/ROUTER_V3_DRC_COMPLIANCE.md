# Router V3: DRC-Compliant PCB Output

**Status**: Planning
**Created**: 2025-12-29
**Goal**: Router produces KiCad PCB files that pass all DRC checks

---

## Current State (DRC Analysis)

From `pcb/DRC_violations.rpt`:

| Category | Count | Severity | Status |
|----------|-------|----------|--------|
| Unconnected Items | 81 | CRITICAL | **Blocking** - No traces in output |
| Clearance Violations | 8 | ERROR | Design rules mismatch |
| Solder Mask Bridge | 8 | ERROR | Same as clearance |
| Silkscreen Issues | ~75 | WARNING | Duplicate text, overlaps |
| Library Mismatch | ~30 | WARNING | Ignorable |
| Hole-to-Hole | 1 | WARNING | Placement collision |

---

## Root Cause Analysis

### Problem 1: No Trace Export (81 Unconnected)

The router computes paths internally as `RoutePath` objects containing grid cells:

```python
@dataclass
class RoutePath:
    net: str
    cells: list[GridCell]  # Internal grid representation
    length: float
    via_count: int
    success: bool
```

But these are **never converted to KiCad PCB elements**:
- No `(segment ...)` elements written
- No `(via ...)` elements written
- Output file only contains components, no traces

**Solution**: Implement `export_routes_to_kicad()` that converts grid paths to actual PCB geometry.

### Problem 2: Clearance Violations (8 errors)

The default netclass specifies 0.2mm clearance:
```
(net_class Default ""
  (clearance 0.2)
  ...
)
```

But some components have tighter pad pitch:
- **U_MCU** (QFN-56): 0.4mm pitch → 0.16mm pad gap
- **J_USB** (USB-C): 0.4mm pitch → 0.1mm pad gap

These are **inherent component characteristics**, not routing issues. The pads themselves violate clearance before any routing occurs.

**Solutions**:
1. Accept pad-to-pad clearance violations (common for fine-pitch)
2. Create net class with 0.1mm clearance for fine-pitch nets
3. Configure KiCad to ignore pad-to-pad clearance in same component

### Problem 3: Solder Mask Bridge (8 errors)

Direct consequence of pad clearance. When pads are <0.2mm apart, no solder mask web can exist between them.

**Solution**: Configure solder mask minimum web width in board setup, or accept as inherent.

### Problem 4: Hole-to-Hole Collision (1 error)

```
C_BUS2 pad 1 @ (86.8666, 108.7500)
D1 pad 2 @ (85.9739, 108.7500)
Distance: 0.0mm (OVERLAPPING)
```

Two THT component holes are at the same position. This is a **placement bug**.

**Solution**: Add placement constraint to prevent THT hole overlap.

### Problem 5: Silkscreen Duplicates (~40 errors)

```
[silk_overlap]: Silkscreen overlap
    @(36.6990 mm, 69.2250 mm): PCB text 'C_BOOT' on F.Silkscreen
    @(36.6990 mm, 69.2250 mm): PCB text 'C_BOOT' on F.Silkscreen
```

Text elements are being written twice at identical positions.

**Solution**: Fix KiCad exporter to deduplicate text elements.

---

## Implementation Plan

### Phase 1: Trace Export (Critical Path)

Convert router grid paths to KiCad PCB geometry.

#### 1.1 Grid-to-World Coordinate Conversion

```python
def grid_to_world(cell: GridCell, origin: tuple, cell_size: float) -> tuple[float, float]:
    """Convert grid cell to world coordinates (mm)."""
    x = origin[0] + cell.x * cell_size + cell_size / 2
    y = origin[1] + cell.y * cell_size + cell_size / 2
    return (x, y)
```

#### 1.2 Path Simplification

Grid paths have many intermediate points. Simplify to essential waypoints:

```python
def simplify_path(cells: list[GridCell]) -> list[GridCell]:
    """Remove redundant points along straight segments."""
    if len(cells) <= 2:
        return cells

    simplified = [cells[0]]
    for i in range(1, len(cells) - 1):
        prev, curr, next = cells[i-1], cells[i], cells[i+1]
        # Keep point only if direction changes
        if not is_collinear(prev, curr, next):
            simplified.append(curr)
    simplified.append(cells[-1])
    return simplified
```

#### 1.3 Segment Generation

```python
def path_to_segments(path: RoutePath, trace_width: float, layer_map: dict) -> list[dict]:
    """Convert path to KiCad segment dictionaries."""
    segments = []
    cells = simplify_path(path.cells)

    for i in range(len(cells) - 1):
        c1, c2 = cells[i], cells[i+1]

        # Layer transition = via, not segment
        if c1.layer != c2.layer:
            continue

        start = grid_to_world(c1, origin, cell_size)
        end = grid_to_world(c2, origin, cell_size)
        layer_name = layer_map[c1.layer]  # e.g., "F.Cu", "B.Cu"

        segments.append({
            'type': 'segment',
            'start': start,
            'end': end,
            'width': trace_width,
            'layer': layer_name,
            'net': path.net,
        })

    return segments
```

#### 1.4 Via Generation

```python
def path_to_vias(path: RoutePath, via_size: float, via_drill: float) -> list[dict]:
    """Extract vias from layer transitions."""
    vias = []

    for i in range(len(path.cells) - 1):
        c1, c2 = path.cells[i], path.cells[i+1]

        if c1.layer != c2.layer:
            pos = grid_to_world(c1, origin, cell_size)
            vias.append({
                'type': 'via',
                'at': pos,
                'size': via_size,
                'drill': via_drill,
                'layers': ['F.Cu', 'B.Cu'],  # Through-hole via
                'net': path.net,
            })

    return vias
```

#### 1.5 KiCad Export Integration

```python
def export_routed_pcb(
    base_pcb_path: str,
    routes: dict[str, RoutePath],
    output_path: str,
    trace_width: float = 0.25,
    via_size: float = 0.8,
    via_drill: float = 0.4,
):
    """Export routes to KiCad PCB file."""
    # Parse base PCB
    pcb = parse_kicad_pcb(base_pcb_path)

    # Generate geometry from routes
    all_segments = []
    all_vias = []

    for net_name, path in routes.items():
        if path.success:
            all_segments.extend(path_to_segments(path, trace_width, layer_map))
            all_vias.extend(path_to_vias(path, via_size, via_drill))

    # Merge into PCB and write
    pcb.add_segments(all_segments)
    pcb.add_vias(all_vias)
    pcb.write(output_path)
```

### Phase 2: Design Rule Compliance

#### 2.1 Trace Width from Net Class

```python
def get_trace_width(net_name: str, netlist: Netlist, default: float = 0.25) -> float:
    """Get trace width from net class."""
    if is_power_net(net_name):
        return 0.5  # Wider for power
    if is_high_speed(net_name):
        return 0.2  # Controlled impedance
    return default
```

#### 2.2 Clearance-Aware Routing

Router must respect clearance during pathfinding:

```python
def is_clearance_violation(pos: tuple, existing_traces: list, clearance: float) -> bool:
    """Check if position violates clearance to existing traces."""
    for trace in existing_traces:
        dist = point_to_segment_distance(pos, trace.start, trace.end)
        if dist < clearance + trace.width / 2:
            return True
    return False
```

#### 2.3 Fine-Pitch Net Class

For components with tight pad pitch, create appropriate net class:

```python
def create_fine_pitch_netclass(pcb: KicadPCB) -> None:
    """Add net class for fine-pitch components."""
    pcb.add_netclass({
        'name': 'FinePitch',
        'clearance': 0.1,  # 0.1mm vs default 0.2mm
        'trace_width': 0.15,
        'via_dia': 0.6,
        'via_drill': 0.3,
        'nets': ['SPI_*', 'USB_*', '+3V3', 'GND'],  # Assign appropriate nets
    })
```

### Phase 3: Placement Validation

#### 3.1 Hole-to-Hole Collision Check

```python
def validate_hole_clearance(components: list[Component], min_clearance: float = 0.25) -> list[str]:
    """Check for THT hole collisions."""
    violations = []
    holes = []

    for comp in components:
        for pad in comp.pads:
            if pad.is_through_hole:
                holes.append((comp.ref, pad.number, pad.position, pad.drill_size))

    for i, (ref1, pad1, pos1, drill1) in enumerate(holes):
        for ref2, pad2, pos2, drill2 in holes[i+1:]:
            dist = distance(pos1, pos2)
            required = (drill1 + drill2) / 2 + min_clearance
            if dist < required:
                violations.append(f"{ref1}.{pad1} <-> {ref2}.{pad2}: {dist:.3f}mm (need {required:.3f}mm)")

    return violations
```

#### 3.2 Placement Constraint for THT

```python
class THTPadClearanceLoss(LossFunction):
    """Ensure THT pads don't overlap."""

    def __call__(self, positions: Array, context: LossContext) -> LossResult:
        penalty = 0.0
        tht_pads = get_all_tht_pads(context.netlist, positions)

        for i, pad1 in enumerate(tht_pads):
            for pad2 in tht_pads[i+1:]:
                dist = jnp.sqrt((pad1.x - pad2.x)**2 + (pad1.y - pad2.y)**2)
                min_dist = (pad1.drill + pad2.drill) / 2 + 0.25
                violation = jnp.maximum(0, min_dist - dist)
                penalty += violation ** 2

        return LossResult(value=self.weight * penalty)
```

### Phase 4: Silkscreen Cleanup

#### 4.1 Deduplicate Text Elements

```python
def deduplicate_silkscreen(pcb: KicadPCB) -> int:
    """Remove duplicate silkscreen text elements."""
    seen = set()
    removed = 0

    new_texts = []
    for text in pcb.silkscreen_texts:
        key = (text.content, text.position, text.layer)
        if key not in seen:
            seen.add(key)
            new_texts.append(text)
        else:
            removed += 1

    pcb.silkscreen_texts = new_texts
    return removed
```

#### 4.2 Move Text Away from Pads

```python
def adjust_silkscreen_for_pads(pcb: KicadPCB, clearance: float = 0.15) -> None:
    """Reposition silkscreen text that overlaps pads."""
    for text in pcb.silkscreen_texts:
        for pad in get_nearby_pads(text.position, pcb):
            if overlaps(text.bounds, pad.bounds):
                # Move text to nearest non-overlapping position
                text.position = find_clear_position(text, pad, clearance)
```

---

## File Changes Required

### New Files

| File | Purpose |
|------|---------|
| `io/kicad_exporter.py` | Export routes to KiCad PCB format |
| `routing/path_simplify.py` | Simplify grid paths to waypoints |
| `routing/drc_check.py` | Pre-export DRC validation |
| `losses/tht_clearance.py` | THT pad collision loss |

### Modified Files

| File | Change |
|------|--------|
| `routing/maze_router.py` | Return net ID with paths for export |
| `io/kicad_parser.py` | Support adding segments/vias |
| `scripts/internal_route.py` | Call exporter after routing |
| `scripts/placement_routing_loop.py` | Export final result |

---

## Acceptance Criteria

### Must Pass

1. **0 Unconnected Items** - All nets have traces
2. **0 Clearance Errors from Traces** - Routed traces respect clearance
3. **0 Hole-to-Hole Errors** - No component collisions

### May Accept (Component Inherent)

1. **Pad-to-Pad Clearance** - Fine-pitch components (QFN-56, USB-C)
2. **Solder Mask Bridge** - Same as pad-to-pad

### Should Fix

1. **Silkscreen Duplicates** - Export bug
2. **Silkscreen Overlaps** - Placement-dependent

### Can Ignore

1. **Library Mismatch Warnings** - Local modifications

---

## Test Plan

### Unit Tests

```python
def test_grid_to_world_conversion():
    cell = GridCell(x=10, y=20, layer=0)
    pos = grid_to_world(cell, origin=(0, 0), cell_size=0.5)
    assert pos == (5.25, 10.25)  # Center of cell

def test_path_simplification():
    # Straight line should collapse to 2 points
    cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
    simplified = simplify_path(cells)
    assert len(simplified) == 2

def test_via_extraction():
    cells = [GridCell(5, 5, 0), GridCell(5, 5, 1), GridCell(6, 5, 1)]
    path = RoutePath(net="TEST", cells=cells, ...)
    vias = path_to_vias(path, 0.8, 0.4)
    assert len(vias) == 1
    assert vias[0]['at'] == grid_to_world(cells[0], ...)
```

### Integration Tests

```python
def test_full_export_pipeline():
    # Route a simple board
    routes = router.rrr_route_all_nets(...)

    # Export
    export_routed_pcb("input.kicad_pcb", routes, "output.kicad_pcb")

    # Run KiCad DRC
    result = run_kicad_drc("output.kicad_pcb")
    assert result.unconnected_count == 0
    assert result.clearance_errors == 0  # Excluding pad-to-pad
```

### Manual Verification

1. Open output in KiCad
2. Visual inspection of traces
3. Run DRC, verify expected errors only
4. 3D view check

---

## Priority Order

| Priority | Task | Impact | Effort |
|----------|------|--------|--------|
| **P0** | Trace export to KiCad | Fixes 81 unconnected | 2-3 days |
| **P0** | Via export to KiCad | Required for multi-layer | 0.5 day |
| **P1** | Path simplification | Cleaner output | 0.5 day |
| **P1** | Clearance-aware routing | Fixes trace DRC | 1 day |
| **P2** | THT collision check | Fixes 1 hole-to-hole | 0.5 day |
| **P2** | Fine-pitch net class | Documents pad DRC | 0.5 day |
| **P3** | Silkscreen dedup | Fixes ~40 warnings | 0.5 day |
| **P3** | Silkscreen positioning | Fixes ~30 warnings | 1 day |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Unconnected Items | 81 | 0 |
| Clearance Errors (traces) | N/A | 0 |
| Clearance Errors (pads) | 8 | 8 (accepted) |
| Silkscreen Warnings | ~75 | <10 |
| Hole-to-Hole | 1 | 0 |
