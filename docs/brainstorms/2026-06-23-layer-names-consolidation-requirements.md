---
date: 2026-06-23
topic: layer-names-consolidation
---

# Layer Names Consolidation (Doc 1 of 4)

## Summary

Introduce a `LayerIndex` IntEnum in `core/board.py` as the canonical layer representation, plus a small set of helpers and constants, then big-bang replace every layer-name literal across the codebase. The audit found 13+ hard-coded `["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]` lists, 2 name↔index dicts in `sequential_routing_helpers.py`, 1 numeric `INTERNAL_LAYERS = frozenset({1, 2})` set in `drc_oracle.py`, 1 string `PLANE_LAYERS = frozenset({"In1.Cu", "In2.Cu"})` set in `via_validation.py`, and 2 side-to-layer-name ternaries — all representing the same concept with different encodings.

## Problem Frame

The codebase has accumulated three independent representations of "which layer is which" — string names, numeric indices, and bidirectional dicts — across at least 13 files. These drift: `INTERNAL_LAYERS` uses `{1, 2}` (numeric) while `PLANE_LAYERS` uses `{"In1.Cu", "In2.Cu"}` (string) for the same concept. The drift is silent — a refactor that adds a new layer or renames an existing one must find and update all 13+ call sites manually, and a missed one becomes a runtime bug (wrong layer, off-by-one, or "Unknown" lookup). The `Layer` dataclass at `core/board.py:125-140` and `LayerStackup.default_4layer()` already establish layer as a first-class concept; the layer-name constants and helpers should live alongside them.

## Requirements

**Canonical layer module**

- R1. `LayerIndex` is an `IntEnum` defined in `core/board.py` with members `F_CU = 0`, `IN1_CU = 1`, `IN2_CU = 2`, `B_CU = 3`. Each member's `.name` attribute (the enum's `name`, not a custom property) returns the standard KiCad string (`"F.Cu"`, `"In1.Cu"`, `"In2.Cu"`, `"B.Cu"`) via a small class method or `__str__`.
- R2. `core/board.py` exposes a module-level constant `STANDARD_LAYER_ORDER: tuple[LayerIndex, ...] = (LayerIndex.F_CU, LayerIndex.IN1_CU, LayerIndex.IN2_CU, LayerIndex.B_CU)` — the canonical 4-layer order. `LayerStackup.default_4layer()` builds its `layers` list from this constant.
- R3. `core/board.py` exposes a module-level constant `PLANE_LAYER_INDICES: frozenset[LayerIndex] = frozenset({LayerIndex.IN1_CU, LayerIndex.IN2_CU})` — the inner plane layers (canonical for "which layers are planes"). Replaces the string `PLANE_LAYERS` in `via_validation.py:21` and the numeric `INTERNAL_LAYERS` in `drc_oracle.py:60`.
- R4. `core/board.py` exposes helpers: `is_plane_layer(name_or_index: str | LayerIndex) -> bool` (true for `In1.Cu`/`In2.Cu`), `is_signal_layer(name_or_index: str | LayerIndex) -> bool` (true for `F.Cu`/`B.Cu`), `side_to_layer_name(side: int) -> str` (returns `"F.Cu"` for 0, `"B.Cu"` for 1; raises for other values), and `layer_name_to_index(name: str) -> LayerIndex` (raises `KeyError` for unknown names).
- R5. `core/board.py` exposes bidirectional maps `LAYER_IDX_TO_NAME: dict[LayerIndex, str]` and `LAYER_NAME_TO_IDX: dict[str, LayerIndex]` derived from the enum (via `dict(LayerIndex.__members__)` or a hand-built `__members__` walk). Existing `LAYER_IDX_TO_NAME` / `LAYER_NAME_TO_IDX` dicts in `deterministic/stages/sequential_routing_helpers.py:7-8` and `deterministic/stages/drc_sweep.py:50` are removed; all consumers import from `core/board.py`.

**Migration: replace every layer-name literal**

