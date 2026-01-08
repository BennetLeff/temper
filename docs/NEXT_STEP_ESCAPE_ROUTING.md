# Next Step: Make Router Escape-Via Aware (temper-f4yg)

## Current Status

### ✅ What Works
- `FinePitchEscapeStage` successfully places 28 escape vias for 4 fine-pitch components
- Escape vias connect F.Cu (Layer 0) to In1.Cu (Layer 1)
- Detection working: U_MCU (0.40mm), J_USB (0.40mm), U_CT (0.65mm), MAX31865 (0.65mm)

### ❌ What's Broken
- Router still tries to route from F.Cu (Layer 0) where clearances conflict
- PWM_H, PWM_L, SPI_MOSI, SPI_MISO, GATE_H, GATE_L still fail to route
- Router doesn't know escape vias exist

## Problem

`SequentialRoutingStage` builds `pin_positions` directly from component pad locations:

```python
# Line 815-831 in sequential_routing.py
pin_positions = []
for comp_ref, pin_name in net.pins:
    comp = comp_by_ref[comp_ref]
    pin = next((p for p in comp.pins if p.name == pin_name), None)
    pos = comp.initial_position or (0, 0)
    pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
    pin_positions.append(pin_pos)  # ← Always uses F.Cu pad position
```

**Issue**: This always uses the pad position on F.Cu (Layer 0), even when an escape via exists at that position connecting to Layer 1.

## Solution

Modify `SequentialRoutingStage` to:
1. Check if escape via exists at pin position
2. If yes, use escape via's target layer (Layer 1) as routing start point
3. Pass layer information to A* router

## Implementation Plan

### Step 1: Add escape via lookup method (NEW METHOD)

Add after `__init__` method (~line 100):

```python
def _get_escape_via_for_pin(self, pin_pos: Tuple[float, float], net_name: str, state: BoardState) -> Tuple[Optional[int], Tuple[float, float]]:
    """Check if an escape via exists at this pin position.
    
    Args:
        pin_pos: (x, y) position of pin on component
        net_name: Net name to match
        state: Current board state with vias
    
    Returns:
        (escape_layer_idx, via_position) if escape via found
        (None, pin_pos) if no escape via at this position
    """
    if not state.vias:
        return (None, pin_pos)
    
    for via in state.vias:
        if via.net != net_name:
            continue
        
        # Check if via is at pin position (within 0.01mm tolerance for floating point)
        dx = via.position[0] - pin_pos[0]
        dy = via.position[1] - pin_pos[1]
        dist = (dx*dx + dy*dy)**0.5
        
        if dist < 0.01:  # Via is at pin
            # Determine escape layer from via.layers tuple
            # Escape vias connect F.Cu (0) -> In1.Cu (1)
            if "In1.Cu" in via.layers or 1 in via.layers:
                return (1, via.position)  # Escape to Layer 1
            elif "In2.Cu" in via.layers or 2 in via.layers:
                return (2, via.position)  # Escape to Layer 2
    
    return (None, pin_pos)  # No escape via found
```

### Step 2: Track escape layers when building pin_positions

Modify around line 815-831:

**BEFORE:**
```python
pin_positions = []
pin_info = []
pins = []
for comp_ref, pin_name in net.pins:
    ...
    pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
    pin_positions.append(pin_pos)
    pin_info.append((comp_ref, pin.name))
    pins.append(pin)
```

**AFTER:**
```python
pin_positions = []
pin_info = []
pins = []
pin_escape_layers = []  # NEW: Track which layer each pin escapes to
for comp_ref, pin_name in net.pins:
    ...
    pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
    
    # NEW: Check for escape via at this pin
    escape_layer, final_pos = self._get_escape_via_for_pin(pin_pos, net_name, state)
    
    pin_positions.append(final_pos)
    pin_info.append((comp_ref, pin.name))
    pins.append(pin)
    pin_escape_layers.append(escape_layer)  # NEW: None or layer index
    
    # NEW: Debug output
    if escape_layer is not None:
        print(f"    Using escape via for {net_name}.{comp_ref}.{pin.name} at {final_pos} on Layer {escape_layer}")
```

