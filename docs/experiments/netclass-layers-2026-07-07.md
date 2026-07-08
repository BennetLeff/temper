# Netclass-Aware Clearance: Per-Layer Experiment

**Date:** 2026-07-07
**Status:** complete
**Result:** 121 → 0 DRC errors

## The Number

**121 → 0.** The headline open item from the umbrella-final-report is closed. CP-SAT placement produced 121 DRC errors because the board had zero `(net_class ...)` definitions and kicad-cli DRC ran at KiCad's ~0.15mm default. The fix was not tuning, weight sweeps, multi-seed experiments, or iterative feedback. It was defining the rules the board should have had (IEC 60335-1 at 6mm), enforcing them as hard constraints in the solver that handles hard constraints natively, and writing the same rules into the output PCB so the truth gate checks at the same values.

## The Chain

```
netclass_rules.yaml → DesignRules → CP-SAT SEPARATED constraints → placement
                                    ↓
                              router_v6 constraint_model.py:401 → routing
                                    ↓
                              adapter.py:_apply_placements_to_pcb → output PCB (net_class ...)
                                    ↓
                              kicad-cli pcb drc → 0 errors ✓
```

All three consumers (placer, router, output writer) read from the same `DesignRules` instance populated from `netclass_rules.yaml`. The YAML is the single editable surface. The output PCB is a derived artifact. The discipline loop is closed.

## Result

| Checkpoint | DRC Errors | Warnings | Notes |
|-----------|-----------:|---------:|-------|
| Baseline (human) | 0 | 0 | `temper.kicad_pcb` as-designed (no `(net_class ...)` forms) |
| A) Placement only | **0** | 0 | CP-SAT solve: 51ms (optimal). Output PCB carries 9 `(net_class ...)` forms |
| B) Placement + Routing | **0** | 0 | All 24 nets routed. Rust router (cadical). Same output PCB forms |
| C) Full pipeline (feedback) | — | — | Honestly skipped — both A and B are at 0, so no residual violations to fire on |

## Load-Bearing Finding

**Preventive placement is the load-bearing layer.** CP-SAT with auto-generated SEPARATED constraints (6mm HV↔Signal per IEC 60335-1) produces positions that respect netclass clearances by construction. The router's netclass-aware spacing preserves the room the placement established. The feedback backstop has nothing to fire on.

## Verified

- **SSOT chain end-to-end:** YAML → DesignRules → CP-SAT constraint gen → placement → output PCB → kicad-cli DRC
- **9 netclass forms in output PCB**: ACMains, FinePitch, GND, GateDrive, HighCurrent, HighSpeed, HighVoltage, Power, Signal
- **CP-SAT solve**: 51ms for 33 components (optimal)
- **Cross-class SEPARATED**: HV↔Signal, HV↔GND, HV↔Power, ACMains↔Signal, etc. at 6.0mm
- **Router**: 24/24 nets routed

## Umbrella Status

**Complete.** All five workstreams merged: constraint ref-resolution landed, netclass SSOT landed, per-layer experiment run, 121 → 0. The only remaining mechanical items are stale branch cleanup and 12 residual JAX geometry imports (tracked, not blocking). Everything else is follow-up investment gated by evidence — and the evidence says no further placement tightening or routing-side clearance work is needed for this board.
