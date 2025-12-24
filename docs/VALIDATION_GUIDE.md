# Validation Guide: How to Test New Features

This guide shows you how to validate the two major systems implemented in this session.

---

## 1. Functional Explainability System

### Quick Validation

```bash
cd packages/temper-placer
uv run pytest tests/explainability/ -v
```

**Expected:** 68/68 tests passing ✅

### Manual Testing

#### Test 1: Basic Trace Usage
```python
from temper_placer.explainability import Trace

# Create and compose traces
trace = Trace.empty()
trace = trace.add("Q1", (45.2, 12.3), "Minimize commutation loop")
trace = trace.add("Q1", (43.8, 11.9), "Thermal edge constraint")

# Query
print(trace.why("Q1"))
# Should show both reasons
```

#### Test 2: Traced Loss with PCL
```python
from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier
from temper_placer.explainability.traced_loss import constraint_to_traced_loss

# Create constraint
constraint = AdjacentConstraint(
    a="Q1", b="Q2",
    max_distance_mm=15,
    tier=ConstraintTier.HARD,
    because="Minimize commutation loop for half-bridge"
)

# Mock loss function
def compute_loss(c, positions):
    return 10.0  # Mock value

# Create traced function
traced_fn = constraint_to_traced_loss(constraint, compute_loss)
loss, trace = traced_fn(None)

print(trace.why("Q1"))
# Should show: "Minimize commutation loop for half-bridge"
```

#### Test 3: Traced Routing
```python
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.traced_routing import route_all_with_trace

router = MazeRouter(grid_size=(100, 100), num_layers=2)

net_routes = [
    ("VCC", (10, 10), (90, 90)),
    ("GND", (20, 20), (80, 80)),
]

routes, trace = route_all_with_trace(router, net_routes, allow_layer_change=True)

print(trace.why("VCC"))
print(trace.why("GND"))
# Should show routing decisions
```

#### Test 4: Pipeline Composition
```python
from temper_placer.explainability.pipeline import TracedPipeline

def placement(data):
    trace = Trace.empty().add("Q1", (10, 20), "Placed for wirelength")
    return "positions", trace

def routing(positions):
    trace = Trace.empty().add("VCC", "path", "Routed on L1")
    return "routes", trace

pipeline = TracedPipeline()
pipeline.add_stage("placement", placement)
pipeline.add_stage("routing", routing)

result, trace = pipeline.run("input")

print(trace.why("Q1"))   # Placement decision
print(trace.why("VCC"))  # Routing decision
```

---

## 2. Layer-Aware Routing

### Quick Validation

```bash
cd packages/temper-placer
uv run pytest tests/routing/test_layer_stackup_integration.py -v
```

**Expected:** 12/12 tests passing ✅

### Manual Testing

#### Test 1: Default Layer Stackup
```python
from temper_placer.routing.maze_router import MazeRouter

router = MazeRouter(grid_size=(100, 100), num_layers=4)

# Check default stackup
print(router.layer_stackup.layers)
# Should show 4 layers: L1 (signal), L2 (plane), L3 (plane), L4 (signal)

# Check routable layers
print(router.layer_stackup.routable_layers("Signal"))
# Should show: [0, 3] (L1 and L4 only)
```

#### Test 2: HV Net Routing (L1 Only)
```python
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.board import LayerStackup

stackup = LayerStackup.default_4layer()
router = MazeRouter(grid_size=(100, 100), num_layers=4, layer_stackup=stackup)

# Get HV allowed layers
hv_layers = stackup.routable_layers("HighVoltage")
print(f"HV allowed layers: {hv_layers}")  # Should be [0] only

# Route HV net
path = router.find_path(
    start=(10, 10),
    end=(50, 50),
    layer=0,
    allowed_layers=hv_layers
)

# Verify all cells are on L1
if path:
    layers_used = set(cell.layer for cell in path)
    print(f"Layers used: {layers_used}")  # Should be {0} only
    assert layers_used == {0}, "HV net used wrong layers!"
```

#### Test 3: Signal Net Avoids Planes
```python
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.board import LayerStackup

stackup = LayerStackup.default_4layer()
router = MazeRouter(grid_size=(100, 100), num_layers=4, layer_stackup=stackup)

# Get signal allowed layers
signal_layers = stackup.routable_layers("Signal")
print(f"Signal allowed layers: {signal_layers}")  # Should be [0, 3]

# Route signal net
path = router.find_path(
    start=(10, 10),
    end=(90, 90),
    layer=0,
    allow_layer_change=True,
    allowed_layers=signal_layers
)

# Verify no plane layers used
if path:
    layers_used = set(cell.layer for cell in path)
    print(f"Layers used: {layers_used}")  # Should NOT include 1 or 2
    assert 1 not in layers_used, "Signal net used GND plane!"
    assert 2 not in layers_used, "Signal net used PWR plane!"
```

