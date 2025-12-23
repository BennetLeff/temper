# Layer-Aware Placement and Routing Architecture

## Overview

This document describes a comprehensive approach to integrating layer stackup awareness throughout the placement and routing pipeline.

## Current State (Pre-Integration)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Optimizer  │───▶│   Router    │───▶│   Export    │
│ (placement) │    │ (maze A*)   │    │  (KiCad)    │
└─────────────┘    └─────────────┘    └─────────────┘
       │                  │
       ▼                  ▼
   No layer           No layer
   awareness          awareness
```

**Problems:**
1. Optimizer assumes infinite routing capacity on all layers
2. Router can route signals on power/ground planes
3. No enforcement of HV-only layers
4. Ground plane splits not considered

## Target State (Layer-Aware)

```
┌─────────────────────────────────────────────────────┐
│                   LayerStackup                       │
│  ┌───────────────────────────────────────────────┐  │
│  │ L1 (F.Cu):   signal, 2oz, is_routable=True   │  │
│  │ L2 (In1.Cu): plane,  1oz, is_routable=False  │  │
│  │ L3 (In2.Cu): plane,  1oz, is_routable=False  │  │
│  │ L4 (B.Cu):   signal, 1oz, is_routable=True   │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                        │
      ┌─────────────────┼─────────────────┐
      ▼                 ▼                 ▼
┌───────────┐    ┌────────────┐    ┌────────────┐
│ Optimizer │◀──▶│   Router   │───▶│   Export   │
│           │    │            │    │            │
│ - RHWL    │    │ - Layer    │    │ - Layer    │
│   uses    │    │   routing  │    │   mapping  │
│   routable│    │   respects │    │   correct  │
│   layers  │    │   is_rout. │    │            │
└───────────┘    └────────────┘    └────────────┘
```

## Integration Points

### 1. Optimizer: Layer-Aware Wirelength Estimation

**Where:** `losses/wirelength.py`, `losses/routability.py`

**What:**
- Use `LayerStackup.routable_layers(net_class)` to determine available layers
- Adjust RHWL (Routed Half-Perimeter Wirelength) estimates based on layer count
- Penalize placements that require more routing layers than available

**Implementation:**
```python
def compute_rhwl(positions, netlist, layer_stackup: LayerStackup):
    for net in netlist.nets:
        # Get net class (HV, Power, Signal)
        net_class = netlist.get_net_class(net.name)
        
        # Get available layers for this net class
        available_layers = layer_stackup.routable_layers(net_class)
        
        # Adjust wirelength estimate based on layer count
        # More layers = more routing capacity = lower congestion
        layer_factor = 1.0 / len(available_layers)
        
        # Compute RHWL with layer adjustment
        rhwl = compute_half_perimeter(net, positions) * layer_factor
```

### 2. Optimizer: Routability Loss

**Where:** `losses/routability.py`

**What:**
- Estimate routing feasibility during placement optimization
- Use layer-aware routing capacity estimation
- Feedback loop: penalize placements that create unroutable regions

**Implementation:**
```python
def routability_loss(positions, netlist, board, layer_stackup):
    # Compute routing demand per grid cell
    demand = estimate_routing_demand(positions, netlist)
    
    # Compute routing capacity per grid cell (layer-aware)
    capacity = layer_stackup.tracks_per_cell(grid_size=1.0, net_class="Signal")
    
    # Overflow = demand - capacity (penalize)
    overflow = jnp.maximum(0, demand - capacity)
    
    return jnp.sum(overflow)
```

### 3. Router: Layer-Aware Pathfinding

**Where:** `routing/maze_router.py`

**What:**
- Block non-routable layers (power/ground planes)
- Route different net classes on appropriate layers
- Respect copper weight requirements (HV on L1)

**Implementation:**
```python
class MazeRouter:
    def __init__(self, ..., layer_stackup: LayerStackup | None = None):
        self.layer_stackup = layer_stackup
        
        # Pre-compute which layers are routable
        if layer_stackup:
            self.routable_mask = jnp.array([
                layer.is_routable for layer in layer_stackup.layers
            ])
        else:
            self.routable_mask = jnp.ones(num_layers, dtype=bool)
    
    def _get_neighbors(self, cell, allow_layer_change=False):
        neighbors = []
        
        # Check if current layer is routable
        if not self.routable_mask[cell.layer]:
            return []  # Can't route on power/ground planes
        
        # ... rest of neighbor logic
        
    def route_net(self, net_name, net_class="Signal"):
        # Get allowed layers for this net class
        if self.layer_stackup:
            allowed_layers = self.layer_stackup.routable_layers(net_class)
        else:
            allowed_layers = list(range(self.num_layers))
        
        # Only start routing from allowed layers
        # Modify find_path to respect layer constraints
        ...
```

### 4. Ground Plane Preservation

**Critical for EMI performance!**

**What:**
- Ground plane (L2) should remain unbroken
- Only allow vias to pierce ground plane, no traces
- Route signals on L1 and L4, via through L2/L3

**Implementation:**
```python
class LayerStackup:
    def is_plane_layer(self, layer_idx: int) -> bool:
        return self.layers[layer_idx].layer_type == "plane"
    
    def get_via_target_layers(self) -> list[tuple[int, int]]:
        """Return valid via transitions that respect planes."""
        # For 4-layer: L1↔L4 via goes through L2, L3 (OK)
        # No traces on L2 or L3
        routable = self.routable_layers()
        return [(a, b) for a in routable for b in routable if a != b]
