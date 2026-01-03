# Design: Physics-Aware Hypergraph Routing System

## Executive Summary
This design proposes a unified architecture for automated PCB layout that eliminates manual "band-aids" by deriving routing strategies directly from physical constraints. By treating the PCB as a **Physics-Aware Hypergraph**, we can programmatically infer complex behaviors (like zone-skirting for orphan traces or automatic plane flooding) without hardcoded rules.

**Design Goals:**
- Reusable across multiple board designs (not just Temper)
- Integrates with existing `MazeRouter` and `congestion` modules
- Provides explainable decisions for debugging

## 1. The Core Problem
Current autorouters (Maze, FreeRouting) are "blind" graph solvers. They treat all nets as equal connections A-to-B. They fail in high-power contexts because they lack **Semantic Awareness**:
*   They don't know that `GND` on `J_AC_IN` is an "orphan" pin in a hostile High Voltage zone.
*   They don't know that `PGND` carries 40A and requires a plane, not a trace.
*   They don't provide spatial feedback to the placer when channels are blocked.

## 2. The Solution: The Hypergraph Bridge
We introduce a middleware layer, the **HypergraphRouterBridge**, which translates physical attributes (Current, Voltage, Zone) into explicit **Routing Strategies**.

### 2.1 Formalizing the Bridge
The Bridge acts as a deterministic translator between the **Physical World** (forces, fields, zones) and the **Routing World** (costs, grids, algorithms). Formalization ensures the system is testable, scalable, and explainable.

#### 2.1.1 The Contract (Input/Output)
The Bridge is a **Stateless Function** (pure for a given snapshot):
*   **Input: `PhysicsState`**
    *   `Hypergraph`: Connectivity + Net Attributes (e.g., 40A, 340V).
    *   `Placement`: Component Coordinates (X, Y, Rotation).
    *   `BoardModel`: Zone Boundaries, Keepouts, Layer Stackup.
*   **Output: `RoutingContext`**
    *   A map of `NetID -> Strategy` (The "How").
    *   A map of `NetID -> CostModifier` (The "Where").

**Incremental Update Strategy:** When placement changes, recompute only affected nets:
1. Identify components that moved > threshold (e.g., 1mm)
2. Recompute zone membership only for pins on those components
3. Invalidate cached strategies only for affected nets

**Complexity:** O(M × Z) where M = moved components, Z = zones. For typical placement steps (few components move), this is ~O(1) amortized.

#### 2.1.2 The Vocabulary (Concrete Data Structures)

