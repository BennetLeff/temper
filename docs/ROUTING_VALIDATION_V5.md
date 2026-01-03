# Router V5: Core Pipeline Validation & Fixes

This document summarizes the changes made to the `temper-placer` routing engine to validate the core pipeline and resolve critical pathfinding failures.

## 1. Objectives
- **Simplify**: Disable advanced V4 features (Dithering, Smoothing, Ballooning) to isolate core bugs.
- **Validate**: Create a repeatable minimal test for 1-net routing.
- **Fix**: Resolve systematic failures related to pin blocking and coarse grid aliasing.

## 2. Changes Implemented

### 2.1 Core Pipeline Reset
- Modified `temper_placer.routing.c_space_pipeline.PipelineConfig` to set `enable_dithering`, `enable_smoothing`, and `enable_ballooning` to `False` by default.
- This ensures that during initial validation, only the raw A* maze router is active.

### 2.2 MazeRouter Improvements
- **Net-Aware Pad Unblocking**: Fixed a critical flaw in `route_net_rrr` where it would unblock pads from ALL nets within a fixed radius. This caused tracks to tunnel through foreign pads, creating DRC shorts. The unblocking logic now respects net ownership from `_pad_net_map`.
- **Increased Unblock Radius**: Increased the escape radius from `0.8mm` to `2.5mm`. On coarse grids (e.g. 0.5mm), large pads (3.0mm) were previously trapping the start/end pins in their own blockage footprint.
- **Coarse Grid Aliasing Fix**: Added better unblocking for components that are -1 but not in the `pad_net_map`, allowing the router to start/end even if centered precisely on a component boundary.

### 2.3 Debugging & Tooling
- **Coordinate Logging**: Added grid and world coordinate logging in `trace_writer.py` and `maze_router.py`.
- **Occupancy Visualization**: Added `visualize_occupancy` to the validation script, which exports the router's internal blockage state to the `Dwgs.User` layer of the PCB.
- **Minimal Test**: Created `packages/temper-placer/scripts/validate_core_routing.py` for headless validation.

### 2.4 Phase 3: MCU Breakout (0.4mm pitch)
- **Resolution**: Demonstrated that **0.05mm grid** is required for reliable breakout from 0.4mm QFN footprints.
- **Clearance Logic**: Successfully used search-time `clearance_mask` (0.1mm) with `margin=0.0` for pads to maintain open channels between MCU pins.
- **Performance**: Routing 10M cells (0.05mm over 4 layers) takes ~1.5s, which is acceptable for single-net validation.

## 3. Findings & Next Steps
- **Resolution**: 0.05mm is the recommended high-density resolution.
- **Placement Issues**: Template PCB still contains overlapping pads (AC section) causing unavoidable DRC errors.
- **Phase 4**: Power section isolation and creeping distance verification.
