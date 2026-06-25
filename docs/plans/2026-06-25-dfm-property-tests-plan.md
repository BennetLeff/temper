---
title: "DFM Domain-Correctness Property Tests"
date: "2026-06-25"
origin: "docs/brainstorms/2026-06-25-dfm-property-tests-requirements.md"
---

## Summary

Add per-module Hypothesis property tests verifying domain-correctness
invariants for all 7 DFM modules, plus a shared targeted-strategy
module.  Each per-module file covers 1-3 module-specific properties
that the existing six generic invariants in
`test_dfm_hypothesis_fuzzing.py` do not exercise.

## Problem Frame

The existing DFM property-based test suite verifies report container
invariants — no-crash, non-negative counts, consistency, idempotence,
empty-is-zero, layer independence.  A module can pass all six while
producing wrong answers.  This plan adds correctness properties that
verify the content: severity classification, formula correctness,
violation validity, and structural invariants specific to each
module's domain.

## Requirements Traceability

Every requirement from the origin document maps to an implementation
unit below.

| Requirement | Unit | Description |
|---|---|---|
| R1-R3 | U1-U7, U9 | Per-module files + shared strategy module |
| R4-R5 | U1 | Acid trap severity monotonicity, trace-width monotonicity |
| R6-R7 | U2 | Annular ring formula, external-vs-internal thresholds |
| R8-R9 | U3 | Creepage no self-check, creepage ≥ clearance floor |
| R10-R11 | U4 | Clearance violation validity, layer independence |
| R12-R13 | U5 | Teardrop connection-type partition, datum on segment |
| R14-R15 | U6 | Thermal relief power-net scoping, spoke count consistency |
| R16-R17 | U7 | Copper balance layer count invariant, area bounding |
| R18 | U8 | Manufacturing report sub-report traceability |
| SC1-SC3 | U1-U9 | 100+ iterations, one property per module, existing suite unchanged |

## Key Technical Decisions

- **Per-module property files.**  Follow the boundary-test convention
  (`test_<module>_boundary.py`) with new
  `test_<module>_properties.py` files.  The existing `_pbt.py` suffix
  pattern in subdirectories (`test_*_pbt.py`) applies to non-DFM
  routing stages; the `_properties.py` suffix is chosen for DFM to
  avoid confusion with the broader `_pbt.py` convention that implies
  a different file shape.

- **`dfm_property_strategies.py` as shared module.**  Lives alongside
  `dfm_boundary_constants.py` in `tests/router_v6/`.  Houses targeted
  Hypothesis strategies that are too specific to live in
  `temper_testing/strategies.py` but needed by multiple per-module
  property files.

- **Targeted strategies over rejection sampling where possible.**
  Properties like severity classification use strategies that
  generate known-angle paths (draw from a small discrete set of
  angles like 30°, 45°, 50°, 60°, 75°, 90°) rather than random
  angles with post-hoc filtering.  This is simpler, deterministic,
  and faster at 100+ iterations.  Properties that need full input
  space coverage (clearance, creepage) use the existing
  `realistic_routing_results` strategy.

- **Internal helpers are importable for targeted testing.**  Several
  properties need to test internal functions directly (e.g.,
  `_classify_severity` for R4, `_check_via` for R6).  These are
  already public-ish (no `__` prefix) and imported in existing tests
  (`test_copper_balance_boundary.py` imports `_via_annular_area`).

- **Existing generic invariant tests are unchanged.**  No edits to
  `test_dfm_hypothesis_fuzzing.py`.  The new properties are additive.

## Implementation Units

### U1. Acid Trap Property Tests

- **Goal:** Verify severity classification correctness (R4) and trace-width
  monotonicity (R5).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_acid_trap_properties.py` *(new)*
- **Dependencies:** U9 (targeted strategies), existing Hypothesis infra
- **Approach:**
  - R4: Import `_classify_severity` and test with a small fixed set of
    known angles.  The strategy generates angles drawn from
    `{30, 44, 45, 52, 60, 75, 89, 90, 120}` and widths from
    `{0.1, 0.2, 0.5}`.  Property: classification matches the
    `<45°=high, 45-60°=medium, 60-90°=low, ≥90°=no trap` contract.
    Width demotion is verified separately with fixed angle/width
    pairs.
  - R5: A strategy generates two identical paths differing only in
    trace width (`w1=0.15, w2=0.5`).  Property: the wider path
    produces ≤ traps than the narrower one.
- **Test Scenarios:**
  - TS1. 30° angle → `"high"` severity regardless of width
  - TS2. 50° angle with 0.2mm width → `"medium"`; with 0.1mm width → `"low"`
  - TS3. 65° angle → `"low"` (any width)
  - TS4. 90° angle → no trap generated
  - TS5. Wider trace produces ≤ traps for identical geometry
- **Patterns to Follow:** `test_acid_trap_boundary.py` — same module,
  same import paths, same `@given` + `@settings` decorator pattern.

### U2. Annular Ring Property Tests

- **Goal:** Verify ring-width formula correctness (R6) and layer-aware
  thresholds (R7).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_annular_ring_properties.py` *(new)*
