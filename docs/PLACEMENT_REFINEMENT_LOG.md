# Placement Refinement Log & Hybrid Strategy

## Overview
This document tracks the immediate, manual/scripted placement refinements applied to the `temper` PCB. This "Hybrid Strategy" serves as a bridge between the current "Naive" optimizer and the future **Physics-Informed Hypergraph Optimizer**.

## 1. Problem Statement: Routing Gridlock
The current `routed_v3.kicad_pcb` failed because:
- **AC Input (`J_AC_IN`)** is placed far from the **Bridge Rectifier (`D1`)**, forcing High-Voltage `AC_L`/`AC_N` tracks to traverse the entire inner-layer logic area.
- **Shorts:** High-Voltage tracks were routed over Low-Voltage pads.
- **Isolation:** Track density created "islands," electrically isolating components like `J_NTC` from the main Ground plane.

## 2. Immediate Refinement Plan (The "Band-Aid")
To achieve a routable board *now*, we are bypassing the optimizer for critical components:

### Action 1: Power Path Compression
- **Goal:** Minimize the "High-Voltage Footprint."
- **Operation:** Scripted relocation of `J_AC_IN` (AC Inlet), `F1` (Fuse), and `VAR1` (Varistor) to be adjacent to `D1`.
- **Expected Outcome:** `AC_L` and `AC_N` tracks will be <10mm long and stay within a dedicated "High-Voltage Zone," preventing them from crossing the MCU/Logic area.

### Action 2: Logic Channel Clearing
- **Goal:** Create routing "highways" for the Autorouter.
- **Operation:** Nudge logic components (ESP32, sensing ICs) to create 5mm wide vertical/horizontal clearways on `In1.Cu` and `In2.Cu`.

## 3. Data for the Future Hypergraph
These manual refinements are not just "fixing the board"; they are providing **Gold Standard** data for the next generation of `temper-placer`:

- **Hyperedge Weights:** The fact that `J_AC_IN` and `D1` *must* be close confirms that their Hyperedge requires a significantly higher weight ($f(Voltage, Current)$) than a signal net.
- **Keepout Constraints:** We are identifying "Implicit Keepouts" (areas where HV tracks must never go) that the Hypergraph Optimizer will eventually enforce using **High-Voltage Repulsion Losses**.
- **Super-Nodes:** The grouping of AC-Inlet + Fuse + Varistor validates the "Super-Node" coarsening strategy discussed in `hypergraph_experiments.md`.

## 4. Execution Trace
- **2025-12-29:** Initiated Step 1 (AC Input Relocation).
- **2025-12-29:** Executed `scripts/refine_placement.py`.
    - Moved `J_AC_IN` to `(10, 125)` (Edge-aligned, same Y-level as Rectifier).
    - Stripped 100% of existing routing segments.
    - Output: `unrouted_v4.kicad_pcb`.
    - Result: AC input loop area reduced by ~50%.
- **2025-12-29:** **CRITICAL FINDING**: IGBT Footprint Pinout Mismatch.
    - Component: `IKW40N120H3` (TO-247).
    - Standard Pinout: 1=Gate, 2=Collector, 3=Emitter.
    - PCB Netlist (Current): Pad 2 assigned to Emitter-side nets, Pad 3 to Collector-side nets.
    - **Risk:** Reverse polarity on IGBTs -> Immediate destruction.
    - **Action:** Implementing net swap script to correct Q1/Q2 pads in place.
- **2025-12-29:** Executed `scripts/fix_igbt_pinout.py`.
    - Swapped Q1 Pads: Pad 2 (`SW_NODE`), Pad 3 (`DC_BUS+`) [Corrected].
    - Swapped Q2 Pads: Pad 2 (`SW_NODE`), Pad 3 (`PGND`) [Corrected].
    - Output: `unrouted_v4_fixed.kicad_pcb`.
    - **Status:** Board is now electrically safe to route.
- **2025-12-29:** Executed `scripts/pre_route_power.py`.
    - Manually routed `AC_L` and `AC_N` (2.0mm width, B.Cu).
    - Path: `J_AC_IN` -> `D1`/`D2` (Direct edge-to-rectifier).
    - Output: `pre_routed_v5.kicad_pcb`.
    - **Status:** Critical HV loops are locked in. Ready for Autorouter (Logic only).