```python
# src/temper_placer/routing/bridge/types.py

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable
import jax.numpy as jnp
from jax import Array

class RoutingStrategy(Enum):
    """How to route this net."""
    STANDARD_A_STAR = auto()   # Shortest path, basic avoidance
    EDGE_HUG = auto()          # Bias toward board/zone boundary
    FLOOD_FILL = auto()        # Skip routing; generate polygon pour
    DIFFERENTIAL_PAIR = auto() # Route parallel to paired net
    EXCLUDE = auto()           # Do not route (manual or plane layer)

class ZoneDomain(Enum):
    """Electrical domain of a zone or net."""
    HIGH_VOLTAGE = auto()      # >60V, mains-referenced
    LOW_VOLTAGE = auto()       # <60V SELV
    ISOLATED = auto()          # Galvanically isolated (gate drive)
    CONTROL = auto()           # Digital/analog control signals

@dataclass(frozen=True)
class Zone:
    """A physical region on the board with electrical properties."""
    name: str
    domain: ZoneDomain
    polygon: list[tuple[float, float]]  # Boundary vertices (mm)
    clearance_mm: float = 2.0           # Required clearance to other domains

    def contains(self, x: float, y: float) -> bool:
        """Point-in-polygon test."""
        # Ray casting algorithm
        n = len(self.polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = self.polygon[i]
            xj, yj = self.polygon[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def distance_to_boundary(self, x: float, y: float) -> float:
        """Signed distance: negative inside, positive outside."""
        # For gradient-based cost modifiers
        ...

@dataclass
class NetPhysics:
    """Physical attributes of a net (from schematic/netlist)."""
    net_name: str
    current_peak_a: float = 0.0      # Peak current (A)
    current_rms_a: float = 0.0       # RMS current for thermal
    voltage_max_v: float = 3.3       # Maximum voltage on net
    frequency_hz: float = 0.0        # Switching frequency (0 = DC)
    domain: ZoneDomain = ZoneDomain.CONTROL

    # Derived: spatial extent (computed from pin positions)
    bounding_box_area_mm2: float = 0.0
    span_mm: float = 0.0             # Max distance between any two pins

@dataclass
class ZoneConflict:
    """Records a detected zone crossing for explainability."""
    net_name: str
    pin_ref: tuple[str, str]         # (component_ref, pin_name)
    pin_position: tuple[float, float]
    physical_zone: str               # Zone the pin is physically in
    electrical_domain: ZoneDomain    # Domain the net belongs to
    conflict_type: str               # e.g., "LV_PIN_IN_HV_ZONE"

    def __str__(self) -> str:
        return f"{self.net_name}.{self.pin_ref[1]}: {self.conflict_type} at {self.pin_position}"

@dataclass
class CostModifier:
    """Spatial cost modification for pathfinding."""
    # Option 1: Zone-based penalty
    zone_penalties: dict[str, float] = field(default_factory=dict)

    # Option 2: Callable cost field (for gradient boundaries)
    cost_field: Callable[[float, float], float] | None = None

    # Option 3: Pre-computed grid overlay (integrates with MazeRouter)
    cost_grid: Array | None = None

    def get_cost(self, x: float, y: float, base_cost: float = 1.0) -> float:
        """Compute modified cost at position."""
        if self.cost_field is not None:
            return base_cost * self.cost_field(x, y)
        return base_cost

@dataclass
class NetStrategy:
    """Complete routing strategy for a single net."""
    net_name: str
    strategy: RoutingStrategy
    cost_modifier: CostModifier | None = None
    conflicts: list[ZoneConflict] = field(default_factory=list)
    reason: str = ""                  # Human-readable explanation

    def explain(self) -> str:
        """Generate explanation string."""
        lines = [f"Net {self.net_name}: {self.strategy.name}"]
        if self.reason:
            lines.append(f"  Reason: {self.reason}")
        for c in self.conflicts:
            lines.append(f"  Conflict: {c}")
        return "\n".join(lines)

@dataclass
class RoutingContext:
    """Output of the Bridge: complete routing instructions."""
    strategies: dict[str, NetStrategy]
    zones: list[Zone]

    # Nets to exclude from maze routing (handled by planes)
    plane_nets: set[str] = field(default_factory=set)

    def get_strategy(self, net_name: str) -> RoutingStrategy:
        if net_name in self.strategies:
            return self.strategies[net_name].strategy
        return RoutingStrategy.STANDARD_A_STAR

    def get_cost_modifier(self, net_name: str) -> CostModifier | None:
        if net_name in self.strategies:
            return self.strategies[net_name].cost_modifier
        return None

    def summary(self) -> str:
        """Print summary of routing decisions."""
        by_strategy = {}
        for ns in self.strategies.values():
            key = ns.strategy.name
            by_strategy.setdefault(key, []).append(ns.net_name)

        lines = ["Routing Context Summary:"]
        for strat, nets in by_strategy.items():
            lines.append(f"  {strat}: {len(nets)} nets")
        if self.plane_nets:
            lines.append(f"  Plane Nets (excluded): {self.plane_nets}")
        return "\n".join(lines)
```

### 2.2 The Inference Engine (The "Brain")
The Bridge runs a series of **Inference Passes** before routing begins.

#### Logic A: Anomaly Detection (Solving the Orphan Trace)
*   **Goal:** Automatically detect when a trace must skirt a zone boundary.

**Problem with Binary Zone Check:** Real boards have complex zone geometries:
*   Isolation slots create "peninsulas" where LV traces must navigate
*   Components like `LMR51430` straddle zone boundaries
*   Some nets legitimately cross zones (e.g., optocoupler outputs)

**Solution: Gradient-Based Zone Cost Fields**

Instead of binary in/out, compute a **signed distance field** for each zone:
- Negative values = inside zone
- Positive values = outside zone
- Gradient = direction to nearest boundary

