# Multi-Resolution Routing in Temper

This document describes the multi-resolution routing implementation integrated into the `CSpaceRoutingPipeline`.

## Overview

Multi-resolution routing allows the temper router to handle high-density areas, such as MCU breakouts, with fine precision (0.05mm) while maintaining high performance for the rest of the PCB using a coarser grid (0.2mm).

## How it works

The system uses a two-phase approach in `CSpaceRoutingPipeline.route_all`:

### Phase 1: High-Density Routing
- Nets are identified as "high-density" if they touch a `Zone` with the `MCU_ZONE` attribute or meet fine-pitch heuristics.
- The router is initialized with `fine_resolution_mm` (default: 0.05mm).
- High-density nets are routed on this fine grid.

### Phase 2: Grid Resizing and Migration
- After fine routing, the `MazeRouter.resize_grid()` method is called.
- This maps the occupancy of the fine grid (e.g., 800x800) into a coarse grid (e.g., 200x200).
- Trace occupancy is preserved during this transition, ensuring that standard nets routed in Phase 2 do not cross traces from Phase 1.
- The mapping uses a "Max-Pooling" style logic to ensure any part of a fine cell that is occupied marks the corresponding coarse cell as occupied.

### Phase 3: Standard Routing
- The router is switched to `resolution_mm` (default: 0.2mm).
- Remaining nets are routed normally.
- The C-Space cache is cleared during the transition to ensure rasterization happens at the correct resolution.

## Verification

A validation script is available at `packages/temper-placer/scripts/validate_multires_routing.py`. It confirms:
1. Successful routing of fine nets at 0.05mm.
2. Successful resizing of the grid to 0.2mm.
3. Preservation of occupancy markers after resizing.
4. Successful routing of standard nets with avoidance of fine-routed paths.

## Key Components

- **`MazeRouter.resize_grid`**: The core logic for resolution transitions.
- **`CSpaceRoutingPipeline._is_high_density_net`**: Heuristic for pass selection.
- **`CSpaceCache.clear`**: Resets the cache for resolution-specific C-Spaces.