- R6. The 13 hard-coded `["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]` lists in `router_v6/astar_core.py:505`, `deterministic/stages/clearance_grid.py:529, 562`, `router_v6/copper_balance.py:84`, `deterministic/stages/via_validation.py:208`, `deterministic/stages/drc_sweep.py:202`, `io/kicad_parser.py:1275`, `io/kicad_exporter.py:224`, and `deterministic/stages/sequential_routing_helpers.py:7-8` (the existing dict pair) are replaced with references to `STANDARD_LAYER_ORDER` or `LAYER_NAME_TO_IDX`.
- R7. The string `PLANE_LAYERS = frozenset({"In1.Cu", "In2.Cu"})` in `deterministic/stages/via_validation.py:21` and the numeric `INTERNAL_LAYERS = frozenset({1, 2})` in `routing/constraints/drc_oracle.py:60` are both replaced with `PLANE_LAYER_INDICES` from `core/board.py`. All `in INTERNAL_LAYERS` and `in PLANE_LAYERS` checks are updated to work with `LayerIndex` (the enum supports `in` via membership in the frozenset directly).
- R8. The two `layer = "F.Cu" if side == 0 else "B.Cu"` ternaries in `router_v6/pipeline.py:175` and `deterministic/pipeline.py:64` are replaced with `side_to_layer_name(side)` from `core/board.py`.
- R9. `core/net_types.py:468-469` defaults (`GROUND: str = "In1.Cu"`, `POWER: str = "In2.Cu"`) are replaced with `LayerIndex` enum members. All call sites that read these as strings are updated to work with the enum.
- R10. `LayerStackup.default_4layer()` in `core/board.py:170-184` is rewritten to use `STANDARD_LAYER_ORDER`. The `default_2layer()` (line 187) continues to use hand-built `Layer` instances (no canonical 2-layer enum exists; this is out of scope for this doc).

**Migration: tests pass**

- R11. `pytest` on `tests/` passes after the migration. `ruff check` is clean. The import boundary check (`uv run python scripts/import_linter_gate.py`) reports zero new violations.
- R12. The placer's existing 4-layer integration tests (e.g., golden fixture parity, closure tests) produce the same routing output as before the migration (byte-for-byte trace paths, same completion rate, same DRC violations).

## Acceptance Examples

- AE1. **Covers R1, R4.** `LayerIndex.F_CU.name == "F.Cu"` and `is_plane_layer(LayerIndex.IN1_CU) is True` and `is_plane_layer("F.Cu") is False` and `side_to_layer_name(0) == "F.Cu"`. Given a 4-layer board parsed via `LayerStackup.default_4layer()`, `layer_name_to_index("B.Cu") == LayerIndex.B_CU`. Given a net classified as plane by `is_plane_layer(net.preferred_layer)`, the deterministic pipeline routes it as a plane (connects via copper pour, not trace).
- AE2. **Covers R3, R7.** A via placed at grid position (10, 20) on a 4-layer board, with `target_layer = LayerIndex.IN1_CU`, fails the DRC `INTERNAL_LAYERS` check after migration with the same error message as before. The check is now `target_layer in PLANE_LAYER_INDICES` (using enum membership) instead of `target_layer in {1, 2}`.
- AE3. **Covers R6, R12.** A canonical 4-layer board (e.g., `piantor_right.kicad_pcb`) routes through the full pipeline with the same `completion_rate`, `success_count`, and DRC violations as recorded in the last closure test report. Trace coordinates are bit-identical (no float drift).

## Success Criteria

- **Human outcome:** any engineer adding a new layer or renaming an existing one updates one place (`LayerIndex`) instead of 13. The drift between name and index representations is gone.
- **Implementation handoff:** `ce-plan` can produce a single, executable plan from this doc. The plan can be implemented as one PR with all 13+ files updated atomically.

## Scope Boundaries

