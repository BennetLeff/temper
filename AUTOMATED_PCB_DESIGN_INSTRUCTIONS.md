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

### Step 2: Smart Plane Generation
**Tool:** `add_power_planes_v2.py`

Standard auto-routers do not understand power planes. They treat a 40A bus as a signal wire. We must procedurally inject geometry (zones) into the PCB file *after* placement but *before* routing.

*   **What it does:**
    *   **Split Ground:** Detects the Y-axis boundary between the Power and Control zones and cuts the Layer 2 ground plane accordingly.
    *   **Power Islands:** Generates targeted copper floods for +3V3 and +5V rails based on component clustering.
*   **Why?** Ensures low impedance for power rails and prevents ground loops.
*   **Command:**
    ```bash
    python3 add_power_planes_v2.py pcb/temper_placed.kicad_pcb pcb/temper_ready_for_route.kicad_pcb
    ```

### Step 3: Routing
**Tool:** FreeRouting (or internal router)

Only after planes are generated do we export the DSN for the router. The router's job is reduced to connecting signal traces (`GATE`, `SENSE`, `SPI`), which it can do safely because the heavy lifting (Power) is already done by the planes.

---

## Architectural Decisions

### 1. The "Split Ground" Topology
*   **Decision:** We use a "Star Ground" architecture where the Power Stage Ground (`PGND`) and Control Ground (`GND`) are physically separate planes on Layer 2.
*   **Implementation:**
    *   The netlist must contain two distinct nets: `PGND` and `GND`.
    *   These nets are connected by a **Net Tie** component (a physical footprint that shorts them).
    *   The `add_power_planes_v2.py` script algorithmically determines the split line based on component placement.

### 2. Zoning Strategy
*   **Power Zone (Top/High Y):** Contains IGBTs (`Q1`, `Q2`), Rectifiers (`D1`, `D2`), and DC Bus Caps (`C_BUS`). High voltage, high noise.
*   **Control Zone (Bottom/Low Y):** Contains MCU (`U_MCU`), Sensors, and UI. Low voltage, noise sensitive.
*   **Interface Zone (Edges):** Connectors must be placed at board edges.

### 3. Documentation & Sync
*   **Rule:** If you modify `add_power_planes_v2.py` or `temper_constraints.yaml`, you **MUST** update this document (`AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md`) to reflect the changes.
*   **Reason:** AI agents relying on outdated context will generate dangerous board designs.

---

## Scripts Reference

*   `scripts/run_clean_flow.sh`: The master script that executes Steps 1-3 in order. Use this for a reliable, "End-to-End" run.
*   `add_power_planes_v2.py`: The procedural geometry engine.
*   `packages/temper-placer/configs/temper_constraints.yaml`: The single source of truth for placement rules.