- **Dependencies:** U9, existing Hypothesis infra
- **Approach:**
  - R6: Import `_check_via`.  Strategy generates Via objects with known
    `(diameter, drill)` pairs drawn from `{(1.0, 0.5), (0.6, 0.3),
    (0.3, 0.2)}`.  Property: the violation's `actual_ring_width`
    equals `(diameter - drill) / 2` within 1e-9 tolerance.
  - R7: Generate a via with internal-only layers (`In1.Cu` →
    `In2.Cu`).  Property: if it passes the internal threshold
    (`min_annular_ring * 0.5`), it must also pass the external
    threshold (`min_annular_ring`) at the same dimensions.  The
    external threshold is ≤ the internal threshold because it
    permits larger rings.
- **Test Scenarios:**
  - TS1. Via (1.0mm pad, 0.5mm drill) → ring width = 0.25mm exactly
  - TS2. Via (0.6mm pad, 0.3mm drill) → ring width = 0.15mm exactly
  - TS3. Microvia with `via_type="microvia"` uses `microvia_ring_mm`
    threshold, not external threshold
  - TS4. Internal-only via passes → also passes when external (same
    pad/drill)
- **Patterns to Follow:** `test_annular_ring_boundary.py`.

### U3. Creepage Property Tests

- **Goal:** Verify HV self-check exclusion (R8) and creepage ≥ clearance
  floor (R9).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_creepage_properties.py` *(new)*
- **Dependencies:** U9, existing `realistic_routing_results` strategy
- **Approach:**
  - R8: Use `@given` with `realistic_routing_results`.  Property:
    iterate every `CreepageViolation` in the report and assert
    `v.hv_net != v.lv_net`.  HV nets are never checked against
    themselves.
  - R9: Import `_calculate_required_creepage`.  For a range of
    voltages `{15, 30, 50, 100, 150, 250, 300, 600}`, compute
    creepage distance and assert it ≥ the general clearance floor
    (0.127mm, the project's 5mil default).  This is a table-lookup
    property, not a fuzzed one.
- **Test Scenarios:**
  - TS1. Fuzzed: 200 iterations of realistic routing results, every
    violation has distinct HV and LV nets
  - TS2. Table: 15V → 0.13mm ≥ 0.127mm (borderline case)
  - TS3. Table: 600V → 8.0mm ≥ 0.127mm
- **Patterns to Follow:** `test_creepage_boundary.py` and the
  existing `realistic_routing_results` strategy from
  `test_dfm_hypothesis_fuzzing.py`.

### U4. Clearance Property Tests

- **Goal:** Verify violation validity (R10) and layer independence (R11).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_clearance_properties.py` *(new)*
- **Dependencies:** U9, existing `realistic_routing_results` strategy
- **Approach:**
  - R10: Use `@given` with `realistic_routing_results`.  Property:
    every `ClearanceViolation` satisfies `v.actual_clearance <
    v.required_clearance`.  If `actual >= required`, the violation
    is a false positive.
  - R11: A targeted strategy generates N nets all on `F.Cu`, then
    adds one net on `B.Cu`.  Property: clearance violations among
    the original F.Cu nets are unchanged.  This is a more targeted
    version of the existing `test_clearance_layer_independence`
    test; the new version uses a strategy that guarantees the
    added net is on a disjoint layer.
- **Test Scenarios:**
  - TS1. Fuzzed: 200 iterations, every violation has actual < required
  - TS2. 5 nets on F.Cu, add 1 net on B.Cu → F.Cu clearance results
    unchanged
  - TS3. 2 nets total, both on same layer → violations only between
    those two nets (no spurious self-violations)
- **Patterns to Follow:** `test_clearance_boundary.py`, existing
  `test_clearance_layer_independence_different_net` in
  `test_dfm_hypothesis_fuzzing.py` (lines 685-771).

### U5. Teardrop Property Tests

