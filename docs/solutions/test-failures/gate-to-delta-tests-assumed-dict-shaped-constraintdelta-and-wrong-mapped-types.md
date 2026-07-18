---
title: "test_physics_gate.py/test_quality_gate.py/test_stackup_gate.py's to_delta() tests assumed a dict-shaped ConstraintDelta and had 3 wrong VIA_COUNT/SLOP/CURRENT_DENSITY mapping expectations, contradicted by test_delta_mapper.py's own established tests"
date: "2026-07-18"
category: test-failures
module: temper_placer
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "TypeError: 'ConstraintDelta' object is not subscriptable"
  - "AttributeError: 'ConstraintDelta' object has no attribute 'get'"
  - "AssertionError: assert ConstraintDelta(...) is None -- for VIA_COUNT and empty-artifacts SLOP violations"
  - "AssertionError: assert None is not None -- for CURRENT_DENSITY in test_stackup_gate.py"
  - "IECCreepageGate's own three tests failed with GateStatus.CLEAN instead of VIOLATIONS -- a real, separate interaction bug with the _drc_api.py DrcError.components fix"
root_cause: test_isolation
resolution_type: test_fix
tags:
  - temper-placer
  - cp-sat
  - gates
  - delta-mapper
  - stale-test
  - hidden-by-ci
---

# `to_delta()` tests assumed a dict-shaped `ConstraintDelta`, plus 3 wrong mapping expectations and one real interaction bug

## Problem

13 tests across `test_physics_gate.py`, `test_quality_gate.py`, and
`test_stackup_gate.py` failed after CI reached the "CP-SAT Placer Tests"
step for the first time (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)).
Two independent problems, plus one real bug this investigation surfaced
and fixed:

1. **Dict-shaped access on a dataclass.** Several tests called
   `delta["type"]` or `delta.get("type", "")` against the return value of
   `Gate.to_delta()`, which is a `ConstraintDelta` dataclass
   (`.constraint`, `.reason`, `.priority`) -- not subscriptable, no
   `.get()`.
2. **Three wrong "returns None" expectations.** `VIA_COUNT` (in both
   `test_physics_gate.py` and `test_quality_gate.py`) and empty-artifact
   `SLOP` (in `test_quality_gate.py`) were asserted to produce `delta is
   None`. `test_delta_mapper.py`'s own established, already-passing tests
   (`test_via_count_maps_to_keepout`, `test_slop_fallback_zone_name`)
   directly contradict this -- both violation types have always mapped
   to a real `KeepoutConstraint` delta via `DeltaMapper.map()`.
   Conversely, `test_stackup_gate.py::test_to_delta_current_density`
   expected the *opposite* -- a real delta -- for `CURRENT_DENSITY`,
   again contradicted by `test_delta_mapper.py`'s
   `test_unmapped_type_returns_none[CURRENT_DENSITY]`, which confirms
   current-density violations are intentionally unmapped (no
   placement-based fix exists for a routing/trace-width problem).
3. **A real bug**, found while investigating why `IECCreepageGate`'s
   three creepage-detection tests failed with `GateStatus.CLEAN` instead
   of `VIOLATIONS`: `IECCreepageGate.check()` reads `err.components` to
   find net names for HV/LV classification, but `components` (per the
   fix in
   [`drc-api-wrapper-components-and-location-always-empty.md`](drc-api-wrapper-components-and-location-always-empty.md))
   only ever contains *component references*, extracted from "of REF"
   patterns -- never net names. Bare copper track/via clearance items
   (which is what creepage violations are) have no owning component at
   all; their net name is embedded in square brackets instead (`"Via
   [GND] on F.Cu - B.Cu"`). `IECCreepageGate` was checking the wrong
   field entirely -- this bug was invisible before because the test
   fixtures independently used the same old, never-real `"reference"`
   key schema the pre-fix `_drc_api.py` also assumed, so test and (old)
   implementation happened to agree with each other while both
   disagreed with real kicad-cli output.

## Resolution

**Test-only fixes** (13 of the original failures): replaced
`delta["type"]`/`delta.get(...)` with the established
`type(delta.constraint).__name__` pattern already used correctly in
`test_delta_mapper.py`. Corrected the three wrong mapping expectations
to match `test_delta_mapper.py`'s cross-verified ground truth: renamed
and rewrote `test_physics_to_delta_via_count_returns_none` →
`test_physics_to_delta_via_count_returns_keepout`,
`test_to_delta_via_count_returns_none` →
`test_to_delta_via_count_returns_keepout`,
`test_to_delta_no_artifacts_in_context_returns_none` →
`test_to_delta_no_artifacts_in_context_falls_back_to_generic_keepout`,
and `test_to_delta_current_density` →
`test_to_delta_current_density_returns_none`, each asserting the real,
tested `DeltaMapper` behavior instead.

**Real code fix**: added a `nets: list[str]` field to `DrcError`/
`DrcWarning` in `_drc_api.py`, populated by a new
`_extract_net_from_item_description()` helper (extracts the bracketed
net name KiCad embeds for net-owned items, e.g. `Via [GND] on ...`,
`Pad 2 [net_name] of REF on ...`) alongside the existing `components`
extraction. Fixed `IECCreepageGate.check()` to read `err.nets` instead
of `err.components`. Checked for other consumers needing this
distinction before adding the field (grepped `gates.py` and
`regression/`) -- `IECCreepageGate` is the only one. Updated
`test_physics_gate.py`'s clearance-violation test fixtures (6 call
sites) from the old, never-real `{"type": "track", "reference": "X"}`
item shape to a real kicad-cli-style `{"description": "Track [X] on
F.Cu"}` shape.

**Verification:** `test_physics_gate.py` 21/21 (was 13/21),
`test_quality_gate.py` 16/16 (was 13/16), `test_stackup_gate.py` 16/16
(was 15/16). Re-ran `test_drc_api_parsing.py`/`test_drc_runner.py`/
`test_drc.py` (23 tests) after the `nets` field addition -- all still
pass, no regressions. Ran the full cluster together (181 tests across
9 files touching `gates.py`/`_drc_api.py`) -- all pass.

## Why This Matters

The `IECCreepageGate` bug is the most consequential finding in this
batch: it's a real, currently-live gate meant to enforce IEC 60335-1
creepage clearance between high-voltage and low-voltage nets in the
place→route loop's `all_gates` mode, and it was **silently reporting
`CLEAN` for every board, always**, because it read a field that could
never contain what it needed. Unlike most of this session's stale-test
findings, this one had real safety-relevant consequences if `--all-gates`
were ever used in production -- a genuine HV/LV creepage violation would
never have been caught.

## Prevention

- **When one test file's fixture and another test file's fixture cover
  the same underlying function/type, and they disagree, treat that as a
  signal, not a coincidence.** `test_delta_mapper.py` and the three gate
  test files tested the same `DeltaMapper.map()` mapping table from two
  different angles; where they disagreed, the dedicated, focused test
  suite (`test_delta_mapper.py`) was the more reliable ground truth.
- **A field that only extracts one kind of identifier (component refs)
  will silently return nothing useful for callers that actually need a
  different kind (net names) -- and a wrong test fixture using the
  pre-fix, never-real schema can hide that mismatch indefinitely.** This
  is the same "test and implementation share a wrong assumption"
  pattern as the original `drc-api-wrapper` bug this net-extraction gap
  was discovered while investigating.

## Related Issues

- [`docs/solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md`](../logic-errors/drc-api-wrapper-components-and-location-always-empty.md)
  — the original DRC wrapper fix; this doc adds the `nets` field that
  fix's `components`-only design was missing.
- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run these
  test files for the first time.
