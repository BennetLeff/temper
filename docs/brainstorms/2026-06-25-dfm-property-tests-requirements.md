---
date: "2026-06-25"
topic: dfm-property-tests
---

## Summary

Add per-module domain-correctness property tests for all 7 DFM modules in
the Router V6 pipeline, plus a shared strategy module providing targeted
Hypothesis strategies.  This complements the existing six generic
invariants (no-crash, non-negative, consistency, idempotence,
empty-is-zero, layer independence) with properties that verify each
module produces *correct* results, not just well-formed reports.

## Problem Frame

The existing property-based tests in `test_dfm_hypothesis_fuzzing.py`
verify the container — every DFM module returns a well-formed report
without crashing.  They do not verify the content.  A module could pass
every invariant while producing wrong answers: miscategorizing acid-trap
severity, miscomputing annular ring width, or flagging creepage
violations at distances that meet the spec.

The git history shows the current PBT + boundary test suites caught ~65
edge-case bugs across the DFM modules.  But the boundary suites test
specific hand-crafted inputs; they cannot discover the kind of
systematic correctness regressions that property-based testing across the
full input space can.

Adding domain-correctness properties closes this gap — the PBT suite
moves from "the modules don't crash" to "the modules produce defensible
results."

## Requirements

### Structure

- R1. Each DFM module with domain-specific invariants gets a dedicated
  property test file at
  `packages/temper-placer/tests/router_v6/test_<module>_properties.py`.
- R2. A shared strategy/driver module at
  `packages/temper-placer/tests/router_v6/dfm_property_strategies.py`
  provides targeted Hypothesis strategies reusable across per-module
  files.  Existing strategies (`realistic_routing_results`, etc.) remain
  in `test_dfm_hypothesis_fuzzing.py` unless they are needed by the new
  properties, in which case they move to the shared module.
- R3. The six generic invariants in
  `test_dfm_hypothesis_fuzzing.py` are left unchanged.

### Acid Trap Detection

- R4. **Severity monotonicity.**  For any single-vertex path with angle
  *θ*, `classify_severity(θ)` returns `"high"` when θ < 45°, `"medium"`
  when 45° ≤ θ < 60°, `"low"` when 60° ≤ θ < 90°, and no trap when θ ≥
  90°.
- R5. **Trace-width monotonicity.**  For two traces with identical
  geometry but different widths (*w₁* < *w₂*), the wider trace produces
  ≤ traps.  Verifies the width-tolerant angle thresholds work in the
  expected direction.

### Annular Ring Check

- R6. **Ring-width formula.**  For any via with pad diameter *D* and
  drill diameter *d*, the computed annular ring width equals
  (*D* − *d*) / 2 exactly, within floating-point tolerance.
- R7. **External-vs-internal thresholds.**  An via that passes on an
  internal layer (stricter IPC-6016 external minimum) also passes when
  assigned to an external layer with the same dimensions.

### Creepage Check

- R8. **No self-check.**  No HV net is ever checked against itself.
  The reported violations must have `hv_net != lv_net`.
- R9. **Creepage ≥ clearance floor.**  The required creepage distance
  for any voltage must be ≥ the general clearance minimum for the same
  net class.  Creepage is a stricter constraint by definition.

### Clearance Check

- R10. **Violation validity.**  Every reported violation has
  `actual_clearance < required_clearance`.  No false positives.
- R11. **Layer independence — addition.**  Adding a net to a different
  layer from all existing nets does not increase the clearance violation
  count among the original same-layer nets.

### Teardrop Generation

- R12. **Connection-type partition.**  `teardrop_count ==
  via_teardrop_count + pad_teardrop_count`.  Every teardrop is
  exhaustively categorized.
- R13. **Datum point on connection.**  Each teardrop's
  `connection_point` lies on one of the route's path segments (within
  floating-point tolerance).

### Thermal Relief

- R14. **Power-net scoping.**  Thermal relief spokes are only inserted
  for nets matching the power-net pattern (`_POWER_NET_PATTERN`).  No
  spoke is inserted for a non-power net.
- R15. **Spoke count consistency.**  When `spoke_count` is configured,
  every inserted relief has ≤ `spoke_count` spokes.

