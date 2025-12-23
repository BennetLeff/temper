# Multi-Layer Routing in Temper Router

## Overview

The maze router supports multi-layer PCB routing with configurable via costs and layer-specific constraints. This document explains how multi-layer routing works and what features are currently supported.

## Current Multi-Layer Support

### ✅ Implemented Features

#### 1. **Basic Multi-Layer Pathfinding**

The router can route across multiple layers using vias (vertical connections):

```python
router = MazeRouter(
    grid_size=(100, 100),
    num_layers=4,  # Support 2, 4, 6+ layers
    via_cost=5.0   # Penalty for changing layers
)

# Find path that can use vias
path = router.find_path(
    start=(10, 10),
    end=(50, 50),
    layer=0,
    allow_layer_change=True  # Enable vias
)
```

**How it works:**
- Each cell in the grid has a layer dimension: `occupancy[x, y, layer]`
- A* pathfinding can move in 5 directions: N, S, E, W, and UP/DOWN (via)
- Via transitions add extra cost to discourage unnecessary layer changes

#### 2. **Via Cost Penalty**

Vias add cost to the routing path to prefer staying on the same layer:

```python
def _get_neighbor_cost(self, current: GridCell, neighbor: GridCell) -> float:
    base_cost = 1.0
    if current.layer != neighbor.layer:
        return base_cost + self.via_cost  # Add via penalty
    return base_cost
```

**Example:**
- Same-layer move: cost = 1.0
- Via (layer change): cost = 1.0 + 5.0 = 6.0
- Router prefers 6 same-layer moves over 1 via

**Why this matters:**
- Vias are expensive to manufacture
- Vias add inductance/capacitance (bad for high-speed signals)
- Vias take up space and can block routing on other layers

#### 3. **Layer-Specific Component Blocking**

Components can block only specific layers:

```python
router.block_components(
    components,
    positions,
    layer_specific=True  # Block only layer 0 (top)
)
```

**Use cases:**
- Through-hole components: block all layers
- SMD components: block only top or bottom layer
- Allows routing underneath SMD components on inner layers

#### 4. **Escape Routes on All Layers**

Escape routes are created on all layers by default:

```python
# In _try_escape_route():
for layer in range(self.num_layers):
    self.occupancy = self.occupancy.at[unblock_gx, unblock_gy, layer].set(0)
```

This allows pins to connect to any layer, enabling flexible via placement.

### ❌ NOT Yet Implemented

#### 1. **Layer Constraints (Ground/Power Planes)**

**What's missing:**
- No concept of "layer 2 is ground plane"
- No prohibition of signal routing on power/ground layers
- No special handling for power net routing

**Common PCB layer stackups:**
```
4-layer PCB:
  Layer 1 (Top):    Signal + components
  Layer 2 (Inner):  Ground plane
  Layer 3 (Inner):  Power plane (VCC)
  Layer 4 (Bottom): Signal + components

6-layer PCB:
  Layer 1 (Top):    Signal + components
  Layer 2 (Inner):  Ground plane
  Layer 3 (Inner):  Signal (high-speed)
  Layer 4 (Inner):  Signal (high-speed)
  Layer 5 (Inner):  Power plane (VCC)
  Layer 6 (Bottom): Signal + components
```

**What we'd need:**
```python
router = MazeRouter(
    grid_size=(100, 100),
    num_layers=4,
    layer_types=[
        LayerType.SIGNAL,  # Layer 0: top signal
        LayerType.GROUND,  # Layer 1: ground plane
        LayerType.POWER,   # Layer 2: power plane
        LayerType.SIGNAL,  # Layer 3: bottom signal
    ]
)

# Only route power nets on power layers
router.route_net(
    net_name="VCC",
    net_type=NetType.POWER,
    allowed_layers=[2]  # Only layer 2 (power plane)
)

# Signal nets avoid power/ground layers
router.route_net(
    net_name="SPI_MOSI",
    net_type=NetType.SIGNAL,
    allowed_layers=[0, 3]  # Only signal layers
)
```

#### 2. **Layer Preference Hints**

**What's missing:**
- No way to prefer certain layers for certain nets
- No "route high-speed signals on inner layers" logic
- No automatic layer assignment

**What we'd need:**
```python
# Prefer inner layers for high-speed signals (better EMI)
router.route_net(
    net_name="USB_DP",
    preferred_layers=[2, 3],  # Inner layers
    layer_preference_weight=2.0  # 2x cost penalty for other layers
)

# Prefer outer layers for low-speed signals (easier access)
router.route_net(
    net_name="LED_CTRL",
    preferred_layers=[0, 5],  # Outer layers
)
```

