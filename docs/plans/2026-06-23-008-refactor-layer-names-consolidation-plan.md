---
title: Layer Names Consolidation
type: refactor
status: active
date: 2026-06-23
origin: docs/brainstorms/2026-06-23-layer-names-consolidation-requirements.md
---

# Layer Names Consolidation

## Summary

Introduce a `LayerIndex` IntEnum and a small surface of canonical layer constants and helpers in `core/board.py`, then big-bang migrate every duplicated layer representation across the placer (`"F.Cu"`/`"In1.Cu"`/... literals, name↔index dicts, numeric `INTERNAL_LAYERS`, string `PLANE_LAYERS`, side-to-layer-name ternaries, and string `GROUND`/`POWER` defaults) to that single source of truth. The result: an engineer adding or renaming a layer edits one place, and the existing 4-layer closure tests still produce bit-identical routing output.

---

## Problem Frame

The placer has accumulated three competing representations of the same concept — string names, numeric indices, and bidirectional dicts — across at least 13 files. They drift silently: `INTERNAL_LAYERS` in `routing/constraints/drc_oracle.py:60` uses `{1, 2}` (numeric) while `PLANE_LAYERS` in `deterministic/stages/via_validation.py:21` uses `{"In1.Cu", "In2.Cu"}` (string) for the same plane-layer concept. Every layer-related change is a manual find-and-replace across the codebase, and a missed call site is a silent runtime bug (wrong layer, off-by-one, "Unknown" lookup). The `Layer` dataclass and `LayerStackup.default_4layer()` in `core/board.py` already establish layer as a first-class concept; the canonical enum should live alongside them (see origin: `docs/brainstorms/2026-06-23-layer-names-consolidation-requirements.md`).

This is the first of four sequential consolidations (layer-names → pad-position → net classification → A* primitives).

---

## Requirements