- **Goal:** Verify connection-type partition (R12) and datum-point
  placement (R13).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_teardrop_properties.py` *(new)*
- **Dependencies:** U9, existing strategies
- **Approach:**
  - R12: Use `@given` with `realistic_routing_results`.  Property:
    `report.teardrop_count == report.via_teardrop_count +
    report.pad_teardrop_count`.  Every teardrop is classified
    exactly once.
  - R13: Generate a path with a known via at a known coordinate,
    and verify the generated teardrop's `connection_point` lies on
    one of the route's path segments (distance to the closest
    segment ≤ 1e-9).  This needs a targeted strategy that places a
    via at a known endpoint of a multi-segment path.
- **Test Scenarios:**
  - TS1. Fuzzed: count partition holds for 200 random inputs
  - TS2. Known geometry: path [(0,0), (10,0), (10,10)], via at
    (10,0) → teardrop connection_point on segment [(0,0), (10,0)]
    or [(10,0), (10,10)]
  - TS3. Empty input → both counts zero (already covered by
    empty-is-zero, re-verified)
- **Patterns to Follow:** `test_teardrop_boundary.py`.  Note:
  `enable_pad_teardrops=True` is currently a no-op; R12 must
  account for this by verifying `via + pad == total` even when
  `pad == 0`.

### U6. Thermal Relief Property Tests

- **Goal:** Verify power-net scoping (R14) and spoke count
  consistency (R15).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_thermal_relief_properties.py` *(new)*
- **Dependencies:** U9, existing strategies
- **Approach:**
  - R14: Targeted strategy generates one power net (matching
    `_POWER_NET_PATTERN`, e.g., "GND") and one signal net (e.g.,
    "SIG1").  Property: the power net gets thermal reliefs; the
    signal net gets none.
  - R15: Use `@given` with `realistic_routing_results` configured
    with `spoke_count=4`.  Property: every `ThermalRelief` in the
    report has `tr.spoke_count ≤ spoke_count`.  Additionally,
    `report.total_spokes == sum(tr.spoke_count for tr in
    report.thermal_reliefs)`.
- **Test Scenarios:**
  - TS1. Power net "GND" with vias → reliefs generated; signal net
    "SIG1" with vias → zero reliefs
  - TS2. Fuzzed: `spoke_count=4` → all reliefs have ≤ 4 spokes
  - TS3. Fuzzed: total_spokes property matches sum of individual
    spoke counts
- **Patterns to Follow:** `test_thermal_relief_boundary.py`.

### U7. Copper Balance Property Tests

- **Goal:** Verify layer count invariant (R16) and area bounding (R17).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_copper_balance_properties.py` *(new)*
- **Dependencies:** U9, existing strategies
- **Approach:**
  - R16: Use `@given` with `realistic_routing_results`.  Property:
    `report.balanced_layer_count + report.unbalanced_layer_count ==
    len(report.layer_balances)`.
  - R17: Use `@given` with `realistic_routing_results`.  Property:
    for each `lb` in `report.layer_balances`, `lb.copper_area_mm2 ≤
    board_width * board_height`.  Additionally,
    `lb.copper_area_mm2 ≥ 0.0` (the area is non-negative).
- **Test Scenarios:**
  - TS1. Fuzzed: layer count invariant holds for 200 random inputs
  - TS2. Fuzzed: no per-layer area exceeds total board area
  - TS3. Empty input: 4 layers, 4 unbalanced (0% copper), all
    areas zero, invariant still holds
- **Patterns to Follow:** `test_copper_balance_boundary.py`.

### U8. Manufacturing Report Property Tests

- **Goal:** Verify sub-report traceability (R18).
- **Files:**
  `packages/temper-placer/tests/router_v6/test_manufacturing_report_properties.py` *(new)*
- **Dependencies:** U1-U7 (runs the composite report after all
  sub-modules are tested), U9
- **Approach:**
  - R18: Use `@given` with `realistic_routing_results`.  Run all 7
    DFM modules, build the composite `ManufacturingReport`.  Compute
    `expected_total = sum of individual violation counts` per the
    documented formula (accounting for teardrop/thermal sentinel
    flags).  Property: `report.total_violations == expected_total`.
    The sentinel logic is: `teardrop_failure = 1 if
    teardrop_count == 0 else 0` and `thermal_failure = 1 if
    relief_count == 0 else 0`.
- **Test Scenarios:**
  - TS1. Fuzzed: composite total matches sub-report sum for 200
    random inputs
  - TS2. Empty input: total_violations accounts for copper-balance
    sentinel (4 unbalanced layers) + teardrop/thermal sentinels
  - TS3. All-passing input (contrived): total_violations == 0
- **Patterns to Follow:** `test_manufacturing_report.py`,
  `test_dfm_interaction.py` for composite report construction.

### U9. Shared Targeted Strategy Module

- **Goal:** Provide reusable Hypothesis strategies for the per-module
  property files.
- **Files:**
  `packages/temper-placer/tests/router_v6/dfm_property_strategies.py` *(new)*
- **Dependencies:** None (leaf unit, consumed by U1-U8)
- **Approach:**
  Strategies to implement (each as `@st.composite`):
  1. `known_angle_path` — generates a 3-point path (single vertex)
     with a known angle.  Parameters: `angle_degrees` (drawn from a
     discrete set) and `layer`.  Returns a `RoutePath` + `width`.
  2. `known_dimension_via` — generates a `Via` with specified
     `(diameter, drill)` pair drawn from known sets, plus optional
     `via_type`.  Returns a `Via` object.
  3. `mixed_net_routing_results` — generates `RoutingResults` with
     a mix of power nets and signal nets (reuses the existing
     `_NET_NAME_VOCAB` from `test_dfm_hypothesis_fuzzing.py`).
  4. `same_layer_net_set` — generates N nets all on the same layer,
     useful for clearance/creepage layer independence tests.
  The module also re-exports `realistic_routing_results` from
  `test_dfm_hypothesis_fuzzing` so per-module files have a single
  import source.
- **Test Scenarios:**
  - TS1. `known_angle_path(angle=45)` produces a path whose computed
    angle at the vertex is 45° ± 1e-9
  - TS2. `known_dimension_via(dia=1.0, drill=0.5)` produces a via
    with those exact dimensions
  - TS3. `mixed_net_routing_results()` includes at least one power
    net and one signal net
  - TS4. `same_layer_net_set(n=5)` produces 5 nets all on `F.Cu`
- **Patterns to Follow:** `dfm_boundary_constants.py` for shared
  helper placement; `temper_testing/strategies.py` for
  `@st.composite` pattern.

## Risks

- **Strategy import cycles.**  If `dfm_property_strategies.py`
  imports strategies from `test_dfm_hypothesis_fuzzing.py`, that
  file imports from DFM modules which in turn import from
  `routing_results`.  Mitigation: keep strategy definitions in the
  shared module; only re-export, don't circular-import.  If
  `realistic_routing_results` is pulled into
  `dfm_property_strategies.py`, move it there and re-import it in
  the fuzzing file.

- **Test execution time.**  7 new property files × 100-200 iterations
  × O(N²) clearance checks = potential CI slowdown.  Mitigation: use
  the same `deadline=2000` + `suppress_health_check=[too_slow]`
  settings as the existing suite.  Targeted strategies (known-angle
  paths, etc.) are cheap — the cost is in clearance/creepage
  properties that use `realistic_routing_results`.

- **Internal API drift.**  Properties importing `_classify_severity`,
  `_check_via`, `_calculate_required_creepage` couple to internal
  helpers.  Mitigation: these are already imported in boundary
  tests; a rename would break existing tests too.

## Dependencies and Sequencing

```
U9 (shared strategies) ──┬── U1 (acid trap)
                         ├── U2 (annular ring)
                         ├── U3 (creepage)
                         ├── U4 (clearance)
                         ├── U5 (teardrop)
                         ├── U6 (thermal relief)
                         └── U7 (copper balance)
                                   │
                                   └── U8 (manufacturing report)
