---
date: 2026-06-23
topic: net-classification-consolidation-requirements
---

# Net Classification Consolidation (Doc 3 of 4)

## Summary

The placer source tree contains 20+ distinct lists defining "is this net a power net / ground net / HV net / signal net?" — all implementing the same substring-match pattern with different keyword sets, sometimes with conflicting answers (e.g., is `+3V3` a power net? Some lists say yes, some say no). Introduce a canonical surface of module-level pattern sets (`GROUND_NET_PATTERNS`, `POWER_NET_PATTERNS`, `HV_NET_PATTERNS`) and free helpers (`is_ground_net`, `is_power_net`, `is_hv_net`, `is_signal_net`) in a new `routing/net_classification.py` module, then big-bang migrate the 20+ call sites to use it.

## Problem Frame

The codebase has accumulated 20+ lists across 7 packages that all attempt to answer the same question: "is this net name a power net, ground net, HV net, or signal net?" The lists have drifted. The most curated is `core/net_types.py:284-288` (the `ground_patterns`, `power_patterns`, `hv_patterns` frozensets on `NetClassSpec`), but most call sites have their own private list with a different (sometimes smaller) keyword set. The drift is silent: a routing decision might classify the same net differently in different layers of the pipeline. The classification logic in `core/net_types.py:NetClassSpec.classify_net` (lines 290-319) is the only correct implementation — it uses the curated patterns and returns the appropriate `NetTypeSpec`. The 20+ inlined call sites are either re-implementing this logic with a different (worse) keyword set, or duplicating the substring match with a different scope (exact match vs substring match).

The drift surface is large but contained: 20+ files across `core/`, `routing/`, `router_v6/`, `heuristics/`, `losses/`, `io/`, `experiments/`, `deterministic/`, and `placement/`. There is a public API change required: `core/net_types.py:NetClassSpec.classify_net` is currently an instance method (the patterns are instance fields); the new helpers are free functions that read module-level pattern sets. Call sites that have a `NetClassSpec` instance can keep using `classify_net`; call sites that don't have one (most of them) call the new free functions.

## Requirements

**Canonical surface**

- R1. A new module `routing/net_classification.py` exposes module-level `GROUND_NET_PATTERNS: frozenset[str]`, `POWER_NET_PATTERNS: frozenset[str]`, `HV_NET_PATTERNS: frozenset[str]`. The values are taken verbatim from `core/net_types.py:284-288` (the most curated set).
- R2. The same module exposes free helpers: `is_ground_net(name: str) -> bool`, `is_power_net(name: str) -> bool`, `is_hv_net(name: str) -> bool`, `is_signal_net(name: str) -> bool`. Each performs a case-insensitive substring match: `any(p in name.upper() for p in PATTERNS)`. The signal-net check is the inverse of any other category.
- R3. The same module exposes `classify_net_type(name: str) -> str` that returns one of `"ground"`, `"power"`, `"hv"`, or `"signal"` (the category that matches first; ground > power > hv > signal precedence matches `NetClassSpec.classify_net`). This consolidates the "what's the type of this net?" question for call sites that don't need a full `NetTypeSpec`.
- R4. `core/net_types.py:NetClassSpec.ground_patterns` / `.power_patterns` / `.hv_patterns` are refactored to default to the module-level constants in `routing/net_classification.py`. The instance fields remain (for backward compat with any code that overrides them) but the defaults point at the canonical set. `NetClassSpec.classify_net` (lines 290-319) is unchanged in behavior; it still uses `self.ground_patterns` etc.

**Migration: replace 20+ inlined call sites with the helpers**

