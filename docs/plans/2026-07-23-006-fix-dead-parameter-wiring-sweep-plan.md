---
title: "fix: Wire or retire dead/silently-discarded parameters in router_v6"
type: fix
status: completed
date: 2026-07-23
origin: docs/brainstorms/2026-07-23-dead-parameter-wiring-sweep-requirements.md
adversarial_review: true
review_findings:
  - "V6RouterAdapter is NOT dormant — has live callers in scripts/internal_route.py (make route target) and benchmarks/routing_benchmark.py (3 sites via MazeRouter alias)"
  - "Original grep scope (src/ + tests/) excluded exactly the directories where production callers live"
  - "Deletion option (R1 option a) would break 4 shell scripts + benchmark suite — not a clean no-op"
  - "The same narrow grep scope may have produced false negatives for other parameters assessed in this sweep"
swept: 2026-07-25
swept_basis: "referenced in git history; 3/4 paths exist"
---

## Summary

The `route_pcb()` `design_rules` wiring bug (fixed in `2026-07-23-005`) had a recognizable shape: a parameter is accepted and stored, but never forwarded to the code that would change behavior. A time-boxed sweep of `router_v6` found the same pattern at multiple sites — most critically, `V6RouterAdapter`/`MazeRouter` carries the identical `design_rules`-never-reaches-the-A*-engine gap, plus 18 additional silently-discarded parameters, and no zone-pour or connectivity-verifier support.

**Corrected finding (post-review):** The original sweep concluded `V6RouterAdapter` was "dormant" / "never instantiated anywhere" based on a grep that only searched `src/` and `tests/`. This was wrong. Real callers exist in:
- `scripts/internal_route.py:499` — the project's documented baseline production router (`make route`)
- `packages/temper-placer/benchmarks/routing_benchmark.py:171,331,344` — three call sites via the `MazeRouter` alias

