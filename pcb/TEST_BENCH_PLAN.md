# Phase 5: The KiCad Integration Test Bench

## Problem: Garbage In, Garbage Out
The topological router is performing correctly mathematically, but it produces shorts because it is operating on an incomplete model of the board. The DRC report confirms that critical footprint libraries (`Capacitor_SMD`, `Package_SO`, `Diode_THT`) are **missing** from the environment.

**Impact**:
- `kicad_parser` cannot load footprint geometry.
- `RoutingSpace` sees empty space where components exist.
- Router places traces through components.
- KiCad DRC (which might have access to system libs or cached data) flags the collision.

## The Solution: A Hermetic Test Bench

We must create a self-contained environment where the Router and the DRC engine see the **exact same reality**.

### 1. Library Management Strategy
Instead of relying on system-installed KiCad libraries (which vary by OS/Version):
- **Localize**: Download/Clone required `.pretty` libraries into `pcb/libs/`.
- **Map**: Generate a local `fp-lib-table` pointing to `pcb/libs/`.
- **Inject**: Ensure both Python Parser and `kicad-cli` use this table.

### 2. The Test Bench Script (`scripts/run_bench.py`)
A unified runner that:
1.  **Checks Environment**: Verifies `kicad-cli` version and Library paths.
2.  **Sanitizes Input**: Runs DRC on the *Input* board. If Input has errors (missing libs), ABORT.
3.  **Runs Router**: Executes `run_router_v6.py`.
4.  **Verifies Output**: Runs DRC on Output.
5.  **Visualizes**: Exports SVG/PNG of the result for human review.

### 3. Missing Libraries to Acquire
Based on DRC logs, we need:
- `Capacitor_SMD`
- `Resistor_SMD`
- `Package_SO`
- `Package_TO_SOT_THT` / `SMD`
- `Diode_THT`
- `Connector_PinHeader_2.54mm`
- `MountingHole`

## Execution Plan

### Step 1: Library Acquisition
Create `tools/fetch_libraries.sh` to `git clone` the official KiCad footprint repositories for the detected missing libs.

### Step 2: Path Configuration
Update the project's `fp-lib-table` to use `${KIPRJMOD}/libs/...` instead of global paths.

### Step 3: Verification
Run the 5-net profile. The "Missing Library" errors should vanish from the DRC report. The Shorts should vanish because the Obstacles will appear in the SDF.

## Success Metrics
1. **DRC Library Errors**: 0.
2. **Short Circuits**: 0 (because obstacles are finally visible).
