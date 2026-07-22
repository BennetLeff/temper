---
title: "Zone/Pour Shape Correctness & Cross-Class Clearance"
type: fix
status: completed
date: 2026-07-21
origin: docs/brainstorms/2026-07-21-zone-pour-shape-and-cross-class-clearance-requirements.md
---

# Zone/Pour Shape Correctness & Cross-Class Clearance

## Summary

Filling router_v6's emitted zones with real copper (`pcbnew.ZONE_FILLER`) regresses `shorting_items` (76.7 mean with zones off vs 84.9 mean with zones on and filled — see `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md`). Root cause: `compute_zone_for_net`'s `_bounding_box` (`packages/temper-placer/src/temper_placer/router_v6/zone_emission.py:24-35`) computes an axis-aligned rectangle over *all* of a net's pad positions, producing zones spanning 40-96% of the board for distributed nets, and `_zone_params_for_net` (`packages/temper-placer/src/temper_placer/router_v6/adapter.py:545-569`) only checks a zone's own netclass clearance — there is no cross-class pairwise enforcement.

This plan wires cross-class pairwise clearance (`DesignRules.class_pairs`, already consumed by CP-SAT placement) into zone emission, sets KiCad-native `(priority N)` on every zone (currently absent — confirmed via `power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb`'s real zone data and `scripts/kicad_fill_zones.py`'s `ZONE_FILLER` usage), and localizes pour shape to each net's actual copper via `shapely` convex hulls (already a project dependency) instead of one board-spanning box. `enable_zone_pours` stays behind its existing default-off flag — this plan's success criterion is "filling zones no longer regresses `shorting_items`," not promotion, which is gated separately on the still-open U5 tree-executor-completion work (`docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md`).

---

## Requirements Traceability

| Origin Requirement | Addressed By |
|---|---|
| R1 (max of own clearance + `class_pairs`) | U1 |
| R2 (native KiCad zone priority) | U2 |
| R3 (no reimplementing `ZONE_FILLER`) | U1, U2 — both only configure standard zone fields |
| R4 (never weaken existing per-net clearance) | U1 (test scenarios explicitly assert same-class clearance is unchanged) |
| R5 (shape localization) | U3 |
| R6 (localization is a conflict-surface reduction, not a full fix for global nets) | U3's test scenarios; U4's measurement is scoped to catch this honestly |
| R7 (multi-sample re-measurement methodology) | U4 |
| R8 (promotion out of scope) | Scope Boundaries |

---

## High-Level Technical Design

