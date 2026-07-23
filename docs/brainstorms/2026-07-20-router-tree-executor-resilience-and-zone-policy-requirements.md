# Router Tree-Executor Resilience and Zone-Pour Connectivity Policy — Requirements

**Date:** 2026-07-20
**Status:** Requirements — ready for planning
**Backfilled:** 2026-07-22 — this requirements doc was never committed at the time its two follow-on plans (`docs/plans/2026-07-20-002` and `docs/plans/2026-07-22-001`) were authored; both plans' frontmatter cites this path as their `origin:`. It is reconstructed here from those plans' requirements tables, the shipped tree-executor resilience PRs (#259, #261, commit `5b15aaca`), and the measurement evidence at `docs/evidence/2026-07-20-tree-executor-resilience-U5-measurement.json`, so the dangling `origin:` links resolve. The requirements R1–R7 (resilience arc, fulfilled by PRs #259/#261) and R8–R14 (zone/pour hybrid-completion arc, fulfilled by PR #270 / `2026-07-22-001`) are recorded together here as they were conceived — one brainstorm with two phases.

## Problem

The `router_v6` tree executor abandoned an entire net on the first infeasible edge: `execute_terminal_tree` recorded a single `failed_edge` and stopped, even when later edges in the same tree were independently routable. On the production temper board this produced a **54-net gap** post-U7 via-aware routing — `kicad-cli pcb drc` reported 54 nets failing with "no legal tree edge," on top of 149 `unconnected_items` on the pre-existing path. All 54 failing nets are power/ground/HV plane-style nets with many pads (`PWR_RTN` 88p, `+3V3` 40p, `vcc` 13p, `+15V` 11p, `+340V_BUS` 11p, `DC_BUS_RTN` 11p, plus smaller near-net interconnects >3 pads).

Two architectural gaps compound:

1. **Solitary-edge fragility** — the tree executor treats one bad edge as net-dead; resilience means tracking which terminals are actually connected to the root and skipping only edges whose source was never reached (descended from an earlier failure), retrying the rest.
2. **No zone/pour primitive** — for high-fanout plane-style nets (`PWR_RTN`'s 88 pads), routed trace trees are the wrong topology. Filled-copper zones (pours) are the correct RF/thermal/current-capacity solution. The router has no such primitive; the production pipeline has never called the geometric `verify_net_connectivity` (it is well-tested standalone but never wired into `route_pcb()` — `pipeline.py`'s `compile_routing_results` omits `connectivity=`, so disposition falls back to raw path-count bookkeeping).

## Verified current state (at the time)

### Resilience side (R1–R7)

- `execute_terminal_tree` records a single `failed_edge`; one infeasible edge abandons the whole net's remaining edges even if they are routable in isolation.
- `verify_net_connectivity` (`connectivity.py`, `kicad_connectivity.py`) — a real, tested, geometric union-find over pad/track/via touch predicates — was claimed by `execute_terminal_tree`'s own docstrings to be "the sole authority" for disposition, but is not actually called in production (`pipeline.py`'s `compile_routing_results` call omits `connectivity=`).
- `adapter._write_routes_to_content` does emit real `(via ...)` s-expressions, but `kicad_connectivity.py`'s post-write parser hardcodes `via_list: list[CopperVia] = []` with a stale comment ("the writer does not emit (via ...) entries yet") that is no longer true — the `_VIA_RE` regex exists but is unused. Production-wiring without via parsing would make any via-crossing net appear disconnected, so this is unblocking work for U4 of the follow-on.

### Zone/pour side (R8–R12)

