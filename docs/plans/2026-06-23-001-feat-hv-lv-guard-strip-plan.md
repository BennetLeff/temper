---
date: 2026-06-23
plan_id: 2026-06-23-001-feat-hv-lv-guard-strip
title: HV/LV Pre-Placement Guard Strip Stage
type: feat
origin: docs/brainstorms/2026-06-23-hv-lv-guard-strip-requirements.md
status: active
---

# Implementation Plan: HV/LV Pre-Placement Guard Strip

## Problem Frame

The temper PCB autorouter pipeline achieves only 33% routing completion (8/24 nets) on the induction-cooker design. Ten nets are blocked because the pre-placement stage is unaware of `NetClassRules.safety_category` and allows HV components (Q1, Q2, D1, D2) to be placed within 6 mm of LV components, leaving no routing path that respects the IEC 60335-1 creepage. This plan adds an additive, ~100-line pipeline stage that partitions components into HV (board edge) and LV (board interior) buckets derived from `safety_category`, reserves a guard strip between them whose width is sourced from `creepage_mm` of HV-classified net classes, and emits a `component_domain_map` plus a routing corridor so downstream placement cannot place LV components in the HV region. No edits to the router, DRC, or `core/design_rules.py`.

## Implementation Units

### U1. BoardState Extensions, `PartitionError`, and Config Loader

**Goal.** Add the immutable state fields and exception type the new stage produces, and load the `hv_lv_guard_strip` config block in one place.

**Requirements.** FR4 (domain map output), FR5 (routing corridors field), FR7 (PartitionError), FR9 (config block parsed).

**Files.**

- `packages/temper-placer/src/temper_placer/deterministic/state.py` — extend the frozen `BoardState` dataclass with `component_domain_map: frozenset = frozenset()` (set of `(ref, "HV_edge" | "LV_interior")` tuples), `routing_corridors: tuple[Polygon, ...] = ()`, and `domain_regions: tuple[Polygon, ...] = ()` (default_factory=tuple) holding the HV and LV region polygons. Default values keep NFR6 (backward compat) intact for stages that do not run, including `domain_regions`.
- `packages/temper-placer/src/temper_placer/deterministic/stages/hv_lv_partition.py` (new) — define `PartitionError(Exception)` carrying `bucket: str`, `largest_ref: str`, `region_area_mm2: float`, `required_area_mm2: float`; define `HvLvGuardConfig` (pydantic model with `enabled: bool = True`, `width_mm: float | None = None`, `fallback_to_unconstrained: bool = True`); and a `load_guard_config(config: Mapping) -> HvLvGuardConfig` helper that reads from `configs/temper_deterministic_config.yaml` under the `hv_lv_guard_strip` key and falls back to defaults.

**Approach.** Add fields with `default_factory` so existing test fixtures that build `BoardState(...)` positionally still construct. `Polygon` is the same shapely type already used by `ClearanceGrid` consumers; importing the type as `TYPE_CHECKING` avoids hard import. `PartitionError` is a plain `Exception` subclass with structured fields (no `__str__` override — the runner formats it for logging per NFR4).

**Test scenarios.**

- `BoardState()` (no kwargs) constructs with `component_domain_map == frozenset()` and `routing_corridors == ()`.
- `HvLvGuardConfig(enabled=False, width_mm=None, fallback_to_unconstrained=True)` round-trips through pydantic.
- Missing `hv_lv_guard_strip` block in a config dict → `load_guard_config` returns defaults (enabled=True, width_mm=None).
- `PartitionError("HV", "Q1", 25.0, 80.0)` exposes the four structured fields.

**Verification.** `uv run pytest packages/temper-placer/tests/deterministic/stages/test_hv_lv_partition.py -k "config or state"`.

---

### U2. `HvLvPartitionStage`: Partition, Guard Geometry, Bucket Edge Cases

**Goal.** Implement the `Stage` ABC subclass that reads `safety_category`, partitions components, computes the guard strip, and populates `component_domain_map` + `routing_corridors`.

**Requirements.** FR1 (new stage), FR2 (HV/LV partition incl. dual-domain policy), FR3 (guard strip geometry + width override), FR6 (empty bucket no-op), FR7 (insufficient area handling).

**Files.**