```

- **Phase 1: U9.**  Build the shared strategy module.  Move
  `realistic_routing_results` and its dependencies
  (`realistic_paths`, `realistic_vias`) from
  `test_dfm_hypothesis_fuzzing.py` into `dfm_property_strategies.py`.
  Update the fuzzing file to import from the new module.  This
  de-duplicates without breaking existing tests.

- **Phase 2: U1-U7 (parallel).**  Each per-module property file is
  independent of the others.  Can be built in any order.  Recommend
  starting with the simpler targeted strategies (U1 acid trap, U2
  annular ring) to validate the strategy module before tackling
  fuzzed properties (U3 creepage, U4 clearance).

- **Phase 3: U8.**  Depends on U1-U7 only for confidence that
  sub-module reports are correct; structurally it only needs U9.

- **Phase 4: Integration.**  Run the full test suite
  (`pytest tests/router_v6/test_*properties*.py
  tests/router_v6/test_dfm_hypothesis_fuzzing.py`) and verify SC3.

## Scope Boundaries

- **In scope:** 15 domain-correctness properties (R4-R18) across 7
  modules + 1 shared strategy module.  7 new test files + 1 new
  helper file.

- **Out of scope:** Fixing known bugs (creepage `ZeroDivisionError`,
  thermal-relief non-determinism).  Modifying DFM module source
  code.  Adding properties to non-DFM stages.  Integration/ordering
  tests (already in `test_dfm_interaction.py`).

## Sources

- `docs/brainstorms/2026-06-25-dfm-property-tests-requirements.md`
  — origin requirements
- `packages/temper-placer/tests/router_v6/test_dfm_hypothesis_fuzzing.py`
  — existing 6-invariant PBT suite and strategies to move
- `packages/temper-placer/tests/router_v6/test_*_boundary.py`
  — per-module boundary test patterns
- `packages/temper-placer/tests/router_v6/dfm_boundary_constants.py`
  — shared test helper precedent
- `packages/temper-testing/src/temper_testing/strategies.py`
  — domain strategy patterns
- `packages/temper-placer/src/temper_placer/router_v6/`
  — all 8 DFM module source files (acid_trap_detection through
  manufacturing_report)
