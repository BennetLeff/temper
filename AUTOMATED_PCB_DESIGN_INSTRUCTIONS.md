# Automated PCB Design Instructions

This document outlines the mandatory workflow, architectural decisions, and tool usage for the Temper PCB project. It serves as the single source of truth for AI agents and engineers working on the board's layout.

## Core Philosophy: Physics-First Design

We do not design PCBs by simply "connecting the dots." High-power induction heaters (40A, 25kHz) are physics problems first and graph problems second. We manage energy fields, thermal gradients, and current loops.

**The 3 Pillars of Temper PCB Design:**

1.  **Zoning (Placement)**: Strict physical segregation of High Voltage (HV) and Low Voltage (LV) domains.
2.  **Topology (Connectivity)**: Explicit Star Grounding via Net Ties. `PGND` (Power) and `GND` (Control) are separate nets that meet at exactly one point.
3.  **Geometry (Planes)**: Procedural generation of copper pours *before* trace routing.

---

## The Workflow

To ensure safety and performance, the following pipeline must be followed strictly. Do not attempt to manually route the board or use a standard auto-router without these preprocessing steps.

### Step 0: Generated-Safety Import Gate

`scripts/run_clean_flow.sh` first compares `elec/build/default.net` with the
KiCad source board. It requires the active-high `SHUTDOWN` and
`RTD_HW_FAULT` nets, RTD connector/sensor nets, and the UCC21550, MAX31865,
reference, comparator, rail-monitor, logic, and redundant fault-OR device
families. This is a stable family/net-name contract rather than a generated
reference-designator comparison.

If it fails, open `pcb/temper.kicad_pcb` in KiCad PCB Editor and use **Tools →
Update PCB from Schematic** with the freshly built Atopile netlist. Place the
new RTD safety cluster before rerunning the pipeline. Do not route the legacy
board and treat its result as evidence for the new safety path.

### Step 1: Physics-Aware Placement
**Tool:** `temper-placer`
**Config:** `packages/temper-placer/configs/temper_constraints.yaml`

We use a JAX-based optimizer to place components. Crucially, we must use the **strict constraints** file (`temper_constraints.yaml`), not the default or minimal config.

*   **Why?** This config enforces the "Power Top / Control Bottom" zoning.
*   **Command:**
    ```bash
    temper-placer optimize pcb/temper.kicad_pcb \
        -c packages/temper-placer/configs/temper_constraints.yaml \
        -o pcb/temper_placed.kicad_pcb \
        --auto-group
    ```

### Step 2: Ground Reference Plane Generation
**Tool:** `scripts/add_power_planes.py`

The current board flow injects one unified `GND` reference plane on `In2.Cu`
after the place→route loop. It is a reference-plane step, not a substitute for
power-stage routing or for an intentional `PGND`/`GND` net-tie topology.

*   **What it does:**
*   **Unified GND:** Adds a board-edge-inset `GND` zone on `In2.Cu`.
*   **Why?** Provides a continuous return reference; it does not automatically
    join distinct `PGND`/`CGND` nets or create +3V3/+5V power islands.
*   **Command:**
    ```bash
    python3 scripts/add_power_planes.py pcb/temper_placed.kicad_pcb pcb/temper_ready_for_route.kicad_pcb
    ```

### Step 3: Routing and Truth Gate
**Tool:** CP-SAT place→route loop, then `kicad-cli pcb drc`

The loop places with CP-SAT and routes using Router V6. For an authoritative
KiCad source board, one deterministic fully-routed artifact goes immediately
to KiCad DRC; repeating the same native-router invocation is not treated as
an independent stability measurement. Its pin-hull overlap check is diagnostic
only—the KiCad DRC on the emitted board is the authoritative physical-overlap
check. The flow fails closed on a non-convergent route or a KiCad DRC error,
then adds the reference plane and runs a second KiCad DRC on the final board.
A failed stage does not leave a board that may be treated as ready for routing.

---

## Architectural Decisions

### 1. The "Split Ground" Topology
*   **Current implementation:** `scripts/add_power_planes.py` emits only a
    unified `GND` reference plane. If the design requires physically separate
    `PGND` and `GND`, represent them as distinct nets joined by an intentional
    net-tie footprint; do not infer that topology from placement.

### 2. Zoning Strategy
*   **Power Zone (Top/High Y):** Contains IGBTs (`Q1`, `Q2`), Rectifiers (`D1`, `D2`), and DC Bus Caps (`C_BUS`). High voltage, high noise.
*   **Control Zone (Bottom/Low Y):** Contains MCU (`U_MCU`), Sensors, and UI. Low voltage, noise sensitive.
*   **Interface Zone (Edges):** Connectors must be placed at board edges.

### 3. Documentation & Sync
*   **Rule:** If you modify `scripts/add_power_planes.py`,
    `scripts/run_clean_flow.sh`, or `temper_constraints.yaml`, you **MUST**
    update this document (`AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md`) to reflect
    the changes.
*   **Reason:** AI agents relying on outdated context will generate dangerous board designs.

---

## Scripts Reference

*   `scripts/run_clean_flow.sh`: The master script that executes the
    fail-closed placement, routing, plane, and DRC path.
*   `scripts/add_power_planes.py`: The unified-GND reference-plane generator.
*   `packages/temper-placer/configs/temper_constraints.yaml`: The single source of truth for placement rules.
