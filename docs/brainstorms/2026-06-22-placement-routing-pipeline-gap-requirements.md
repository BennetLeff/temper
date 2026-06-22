---
date: 2026-06-22
topic: placement-routing-pipeline-gap
focus: Wire the existing placer and Router V6 into the closure test pipeline with extensible placement strategy
origin: docs/ideation/2026-06-22-design-validation-ideation.md
status: active
actors: closure test, CI system
---

# Requirements: Placement-to-Routing Pipeline Gap

## Problem Frame

The `temper_placer.regression.closure_test` runs a parse → place → route → DRC pipeline against a PCB. Today, both the placement step (`benders_placement`) and routing step (`route_pcb`) fail as `ImportError` — the closure test reports a PASS with zero real results because both steps are no-op warnings.

The Router V6 pipeline (`RouterV6Pipeline.run()`) is a fully implemented 4-stage router, but it exposes a `run(pcb_path)` interface that doesn't accept pre-computed placements. The existing deterministic placer (`template.py`, `deterministic.py`) is in the codebase but has no closure-test-compatible entry point.

This gap means the project's primary validation loop (placement → routing → DRC) reports success without exercising the placer or router — false confidence.

## Actors

- **A1. Closure test developer** — invokes `ClosureTest(pcb_path, seed).run()` and expects placement and routing to produce real results, not warnings
- **A2. CI system** — runs `ci_closure_test.py` and needs the pipeline to return meaningful `router_completion_pct` and `drc_errors` values for regression gates

## Key Decisions

- **K1. Strategy pattern for placement.** `benders_placement()` exposes a fixed interface `(parsed: ParsedPCB, seed: int) → PlacementResult` with a `strategy` parameter. The default strategy delegates to the existing deterministic placer. Benders decomposition — when built — becomes a second strategy registered under the same interface. The closure test does not change; it calls the same function regardless of strategy.
- **K2. Placement-aware routing.** `route_pcb(parsed: ParsedPCB, placements: dict, seed: int) → RoutingResult` accepts the placement dict from step 1 and feeds component positions into Router V6's internal stages before routing commences. The adapter does not modify `pipeline.py`.
- **K3. Existing placer delegation.** The deterministic placer (whatever its actual function signatures and output format) is wrapped, not rewritten. If its output format differs from the expected `{component_id: (x, y)}` dict, the wrapper transforms it.
- **K4. Module location.** The placement module lives at `temper_placer.placement.benders_loop` (where the closure test imports it). The Router V6 adapter is a new function `route_pcb` exported from `temper_placer.router_v6`.

## Requirements

### R1. Placement Module (`benders_loop`)
Status: required

Expose a `benders_placement(parsed, seed, *, strategy="template")` function that:
- Returns an object with `.placements` (dict of `{component_id: (x, y)}`), `.iterations` (int), and `.cuts` (int)
- Defaults to the existing template-based deterministic placer
- Accepts a `strategy` keyword so Benders decomposition can be registered later without changing callers
- Gracefully falls back if the strategy fails (log a warning, return empty placements — do not raise)

### R2. Router V6 Adapter (`route_pcb`)
Status: required

Export a `route_pcb(parsed, placements, seed)` function from `temper_placer.router_v6` that:
- Accepts the `ParsedPCB` object from the parse step and the `placements` dict from the placement step
- Applies component positions into the routing pipeline before invoking `RouterV6Pipeline.run()`
- Returns an object with `.completion_rate` (float, 0.0–1.0) matching what the closure test expects
- Does not modify `RouterV6Pipeline` internals beyond feeding placement data into the appropriate stage

### R3. Closure Test Integration
Status: required

The closure test at `packages/temper-placer/src/temper_placer/regression/closure_test.py` already imports from the correct paths. After R1 and R2, the test should:
- Display non-zero `benders_iterations` / `benders_cuts` when the default strategy runs
- Display non-zero `router_completion_pct` when route_pcb runs
- No longer emit `WARNING: Benders not importable` or `WARNING: Router V6 not importable` on the default strategy path

### R4. Verification
Status: required

- **AE1.** Running `ClosureTest(pcb_path=placement_optimized.kicad_pcb, seed=...).run()` produces `benders_iterations > 0` and `router_completion_pct > 0.0` on the default strategy
- **AE2.** The closure test result no longer logs Benders or Router import warnings
- **AE3.** Running with `strategy="benders"` before Benders is implemented produces a warning and empty placements — the pipeline degrades gracefully, does not crash

## Scope Boundaries

### Deferred for later
- **Implementing Benders decomposition.** This builds the interface slot and strategy pattern. Actual Benders optimization is a separate, larger effort requiring the decomposition algorithm, Lagrangian multipliers, and convergence criteria.
- **Placement quality improvements.** The existing deterministic placer's quality is unchanged — this work wires it in, it doesn't improve it.
- **Router V6 performance tuning.** The adapter does not change how Router V6 routes — it only feeds placement positions into the existing stages.

### Outside this product's identity
- Replacement of the deterministic placer with a different placement algorithm. The strategy pattern supports this but doesn't mandate it.
- Changes to the closure test's pass/fail criteria. The test already correctly treats placement/routing warnings as non-blocking.

## Success Criteria

- **SC1.** Pipeline closure test produces real placement and routing results (non-zero iterations, non-zero completion rate) using the existing placer and Router V6
- **SC2.** The strategy pattern interface is forward-compatible: adding `strategy="benders"` later requires no changes to the closure test or `route_pcb`
- **SC3.** Existing tests in `tests/regression/test_closure.py` continue to pass

## Dependencies

- `temper_placer.placer.template` / `temper_placer.placer.deterministic` — existing placement code (functions and output format must be discovered during planning)
- `temper_placer.router_v6.pipeline.RouterV6Pipeline` — existing Router V6 implementation (interface must be discovered during planning)
- `packages/temper-placer/src/temper_placer/regression/closure_test.py` — consumer of both modules (interface is already fixed)

## Assumptions

1. The deterministic placer produces component positions in some mappable format (dict, list, named object) that can be transformed into `{component_id: (x, y)}`
2. Router V6's `RouterV6Pipeline.run(pcb_path)` reads component positions from the PCB data and can be influenced to use externally-supplied positions during one of its stages
3. The closure test's expected interface (`benders_placement(parsed, seed)` → object with `.placements`, `route_pcb(parsed, placements, seed)` → object with `.completion_rate`) is fixed and authoritative