- R5. The 20+ call sites that define their own `power_keywords` / `ground_patterns` / `_is_power_net` / `_is_ground_net` / `in [GND, VCC]` / etc. (per the audit: `core/design_rules.py:252, 264-280`, `routing/constraints/design_rules.py:519, 525-537`, `routing/heuristics.py:299, 305`, `routing/maze_router.py:5015, 5019`, `router_v6/thermal_relief.py:92-104`, `router_v6/astar_pathfinding.py:407`, `router_v6/channel_mapping.py:37`, `routing/critical_net_detector.py:168-189`, `losses/enhanced_congestion.py:114`, `heuristics/organizational.py:565, 585, 751`, `heuristics/style.py:52`, `heuristics/structural.py:279-281, 500`, `heuristics/force_directed.py:34`, `routing/c_space_pipeline.py:71-72`, `routing/post_processing/trace_ballooner.py:33, 36`, `routing/pdn_router.py:194`, `io/net_class_manager.py:11`, `io/dsn_exporter.py:370`, `io/zone_manager.py:151-152, 239-240`, `io/config_loader.py:673-678, 761`, `experiments/feedback_effectiveness.py:55`, `deterministic/stages/zone_aware_slot_generation.py:20-32`, and any others found during U2 audit) are migrated to call `is_ground_net(name)`, `is_power_net(name)`, or `is_hv_net(name)` from `routing.net_classification`. The migration replaces the inlined lists and the `in` checks.
- R6. The three existing plane-net sets (`router_v6/routing_space.py:PLANE_NETS` — 13 nets exact match; `deterministic/stages/power_plane.py:TEMPER_PLANE_NETS` — 6 nets exact match; `deterministic/stages/via_validation.py:PLANE_NET_PATTERNS` — 13 patterns substring match) are audited. Where they overlap with the canonical `GROUND_NET_PATTERNS + POWER_NET_PATTERNS + HV_NET_PATTERNS`, the inlined sets are removed and the call site uses `is_ground_net` / `is_power_net` / `is_hv_net` instead. Where they extend beyond (e.g., TEMPER_PLANE_NETS adds `+15V`, `+3V3`, `+5V` which are already in `POWER_NET_PATTERNS`), the inlined set is dropped. If any plane-net set is intentionally distinct (e.g., a closed-world override for a specific board), it stays as a local constant with a comment explaining why.
- R7. `routing/critical_net_detector.py:168-189` (POWER_PIN_PATTERNS, GROUND_PIN_PATTERNS, CLOCK_PIN_PATTERNS) is audited. The pin-pattern version of the helper (`is_ground_pin(pin_name) -> bool` etc.) is added to `routing/net_classification.py` if the patterns are distinct from the net-name patterns. If they're the same patterns, the existing `is_ground_net` / `is_power_net` / `is_hv_net` helpers are used (call site passes `pin.name`).
- R8. The migration is big-bang (matching Doc 1 and Doc 2). All 20+ call sites are updated in one PR. The drift surface is closed atomically.

**Migration: tests pass**

- R9. A new test class `TestNetClassification` in `tests/routing/test_net_classification.py` (or a new file) covers the helpers and constants. Tests include: `is_ground_net("GND") == True`, `is_ground_net("+3V3") == False` (different category), `is_power_net("+3V3") == True`, `is_hv_net("AC_L") == True`, `is_signal_net("DATA1") == True`, case-insensitivity (`is_ground_net("gnd") == True`), substring matching (`is_ground_net("/GND_NET/") == True`). Plus: `classify_net_type` precedence (ground > power > hv > signal).
- R10. The existing `NetClassSpec.classify_net` tests (if any) continue to pass. The pattern defaults are now module-level, so the test can verify the instance defaults match the module constants.
- R11. `pytest tests/` passes after the migration. `ruff check` clean. The import boundary check reports zero new violations.
- R12. The existing 4-layer integration test (closure test on `piantor_right.kicad_pcb` or equivalent canonical board) produces the same routing output as before the migration. The behavioral change is the keyword-set unification; for any specific net, the result must be the same as before. If a call site was previously classifying a net differently (because of drift), this PR exposes that drift — but the migration follows the canonical pattern, so the result is the "correct" answer per `core/net_types.py:284-288`.

## Acceptance Examples

- AE1. **Covers R1, R2, R9.** `is_ground_net("GND") == True`, `is_ground_net("+3V3") == False`, `is_power_net("+3V3") == True`, `is_hv_net("AC_L") == True`, `is_signal_net("DATA1") == True`, `is_ground_net("gnd") == True` (case-insensitive), `is_ground_net("/GND_NET/") == True` (substring match). `classify_net_type("GND") == "ground"`, `classify_net_type("+3V3") == "power"`, `classify_net_type("AC_L") == "hv"`, `classify_net_type("DATA1") == "signal"`. The precedence in `classify_net_type` matches `NetClassSpec.classify_net` (ground > power > hv > signal).
- AE2. **Covers R5, R6.** A canonical 4-layer board (e.g., `piantor_right.kicad_pcb`) routes through the full pipeline with the same `completion_rate`, `success_count`, and DRC violations as the last closure test report. The `classify_net_type` answers for every net in the board are the same before and after the migration.
- AE3. **Covers R4.** `NetClassSpec().ground_patterns == GROUND_NET_PATTERNS` (the instance field defaults to the module constant). A `NetClassSpec` with custom `ground_patterns={"FOO"}` still uses `FOO` for its own classification (the instance field overrides the default).

## Success Criteria

- **Human outcome:** the 20+ duplicate lists are gone. There is one canonical pattern set per category (ground, power, HV) in `routing/net_classification.py`. Drift across the codebase is closed atomically.
- **Implementation handoff:** `ce-plan` can produce a single executable plan from this doc. The plan is implementable as one PR (or 2 PRs: surface + migration, if the surface PR is small enough to review in isolation).

## Scope Boundaries

