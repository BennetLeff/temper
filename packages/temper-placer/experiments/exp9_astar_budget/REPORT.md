# EXP-9: Fix Escape Layer / Routing Layer Mismatch

## Summary
Fixed a layer mismatch bug where analog nets (I_SENSE, TEMP_SENSE) escaped to In1.Cu 
but were only allowed to route on layers [0, 3]. Changed escape target to B.Cu (layer 3).

## Results

| Metric | Baseline | After EXP-9 | Change |
|--------|----------|-------------|--------|
| Total violations | 102 | 99 | -3 (-2.9%) |
| I_SENSE violations | 19 | 15 | -4 (-21%) |
| TEMP_SENSE violations | 3 | 4 | +1 |
| Dangling vias removed | 28 | 16 | -12 (fewer failed routes) |
| Routing time | 11.0s | 11.0s | No change |

## Root Cause Found
The original hypothesis (A* iteration budget) was incorrect. Testing 2x budget showed no change.

**Actual bug**: `fine_pitch_escape.py` placed vias to In1.Cu for all nets by default,
but `sequential_routing.py` restricted analog nets to layers [0, 3] only.
The router couldn't continue routes from In1.Cu because layer 1 wasn't allowed.

## Changes Made

1. **fine_pitch_escape.py**: Added `layer3_nets` parameter for nets that should
   escape to B.Cu instead of inner layers.
   
2. Set `layer3_nets = {"I_SENSE", "TEMP_SENSE"}` to match routing restriction [0, 3].

## Observations

- I_SENSE improved significantly (-21%)
- TEMP_SENSE got slightly worse (+1) - likely routing order effects
- Total dangling vias dropped from 28 to 16 - indicates fewer routing failures
- SPI nets unchanged - they escape to In1.Cu but are allowed on all layers (no mismatch)

## Next Steps

The remaining violations are primarily on:
- GATE_L: 15 (escape to In2.Cu, allowed all layers - no mismatch)
- SPI_MISO: 13 (escape to In1.Cu, allowed all layers - no mismatch)
- SPI_MOSI: 11 (same)

These may benefit from:
1. Layer congestion balancing (move some SPI to In2.Cu)
2. Net ordering adjustments
3. Rip-up-and-retry implementation