```

### 5. HV Trace Routing

**What:**
- High-voltage traces require 2oz copper (L1 only on Temper board)
- HV traces must not route on L4 (1oz copper)
- Clearance requirements around HV nets

**Implementation:**
```python
def route_hv_net(self, net_name):
    # Force routing on L1 only
    if self.layer_stackup:
        hv_layers = [i for i, layer in enumerate(self.layer_stackup.layers)
                     if layer.copper_weight >= 2.0]
    else:
        hv_layers = [0]  # Default: top layer only
    
    return self.find_path(..., allowed_layers=hv_layers)
```

## Testing Strategy

### Unit Tests

1. **Router Layer Masking:**
   ```python
   def test_router_blocks_power_plane():
       stackup = LayerStackup.default_4layer()
       router = MazeRouter(..., layer_stackup=stackup)
       
       # Try to route on L2 (ground plane)
       path = router.find_path(start, end, layer=1)  # L2 = In1.Cu
       
       assert path is None, "Should not route on ground plane"
   ```

2. **Router Net Class Awareness:**
   ```python
   def test_hv_routes_only_on_l1():
       stackup = LayerStackup.default_4layer()
       router = MazeRouter(..., layer_stackup=stackup)
       
       path = router.route_net("HV_BUS", net_class="HighVoltage")
       
       for cell in path:
           assert cell.layer == 0, "HV must stay on L1"
   ```

3. **Optimizer Layer Factor:**
   ```python
   def test_rhwl_uses_layer_count():
       stackup_2layer = LayerStackup(layers=[signal, signal], ...)
       stackup_4layer = LayerStackup(layers=[signal, gnd, pwr, signal], ...)
       
       # 4-layer has 2 routable, 2-layer has 2 routable
       # Same capacity, should get similar wirelength
       rhwl_2 = compute_rhwl(positions, netlist, stackup_2layer)
       rhwl_4 = compute_rhwl(positions, netlist, stackup_4layer)
       
       assert abs(rhwl_2 - rhwl_4) < tolerance
   ```

### Integration Tests

1. **End-to-End Layer Awareness:**
   ```python
   def test_placement_respects_routing_layers():
       # Run optimizer with 4-layer stackup
       placement = optimize(netlist, board, stackup_4layer)
       
       # Route placement
       router = MazeRouter.from_placement(placement, stackup_4layer)
       results = router.route_all_nets(netlist)
       
       # Verify no routing on power/ground planes
       for net, path in results.items():
           for cell in path:
               layer = stackup_4layer.layers[cell.layer]
               assert layer.is_routable, f"Net {net} routed on non-routable layer"
   ```

2. **Optimizer-Router Consistency:**
   ```python
   def test_optimizer_estimates_match_router():
       # Get optimizer's wirelength estimate
       estimated = optimizer.estimate_wirelength(placement, stackup)
       
       # Get actual routed wirelength
       actual = router.route_all_and_measure(placement, stackup)
       
       # Estimate should be within 20% of actual
       assert abs(estimated - actual) / actual < 0.2
   ```

## Implementation Tasks

### Phase 1: Router Integration (P1)

1. [ ] Add `layer_stackup` parameter to `MazeRouter.__init__()`
2. [ ] Implement routable layer masking in `_get_neighbors()`
3. [ ] Add `route_net(net_name, net_class)` method
4. [ ] Add tests for layer blocking and net class routing

### Phase 2: Optimizer Integration (P2)

1. [ ] Modify `compute_rhwl()` to use layer count
2. [ ] Add layer-aware `routability_loss()`
3. [ ] Update `LossConfig` to include `layer_stackup`
4. [ ] Add tests for layer-aware wirelength estimation

### Phase 3: Ground Plane Preservation (P2)

1. [ ] Implement via-only policy for plane layers
2. [ ] Add ground plane integrity metric
3. [ ] Add visualization for ground plane continuity
4. [ ] Add tests for ground plane preservation

### Phase 4: HV Routing (P3)

1. [ ] Implement copper weight checking
2. [ ] Add HV clearance requirements
3. [ ] Add HV-specific routing tests
4. [ ] Update PCL to support HV net class specification

## Risks and Mitigations

### Risk 1: Optimizer-Router Mismatch

**Problem:** Optimizer estimates wirelength differently than router calculates.

**Mitigation:**
- Use same `LayerStackup` object everywhere
- Unit tests to verify consistency
- Periodic router feedback during optimization (curriculum learning)

### Risk 2: Performance Impact

**Problem:** Layer checks add overhead to pathfinding.

**Mitigation:**
- Pre-compute routable layer mask once
- Use JAX boolean indexing (vectorized)
- Cache layer lookups

### Risk 3: Ground Plane Splits

**Problem:** Too many vias can split ground plane, degrading EMI.

**Mitigation:**
- Via clustering metric (prefer vias near existing vias)
- Ground plane continuity loss
- Visual ground plane rendering

## Next Steps

1. Upgrade task `temper-xttl` to an Epic with subtasks
2. Start with Phase 1 (router integration)
3. Add tests before implementation (TDD)
4. Integrate incrementally, testing at each step