- The `NetClassSpec.classify_net` instance method is preserved (R4) — only its default pattern fields are re-pointed at the module constants. Removing the instance method is a separate breaking-change effort.
- The closed-world `PLANE_NETS` lists (e.g., `router_v6/routing_space.py:PLANE_NETS` if it's intentionally distinct from `is_ground_net | is_power_net`) stay as local constants with a comment explaining why. The audit (R6) determines which ones are "intentionally distinct" vs "drift" — drift is removed, intentionally distinct stays.
- The 7 new plans (2026-06-23-001 through 007) are out of scope.
- The other 3 consolidations (layer names, pad-position, A* primitives) each get their own doc; this doc is only net classification.
- The pin-pattern variant (R7) is included if the patterns differ from the net-name patterns. If they're the same, the existing helpers are used and no new helpers are added.

## Key Decisions

- **Module `routing/net_classification.py`:** chosen over extending `core/net_types.py` because the new helpers are not tied to the `NetClassSpec` dataclass. Free functions are easier to call from the 20+ call sites that don't have a `NetClassSpec` instance. The `routing/` location matches the existing `routing/heuristics.py` and `routing/constraints/design_rules.py` style.
- **Module-level pattern sets, not instance fields:** the new patterns are module-level constants. `NetClassSpec` keeps its instance fields (for backward compat) but defaults to the module constants. The pattern set is "the source of truth" — it's not a per-instance config knob.
- **Big-bang migration (R8):** matching Doc 1 and Doc 2. The drift is real; the moment-of-truth is at every call site simultaneously. There is no deprecation window — the duplicates are wrong today (different answers for the same net), every minute they stay is a bug.
- **`is_signal_net = not (any other category)`:** the signal-net check is defined as the inverse of any other category. There's no `SIGNAL_NET_PATTERNS` because signal means "none of the above" — adding one would be a fourth source of truth.
- **`classify_net_type` precedence (ground > power > hv > signal):** matches `NetClassSpec.classify_net` exactly. This is the documented behavior in the canonical implementation; the new helper must agree.
- **Case-insensitive substring match:** matches the existing `NetClassSpec.classify_net` behavior. The plan's R5 deferred question "is `+3V3` a power net?" is resolved by the canonical pattern set (`+3V3` is in `POWER_NET_PATTERNS`).

## Dependencies / Assumptions

- **Dependency:** `core/net_types.py:NetClassSpec.classify_net` is the canonical implementation. Verified by reading the source (lines 290-319). The 20+ inlined sites are duplicates of this logic with different keyword sets.
- **Dependency:** Doc 1 (Layer Names) and Doc 2 (Pad-Position) are shipped. Their modules (`core/board.py:LayerIndex`, `core/pin_geometry.py:pin_world_position`) are stable.
- **Assumption:** the canonical 4-layer board's net names are in the canonical pattern sets. Verified by spot-checking the closure test board's net names against `GROUND_NET_PATTERNS` + `POWER_NET_PATTERNS` + `HV_NET_PATTERNS`.
- **Assumption:** `NetClassSpec` instance fields are read by tests and may be overridden by callers. Verified by reading the dataclass (lines 281-288). Keeping the instance fields as overrides preserves backward compat.
- **Assumption:** the audit's "20+ lists" count is accurate. The list in the requirements doc (R5) enumerates them; the planner's U2 audit may find a few more.

## Outstanding Questions

### Resolve Before Planning

- (None — the design is settled. The pattern set is taken verbatim from `core/net_types.py:284-288`.)

### Deferred to Planning

- **[Affects R5]** [Technical] The planner should grep for all `is_power_net` / `is_ground_net` / `is_hv` / `in [GND, VCC]` patterns in `packages/temper-placer/src/temper_placer/` and add any missed call sites to U2's file list. The audit's 20+ count is a lower bound.
- **[Affects R6]** [Technical] The planner should audit `PLANE_NETS`, `TEMPER_PLANE_NETS`, and `PLANE_NET_PATTERNS` to determine which are "intentionally distinct" vs "drift". The migration removes the drift cases and keeps the intentionally distinct ones with comments.
- **[Affects R7]** [Technical] The planner should determine whether pin-pattern names are distinct from net-name patterns. If `POWER_PIN_PATTERNS = ["VCC", "VDD"]` and `POWER_NET_PATTERNS = {"+3V3", "+5V", ...}` (where `+3V3` etc. are net-name prefixes but pin names are usually `VCC`, `VDD` for power-rail pins), the patterns are distinct and need separate helpers.
- **[Affects R9]** [Technical] The test file should live at `tests/routing/test_net_classification.py` (new file) or be added to an existing test file. The planner picks based on test-class organization.
- **[Affects R12]** [Needs research] The canonical board for the closure test may be different from `piantor_right.kicad_pcb`. The planner should grep for the closure test config to identify the right board.