```python
def compute_zone_sdf(zone: Zone, grid_resolution_mm: float = 0.5) -> Array:
    """
    Compute signed distance field for a zone.

    Returns a grid where each cell contains the signed distance
    to the nearest zone boundary (negative inside, positive outside).
    """
    # Use existing SDF infrastructure from temper_placer.geometry.sdf
    from temper_placer.geometry.sdf import polygon_sdf

    return polygon_sdf(zone.polygon, grid_resolution_mm)

def compute_zone_cost_field(
    net_domain: ZoneDomain,
    zones: list[Zone],
    board_width: float,
    board_height: float,
    resolution_mm: float = 0.5,
) -> Array:
    """
    Compute cost field for routing a net of given domain.

    High cost inside incompatible zones, low cost elsewhere.
    Uses smooth gradient at boundaries for better optimization.
    """
    width_cells = int(board_width / resolution_mm)
    height_cells = int(board_height / resolution_mm)
    cost = jnp.ones((height_cells, width_cells))

    for zone in zones:
        if not _domains_compatible(net_domain, zone.domain):
            sdf = compute_zone_sdf(zone, resolution_mm)

            # Smooth cost transition at boundary
            # Inside hostile zone: high cost
            # At boundary: medium cost
            # Outside: base cost
            zone_cost = jnp.where(
                sdf < -zone.clearance_mm,  # Deep inside
                10.0,                       # Very high cost
                jnp.where(
                    sdf < 0,                # Inside but near boundary
                    5.0 - 4.0 * (sdf / zone.clearance_mm),  # Gradient
                    1.0                     # Outside
                )
            )
            cost = cost * zone_cost

    return cost

def _domains_compatible(net_domain: ZoneDomain, zone_domain: ZoneDomain) -> bool:
    """Check if net can safely route through zone."""
    # Same domain: always compatible
    if net_domain == zone_domain:
        return True

    # Control/LV can route through each other (same reference)
    if {net_domain, zone_domain} <= {ZoneDomain.CONTROL, ZoneDomain.LOW_VOLTAGE}:
        return True

    # Everything else requires isolation
    return False
```

**Refined Algorithm:**

1.  For each Pin $P$ on Net $N$:
2.  Compute signed distance $d$ to nearest incompatible zone boundary
3.  **IF** $d < 0$ (pin is inside incompatible zone):
    *   Compute gradient $\nabla d$ (direction to boundary)
    *   **Action:** Generate `CostModifier` with zone cost field
    *   **Router Interpretation:** "Cost increases toward zone center. Follow gradient to escape."
4.  **IF** $d < clearance_{required}$ (pin is near boundary):
    *   **Action:** Tag as `EDGE_HUG` with cost field
    *   **Router Interpretation:** "Stay near boundary, don't venture deeper."

**Handling Legitimate Zone Crossings:**

Some components (optocouplers, isolated supplies) legitimately bridge domains:

```python
@dataclass
class IsolationBridge:
    """A component that bridges two electrical domains."""
    component_ref: str
    primary_side_pins: list[str]    # Pins on primary domain
    secondary_side_pins: list[str]  # Pins on secondary domain
    primary_domain: ZoneDomain
    secondary_domain: ZoneDomain

# Example: UCC14140 isolated DC-DC
UCC14140_BRIDGE = IsolationBridge(
    component_ref="U_ISO_DCDC",
    primary_side_pins=["VIN", "GND", "EN"],
    secondary_side_pins=["VOUT", "PGND", "FB"],
    primary_domain=ZoneDomain.LOW_VOLTAGE,
    secondary_domain=ZoneDomain.ISOLATED,
)

def is_legitimate_crossing(net: Net, bridges: list[IsolationBridge]) -> bool:
    """Check if net connects pins across an isolation bridge."""
    for bridge in bridges:
        net_pins = {(ref, pin) for ref, pin in net.pins}
        primary_pins = {(bridge.component_ref, p) for p in bridge.primary_side_pins}
        secondary_pins = {(bridge.component_ref, p) for p in bridge.secondary_side_pins}

        # Net connects primary to secondary through bridge component
        if net_pins & primary_pins and net_pins & secondary_pins:
            return True

    return False
```

**Example Cost Field Visualization:**