- R1. `LayerIndex` is an `IntEnum` defined in `core/board.py` with members `F_CU = 0`, `IN1_CU = 1`, `IN2_CU = 2`, `B_CU = 3`. Each member's string representation is the standard KiCad name (`"F.Cu"`, `"In1.Cu"`, `"In2.Cu"`, `"B.Cu"`) via a `__str__` method (the enum's own `.name` returns `"F_CU"` etc., which is not the KiCad name; do not conflate).
- R2. `core/board.py` exposes `STANDARD_LAYER_ORDER: tuple[LayerIndex, ...] = (LayerIndex.F_CU, LayerIndex.IN1_CU, LayerIndex.IN2_CU, LayerIndex.B_CU)`. `LayerStackup.default_4layer()` builds its `layers` list from this constant.
- R3. `core/board.py` exposes `PLANE_LAYER_INDICES: frozenset[LayerIndex] = frozenset({LayerIndex.IN1_CU, LayerIndex.IN2_CU})`. Replaces the string `PLANE_LAYERS` in `via_validation.py` and the numeric `INTERNAL_LAYERS` in `drc_oracle.py`.
- R4. `core/board.py` exposes helpers `is_plane_layer(name_or_index: str | LayerIndex) -> bool`, `is_signal_layer(name_or_index: str | LayerIndex) -> bool`, `side_to_layer_name(side: int) -> str` (raises `ValueError` for non-{{0, 1}}), and `layer_name_to_index(name: str) -> LayerIndex` (raises `KeyError` for unknown names).
- R5. `core/board.py` exposes `LAYER_IDX_TO_NAME: dict[LayerIndex, str]` and `LAYER_NAME_TO_IDX: dict[str, LayerIndex]` derived from the enum. The existing dicts in `sequential_routing_helpers.py:7-8` and the local dict in `drc_sweep.py:50` are removed; the local `_SMD_LAYER_NAME_TO_IDX` mirror in `router_v6/bottleneck_geometry.py:610` and any other in-module mirrors are removed and replaced with imports from `core/board.py`.
- R6. The 13 hard-coded `["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]` lists in `router_v6/astar_core.py:505`, `deterministic/stages/clearance_grid.py:529, 562`, `router_v6/copper_balance.py:84`, `deterministic/stages/via_validation.py:208`, `deterministic/stages/drc_sweep.py:202`, `io/kicad_parser.py:1275`, `io/kicad_exporter.py:224`, and the 4-element dicts in `sequential_routing_helpers.py:7-8` are replaced with references to `STANDARD_LAYER_ORDER` or `LAYER_NAME_TO_IDX`.
- R7. The string `PLANE_LAYERS` in `via_validation.py:21` and the numeric `INTERNAL_LAYERS` in `routing/constraints/drc_oracle.py:60` are both replaced with `PLANE_LAYER_INDICES`. All `in INTERNAL_LAYERS` and `in PLANE_LAYERS` checks are updated to work with `LayerIndex` (membership in `frozenset[LayerIndex]` is supported by Python's standard `Enum` hashing).
- R8. The two `layer = "F.Cu" if side == 0 else "B.Cu"` ternaries at `router_v6/pipeline.py:212` and `deterministic/pipeline.py:64` are replaced with `side_to_layer_name(side)`.
- R9. `core/net_types.py:468-469` (`GROUND: "In1.Cu"`, `POWER: "In2.Cu"` in `_default_layer`) is updated so the return type is `LayerIndex` (not `str`); all call sites that consume the return value are updated to work with the enum (including string-formatting and `==` comparisons).
- R10. `LayerStackup.default_4layer()` is rewritten to use `STANDARD_LAYER_ORDER` for layer names. `copper_weight` and `is_routable` remain instance-level. `default_2layer()` is unchanged.
- R11. `pytest` on `tests/` passes, `ruff check` is clean, and `uv run python scripts/import_linter_gate.py` reports zero new violations after the migration.
- R12. The placer's 4-layer integration tests (golden fixture parity, closure tests) produce the same routing output as before the migration — bit-identical trace paths, same `completion_rate`, same `success_count`, same DRC violations.

**Origin actors:** (none — no actor IDs in origin)
**Origin flows:** (none — no F-IDs in origin)
**Origin acceptance examples:** AE1 (covers R1, R4), AE2 (covers R3, R7), AE3 (covers R6, R12)

---

## Scope Boundaries

- 6-layer board support (`io/kicad_exporter.py:1271-1277` extends the layer list to 6 layers) is **out of scope**. The 6-layer path keeps its inline list; this consolidation is strictly 4-layer. A future doc may extend `LayerIndex` to 6 layers. (Verified: no tests use a `default_6layer` method or 6-layer `LayerStackup`; only the `kicad_exporter` 6-layer branch and the inline parser list reference 6 layers.)
- Routing-side layer assignment (which layers a net *can* use) is owned by `router_v6/channel_assignment.py` and friends — out of scope. The existing `routing/layer_assignment.py` `Layer` enum (`L1_TOP`/`L2_GND`/`L3_PWR`/`L4_BOT`) is also out of scope (different concept: routing capability, not KiCad layer name).
- The `Layer.layer_type` string field ("signal"/"plane"/"mixed") at `core/board.py:138` is adjacent but out of scope — could become a `LayerType` enum in a future doc.
- Linter / CI enforcement of enum usage (a `ruff` rule banning raw layer strings in layer contexts) is out of scope. R1–R12 cover the migration; enforcement is a follow-up.
- The other three consolidations (pad-position, net classification, A* primitives) each get their own doc — out of scope here.

### Deferred to Follow-Up Work

- **Ruff rule banning raw layer strings** in known layer contexts: separate doc, once the enum is in place and the migration is stable.
- **6-layer `LayerIndex` extension**: separate doc, after the 4-layer migration is verified.
- **`LayerType` enum** to replace the `Layer.layer_type` string field: separate doc.

---

## Context & Research

### Relevant Code and Patterns

- `core/board.py:125-140` — `Layer` dataclass (sibling of new `LayerIndex`).
- `core/board.py:143-241` — `LayerStackup` dataclass, including the instance method `is_plane_layer(layer_idx: int)` at line 162 (signature collision risk with the new module-level `is_plane_layer` — see Key Technical Decisions).
- `core/board.py:170-195` — `default_4layer()` and `default_2layer()` classmethods (R10 target).
- `routing/constraints/drc_oracle.py:60` — `INTERNAL_LAYERS = frozenset({1, 2})` and the call site at line 520 (`layer in INTERNAL_LAYERS`).
- `deterministic/stages/via_validation.py:21` — `PLANE_LAYERS` frozenset and call site at line 237.
- `deterministic/stages/sequential_routing_helpers.py:7-8` — the two `LAYER_*` dicts (R5 target).
- `deterministic/stages/drc_sweep.py:50` — local `layer_name_to_idx` dict (R5 target, also R6 — needs to import from `core/board.py`).
- `deterministic/stages/sequential_routing.py:10, 884, 889, 904, 977, 1144, 1641, 1691, 1928, 1974-1975` — heavy consumer of `LAYER_IDX_TO_NAME.get(idx, "F.Cu")` (the `.get(..., "F.Cu")` default is itself a string-literal bug — see Key Technical Decisions).
- `router_v6/bottleneck_geometry.py:610` — local `_SMD_LAYER_NAME_TO_IDX` mirror (R5).
- `core/net_types.py:465-475` — `_default_layer` returns string; called from multiple sites in the same module.
- `router_v6/astar_core.py:505`, `router_v6/copper_balance.py:84`, `deterministic/stages/clearance_grid.py:529, 562`, `deterministic/stages/via_validation.py:208`, `deterministic/stages/drc_sweep.py:202`, `io/kicad_parser.py:1275`, `io/kicad_exporter.py:224` — hard-coded 4-element layer lists (R6).
- `router_v6/pipeline.py:212`, `deterministic/pipeline.py:64` — `layer = "F.Cu" if side == 0 else "B.Cu"` ternaries (R8).
- `tests/core/test_board.py` — existing 4-layer stackup tests; new helper/constant tests land here.

### Institutional Learnings

- `docs/solutions/best-practices/` and `docs/solutions/architecture-patterns/` were spot-checked; no prior consolidation docs specifically for the layer-name pattern. The closest pattern is the safety-constant SSOT (plan `2026-06-22-002-feat-safety-constant-ssot-plan.md`) which established the "one canonical location, import-everywhere" convention this plan follows.
- The codebase has a strong existing pattern of dataclass + module-level constants colocated (see `LayerStackup` in `core/board.py`); the new `LayerIndex` and constants follow that convention.

### External References

None — this is a refactor within an established Python pattern (`enum.IntEnum` + module-level `frozenset`/`tuple` constants). Local patterns are sufficient; no external research needed.

---

## Key Technical Decisions

- **`__str__` for the KiCad name, not `.name`.** `IntEnum` inherits `.name` from `Enum`, which returns the Python identifier (`"F_CU"`, not `"F.Cu"`). The plan overrides `__str__` to return the KiCad name. Cost: `str(LayerIndex.F_CU) == "F.Cu"`, but `LayerIndex.F_CU.name == "F_CU"`. Documented in the enum's docstring. (Resolves the R1 wording "via a small class method or `__str__`".)
- **Naming collision on `is_plane_layer`.** `LayerStackup` has an instance method `is_plane_layer(layer_idx: int) -> bool` (line 162) that consults the `layer_type` field. The new module-level `is_plane_layer(name_or_index: str | LayerIndex) -> bool` is a different signature and different semantics (canonical names, not stackup instance state). They can coexist as long as no caller does `from core.board import is_plane_layer` and then calls it on a `LayerStackup` (which would silently break the instance method's contract). The plan keeps both; the method body is rewritten to delegate to the module function for clarity (`return is_plane_layer(self.layers[layer_idx].name)`) but the instance method stays for callers that need stackup-instance awareness.
- **Helpers accept `str | LayerIndex` (no `None`).** The deferred-to-planning question on R4 (whether to accept `None`) is resolved: the four canonical inputs are string or enum. Callers that have a possibly-`None` layer should default-arg to a known value or branch before calling. Avoids making the helper a `is_truthy` shim.
- **`STANDARD_LAYER_ORDER` is a `tuple`, not a `list`.** Immutable, hashable, can be the key of a dict if ever needed. No call site mutates it. (Resolves deferred R2 question.)
- **`PLANE_LAYER_INDICES` is a `frozenset`, not a `list`.** The two existing check sites (`layer in PLANE_LAYERS`, `layer in INTERNAL_LAYERS`) are membership tests. A `frozenset` is hashable (so the constant can be cached), and `in` is O(1). The two existing constant sites become imports of this one frozenset. (Resolves deferred R3 question.)
- **No new `default_6layer()` method.** Verified: no test or call site uses a 6-layer `LayerStackup`; only the `kicad_exporter.py:1271-1277` 6-layer branch and the inline parser list reference 6 layers. Out of scope per origin doc; the 6-layer path continues to use its inline layer list. (Resolves deferred 6-layer research question.)
- **`copper_weight` stays instance-level on `Layer`.** The canonicalization is on the names, not the weights. `default_4layer()` keeps the existing `2.0` for `F.Cu` and `1.0` for the others. (Resolves deferred R10 question.)
- **`LAYER_IDX_TO_NAME.get(idx, "F.Cu")` default is a string-literal bug.** Existing call sites in `sequential_routing.py` default to `"F.Cu"` when the index is out of range. After the migration, the import from `core/board.py` returns a `LayerIndex` key, and the fallback should be `LayerIndex.F_CU`. The plan updates these `.get(..., default)` calls to use the enum member as the default (or converts them to direct dict access since the index is always in range at those call sites — verification needed at implementation time, see Open Questions).
- **Big-bang migration, not staged.** Per origin Key Decision: intermediate states with both representations are confusing; review burden is bounded by reviewer patience, not diff size. Single PR, atomic.

---

## Open Questions

### Resolved During Planning

- **R2 (tuple vs list for `STANDARD_LAYER_ORDER`):** `tuple`. Immutable, hashable, right default for a constant. No call site mutates it.
- **R3 (frozenset vs list for `PLANE_LAYER_INDICES`):** `frozenset`. Supports `in`, hashable, O(1) membership. The two existing check sites are `in` tests, so the container must support that efficiently.
- **R4 (should helpers accept `None`?):** No. The four canonical inputs are string or enum. `None` is a different concept (unknown layer) that should be handled by the caller, not papered over by the helper.
- **R10 (canonicalization scope for `default_4layer`):** Names only. `copper_weight` and `is_routable` remain instance-level. The `Layer` dataclass keeps the same fields and same defaults.
- **6-layer case (research check):** No tests use a 6-layer `LayerStackup`. The 6-layer path lives entirely in `kicad_exporter.py:1271-1277` and `kicad_parser.py:1271-1277` (inline lists). Migration does not break it. No `default_6layer()` method needed.

### Deferred to Implementation

- **`LAYER_IDX_TO_NAME.get(idx, "F.Cu")` defaults in `sequential_routing.py`:** the original fallback is a string literal. After migration, the import returns a `LayerIndex` key. Whether to use `LayerIndex.F_CU` as the new default or to assert the index is in range (direct dict access) depends on the call-site contract — needs a per-call-site audit at implementation time. Either choice is acceptable; the test scenarios in U2 cover the in-range case.
- **Whether `_default_layer` in `core/net_types.py` should change its return annotation from `str` to `LayerIndex` (R9) or should return a `str` and convert at the call site:** direction is "return `LayerIndex`" (matches the rest of the migration), but the implementation may discover string-formatting sites that need `.name` or `str()` and the implementer should pick the cleanest local fix.

---

## Implementation Units

### U1. Add canonical layer module in `core/board.py`

**Goal:** Introduce `LayerIndex`, `STANDARD_LAYER_ORDER`, `PLANE_LAYER_INDICES`, the four helpers, and the two bidirectional maps in `core/board.py`, with full unit-test coverage.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/core/board.py`
- Modify: `packages/temper-placer/tests/core/test_board.py`

**Approach:**
- Add `LayerIndex(IntEnum)` near the existing `Layer` dataclass. Override `__str__` to return the KiCad name (`"F.Cu"` etc.). Add a class-level `from_name(cls, name: str) -> LayerIndex` convenience for the call sites that want a `.get`-style default.
- Add `STANDARD_LAYER_ORDER: tuple[LayerIndex, ...]` and `PLANE_LAYER_INDICES: frozenset[LayerIndex]` as module-level constants directly below the enum.
- Add the four helpers (`is_plane_layer`, `is_signal_layer`, `side_to_layer_name`, `layer_name_to_index`) with the `str | LayerIndex` union signature for the first two; dispatch on `isinstance` to convert to canonical form. `side_to_layer_name` raises `ValueError` for non-{0, 1}; `layer_name_to_index` raises `KeyError` for unknown names.
- Add `LAYER_IDX_TO_NAME` and `LAYER_NAME_TO_IDX` derived from the enum's `__members__` (or hand-built from the four members — either is fine; hand-built is more explicit).
- Add a new test class `TestLayerIndex` to `tests/core/test_board.py` covering the helpers and constants.
- **Do not** migrate any call site in this unit. This unit is "add the canonical surface and prove it works." The next unit migrates callers.

**Patterns to follow:**
- `Layer` dataclass (line 125) and `LayerStackup` (line 143) for placement and naming style.
- The existing `default_4layer()` classmethod (line 168) for module-level constant co-location.

**Test scenarios:**
- Happy path: `LayerIndex.F_CU.name == "F_CU"` and `str(LayerIndex.F_CU) == "F.Cu"`; `is_plane_layer(LayerIndex.IN1_CU) is True`; `is_plane_layer("In1.Cu") is True`; `is_signal_layer("F.Cu") is True`; `is_signal_layer("In1.Cu") is False`; `side_to_layer_name(0) == "F.Cu"`; `side_to_layer_name(1) == "B.Cu"`; `layer_name_to_index("B.Cu") == LayerIndex.B_CU`; `LAYER_IDX_TO_NAME[LayerIndex.F_CU] == "F.Cu"`; `LAYER_NAME_TO_IDX["In2.Cu"] == LayerIndex.IN2_CU`.
- Edge case: `LayerIndex.F_CU.value == 0` (IntEnum value is the int).
- Error path: `side_to_layer_name(2)` raises `ValueError`; `side_to_layer_name(-1)` raises `ValueError`; `layer_name_to_index("F.GND")` raises `KeyError`.
- Integration: `len(STANDARD_LAYER_ORDER) == 4` and `STANDARD_LAYER_ORDER[0] is LayerIndex.F_CU` and `STANDARD_LAYER_ORDER[-1] is LayerIndex.B_CU`; `PLANE_LAYER_INDICES == frozenset({LayerIndex.IN1_CU, LayerIndex.IN2_CU})`.

**Verification:** The new test class passes in isolation (`pytest tests/core/test_board.py::TestLayerIndex -v`). No existing test in the file regresses.

---

### U2. Migrate layer-list literals, layer-name dicts, and side-to-layer-name ternaries across src/

**Goal:** Replace every duplicated layer-name representation in the placer source tree with an import from `core/board.py`. After this unit, a search for `"F.Cu"` in the source tree (outside `core/board.py`, `core/net_types.py`, and `io/kicad_*`) returns no string literals — only references to `STANDARD_LAYER_ORDER`, `LAYER_NAME_TO_IDX`, or the helpers.

**Requirements:** R5, R6, R7, R8

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` (line 505 — hard-coded list)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/copper_balance.py` (line 84)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (line 212 — side ternary; many other `"F.Cu"`/`"B.Cu"` references downstream are read-only lookups against grid data and stay as strings, see Approach)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/bottleneck_geometry.py` (line 610 — local `_SMD_LAYER_NAME_TO_IDX` mirror)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py` (lines 529, 562)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/via_validation.py` (line 21 — `PLANE_LAYERS`; line 208 — list; line 237 — `in` check)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/drc_sweep.py` (line 50 — local dict; line 202 — list)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing_helpers.py` (lines 7-8 — both dicts)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` (10 import sites + ~10 call sites using `LAYER_IDX_TO_NAME.get(idx, "F.Cu")`)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/pipeline.py` (line 64 — side ternary)
- Modify: `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py` (line 60 — `INTERNAL_LAYERS`; line 520 — `in` check)
- Modify: `packages/temper-placer/src/temper_placer/io/kicad_parser.py` (line 1275 — 4-layer list; the 6-layer branch at line 1277 stays)
- Modify: `packages/temper-placer/src/temper_placer/io/kicad_exporter.py` (line 224 — 4-layer list; the 6-layer branch at line 1277 stays)

**Approach:**
- For each file, change the import block to add the relevant symbols from `temper_placer.core.board` (use a relative import matching the existing import style: `from ...core.board import ...` for files in `routing/` or `deterministic/`, `from ..core.board import ...` for files in `io/`, etc.).
- Replace `PLANE_LAYERS` (string frozenset) with `PLANE_LAYER_INDICES` (LayerIndex frozenset). The call site `layer in PLANE_LAYERS` becomes `layer in PLANE_LAYER_INDICES`; `layer` is already an `int` at that site — convert it to `LayerIndex(layer)` at the boundary, or change the surrounding code to track `LayerIndex` end-to-end. The implementation picks the lighter-touch option per file (audit each `layer` variable to see if it's already a `LayerIndex` upstream).
- Replace `INTERNAL_LAYERS` (numeric frozenset) with `PLANE_LAYER_INDICES`. The call site at `drc_oracle.py:520` checks `layer in INTERNAL_LAYERS` where `layer` is the `target_layer` argument — same boundary-conversion question as above.
- Replace the 4-element hard-coded lists with `STANDARD_LAYER_ORDER` (when the code iterates) or with `LAYER_NAME_TO_IDX` / `LAYER_IDX_TO_NAME` (when the code looks up a name or index). Pick the right one per call site; both are valid.
- Replace the two side-to-layer-name ternaries with `side_to_layer_name(side)`.
- The `sequential_routing.py` heavy-use of `LAYER_IDX_TO_NAME.get(idx, "F.Cu")` becomes `LAYER_IDX_TO_NAME.get(LayerIndex(idx), LayerIndex.F_CU)` (or direct access if the audit in U2 shows the index is always in range). See Open Questions: Deferred to Implementation.
- **`kicad_exporter.py:1277` 6-layer list and `kicad_parser.py` 6-layer branch:** leave alone. Out of scope per R10 and origin scope boundaries. The 4-layer branches at line 1275 (parser) and 224 (exporter) are migrated.
- **`router_v6/pipeline.py` and other files with downstream `"F.Cu"`/`"B.Cu"` reads against grid/skeleton data (e.g., line 499 `stage2.skeletons.get("F.Cu")`):** leave alone. These are runtime lookups against a `dict[str, GridSkeleton]` keyed by the parsed layer name from a KiCad file — they cannot use a `LayerIndex` constant because the key set is the file's actual layers, not the canonical 4. Only the line-212 ternary migrates.

**Patterns to follow:**
- The existing import style at the top of each file (relative imports, multi-line from imports grouped by responsibility).
- The `default_4layer()` classmethod for `STANDARD_LAYER_ORDER` consumption.

**Test scenarios:**
- Happy path: `LAYER_IDX_TO_NAME` import in `sequential_routing_helpers.py` is removed; the dict is no longer defined there; `from .sequential_routing_helpers import LAYER_IDX_TO_NAME` (if any) fails (verify no consumer does this).
- Integration: `uv run python -c "from temper_placer.core.board import LAYER_IDX_TO_NAME, LAYER_NAME_TO_IDX, STANDARD_LAYER_ORDER, PLANE_LAYER_INDICES; assert len(STANDARD_LAYER_ORDER) == 4; assert LAYER_IDX_TO_NAME[LayerIndex.F_CU] == 'F.Cu'"` succeeds.
- Error path: `rg '"F\.Cu"|"In1\.Cu"|"In2\.Cu"|"B\.Cu"' packages/temper-placer/src/temper_placer/router_v6 packages/temper-placer/src/temper_placer/deterministic packages/temper-placer/src/temper_placer/io/kicad_parser.py packages/temper-placer/src/temper_placer/io/kicad_exporter.py` returns no matches in non-6-layer code paths (the 6-layer extension at `kicad_exporter.py:1277` and `kicad_parser.py:1277` may still match — verify those are the only remaining hits).

**Verification:** A search for the four canonical layer-name strings across the modified source files (excluding the 6-layer extension and the read-only grid-key lookups) returns zero hits in code that defines them; all consumers import from `core/board.py`.

---

### U3. Migrate `core/net_types.py` defaults and rewrite `LayerStackup.default_4layer()`

**Goal:** `_default_layer` in `core/net_types.py` returns `LayerIndex` instead of `str`; `LayerStackup.default_4layer()` builds its `layers` list from `STANDARD_LAYER_ORDER`. The 4-layer stackup's `copper_weight` and `is_routable` instance fields are unchanged.

**Requirements:** R9, R10

**Dependencies:** U1, U2

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/core/net_types.py` (line 465-475 — `_default_layer` and its annotation)
- Modify: `packages/temper-placer/src/temper_placer/core/board.py` (line 168-184 — `default_4layer`)
- Modify: all call sites of `_default_layer` in `core/net_types.py` and any external importer (audit with `rg _default_layer packages/`)

**Approach:**
- Update `_default_layer` to return `LayerIndex`. The defaults dict maps `NetType -> LayerIndex`. Add a docstring noting the return-type change.
- Audit every call site of `_default_layer` in `core/net_types.py` and any external consumer. The two known internal call sites are in the same module — the implementation does a focused sweep.
- For string-formatting sites that consumed the old `str` return (e.g., `f"layer={default_layer}"`), wrap with `str(default_layer)` to get the KiCad name. For `==` comparisons against string literals (e.g., `default_layer == "In1.Cu"`), update to `== LayerIndex.IN1_CU`. For places that pass the value to a function expecting `str` (e.g., `LAYER_NAME_TO_IDX[default_layer]`), convert to `LAYER_NAME_TO_IDX[str(default_layer)]` or to `default_layer.value`.
- Rewrite `default_4layer()`: build the four `Layer` instances by iterating `STANDARD_LAYER_ORDER` and pulling the `copper_weight` and `is_routable` from a small static lookup (e.g., `{"F.Cu": 2.0, "In1.Cu": 1.0, "In2.Cu": 1.0, "B.Cu": 1.0}` and `{"F.Cu": True, "In1.Cu": False, "In2.Cu": False, "B.Cu": True}`). The structure reads naturally as "for each canonical layer in order, build a `Layer` with these per-layer properties."
- `default_2layer()` (line 187) is unchanged per R10.

**Patterns to follow:**
- The existing `default_4layer()` shape — four hand-built `Layer` instances with the right `copper_weight` per side.
- The `_default_layer` returns-dict-by-NetType pattern.

**Test scenarios:**
- Happy path: `_default_layer(NetType.GROUND) is LayerIndex.IN1_CU`; `_default_layer(NetType.POWER) is LayerIndex.IN2_CU`; `_default_layer(NetType.HIGH_VOLTAGE) is LayerIndex.F_CU`.
- Integration: `LayerStackup.default_4layer().layers[0].name == "F.Cu"` and `layers[1].copper_weight == 1.0` and `layers[0].copper_weight == 2.0` and `len(layers) == 4`.
- Edge case: `_default_layer(NetType.SIGNAL) is LayerIndex.F_CU`; the dict's `.get(net_type, LayerIndex.F_CU)` fallback is a `LayerIndex` (not a string).

**Verification:** `pytest tests/core/test_board.py tests/core/test_net_types.py` (or whatever covers `net_types.py`) passes. The 4-layer stackup output is byte-identical to the pre-migration output (same names, same `copper_weight`, same `is_routable`, same order).

---

### U4. Validation pass: pytest, ruff, import-linter-gate, closure tests

**Goal:** Confirm R11 and R12 — full test suite passes, lint and import boundary check are clean, and the placer's 4-layer integration tests produce the same routing output as before the migration.

**Requirements:** R11, R12, AE1, AE2, AE3

**Dependencies:** U1, U2, U3

**Files:** (no new files; this unit is a verification gate)

**Approach:**
- Run `uv run pytest packages/temper-placer/tests/` and resolve any failures. The most likely failure modes are: (a) string-vs-`LayerIndex` mismatches in string formatting or dict lookups, (b) `LAYER_IDX_TO_NAME.get(idx, "F.Cu")` callsites that were converted but need a different default shape, (c) tests that asserted on `str` layer names returned by `_default_layer`.
- Run `uv run ruff check packages/temper-placer/` and resolve any new violations.
- Run `uv run python scripts/import_linter_gate.py` and resolve any new violations (the migration should not add new cross-boundary imports — the new canonical surface is in `core/`, and consumers continue to import from `core/`, which the linter already permits).
- Run the closure test (`uv run python packages/temper-placer/src/temper_placer/regression/closure_test.py` or the repo's standard invocation) and confirm the output is bit-identical to the pre-migration snapshot — same `completion_rate`, same `success_count`, same DRC violations, same trace coordinates on the canonical 4-layer board (`piantor_right.kicad_pcb` per AE3).
- Capture the closure-test report and link it from the plan's PR description (the orchestrator/parent will write the PR body).

**Patterns to follow:**
- The repo's existing CI commands (ruff, pytest, import-linter-gate).

**Test scenarios:**
- Happy path: `pytest` exit code 0; `ruff check` exit code 0; `import_linter_gate.py` reports zero new violations.
- Integration: closure test report matches the pre-migration snapshot for `piantor_right.kicad_pcb` (4-layer board).
- Edge case: `pytest tests/losses/test_layer_aware_losses.py` passes (this test directly instantiates a `LayerStackup` and exercises layer-aware loss — confirms the `default_4layer()` rewrite is compatible with downstream loss computation).

**Verification:** All four checks exit 0; the closure-test diff against the pre-migration snapshot is empty; the migration can land atomically as one PR per the origin's success criterion.

---

## System-Wide Impact

- **Interaction graph:** The migration is structurally a rename. No callbacks, observers, or middleware change behavior. The two interfaces affected are: (a) the `Layer` / `LayerStackup` constructors (no signature change; `Layer` still has `name: str`, `LayerStackup` still has `layers: list[Layer]`), and (b) the consumer functions that previously read `str` and now read `LayerIndex`. For the second, the only observable difference is type-checker output — runtime semantics are identical when the call site is updated correctly.
- **Error propagation:** The two new helpers raise `ValueError` (`side_to_layer_name`) and `KeyError` (`layer_name_to_index`). The existing call sites that called the ternaries cannot fail (the ternary was total). The migration is **stricter** than the prior code: an unexpected `side` value will now raise `ValueError` instead of silently defaulting to `"B.Cu"`. This is a positive behavior change (catches bugs) but is technically observable. Document in the PR description.
- **State lifecycle risks:** No persistent state is added. The `LayerIndex` enum is module-imported across files; Python's import caching ensures the same enum instance is shared. No cache, no cleanup, no partial-write concern.
- **API surface parity:** The public API of `core/board.py` grows (`LayerIndex`, `STANDARD_LAYER_ORDER`, `PLANE_LAYER_INDICES`, four helpers, two maps) but does not break. The public API of `core/net_types.py` changes (`_default_layer` returns `LayerIndex` instead of `str` — private function, no public consumers other than the same module). The public API of `routing/constraints/drc_oracle.py` keeps `INTERNAL_LAYER_CREEPAGE_FACTOR` (still a float) but the in-check `layer in INTERNAL_LAYERS` becomes `layer in PLANE_LAYER_INDICES` — semantically identical for in-range inputs.
- **Integration coverage:** The closure test (U4) is the integration scenario. A 4-layer board through the full pipeline exercises every migrated call site end-to-end. The unit tests in U1 cover the canonical surface; U2 and U3 unit-test the call-site conversions.
- **Unchanged invariants:** The 4-layer `LayerStackup` is byte-identical after U3 (same names, same `copper_weight`, same `is_routable`, same order). The closure-test output is bit-identical after U4. The 6-layer path (`kicad_exporter.py:1277`, `kicad_parser.py:1277`) is untouched and continues to work as before.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Missed call site (a `"F.Cu"` literal in a 13th file the audit didn't find) | U4's `rg` verification (test scenario) plus full pytest run; any test failure is a signal |
| `LayerStackup.is_plane_layer` (method, line 162) shadowed by new module function | Key Technical Decisions documents the deliberate coexistence; method body is rewritten to delegate to the module function for clarity |
| `LAYER_IDX_TO_NAME.get(idx, "F.Cu")` defaults in `sequential_routing.py` use a string-literal fallback that becomes a `LayerIndex`-keyed lookup | Deferred to implementation; U2 lists the audit as a test scenario and U4 catches any miss via pytest |
| 6-layer path breaks unexpectedly (e.g., a hidden 6-layer test) | U4's full pytest run catches it; 6-layer is grep-verified out-of-scope at planning time |
| Closure test output drifts (different routing despite same inputs) | U4 explicitly compares against the pre-migration snapshot; bit-identical is the success criterion (AE3) |
| Import boundary violation (a new cross-module import triggers `import_linter_gate`) | U4 runs the gate; the new canonical surface lives in `core/` and the existing import directions are preserved |
| `IntEnum.__str__` overrides confuse `repr()` or `f"{x!r}"` in downstream logging | U1's tests cover `__str__` and `.name` separately; if a logging site relies on the default enum repr, it gets `"<LayerIndex.F_CU: 0>"` which is acceptable for debug logs but may surprise — U4's pytest run surfaces any string-comparison assertion that breaks |

---

## Documentation / Operational Notes

- The `LayerIndex` docstring should explicitly call out the `__str__` vs `.name` distinction so future contributors don't confuse `"F.Cu"` (str) with `"F_CU"` (`.name`).
- The PR description should mention that the 4-layer closure test output is bit-identical to the pre-migration snapshot (link to the report captured in U4).
- The PR description should call out the `side_to_layer_name` strictness change (now raises `ValueError` for non-{0, 1} sides instead of silently defaulting to `"B.Cu"`). This is a positive behavior change but is technically observable.
- The PR description should note that the 6-layer path is unchanged. A reviewer who searches the diff for "6-layer" and finds nothing will get confidence from this note.
- No runbook or operational doc updates needed — the migration is internal-source-only and changes no user-facing CLI, no config file, no environment variable.

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-23-layer-names-consolidation-requirements.md](docs/brainstorms/2026-06-23-layer-names-consolidation-requirements.md)
- **Related code:**
  - `packages/temper-placer/src/temper_placer/core/board.py` — `Layer` (line 125), `LayerStackup` (line 143), `default_4layer` (line 168), `default_2layer` (line 187), `is_plane_layer` method (line 162)
  - `packages/temper-placer/src/temper_placer/core/net_types.py` — `_default_layer` (line 465)
  - `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py` — `INTERNAL_LAYERS` (line 60), `in INTERNAL_LAYERS` (line 520)
  - `packages/temper-placer/src/temper_placer/deterministic/stages/via_validation.py` — `PLANE_LAYERS` (line 21), `in PLANE_LAYERS` (line 237)
  - `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing_helpers.py` — `LAYER_IDX_TO_NAME` / `LAYER_NAME_TO_IDX` (lines 7-8)
  - `packages/temper-placer/src/temper_placer/deterministic/stages/drc_sweep.py` — local `layer_name_to_idx` (line 50)
  - `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` — heavy consumer of `LAYER_IDX_TO_NAME.get(idx, "F.Cu")` (10+ sites)
  - `packages/temper-placer/src/temper_placer/router_v6/bottleneck_geometry.py` — `_SMD_LAYER_NAME_TO_IDX` mirror (line 610)
  - `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — side ternary (line 212)
  - `packages/temper-placer/src/temper_placer/deterministic/pipeline.py` — side ternary (line 64)
- **Related plans:**
  - `docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md` — established the "one canonical location, import-everywhere" pattern this plan follows
  - Future docs: pad-position consolidation, net classification consolidation, A* primitives consolidation (per the 4-doc sequence named in origin)
- **External docs:** None used