*This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Cross-class clearance resolution** (mirrors `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py:106-119`'s pattern exactly, but keyed by the same netclass names zone emission already resolves via `TEMPER_NET_ASSIGNMENTS` — not the coarser 4-bucket `classify_net_type()` CP-SAT uses elsewhere, since `class_pairs` keys are the fuller 8/9-class names and a mismatched key space would silently miss every lookup):

```
for each zone-eligible net's netclass NC:
    own_clearance = TEMPER_NET_CLASSES[NC].clearance
    effective_clearance = own_clearance
    for other_NC in {netclasses of all other zone-eligible nets present on the board}:
        if other_NC == NC: continue
        pair_key = tuple(sorted((NC, other_NC)))  # class_pairs is keyed by tuple, not list -- list keys raise TypeError: unhashable type
        pair_clearance = class_pairs.get(pair_key, {}).get("clearance", max(own_clearance, TEMPER_NET_CLASSES[other_NC].clearance))
        effective_clearance = max(effective_clearance, pair_clearance)
    zone.clearance = effective_clearance
```

Resolving against *all other zone-eligible netclasses present* (a small, bounded set — currently ≤8) rather than a geometric pairwise-overlap test keeps this cheap and avoids needing to know actual zone geometry ahead of the clearance decision — it answers the origin doc's deferred question ("every zone pairwise, or only overlapping ones?") conservatively: always resolve against every other present class, since the current shapes overlap so extensively that a geometric pre-filter would rarely skip anything anyway.

**Note on this premise (U1/U3 interaction):** the "extensively overlap" justification is measured against *pre-fix* board-spanning bounding-box shapes (origin doc's 40-96%-of-board figures). U3, landing in the same plan, is specifically designed to shrink those shapes for nets where clustering helps. This doesn't make U1's approach incorrect — always-resolve-against-all-present-classes is the conservative (safe) direction regardless of geometry, never under-enforcing clearance — but it can cost more copper area than strictly necessary for nets that no longer geometrically overlap a given class after U3 lands. This is an efficiency question, not a correctness one; revisit only if U4's measurement shows the conservatism meaningfully hurts the `unconnected_items` improvement.

**Zone priority**: `TEMPER_NET_CLASSES` already has an authoritative `dru_priority` field on every entry (`packages/temper-placer/src/temper_placer/core/design_rules.py:322-429`; ACMains=10 … HighCurrent=90, lower number = higher real-world priority per `AGENTS.md`'s N4 SSOT convention). KiCad zone `(priority N)` is the opposite direction (higher number wins/fills first — confirmed via the corpus example). Invert: `kicad_priority = MAX_DRU_PRIORITY - dru_priority` (or an equivalent monotonic inversion) so ACMains gets the highest KiCad zone priority number and HighCurrent the lowest.

**Shape localization**: pad positions gathered at `adapter.py:618-636` are currently a flat `list[(x, y)]` per net with no retained component/connectivity identity. Cluster spatially (simple distance-threshold grouping is sufficient — this is a bounded, low-cardinality problem, not a case needing a general-purpose clustering library) into connected groups, then take `shapely.geometry.MultiPoint(cluster_positions).convex_hull` per group instead of one bounding box over everything — **except for `GND`/`ACMains`/`HighVoltage`-class (return/ground path) nets, which are exempted from clustering and keep a single hull over all their pads**, since fragmenting a ground/return net's pour into disconnected islands directly contradicts the origin doc's own electrical justification for pours (continuous plane for EMI/loop-area control). Nets whose pads are all mutually close collapse to one cluster (little change from today); nets with genuinely distant pad groups (non-exempt rails) still produce multiple hulls, each local to its own cluster rather than one shape spanning the gap between them — but a rail with pads legitimately scattered across the whole board will still produce a hull covering most of the board (or, for exempt classes, a single hull over all of them), which is expected and is why U1/U2 (not U3) are the requirements this fix's success depends on most (see origin doc R6).

---

## Output Structure

No new files or directories — this plan modifies existing modules in place:

```
packages/temper-placer/src/temper_placer/router_v6/
├── zone_emission.py      (ZoneDefinition gains `priority`; _bounding_box replaced/supplemented by cluster+hull; emit_zone_s_expr emits (priority N))
└── adapter.py             (_zone_params_for_net extended or a new helper added for cross-class resolution; zone-emission loop in _write_routes_to_content wires the new clearance/priority values through)

packages/temper-placer/tests/router_v6/
├── test_zone_emission.py  (new tests: priority field, hull-vs-bbox shape tests)
└── test_adapter.py        (new tests: TestZoneParamsForNet extended or a new TestCrossClassZoneClearance class)

packages/temper-placer/tests/placer/cp_sat/
└── test_zone_pour_shape_clearance_measurement.py  (new, U4 — standalone verification, follows test_zone_pour_production_measurement.py's pattern)
```

---

## Implementation Units

### U1. Cross-class pairwise clearance resolution

**Goal:** A zone's effective clearance is the maximum of its own netclass's clearance and any applicable `DesignRules.class_pairs` entry against every other zone-eligible netclass present on the board, so a 0.25mm-clearance zone can no longer legally sit directly against a 6mm-clearance zone's boundary.

**Requirements:** R1, R3, R4 (origin doc)

**Dependencies:** None (first unit; independent of U2/U3)

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — add cross-class resolution (extend `_zone_params_for_net` or add a sibling helper consumed by the zone-emission loop at `adapter.py:726-755`); thread `design_rules` into `_write_routes_to_content` (see Approach — this is a required signature change, not optional)
- `packages/temper-placer/tests/router_v6/test_adapter.py` — new test coverage

**Approach:** Resolve each net's netclass via `TEMPER_NET_ASSIGNMENTS.get(net_name, "")` (the same lookup `_zone_params_for_net` already uses), not `classify_net_type()` — the two use different class vocabularies and only the `TEMPER_NET_ASSIGNMENTS`/`TEMPER_NET_CLASSES` names match `class_pairs`' keys. Read `class_pairs` defensively via `getattr(design_rules, 'class_pairs', {})`, matching the existing CP-SAT consumer's pattern (`netclass_constraints.py:106-119`) — `class_pairs` is a dynamically-set attribute, not a declared `DesignRules` dataclass field. The set of "other zone-eligible netclasses present on the board" comes from the same netlist iteration the zone-emission loop already performs (`adapter.py:726-755`'s existing loop over `pad_positions`).

**Required plumbing (verified against source, not optional):** `_write_routes_to_content(pcb_content: str, result: Any) -> str` (`adapter.py:572`) currently receives no `design_rules` parameter, and neither call site in `route_pcb()` (`adapter.py:520-522`, `adapter.py:531`) passes one — `route_pcb()`'s own `design_rules` argument (the one built via `netclass_loader.load_netclass_rules()` and carrying `.class_pairs`) is currently only used for `_apply_placements_to_pcb` and `layer_assignments_from_netclass`. The zone-emission loop must gain access to this real `design_rules` object — add it as a parameter to `_write_routes_to_content` and pass it through from both call sites. **Do not** reach for `result.pcb.design_rules` as a substitute: that is a different, unrelated `stage0_data.DesignRules` class (parsed from the `.kicad_pcb` file's own `net_class` blocks) with no `class_pairs` concept at all — the defensive `getattr(design_rules, 'class_pairs', {})` pattern would silently return `{}` for every net if pointed at it, no-opping this entire unit without ever failing loudly. This is the exact silent-failure shape documented in `docs/solutions/conventions/verify-netclass-clearance-on-the-routing-path-2026-07-12.md`.

**Patterns to follow:** `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py:106-119` (the `max(own, class_pairs override)` resolution) and `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md` (the SSOT consumption pattern generally — extend `DesignRules` consumption, don't build a parallel lookup).

**Test scenarios:**
- Happy path: a `vcc` zone (Power, 0.25mm) and a `+340V_BUS` zone (HighVoltage, 6.0mm) present on the same board resolve to 6.0mm effective clearance for the `vcc` zone (the stricter applicable rule), not 0.25mm.
- Happy path: two zones of the same netclass (e.g. two `GND`-class nets) resolve to their own class's clearance, unchanged from today — confirms R4 (never weaken an existing guarantee).
- Edge case: a netclass with no explicit `class_pairs` entry against another present class falls back to `max(own_clearance, other_clearance)`, matching the CP-SAT consumer's fallback behavior exactly.
- Edge case: only one zone-eligible netclass present on the board (e.g. a minimal test board) — no cross-class resolution needed, effective clearance equals own clearance.
- Integration scenario: the value computed by this resolution is the value that actually reaches the emitted `(zone ... (connect_pads yes (clearance N)))` s-expression and, after a real `pcbnew.ZONE_FILLER` fill, the filled polygon respects it — not just that the Python function returns the right number in isolation (per `docs/solutions/conventions/verify-netclass-clearance-on-the-routing-path-2026-07-12.md`'s caution: SSOT values have silently failed to reach the actual enforcement point in this codebase before).
- Integration scenario: calling `route_pcb(..., design_rules=<a DesignRules with class_pairs populated>, enable_zone_pours=True)` end-to-end produces zones whose emitted clearance reflects the cross-class resolution — confirming `design_rules` was actually threaded through `_write_routes_to_content` into the zone-emission loop, not silently dropped or shadowed by `result.pcb.design_rules`.

**Verification:** Unit tests pass; a manual `pcbnew.ZONE_FILLER`-based fill of a board with adjacent HV/Power-class zones (e.g. reusing `scripts/kicad_fill_zones.py`) shows the filled copper maintains the stricter clearance, inspected directly in the output `.kicad_pcb`.

---

### U2. KiCad-native zone priority

**Goal:** Every emitted zone carries a `(priority N)` field derived from its netclass's existing `dru_priority`, so `pcbnew.ZONE_FILLER` resolves overlapping zone territory deterministically — safety-critical nets (ACMains/HighVoltage) are never displaced by a lower-priority pour.

**Requirements:** R2, R3 (origin doc)

**Dependencies:** None (independent of U1/U3; can land in either order relative to U1)

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/zone_emission.py` — `ZoneDefinition` gains a `priority: int = 0` field; `emit_zone_s_expr` emits `(priority N)`
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — thread the resolved priority through the `ZoneDefinition` reconstruction at `adapter.py:745-752`
- `packages/temper-placer/tests/router_v6/test_zone_emission.py` — new test coverage

**Approach:** Invert `TEMPER_NET_CLASSES[nc].dru_priority` (lower = higher real-world priority, e.g. ACMains=10) into a KiCad zone priority number (higher = fills/wins first, confirmed via `power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb`'s real zone data). Emit `(priority N)` positioned immediately after the `(hatch ...)` clause and before `(connect_pads ...)`, matching the corpus-confirmed field ordering exactly — `ZONE_FILLER` may be order-sensitive in ways not worth risking.

**Test scenarios:**
- Happy path: an ACMains-class zone's emitted `(priority N)` is numerically higher than a Signal-class zone's.
- Happy path: `emit_zone_s_expr`'s output contains `(priority N)` positioned between `(hatch ...)` and `(connect_pads ...)`, matching the corpus convention (substring/ordering assertion, mirroring existing tests like `test_emit_zone_s_expr_includes_fill_directive`).
- Edge case: a net whose class has no explicit `dru_priority` override uses a sane default rather than raising or emitting a malformed field.
- Integration scenario: after a real `ZONE_FILLER` fill of two overlapping zones with different priorities, the higher-priority zone's filled copper claims the contested area and the lower-priority zone's filled copper is excluded from it (inspect `(filled_polygon ...)` data or visually via KiCad).

**Verification:** Unit tests pass; a manual fill of two deliberately-overlapping test zones with different priorities shows the expected exclusion in the filled output.

---

### U3. Localized pour shape via clustered convex hull

**Goal:** Replace the board-wide axis-aligned bounding box with a convex hull computed per spatially-clustered group of a net's pad positions, reducing zone-vs-zone and zone-vs-track conflict surface for nets where pads aren't genuinely board-distributed.

**Requirements:** R5, R6 (origin doc)

**Dependencies:** None (independent of U1/U2)

**Files:**
- `packages/temper-placer/src/temper_placer/router_v6/zone_emission.py` — new clustering + hull computation, replacing or supplementing `_bounding_box`
- `packages/temper-placer/tests/router_v6/test_zone_emission.py` — new test coverage

**Approach:** Add a simple spatial clustering pass over the net's pad positions (distance-threshold grouping is sufficient given the low point counts involved — no general-purpose clustering library needed beyond what's already available). For each resulting cluster, compute `shapely.geometry.MultiPoint(cluster_positions).convex_hull` and expand by the net's margin (reusing the existing margin/clearance values from U1), emitting one zone polygon per cluster instead of one box over every position. `shapely` is already a direct dependency (`pyproject.toml`), used elsewhere in this codebase (`core/courtyard.py`, `geometry/drc_inflate.py`) — no new dependency.

**Continuity exemption (required, not optional):** the origin doc's own stated justification for zone/pour is that "ground needs a continuous plane for EMI/loop-area control in a switching supply" — clustering-by-construction fragments a net's pour into disconnected islands whenever its pads are spatially separated, which is the opposite of what continuity-sensitive nets need. Clustering shall **not** apply to `GND`, `ACMains`, or `HighVoltage`-class nets (and any net whose `TEMPER_NET_ASSIGNMENTS` class is a return/ground path) — these keep today's single-shape-over-all-positions behavior (a hull over *all* the net's pads, not a board-wide rectangle, but still one connected shape, not per-cluster islands). Clustering applies only to netclasses where fragmentation is electrically acceptable (e.g. `Power`, `Signal`, `GateDrive` rails that aren't themselves return paths).

**Patterns to follow:** `packages/temper-placer/src/temper_placer/core/courtyard.py`'s existing `shapely.geometry.Polygon`/`shapely.affinity` usage for the general pattern of working with `shapely` geometry in this codebase.

**Test scenarios:**
- Happy path: a net whose pads are all tightly clustered (e.g. all pins of one connector) produces a hull materially smaller than the old board-wide bounding box would have been.
- Edge case: a net with pads in two widely-separated clusters produces two separate hull polygons, not one hull spanning the gap between them (which would be worse than today's box, not better).
- Known-limitation scenario (explicitly asserted, not silently accepted): a net whose pads are genuinely scattered across most of the board (simulating `PWR_RTN`/`DC_BUS_RTN`) still produces a hull covering most of the board — this test exists to confirm the plan's own stated limitation (R6) rather than let a future change silently break the assumption that U1/U2 carry the real fix.
- Edge case: a net with a single pad position (degenerate hull) does not crash and produces a sane minimal shape (matching today's single-point bounding-box behavior).
- Covers the continuity exemption. Given a `GND`-class net with pads in two widely-separated clusters, when its zone shape is computed, then it produces one connected hull covering all pads (not fragmented per-cluster islands) — confirming ground/return-path nets are exempted from clustering, unlike a same-shaped `Signal`-class net in the same scenario, which does fragment.

**Verification:** Unit tests pass; visual/measured comparison of total zone polygon area before and after, on a board with both tightly-clustered and widely-distributed nets, shows the expected reduction for the former and little change for the latter.

---

### U4. Multi-sample verification against the real filled artifact

**Goal:** Confirm the combined fix (U1-U3) actually resolves the `shorting_items` regression, measured the same way the regression was originally diagnosed — real `pcbnew.ZONE_FILLER` fill, multiple routing seeds, multiple DRC samples per board — not a single noisy sample.

**Requirements:** R7 (origin doc)

**Dependencies:** U1, U2, U3 (measures their combined effect)

**Files:**
- `packages/temper-placer/tests/placer/cp_sat/test_zone_pour_shape_clearance_measurement.py` (new) — standalone verification test, following `test_zone_pour_production_measurement.py`'s existing pattern (`_kicad_cli_available()`, `_fill_zones_via_pcbnew()` shelling out to `scripts/kicad_fill_zones.py`, `_run_drc()`)

**Approach:** This is a standalone verification unit (script/test run manually as part of implementing and validating this plan), not a new CI-blocking or CI-informational job — `enable_zone_pours` stays behind its existing default-off flag and this plan does not change CI gating (see Scope Boundaries). It produces the evidence a future promotion decision would need, without being that decision itself. Route multiple seeds through `route_pcb(..., enable_zone_pours=True)`, fill each with `pcbnew.ZONE_FILLER`, run `kicad-cli pcb drc` multiple times per board, and compare the `shorting_items`/`unconnected_items` distributions against a zones-off baseline computed the same way — mirroring the exact methodology already validated during this investigation (4 seeds × 3 DRC samples was sufficient to get non-overlapping distributions in the pre-fix measurement).

**Per-net diagnostic (required, not just aggregate counts):** U2's priority-based exclusion mechanism can, in principle, let a high-priority zone (e.g. ACMains) claim contested territory that a lower-priority net actually needed near its own pads — converting a `shorting_items` violation into a new `unconnected_items`/isolated-copper problem for a *different* net. The board-wide aggregate distributions above wouldn't attribute a regression to this cause specifically. In addition to the aggregate comparison, log or spot-check each zone-eligible net's post-fill copper area/connectivity against its own pre-fill zone, so a priority-exclusion-caused regression on a specific net class is attributable rather than folded into an unexplained aggregate number.

**Cross-KiCad-version check:** local manual verification in U1/U2 runs against the locally-installed pcbnew (10.0.4). CI's `kicad-cli`/pcbnew is 8.0.9 — the same version gap that caused the original `--refill-zones` flag to not exist there. `ZONE_FILLER`'s priority/clearance fill semantics are assumed identical across these versions (see Dependencies/Assumptions) but this has not been independently confirmed for this specific behavior. Treat this unit's `kicad-cli pcb drc`-based measurement — which can run in CI's actual environment — as the authoritative check of priority/clearance behavior, not U1/U2's local manual verification alone.

**Patterns to follow:** `packages/temper-placer/tests/placer/cp_sat/test_zone_pour_production_measurement.py`'s existing helpers (`_kicad_cli_available`, `_fill_zones_via_pcbnew`, `_run_drc`) — reuse directly rather than reimplementing.

**Test scenarios:**
- Covers R7. Given the U1-U3 fix has shipped, when the production board is routed across 4+ seeds with `enable_zone_pours=True`, filled via `pcbnew.ZONE_FILLER`, and DRC'd 3+ times per board, then the resulting `shorting_items` range does not exceed the zones-off baseline range measured the same way.
- Given the same measurement, when `unconnected_items` is compared to the zones-off baseline, then the improvement previously measured (260 → ~255) is preserved or improved, not regressed by the shape/clearance changes.
- Test expectation: this unit produces a measurement report (printed/logged distribution comparison), not a pass/fail CI gate — `pytest.skip` on missing `kicad-cli`/`pcbnew` per the existing pattern, and the test's assertions (if any) should be soft evidence-gathering assertions, not hard promotion gates, consistent with this plan not deciding promotion.
- Covers the per-net diagnostic. Given the combined fix has shipped, when each zone-eligible net's post-fill copper area/connectivity is compared against its own pre-fill zone, then any net showing a meaningful drop is logged individually (not just visible as an unexplained shift in the board-wide aggregate), so a priority-exclusion-caused regression on a specific net class would be attributable if it occurred.

**Verification:** Running the new test locally (or in a manual CI dispatch) produces the distribution comparison table; the resulting numbers are recorded (e.g. appended to the diagnosis doc or a new dated solutions-doc addendum) as the evidence base for the future promotion decision.

---

## Scope Boundaries

### Deferred to Follow-Up Work
- Promoting `enable_zone_pours` to default-on — gated separately on the still-open U5 zone/exemption policy (tree-executor completion), per origin doc R8. This plan's success criterion is the U4 measurement showing no regression, not promotion.
- Wiring U4's verification into a CI job (informational or blocking) — this plan keeps it a standalone, manually-run measurement; adding CI wiring is straightforward follow-up once the fix's real-world evidence is in hand, but is not required for this plan's own success criteria.
- Redesigning `TEMPER_NET_ASSIGNMENTS`/`TEMPER_NET_CLASSES` or `netclass_rules.yaml`'s schema — this plan consumes `class_pairs` and `dru_priority` as they exist today.
- The pre-existing `_write_routes_to_content` return-type/annotation mismatch (declared `-> str`, actually returns a 2-tuple) noted during research — unrelated to this fix, not touched.

### Outside This Plan's Identity
- The router non-determinism fix (`_compute_net_order`'s `PYTHONHASHSEED` dependency) — already shipped, PR #264.
- The U5 zone/exemption policy (tree-executor completion for plane-style nets currently failing to route at all) — separate requirements doc, separate plan.

---

## Key Technical Decisions

- **Resolve cross-class clearance against all other present zone-eligible netclasses, not a geometric overlap pre-filter:** the origin doc's deferred question ("every zone pairwise, or only overlapping ones?") is answered conservatively — given current shapes overlap so extensively, a geometric pre-filter would rarely skip anything, so the simpler always-resolve-against-all-present-classes approach is used. Netclass count is small (~8), so this is cheap.
- **Netclass resolution uses `TEMPER_NET_ASSIGNMENTS`, not `classify_net_type()`:** confirmed via research that `class_pairs` keys are the fuller 8/9-class names zone emission already uses, while CP-SAT's `classify_net_type()` collapses to 4 coarse buckets — using the coarse classifier here would silently miss every `class_pairs` lookup.
- **Zone priority inverts the existing `dru_priority` field rather than inventing a new ranking:** `dru_priority` is already the authoritative, AGENTS.md-mandated (N4 SSOT) safety ranking on every `TEMPER_NET_CLASSES` entry — reusing it avoids a second, potentially-drifting ranking table.
- **Shape localization uses `shapely` (already a dependency), simple distance-threshold clustering (not a general-purpose clustering library):** the problem is low-cardinality (pad counts per net are small), so a lightweight clustering approach is sufficient and avoids adding dependency surface.
- **U4's verification is standalone, not CI-wired, per this session's confirmed scope:** keeps this plan's footprint limited to the geometry/clearance fix itself; CI integration is easy follow-up once the fix is proven, not a prerequisite for proving it.
- **`design_rules` must be threaded into `_write_routes_to_content` as a new parameter (U1):** verified against source that the zone-emission loop currently has no access to the `DesignRules` instance carrying `.class_pairs` — the only same-named object in scope (`result.pcb.design_rules`) is a different, unrelated class with no `class_pairs` concept, and reaching for it would silently no-op U1's entire clearance resolution. Explicitly called out to prevent this trap during implementation.
- **`GND`/`ACMains`/`HighVoltage`-class nets are exempted from U3's clustering:** these are return/ground-path netclasses where the origin doc's own justification for pours (continuous plane for EMI/loop-area control) directly conflicts with clustering's tendency to fragment spatially-separated pads into disconnected islands. Clustering only applies where fragmentation is electrically acceptable.

---

## Dependencies / Assumptions

- Assumes `pcbnew.ZONE_FILLER` correctly honors `(priority N)` and per-zone `(clearance N)` fields as documented, standard KiCad behavior. The `.kicad_pcb` file-format support for these fields is confirmed via real zone data in `power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb` — but that only confirms the format, not that the fill *algorithm* behaves identically between local pcbnew (10.0.4, where U1/U2's manual verification runs) and CI's kicad-cli (8.0.9, where the original regression was diagnosed). This gap is not fully closed by this plan; U4's `kicad-cli`-based measurement (runnable in CI's actual environment) is the authoritative check, not U1/U2's local verification alone (see U4's Approach).
- Assumes `shapely>=2.1.2` (already in `pyproject.toml`/`uv.lock`) is sufficient for the convex-hull computation needed — no new dependency required.
- Assumes `DesignRules.class_pairs` (dynamically set, not a declared dataclass field) continues to be populated the same way by `io/netclass_loader.py` — this plan reads it defensively (`getattr(..., 'class_pairs', {})`), matching the existing CP-SAT consumer's own defensiveness.
- Assumes the multi-sample methodology (seeds × DRC runs) established during the original diagnosis (4 seeds × 3 samples) remains a reasonable default for U4; exact counts may be tuned during implementation if measurement proves noisier or cleaner than expected.

---

## Outstanding Questions

### Deferred to Implementation
- Exact spatial-clustering distance threshold for U3 — not knowable without testing against the real production board's pad distributions; start with a reasonable default (e.g. related to typical component pitch) and tune based on observed hull sizes.
- Exact `dru_priority` → KiCad `(priority N)` inversion formula (linear inversion vs. an explicit small lookup table) — either is fine; pick whichever is simpler to implement and test against U2's test scenarios.