- `packages/temper-placer/src/temper_placer/deterministic/stages/hv_lv_partition.py` — define `class HvLvPartitionStage(Stage)` with `name = "hv_lv_partition"`, `run(state: BoardState) -> BoardState`. Pseudocode of `run`:
  ```
  cfg = load_guard_config(state.config)
  if not cfg.enabled: return state                     # NFR6
  rules_by_net = state.drc_oracle.design_rules.get_rules_for_net  # per-net
  components = list(state.netlist.components)
  hv_buckets, lv_buckets = [], []
  for c in components:
      cats = { rules_by_net[net].safety_category for net in c.nets if net in rules_by_net }
      has_hv = bool(cats & {"HV", "AC"})
      has_lv = bool(cats & {"LV", "iso"})
      if has_hv and not has_lv: hv_buckets.append(c.ref)
      elif has_lv and not has_hv: lv_buckets.append(c.ref)
      elif has_hv and has_lv: lv_buckets.append(c.ref); log.warning("dual-domain %s → LV", c.ref)   # FR2 dual-domain policy: LV with warning
      else: lv_buckets.append(c.ref)                    # FR2 unmapped → LV default
  if not hv_buckets or not lv_buckets: log.info("empty bucket"); return state   # FR6
  hv_nets = {net for c in components if c.ref in hv_buckets for net in c.nets if net in rules_by_net and rules_by_net[net].safety_category in {"HV", "AC"}}
  width = cfg.width_mm or max(rules_by_net[n].creepage_mm for n in hv_nets)
  if cfg.width_mm == 0: return state                    # FR3 explicit disable
  if cfg.width_mm is not None and cfg.width_mm < width: log.warning("width_mm=%s below creepage %s, using creepage", cfg.width_mm, width); width = width  # keep creepage
  hv_poly, lv_poly, corridor = compute_guard_strip(state.board.outline, width)
  if area(hv_poly) < bbox_area(largest(hv_buckets)) or area(lv_poly) < bbox_area(largest(lv_buckets)):
      if cfg.fallback_to_unconstrained: log.warning("insufficient area, legacy placement"); return state
      raise PartitionError(...)                        # FR7
  domain_map = [(r, "HV_edge") for r in hv_buckets] + [(r, "LV_interior") for r in lv_buckets]
  return replace(state, component_domain_map=frozenset(domain_map), routing_corridors=(corridor,), domain_regions=(hv_poly, lv_poly))
  ```
- `packages/temper-placer/src/temper_placer/deterministic/geometry/guard_strip.py` (new) — `compute_guard_strip(outline: Polygon, width_mm: float) -> tuple[Polygon, Polygon, Polygon]` returning `(hv_region, lv_region, corridor)`. Use shapely `buffer(-width_mm)` for the inward offset; `corridor = outline - lv_region`; `hv_region = outline - corridor`.

**Approach.** Reuse `DesignRules.get_rules_for_net()` (SSOT per FR2). Compute `width` as `max(creepage_mm)` filtered to net classes whose `safety_category in {"HV", "AC"}`, not as a hard-coded 6.0. The dual-domain policy (FR2 last bullet) is fixed here as "assign to LV bucket, log WARNING with ref" — explicit and testable. `phased_component_assignment` consumers (U3) treat LV bucket members as in-domain for the LV region. Determinism (NFR1) is guaranteed by iterating `netlist.components` in declared order; no random sampling.

**Test scenarios.**

