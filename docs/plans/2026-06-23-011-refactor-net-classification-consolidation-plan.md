---
title: Net Classification Consolidation
type: refactor
status: active
date: 2026-06-23
origin: docs/brainstorms/2026-06-23-net-classification-consolidation-requirements.md
---

# Net Classification Consolidation

## Summary

Introduce a canonical surface of module-level pattern sets (`GROUND_NET_PATTERNS`, `POWER_NET_PATTERNS`, `HV_NET_PATTERNS`) and free helpers (`is_ground_net`, `is_power_net`, `is_hv_net`, `is_signal_net`, plus the composite `classify_net_type`) in a new `routing/net_classification.py` module, then big-bang migrate the 20+ inlined call sites — plus the three `PLANE_NETS` / `TEMPER_PLANE_NETS` / `PLANE_NET_PATTERNS` plane-net sets — to use that single source of truth. After this plan, an engineer adding a new power-net keyword edits one place, and the existing 4-layer closure tests on `piantor_right_unrouted.kicad_pcb` still produce the same routing output.

---

## Problem Frame

The placer source tree has accumulated 20+ lists across 7 packages that all attempt to answer the same question: "is this net name a power net, ground net, HV net, or signal net?" The lists have drifted silently: most call sites have their own private list with a different (sometimes smaller) keyword set, and a routing decision might classify the same net differently in different layers of the pipeline. The classification logic in `core/net_types.py:NetClassSpec.classify_net` (lines 290-319) is the only correct implementation — it uses the curated patterns on `NetClassSpec.ground_patterns` / `.power_patterns` / `.hv_patterns` (lines 284-288) and returns the appropriate `NetTypeSpec`. The 20+ inlined call sites are either re-implementing this logic with a different (worse) keyword set, or duplicating the substring match with a different scope (exact match vs substring match).

This is the third of four sequential consolidations (layer-names → pad-position → net classification → A* primitives); see origin: `docs/brainstorms/2026-06-23-net-classification-consolidation-requirements.md` and the sibling plans `docs/plans/2026-06-23-008-refactor-layer-names-consolidation-plan.md` and `docs/plans/2026-06-23-010-refactor-pad-position-consolidation-plan.md` for the prior art. The first two are shipped; this plan follows the same canonical-surface + big-bang-migration + closure-test-parity pattern.

The drift surface is large but contained: 20+ files across `core/`, `routing/`, `router_v6/`, `heuristics/`, `losses/`, `io/`, `experiments/`, `deterministic/`, and `placement/`. There is a public API change required: `core/net_types.py:NetClassSpec.classify_net` is currently an instance method (the patterns are instance fields); the new helpers are free functions that read module-level pattern sets. Call sites that have a `NetClassSpec` instance can keep using `classify_net`; call sites that don't have one (most of them) call the new free functions. There is no behavior change for any net that the canonical patterns classify "correctly"; the only observable difference is the unification of the keyword sets across the codebase (drift → canonical).

---

## Requirements

