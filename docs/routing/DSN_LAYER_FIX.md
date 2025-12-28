# DSN Export Layer Fix

## Problem Summary

The DSN exporter was producing files that Freerouting could only route to ~19% completion. Investigation revealed two critical bugs in the layer handling.

## Root Causes

### 1. Through-Hole Pads Missing Multi-Layer Padstacks

**Location**: `packages/temper-placer/src/temper_placer/io/kicad_parser.py`

**Issue**: When parsing KiCad PCB files, through-hole (THT) pads were being assigned `layer="F.Cu"` instead of `layer="all"`. This meant the DSN exporter created padstacks with shapes only on F.Cu, preventing the router from using vias to connect to THT components on other layers.

**Before** (broken):
```python
raw_pins.append({
    "name": pad.number or "",
    "number": pad.number or "",
    "position": (local_x, local_y),
    "net": pad.net.name if pad.net else None,
})
# Pin created with default layer="F.Cu"
```

**After** (fixed):
```python
# Detect THT pads by checking for "*.Cu" in layers list
pad_layers = pad.layers if hasattr(pad, 'layers') and pad.layers else ["F.Cu"]
is_through_hole = any("*.Cu" in layer or layer == "*.Cu" for layer in pad_layers)

layer = "all" if is_through_hole else copper_layers[0]

raw_pins.append({
    ...
    "width": pad_width,
    "height": pad_height,
    "shape": pad_shape,
    "layer": layer,  # Now correctly set to "all" for THT
})
```

### 2. Inner Layers Marked as "Power" Type

**Location**: `packages/temper-placer/src/temper_placer/io/dsn_exporter.py`

**Issue**: The structure export was marking inner layers (In1.Cu, In2.Cu) with `(type power)`, which tells Freerouting these layers can only be used for power plane connections, not signal routing.

**Before** (broken):
```
(layer In1.Cu (type power) (property (index 1)))
(layer In2.Cu (type power) (property (index 2)))
```

**After** (fixed):
```
(layer In1.Cu (type signal) (property (index 1)))
(layer In2.Cu (type signal) (property (index 2)))
```

The fix adds an `all_layers_signal` parameter (default `True`) to `export_structure()`:

```python
def export_structure(self, all_layers_signal: bool = True) -> DSNExpression:
    if all_layers_signal:
        ltype = "signal"  # Allow signal routing on all layers
    else:
        ltype = "signal" if layer.layer_type == "signal" else "power"
```

## Impact

| Metric | Before Fix | After Fix |
|--------|------------|-----------|
| Routed connections | 16/84 | 81/84 |
| Completion rate | 19% | **96.4%** |
| Vias used | 0 | 15 |
| Wire segments | ~16 | 184 |

## Verification

The fix was validated by:

1. Re-exporting a DSN from `pcb/temper_boundary_fixed.kicad_pcb`
2. Checking padstack definitions contain all 4 copper layers:
   ```
   (padstack PS_CIRCLE_3_500x3_500_ALL
     (shape (circle F.Cu 350))
     (shape (circle In1.Cu 350))
     (shape (circle In2.Cu 350))
     (shape (circle B.Cu 350)))
   ```
3. Running Freerouting for 596 passes, achieving 96.4% completion

## Files Modified

- `packages/temper-placer/src/temper_placer/io/kicad_parser.py`
  - Added THT pad detection via `*.Cu` layer pattern
  - Extract pad width, height, shape, and layer into Pin objects

- `packages/temper-placer/src/temper_placer/io/dsn_exporter.py`
  - Added `all_layers_signal` parameter to `export_structure()`
  - Default behavior now marks all layers as signal type

## Remaining Issues

3-4 connections remain unrouted, all within the GND net which spans 141mm vertically (22 pins from Y=5mm to Y=146mm).

### GND Net Gap Analysis

The GND net has significant vertical gaps with no intermediate connections:

| Gap | From Component | To Component |
|-----|----------------|--------------|
| 52.2mm | U_OPAMP_CT-4 (Y=86mm) | J_NTC-2 (Y=138mm) |
| 32.8mm | J_DEBUG-1 (Y=22mm) | U_MCU-2 (Y=55mm) |
| 17.4mm | J_USB (Y=5mm) | J_DEBUG-1 (Y=22mm) |

These gaps force the router to create long traces with limited layer options, competing for routing channels.

### Recommended Solutions

1. **Manual routing** - Route the 3-4 remaining GND stubs manually
2. **Ground plane** - Use In1.Cu or In2.Cu as a dedicated GND plane (most PCBs do this)
3. **Placement optimization** - Move J_DEBUG closer to the MCU cluster to reduce the 32.8mm gap

## Usage

To export a properly routable DSN:

```python
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.dsn_exporter import DSNExporter

result = parse_kicad_pcb(Path("board.kicad_pcb"))
exporter = DSNExporter(result.board, result.netlist)
dsn_expr = exporter.export_pcb(pcb_name="board")
Path("board.dsn").write_text(str(dsn_expr))
```

The exporter now correctly:
1. Creates multi-layer padstacks for THT pads
2. Marks all copper layers as signal type for autorouting
3. Preserves actual pad dimensions from the KiCad file