### Copper Balance

- R16. **Layer count invariant.**  `balanced_layer_count +
  unbalanced_layer_count == total_layers` (the number of layer-balance
  entries in the report).
- R17. **Area bounding.**  For each layer, `copper_area_mm2 ≤
  board_width × board_height`.  Copper area cannot exceed the physical
  board area.

### Manufacturing Report

- R18. **Sub-report traceability.**  Total violations in the composite
  report equals the sum of violation counts from each sub-report,
  modulo any sentinel-based flagging documented in `ManufacturingReport`.

## Key Decisions

- **Per-module files over single-file extension.**  The house style
  established by `test_<module>_boundary.py` keeps each module's tests
  discoverable and short.  A single growing file past 1,500 lines
  would bury module-specific properties among generic invariants.
- **Shared strategy module over in-file duplication.**  Several
  properties need targeted strategies (known-angle paths, known-
  dimension vias) that would otherwise be copied.  Shared strategies
  in `dfm_property_strategies.py` follow the existing
  `dfm_boundary_constants.py` precedent.
- **Targeted strategies preferred over generative where possible.**
  For properties like severity classification and ring-width formula,
  strategies that generate *known* inputs (a 43° angle, a 50° angle,
  etc.) are simpler and more reliable than generative strategies that
  would need post-hoc filtering to verify the property held.

## Success Criteria

- SC1. Every property test runs at ≥100 Hypothesis iterations with a
  2000ms deadline and passes consistently.
- SC2. At least one property per DFM module exercises a correctness
  condition beyond the six generic invariants.
- SC3. The existing six-invariant suite in
  `test_dfm_hypothesis_fuzzing.py` continues to pass unchanged.

## Scope Boundaries

### Deferred for later

- Fixing the two known unfixed bugs (creepage `ZeroDivisionError`,
  thermal-relief non-deterministic spoke geometry).  These remain
  `xfail`-tagged.
- Extending property tests to non-DFM stages (routing, placement).
- Adding metamorphic / round-trip properties (e.g., "teardrop insertion
  followed by teardrop removal on the same path is identity").

### Outside this work's identity

- Writing the properties in a different framework (no Hypothesis
  alternative).  Hypothesis is the established dependency.
- Property tests for the pipeline orchestration layer
  (`_run_manufacturing_drc`, `dfm_fail_on` gate logic).  These are
  interaction tests, already covered by `test_dfm_interaction.py`.

## Dependencies / Assumptions

- **Hypothesis ≥ 6.148.7** is already a project dependency.
- **Existing strategies** in `test_dfm_hypothesis_fuzzing.py` and
  `temper_testing/strategies.py` are stable and reusable.
- **DFM module public APIs** (`detect_acid_traps`, `verify_creepage`,
  etc.) are the test surface; internal helpers are reachable for
  targeted testing when the contract is defined at the helper level
  (e.g., `_classify_severity`).

## Outstanding Questions

### Deferred to Planning

- Whether targeted strategies for acid-trap severity should generate
  exact-known-angle paths or random paths with angle rejection
  sampling.  Exact-known is simpler but tests fewer angle values;
  rejection sampling is more thorough but complicates the strategy.
- Whether the shared strategy module should live at
  `tests/router_v6/dfm_property_strategies.py` or extend the existing
  `dfm_boundary_constants.py`.

## Sources / Research

- `packages/temper-placer/tests/router_v6/test_dfm_hypothesis_fuzzing.py`
  — existing 6-invariant PBT suite
- `packages/temper-placer/tests/router_v6/test_dfm_interaction.py`
  — DFM interaction and pipeline tests
- `packages/temper-placer/tests/router_v6/test_*_boundary.py`
  — per-module boundary test suite establishing the house style
- `packages/temper-placer/tests/router_v6/dfm_boundary_constants.py`
  — shared boundary constants, precedent for shared test helpers
- `packages/temper-testing/src/temper_testing/strategies.py`
  — domain Hypothesis strategies (board, component, placement)
- Git history: ~65 edge-case bugs fixed across DFM modules discovered
  by PBT + boundary suites