- `zone_emission.py`'s bounding-box shape code, the `enable_zone_pours` flag plumbing, `_zone_layers_for_net`, `_zone_params_for_net`, and the pad-position-gathering loop in `_write_routes_to_content` already exist on `main` (PRs #260–263) but are **flag-gated off by default**.
- PR #267 prototyped a cross-class clearance + native KiCad `(priority N)` mechanism **and** a clustering approach; it closed without merging. The clearance/priority mechanism is reusable; the clustering approach is the part being replaced (its single fixed 2.5 mm threshold fragmented `+3V3`'s 40 pads into 38 disconnected islands — real inter-pad spacing on this board ranges from ~0.6 mm within-component to 70–111 mm median across scattered components).
- The honest baseline with zones off the production path: **260 `unconnected_items`** (PR #268 fixed `parsed.nets` plumbing so this count is honest — earlier 149 count included fabrications).
- `shapely>=2.1.2` and `scipy>=1.10.0` are already dependencies, unused in `router_v6` today.

## Requirements

### Phase A — Tree-executor resilience (R1–R7)

- **R1** — `execute_terminal_tree` tracks which terminals are actually connected to the root via completed edges.
- **R2** — Edges whose source was never reached (descended from an earlier failure) are skipped; remaining edges are retried independently.
- **R3** — `TerminalTreeExecution.failed_edge` (single) becomes `failed_edges` (tuple) for multi-edge failure reporting.
- **R4** — `verify_net_connectivity` remains the sole authority for `ROUTED` vs `INCOMPLETE` disposition.
- **R5** — Truthful-completion contract: a net is `ROUTED` only when every pad is verifiably in one connected copper component, not inferred from path-count bookkeeping.
- **R6** — Resilience is a strict improvement (must not regress routing of nets that were routing successfully); measurable via the existing test suite plus the production board's `unconnected_items` count.
- **R7** — Measurement of resilience impact (U5): a multi-sample re-run of the production board routes with resilience on/off, recording `unconnected_items` distributions, as evidence for whether to promote resilience to default-on.

### Phase B — Zone/pour connectivity (R8–R14)

- **R8** — Identify the six high-fanout plane-style target nets from the honest 260-baseline measurement (`PWR_RTN`, `+3V3`, `vcc`, `+15V`, `+340V_BUS`, `DC_BUS_RTN`, plus smaller counts on others), replacing the inferred 149 baseline that included fabrications.
- **R9** — Promotion discipline: `enable_all_pad_tree`/`enable_zone_pours` stay behind their existing default-off flags. Promotion to default-on is a separate decision gated on real, multi-sample DRC measurement (R14) showing production `unconnected_items` below the honest 260 baseline with corpus at 0 — never on the resilience/zone work's own success criteria alone.
- **R10** — Data-informed dense-cluster identification for pour-eligible nets: derive the cluster cut threshold from each net's own nearest-neighbor distance distribution (e.g., `scipy.cluster.hierarchy` linkage with a data-driven cut, or a k-NN distance elbow), **not** a single global constant. PR #267's specific single-2.5-mm-threshold failure mode must not be repeated. `PWR_RTN` (carries roughly half the ~336 total unconnected-item entries across the six target nets) needs its continuity exemption resolved explicitly, not left "likely."
- **R11** — Cross-class pairwise clearance + native KiCad zone priority: re-create (as fresh work, not a cherry-pick) the clearance/priority mechanism PR #267 prototyped — `effective_clearance = max(own_clearance, class_pairs[sorted_pair].clearance, max(own, other))` resolved via `TEMPER_NET_ASSIGNMENTS`-derived netclass names, matching `_zone_layers_for_net`'s existing lookup (not the coarser `classify_net_type()`). Explicitly avoid the "decoy trap": `result.pcb.design_rules` is a different, unrelated `stage0_data.DesignRules` class with no `class_pairs` concept — the real `design_rules` must be threaded as an explicit parameter into `_write_routes_to_content`, not assumed reachable via `result.pcb`. Invert each net's `dru_priority` into KiCad's higher-wins zone priority scheme.
- **R12** — Trace-stitching for pads outside all dense-cluster pours: for any pad not covered by a pour, route a discrete trace via the existing tree executor connecting it to the nearest pour, using a synthetic `TreeTerminal` representing the pour's nearest boundary point or an already-covered pad within it, reusing `_astar_route`'s point-to-point machinery unmodified (no new A* goal-shape type). Deterministic (same seed, same result); a pad with no legal path to any pour must honestly reflect `INCOMPLETE`, per R5.
- **R13** — Verifiably one connected copper structure: wire `verify_net_connectivity` into the production pipeline (`pipeline.py`'s `compile_routing_results`), and extend it with a `CopperZone`/`CopperPour` primitive and geometric touch predicates (`_zone_touches_pad`, `_zone_touches_track`, `_zones_touch`) analogous to existing `_pads_touch`/`_track_touches_pad`/`_via_touches_pad` — so a net completed via pour+stitch is verifiably confirmed `ROUTED` by the same real geometric authority ordinary trace-based nets use, not a separate weaker bookkeeping check. Via-parsing must be implemented first (`_VIA_RE` is defined but unused) — without it any via-crossing net will appear disconnected the moment this wires in.
- **R14** — Multi-sample re-measurement before promotion: route the production board across 4+ seeds with `enable_all_pad_tree=True, enable_zone_pours=True`, fill via real `pcbnew.ZONE_FILLER`, run `kicad-cli pcb drc` 3+ times per board, and compare `unconnected_items`/`shorting_items` distributions against a zones-off baseline measured the same way. Single-sample comparisons have twice in this codebase's history been indistinguishable from noise — this is non-negotiable. Outcome: production `unconnected_items` for the six target nets is measurably reduced versus baseline, and `shorting_items` does not regress (the specific failure mode of all three prior pour attempts).

## Scope boundaries

- **Promotion is separate from the work**: R9 keeps flags default-off until R14's measured evidence supports flipping them — this brainstorm's success criterion is measurable improvement, not default-on.
- **CI integration of the measurement is follow-up**: U6-style measurement tests are standalone/manual for this brainstorm, not CI-blocking jobs, until proven.
- **A general-purpose "route to a region" A* capability is out of scope**: R12 solves pour-stitching narrowly (synthetic terminal targeting a pour), not as a reusable primitive for other use cases.
- **Multi-layer zone pours and thermal reliefs are deferred**: pours are on the netclass-assigned layer only.
- **Full copper pour polygon intersection with pad shapes is deferred**: start with bounding-box / convex-hull emission; KiCad DRC validates connectivity. Subsequent iteration toward shapely intersection is follow-up.

## Non-negotiable guards (the project's hard-won discipline)

1. **Anti-false-zero (R7 from the 2026-07-10 brainstorm, restated)**: completion and zero counts only when measured within the unchanged constraint set against a properly-configured gate. A relax, a padding, a misconfigured gate, an unmeasured-aborted run, or a single-sample comparison is a **failure mode**, not a pass.
2. **Never weaken an existing guarantee**: R11's cross-class clearance resolves to the **stricter** applicable rule, never the weaker. Two same-class pours keep their own class's clearance unchanged.
3. **Fail-closed measurement**: a `kicad-cli` abort (this codebase has history of macOS KiCad crashes) is UNMEASURED, never clean.
4. **Truthful completion (R5)**: a net is `ROUTED` only when verified by the real geometric union-find — never inferred from path-count bookkeeping.

## Success metrics

- **Resilience**: tree executor no longer abandons nets on solitary-edge failure; `unconnected_items` on the production board does not regress versus the resilience-off baseline.
- **Zone/pour hybrid completion**: `unconnected_items` for the six target nets measurably reduced across the multi-sample distribution (R14), `shorting_items` does not regress.
- **Real geometric verification in production**: `RoutingResults.success_count`/`failure_count` reflects the real `verify_net_connectivity`'s disposition, not raw path-count bookkeeping.
- **Promotion evidence exists**: a dated solutions-doc addendum recording the R14 measurement, as the evidence base for the R9 promotion decision (separate from the work itself).

## Sources & References

- Plans:
  - [`docs/plans/2026-07-20-002-feat-zone-pour-connectivity-plan.md`](../plans/2026-07-20-002-feat-zone-pour-connectivity-plan.md) (R1–R5, the original zone-emission scope — superseded in detail by the hybrid plan below)
  - [`docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md`](../plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md) (R10–R14, the hybrid completion scope)
- Resilience work shipped: PRs #259 (`fix/tree-executor-resilience`) and #261 (`fix/tree-executor-resilience`), commit `5b15aaca` (`feat(router): U2 — subtree-aware resilient tree executor (R4, R5, R6)`).
- Hybrid completion shipped: PR #270 (`feat/hybrid-pour-trace-stitch`), commit `6df48115`.
- Measurement evidence: `docs/evidence/2026-07-20-tree-executor-resilience-U5-measurement.json`
- Key prior art:
  - `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md` (PR #269, recovered diagnosis)
  - `docs/solutions/logic-errors/missing-cross-class-zone-clearance-regression-2026-07-21.md` (PR #269, the clearance mechanism and its "decoy trap" warning)
  - `docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md` (the honest 260 baseline)
  - `docs/solutions/conventions/verify-netclass-clearance-on-the-routing-path-2026-07-12.md` (the standing caution about reading the right value at the right path)