- R1. A new module `packages/temper-placer/src/temper_placer/routing/net_classification.py` exposes module-level `GROUND_NET_PATTERNS: frozenset[str]`, `POWER_NET_PATTERNS: frozenset[str]`, `HV_NET_PATTERNS: frozenset[str]`. The values are taken verbatim from `core/net_types.py:284-288` (the curated set): `GROUND_NET_PATTERNS = frozenset({"GND", "PGND", "CGND", "AGND", "DGND", "VSS"})`, `POWER_NET_PATTERNS = frozenset({"+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"})`, `HV_NET_PATTERNS = frozenset({"AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"})`.
- R2. The same module exposes free helpers: `is_ground_net(name: str) -> bool`, `is_power_net(name: str) -> bool`, `is_hv_net(name: str) -> bool`, `is_signal_net(name: str) -> bool`. Each performs a case-insensitive substring match: `any(p in name.upper() for p in PATTERNS)`. The signal-net check is `not (is_ground_net(name) or is_power_net(name) or is_hv_net(name))`. The helpers are total (a `None` or empty name returns `False` for the three category checks; `is_signal_net` returns `True` for an empty/None name).
- R3. The same module exposes `classify_net_type(name: str) -> str` that returns one of `"ground"`, `"power"`, `"hv"`, or `"signal"`, using precedence `ground > power > hv > signal` (matches `NetClassSpec.classify_net` at `core/net_types.py:307-319` exactly). This consolidates the "what's the type of this net?" question for call sites that don't need a full `NetTypeSpec`.
- R4. `core/net_types.py:NetClassSpec.ground_patterns` / `.power_patterns` / `.hv_patterns` (lines 284-288) are refactored to default to the module-level constants in `routing/net_classification.py`: `ground_patterns: FrozenSet[str] = field(default_factory=lambda: GROUND_NET_PATTERNS)`, etc. (using `dataclasses.field` with a default factory; the `frozenset` is referenced, not deep-copied — the canonical set is the source of truth). The instance fields remain for backward compat with any code that overrides them. `NetClassSpec.classify_net` (lines 290-319) is unchanged in behavior; it still uses `self.ground_patterns` etc.
- R5. The 20+ call sites that define their own `power_keywords` / `ground_patterns` / `_is_power_net` / `_is_ground_net` / `in [GND, VCC]` / etc. (per the origin's audit: `core/design_rules.py:252, 264-280`, `routing/constraints/design_rules.py:519, 525-537`, `routing/heuristics.py:299, 305`, `routing/maze_router.py:5015, 5019`, `router_v6/thermal_relief.py:92-104`, `router_v6/astar_pathfinding.py:407`, `router_v6/channel_mapping.py:37`, `routing/critical_net_detector.py:168-189`, `losses/enhanced_congestion.py:114`, `heuristics/organizational.py:565, 585, 751`, `heuristics/style.py:52`, `heuristics/structural.py:279-281, 500`, `heuristics/force_directed.py:34`, `routing/c_space_pipeline.py:71-72`, `routing/post_processing/trace_ballooner.py:33, 36`, `routing/pdn_router.py:194`, `io/net_class_manager.py:11`, `io/dsn_exporter.py:370`, `io/zone_manager.py:151-152, 239-240`, `io/config_loader.py:673-678, 761`, `experiments/feedback_effectiveness.py:55`, `deterministic/stages/zone_aware_slot_generation.py:20-32`, and any others found during U2 audit) are migrated to call `is_ground_net(name)`, `is_power_net(name)`, or `is_hv_net(name)` from `routing.net_classification`. The migration replaces the inlined lists and the `in` checks.
- R6. The three existing plane-net sets are audited. `router_v6/routing_space.py:PLANE_NETS` (13 nets, exact match), `deterministic/stages/power_plane.py:TEMPER_PLANE_NETS` (13 nets, exact match), and `deterministic/stages/via_validation.py:PLANE_NET_PATTERNS` (13 patterns, substring match) are checked against the canonical `GROUND_NET_PATTERNS + POWER_NET_PATTERNS + HV_NET_PATTERNS`. The audit's finding (per planning research): `PLANE_NET_PATTERNS` is exactly the union of the canonical ground+power patterns and is **drift** — remove and use `is_ground_net | is_power_net`. `TEMPER_PLANE_NETS` is a strict subset of the canonical union (every entry is in GROUND or POWER or HV) and is **drift** — remove. `PLANE_NETS` is exact-match where canonical is substring-match; the substring-match is a **superset** of the exact-match for any net name in `PLANE_NETS` (e.g., `is_ground_net("+15V_PLANE")` would be `True` for the substring match but `False` for the exact match) — this is the documented canonical behavior and the migration accepts it; `PLANE_NETS` is removed and the call site uses `is_ground_net | is_power_net`. If the U2 audit finds any plane-net set that is intentionally distinct (e.g., a closed-world override for a specific board), it stays as a local constant with a comment explaining why.
- R7. `routing/critical_net_detector.py:168-198` (POWER_PIN_PATTERNS, GROUND_PIN_PATTERNS, CLOCK_PIN_PATTERNS) is audited. Per planning research: pin patterns are distinct from net-name patterns (e.g., `POWER_PIN_PATTERNS` includes "VIN", "VOUT", "PVCC", "VBAT", "PWR", "POWER", "V+", "VCC_IN", "VCC_OUT" which are pin names, not net-name prefixes; the net `+3V3` is the rail, the pin `VCC_IN` is the chip-side connection). The pin-pattern helpers `is_ground_pin(pin_name: str) -> bool`, `is_power_pin(pin_name: str) -> bool`, `is_hv_pin(pin_name: str) -> bool`, `is_clock_pin(pin_name: str) -> bool` are added to `routing/net_classification.py`, each backed by a module-level `*_PIN_PATTERNS` frozenset. The four `CriticalNetDetector` class-level pattern lists (lines 168-198) are refactored to default to these module constants (mirroring the `NetClassSpec` R4 pattern).
- R8. The migration is big-bang (matching Doc 1 and Doc 2). All 20+ call sites, the three plane-net sets, and the pin-pattern sets are updated in one PR. The drift surface is closed atomically.
- R9. A new test class `TestNetClassification` in a new file `packages/temper-placer/tests/routing/test_net_classification.py` covers the helpers and constants. Tests include the AE1 matrix: `is_ground_net("GND") == True`, `is_ground_net("+3V3") == False`, `is_power_net("+3V3") == True`, `is_hv_net("AC_L") == True`, `is_signal_net("DATA1") == True`, `is_ground_net("gnd") == True` (case-insensitive), `is_ground_net("/GND_NET/") == True` (substring match), and the `classify_net_type` precedence: `classify_net_type("GND") == "ground"`, `classify_net_type("+3V3") == "power"`, `classify_net_type("AC_L") == "hv"`, `classify_net_type("DATA1") == "signal"`, and the precedence order (a net name like `"GND_AND_+3V3"` is classified as `"ground"` not `"power"`).
- R10. The existing `NetClassSpec.classify_net` tests (if any) continue to pass. The pattern defaults are now module-level, so a new test verifies `NetClassSpec().ground_patterns is GROUND_NET_PATTERNS` (identity, not equality — the default factory returns the same object) and that `NetClassSpec(ground_patterns={"FOO"}).ground_patterns == {"FOO"}` (custom override preserved, AE3).
- R11. `uv run pytest packages/temper-placer/tests/` passes after the migration. `uv run ruff check packages/temper-placer/` is clean. `uv run python scripts/import_linter_gate.py` reports zero new violations.
- R12. The placer's 4-layer integration test (closure test on `piantor_right_unrouted.kicad_pcb` per `router_v6/test_boards.py:50`, matching the Doc 1 and Doc 2 plans) produces the same `router_completion_pct`, `success_count`, and DRC violations as the last closure test report. For every net in the board, the `classify_net_type` answer is the same before and after the migration (the canonical patterns are a strict superset of the most-curated call-site lists and an exact match for the canonical `core/net_types.py:284-288` set).

**Origin actors:** (none — no A-IDs in origin)
**Origin flows:** (none — no F-IDs in origin)
**Origin acceptance examples:** AE1 (covers R1, R2, R9), AE2 (covers R5, R6, R12), AE3 (covers R4, R10)

---

## Scope Boundaries

- The `NetClassSpec.classify_net` instance method is preserved (R4) — only its default pattern fields are re-pointed at the module constants. Removing the instance method is a separate breaking-change effort and is **out of scope** here.
- The three plane-net sets (R6) are removed in favor of the helpers. If the U2 audit finds an intentionally-distinct set (e.g., a closed-world override for a specific board), it stays as a local constant with a comment explaining why. No intentionally-distinct sets are known at planning time; the audit is a planning-research task that the implementer confirms.
- The 7 new plans (`2026-06-23-001` through `007`) are out of scope.
- The other 3 consolidations (layer names, pad-position, A* primitives) each get their own doc; this doc is only net classification.
- The pin-pattern variants (R7) are added as separate helpers (not the same as the net-name helpers) because the patterns are distinct. The four `*_PIN_PATTERNS` constants are colocated with the four `*_NET_PATTERNS` constants in `routing/net_classification.py` (per origin's R7 explicit instruction). The pin helpers are a separate concern from the net helpers and don't share logic.
- The `routing/critical_net_detector.py:CriticalNetDetector` class is preserved — its `POWER_PATTERNS` / `GROUND_PATTERNS` / etc. (line 168-198, the net-name regex patterns) are distinct from the new `*_NET_PATTERNS` substring patterns (they are regex, not substring) and stay as instance fields. The class-level `*_PIN_PATTERNS` (lines 168-198, the pin-name substring patterns) are the ones that migrate to the module constants (R7).
- Ruff / CI enforcement of helper usage (a rule banning private `_is_power_net` / `_is_ground_net` re-implementations) is out of scope. R1-R12 cover the migration; enforcement is a follow-up.
- No new public dataclass fields are added to `NetClassSpec` — only the existing three pattern fields are re-pointed at the module constants. No behavior change for any code that instantiates `NetClassSpec()` with no arguments.

### Deferred to Follow-Up Work

- **Ruff rule banning private `_is_*_net` re-implementations**: separate doc, once the migration is stable and the helpers are the proven pattern.
- **Removing `NetClassSpec.classify_net` instance method entirely** (R4 retains it): a future doc can delete it once all inlined callers have moved to the free functions and a `NetTypeSpec` is no longer needed for the simple "what type is this net?" question.
- **Extending `HV_NET_PATTERNS` to cover USB_VBUS, ETH_XFMR_CT, and other HV-adjacent nets**: the canonical set is a deliberate curated subset; adding to it is a separate decision per board topology. Not part of this consolidation.
- **Per-board plane-net overrides** (the "intentionally distinct" case in R6): a future doc can introduce a `BoardNetClassification` config object that extends the canonical set per board, if a use case emerges.

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/core/net_types.py:283-288` — `NetClassSpec` pattern fields (the canonical patterns this plan lifts to module level).
- `packages/temper-placer/src/temper_placer/core/net_types.py:290-319` — `NetClassSpec.classify_net` (the reference implementation; the precedence ground > power > hv > signal is the source of truth for `classify_net_type`).
- `packages/temper-placer/src/temper_placer/routing/maze_router.py:5014-5019` — the local `_is_power_net` and `_is_ground_net` functions (the most-extreme drift case: a 4-element list for power, a 6-element list for ground, neither matches canonical).
- `packages/temper-placer/src/temper_placer/router_v6/routing_space.py:23-37` — `PLANE_NETS` (13 nets, exact match) — the R6 audit's substring-vs-exact-match case.
- `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py:26-45` — `TEMPER_PLANE_NETS` (13 nets, exact match) — the R6 audit's "strict subset of canonical" case.
- `packages/temper-placer/src/temper_placer/deterministic/stages/via_validation.py:20-47` — `PLANE_NET_PATTERNS` (13 patterns, substring match) — the R6 audit's "exact union of canonical" drift case.
- `packages/temper-placer/src/temper_placer/routing/critical_net_detector.py:168-198` — `POWER_PIN_PATTERNS`, `GROUND_PIN_PATTERNS`, `CLOCK_PIN_PATTERNS` (pin-name substring patterns, distinct from net-name patterns) — the R7 source.
- `packages/temper-placer/src/temper_placer/routing/critical_net_detector.py:79-166` — `CriticalNetDetector.POWER_PATTERNS`, `GROUND_PATTERNS`, etc. (net-name regex patterns) — distinct from pin patterns; stay as instance fields.
- `packages/temper-placer/src/temper_placer/core/design_rules.py:226-292` — `DesignRulesParser._is_ground_net` and `_is_power_net` (the origin's R5 example for the most-extensive private re-implementations).
- `packages/temper-placer/src/temper_placer/heuristics/organizational.py:565, 751` and `heuristics/structural.py:500` — `power_patterns` lists in heuristic scoring functions (R5 migration targets).
- `packages/temper-placer/src/temper_placer/router_v6/test_boards.py:50` — `PIANTOR_PATH` (canonical 4-layer board for the closure test, matching Doc 1 and Doc 2 — resolves the origin's deferred R12 question).
- `packages/temper-placer/src/temper_placer/regression/closure_test.py:151-209` — `ClosureResult` dataclass (`router_completion_pct`, `drc_errors`, `drc_warnings` are the per-run metrics for R12 parity).
- The existing `routing/` module style (e.g., `routing/heuristics.py`, `routing/constraints/design_rules.py`) — colocated, focused single-responsibility modules; the new `routing/net_classification.py` follows the same style.

### Institutional Learnings

- The sibling plan `docs/plans/2026-06-23-008-refactor-layer-names-consolidation-plan.md` established the canonical-surface + big-bang-migration + closure-test-parity pattern that this plan follows. The test scenarios, key-decision style, and risk-register structure are intentionally consistent.
- The sibling plan `docs/plans/2026-06-23-010-refactor-pad-position-consolidation-plan.md` (Doc 2) established the new-test-file convention (`tests/core/test_pin_geometry.py`, separate from the existing `test_netlist.py`). This plan follows the same convention with a new `tests/routing/test_net_classification.py` (in `tests/routing/`, not `tests/core/`, because the new module lives in `routing/`, not `core/`).
- The `routing/` package convention is "free helpers + dataclasses, no JAX". The new `routing/net_classification.py` is pure-Python (no JAX imports), matching the convention.
- `docs/solutions/architecture-patterns/layer-index-ssot-placer-2026-06-23.md` (Doc 1's compounding doc) is the documented SSOT pattern; this plan is a direct application to a different concept (net classification vs layer name).
- The `safety-constant SSOT` plan (`docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md`) established the "one canonical location, import-everywhere" convention this plan follows.

### External References

None — this is a refactor within established Python patterns (`frozenset` constants, free helper functions, `dataclasses.field(default_factory=...)` for defaulting to a module-level constant). Local patterns are sufficient; no external research needed.

---

## Key Technical Decisions

- **Module location: `routing/net_classification.py`, not `core/`.** The origin's R1 specifies `routing/`. The rationale: the new helpers are not tied to the `NetClassSpec` dataclass (which lives in `core/`); free functions are easier to call from the 20+ call sites that don't have a `NetClassSpec` instance. The `routing/` location matches the existing `routing/heuristics.py` and `routing/constraints/design_rules.py` style. `NetClassSpec`'s pattern fields default to these module-level constants via a `default_factory` (R4), so `core/net_types.py` re-exports the canonical surface for its own consumers.
- **Module-level `frozenset` constants, not `enum.StrEnum`.** Strings are the natural representation (net names are strings, the pattern match is `in name.upper()`). A `frozenset` is hashable, supports O(1) `in` checks, and the `NetClassSpec` default-factory pattern (`field(default_factory=lambda: GROUND_NET_PATTERNS)`) works seamlessly. A `StrEnum` would force the comparison `PATTERN.value in name.upper()` and adds no value.
- **`is_signal_net = not (any other category)`.** Per origin: there's no `SIGNAL_NET_PATTERNS` because signal means "none of the above". Adding one would be a fourth source of truth and a maintenance burden.
- **Empty/None name handling: `is_signal_net` returns `True`, the others return `False`.** A `None` net name is "no name, so not power/ground/HV, so signal". This is the only total behavior consistent with the origin's `is_signal_net = not (others)` definition. A `KeyError` on `None` would force every caller to add a `if name is None:` branch.
- **Pin helpers colocated with net helpers (R7), not in `critical_net_detector.py`.** Per origin's R7 explicit instruction: "the pin-pattern version of the helper ... is added to `routing/net_classification.py` if the patterns are distinct from the net-name patterns". Per planning research, the patterns are distinct (e.g., `POWER_PIN_PATTERNS` has "VIN", "VOUT", "VCC_IN" — pin names, not net-name prefixes). Colocation makes the surface obvious: "if you want to know what kind of net or pin this is, look here".
- **Pin pattern migration: `CriticalNetDetector.POWER_PIN_PATTERNS` etc. default to the module constants via `default_factory` (mirroring R4).** The class-level `*_PIN_PATTERNS` lists are still defined as class attributes for backward compat with any code that subclasses or overrides them, but the defaults point at the canonical set.
- **`NetClassSpec` net-name regex patterns (`POWER_PATTERNS`, `GROUND_PATTERNS`, etc. in `CriticalNetDetector` lines 79-166) are NOT migrated.** These are regex patterns (not substring patterns) and are used for net-name classification with `re.match`. The new `*_NET_PATTERNS` are substring patterns. Different matching strategies, different concepts — the regex patterns stay where they are. (The pin patterns at lines 168-198 are substring patterns, so they migrate per R7.)
- **`PLANE_NET_PATTERNS` removal: use `is_ground_net | is_power_net | is_hv_net`.** The 13-pattern `PLANE_NET_PATTERNS` is exactly the union of canonical `GROUND_NET_PATTERNS + POWER_NET_PATTERNS` (the `via_validation.py` author had the right idea — they just didn't import from a canonical source). After the migration, the call site at `via_validation.py:44` becomes `if is_ground_net(net_name) or is_power_net(net_name) or is_hv_net(net_name):`. The new helper-based check is a strict superset of the prior `PLANE_NET_PATTERNS` check for any net name; for any name in the canonical closure-test board, the result is the same.
- **`TEMPER_PLANE_NETS` removal: use the same `is_ground_net | is_power_net | is_hv_net`.** The 13-net `TEMPER_PLANE_NETS` is a strict subset of the canonical union. Removing the inlined set is unambiguous: every entry in `TEMPER_PLANE_NETS` is matched by the canonical patterns. The `TEMPER_PLANE_LAYERS` dict (the layer-assignment companion) is **out of scope** — it's a different concept (net → plane layer index) and stays as a local constant.
- **`PLANE_NETS` removal: same `is_ground_net | is_power_net | is_hv_net`.** The 13-net `PLANE_NETS` is exact-match (set membership) where canonical is substring-match. The substring match is a **strict superset** of the exact match for any net name containing a canonical pattern as a substring — for the canonical closure-test board, every net name in `PLANE_NETS` matches `is_ground_net | is_power_net | is_hv_net` exactly as before. For hypothetical "drift" net names like `"+15V_PLANE"`, the substring match returns `True` where the exact match returned `False` — this is the documented canonical behavior and matches `NetClassSpec.classify_net` (`core/net_types.py:307-315`). The migration accepts this; the U2 audit confirms no `piantor_right_unrouted.kicad_pcb` net name is incorrectly classified by the substring-match superset.
- **The `classify_net_type` precedence (ground > power > hv > signal) is implemented as a chained `if/elif/elif/else`**, not a dict-based dispatch. The precedence order is documented behavior (origin's R3 + `NetClassSpec.classify_net`), and the chained form makes the precedence visible at a glance. A `dict[str, int]` priority table would be less readable.
- **Big-bang migration, not staged.** Per origin's Key Decision: intermediate states with both representations are confusing; the moment-of-truth is at every call site simultaneously. There is no deprecation window — the duplicates are wrong today (different answers for the same net), every minute they stay is a bug. Single PR, atomic.
- **New test file `tests/routing/test_net_classification.py`, not appended to `test_netlist.py` or `test_net_types.py`.** The new module lives in `routing/`, so the test lives in `tests/routing/` (matching the `routing/` location, same convention as Doc 2's `tests/core/test_pin_geometry.py` matching `core/pin_geometry.py`). The existing `NetClassSpec` tests (if any) continue to cover the class method.
- **No behavior change for the closure-test board.** The canonical patterns at `core/net_types.py:284-288` are the source of truth. The migration is unification of the duplicate lists onto the canonical set. For any net name on the closure-test board, the new helper-based check returns the same boolean as the prior local check (because the prior local checks were subsets of the canonical set or supersets that happen to agree on the board's actual net names). The closure-test output is bit-identical post-migration.

---

## Open Questions

### Resolved During Planning

- **R6 (plane-net sets):** `PLANE_NET_PATTERNS` is the exact union of canonical ground+power patterns — drift, remove and use `is_ground_net | is_power_net`. `TEMPER_PLANE_NETS` is a strict subset of canonical ground+power+hv union — drift, remove. `PLANE_NETS` is exact-match vs canonical substring-match — the substring match is the documented canonical behavior, and for the closure-test board the result is identical; the inlined set is removed and the call site uses the helper. None of the three are "intentionally distinct" — they all collapse to the canonical union.
- **R7 (pin pattern helpers):** the pin patterns (`POWER_PIN_PATTERNS` has "VIN", "VOUT", "PVCC", "VBAT", "PWR", "POWER", "V+", "VCC_IN", "VCC_OUT" — all pin names, not net-name prefixes) are clearly distinct from the net patterns (`+3V3`, `+5V`, `+12V`, `+15V`, `VCC`, `VDD`, `VBUS` — all net-name prefixes). Per origin's R7 explicit instruction, the new helpers `is_ground_pin` / `is_power_pin` / `is_hv_pin` / `is_clock_pin` go in `routing/net_classification.py`. The `CriticalNetDetector` class's `*_PIN_PATTERNS` class attributes default to the module constants via `default_factory` (R7's literal instruction: "the existing `is_ground_net` / `is_power_net` / `is_hv_net` helpers are used" if same; "the pin-pattern version of the helper is added" if distinct — distinct applies here).
- **R9 (test file location):** `tests/routing/test_net_classification.py` (new file, new `TestNetClassification` class). The new module lives in `routing/`, so the test lives in `tests/routing/` (mirrors Doc 2's `tests/core/test_pin_geometry.py` for `core/pin_geometry.py`). The class is small (helpers + classify_net_type precedence + pin helpers) and self-contained.
- **R10 (test for instance default identity):** the default factory returns the same `frozenset` object (not a copy) — `NetClassSpec().ground_patterns is GROUND_NET_PATTERNS` is `True`. The test asserts `is` (identity), not `==` (equality), to prove the canonical set is the single source of truth. A custom override (`NetClassSpec(ground_patterns=frozenset({"FOO"}))`) returns a different object — the test asserts `.ground_patterns == {"FOO"}` for the override.
- **R12 (closure test board):** `piantor_right_unrouted.kicad_pcb` per `router_v6/test_boards.py:50` (already verified in repo research; the path resolves to `packages/temper-placer/tests/fixtures/external/.cache/piantor_right/piantor_right_unrouted.kicad_pcb`). The closure test reads `router_completion_pct`, `drc_errors`, `drc_warnings` from `ClosureResult`. Matches Doc 1 and Doc 2's choice.

### Deferred to Implementation

- **R5 call-site audit (the 20+ count is a lower bound):** the origin's audit enumerated the known call sites; the U2 implementation does a focused `rg` sweep for `is_power_net` / `is_ground_net` / `in [GND, VCC]` / `power_keywords` / `ground_patterns` across `packages/temper-placer/src/temper_placer/` and adds any missed sites to the U2 file list. The audit is part of U2.
- **`is_signal_net` for empty string:** the spec says "signal means none of the above". An empty string is "none of the above" → `is_signal_net("") == True`. The test in R9 should pin this behavior.
- **R6 plane-net override audit:** the U2 implementation does a `rg` sweep for any *other* inlined plane-net set beyond the three enumerated in R6. If found, the implementer applies the same drift/override test and either removes (drift) or keeps with a comment (override). The expected count of additional sets is 0 based on planning research.

---

## Implementation Units

### U1. Add canonical net-classification module in `routing/net_classification.py`

**Goal:** Introduce the canonical surface — module-level `GROUND_NET_PATTERNS`, `POWER_NET_PATTERNS`, `HV_NET_PATTERNS`; the four `is_*_net` helpers; `classify_net_type`; the four `*_PIN_PATTERNS` constants; the four `is_*_pin` helpers — in a new `routing/net_classification.py` module, with full unit-test coverage in a new `tests/routing/test_net_classification.py`.

**Requirements:** R1, R2, R3, R7, R9

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/src/temper_placer/routing/net_classification.py`
- Create: `packages/temper-placer/tests/routing/test_net_classification.py`
- Modify: `packages/temper-placer/src/temper_placer/core/net_types.py` (line 284-288 — refactor `NetClassSpec` pattern fields to default to module constants via `field(default_factory=...)`)

**Approach:**
- Create `routing/net_classification.py` with:
  - Three module-level `frozenset` constants: `GROUND_NET_PATTERNS`, `POWER_NET_PATTERNS`, `HV_NET_PATTERNS`, with the verbatim values from `core/net_types.py:284-288`.
  - Four `is_*_net` free functions: `is_ground_net(name)`, `is_power_net(name)`, `is_hv_net(name)`, `is_signal_net(name)`. The first three are `any(p in name.upper() for p in PATTERNS)`, returning `False` for `None` or empty string. `is_signal_net(name) = not (is_ground_net(name) or is_power_net(name) or is_hv_net(name))`.
  - One `classify_net_type(name)` function: chained `if is_ground_net: return "ground"; elif is_power_net: return "power"; elif is_hv_net: return "hv"; else: return "signal"`. Precedence matches `NetClassSpec.classify_net` exactly.
  - Four `*_PIN_PATTERNS` constants (`POWER_PIN_PATTERNS`, `GROUND_PIN_PATTERNS`, `HV_PIN_PATTERNS`, `CLOCK_PIN_PATTERNS`) with the verbatim values from `routing/critical_net_detector.py:168-198`.
  - Four `is_*_pin(pin_name)` free functions: same shape as `is_*_net` but using the pin patterns.
  - Each helper has a one-line docstring summarizing the matching rule.
- The module is pure-Python (no JAX, no `re` — the patterns are substring, not regex).
- Refactor `core/net_types.py:284-288` to:
  ```python
  from temper_placer.routing.net_classification import (
      GROUND_NET_PATTERNS, POWER_NET_PATTERNS, HV_NET_PATTERNS,
  )
  ...
  ground_patterns: FrozenSet[str] = field(default_factory=lambda: GROUND_NET_PATTERNS)
  power_patterns: FrozenSet[str] = field(default_factory=lambda: POWER_NET_PATTERNS)
  hv_patterns: FrozenSet[str] = field(default_factory=lambda: HV_NET_PATTERNS)
  ```
  Add `from dataclasses import field` (verify it's not already imported) and the new import from `routing.net_classification`. The instance fields remain, but the defaults point at the canonical set. `NetClassSpec.classify_net` (lines 290-319) is unchanged — it still reads `self.ground_patterns` etc.
- Add `TestNetClassification` to `tests/routing/test_net_classification.py` covering all helpers and constants per R9 + R10:
  - AE1 matrix: `is_ground_net("GND") == True`, `is_ground_net("+3V3") == False`, `is_power_net("+3V3") == True`, `is_hv_net("AC_L") == True`, `is_signal_net("DATA1") == True`, `is_ground_net("gnd") == True` (case-insensitive), `is_ground_net("/GND_NET/") == True` (substring match).
  - `classify_net_type` precedence: all four return values + a mixed-name case (`"GND_AND_+3V3"` → `"ground"`, not `"power"`).
  - Empty/None handling: `is_ground_net("") == False`, `is_ground_net(None) == False` (or raises — pick the implementation that reads cleanest, document in the docstring), `is_signal_net("") == True`, `is_signal_net(None) == True`.
  - Pin helpers: `is_ground_pin("GND") == True`, `is_power_pin("VCC_IN") == True`, `is_clock_pin("XTAL1") == True`, `is_hv_pin("SW_NODE") == True`.
  - R10 instance default: `NetClassSpec().ground_patterns is GROUND_NET_PATTERNS` (identity), `NetClassSpec(ground_patterns=frozenset({"FOO"})).ground_patterns == frozenset({"FOO"})` (custom override preserved).
- **Do not** migrate any call site in this unit. This unit is "add the canonical surface and prove it works." The next units migrate callers.

**Patterns to follow:**
- The `routing/` package style: free helpers + module-level constants, no JAX.
- The `core/board.py` style for module-level constants colocated with related dataclasses.
- The `field(default_factory=lambda: ...)` pattern from `dataclasses` for defaulting to a module-level immutable.

**Test scenarios:**
- Happy path: AE1 matrix passes exactly as specified.
- Edge case: `is_ground_net("")` returns `False`; `is_signal_net("")` returns `True`; `is_power_net(None)` returns `False` (or raises — whichever the implementation picks, test pins it).
- Edge case: `is_ground_pin("FOO")` returns `False`; `is_ground_pin("GND")` returns `True`; `is_ground_pin("agnd")` returns `True` (case-insensitive).
- Error path: none — all helpers are total.
- Integration: `NetClassSpec().ground_patterns is GROUND_NET_PATTERNS` (identity proves canonical surface is the source of truth); `NetClassSpec(ground_patterns=frozenset({"X"})).ground_patterns == frozenset({"X"})` (custom override preserved, AE3).

**Verification:** The new test class passes in isolation (`uv run pytest packages/temper-placer/tests/routing/test_net_classification.py -v`). No existing test in `tests/core/test_net_types.py` (or wherever `NetClassSpec` is tested) regresses. The `core/net_types.py:284-288` change is verified by `R10`'s instance-default test.

---

### U2. Big-bang migration: replace 20+ inlined net-classification call sites across the placer source tree

**Goal:** Every "is this net a power/ground/HV/signal net?" decision in the placer source tree is answered by a call to `is_ground_net` / `is_power_net` / `is_hv_net` from `routing/net_classification.py`. After this unit, a `rg` search for `power_keywords` / `ground_patterns` / `_is_power_net` / `_is_ground_net` / `in [GND, VCC]` (and similar local patterns) across `packages/temper-placer/src/temper_placer/` returns zero hits in code that defines the lists; all consumers import from `routing/net_classification`.

**Requirements:** R5, R6, R7, R8, R11, R12

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/core/design_rules.py` (lines 226-292 — `_is_ground_net` / `_is_power_net` private methods; call sites at 226, 230)
- Modify: `packages/temper-placer/src/temper_placer/routing/constraints/design_rules.py` (lines 519-537 — `ground_patterns` / `power_patterns` lists)
- Modify: `packages/temper-placer/src/temper_placer/routing/heuristics.py` (lines 272-273, 292 — uses `is_power_net` / `is_ground_net`; verify imports point at the new module)
- Modify: `packages/temper-placer/src/temper_placer/routing/maze_router.py` (lines 5014-5019 — private `_is_power_net` / `_is_ground_net`; call sites at 4999-5000, 5009-5010)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/thermal_relief.py` (lines 92-104 — inlined power-pattern list)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` (line 407 — uses `PLANE_NETS` from `routing_space.py`; covered by R6 plane-net set migration)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py` (line 37 — inlined ground-pattern list)
- Modify: `packages/temper-placer/src/temper_placer/routing/critical_net_detector.py` (lines 168-198 — `*_PIN_PATTERNS` class attributes; refactor to default to module constants per R7; call sites at 267, 269, 271 use the instance patterns, no further change)
- Modify: `packages/temper-placer/src/temper_placer/losses/enhanced_congestion.py` (line 114 — inlined pattern)
- Modify: `packages/temper-placer/src/temper_placer/heuristics/organizational.py` (lines 565, 583-585, 751-764 — `power_patterns` lists)
- Modify: `packages/temper-placer/src/temper_placer/heuristics/style.py` (line 52 — `power_patterns` list)
- Modify: `packages/temper-placer/src/temper_placer/heuristics/structural.py` (lines 279-281, 500 — `power_patterns` lists)
- Modify: `packages/temper-placer/src/temper_placer/heuristics/force_directed.py` (line 34 — pattern)
- Modify: `packages/temper-placer/src/temper_placer/routing/c_space_pipeline.py` (lines 71-72 — pattern)
- Modify: `packages/temper-placer/src/temper_placer/routing/post_processing/trace_ballooner.py` (lines 33, 36 — pattern; the `is_power_net` method at line 74 is preserved per R5 — the per-instance `power_nets` config is a different concept)
- Modify: `packages/temper-placer/src/temper_placer/routing/pdn_router.py` (line 194 — pattern; the `power_nets` parameter at line 257 is preserved — it's a per-call list, not a pattern match)
- Modify: `packages/temper-placer/src/temper_placer/io/net_class_manager.py` (line 11 — pattern)
- Modify: `packages/temper-placer/src/temper_placer/io/dsn_exporter.py` (line 370 — pattern)
- Modify: `packages/temper-placer/src/temper_placer/io/zone_manager.py` (lines 151-152, 239-240 — patterns)
- Modify: `packages/temper-placer/src/temper_placer/io/config_loader.py` (lines 673-678, 761 — patterns)
- Modify: `packages/temper-placer/src/temper_placer/experiments/feedback_effectiveness.py` (line 55 — pattern)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/zone_aware_slot_generation.py` (lines 20-32 — pattern)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/routing_space.py` (lines 23-37 — `PLANE_NETS` set removed; R6)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py` (lines 26-45 — `TEMPER_PLANE_NETS` removed; R6; the `TEMPER_PLANE_LAYERS` dict at line 50 is preserved — out of scope)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/via_validation.py` (lines 20-47 — `PLANE_NET_PATTERNS` and `_is_plane_net` removed; R6; the call site at line 44 uses `is_ground_net | is_power_net | is_hv_net`)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (line 640 — uses `PLANE_NETS` from `routing_space.py`; covered by R6; the call site uses the helper instead)
- Modify: `packages/temper-placer/tests/routing/test_c_space_pipeline.py` (lines 200-206 — the `_classify_net` assertions; if the test exposes a function name that was renamed, update accordingly)
- Modify: `packages/temper-placer/tests/routing/constraints/test_design_rules.py` (lines 106-124 — the `_classify_net` assertions; same)

**Approach:**
- For each file in the R5 file list:
  - Add the import `from temper_placer.routing.net_classification import is_ground_net, is_power_net, is_hv_net` (using the existing import style — relative imports, multi-line from imports). Some files need only one of the three; the import is right-sized per file.
  - Replace the inlined `power_keywords = [...]` / `ground_patterns = [...]` / `hv_patterns = [...]` / `_is_power_net` / `_is_ground_net` definition with the helper call. The inlined check `any(p in name.upper() for p in power_patterns)` becomes `is_power_net(name)`. The `if net in [GND, VCC, ...]` becomes `if is_ground_net(net) or is_power_net(net)`.
  - For the three plane-net sets (R6): remove the local constant, remove the local helper function (where one exists, e.g., `_is_plane_net` in `via_validation.py`), and replace the call site with `is_ground_net(name) or is_power_net(name) or is_hv_net(name)`. If the file's import block already imports `is_ground_net` etc., no new import is needed.
  - For `routing/critical_net_detector.py` (R7): refactor the four class-level `*_PIN_PATTERNS` lists (lines 168-198) to default to the module-level `*_PIN_PATTERNS` constants from `routing/net_classification` via `default_factory` (or by re-assigning the class attribute to point at the module constant — both forms are acceptable; pick the one that reads cleanest given the class is `dataclass`-based or not). The pin-pattern instance fields are kept for backward compat with subclasses; the defaults point at the canonical set.
- The `core/design_rules.py:_is_ground_net` / `_is_power_net` private methods (lines 257, 266) are removed and the call sites at lines 226, 230 call the free functions. The `DesignRulesParser` class itself is preserved.
- The `routing/post_processing/trace_ballooner.py:74` `is_power_net` method on `TraceBallooner` is preserved — it's a different concept (checks the instance's `power_nets` set, not a pattern match). The `power_patterns` at line 33-36 (if any) migrates; the `power_nets` field stays.
- The `routing/pdn_router.py:194` `power_patterns` migrates; the `power_nets: list[str]` parameter at line 257 is a per-call list (not a pattern set) and stays.
- The `routing/c_space_pipeline.py:71-72` `power_nets` and `ground_nets` lists in the config dataclass are preserved — they're per-instance config, not patterns. The pattern-based check at the call site migrates to use the helper.
- Run the U2 audit (`rg` sweep) for any missed call sites not in the R5 file list. The expected count of missed sites is 0 based on planning research, but the audit is a planning-owned task and the implementer adds any found to the U2 file list.
- Do **not** migrate `CriticalNetDetector.POWER_PATTERNS` / `.GROUND_PATTERNS` / etc. (the net-name regex patterns at lines 79-166). These are regex, not substring; different concept; out of scope.
- Do **not** migrate `TEMPER_PLANE_LAYERS` (the net → plane layer index dict at `power_plane.py:50`). Different concept; out of scope.

**Patterns to follow:**
- The sibling plan's `U2` (`docs/plans/2026-06-23-008-refactor-layer-names-consolidation-plan.md:158-200` and `docs/plans/2026-06-23-010-refactor-pad-position-consolidation-plan.md:167-226`) for the per-file modify + import-pattern style.
- The existing relative-import style at the top of each file (e.g., `from ...core.board import LayerIndex`).
- The `field(default_factory=lambda: ...)` pattern for the `CriticalNetDetector` pin patterns (R7).

**Test scenarios:**
- Happy path: `pytest packages/temper-placer/tests/` passes (R11).
- Edge case: a `rg` search for the inlined patterns across `packages/temper-placer/src/temper_placer/` returns zero hits in code that defines them. Specifically:
  - `rg 'power_keywords\s*=\s*\[' packages/temper-placer/src/temper_placer/` → no matches.
  - `rg 'ground_patterns\s*=\s*[\[\(]' packages/temper-placer/src/temper_placer/` → no matches outside `routing/net_classification.py` and `core/net_types.py` (the latter is the `NetClassSpec` field).
  - `rg '_is_power_net|_is_ground_net' packages/temper-placer/src/temper_placer/` → no matches outside the new module's tests and the (now-deleted) private method definitions.
  - `rg 'PLANE_NETS|TEMPER_PLANE_NETS|PLANE_NET_PATTERNS' packages/temper-placer/src/temper_placer/` → no matches outside `routing/net_classification.py` and the `deterministic/stages/__init__.py` `__all__` re-export (which can be removed).
- Error path: any caller that referenced a removed private method (`_is_ground_net` etc.) is updated to call the helper directly.
- Integration: the closure test on `piantor_right_unrouted.kicad_pcb` produces the same `router_completion_pct`, `drc_errors`, `drc_warnings` as the pre-migration snapshot (R12 / AE2).

**Verification:** A search for the inlined patterns across the modified source files returns zero hits; `pytest` passes; `ruff check` is clean. The 20+ call-site list in R5 is fully migrated (plus any found by the U2 audit).

---

### U3. Pin-helper migration in `routing/critical_net_detector.py` (R7 follow-through)

**Goal:** `CriticalNetDetector` consumes the new `*_PIN_PATTERNS` constants from `routing/net_classification.py` and the pin helpers are reachable from the rest of the placer source tree for any future caller. The four `*_PIN_PATTERNS` class attributes are refactored to default to the module constants; the call sites at lines 267, 269, 271 (which use `self.POWER_PIN_PATTERNS` etc.) continue to work unchanged.

**Requirements:** R7, R11

**Dependencies:** U1, U2

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/routing/critical_net_detector.py` (lines 168-198 — `*_PIN_PATTERNS` class attributes; lines 267, 269, 271 — call sites; verified to continue working)

**Approach:**
- If the class is a `dataclass`, refactor the four `*_PIN_PATTERNS` class attributes to use `field(default_factory=lambda: POWER_PIN_PATTERNS)` etc., matching the `NetClassSpec` R4 pattern.
- If the class is a regular class with class-level mutable defaults, refactor to read the module constant directly at instance-init time (e.g., `self._power_pin_patterns = POWER_PIN_PATTERNS`) and update the class-level list to be a reference to the module constant (`POWER_PIN_PATTERNS: list[str] = POWER_PIN_PATTERNS` — this is an alias, not a copy).
- The call sites at lines 267, 269, 271 continue to read `self.POWER_PIN_PATTERNS` etc. (no call-site change needed — the class-level attribute resolves to the module constant).
- Verify the existing `tests/routing/test_critical_net_detector.py` (or equivalent) tests pass after the refactor.
- The `CriticalNetDetector.POWER_PATTERNS` / `.GROUND_PATTERNS` / `.CLOCK_PATTERNS` / etc. (the net-name regex patterns at lines 79-166) are **not** touched — they are regex, not substring, and out of scope per Key Technical Decisions.

**Patterns to follow:**
- The `NetClassSpec` R4 refactor pattern (U1) for the `field(default_factory=...)` shape.

**Test scenarios:**
- Happy path: `CriticalNetDetector().POWER_PIN_PATTERNS == POWER_PIN_PATTERNS` (the class attribute is the module constant).
- Happy path: `CriticalNetDetector(POWER_PIN_PATTERNS=["VCC"]).POWER_PIN_PATTERNS == ["VCC"]` (custom override preserved).
- Integration: the existing `TestCriticalNetDetector` tests pass after the refactor (R11).

**Verification:** `pytest packages/temper-placer/tests/routing/test_critical_net_detector.py -v` passes. The R7 call sites at lines 267, 269, 271 continue to work with the refactored class-level attributes.

**Note:** U3 is a small follow-through to ensure the R7 refactor is fully consistent. If U2 already accomplishes the R7 refactor (it includes `routing/critical_net_detector.py` in the file list), U3 may be merged into U2 — the plan keeps them separate for clarity but the implementer may combine. U3 is a no-op if U2 already covers it.

---

### U4. Validation pass: pytest, ruff, import-linter-gate, closure test parity

**Goal:** Confirm R11 and R12 — full test suite passes, lint and import boundary check are clean, and the placer's 4-layer integration test (closure test on `piantor_right_unrouted.kicad_pcb`) produces the same routing output as before the migration.

**Requirements:** R11, R12, AE1, AE2, AE3

**Dependencies:** U1, U2, U3

**Files:** (no new files; this unit is a verification gate)

**Approach:**
- Run `uv run pytest packages/temper-placer/tests/` and resolve any failures. The most likely failure modes are: (a) a call site that used a private method (`_is_ground_net` etc.) and now needs the helper, (b) a test that asserted on a removed local constant (`PLANE_NETS` etc.), (c) the `TestCriticalNetDetector` tests that expected class-level mutable defaults (the R7 refactor changes the defaulting shape).
- Run `uv run ruff check packages/temper-placer/` and resolve any new violations.
- Run `uv run python scripts/import_linter_gate.py` and resolve any new violations. The new `routing/net_classification.py` lives in `routing/`, and `core/net_types.py` imports from `routing/` (a new direction). The import-linter config may need an allowlist entry for `core → routing` (the linter typically allows `routing → core` but not vice versa). The implementer adds the allowlist entry with a justification + ticket reference per the AGENTS.md import boundary convention.
- Run the closure test on `piantor_right_unrouted.kicad_pcb` and confirm the output matches the pre-migration snapshot: same `router_completion_pct`, same `drc_errors`, same `drc_warnings`, same trace coordinates for `initial_rotation == 0 and initial_side == 0` components (bit-identical) and same `classify_net_type` answer for every net on the board (R12 / AE2).
- Capture the closure-test report and link it from the plan's PR description.
- For the `classify_net_type` per-net parity check, dump the answers for every net in `piantor_right_unrouted.kicad_pcb` (e.g., via a small ad-hoc script: `for net in pcb.nets: print(net.name, classify_net_type(net.name))`) and diff against the pre-migration dump. The diff is expected to be empty for the closure-test board (because the canonical patterns are the source of truth and the prior local lists were subsets of the canonical patterns for the board's actual net names).

**Patterns to follow:**
- The sibling plan's `U4` (`docs/plans/2026-06-23-008-refactor-layer-names-consolidation-plan.md:237-263` and `docs/plans/2026-06-23-010-refactor-pad-position-consolidation-plan.md:264-292`) for the verification-gate structure.
- The repo's existing CI commands (ruff, pytest, import-linter-gate, closure test).

**Test scenarios:**
- Happy path: `uv run pytest` exit code 0; `uv run ruff check` exit code 0; `uv run python scripts/import_linter_gate.py` reports zero new violations (or the new `core → routing` allowlist entry is approved).
- Integration: closure test report matches the pre-migration snapshot for `piantor_right_unrouted.kicad_pcb` (4-layer board).
- Integration: `classify_net_type` returns the same answer for every net in the closure-test board, pre- and post-migration (AE2).
- Edge case: `uv run pytest packages/temper-placer/tests/routing/test_net_classification.py` passes (the new helper tests from U1).
- Edge case: `uv run pytest packages/temper-placer/tests/core/test_net_types.py` passes (the retained `NetClassSpec` tests, with the new R10 default-identity assertion).

**Verification:** All four checks exit 0; the closure-test diff is empty (or the new allowlist entry is approved and committed); the `classify_net_type` per-net parity dump is identical; the migration can land atomically as one PR per the origin's success criterion.

---

## System-Wide Impact

- **Interaction graph:** The migration is structurally a call-site rename. No callbacks, observers, or middleware change behavior. The interfaces affected are: (a) the new `routing/net_classification.py` module (new public surface; pure addition), (b) `core/net_types.py:NetClassSpec`'s default pattern fields (re-pointed at module constants via `default_factory`; instance fields retained for backward compat), (c) `routing/critical_net_detector.py:CriticalNetDetector`'s `*_PIN_PATTERNS` class attributes (re-pointed at module constants; class-level list retained for backward compat), and (d) the 20+ call sites that switch from local lists/helpers to the canonical helpers. The runtime semantics for the closure-test board are unchanged (R12 / AE2).
- **Error propagation:** The new helpers are total: `is_ground_net(None) == False`, `is_power_net("") == False`, etc. The migration is **less strict** than the prior inlined code only in the sense that some inlined `_is_power_net` implementations did substring match with smaller keyword sets and would have returned `False` for a net name the canonical set would have classified as power — the canonical helper returns the "correct" answer per `core/net_types.py:284-288`. No new error paths are introduced; no existing error paths are tightened.
- **State lifecycle risks:** No persistent state is added. The `routing/net_classification.py` module is imported across files; Python's import caching ensures the same `frozenset` instances are shared. The `NetClassSpec` instance fields default to the module constants via `field(default_factory=lambda: GROUND_NET_PATTERNS)` — the default factory returns the same object reference (the canonical frozenset) on every instantiation, so the canonical set is genuinely the single source of truth (R10's identity assertion). No cache, no cleanup, no partial-write concern.
- **API surface parity:** The public API of `routing/net_classification.py` grows (3 net-pattern constants + 4 net helpers + `classify_net_type` + 4 pin-pattern constants + 4 pin helpers = 16 new public names) but does not break. The public API of `core/net_types.py:NetClassSpec` is unchanged in signature (the pattern fields are still `FrozenSet[str]`); only the default values point at the canonical set. The public API of `routing/critical_net_detector.py:CriticalNetDetector` is unchanged in signature; only the class-level `*_PIN_PATTERNS` defaults point at the canonical set. The public API of every consumer file changes only at the function-call level: a helper call replaces a local list+check. No public dataclass fields are added, renamed, or removed.
- **Import boundary:** The new `core/net_types.py:NetClassSpec` default-factory imports from `routing/net_classification` (a `core → routing` direction). The import-linter typically allows `routing → core` (lower layers import from higher layers) but not vice versa. The implementer adds an allowlist entry to `import-linter-allowlist.yaml` with justification "NetClassSpec pattern defaults are unified onto the canonical surface per consolidation plan 2026-06-23-011". If the linter rejects the direction, the alternative is to define the three pattern constants in `core/net_types.py` and have `routing/net_classification.py` re-export them — but this inverts the origin's R1 directive (which says the canonical surface lives in `routing/net_classification.py`). The implementer picks the lighter-touch option per the import-linter-allowlist.yaml convention.
- **Integration coverage:** The closure test (U4) is the integration scenario. A 4-layer board through the full pipeline exercises every migrated call site end-to-end. The unit tests in U1 cover the canonical surface; U2's per-file modifications are covered by `pytest`; U3 is covered by the `TestCriticalNetDetector` tests.
- **Unchanged invariants:** The 4-layer `LayerStackup` from Doc 1's plan is unchanged. The 6-layer path (`io/kicad_exporter.py:1277`, `io/kicad_parser.py:1277`) is unchanged. The `pad_world_position` helper from Doc 2's plan is unchanged. The `NetClassSpec.classify_net` class method is preserved (R4 retains the existing signature). The `CriticalNetDetector.POWER_PATTERNS` / `.GROUND_PATTERNS` / etc. (the net-name regex patterns) are unchanged. The `TEMPER_PLANE_LAYERS` dict (the net → plane layer index companion to `TEMPER_PLANE_NETS`) is unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Missed call site (a 21st file the audit didn't find) | U2's `rg` verification (test scenario) plus full pytest run; any test failure is a signal |
| `PLANE_NETS` exact-match vs canonical substring-match — a hypothetical "drift" net name (e.g., `+15V_PLANE`) that the inlined set rejected but the canonical helper accepts | The substring match is the documented canonical behavior (`NetClassSpec.classify_net` at `core/net_types.py:307-315`); the migration accepts this. U2's audit confirms the closure-test board's net names are not affected. |
| `CriticalNetDetector.POWER_PIN_PATTERNS` etc. is a class-level mutable default; refactoring to a module constant reference may break subclasses that mutate the class attribute | R7 preserves the class-level attribute name; the value is the module constant. Subclasses that override via constructor (per `__init__` lines 200-227) continue to work. Subclasses that mutate the class attribute directly are an anti-pattern and are not supported. |
| `NetClassSpec` instance field default factory: `field(default_factory=lambda: GROUND_NET_PATTERNS)` returns the same object reference on every instantiation — but if a test mutates the returned object, it mutates the canonical set | The canonical set is a `frozenset` (immutable). Mutation is not possible. The R10 identity test proves the canonical set is the source of truth without risk of mutation. |
| Closure test output drifts (different routing for the same board) | U4 explicitly compares against the pre-migration snapshot; bit-identical is the success criterion (R12 / AE2). The per-net `classify_net_type` parity dump is the proof. |
| Import boundary violation: `core → routing` is a new direction | U4 runs the gate; the implementer adds the allowlist entry per the AGENTS.md convention. Alternative: define the canonical constants in `core/net_types.py` and re-export from `routing/net_classification.py`, but this inverts the origin's R1 directive. |
| `is_signal_net("")` and `is_signal_net(None)` return `True` — a None net name is classified as "signal" | This is the only total behavior consistent with the origin's `is_signal_net = not (others)` definition. Documented in the helper's docstring; pinned by U1's test. |
| The three `*_PIN_PATTERNS` constants have overlapping entries (e.g., `"GND"` is in both `GROUND_PIN_PATTERNS` and could be in `CLOCK_PIN_PATTERNS` if a clock net is named `GND_CLK`) | The pin helpers check the patterns in precedence order (ground > power > hv > clock, matching the net helpers), and `is_*_pin` is a one-category check (returns `True` if the pattern is in any of the four sets). The exact overlap is a property of the source data; the helpers don't introduce new overlap. |

---

## Documentation / Operational Notes

- The `routing/net_classification.py` module docstring should call out: (a) the verbatim source of the patterns (`core/net_types.py:284-288`), (b) the precedence `ground > power > hv > signal` (matching `NetClassSpec.classify_net`), (c) the substring vs exact-match convention (substring, case-insensitive), and (d) the empty/None handling (returns `False` for the three category checks; `is_signal_net` returns `True`).
- The `core/net_types.py:NetClassSpec` field docstrings should note that the defaults are now the canonical surface from `routing/net_classification.py`.
- The PR description should call out: (a) the 20+ drift sites are gone, (b) the three plane-net sets are removed in favor of the helper, (c) the pin patterns are unified onto the canonical surface (R7), (d) the closure-test output is bit-identical (link to the U4 report), (e) the import boundary allowlist entry (the `core → routing` direction) is approved per the AGENTS.md convention.
- The PR description should note that the `NetClassSpec.classify_net` instance method is preserved (R4) so any code that uses the class method continues to work unchanged.
- The PR description should note that `CriticalNetDetector.POWER_PATTERNS` / `.GROUND_PATTERNS` / etc. (the net-name regex patterns) are unchanged — they are a different concept (regex, not substring; net-name, not pin-name).
- No runbook or operational doc updates needed — the migration is internal-source-only and changes no user-facing CLI, no config file, no environment variable.

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-23-net-classification-consolidation-requirements.md](docs/brainstorms/2026-06-23-net-classification-consolidation-requirements.md)
- **Sibling plan (Doc 1, shipped):** [docs/plans/2026-06-23-008-refactor-layer-names-consolidation-plan.md](docs/plans/2026-06-23-008-refactor-layer-names-consolidation-plan.md) — establishes the SSOT pattern this plan follows
- **Sibling plan (Doc 2, shipped):** [docs/plans/2026-06-23-010-refactor-pad-position-consolidation-plan.md](docs/plans/2026-06-23-010-refactor-pad-position-consolidation-plan.md) — Doc 2's `tests/core/test_pin_geometry.py` convention; closure-test board path
- **Related code:**
  - `packages/temper-placer/src/temper_placer/core/net_types.py:283-288` — `NetClassSpec` pattern fields (canonical source)
  - `packages/temper-placer/src/temper_placer/core/net_types.py:290-319` — `NetClassSpec.classify_net` (reference implementation; precedence source)
  - `packages/temper-placer/src/temper_placer/routing/critical_net_detector.py:168-198` — `*_PIN_PATTERNS` class attributes (R7 source)
  - `packages/temper-placer/src/temper_placer/router_v6/routing_space.py:23-37` — `PLANE_NETS` (R6 site 1, removed)
  - `packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py:26-45` — `TEMPER_PLANE_NETS` (R6 site 2, removed)
  - `packages/temper-placer/src/temper_placer/deterministic/stages/via_validation.py:20-47` — `PLANE_NET_PATTERNS` (R6 site 3, removed)
  - `packages/temper-placer/src/temper_placer/routing/maze_router.py:5014-5019` — most-extreme drift case (private `_is_power_net` / `_is_ground_net`)
  - `packages/temper-placer/src/temper_placer/core/design_rules.py:226-292` — `DesignRulesParser._is_ground_net` / `_is_power_net` private methods (R5 target)
  - `packages/temper-placer/src/temper_placer/router_v6/test_boards.py:50` — `PIANTOR_PATH` (canonical closure test board, matching Doc 1 and Doc 2)
  - `packages/temper-placer/src/temper_placer/regression/closure_test.py:151-209` — `ClosureResult` dataclass (`router_completion_pct`, `drc_errors`, `drc_warnings`)
- **Related plans:**
  - `docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md` — established the "one canonical location, import-everywhere" pattern
- **Future docs (out of scope here):** A* primitives consolidation (Doc 4 in the 4-doc sequence)
- **External docs:** None used