```
Board with HV zone (left) and LV zone (right), isolation slot in middle:

Cost field for LV net:
┌─────────────────────────────────────────────────────────────┐
│ 10  10  10  10  │  5   2   1   1   1   1   1   1   1   1   │
│ 10  10  10  10  │  5   2   1   1   1   1   1   1   1   1   │
│ 10  10  10  10  │  5   2   1   1   1   1   1   1   1   1   │
│ 10  10  10  10  │  5   2   1   1   1   1   1   1   1   1   │
│ HIGH VOLTAGE    │ SLOT │        LOW VOLTAGE               │
│ (cost = 10)     │      │        (cost = 1)                │
└─────────────────────────────────────────────────────────────┘
                  ↑ Gradient region (cost 5→2→1)
```

This allows the router to:
- Never enter deep HV zone (cost 10 is prohibitive)
- Route along the slot boundary if needed (cost 5 is possible)
- Prefer LV region strongly (cost 1)

#### Logic B: Plane vs Trace Decision (Multi-Factor)
*   **Goal:** Automatically decide when to flood a plane vs route a trace.
*   **Problem with Simple Thresholding:** A 2A threshold is insufficient:
    *   `+3V3` carries only 0.8A but spans the entire board → needs plane
    *   `GATE_H` carries 3A peak but only 20ns bursts → doesn't need plane
    *   `GND` has 50+ pins → always needs plane regardless of current

**Multi-Factor Decision Matrix:**

```python
def should_use_plane(net: NetPhysics, pin_count: int, board_diagonal_mm: float) -> tuple[bool, str]:
    """
    Decide if net should use plane fill instead of trace routing.

    Returns (should_use_plane, reason).
    """
    # Factor 1: High fanout (many connections)
    if pin_count >= 10:
        return True, f"High fanout ({pin_count} pins)"

    # Factor 2: High sustained current (thermal concern)
    if net.current_rms_a >= 2.0:
        return True, f"High RMS current ({net.current_rms_a}A)"

    # Factor 3: Board-spanning distribution
    span_ratio = net.span_mm / board_diagonal_mm
    if span_ratio >= 0.5 and pin_count >= 5:
        return True, f"Wide distribution ({span_ratio:.0%} of board, {pin_count} pins)"

    # Factor 4: Power net naming convention (fallback heuristic)
    if net.net_name.upper() in ('GND', 'VCC', 'VDD', '+3V3', '+5V', 'PGND', 'AGND'):
        if pin_count >= 3:
            return True, f"Power net convention ({net.net_name})"

    # Factor 5: High peak current with significant duty cycle
    # Burst currents (gate drive) don't need planes
    if net.current_peak_a >= 5.0 and net.frequency_hz < 1e6:  # Not fast switching
        return True, f"High peak DC/low-freq current ({net.current_peak_a}A)"

    return False, "Standard trace routing"
```

**Decision Table (Examples):**

| Net | Peak I | RMS I | Pins | Span | Decision | Reason |
|-----|--------|-------|------|------|----------|--------|
| GND | 40A | 15A | 52 | 140mm | PLANE | High fanout (52 pins) |
| +3V3 | 0.8A | 0.3A | 12 | 120mm | PLANE | High fanout (12 pins) |
| GATE_H | 3A | 0.1A | 2 | 15mm | TRACE | Low fanout, burst current |
| DC_BUS+ | 20A | 12A | 4 | 80mm | PLANE | High RMS current |
| SPI_CLK | 10mA | 5mA | 3 | 45mm | TRACE | Standard signal |

#### Logic C: Spatial Feedback (Closing the Loop)
*   **Goal:** Tell the placer *exactly* where to open a channel.

**Problem with Naive Approach:** A simple inverse-square repulsion field can oscillate:
1. Router fails at $(x_1, y_1)$
2. Placer pushes components away → opens channel at $(x_1, y_1)$
3. But this closes channel at $(x_2, y_2)$ → router fails there
4. Placer pushes components away → reopens $(x_1, y_1)$ failure
5. Repeat forever

**Solution: Damped Feedback with Memory and Bounded Iterations**