### Step 3: Pass layer hints to MultiLayerAStar

Find where A* is called (~line 1040-1070). Currently:

```python
path = astar.find_path(
    snapped_positions[idx1],
    snapped_positions[idx2],
    obstacles_with_clearance,
)
```

Modify to pass start/end layer hints:

```python
# NEW: Get escape layers for these endpoints
start_layer = pin_escape_layers[idx1] if pin_escape_layers[idx1] is not None else 0
end_layer = pin_escape_layers[idx2] if pin_escape_layers[idx2] is not None else 0

path = astar.find_path(
    snapped_positions[idx1],
    snapped_positions[idx2],
    obstacles_with_clearance,
    start_layer=start_layer,  # NEW
    end_layer=end_layer,      # NEW
)
```

### Step 4: Update MultiLayerAStar.find_path signature

**File**: `packages/temper-placer/src/temper_placer/deterministic/stages/multilayer_astar.py`

Add optional parameters to `find_path`:

```python
def find_path(
    self,
    start: Tuple[float, float],
    goal: Tuple[float, float],
    obstacles: List[Tuple[Tuple[float, float], float, int]],
    start_layer: Optional[int] = None,  # NEW: Layer hint for start
    end_layer: Optional[int] = None,    # NEW: Layer hint for end
) -> MultiLayerPath | None:
```

Then use these hints:
```python
if start_layer is not None:
    start_node = (start_x, start_y, start_layer)  # Force start layer
else:
    start_node = (start_x, start_y, 0)  # Default to F.Cu

if end_layer is not None:
    end_node = (end_x, end_y, end_layer)  # Force end layer
else:
    end_node = (end_x, end_y, 0)  # Default to F.Cu
```

## Testing

After implementation, run:

```bash
python3.11 scripts/profile_pipeline.py 2>&1 | tee /tmp/pipeline_test.log
```

**Expected output:**
```
[Stage 14/21] fine_pitch_escape
  Fine-pitch components detected: 4
  Placed 28 escape vias to Layer 1 (In1.Cu)

[Stage 15/21] sequential_routing
  Routing net 12/24: PWM_H...
    Using escape via for PWM_H.U_GATE.2 at (14.3, 31.8) on Layer 1
    Using escape via for PWM_H.U_MCU.13 at (76.5, 3.7) on Layer 1
  INFO: Multi-layer route found for PWM_H (X/Y iters, Z vias)
      ✓ PWM_H routed in X.XXs [LOCKED]
```

**Success criteria:**
- PWM_H, PWM_L successfully routed
- SPI_MOSI, SPI_MISO successfully routed
- GATE_H, GATE_L successfully routed
- No more "Could not find any path" warnings for these nets

## Files to Modify

1. **`packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`**
   - Add `_get_escape_via_for_pin()` method
   - Modify pin_positions building to track escape layers
   - Pass layer hints to A* calls

2. **`packages/temper-placer/src/temper_placer/deterministic/stages/multilayer_astar.py`**
   - Add `start_layer` and `end_layer` parameters to `find_path()`
   - Use hints when building start/end nodes

## Beads Issues

- **temper-vo3r** (P1): Implement FinePitchEscapeStage ✅ DONE
- **temper-f4yg** (P1): Update SequentialRoutingStage ← THIS TASK
- **temper-23lo** (P2): Test and validate

## Commit Message Template

```
feat: make SequentialRoutingStage aware of escape vias

- Add _get_escape_via_for_pin() to detect escape vias at pin positions
- Track escape layers (pin_escape_layers) when building routing terminals
- Pass start_layer/end_layer hints to MultiLayerAStar.find_path()
- Update MultiLayerAStar to accept and use layer hints

Now PWM_H, PWM_L, SPI_MOSI, SPI_MISO, GATE_H, GATE_L route successfully
by starting from Layer 1 (In1.Cu) where clearances don't conflict.

Completes temper-f4yg: Update router to use escape vias
```