Both callers are not CI-automated, but `scripts/internal_route.py` is classified as `disposition: shell-invoked` / `category: keep` in `scripts/manifest.yaml` (31 days stale as of 2026-07-23 — right at the project's 30-day sunset-warning threshold). This is not a dormant landmine; it is a reachable, exploitable gap on the baseline routing path.

---

## Requirements

### R1 — Fix V6RouterAdapter's design_rules gap or sunset it deliberately
**Priority: P0**

`rrr_route_all_nets()` in `_adapter_core.py` constructs a `RouterV6Pipeline` with no `layer_constraints`, no `enable_all_pad_tree`/`enable_zone_pours`, no `connectivity_verifier`, and zero `net_class_assignments`/`net_classes` kwargs — the exact call shape `route_pcb()` had before the 2026-07-23-005 fix. `self._design_rules` is stored but never referenced. Two options, with different blast radii:

**(a) Fix its wiring** to match `route_pcb()`'s corrected pattern. Wire `self._design_rules` → `net_class_assignments`/`net_classes` → `pipeline.run(...)`, and add `layer_constraints`, `enable_zone_pours`, `connectivity_verifier` support.

**(b) Sunset it deliberately.** Update `scripts/manifest.yaml` to `category: delete`, remove the `Makefile` `route` target, and add a deprecation comment to `V6RouterAdapter`/`MazeRouter`. This is not a no-op removal — it breaks the Makefile target and the benchmark suite. If chosen, first check with the script owner (`owner: unassigned` currently) whether the `make route` workflow is still wanted.

**Constraints:** Option (a) is the right choice if the `make route` workflow is still in use. Option (b) is cleanup if it's genuinely abandoned (31 days stale). Either outcome is better than leaving a known-broken, occasionally-reachable code path in place.

### R2 — Confirm `_astar_route_with_ripup`'s `_routed_paths`/`_pad_centers` are genuinely dead, not silently-broken
**Priority: P2**

Both positional parameters are unreferenced anywhere in the function body (verified: `_astar_reconstruct.py:1073-1169`). Static reading says vestigial from a refactor — rip-up detection now goes through grid `net_id` lookup via `id_to_net`, not a passed-in `routed_paths` dict; pad-avoidance is handled by the caller's `_unblock_net_pads` before this function is invoked. But this session's design_rules "fix" also looked correct by inspection and was a runtime no-op. **Verify before deleting:** a cheap runtime probe confirming rip-up decisions are equally correct with vs. without a populated `_routed_paths` argument. If confirmed dead, delete both unused positional parameters and update call sites.

> **Scope note:** The original sweep used a `src/` + `tests/`-only grep. If callers to this function exist in `scripts/` or `benchmarks/`, the same blind spot applies. Verify consumer scope across `scripts/`, `benchmarks/`, and shell automation before deletion.

### R3 — Remove or wire `RouterV6Pipeline.enable_connectivity_verifier`
**Priority: P3**

`_pipeline_core.py:160` sets `self.enable_connectivity_verifier` — this attribute is **never read anywhere else in `_pipeline_core.py` or `_pipeline_route.py`**. The actual feature still works because `route_pcb()` threads `enable_connectivity_verifier` to `_build_routing_result(...)` as a separate, independently-passed parameter (`_adapter_convert.py:231/253`), bypassing the pipeline object entirely. The pipeline's own copy is redundant, unread plumbing.

**Action:** Delete the stored-but-unread attribute. The real flag already flows correctly via the separate parameter; keeping a second, inert copy of the same flag in the pipeline object is misleading to future readers who might assume `self.enable_connectivity_verifier` gates something inside the pipeline stages. It doesn't.

### R4 — Decide the fate of `rrr_route_all_nets`'s twelve unused RRR-tuning parameters
**Priority: P3 (moot if V6RouterAdapter is deleted per R1 option b)**

`rrr_route_all_nets(...)` accepts thirteen parameters named for rip-up-reroute convergence tuning (`_assignments`, `_max_iterations`, `_history_increment`, `_history_decay`, `_p_scale_start`, `_p_scale_step`, `_progress_callback`, `_incremental`, `_validate_final`, `_pin_positions_overrides`, `_component_margin`, `_soft_c_spaces`, plus `_cost_maps` which *is* used for a thermal-field seam). The method calls `RouterV6Pipeline.run()` exactly once with none of them. If V6RouterAdapter survives R1, either wire them or remove them. If deleted per R1 option b, R4 is moot.

### R5 — Extend variant-2 tracing beyond the seams checked today
**Priority: P4 (tracked follow-up, not blocking)**

This sweep only checked `enable_connectivity_verifier` and the two `.run()` call sites adjacent to the design_rules fix. A full pass would mean: for every object threaded through more than one pipeline layer (`layer_constraints`, `thermal_flat`/`thermal_weight`, `enable_all_pad_tree`, `enable_zone_pours`), confirm each one is actually read at *every* layer it's supposed to affect, not just the first. Variant 2 requires per-parameter judgment, not a mechanical grep. **Scope as a separate follow-up** — do not assume this sweep was exhaustive. With the grep-scope blind spot corrected (R1 post-review), re-run any variant-2 searches across `scripts/`, `benchmarks/`, and shell automation, not just `src/` and `tests/`.

---

## Scope Boundaries

**In scope:** R1 (fix or sunset V6RouterAdapter), R2 (verify-and-delete dead params in `_astar_route_with_ripup`), R3 (remove unread pipeline attribute), R4 (decide RRR-param fate, gated on R1 outcome), R5 (tracked follow-up).

**Out of scope:** A fully exhaustive variant-2 trace of every multi-layer-threaded parameter in `router_v6` (flagged as R5, not attempted here). **Out of scope:** anything outside `router_v6`/its direct adapters. **Out of scope:** any changes to `_astar_reconstruct.py`'s forced-segment fallback (that's `2026-07-23-007`'s territory).

---

## Key Technical Decisions

- **Grep scope correction.** This plan's own investigative methodology failed because it searched only `src/` and `tests/`. All verification steps below must include `scripts/`, `benchmarks/`, and shell automation in their scope. The `MazeRouter` alias also means grepping for `V6RouterAdapter` alone is insufficient — search for `MazeRouter` as well.
- **R1 fix approach.** If V6RouterAdapter survives, follow `route_pcb()`'s corrected pattern exactly: `_to_stage0_netclass_rules()` for conversion, `pipeline.run(net_class_assignments=..., net_classes=...)` for injection. Do not invent a third mechanism.
- **R2 verification discipline.** The design_rules "fix" looked correct by inspection and was a no-op. R2's dead-parameter confirmation must include a runtime probe, not static reading alone, before deletion.

---

## Dependencies / Assumptions

- **R1 is gated on the `scripts/internal_route.py` ownership decision.** If the `make route` workflow is still in active use, fix (option a). If abandoned, sunset (option b). Without this decision, R1 is blocked.
- **R4 is gated on R1.** If V6RouterAdapter is deleted, R4 is moot.
- **R2 assumes** `_routed_paths`/`_pad_centers` are not consumed by callers in `scripts/` or `benchmarks/` that the original sweep missed. Verify across the full repo before deletion.
- `configs/netclass_rules.yaml` and `core.design_rules.TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS` remain the authoritative netclass data source; R1's fix reads from the same source `route_pcb()`'s fix uses.

---

## Success Criteria

- [ ] R1: `V6RouterAdapter.rrr_route_all_nets()` either (a) passes real netclass rules to `pipeline.run()` matching `route_pcb()`'s corrected call shape, verified with a runtime probe showing `assignments_size > 0`, OR (b) is formally sunset (manifest updated, Makefile target removed, deprecation comment added).
- [ ] R2: Runtime probe confirms `_routed_paths`/`_pad_centers` are genuinely unused; both parameters deleted and all call sites updated with zero test regressions.
- [ ] R3: `RouterV6Pipeline.enable_connectivity_verifier` attribute removed; connectivity-verifier feature confirmed still working via the separate parameter path.
- [ ] R4: Twelve unused RRR-tuning parameters either wired or removed (or moot if V6RouterAdapter deleted).
- [ ] R5: Follow-up issue filed tracking the broader variant-2 sweep, with corrected grep scope.

---

## Sources & References

- `docs/brainstorms/2026-07-23-dead-parameter-wiring-sweep-requirements.md` — source requirements doc
- `docs/plans/2026-07-23-005-fix-router-design-rules-wiring-plan.md` — the upstream fix this sweep follows from
- `_adapter_core.py` — V6RouterAdapter/MazeRouter, the primary target
- `_astar_reconstruct.py` — `_astar_route_with_ripup` (R2), forced-segment fallback (not in scope)
- `_pipeline_core.py` — `RouterV6Pipeline.enable_connectivity_verifier` (R3)
- `scripts/internal_route.py` — baseline production router, R1's primary caller
- `packages/temper-placer/benchmarks/routing_benchmark.py` — R1's secondary caller (MazeRouter alias)
- `scripts/manifest.yaml` — `internal_route.py` classification (shell-invoked, keep, 31d stale)