#### 3. **Via Stacking and Blind/Buried Vias**

**What's missing:**
- All vias are through-hole (connect all layers)
- No blind vias (outer layer to inner layer)
- No buried vias (inner layer to inner layer)
- No via-in-pad support

**What we'd need:**
```python
# Blind via: Layer 0 to Layer 2 only
router.add_via(
    x=10, y=10,
    from_layer=0,
    to_layer=2,
    via_type=ViaType.BLIND
)

# Buried via: Layer 2 to Layer 3 only
router.add_via(
    x=20, y=20,
    from_layer=2,
    to_layer=3,
    via_type=ViaType.BURIED
)
```

#### 4. **Keepout Zones Per Layer**

**What's missing:**
- No per-layer keepout zones
- Can't say "no routing on layer 2 in this area"

**What we'd need:**
```python
# Keepout zone on ground layer under high-speed IC
router.add_keepout(
    x=50, y=50, width=20, height=20,
    layers=[1],  # Only layer 1 (ground)
    reason="Preserve ground plane under U1"
)
```

## How Multi-Layer Routing Works Now

### Pathfinding with Vias

The A* algorithm treats layer changes as just another type of move:

```python
def _get_neighbors(self, cell: GridCell, allow_layer_change: bool = False):
    neighbors = []
    
    # 4-connected neighbors on same layer
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = cell.x + dx, cell.y + dy
        if is_free(nx, ny, cell.layer):
            neighbors.append(GridCell(nx, ny, cell.layer))
    
    # Layer transitions (vias)
    if allow_layer_change and self.num_layers > 1:
        for new_layer in range(self.num_layers):
            if new_layer != cell.layer and is_free(cell.x, cell.y, new_layer):
                neighbors.append(GridCell(cell.x, cell.y, new_layer))
    
    return neighbors
```

**Key points:**
1. Vias are only added as neighbors if `allow_layer_change=True`
2. Via moves keep same (x, y) position, only change layer
3. Via cost is added in `_get_neighbor_cost()`
4. A* naturally finds optimal via placement based on cost

### Example: Routing Around Obstacle with Via

```
Layer 0 (top):
  S X X X E    S = start, E = end, X = obstacle
  . . . . .

Layer 1 (bottom):
  . . . . .    All clear
  . . . . .

Path without vias (allow_layer_change=False):
  S → down → down → right → right → right → up → up → E
  Length: 8 cells, Cost: 8.0

Path with vias (allow_layer_change=True, via_cost=2.0):
  S → via to L1 → right → right → right → via to L0 → E
  Length: 5 cells + 2 vias, Cost: 5.0 + 2*2.0 = 9.0

Router chooses: No vias (8.0 < 9.0)
```

If via_cost was 1.0:
```
Path with vias: 5.0 + 2*1.0 = 7.0
Router chooses: Use vias (7.0 < 8.0)
```

## Test Coverage

Multi-layer routing is tested in:

- **`test_layer_preference.py`**: Via cost effects on path selection
- **`test_layer_specific_blocking.py`**: Layer-specific component blocking
- **`test_maze_router_oracles.py`**: Basic multi-layer pathfinding
- **`test_real_world_scenarios.py`**: BGA fanout with 4 layers

All tests passing ✅

## Future Work

To support real-world PCB design, we need:

1. **Layer types** (signal/power/ground) - **Priority: HIGH**
   - Essential for proper power distribution
   - Prevents signal routing on power planes
   - See: `temper-jnbs` (differential pairs need this)

2. **Layer preference** - **Priority: MEDIUM**
   - Route high-speed on inner layers (EMI)
   - Route low-speed on outer layers (access)

3. **Blind/buried vias** - **Priority: LOW**
   - Advanced manufacturing feature
   - Reduces via count and improves density
   - Not needed for 2-4 layer boards

4. **Per-layer keepouts** - **Priority: MEDIUM**
   - Preserve ground plane integrity
   - Avoid routing under sensitive components

## References

- Via cost implementation: `MazeRouter._get_neighbor_cost()`
- Multi-layer neighbors: `MazeRouter._get_neighbors()`
- Layer-specific blocking: `MazeRouter.block_components(layer_specific=True)`
- Tests: `packages/temper-placer/tests/routing/test_layer_*.py`