```python
@dataclass
class RoutingFailure:
    """Record of a routing failure for feedback."""
    net_name: str
    position: tuple[float, float]   # (x, y) in mm
    epoch: int                       # When failure occurred
    blocking_components: list[str]   # What's in the way

@dataclass
class FeedbackState:
    """State for convergent feedback loop."""
    failures: list[RoutingFailure] = field(default_factory=list)
    epoch: int = 0
    max_epochs: int = 10             # Hard limit on iterations

    # Damping: older failures contribute less
    decay_rate: float = 0.7          # Per-epoch decay

    def add_failure(self, failure: RoutingFailure) -> None:
        self.failures.append(failure)

    def compute_congestion_loss(
        self,
        component_positions: Array,  # (N, 2)
        component_refs: list[str],
    ) -> float:
        """
        Compute congestion loss with damped historical failures.

        Uses exponential decay so recent failures matter more,
        preventing oscillation from chasing old problems.
        """
        if not self.failures:
            return 0.0

        loss = 0.0
        for failure in self.failures:
            # Age-based damping
            age = self.epoch - failure.epoch
            weight = self.decay_rate ** age

            # Skip very old failures (effectively forgotten)
            if weight < 0.01:
                continue

            fx, fy = failure.position

            # Only penalize components that were identified as blockers
            for i, ref in enumerate(component_refs):
                if ref in failure.blocking_components:
                    cx, cy = component_positions[i]
                    dist_sq = (cx - fx)**2 + (cy - fy)**2
                    # Capped inverse-square to prevent infinity at origin
                    loss += weight / max(dist_sq, 1.0)

        return loss

    def should_continue(self, current_failures: int) -> bool:
        """Check if feedback loop should continue."""
        if self.epoch >= self.max_epochs:
            return False  # Hard limit reached
        if current_failures == 0:
            return False  # Success!
        return True

    def get_unresolved_failures(self) -> list[RoutingFailure]:
        """Get failures that haven't been resolved for human review."""
        # Failures that persist across multiple epochs
        persistent = {}
        for f in self.failures:
            key = (f.net_name, round(f.position[0]), round(f.position[1]))
            if key in persistent:
                persistent[key].append(f)
            else:
                persistent[key] = [f]

        # Return failures that occurred in 3+ epochs
        return [fs[-1] for fs in persistent.values() if len(fs) >= 3]
```

**Convergence Strategy:**

1. **Damped Influence:** Older failures decay exponentially (0.7^age), so the system doesn't chase stale problems.

2. **Targeted Repulsion:** Only push components identified as blockers, not everything near the failure.

3. **Bounded Iterations:** Hard limit of 10 epochs. If not converged, report to human.

4. **Memory of Failures:** Track failures across epochs to detect oscillation patterns.

5. **Escape Hatch:** After max_epochs, `get_unresolved_failures()` returns persistent problems for manual review.

**Integration with JAX Optimizer:**

```python
# In placement optimization loop
feedback = FeedbackState(max_epochs=10)

for epoch in range(feedback.max_epochs):
    # 1. Compute standard placement losses
    placement_loss = wirelength_loss + overlap_loss + boundary_loss

    # 2. Add damped congestion feedback
    congestion_loss = feedback.compute_congestion_loss(positions, component_refs)
    total_loss = placement_loss + 0.1 * congestion_loss  # Weighted contribution

    # 3. Optimize placement
    positions = optimizer.step(total_loss)

    # 4. Attempt routing
    routing_result = router.route_all_nets(...)
    failures = [r for r in routing_result.values() if not r.success]

    # 5. Record new failures
    for f in failures:
        feedback.add_failure(RoutingFailure(
            net_name=f.net,
            position=extract_failure_position(f),
            epoch=epoch,
            blocking_components=identify_blockers(f, positions),
        ))

    feedback.epoch += 1

    # 6. Check termination
    if not feedback.should_continue(len(failures)):
        break

# 7. Report unresolved failures
unresolved = feedback.get_unresolved_failures()
if unresolved:
    print("Manual intervention needed:")
    for f in unresolved:
        print(f"  {f.net_name} blocked at {f.position}")
```

## 3. Architecture & Implementation Plan

### Existing Infrastructure (Already Built)

The following modules already exist and will be integrated:

| Module | Location | Reuse |
|--------|----------|-------|
| `MazeRouter` | `routing/maze_router.py` | Core A* implementation. Add `cost_grid` parameter to `find_path`. |
| `CongestionGrid` | `routing/congestion.py` | Grid-based demand/supply. Use for zone cost fields. |
| `LayerAssignment` | `routing/layer_assignment.py` | Net class awareness. Extend with `ZoneDomain`. |
| `strategy.py` | `routing/strategy.py` | Net ordering. Already has `HighVoltage`, `Power`, etc. |
| `polygon_sdf` | `geometry/sdf.py` | SDF computation. Use for gradient zone boundaries. |

### Phase 1: Data Structures and Bridge Core

**Branch:** `feat/physics-hypergraph-routing`
**Effort:** ~3-5 days

1. **Create `routing/bridge/` directory** with:
   - `types.py` - Data structures from Section 2.1.2
   - `zone_detector.py` - Logic A implementation
   - `plane_decider.py` - Logic B implementation
   - `bridge.py` - Main `HypergraphRouterBridge` class

2. **Implement `HypergraphRouterBridge`**:
   ```python
   class HypergraphRouterBridge:
       def __init__(self, zones: list[Zone], bridges: list[IsolationBridge]):
           self.zones = zones
           self.bridges = bridges
           self._cache: dict[str, NetStrategy] = {}

       def analyze(
           self,
           netlist: Netlist,
           positions: Array,
           net_physics: dict[str, NetPhysics],
       ) -> RoutingContext:
           """Compute routing strategies for all nets."""
           ...

       def invalidate_nets(self, moved_components: set[str]) -> None:
           """Clear cached strategies for nets connected to moved components."""
           ...
   ```

3. **Extend `MazeRouter.find_path()`**:
   ```python
   def find_path(
       self,
       start: tuple[int, int],
       end: tuple[int, int],
       layer: int = 0,
       allow_layer_change: bool = False,
       allowed_layers: list[int] | None = None,
       cost_grid: Array | None = None,  # NEW: per-cell cost modifier
   ) -> list[GridCell] | None:
   ```

### Phase 2: Zone Definition for Temper Board

**Branch:** `feat/physics-hypergraph-routing`
**Effort:** ~1-2 days

1. **Define Temper zones in config**:
   ```python
   # config/temper_zones.py
   TEMPER_ZONES = [
       Zone(
           name="HV_ZONE_A",
           domain=ZoneDomain.HIGH_VOLTAGE,
           polygon=[(0, 0), (50, 0), (50, 150), (0, 150)],  # Left side
           clearance_mm=8.0,  # IEC 60335-2-6 reinforced
       ),
       Zone(
           name="LV_ZONE_D",
           domain=ZoneDomain.CONTROL,
           polygon=[(60, 0), (100, 0), (100, 150), (60, 150)],  # Right side
           clearance_mm=2.0,
       ),
       # ... etc
   ]

   TEMPER_BRIDGES = [
       IsolationBridge(
           component_ref="U_GD",  # UCC21550
           primary_side_pins=["INA", "INB", "VDD", "GND"],
           secondary_side_pins=["VDDA", "GNDA", "OUTA", "VDDB", "GNDB", "OUTB"],
           primary_domain=ZoneDomain.CONTROL,
           secondary_domain=ZoneDomain.ISOLATED,
       ),
   ]
   ```

2. **Extract `NetPhysics` from net class annotations**:
   ```python
   def net_physics_from_netlist(netlist: Netlist) -> dict[str, NetPhysics]:
       """Derive NetPhysics from existing net_class annotations."""
       result = {}
       for net in netlist.nets:
           domain = {
               "HighVoltage": ZoneDomain.HIGH_VOLTAGE,
               "Power": ZoneDomain.LOW_VOLTAGE,
               "GateDrive": ZoneDomain.ISOLATED,
               "Signal": ZoneDomain.CONTROL,
           }.get(net.net_class, ZoneDomain.CONTROL)

           result[net.name] = NetPhysics(
               net_name=net.name,
               domain=domain,
               # TODO: Import current from schematic annotations
           )
       return result
   ```

### Phase 3: Integration and Verification

**Branch:** `feat/physics-hypergraph-routing`
**Effort:** ~2-3 days

