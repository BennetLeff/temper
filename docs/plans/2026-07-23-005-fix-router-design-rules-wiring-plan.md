---
title: "fix: Thread real per-net design rules into the Router V6 A* engine"
type: fix
status: R1/R2/R5/R6 shipped and verified; R3/R4/R7 open; R8 (new) open
date: 2026-07-23
origin: investigation triggered by re-measuring docs/plans/2026-07-22-001's R14 promotion gate
---

## Post-implementation update (same day)

R1/R2/R5 are implemented and empirically verified, not just code-reviewed:
a runtime probe during a real `route_pcb()` run against the production board
confirmed `design_rules.net_class_assignments`/`net_classes` went from
permanently empty (`assignments_size=0`, every net) to correctly populated
(`assignments_size=38, classes_size=9`), with `+340V_BUS`/`SW_NODE` resolving
`HighVoltage, clearance_mm=6.0` and `+3V3`/`vcc` resolving `Power,
clearance_mm=0.25` -- exactly as designed. R5's property test (`test_adapter.py
::test_route_pcb_forwards_real_netclass_rules_to_pipeline_engine`) is red
before the fix, green after, confirmed both ways. R6 (tree_routes/
partial_tree_routes rip-up cleanup + the routed-XOR-failed inductive
assertion) also verified via the full existing test suite with zero new
regressions (2 unrelated pre-existing failures confirmed via `git stash`
against unmodified `main`).

**However:** re-measuring the R14 hybrid-pour-stitch shorting_items count
after the fix showed **no material change** (199 → 200, within noise) on the
production board. This is not a failure of R1/R2 -- it means the residual
shorting was never caused by the wiring gap in the first place. Root cause,
confirmed by reading `_astar_reconstruct.py:809-825`: when plain A* (not the
tree executor -- tree-executed nets get `allow_forced_segments=False`,
line 350) cannot find a legal path, it falls back to drawing a **raw direct
line from start to goal, bypassing the grid/clearance/obstacle system
entirely** (`forced_segment_count` bookkeeping tracks this but nothing gates
on it for correctness). The nets that still short after R1/R2
(`vcc`, `+3V3`, `PWR_RTN`) are exactly the congested, high-fanout nets plain
A* can't legally route -- so they hit this fallback, and a fallback that
skips clearance checking entirely doesn't care what the correct clearance
value is. This is added below as **R8**, out of R1/R2's original scope but
discovered by this plan's own verification step -- exactly the kind of thing
TDD-first, measure-don't-assume practice is supposed to surface.

# fix: Thread real per-net design rules into the Router V6 A* engine

## Summary

While re-measuring the `enable_all_pad_tree` R14 promotion gate (`docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md`) with the tree-executor writer crash fixed (see below), the multi-pad tree planner appeared to regress DRC badly: `shorting_items` went from ~81 (flags off) to 199 (flags on), `clearance` violations from 6 to 499. The first hypothesis — that `execute_terminal_tree`'s only call site hardcoded `clearance=design_rules.default_clearance_mm` (0.2mm) instead of resolving per-net rules — was real (confirmed at `_astar_reconstruct.py:277-287`, already patched this session) but produced **zero change** when measured, which is the actual trigger for this plan.

Root cause, confirmed by a runtime probe inside `attempt_route` during a real `route_pcb()` run: the `design_rules` object that reaches the A* engine (both the tree executor and the plain path) is `pcb.design_rules` — built by `RouterV6Pipeline.run()` re-parsing the `.kicad_pcb` file from scratch via `parse_kicad_pcb_v6` — and it has `net_class_assignments={}` for every net, always, including `+340V_BUS`. The rich, correctly-populated `design_rules` object (`HighVoltage=6.0mm`, `Power=0.25mm`, etc., loaded from `configs/netclass_rules.yaml` via `load_netclass_rules`) that callers pass into `route_pcb(design_rules=...)` is used only to (a) compute `layer_constraints` and (b) feed the writer's zone-pour clearance resolution (`_emit_zone_pours`, which reads a *third*, separately-loaded source: `core.design_rules.TEMPER_NET_CLASSES`). It is never threaded into `RouterV6Pipeline.run()`, which accepts a `net_class_assignments` injection parameter (`_pipeline_core.py:183-218`) that `route_pcb()` simply never calls with real data.

Net effect: **every net this router has ever traced via A* — tree-executed or plain, `enable_all_pad_tree` on or off — has used a flat 0.2mm clearance, ignoring all netclass rules**, including the IEC 60335-1-driven 6.0mm HV isolation requirement. This predates and is unrelated to the tree planner; enabling it merely draws real copper for previously-unrouted high-fanout power/HV nets for the first time, which is what made the pre-existing gap visible as DRC damage. Two dead-parameter symptoms of the same "accepted but never forwarded" pattern were also found on `route_pcb()`: `_seed` (no randomness exists anywhere in the routing pipeline for it to seed — confirmed via `grep` for `random`/`np.random`, and empirically: 4 different seed values produced bit-identical routing output across a full 12-sample measurement campaign) and `_net_class_assignments` (never passed to `pipeline.run()`).

---

## Requirements

- **R1** — Thread real per-net design rules (`net_class_assignments` *and* a populated `net_classes` dict of real `NetClassRules`, not just the name-mapping half `_pipeline_core.py` already partially supports) from `route_pcb()`'s `design_rules` parameter into `RouterV6Pipeline.run()` → `pcb.design_rules`, so the A* engine's `get_rules_for_net()` calls resolve real clearance/trace-width/via values instead of always falling through to the board-wide default.
- **R2** — Reconcile (or explicitly, testably adapt between) the three `DesignRules`/`NetClassRules` representations in play: `stage0_data.DesignRules`/`NetClassRules` (router internals, `.clearance_mm`), `core.design_rules.DesignRules`/`netclass_rules_gen.NetClassRules` (YAML loader + zone-pour emission, `.clearance`), and whatever `parse_kicad_pcb_v6` extracts natively from the `.kicad_pcb` file's own netclass sections. At minimum: a documented, unit-tested conversion function. Do not assume they agree without a test — this exact "decoy trap" (a similarly-named but unrelated `design_rules` object) has already bitten this codebase once (`docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md`, R11).
- **R3** — Decide the fate of `_seed`: either (a) implement a real, documented source of routing variance it controls (e.g., A* tie-break jitter, net-order permutation within priority tiers) so multi-seed measurement campaigns (`test_hybrid_pour_stitch_measurement.py`, R14's "route across 4+ seeds — non-negotiable" language) actually sample independent outcomes, or (b) remove the parameter and correct every doc/test claiming multi-sample statistical confidence to state plainly that current measurements are N=1 (repeated only for KiCad DRC report-generation noise, not routing variance) until R3 lands.
- **R4** — Decide the fate of `_net_class_assignments` (same dead-parameter shape as `_seed`): wire it for real, or remove it. R1 likely supersedes its narrow FinePitch-only use case with a general mechanism.
- **R5** — Regression coverage, written first (red) before R1/R2 (green): a property-based test (Hypothesis) that, for a swept range of generated per-netclass clearance/trace-width values assigned to a multi-terminal net, asserts the value actually used during real grid-marking — through `route_pcb()` end-to-end, not just `run_astar_pathfinding` in isolation, since the bug is specifically in the `route_pcb()` → pipeline wiring — matches the netclass-resolved value, not the flat board default. Must cover both the tree-executor path (`enforce_all_pad_tree=True`) and the plain A* path's primary (non-fallback-tier) grid marking.
- **R6** — Carry forward as already-shipped groundwork (this session, prior to this plan): the `tree_routes`/`partial_tree_routes` cleanup-on-ripup fix and the inductive "routed XOR failed, never both" assertion added at the end of `run_astar_pathfinding` in `_astar_reconstruct.py`. Reference, don't re-do.
- **R7** — Re-run the R14 hybrid-pour-stitch promotion measurement (`docs/plans/2026-07-22-001`) after R1/R2 land. This session's measurement (295 vs. 299 `unconnected_items`, 199 vs. ~81 `shorting_items`) was taken entirely under the always-0.2mm-clearance bug and must be treated as provisional — the real promotion verdict can only be trusted once the A* engine is actually netclass-aware. **Update:** re-measured post-fix; `shorting_items` did not improve (199→200) — see R8, discovered by this re-measurement.
- **R8** (new, discovered by R7's re-measurement) — The plain A* path's forced-segment fallback (`_astar_reconstruct.py:809-825`, gated by `allow_forced_segments`, true for every net except tree-executed ones) draws a raw direct line between waypoints when no legal path is found, with zero clearance/obstacle checking. This is the actual cause of persistent `shorting_items` post-R1/R2: congested high-fanout nets (`vcc`, `+3V3`, `PWR_RTN`) hit this fallback, where the netclass-aware clearance fix has no effect since the check is skipped entirely. Decide: (a) fail-closed instead — treat a forced segment as `INCOMPLETE` rather than fabricating out-of-clearance copper, matching the tree executor's already-established `NetDisposition.INCOMPLETE` philosophy and this codebase's general anti-fabricated-copper discipline, or (b) keep forced segments but enforce at least clearance-aware placement for them (harder, and arguably contradicts the "forced" escape-hatch's purpose). Option (a) is probably correct given precedent elsewhere in this codebase, but is a real behavior change (nets currently silently "succeeding" via forced segments would become honestly `unrouted`) and deserves its own requirements/scope pass, not a same-session tack-on.

---

## Scope Boundaries

**In scope:** the wiring fix (R1), enough reconciliation of the three representations to make R1 correct and testable (R2), the two dead-parameter decisions (R3, R4), and TDD-first regression coverage (R5).

**Out of scope:**
- Deciding whether to promote `enable_all_pad_tree`/`enable_zone_pours` to default-on — that decision depends on R7's re-measurement and belongs to `2026-07-22-001`, not this plan.
- Implementing full cross-class *pairwise* clearance (`class_pairs` in `netclass_rules.yaml`, e.g. `HighVoltage-Signal: 6.0mm`) inside the A* engine. Today that logic exists only in zone-pour emission (`_adapter_convert.py:349-361`). R1's fix (correct *own*-netclass clearance reaching the A* engine at all) is the minimum bar to close the safety-relevant "everything is 0.2mm" gap. Cross-class pairwise-max resolution for traces is a real enhancement on top, likely its own follow-up (an "R8").
- A broader systematic sweep for other instances of "a rich config object is silently dropped/replaced by an empty default across a module boundary" elsewhere in the codebase. Worth doing — this pattern (two same-named, differently-populated objects) may not be unique to `design_rules` — but tracked as separate future work, not blocking here.

**Deferred:** Full IEC 60335-1 compliance sign-off on the resulting board — this plan fixes the measurement/enforcement infrastructure; certification is a downstream lab activity, consistent with how this project has scoped DRC/ERC infra work before.

---

## Key Technical Decisions

- **Fail-closed, not silent-default.** If a net has no resolvable netclass assignment after R1 lands, prefer this codebase's established `UNMEASURED`/loud-failure discipline (`docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`) over silently falling back to the flat default — a future net added without an assignment should surface immediately, not get quietly routed at 0.2mm again.
- **TDD ordering is load-bearing here, not stylistic.** The reason this bug survived is that the "fix" (my first attempted patch) *looked* correct by code inspection and only proved to be a no-op when actually measured end-to-end. R5 must exercise the real `route_pcb()` wiring path, not a unit that only tests `get_rules_for_net()` in isolation — that would pass today even though the system is broken, since `get_rules_for_net()` itself is correct; the bug is entirely in what object reaches it.

---

## Dependencies / Assumptions

- Need to determine during U2 (implementation) whether `parse_kicad_pcb_v6` should itself be taught to read richer netclass data directly from the `.kicad_pcb` file (if the recently-landed "cross-language NetClassRules SSOT pipeline" codegen writes real netclass sections into the file), versus `route_pcb()`'s explicit post-parse injection being the intended long-term mechanism. Either is viable; pick one and document why, rather than half-doing both (which is close to today's actual failure mode).
- `configs/netclass_rules.yaml` and `core.design_rules.TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS` are assumed to be the authoritative source for real clearance values (per the SSOT pipeline commit history); R2's conversion function reads from there.

---

## Success Criteria

- ✅ R5's property test fails before R1/R2 land, passes after (TDD, verified both ways).
- ✅ A net assigned to `HighVoltage` is provably enforced at 6.0mm clearance during real A* grid-marking (not only zone-pour emission), across a swept range of generated netclass configs — not one hardcoded example. Verified via runtime probe: `assignments_size` 0→38, `classes_size` 0→9, correct per-class values resolved for real nets on the production board.
- ⬜ `_seed` and `_net_class_assignments` each have a decided, documented, non-dead fate. (R3/R4, not started.)
- ✅ R7's re-measurement of the R14 gate is recorded as a new, trustworthy data point, explicitly superseding this session's provisional numbers. Result: `shorting_items` unchanged (199→200) — R1/R2 were necessary but not sufficient; root cause of persistent shorting is R8, a distinct bug.
- ⬜ R8 (forced-segment clearance bypass) has a decided fate and, if fixed, a final re-measurement showing genuine improvement. Not started — flagged for a follow-up plan or a continuation of this one.

---

## Sources & References

- This session's investigation: `_astar_reconstruct.py` (`attempt_route`, `run_astar_pathfinding`, the ripup-cleanup fix and XOR-invariant assertion already landed), `terminal_tree_execution.py` (`execute_terminal_tree`), `_pipeline_core.py` (`RouterV6Pipeline.run`'s existing but unused-by-`route_pcb` `net_class_assignments` injection), `_adapter_convert.py` (`route_pcb`, `_emit_zone_pours`'s cross-class clearance resolution), `stage0_data.py` (`DesignRules`/`NetClassRules`), `core/design_rules.py` (the parallel SSOT-generated representation), `configs/netclass_rules.yaml`.
- `docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md` — the R14 promotion gate this plan's fix directly affects; its measurement is provisional pending R7.
- `docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md` R11 — prior art for the "decoy trap" (a similarly-named, unrelated `design_rules` object) and for cross-class pairwise clearance, already solved once for zone emission, not yet for traces.
- `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md` — the fail-closed/`UNMEASURED` discipline this plan's netclass-resolution fallback should follow.
- `AGENTS.md` Bug-Triage Rule (R22) — architectural fixes get scoped as a separate follow-up rather than inlined into a bugfix; this plan is the follow-up.