- Input: 4 components — Q1 on `+HV` (HV), D1 on `AC_L` (AC), U_MCU on `SPI_CLK` (LV), J1 on `+3V3` (LV). Action: run stage with enabled=True, no width override. Expected: `component_domain_map == {("Q1","HV_edge"), ("D1","HV_edge"), ("U_MCU","LV_interior"), ("J1","LV_interior")}`.
- Input: dual-domain netlist (one component connected to `+HV` and `SPI_CLK`). Action: run stage. Expected: component is in `LV_interior` and a WARNING is logged with the ref.
- Input: empty HV bucket (only LV components). Action: run stage. Expected: `state` returned unchanged; INFO log; `component_domain_map == frozenset()`.
- Input: `cfg.width_mm = 10.0`, derived creepage = 6.0. Action: run stage. Expected: corridor width = 10.0, no WARNING.
- Input: `cfg.width_mm = 3.0`, derived creepage = 6.0. Action: run stage. Expected: corridor width = 6.0, WARNING logged naming both values.
- Input: `cfg.width_mm = 0`. Action: run stage. Expected: pass-through, no `routing_corridors` set.
- Input: 100mm × 150mm board, 4 HV components whose total bbox > 80 × 120 mm; LV region shrinks below largest LV bbox. Action: run stage with `fallback_to_unconstrained=True`. Expected: WARNING logged with bucket/largest_ref/areas; pass-through.
- Same input, `fallback_to_unconstrained=False`. Expected: `PartitionError` raised with all four structured fields.
- Two identical runs on the same inputs produce identical `component_domain_map` ordering and `routing_corridors` (NFR1 determinism).
- NFR5 size budget: `hv_lv_partition.py` + `guard_strip.py` total Python lines (excl. tests) ≤ 150.

**Verification.** `uv run pytest packages/temper-placer/tests/deterministic/stages/test_hv_lv_partition.py`; coverage report via `uv run pytest --cov=temper_placer.deterministic.stages.hv_lv_partition` ≥ 95% (SM5).

---

### U3. Pipeline DAG Insertion, Config Wiring, and `phased_component_assignment` Filter

**Goal.** Slot the new stage into the deterministic DAG between `zone_assignment` and `phased_component_assignment`, register it for export, and have `PhasedComponentAssignmentStage` honor `component_domain_map`.

**Requirements.** FR4 (consume domain map in phased assignment), FR5 (register corridor, mark advisory if router does not consume), FR8 (DAG insertion), FR9 (config block), NFR6 (golden-fixture compatibility when `enabled: false`).

**Files.**

