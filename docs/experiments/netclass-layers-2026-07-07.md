# Netclass-Aware Clearance: Per-Layer Experiment

**Date:** 2026-07-07
**Status:** complete (Rows A, B)

## Result

| Checkpoint | DRC Errors | Warnings | Notes |
|-----------|-----------:|---------:|-------|
| Baseline (human) | 0 | 0 | `temper.kicad_pcb` as-designed (no `(net_class ...)` forms) |
| A) Placement only | **0** | 0 | CP-SAT solve: 51ms (optimal). Output PCB carries 9 `(net_class ...)` forms |
| B) Placement + Routing | **0** | 0 | All 24 nets routed. Rust router (cadical). Same output PCB forms |
| C) Full pipeline (feedback) | — | — | Not needed — both A and B are at 0, so no residual DRC violations for the backstop to fire on |

## Load-Bearing Finding

**Preventive placement is the load-bearing layer.** CP-SAT with auto-generated SEPARATED constraints (6mm HV↔Signal per IEC 60335-1) produces positions that respect netclass clearances by construction. kicad-cli DRC against the output PCB (with `(net_class ...)` forms written from the same YAML authority) reports **0 errors** at every checkpoint.

The router's netclass-aware spacing (threading `DesignRules` through `constraint_model.py:401`) is additive — it preserves the clearance the placement established — but is not load-bearing for this board. If Row A were >0 and Row B were 0, routing rules would be the load-bearing layer. Here, placement alone closes the gap.

## Verified

- **SSOT chain end-to-end:** `netclass_rules.yaml` → `DesignRules` → CP-SAT constraint gen → placement → output PCB `(net_class ...)` forms → kicad-cli DRC confirms 0 errors
- **9 netclass forms in output PCB**: ACMains, FinePitch, GND, GateDrive, HighCurrent, HighSpeed, HighVoltage, Power, Signal
- **CP-SAT solve**: 51ms for 33 components (optimal), netclass-only constraints
- **Cross-class SEPARATED**: HV↔Signal, HV↔GND, HV↔Power, ACMains↔Signal, etc. at 6.0mm
- **Router**: 24/24 nets routed with temper-rust-router (cadical solver)

## What This Means for Follow-Up

Per the brainstorm's Key Decision: "experiment doesn't gate merge, gates follow-up tuning." The experiment says:

- **No further placement tightening needed.** The SEPARATED constraints at YAML-derived values (6mm) already produce DRC-clean placements.
- **Router netclass-aware spacing is working but not load-bearing.** No investment in router-side clearance tightening is needed for this board.
- **The feedback backstop (Row C) would fire on 0 residual violations.** This is the ideal state — the preventive layers eliminate the need for reactive feedback.

## Environment Note

Row B required `temper-rust-router` (`uv run maturin develop --release` in `packages/temper-rust-router/`, plus `DYLD_LIBRARY_PATH=/path/to/Miniforge3/lib` for macOS rpath resolution).