#### Test 4: Mixed Net Classes
```python
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.board import LayerStackup

stackup = LayerStackup.default_4layer()
router = MazeRouter(grid_size=(100, 100), num_layers=4, layer_stackup=stackup)

# Route HV net
hv_path = router.find_path(
    start=(10, 10), end=(30, 10), layer=0,
    allowed_layers=stackup.routable_layers("HighVoltage")
)
print(f"HV path uses layers: {set(c.layer for c in hv_path)}")

# Mark as routed
for cell in hv_path:
    router.occupancy = router.occupancy.at[cell.x, cell.y, cell.layer].set(2)

# Route Power net
power_path = router.find_path(
    start=(40, 10), end=(60, 10), layer=0,
    allow_layer_change=True,
    allowed_layers=stackup.routable_layers("Power")
)
print(f"Power path uses layers: {set(c.layer for c in power_path)}")

# Route Signal net
signal_path = router.find_path(
    start=(70, 10), end=(90, 10), layer=0,
    allow_layer_change=True,
    allowed_layers=stackup.routable_layers("Signal")
)
print(f"Signal path uses layers: {set(c.layer for c in signal_path)}")
```

---

## 3. Backward Compatibility

### Verify No Regressions

```bash
cd packages/temper-placer

# Run all existing router tests
uv run pytest tests/routing/test_maze_router_oracles.py tests/routing/test_real_world_scenarios.py -v
```

**Expected:** 23/23 tests passing ✅

### Verify Old Code Still Works

```python
from temper_placer.routing.maze_router import MazeRouter

# Old-style usage (no layer_stackup, no allowed_layers)
router = MazeRouter(grid_size=(100, 100), num_layers=2)

path = router.find_path(
    start=(10, 10),
    end=(50, 50),
    layer=0,
    allow_layer_change=True
)

assert path is not None, "Old-style routing should still work!"
```

---

## 4. Full Integration Test

### End-to-End Validation

```python
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.board import LayerStackup
from temper_placer.routing.traced_routing import route_all_with_trace
from temper_placer.explainability import Trace

# Create router with layer stackup
stackup = LayerStackup.default_4layer()
router = MazeRouter(grid_size=(100, 100), num_layers=4, layer_stackup=stackup)

# Define nets with different classes
nets = [
    ("HV_BUS", (10, 10), (30, 10)),      # HV net
    ("VCC", (40, 10), (60, 10)),         # Power net
    ("SIG_CLK", (70, 10), (90, 10)),     # Signal net
]

# Route each with appropriate restrictions
all_traces = Trace.empty()

for net_name, start, end in nets:
    # Determine net class from name
    if "HV" in net_name:
        net_class = "HighVoltage"
    elif "VCC" in net_name or "GND" in net_name:
        net_class = "Power"
    else:
        net_class = "Signal"
    
    # Get allowed layers
    allowed_layers = stackup.routable_layers(net_class)
    
    # Route
    path = router.find_path(
        start=start, end=end, layer=0,
        allow_layer_change=(net_class != "HighVoltage"),
        allowed_layers=allowed_layers
    )
    
    if path:
        print(f"{net_name} ({net_class}): {len(path)} cells, layers {set(c.layer for c in path)}")
        
        # Create trace entry
        trace = Trace.empty().add(
            net_name,
            len(path),
            f"{net_class} net routed on layers {allowed_layers}"
        )
        all_traces = all_traces + trace

# Query combined trace
print("\nExplanations:")
for net_name, _, _ in nets:
    print(all_traces.why(net_name))
```

---

## Expected Results Summary

### Explainability System
- ✅ 68/68 tests passing
- ✅ Traces compose via `+` operator
- ✅ `why()` generates natural language
- ✅ PCL `because` fields propagate

### Layer-Aware Routing
- ✅ 12/12 new tests passing
- ✅ 23/23 existing tests passing
- ✅ HV nets route only on L1
- ✅ Signal/Power nets avoid planes (L2/L3)
- ✅ Backward compatible

### Total
**103/103 tests passing** across both systems ✅