- `packages/temper-placer/src/temper_placer/deterministic/stages/__init__.py` — add `from .hv_lv_partition import HvLvPartitionStage, PartitionError` and append both to `__all__`.
- `packages/temper-placer/src/temper_placer/deterministic/__init__.py` — insert `HvLvPartitionStage()` into both stage lists (the one used by `PipelineOrchestrator.run` around line 216 and the public re-export list around line 278), positioned between `ZoneAssignmentStage()` and `PhasedComponentAssignmentStage()`.
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` — in the slot-filtering loop, drop any `zone_slot` whose point lies outside the assigned component's domain region (HV-edge slots for LV refs and vice versa). If `component_domain_map` is empty (stage skipped or disabled), skip the filter so NFR6 still holds. Source region membership from `state.component_domain_map` paired with `state.domain_regions` to look up the right polygon for each ref.
- `configs/temper_deterministic_config.yaml` — append a top-level `hv_lv_guard_strip:` block with `enabled: true`, `width_mm: null`, `fallback_to_unconstrained: true` plus an inline comment pointing to `core/design_rules.py:121` as the SSOT for `creepage_mm`.
- `docs/brainstorms/2026-06-23-hv-lv-guard-strip-requirements.md` (deferred) — no edits; corridor advisory note lives in the plan.

**Approach.** Insertion order follows the existing two-list pattern in `__init__.py`. The `phased_component_assignment` change is a single point-in-polygon filter inside the existing slot iteration; no new helpers, no signature changes. Router-side corridor consumption is intentionally out of scope — record the gap as a "router support for routing_corridors" deferred item (see Scope Boundaries) so a follow-up can wire the router without re-touching this stage.

**Test scenarios.**

- Full pipeline run with `enabled=True` and a fabricated netlist whose HV components would normally intrude on the LV region: the resulting `placements` show no LV ref inside the HV region and no HV ref inside the LV region (point-in-polygon check).
- Full pipeline run with `enabled=False` (or config block absent → default `enabled=True` overridden by env or feature flag) on the golden fixture referenced in `docs/brainstorms/2026-06-22-golden-fixture-ladder-requirements.md`: output bytes are identical to the pre-change snapshot (NFR6 / SM6).
- `phased_component_assignment` with `component_domain_map = frozenset()` (no prior partition stage) produces the same placements as the unfiltered baseline (backward compat).
- `__init__.py` re-exports include `HvLvPartitionStage` and `PartitionError`; import succeeds via `from temper_placer.deterministic import HvLvPartitionStage`.
- Config block parses via `load_guard_config` (U1's helper) with the live YAML; missing key returns defaults.

**Verification.** `uv run pytest packages/temper-placer/tests/deterministic/test_orchestrator.py` (existing 56 tests must pass) + `uv run pytest packages/temper-placer/tests/deterministic/test_full_pipeline_drc.py` (golden-fixture regression). Manual diff: `git stash; uv run … --output snapshot_pre.kicad_prl; git stash pop; uv run … --output snapshot_post.kicad_prl; diff snapshot_pre.kicad_prl snapshot_post.kicad_prl` with `enabled: false` in config to confirm byte-identical output (SM6).

---

### U4. Unit, Integration, and Golden-Fixture Tests

**Goal.** Hit SM5 (≥95% line/branch coverage) on `hv_lv_partition.py` + `guard_strip.py`, lock in SM1 (≥90% routing completion) via an integration assertion, and pin NFR6 via the golden-fixture ladder.

**Requirements.** NFR3 (stage unit-testable in isolation), NFR5 (size budget), NFR6 (backward compat), SM1, SM2, SM5, SM6.

**Files.**

- `packages/temper-placer/tests/deterministic/stages/test_hv_lv_partition.py` (new) — unit tests covering every scenario listed in U2. Use a `make_state(netlist, design_rules, config)` fixture that builds a `BoardState` with a 100 × 150 mm rectangle, a synthetic `DesignRules` containing `HighVoltage` and `ACMains` net classes (creepage_mm=6.0, safety_category="HV"/"AC"), and a 6-component netlist covering HV, AC, LV, iso, dual-domain, and unmapped refs.
- `packages/temper-placer/tests/deterministic/test_hv_lv_partition_integration.py` (new) — runs the full deterministic pipeline on a small fixture board and asserts: (a) zero HV↔LV component footprint overlap by ≥6 mm (SM2), (b) the 10 historically-stuck HV nets (those tied to Q1, Q2, D1, D2) are all routed (SM3). Marked `@pytest.mark.slow` so it can be excluded from pre-commit.
- `packages/temper-placer/tests/deterministic/stages/test_guard_strip_geometry.py` (new) — pure shapely tests for `compute_guard_strip`: 100 × 150 mm input with width=6.0 → corridor area = perimeter × 6.0 minus corner cuts (analytical formula `2*(W+H)*w - 4*w^2`), guard polygon is a closed ring with no self-intersections; width=0 returns `outline`; width larger than half-min-side returns an empty LV region; outline = `LineString([(0,0),(100,0),(100,150)])` (open polyline) → raises `PartitionError` whose `bucket` field starts with `"geometry"`.
- `packages/temper-placer/tests/deterministic/test_hv_lv_golden_fixture.py` (new) — runs the pipeline with `enabled: false` and compares `placements`, `routes`, and `drc_violations` byte-for-byte against the snapshot in `tests/deterministic/snapshots/golden_pre_hv_lv/` (SM6). Snapshot generation is one-shot via an env-flagged `--update-snapshots` path; the default test path is strict equality.
- `packages/temper-placer/tests/deterministic/conftest.py` (extend) — add `fixture_minimal_pcb` (10-component mixed HV/LV), `fixture_design_rules_temper` (loads `core/design_rules.py:337-444` net classes), and `fixture_hv_lv_config_yaml` (string containing the YAML block from U3).

**Approach.** Unit tests mock `state.drc_oracle` rather than standing up a full DRC. Integration test reuses the temper `kicad_prl` fixture already present in `tests/deterministic/`. The golden-fixture test reuses the snapshot infrastructure from the golden-fixture ladder brainstorm (`docs/brainstorms/2026-06-22-golden-fixture-ladder-requirements.md`) — no new snapshot system.

**Test scenarios.**

- All U2 scenarios.
- `compute_guard_strip(rectangle(0,0,100,150), 6.0)` area == `2*(100+150)*6.0 - 4*6.0**2` (asserted to within 0.01 mm² floating-point tolerance).
- `compute_guard_strip(rectangle(0,0,10,10), 6.0).is_empty` is True.
- `__init__.py` import smoke test (`import temper_placer.deterministic.stages` does not raise).
- `phased_component_assignment` placement filter test (mirrors U3 last scenario).
- Coverage gate: `uv run pytest --cov=temper_placer.deterministic.stages.hv_lv_partition --cov=temper_placer.deterministic.geometry.guard_strip --cov-fail-under=95`.
- NFR2 performance: a `@pytest.mark.benchmark` test asserting the stage adds <5% to total pipeline wall-clock on the temper fixture (NFR2 / SM4).

**Verification.** `uv run pytest packages/temper-placer/tests/deterministic/ -q`; coverage report ≥ 95% on new modules; manual golden-fixture diff with `enabled: false` returns zero differences.

## Risks & Dependencies

| Risk / Dependency | Mitigation |
|---|---|
| `BoardState` is a frozen dataclass; downstream test fixtures construct it positionally in some places. | New fields use `default_factory=frozenset` / `default_factory=tuple`; positional callers remain valid. |
| `phased_component_assignment` slot filter may drop valid slots and force a re-assignment pass. | Run the existing convergence loop unchanged; if iteration count exceeds its cap, surface as a regression in integration test. |
| `DesignRules.get_rules_for_net()` lookup is O(N) per net in the current implementation; FR2 walk is O(N·M). | Acceptable per NFR2 (partition is O(N+M) amortized via a single build of `rules_by_net`); document in the stage docstring. |
| Router does not consume `routing_corridors` (FR5 last sentence). | Mark advisory; defer router-side wiring to a follow-up. Golden-fixture comparison (SM6) ignores corridor contents. |
| `import-linter` boundary check (`.importlinter`) may flag new cross-module imports. | Run `uv run python scripts/import_linter_gate.py`; if violated, add an `import-linter-allowlist.yaml` entry per `docs/plans/2026-06-22-014-feat-import-linter-boundary-enforcement-plan.md`. |
| `safety_category` not populated for some net classes in legacy fixtures. | FR2 last bullet + NFR6: unmapped components default to LV; log INFO with ref. |
| Dual-domain policy (FR2 last bullet) is fixed here as "assign to LV with WARNING" but the brainstorm calls it an implementation choice. | Document the choice in the stage module docstring; if a future brainstorm reverses it, the partition is a single boolean flip. |
| Board outline is assumed to be a closed polygon. | `compute_guard_strip` validates `outline.is_closed` and raises `PartitionError` with diagnostic context if not (NFR4). |
| Net-class-rule width override below creepage (`width_mm < max(creepage)`) silently widens to creepage (FR3). | Log WARNING with both values; do not raise. |

## Scope Boundaries

### Deferred to Follow-Up Work

- **Router consumption of `routing_corridors`.** FR5 marks the corridor as advisory until a router-side change reads it. A future plan adds a `corridors` parameter to the router's `RoutingSpace` construction.
- **Per-pin creepage enforcement at placement time.** Brainstorm Out-of-Scope; remains a post-placement DRC concern.
- **Layer-aware HV partitioning** (HV on F.Cu only) — brainstorm Out-of-Scope.
- **Non-rectangular / L-shaped / U-shaped guard geometries** — brainstorm Out-of-Scope; single convex offset only.
- **Voltage-aware dynamic guard-strip width** — brainstorm Out-of-Scope; width derives from `creepage_mm` only.
- **Auto-tuning guard-strip width per region / per component** — brainstorm Out-of-Scope.
- **Second guard strip between "AC" and "HV" sub-domains** — brainstorm Out-of-Scope; both fall in the same HV bucket.
- **Re-routing the existing 4-zone layout** (HV / Power / Signal / MCU) — brainstorm Out-of-Scope; the new partition is a strict refinement.
- **Migration of `zone_assignments` config** in `configs/temper_deterministic_config.yaml` — brainstorm Out-of-Scope; existing entries remain valid; the new stage layers above them.

### Out of Scope

- Any modification to `core/design_rules.py` (SSOT for `creepage_mm`, `safety_category`).
- Any modification to the existing DRC check set.
- Any modification to routing strategies.
- Changes to `NetClassRules.safety_category` semantics, values, or population.
- Multi-domain partitions beyond single HV vs LV cut.
- Pin-level creepage placement enforcement.
- Changes to `zone_geometry.py` or `zone_assignment.py` outputs (the new stage consumes them, not modifies them).
