# Placement Improvement Tasks for Routing Success

These tasks address the root cause of SPI routing failures: **placement that ignores routing channel requirements**.

> "Routing failures are placement failures unless proven otherwise." — Architecture Doc, Section 4

---

## Task 1: Routing Channel Loss

### Problem
Components placed edge-to-edge create **narrow corridors** where multiple nets must compete for limited routing space. The SPI failure demonstrates this:

```
Board Edge (x=0)     U_CT (x=10)      U_MCU (x=21)
    |                   |                 |
    |    6mm corridor   |                 |
    |<----------------->|                 |
    |  4 SPI signals    |                 |
    |  must fit here!   |                 |
```

### Solution
Add a **RoutingChannelLoss** that:
1. Computes pairwise distances between components
2. Penalizes placements where corridor width < minimum (e.g., 5mm)
3. Higher penalty when corridor carries more nets

### Implementation
```python
class RoutingChannelLoss(LossFunction):
    """Penalize placements that create narrow routing corridors."""
    
    def __call__(self, positions, context):
        # For each pair of adjacent components
        # Estimate nets that must route between them
        # If corridor < min_width, apply penalty
        pass
```

### Files to Modify
- `losses/routing_channel.py` (NEW)
- `losses/__init__.py` (add export)
- `optimizer/core.py` (include in default loss)

### Acceptance Criteria
- [ ] Components separated by < 5mm with >2 crossing nets get penalty
- [ ] Penalty scales with (net_count / corridor_width)
- [ ] Unit tests verify penalty gradient pushes components apart

---

## Task 2: MCU Peripheral Clustering

### Problem
MCUs have many direct connections to peripherals (SPI slaves, I2C devices, ADC inputs). When peripherals are placed far from the MCU:
- Long traces = more routing conflicts
- Signal integrity issues (for high-speed signals)
- Wasted board space

Current placement:
- U_MCU @ (21.4, 60.9)
- U_CT (SPI) @ (10.0, 81.5) — **23mm away**
- MAX31865 (SPI) @ (5.6, 108.8) — **50mm away**

### Solution
Add an **MCUClusteringLoss** that:
1. Identifies the MCU component (by reference pattern or net fanout)
2. Identifies direct peripherals (components sharing nets with MCU)
3. Penalizes peripherals beyond a clustering radius (e.g., 15mm)

### Implementation
```python
class MCUClusteringLoss(LossFunction):
    """Keep MCU peripherals within clustering radius."""
    
    def __init__(self, mcu_ref: str, max_distance: float = 15.0):
        self.mcu_ref = mcu_ref
        self.max_distance = max_distance
    
    def __call__(self, positions, context):
        mcu_pos = positions[mcu_idx]
        for peripheral_idx in peripheral_indices:
            dist = distance(mcu_pos, positions[peripheral_idx])
            if dist > self.max_distance:
                penalty += (dist - self.max_distance) ** 2
        return penalty
```

### Files to Modify
- `losses/clustering.py` (NEW)
- `io/config_loader.py` (parse MCU ref from constraints)
- Test with temper board (U_MCU reference)

### Acceptance Criteria
- [ ] MCU identified by reference ("U_MCU" or highest fanout)
- [ ] Direct peripherals identified (share ≥2 pins with MCU)
- [ ] Penalty applied when peripheral > 15mm from MCU
- [ ] Test: SPI peripherals pulled toward MCU after optimization

---

## Task 3: Bus-Aware Placement

### Problem
SPI, I2C, and parallel buses consist of **multiple parallel signals** that must route together. When components are not aligned along a bus axis:
- Signals cross each other
- Routing becomes impossible in narrow corridors
- Conflicts multiply (N signals × M crossing points)

Current SPI routing requires:
```
  U_MCU       →  U_CT    →  MAX31865
  (21, 61)       (10, 81)    (6, 109)
        ↘          ↓           ↙
        All 4 signals must fit in 6mm corridor
```

### Solution
Add **BusAlignmentLoss** that:
1. Identifies bus nets (signals with matching prefixes: SPI_*, I2C_*)
2. Finds components on each bus
3. Penalizes placements where bus components are not collinear

### Implementation
```python
class BusAlignmentLoss(LossFunction):
    """Encourage collinear placement of bus-connected components."""
    
    def __init__(self, bus_patterns: list[str] = ["SPI_", "I2C_", "USB_"]):
        self.bus_patterns = bus_patterns
    
    def __call__(self, positions, context):
        # For each bus, find connected components
        # Compute best-fit line through component centers
        # Penalize deviation from line
        pass
```

### Alignment Options
1. **Horizontal alignment**: Components at similar Y, different X
2. **Vertical alignment**: Components at similar X, different Y  
3. **L-shaped**: Allow one turn in the bus path

### Files to Modify
- `losses/bus_alignment.py` (NEW)
- `core/netlist.py` (add bus detection helper)
- `constraints/pcl_parser.py` (allow explicit bus definitions)

### Acceptance Criteria
- [ ] SPI_* nets grouped as single bus
- [ ] Bus component alignment computed (horizontal/vertical)
- [ ] Penalty for component deviation from bus axis
- [ ] Test: SPI peripherals aligned after optimization

---

## Dependencies

```
Task 1 (Routing Channel)
    ↓
Task 2 (MCU Clustering)  ── These can run in parallel
    ↓
Task 3 (Bus Alignment)   ── Builds on clustering
```

## Priority

1. **Routing Channel Loss** — Most general, fixes the immediate problem
2. **MCU Clustering** — Addresses specific SPI issue
3. **Bus Alignment** — Polish for complex buses

## Validation

After implementing all three, re-run placement+routing loop:
```bash
uv run python scripts/placement_routing_loop.py pcb/temper_ready_for_route.kicad_pcb \
  --max-iterations 10 \
  --exclude-power-nets
```

Expected outcome:
- SPI peripherals moved closer to MCU
- Routing corridor > 10mm
- 0 failed nets, 0 conflicts for SPI
