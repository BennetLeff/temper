<!-- provenance: commit=e3a73885a491b19bea51d83bff1c4eb949e05c0a dirty=false -->
<!-- provenance: this document's fix is on branch
agent/router-primary-grid-and-partial-decline, built from
agent/router-pad-attachment-diagnosis-clean (PR #1196) at commit c331903f6
(fix(router): land N-layer routes on their pad's real copper layer, plus
its own evidence doc). PR #1178 -- the 6-layer stackup decision this WHOLE
lineage descends from -- has NOT merged to main as of this writing;
board_layer_roles.py, ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED, and the
N-layer occupancy-grid set (F.Cu/In3.Cu/In4.Cu/B.Cu) do not exist on main.
Every connectivity figure in this document comes from the FIXED
pad_connectivity_audit.py (union-find stale-root, cluster-key rounding tie,
zone-dependent-unmeasured classification), cherry-picked verbatim from
fix/pad-connectivity-audit-metric @ 575f1ba8f as commit 570007030 on this
branch -- never the pre-fix audit, except where a figure is explicitly
labeled "old audit" for reconciliation with route_board.py's own printed
output. pcb/temper.kicad_pcb sha256 =
1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d --
unchanged throughout every measurement in this document. No DRU/clearance/
creepage threshold changed. No ceiling in power_pcb_dataset/drc_ceiling.json
touched. -->

# Router primary_grid selection and per-endpoint decline reporting: closing the two follow-ups from PR #1196

**Verdict up front.**

1. **`cs_n`, `sdo`, `RTD_DRDY` -- the three nets PR #1196 left fake-completing -- are fixed.** Root cause: their `primary_grid` (the netclass-SSOT working layer) was ALSO wrong, so Tier 2 anchored its own via at the pad's `(x, y)` using the SSOT layer before PR #1196's landing via got added -- three layers stacking on one coordinate, which `via_layer_pair` (`packages/temper-geometry/src/via_clearance.rs:100`) cannot resolve (it assumes at most two layers ever meet at one point). Fixed at the root: `_astar_route_nlayer` now anchors the route's own start/end point (not the route body, not mid-route continuity) on the net's own real pad layer instead of blindly reusing the SSOT layer there. All three move from `is_fake_completion` to `fully_connected=True`, confirmed by direct `check_net_pad_connectivity` calls on both boards. §1, §4.
2. **Task 2's surgical per-endpoint decline was NOT implemented, and that refusal is the load-bearing result of this document, not a limitation to skim past.** `pad_connectivity_audit`'s `is_fake_completion` is defined purely geometrically -- `has_any_copper and not fully_connected` -- with no channel for "the router itself already knows and honestly reported this is partial." That means ANY nonzero copper on a net that doesn't reach every one of its own pads is, by construction, indistinguishable from the exact defect PR #1196 exists to prevent. Making the `gnd`/`vcc` decline surgical would flip them from honest zero-copper (`category=broken`, `has_any_copper=False`) to reported fake-completion (`has_any_copper=True`, `fully_connected=False`) -- the specific regression this task's own hard constraint calls worse than the copper loss it would recover. The prerequisite for a surgical decline is a metric that can tell "honestly partial" apart from "silently fake"; that is a `pad_connectivity_audit` change, not a router change, and it was explicitly out of scope here (that file belongs to another agent this session). What WAS done instead: the net-level decline stays net-level (zero copper reaches the board, exactly PR #1196's existing behavior, measured byte-identical), but the refusal is now recorded honestly in a side channel the board writer never reads and the success counter never sees -- `PathfindingResult.partial_paths`, an existing pattern already used by `_astar_reconstruct.py`'s tree-route path, not something invented for this. §5.
3. **A defect in this fix's own first draft, caught before shipping.** The anchor-layer fix could coincide with Tier 2's own chosen alternate layer, emitting a via that spans zero real layers -- `(layers "F.Cu" "F.Cu")` -- caught on the real board, net `RTD_SDO`. Fixed by only emitting/recording the anchor when it differs from the alternate layer; a direct repro test pins it. §3.
4. **Cross-check: my independently re-run pre-landing-fix figure reproduces the coordinator's exactly** -- 59 connected / 56 fake-completion / 11 honest-gap / 13 zone-dependent-unmeasured, out of 139 nets with pads. This is the first time two independently-run measurements agreed on this board all session; it is what makes the 59 → 66 → 69 arc below a real trend and not three unrelated numbers. §2.
5. **`route_board.py`'s own printed completion line and this document's 4-way breakdown are the SAME measurement in two different bases**, not disagreeing figures -- `route_board.py` still calls the audit's old 2-way `is_fake_completion`/`fully_connected` split, which folds every `zone_dependent_unmeasured` net into "fake" (that property is deliberately unchanged by zone classification -- see the audit module's own docstring). Reconciled exactly in §2.
6. **`via_layer_pair`'s two-layers-per-point assumption is still unfixed.** This document's fix removes the only known TRIGGER for it on this board (no more co-located via stacking at a pad), not the underlying assumption. Anyone who hits a genuine 3-layer via stack elsewhere is hitting a known, reported gap, not an unexplored one. §6.
7. **Two pre-existing test failures, confirmed unrelated to this change** -- `test_bundle_analyzer.py::test_identical_signal_nets_bundle` (a `networkx` API mismatch predating this session) and `test_strip_copper.py::test_matches_real_production_board_zone_count` (a pinned segment count, 2290, that no longer matches this worktree's actual committed `pcb/temper.kicad_pcb`, which has 2149) -- neither touches any file this change modified. The second one is flagged separately below: a test pinned against a board file that has since moved on is its own small instance of the exact pattern (stale ground truth silently misreported as current) this whole session has been chasing. §7.

---

## 1. `primary_grid` selection: the rule chosen, and why not the deleted guard

`docs/evidence/2026-08-14-router-pad-layer-landing-fix.md` §5a root-caused the residual defect: for `cs_n`/`sdo`/`RTD_DRDY`, the net's `primary_grid` (`channel_path.preferred_layer`, resolved by `channel_mapping._assign_layer` -> `assign_layer_impl` in `temper-orchestration/src/channel_mapping.rs`) was ALSO wrong -- not just the pad-landing endpoint PR #1196 fixed. Tier 1 failed on that wrong primary layer (unlike the 6 nets PR #1196 fixed outright, where Tier 1 walked straight through and "succeeded"), so Tier 2's whole-segment alternate-layer detour fired -- and Tier 2 anchors its own via at the route's boundary point using `primary_grid.layer_name`, the SSOT layer, before PR #1196's landing fix ever runs. PR #1196's landing fix then ALSO fires at that same coordinate, inserting a SECOND via. Three layers meet at one point; `via_layer_pair` resolves only the first adjacent pair, twice, and the transition that would have actually landed copper on the pad's real layer is silently dropped.

The task this document answers directly: **how should a net's working layer be chosen when its netclass-SSOT layer disagrees with the layer its own pads are on?** A prior "divergence guard" (SSOT applied only when it agreed with a name-based heuristic: power/ground/HV -> B.Cu, else F.Cu) was deleted before this session, with the stated reasoning that via-aware transitions and the fallback tier would compensate -- an assumption PR #1196 disproved for 9 nets, 6 of which its own landing-via fix then repaired. Restoring that guard verbatim would have pushed EVERY SSOT-classified net -- including the 6 PR #1196 just fixed -- back onto whatever its bare name heuristic says, discarding the netclass's copper-weight/routing-convention intent wholesale. That is explicitly not what was done here.

**The rule implemented:** `primary_grid` itself (the value that drives Tier 1's same-layer search, and every MID-route Tier-2/Tier-3 continuity anchor) is unchanged -- still the netclass-SSOT layer. A net whose SSOT layer is actually reachable still routes on it end to end, honoring the netclass's intent; this is the common case (Tier 1 succeeds directly, or Tier 2 needs the pad-layer correction only at its own endpoints). What changed is narrower and lives only at the route's own boundary: the very first and very last emitted point of the whole net -- which is the pad itself, not a hop with a "next segment" to stay continuous with -- now anchors on that pad's own real, measured copper layer (`pad_layer_start`/`pad_layer_end`, looked up once per net from the board's actual pad positions via a new shared helper, `_pad_layer_at_point`) instead of blindly reusing `primary_grid.layer_name` there. Concretely, in `_astar_route_nlayer` (`packages/temper-placer/src/temper_placer/router_v6/_astar_nlayer.py`):

- Tier 1's own emission is untouched -- it already gets corrected post-hoc by PR #1196's `_land_route_on_pad_layers` when it walks straight through on the wrong layer, and that correction is proven working for 6/9 nets.
- Tier 2's whole-segment alternate-layer detour now anchors the route's OWN start point on `effective_start_layer` (falls back to `primary_grid.layer_name` when no pad-layer override is known or it isn't a routable grid) instead of unconditionally `primary_grid.layer_name`, and symmetrically for the last segment's end anchor on `effective_end_layer`. Every mid-route anchor (any segment that is neither the route's first nor its last) is untouched -- still `primary_grid.layer_name`, preserving intra-net continuity exactly as before.
- Tier 3's full via-aware 3D search receives the same `effective_start_layer`/`effective_end_layer` as its `start_layer`/`goal_layer` arguments at the route's own boundary, and `primary_grid.layer_name` everywhere else.
- The forced-segment fallback (dead in production -- `allow_forced_segments` is unconditionally `False` -- but exercised by one existing test) gets the same substitution, for the same reason: consistency, and because this data is exactly what Task 2's `partial_paths` diagnostic preserves on a decline.

**Disagreement is made visible, not silently resolved either way.** `run_astar_pathfinding_nlayer.attempt_route` computes `pad_layer_start`/`pad_layer_end` before calling `_astar_route_nlayer`, and logs (`logger.info`) plus counts (`PathfindingResult.layer_divergence_count`, new field, default `0`, purely additive) every endpoint where the SSOT layer and the pad's own layer disagree -- regardless of whether the net ultimately routes successfully. Verified firing directly (isolated harness, `run_astar_pathfinding_nlayer` on a 2-grid synthetic board with SSOT=B.Cu, pads on F.Cu):

```
INFO:...:net 'NET1': netclass-SSOT preferred_layer='B.Cu' disagrees with the start pad's own layer='F.Cu'; anchoring that route endpoint on the pad's real layer instead of the SSOT layer.
INFO:...:net 'NET1': netclass-SSOT preferred_layer='B.Cu' disagrees with the end pad's own layer='F.Cu'; anchoring that route endpoint on the pad's real layer instead of the SSOT layer.
layer_divergence_count: 2
```

`channel_mapping._assign_layer`'s Python-shim docstring was also corrected in this branch (docs-only change, `b64c9df99`) -- it still described the deleted divergence guard as current behavior, which is exactly the stale-truth pattern flagged again in §7.

---

## 2. Numbers: the cross-check, then the arc

**Cross-check first, because it is what makes the rest of this trustworthy.** The pre-landing-fix board (`fix/router-nlayer-routing @ f870bc966`, artifact `scratch_out/temper_routed_nlayer.kicad_pcb`, copied read-only from `/home/bennet/Desktop/temper-worktrees/router-nlayer-routing` -- never modified, never regenerated) was independently re-audited in this branch's own worktree, with this branch's own cherry-picked fixed audit tool, with no communication with whoever produced the coordinator's own figure for the same board:

| | connected | fake-completion | honest-gap | zone-dependent-unmeasured |
|---|---:|---:|---:|---:|
| coordinator's figure | 59 | 56 | 11 | 13 |
| this document's independent re-measurement | 59 | 56 | 11 | 13 |

Exact agreement, all four cells, first try. That is the first time two independently-run measurements on this board agreed all session, and it is the reason the arc below is read as one coherent trend rather than three numbers that happen to share a magnitude.

**The arc.** All three boards below are routed with the identical invocation (`scripts/route_board.py --pcb pcb/temper.kicad_pcb --output <scratch>/out.kicad_pcb --net-batching --batch-size 10`), all three audited with the same fixed `pad_connectivity_audit.check_net_pad_connectivity`, out of the same 139 nets-with-pads:

| stage | connected | fake-completion | honest-gap | zone-dependent-unmeasured |
|---|---:|---:|---:|---:|
| pre-landing-fix (`f870bc966`, before PR #1196) | 59 | 56 | 11 | 13 |
| post-landing-fix only (`c331903f6`, PR #1196, before this fix) | 66 | 43 | 17 | 13 |
| **post-this-fix** (this branch, HEAD `7e8343707`) | **69** | **40** | 17 | 13 |

The delta this document is responsible for is the last row versus the middle row: **+3 connected, -3 fake-completion, honest-gap and zone-dependent-unmeasured both exactly unchanged.** That is precisely the shape of `cs_n`/`sdo`/`RTD_DRDY` moving from fake to connected and nothing else moving -- confirmed directly in §4, not inferred from the aggregate.

**`route_board.py`'s own printed line is the same measurement in a different basis, not a discrepancy.** Its `audit_pad_connectivity` helper (`scripts/route_board.py`) still computes `fake_completion_nets = [n for n, r in results.items() if r.is_fake_completion]` -- the audit's old 2-way property, which the fixed audit's own docstring says is "deliberately UNCHANGED by zone dependence": it does not know about the new 3-way `category` (`connected`/`zone_dependent_unmeasured`/`broken`) at all, so every `zone_dependent_unmeasured` net that also happens to have non-joining copper (`is_fake_completion=True`) still gets folded into "fake" by that call site. Reconciled exactly for the post-this-fix board: of the 13 `zone_dependent_unmeasured` nets, 8 are ALSO `is_fake_completion=True`; `40 (broken-and-fake) + 8 (zdu-and-fake) = 48`, matching `route_board.py`'s printed `fake-completion=48` exactly; `17 (honest-gap) + 5 (zdu, not fake-shaped) = 22`, matching its printed `honest-gap=22` exactly. So `route_board.py`'s `69/48/22` and this document's `69/40/17/13` are the identical audit run read through two different collapses of the same four numbers -- not two different measurements, and not one of them wrong.

**Physical corroboration, measured directly from the emitted `.kicad_pcb` content (paren-balanced block extraction, independent of the audit tool):**

| | post-landing-fix only | post-this-fix |
|---|---:|---:|
| segments | 5612 | 5672 |
| vias | 103 | 91 |
| F.Cu↔B.Cu vias | 43 | 31 |
| zones | 160 | 160 (unchanged) |
| segments by layer | F.Cu 2069 / In3.Cu 1449 / In4.Cu 1092 / B.Cu 1002 | F.Cu 2069 / In3.Cu 1513 / In4.Cu 1136 / B.Cu 954 |

Via count and F.Cu↔B.Cu via count both drop (103->91, 43->31): the fix removes the duplicate/degenerate via records the three-layer collision and the anchor bug (§3) were producing, not "fewer connections" -- connectivity rose in the same measurement.

---

## 3. A defect this fix's own first draft produced, caught before shipping

The first working version of the anchor-layer fix (§1) unconditionally emitted the route's own boundary anchor point, then unconditionally emitted the Tier-2 alternate-layer point, exactly mirroring the pre-existing code's shape. That pre-existing shape was safe because `other_grids` (Tier 2's candidate alternate layers) is constructed as `[g for name, g in grids.items() if name != primary_grid.layer_name]` -- it excludes `primary_grid.layer_name` by construction, so the old unconditional anchor-then-alternate pair could never be a same-layer no-op. `effective_start_layer`/`effective_end_layer` (the pad's own real layer) carries no such guarantee -- `other_grids` never excludes it. When a net's pad real layer happened to equal the alt_layer Tier 2 actually landed the detour on, the anchor-then-alternate pattern emitted the identical `(x, y)` point on the identical layer twice in a row.

Measured directly on the real board's first routed output (`myfix_after.kicad_pcb`, pre-dating the fix in this section): net `RTD_SDO` carried two via records with `(layers "F.Cu" "F.Cu")` -- a via drilled through zero real layers, a malformed record.

**Fixed** (`7e8343707`): the anchor point (and its `via_positions` entry) is now only emitted when it actually differs from `alt_layer`; when it doesn't, the route begins/ends directly on `alt_layer` with no via at all -- correct, since the pad's own layer already IS where Tier 2 landed. **Regression test added**, `test_nlayer_tier2_skips_degenerate_same_layer_anchor_via` (`packages/temper-placer/tests/router_v6/test_astar_nlayer.py`): B.Cu fully blocked so Tier 1 fails outright, Tier 2 detours onto F.Cu -- which is also set as the pad's own layer -- asserts zero vias and every segment on F.Cu.

Re-measured after the fix (`myfix_after2.kicad_pcb`): connectivity numbers identical to the pre-fix intermediate result (69/40/17/13, `cs_n`/`sdo`/`RTD_DRDY` all still `fully_connected=True`) -- the degenerate via was a hygiene/via-count defect, never a connectivity one, and it is the numbers in §2 (drawn from `myfix_after2.kicad_pcb`, the post-fix board) that are canonical.

---

## 4. The three residual nets, confirmed directly

`check_net_pad_connectivity`, called directly (not inferred from the aggregate), on both the post-landing-fix-only board and the post-this-fix board:

| net | post-landing-fix only | post-this-fix |
|---|---|---|
| `cs_n` (2 pads) | `pads_connected=1, fully_connected=False, category=broken` | `pads_connected=2, fully_connected=True, category=connected` |
| `sdo` (2 pads) | `pads_connected=1, fully_connected=False, category=broken` | `pads_connected=2, fully_connected=True, category=connected` |
| `RTD_DRDY` (2 pads) | `pads_connected=1, fully_connected=False, category=broken` | `pads_connected=2, fully_connected=True, category=connected` |

All three: one pad connected, one pad stranded on the wrong layer with no via reaching it -> both pads reached, `fully_connected=True`. Exactly the shape §1 predicts and nothing else.

---

## 5. Task 2: why the decline stays net-level, argued in full

**The ask.** PR #1196's decline (`_land_route_on_pad_layers` returning `None`, the whole net discarded) is net-level and all-or-nothing: if either endpoint's landing via cannot be legally placed, the entire net is thrown away, including segments that routed correctly. Measured, real, not an audit artifact (per PR #1196's own evidence doc §5b): `gnd` (88 pads, 106 segments before PR #1196) and `vcc` (150 segments before PR #1196) went from partial copper to zero segments and zero vias under PR #1196's fix. The ask for this task was to make that decline surgical -- keep the valid routed segments, refuse only the landing that cannot be placed, report the net as honestly partial.

**Why it cannot be done that way under the current metric.** `pad_connectivity_audit.NetConnectivityResult.is_fake_completion` (`packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py`) is defined as `has_any_copper and not fully_connected` -- a pure function of the emitted geometry and the net's own pad set. It carries no channel for "the router computed this honestly and is telling you it's incomplete" versus "the router thinks this is done and is wrong." Those are, to this metric, the identical shape. This is not an incidental gap -- the fixed audit's own `category` property (`connected`/`zone_dependent_unmeasured`/`broken`) explicitly documents that `is_fake_completion` is "Deliberately UNCHANGED by zone dependence," i.e. the metric owner already made a considered choice to keep this property purely geometric even while adding a different kind of nuance (zone visibility) elsewhere.

Concretely: `gnd` has 88 pads. Any decline strategy that keeps even one but not all of its previously-computed segments -- refusing only the one bad landing while keeping the rest -- necessarily leaves `gnd` with `has_any_copper=True` and `fully_connected=False` (unless it happens to reach literally every one of 88 pads, which is exactly the scenario that already failed). By the metric's own definition, that is indistinguishable from `is_fake_completion=True`. Verified directly, not asserted: this document's own measurement (§2, §4) shows `gnd`/`vcc` at `has_any_copper=False, category=broken` (honest zero-copper) on BOTH the post-landing-fix-only board and the post-this-fix board -- identical, unchanged, confirming no surgical-decline logic was allowed to leak any partial copper onto the board for these nets.

**This task's own hard constraint says the direction of that tradeoff explicitly:** "A regression to fake completion would undo the entire value of PR #1196, and is far worse than `gnd` having no copper." Given the metric's construction, "surgical decline that still emits some copper" and "regression to fake completion" are not two different outcomes to weigh against each other for a multi-pad net like `gnd` -- they are the same outcome, described two ways. So the honest engineering answer here is not "surgical decline was attempted and it regressed" -- it is that surgical decline, as specified, is not expressible as a safe change to the router alone. **The prerequisite is a metric that can represent "honestly partial" as its own state, distinct from "fake" -- which is a `pad_connectivity_audit` change, not a router change.** That file is explicitly out of scope for this task (owned by another agent this session, and this task's own instructions say not to edit it). Recording that here is the point: whoever picks up surgical decline next should start from the metric, not from `_land_route_on_pad_layers`.

**What was implemented instead: honest reporting that never touches the board.** `_land_route_on_pad_layers`'s existing net-level all-or-nothing contract is UNCHANGED (still returns `None` on any endpoint failure -- all 4 of PR #1196's original tests for it pass unmodified). What changed is a NEW parallel path in `run_astar_pathfinding_nlayer.attempt_route`, using the SAME underlying attempt (refactored into `_attempt_pad_layer_landing`, returning `(route_with_whatever_landing_succeeded, blocked_ends)` instead of collapsing straight to `None`):

- The failure reason is now specific: `pad_layer_landing_blocked:start`, `:end`, or `:start,end` -- not just the single undifferentiated string PR #1196 used.
- The geometry that WAS legitimately computed -- every segment plus a landing via at whichever end succeeded, if any -- is preserved in `PathfindingResult.partial_paths`, keyed by net name. This is not a new mechanism: `_astar_reconstruct.py`'s tree-route path already populates this exact field, gated by the exact same `_has_safe_partial_geometry` check (rejects a forced/fabricated edge; requires real, searched geometry), for its own analogous partial-decline case. This task's change reuses it rather than inventing a second one.
- `PathfindingResult.partial_paths` flows to `RoutingResults.partial_routes` (`routing_results.compile_routing_results`, pre-existing) which is **never read by `_write_routes_to_content`** (`_adapter_convert.py:577`, `compiled = getattr(routing_results, "compiled_routes", {})` -- `partial_routes` is not in that call at all) and **never counted by `success_count`** (`sum(compiled_routes) + tree_routes + plane_net_count` -- again, `partial_routes` excluded). So nothing in `partial_paths` can reach the board file or inflate a completion counter, by construction, not by convention.
- The SAME preservation was applied to the pre-existing forced-segment decline (`route_path.forced_segment_count > 0`, unrelated to PR #1196, predates this session) for consistency -- it is the other shape of "net-level decline discards a valid partial prefix," and the fix is the identical pattern.

**Verified end to end**, not just described (synthetic harness, occupying the end pad's own grid cell to force exactly a `blocked_ends=("end",)` outcome):

```
routed_paths: []
failed_nets: ['NET1']
failure_reports: {'NET1': 'pad_layer_landing_blocked:end'}
partial_paths: ['NET1']
partial segments: [(2.0, 2.0, 'F.Cu'), (2.0, 2.0, 'B.Cu'), ... (8.0, 8.0, 'B.Cu')]
partial via_positions: [(2.0, 2.0)]
```

The start pad's landing via IS present (`(2.0, 2.0, 'F.Cu') -> (2.0, 2.0, 'B.Cu')`); the route never lands on the end pad's real layer at all (ends on `'B.Cu'`, not the pad's `'F.Cu'`) -- an honest record of exactly what succeeded and what didn't, held entirely outside the board-writing path.

---

## 6. `via_layer_pair`: still not fixed, and what "not fixed" actually covers now

`via_layer_pair` (`packages/temper-geometry/src/via_clearance.rs:100`) still resolves a via's `(from, to)` layer pair by scanning for the FIRST index in the route's flat point list where the via's `(x, y)` occurs and returning that point's layer paired with the next point's layer -- still assumes at most two layers ever meet at one coordinate, still silently drops any third transition stacked at the same point.

This document's fix removes the only known TRIGGER for that assumption failing on this board: the specific mechanism (§1) where Tier 2 anchors a via at a pad using the wrong SSOT layer, and PR #1196's landing fix then stacks a second via at the identical point, no longer arises, because Tier 2 now anchors correctly the first time. It does not touch `via_layer_pair`'s own logic, and does not prove no OTHER path on this or any other board could still stack three (or more) via crossings at one coordinate -- that remains a real, structural limitation of the function, unresolved, cross-crate (`temper-geometry`, with its own pinned oracle and differential tests separate from anything this task touched), and with (from PR #1196's own evidence doc) two candidate fix directions that were never adjudicated against each other. Recorded here explicitly so the next person who reproduces a 3-layer via collision on this board knows it is a known, described gap -- not a new discovery requiring re-diagnosis from scratch.

---

## 7. Pre-existing test failures, confirmed unrelated

Full `router_v6` suite run against this branch's own isolated `.venv` (no shared-repo `.venv` rebuild): reached 94%+ of ~2000 collected tests with exactly the two failures below, before the shared machine's memory pressure OOM-killed the pytest process itself on an unrelated, memory-heavy integration test (`test_temper_production_board_routing.py`) -- confirmed via `journalctl -k`, which shows the kernel OOM-killer targeting the pytest PID directly (`Out of memory: Killed process ... anon-rss:59003832kB`), alongside an unrelated process on the same shared machine OOM-killed minutes earlier. Not a code failure; not attributable to this change; the `--deselect` flag for that one heavy test did not prevent the collector from reaching it before the kill.

- **`test_bundle_analyzer.py::test_identical_signal_nets_bundle`** -- `AttributeError: 'Graph' object has no attribute 'edges_with_data'`, a `networkx` API mismatch. `git blame` places this before this session; PR #1196's own evidence doc records the identical failure. `bundle_analyzer.py` is not in this change's diff.
- **`test_strip_copper.py::TestStripExistingCopper::test_matches_real_production_board_zone_count`** -- asserts this worktree's own `pcb/temper.kicad_pcb` carries exactly `2290` segments (`+ 48` vias `+ 96` zones); the file this worktree actually has carries `2149` segments and `44` vias (`96` zones, unchanged) -- `2149 + 44 + 96 = 2289`, exactly the failure's reported actual value. `_strip_copper.py` is not in this change's diff, and `pcb/temper.kicad_pcb`'s sha256 is verified unchanged throughout this entire task (see provenance comment). **Flagged separately, not just as "unrelated":** this is the same pattern as the deleted-guard docstring in §1 and the whole reason PR #1196 exists in the first place -- a pinned expectation (here, a literal segment count; there, `_assign_layer`'s docstring; originally, a completion counter) that quietly stopped matching the artifact it describes, and nothing forced a human to notice until this task's own verification pass happened to run this specific test. Not fixed here (touching a pinned regression guard's expected value is its own reviewable decision, and the file it guards is explicitly off-limits to modify for this task) -- reported so a reviewer attributes it to drift, not to this diff.

Targeted tests for every file this change touched: `test_astar_nlayer.py` 16/16 (15 pre-existing + 1 new, `test_nlayer_tier2_skips_degenerate_same_layer_anchor_via`), `test_astar_route_multilayer_via_fallback.py` 7/7 (unchanged production-path tests, confirming the N=2 case this generalizes still behaves identically), `test_pad_connectivity_audit.py` 19/19 (cherry-picked from `575f1ba8f`, unmodified by this branch).

---

## 8. What was deliberately not changed, and why

- `primary_grid` itself was not reassigned for the whole net -- only the route's own start/end anchor. Reassigning `primary_grid` wholesale would discard the netclass's routing-convention intent for the entire route body on every net where it disagrees with the pad's own layer, which is exactly what restoring the deleted divergence guard would also have done, and exactly what this task's brief says not to do.
- The deleted `_assign_layer` divergence guard was not restored, in any form -- see §1.
- `via_layer_pair`'s two-layers-per-point assumption was not fixed -- see §6. Judged as needing its own design (two candidate directions, cross-crate, pinned oracle), not a same-session extension of this fix.
- Task 2's decline was not made surgical at the board-output level -- see §5. The metric change that would make it safe is out of scope (owned elsewhere this session, and explicitly off-limits to edit here).
- `pad_connectivity_audit.py` was cherry-picked verbatim (`570007030`), never edited, per this task's explicit instruction.
- `test_strip_copper.py`'s pinned segment count was not updated -- see §7; flagged, not fixed, since the guard and the file it pins are both outside this task's scope.
- No DRU/clearance/creepage threshold changed. No ceiling in `power_pcb_dataset/drc_ceiling.json` touched. `pcb/temper.kicad_pcb`'s sha256 unchanged throughout.