1. **Unit tests for Bridge logic**:
   - `test_zone_detector.py`: Zone conflict detection
   - `test_plane_decider.py`: Multi-factor plane decision
   - `test_bridge.py`: Full pipeline

2. **Integration test with Temper board**:
   ```python
   def test_temper_gnd_routing():
       """Verify GND net from J_AC_IN gets EDGE_HUG strategy."""
       bridge = HypergraphRouterBridge(TEMPER_ZONES, TEMPER_BRIDGES)
       context = bridge.analyze(temper_netlist, positions, net_physics)

       gnd_strategy = context.get_strategy("GND")
       assert gnd_strategy == RoutingStrategy.FLOOD_FILL  # High fanout

       # Pin on J_AC_IN should have conflict detected
       conflicts = context.strategies["GND"].conflicts
       assert any(c.pin_ref[0] == "J_AC_IN" for c in conflicts)
   ```

3. **Benchmark against FreeRouting baseline**:
   - Run `experiment_tracker.py` with Bridge-guided DSN export
   - Compare completion %, via count, wirelength

### Phase 4: Feedback Loop (Deferred)

**Branch:** `feat/routing-feedback-loop`
**Effort:** ~1 week
**Risk:** Medium (requires convergence tuning)

Only implement after Phases 1-3 are validated:

1. **Implement `FeedbackState`** from Section 2.2 (Logic C)
2. **Integrate with JAX optimizer loop**
3. **Add oscillation detection and damping**
4. **Validate convergence on test cases**

**Decision Point:** If Phase 3 achieves 100% routing without feedback loop, consider deferring Phase 4 indefinitely.

## 4. Risk Mitigation

### Identified Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Feedback loop oscillation** | High | Damped influence with decay_rate=0.7, bounded iterations (max 10), escape hatch for human review |
| **Zone model too coarse** | Medium | Gradient-based SDF instead of binary membership; IsolationBridge for legitimate crossings |
| **Plane decision wrong** | Medium | Multi-factor decision matrix; unit tests with known cases; override mechanism |
| **Performance (recompute every epoch)** | Low | Incremental updates: only recompute nets on moved components |
| **FreeRouting benchmark diverges from custom router** | Low | FreeRouting is benchmark only; custom MazeRouter is source of truth |

### Open Questions

1. **Current/Voltage Annotation Source:** Where do we get `current_peak_a`, `voltage_max_v` for each net?
   - **Option A:** Manual annotation in schematic (tedious but accurate)
   - **Option B:** Infer from net class heuristically (easy but approximate)
   - **Option C:** Parse from simulation results (accurate but requires sim infrastructure)
   - **Recommendation:** Start with Option B, add Option A for critical nets

2. **Zone Polygon Source:** How are zones defined?
   - **Option A:** Manual definition in config file (per-board, flexible)
   - **Option B:** Derive from KiCad keepout areas (automatic but limited)
   - **Option C:** Infer from component placement domains (automatic but fragile)
   - **Recommendation:** Option A for v1, explore Option B later

3. **When to Route vs When to Plan:** Should routing happen every placement epoch?
   - Full routing is expensive (~seconds per attempt)
   - Consider: route only on "major" placement changes (movement > 5mm)
   - Or: route only at end of placement optimization

4. **How to Handle "Impossible" Boards:** What if placement makes routing impossible?
   - Current plan: report unresolved failures for human review
   - Future: automatically backtrack placement or suggest component swap

## 5. Why This is Scalable

This system scales because it relies on **First Principles**, not heuristics.
*   **Testability:** The Bridge logic can be unit-tested in isolation (e.g., "Does 40A yield FLOOD_FILL?").
*   **Generality:** It works for any board shape, component, or stackup.
*   **Explainability:** The system can report: *"Routed Net GND via edge because it entered High Voltage Zone."*
*   **Reusability:** Zone definitions and IsolationBridges can be templated for common board types.

We are moving from "Scripting the Router" to "Teaching the Router Physics."

## 6. Changelog

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-XX | Initial | Original design proposal |
| 2025-12-28 | Claude (critic review) | Added: concrete data structures (Section 2.1.2), multi-factor plane decision (Logic B), gradient zone model (Logic A), damped feedback loop with convergence (Logic C), existing infrastructure mapping, risk mitigations, open questions |