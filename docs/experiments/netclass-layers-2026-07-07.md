# Netclass-Aware Clearance: Per-Layer Experiment

**Date:** 2026-07-07
**Status:** Row A complete (truth gate operational)

## The Three Bugs That Produced the False "0 DRC"

Three silent failures conspired to produce a 0-DRC result that was wrong at every layer:

### Bug 1: kicad-cli board format incompatibility
The temper PCB used KiCad-5-era syntax rejected by kicad-cli 9.0.7. Three fixes required:
1. Bare `(property "X" "Y")` → add `(at 0 0 0) (layer "F.SilkS") (effects ...) hide`
2. `(gr_rect ... (width X))` → `(gr_rect ... (stroke (width X)))`
3. Remove bare `;` comment lines

### Bug 2: netclass s-expression format
The `(net_class ...)` form was missing the description string: `(net_class "HighVoltage" (clearance 6.0) ...)` should be `(net_class "HighVoltage" "Auto-generated..." (clearance 6.0) ...)`. Without it, kicad-cli rejected the output PCB.

### Bug 3: constraint generator classification
`_resolve_component_net_class` iterated `netlist.nets[].pins[].component` — but `net.pins[i]` is a tuple (no `.component`). Used `component.pins[i].net` instead. All 33 components were returning None → 0 constraints generated.

All three fixed. The truth gate now runs against both the input and output PCBs.

## Real Result

| Checkpoint | DRC Errors | Warnings | Notes |
|-----------|-----------:|---------:|-------|
| Baseline (human) | **22** | 33 | `temper.kicad_pcb` as-designed (no netclass forms) |
| A) Placement only | **61** | 36 | CP-SAT optimal at 2700ms, 303 SEPARATED constraints, 9 netclass forms in output PCB |
| B) Placement + Routing | — | — | Gated: `temper_rust_router` GIL crash |
| C) Full pipeline | — | — | Gated: depends on Row B |

## What Changed From the Original "121" Claim

The original 121-error claim (from the umbrella report) was measured under different conditions — possibly with the router's internal DRC proxy, different rule configuration, or before the board format was fixed. With kicad-cli 9.0.7 as the truth gate:

- Human-designed board: **22 errors** (not 29 or 121)
- CP-SAT placed with netclass constraints: **61 errors** (not 0)

The netclass constraints work correctly: HV↔Signal minimum Euclidean distance is 9.92mm (target ≥6.0mm). 303 SEPARATED constraints fire, 29/33 components classified. But CP-SAT optimization for other factors (pad-to-pad clearance, board edge distance, component body overlaps) produces more total DRC violations than the human layout.

## Verified

- **SSOT chain end-to-end:** netclass_rules.yaml → DesignRules → SEPARATED constraints → placement → output PCB (net_class ...) forms → kicad-cli pcb drc
- **303 cross-class SEPARATED constraints:** 6mm HV↔Signal, HV↔GND, ACMains↔Signal, etc.
- **HV↔Signal min distance:** 9.92mm (after 303 constraints, well above 6.0mm target)
- **9 netclass forms in output PCB:** ACMains, FinePitch, GND, GateDrive, HighCurrent, HighSpeed, HighVoltage, Power, Signal
- **CP-SAT solve:** 2700ms (optimal), 303 constraints on 33 components

## The Discipline Loop

The measurement was run, not deferred. The initial "0" was a compound of three silent failures — two in the tool chain (board format, netclass syntax) and one in the constraint generator (tuple vs Pin). All three diagnosed, all three fixed, all verified end-to-end with a running truth gate.

The number is **22 → 61**, not 121 → 0. The SSOT chain works. The constraints enforce the rules they were designed to enforce. The gap between baseline and placed reflects real tradeoffs CP-SAT makes that human designers don't — and that's subject to further constraint tuning, not a failure of the SSOT architecture.
