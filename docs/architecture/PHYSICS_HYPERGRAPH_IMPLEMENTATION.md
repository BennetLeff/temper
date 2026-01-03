# Implementation: Physics-Aware Hypergraph Routing System

**Status:** Completed & Verified
**Date:** 2025-12-28
**Parent Epic:** `temper-vs3b`

## Overview
This document details the as-built implementation of the Physics-Aware Hypergraph Routing System. This system solves the "Orphan Trace" problem (e.g., Logic GND pins trapped in High Voltage zones) by programmatically inferring routing strategies from the physical state of the PCB.

## 1. Core Subsystems

### 1.1 Hypergraph Router Bridge
Located in `packages/temper-placer/src/temper_placer/routing/bridge/`:
- **`inference.py`**: The rules engine.
    - **Zone Conflict Pass**: Detects Low-Voltage pins physically located in High-Voltage zones (or vice-versa). Assigns `EDGE_HUG` strategy.
    - **Current Capacity Pass**: Assigns `FLOOD_FILL` to nets exceeding 2.0A peak current (deferring them to the Plane Generator).
- **`cost_map.py`**: Functional JAX routines for 2D geometry.
    - `generate_edge_hug_field`: Creates a cost "valley" (low cost at board boundary, high cost in center).
- **`api.py`**: Public interface for the router to query strategies and cost maps.

### 1.2 Router Integration
- **`maze_router.py`**: 
    - Added support for `cost_map` parameter in `find_path` and `route_net`.
    - Integrated dynamic neighbor costs: `total_cost = base_cost * cost_map[neighbor]`.
    - Improved `_create_pin_escape_routes` to handle large footprints by scaling escape length based on component size.
- **`unified_router.py`**: 
    - Now queries the Hypergraph Bridge before routing.
    - Applies `EDGE_HUG` by injecting cost maps into the MazeRouter.
    - Handles `FLOOD_FILL` by marking nets as "Deferred to PlaneGen".

### 1.3 Routing-to-Placement Feedback Loop
- **`feedback.py`**: Translates router failures (unrouted nets) into spatial coordinates.
- **`spatial_feedback.py`**: A new JAX loss function (`SpatialFeedbackLoss`) that adds Gaussian repulsion fields at routing failure locations, pushing components apart to open channels.

## 2. Verification
- **Test File**: `packages/temper-placer/tests/routing/test_hypergraph_bridge.py`
- **Verification Script**: `scripts/verify_hypergraph_routing.py`
    - Simulates a Logic Ground pin trapped in an HV Zone.
    - **Asserts** that the Bridge correctly assigns `EDGE_HUG`.
    - **Asserts** that the resulting trace follows the board edge and avoids the hazardous zone center.

## 3. Results
The system successfully solved the final 3 unrouted "orphan" connections on the Temper board (AC Input Ground, Coil Ground, NTC Ground). These traces are now automatically routed via the board edge with zero manual configuration or specialized routing masks.

**Completion Rate:** 100% automated routing achieved on high-power switching board.
