---
title: Placer→router seam broken by a chain of silent constraint-drop bugs (board falsely stuck at 83.3%)
date: "2026-07-11"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
symptoms:
  - "board routes at 83.3% (20/24 nets) and the router is blamed, but the placement was never actually constrained"
  - "CP-SAT placement returns model_invalid / UNSAT at round 1 with an empty unsat_core"
  - "load_constraints warns 'Unknown config keys will be ignored: [constraints, ...]' and only 1 of ~29 constraints reaches the solver"
  - "solver logs 'comp J_AC not found' / 'comp U_RTD not found' but proceeds — constraints silently drop"
  - "kicad-cli DRC reports 59 track_width violations with actual 0.0000mm on power/ground nets"
root_cause: config_error
resolution_type: code_fix
severity: critical
tags:
  - cp-sat
  - constraint-encoding
  - config-drift
  - silent-failure
  - fail-closed
  - zone-bounds
  - routing
  - drc
---

# Placer→router seam broken by a chain of silent constraint-drop bugs

## Problem

The temper board appeared stuck at 83.3% routed and the router was blamed.
The real cause: the CP-SAT placer was optimizing against almost no
constraints, and routing was being measured on an unoptimized hand
placement, because the placer→router seam was broken by a chain of
independent silent-drop bugs. Fixing them took the board to 100% routed
(0 unconnected, kicad-cli-confirmed) with the mains input correctly
zone-contained.

## Symptoms

- Routing plateaus at 83.3% (20/24); the 4 failing nets shuffle when net
  order changes but the count does not — the signature of a weak lever,
  not the real cause.
- CP-SAT placement returns `model_invalid` at round 1 with empty core.
- `load_constraints` warns `Unknown config keys will be ignored:
  ['constraints', 'metadata', ...]`; only 1 constraint is loaded.
- Solver logs `comp 'J_AC' not found`, `comp 'U_RTD' not found`, etc., yet
  proceeds — the constraints referencing those refs vanish.
- After the placement fix: `kicad-cli pcb drc` shows 59 `track_width`
  violations at `actual 0.0000 mm` on GND / AC_L / AC_N.

## What Didn't Work

- **Re-attacking routing as an ordering / router problem.** The prior
  diagnosis ("route signals last") was already implemented in the pipeline
  and only reshuffled which 4 nets failed. Reading the code suggested it
  was applied; only running it revealed it did not help — because it was
  the wrong layer entirely (the placement was unconstrained).
- **Treating the CP-SAT `INFEASIBLE` as a design conflict.** Once
  constraints actually applied, the solver proved UNSAT and the core
  looked like a real power-stage geometry conflict. It was two more
  encoding bugs (see below); relaxing the loop-area design margin would
  have masked them.

## Solution

Five distinct bugs, each a silent drop, fixed at source:

1. **Zone-bounds convention mismatch (empty zones → UNSAT).** The config
   wrote zones as `(x, y, width, height)` on a phantom 120×80 board; the
   encoder and every other config use `(x_min, y_min, x_max, y_max)` on
   the real 100×150 board. `[70,0,50,80]` read as xyxy is an inverted
   (empty) rectangle, so any `enclosing` constraint became infeasible.
   Fix: a validated `Rect` value type with explicit `from_xyxy` /
   `from_xywh` constructors that reject inverted/degenerate rectangles at
   construction, plus rewriting the temper zones to canonical form.

2. **The `constraints:` block was never parsed.** `load_constraints` had
   no handler for the top-level `constraints:` list, so ~28 of 29
   constraints were dropped. Fix: `_parse_pcl_constraints` (delegating to
   the existing `parse_constraint_dict`) + register the previously-unknown
   config keys.

3. **`_encode_adjacent` ignored the `metric` field.** Config said
   `adjacent Q1-Q2 max 10mm metric: edge_to_edge`; the encoder always used
   center-to-center. For 25.3mm-wide IGBTs forced side-by-side by
   `on_side top`, no-overlap needs centers ≥25.3mm apart while
   center-to-center adjacency demanded ≤10mm — a contradiction invisible
   in the config. Fix: honor `EDGE_TO_EDGE`/`PIN_TO_PIN` (per-axis
   bounding-box gap) vs `CENTER_TO_CENTER`.

4. **Phantom loop reference.** `pcb_spec.yaml` gate-drive loops referenced
   `U_GATE_DRV`, absent from the netlist, so the loop-area encoder silently
   computed over a partial component set. Fix: rename to `U_GATE`.

5. **Zero-width plane-net tracks.** Plane/power nets were compiled with
   `width_mm=0.0` yet still emitted real MST trace geometry in the
   exporter → 59 zero-width tracks flagged by DRC. Fix: floor plane-net
   width at the 0.2mm board minimum in `routing_results.py`, plus a
   defense-in-depth `width <= 0` guard in `adapter._inject_routed_traces`.

The connecting fix — **fail-closed ref validation**:
`validate_constraint_refs` now raises (default) when any constraint operand
resolves to no component/zone/loop, catching config↔netlist drift at the
resolution boundary instead of silently dropping. It surfaced 17 dropping
refs at once. Unambiguous renames applied (`J_AC`→`J_AC_IN`,
`U_RTD`→`MAX31865`); genuinely-missing parts (`C_TANK`, `D_BOOT`, `J_FAN`,
`U_SPI_FLASH`, `C_VCC1/2`, `CT1`) were disabled with documented NOTEs, not
guessed — they are board-completeness decisions.

## Why This Works

Every one of these was a "looks applied but isn't" failure: the constraint
was present in the config, so it appeared enforced, but it resolved to
nothing (empty zone, unparsed block, wrong metric, phantom ref) and
dropped without error. That made every placement metric a lie — the placer
reported OPTIMAL because it was solving a nearly-unconstrained problem. The
fixes restore the constraints to the solver; the fail-closed guard ensures
the next drift raises instead of hiding.

## Prevention

- **Fail-closed at resolution boundaries.** Any ref that resolves to
  nothing must raise, not skip. `TEMPER_UNRESOLVED_REF_POLICY=warn` allows
  a deliberate exploratory downgrade.
- **Encode conventions in types.** A bare `tuple[float,float,float,float]`
  is ambiguous between `(x,y,w,h)` and `(x_min,y_min,x_max,y_max)`. A
  `Rect` with named constructors makes the convention unstateable-wrong
  and rejects inverted rectangles at construction.
- **Register-and-reject unknown config keys loudly** — an "ignored keys"
  warning that scrolls past is a silent-drop in disguise; prefer a hard
  error for structural keys like `constraints:`.
- **Verify each constraint in a UNSAT core individually** before calling
  INFEASIBLE a design verdict. Use `SufficientAssumptionsForInfeasibility`.
- **Never emit degenerate geometry** (`width <= 0`) — guard at the
  exporter, and floor at the board minimum at the source.

## Related Issues

- `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md` — the generalizable discipline these bugs taught
- `docs/solutions/best-practices/per-net-isolation-routing-diagnosis-2026-07-10.md` — the router-vs-placement diagnosis this arc resolved
- `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md` — a sibling CP-SAT encoding-soundness bug
- `docs/solutions/logic-errors/off-center-pad-offset-defeats-centered-bounds-2026-07-08.md` — a sibling geometry-convention bug in the placer