- 6-layer board support (`io/kicad_exporter.py:1277` extends the layer list to 6 layers) is **out of scope**. The 6-layer path will continue to use its inline list; this consolidation is strictly 4-layer. A future doc may extend `LayerIndex` to 6 layers.
- Routing-side layer assignment (which layers a net *can* use) is a separate concern owned by `router_v6/channel_assignment.py` and friends — out of scope.
- The `Layer.layer_type` string field ("signal"/"plane"/"mixed") at `core/board.py:138` is adjacent to this consolidation but out of scope. It is a closed enum-like value and could become a `LayerType` enum in a future doc.
- Linter / CI enforcement of enum usage (a `ruff` rule banning raw string literals in layer contexts) is out of scope. R1–R10 cover the migration; enforcement is a follow-up.
- The other 3 consolidations (pad-position, net classification, A* primitives) each get their own doc; this doc is only layer names.

## Key Decisions

- **LayerIndex IntEnum, not just constants:** chose enum over a string-typed constant because it gives the type checker something to flag, supports `in` checks against `frozenset[LayerIndex]`, and provides `.name` / `.value` for free. Cost: every `str(layer)` or `int(layer)` consumer needs updating.
- **Co-locate with `Layer` dataclass in `core/board.py`:** chose the existing `Layer` dataclass's home rather than a new module because the `Layer` type is the natural sibling of `LayerIndex` and the 4-layer `LayerStackup.default_4layer()` already uses the same 4 names.
- **Big-bang over staged migration:** chose big-bang because intermediate states with both representations are confusing and review burden is bounded by the reviewer's patience, not the diff size.
- **Helpers accept `str | LayerIndex`:** chose the union type for ergonomics — call sites that already have a string can pass it without conversion, and call sites that have an enum can pass it directly. The helper dispatches with `isinstance`.

## Dependencies / Assumptions

- **Dependency:** `core/board.py:125-140` `Layer` dataclass and `core/board.py:170-184` `LayerStackup.default_4layer()` are stable (will not be removed or significantly changed in this PR).
- **Assumption:** the 4-layer standard (`F.Cu`/`In1.Cu`/`In2.Cu`/`B.Cu`) is the canonical Temper board. Verified at `core/board.py:170-184` (`default_4layer`). 2-layer and 6-layer boards exist as edge cases but are out of scope.
- **Assumption:** `IntEnum` supports `frozenset` membership (`LayerIndex.IN1_CU in PLANE_LAYER_INDICES`) correctly — verified (Python's `Enum` and `IntEnum` are hashable and comparable by identity).
- **Assumption:** the existing `LAYER_IDX_TO_NAME` / `LAYER_NAME_TO_IDX` dicts in `sequential_routing_helpers.py:7-8` and `drc_sweep.py:50` are exact 4-layer maps and not parameterized by stackup. Verified by reading — both are static 4-key dicts.

## Outstanding Questions

### Resolve Before Planning

- (None — the design is settled. The doc can be planned immediately.)

### Deferred to Planning

- **[Affects R2]** [Technical] Should `STANDARD_LAYER_ORDER` be a `tuple[LayerIndex, ...]` or a `list[LayerIndex]`? `tuple` is immutable and the right default, but some call sites may expect mutation. The planner should pick based on call-site usage.
- **[Affects R3]** [Technical] Should `PLANE_LAYER_INDICES` use enum membership semantics (a frozenset of `LayerIndex`) or a list? The audit found 5–10 `in` checks across the codebase; the planner should grep for them and pick the most ergonomic container.
- **[Affects R4]** [Technical] Should `is_plane_layer` accept `Layer | None` and return `False` for `None`? Some call sites pass a possibly-`None` `layer` argument (e.g., from a default arg). The planner should grep for `is None` checks around layer arguments and decide.
- **[Affects R10]** [Technical] The `default_4layer()` method uses 4 hand-built `Layer` instances with `copper_weight=2.0` for `F.Cu` and `1.0` for the others. The `copper_weight` is an instance-level concern, not a class-level one — the canonicalization is on the names, not the weights.
- **[Affects the 6-layer case]** [Needs research] The planner should check whether any tests use a 6-layer board via `LayerStackup` (not via the `kicad_exporter` 6-layer extension) and whether the migration breaks them. If yes, the planner should add a `default_6layer()` method to `LayerStackup` (out of scope per R10, but the planner may need to verify).
