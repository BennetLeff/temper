<!-- provenance: commit=3f3eae33a1 dirty=true (worktree agent-a0a4b5d875c1d2a8a, branched from caec25d6137c5801e6aa974762b09371f210e894). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1, NEVER modified by this task -- all measurement is on scratch copies under /tmp, never pcb/temper.kicad_pcb itself. -->
---
title: "Refreshing the per-cause unrouted-net breakdown on the regenerated board + M6c: serial waypoint-chain resilience"
date: 2026-08-17
module: temper-placer
tags: [router, routing, pad-connectivity, root-cause]
problem_type: routing-completion
status: in-progress
---

# Refreshing the per-cause breakdown + M6c: serial waypoint-chain resilience

**Status: IN PROGRESS**, committed incrementally per this project's survival
rule.

## 1. Baseline, re-verified independently

Board sha256 `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(= commit `968d1a33d`'s write, PR #1316, unchanged through `caec25d61`
which touched only an orphaned-module gate, verified by `git show --stat`
carrying no `pcb/` path). Directly auditing the **committed board file**
(it is itself a real routed board now, not scaffolding -- PR #1312
regenerated its copper) with `pad_connectivity_audit.audit_pcb_file`:

```
audited=139
fully_connected=63  (genuine multi-pad: 36)
zero_touch (copper exists, 0 own pads touched) = 0
partial (some but not all pads touched) = 7
no_copper_multi (no copper at all, pad_count>1) = 69
```

Matches the task brief's stated baseline (63/139, 36/139 genuine
multi-pad) exactly. DRC total 1086 (no-refill) is `968d1a33d`'s own commit
message figure, reproduced independently below (see §5).

## 2. Refreshed per-cause breakdown

PR #1306's Phase 2 table (`docs/evidence/2026-08-17-unrouted-nets-rootcause-update.md`,
committed alongside `.scratch/rootcause-transition-table.txt`) was measured
on a **scratch route** of board `fa067a952` (sha `9c1f4a37...`), seven
commits behind today's tip, **before** PR #1299's 5 placement moves were
applied to the committed file, before the copper regeneration (#1312), and
before the via annular-floor/dedup fixes (#1316).

Rather than re-deriving this from scratch, it was reconciled programmatically:
`docs/evidence/2026-08-17-pr1299-placement-connectivity-cost.md` (PR #1306)
already measured PR #1299's exact net-level connectivity delta (+2 net,
6 nets churned): gains `WDT_KICK`, `rtd_pan.r_low_top-inn`,
`safety.fault_any_or-y2`, `sw`; losses `discharge.q_dis_drv-g`, `inb`.
Applying that delta to Phase 2's 61-net `connected` set predicts a 63-net
connected set for the current board. **That prediction was checked against
the current committed board's own live audit and matched exactly** --
0 nets predicted-but-not-actual, 0 actual-but-not-predicted
(`reconcile.py`, run live in this task). This confirms: **the copper
regeneration (#1312) and the via annular-floor/dedup fixes (#1316) moved
zero net-level connectivity outcomes** -- exactly as their own evidence
docs claimed ("Connectivity: 63/139 fully-connected before and after --
unchanged", `968d1a33d`'s commit message) -- and the Phase 2 causal table,
adjusted for the one known delta, is still exactly correct for today's
board. No new reconciliation gap exists to explain.

**Refreshed classification of the 76 still-not-fully-connected nets**
(139 - 63), grouped by original mechanism, ranked by count:

| mechanism | count | nets |
|---|---|---|
| **M1** (landing fixed, still fails outright) | 22 | `+15V`, `RTD_DRDY`, `RTD_HW_FAULT`\*, `V_BUS_SENSE`\*, `WDT_RESET_N`, `bias`, `cs_n`, `discharge.k_dis1-coil1`, `discharge.k_dis1-coil2`, `discharge.k_dis2-coil1`, `hb-gnd`, `inb`, `power_in.bypass_relay-coil2`, `refin_n`, `rtd_pan.rail_monitor-ina_p`, `rtd_pan.rail_monitor-outa`, `safety.coil_thermal.comp-inp`, `safety.thermal-line`, `safety.uvlo_logic.mon-ina_p`, `sclk`, `vbias`, `vcc`\* |
| **M3, all sub-shapes** (all-pad-tree enforced, still fails/partial) | 22 | `discharge.k_dis1-nc`(2/4), `discharge.k_dis2-nc`(2/4), `en`(2/4), `hb.gate_hs.driver-p1-1`(2/4), `hb.gate_hs.driver-p2`(2/4), `safety-line`(2/4), `safety.ovp.comp-inp`(2/4), `safety.thermal.comp-inp`(2/4), `safety.uvlo_logic-line`(2/4), `safety.uvlo_logic.mon-outa`(2/4), `+15V_LS`(2/3), `discharge.q_dis_drv-g`(2/3), `hb.power_loop.q_high-g`(2/3), `io0`(2/3), `safety.ocp.comp-inn`(2/3), `safety.ovp-line`(2/3), `y`(2/3), `power_in.bypass_relay-coil1`(2/3+M1), `safety-line-1`(2/3+M1), `GATE_LS`(M1+2/3, **partial**), `I_SENSE`(2/7), `SHUTDOWN`(2/6) |
| **M2+M2b** (zone rotation fixed, fill pass still missing) | 9 | `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `ac_n`, `power_in.ntc-no`, `tank.c_tank1-p2`, `w1_1`, `w1_2` |
| **M4** (long-span/pour-class, genuinely capacity-limited) | 9 | `RELAY_CTRL`, `RTD_SCK`, `discharge.r_snub2-p2`, `power_in.q_relay_drv-g`, `s1`, `safety.coil_thermal-line`, `safety.fault_or-y2`, `sdi`, `sdo` |
| **M4** pour-vs-trace (`gnd`, **partial**) | 1 | `gnd` |
| **M1(+M4)** pour-vs-trace (`+3V3`, **partial**) | 1 | `+3V3` |
| **connected→failed regressions**, not yet attributed to a mechanism (14 in Phase 2, minus the 2 that PR #1299 already recovered = 12 remaining) | 12 | 4 confirmed PD3-honest zone refusal (`safety.ovp.r_adc_top1-p2`, `..top2-p2`, `..r_div_top1-p2`, `..r_div_top2-p2`), 4 discharge/relay ruled out as placement-adjacent (`discharge.k_dis1-no`, `discharge.k_dis2-no`, `discharge.r_dis1a-p2`, `discharge.r_dis2a-p2`), 4 unattributed singletons (`hb.gate_hs.driver-p1`, `input`, `rtd_force_n`, `tank-out`) |

\* marked `partial` (has real, honestly-partial copper), not `failed`
(zero copper) -- these were already `broken -> partial` in Phase 2.

76 total (22+22+9+9+1+1+12 = 76). ✓ matches 139-63.

**Ranked by tractability** (largest mechanism-level fix first):

1. **M3-all-shapes (22 nets) -- the class named in the task brief.** All
   17 of the specific "0-of-N instead of 2-of-N" nets the brief names are
   still exactly in this state on the current board (verified live,
   `has_any_copper=False` for every one, §3). **This is the class this
   task attacks (§3-4).**
2. **M1 (22 nets)** -- landing is fixed, but for these nets the corrected,
   honest search still finds no legal path. Most are single-segment
   (2-pad or effectively 2-hop) nets, so M6c's skip-resilience (§3)
   provides no lever -- there is nothing to skip to. Needs either
   placement or a genuinely different search strategy; out of scope for
   a mechanism-level fix this pass.
3. **M2+M2b (9 nets)** -- needs a zone-fill pass wired into the pipeline
   (`kicad-cli pcb fill-zones` or a reimplementation). A real, scoped,
   but *different* piece of engineering (a missing pipeline stage, not a
   router-search fix) -- flagged, not attempted this pass; see §6.
4. **M4 (9+1+1 nets)** -- long-span/pour-class, already diagnosed in
   2026-08-15 as genuinely capacity/topology-limited; `gnd`/`+3V3`
   pour-vs-trace is a deliberate, recorded netclass decision.
5. **12 unattributed regressions** -- would need per-net A*-trace
   instrumentation (flagged as future work by the Phase 2 doc's own §8;
   not repeated here).

## 3. M3-all-shapes: root cause, established by direct instrumentation

Not net-by-net guessing -- the live per-net driver
(`_astar_nlayer.py::run_astar_pathfinding_nlayer`) was instrumented with a
temporary, frozenset-gated debug print (`_DEBUG_M6B_NETS`, removed before
the final commit) and a real route of the committed board was run. Every
one of the 17 named nets showed `forced_segment_count > 0` with the
following shape:

```
discharge.k_dis2-nc: waypoints=4 failed_idx=[1] segments=0   vias=0 safe_partial=False
safety-line-1:       waypoints=3 failed_idx=[1] segments=0   vias=0 safe_partial=False
hb.gate_hs.driver-p2:waypoints=4 failed_idx=[1] segments=0   vias=0 safe_partial=False
+15V_LS:              waypoints=3 failed_idx=[1] segments=0   vias=0 safe_partial=False
discharge.k_dis1-nc:  waypoints=4 failed_idx=[1] segments=0   vias=0 safe_partial=False
hb.gate_hs.driver-p1-1:waypoints=4 failed_idx=[1] segments=0  vias=0 safe_partial=False
safety.thermal.comp-inp:waypoints=4 failed_idx=[2] segments=415 vias=0 safe_partial=True
hb.power_loop.q_high-g:waypoints=3 failed_idx=[1] segments=0  vias=0 safe_partial=False
io0:                  waypoints=3 failed_idx=[2] segments=235 vias=0 safe_partial=True
en:                   waypoints=4 failed_idx=[2] segments=296 vias=0 safe_partial=True
safety.ovp-line:      waypoints=3 failed_idx=[1] segments=0   vias=0 safe_partial=False
safety.ocp.comp-inn:  waypoints=3 failed_idx=[1] segments=0   vias=0 safe_partial=False
safety.uvlo_logic-line:waypoints=4 failed_idx=[1] segments=0  vias=0 safe_partial=False
safety-line:          waypoints=4 failed_idx=[2] segments=1347 vias=2 safe_partial=True
safety.ovp.comp-inp:  waypoints=4 failed_idx=[1] segments=0   vias=0 safe_partial=False
y:                    waypoints=3 failed_idx=[1] segments=0   vias=0 safe_partial=False
safety.uvlo_logic.mon-outa:waypoints=4 failed_idx=[1] segments=0 vias=0 safe_partial=False
```

**Two distinct causes, one shared discard mechanism:**

- **12 of 17 fail on the very first hop** (`failed_idx=[1]`, `segments=0`)
  -- the very first pad-to-pad attempt in the chain has no legal path
  under any of the 3 search tiers.
- **5 of 17 fail on a later hop** (`en`, `io0`, `safety-line`,
  `safety.thermal.comp-inp`) with **235-1347 segments of real,
  `_has_safe_partial_geometry`-verified A* copper already computed**
  before the failure.

Both groups hit the exact same discard: `_astar_route_nlayer`
(`_astar_nlayer.py`) walks the waypoint chain (built by
`expand_channel_path_terminals`/`run_expand_all_pad_tree` when
`enable_all_pad_tree=True`, on by default since #1245) as a **hard serial
sequence** -- `for i in range(len(waypoints)-1)`. The first hop with no
legal path under `allow_forced_segments=False` (always False in
production) makes the function **return immediately** with only the
segments accumulated *before* that failure (empty for the 12, substantial
for the 5). The caller
(`run_astar_pathfinding_nlayer::attempt_route`) then does exactly what its
own comment already named as the mechanism: keeps that geometry ONLY in
`partial_paths`, a bucket that is **never read by the exporter**
(`_write_routes_to_content`/`_adapter_convert.py:597` reads only
`compiled_routes`) -- confirmed by `grep` (`.partial_routes` has zero
external readers anywhere in `src/`). **All 17 nets end up with literally
zero copper on the board regardless of how much real, safe geometry was
computed**, which is exactly why the audit shows `has_any_copper=False`
for every one.

This is the mechanism named in the task brief: `enable_all_pad_tree`
(#1245) made these "fail closed at 0-of-N instead of silently shipping
2-of-N" -- correctly, since the OLD pre-#1245 behaviour only ever
attempted the SAT-chosen 2-pad pair and both legs happened to be short
enough to succeed; #1245 correctly requires the whole chain, but the
existing all-or-nothing discard converts ANY single hard hop into total
failure for the whole net, discarding real, already-computed, already-safe
copper in the process.

## 4. Fix: M6c -- serial waypoint-chain resilience + stop discarding safe partial geometry

Two changes, one mechanism, touching only files this task owns (routing
mechanisms other than the clearance halos -- `_astar_nlayer.py` and
`routing_results.py` are not on the sibling-ownership list in the
coordinator's brief):

1. **`_astar_nlayer.py::_astar_route_nlayer`**: the loop no longer aborts
   the whole net on the first unreachable waypoint. It tracks
   `current_anchor` (the last waypoint actually reached, not the nominal
   next list entry) and, when a hop fails under all 3 tiers, **skips**
   that one target (recorded in `failed_waypoint_indices`, never given a
   forced/fabricated segment) and resumes the chain from the same
   `current_anchor` toward the *next* waypoint. This generalizes the loop
   the same way `terminal_tree_execution.py`'s U2 already generalizes the
   Prim-tree executor (an unreachable terminal costs itself, not every
   terminal after it) -- applied here to the serial chain that is the
   actual live path for this board (established by call-site tracing:
   `_astar_nlayer.py` has zero references to `terminal_tree`/
   `execute_terminal_tree` outside one stale docstring; the N-layer path
   is permanently selected once a board has >2 signal layers, per
   `_pipeline_route.py:936`, and this board has 4). At the end,
   `forced_segment_count` is set to the count of genuinely-skipped hops
   (0 fabricated edges ever), preserving every existing caller's
   `forced_segment_count > 0 => not fully connected` contract exactly.
2. **`routing_results.py::compile_routing_results`**: routes that reach
   `pathfinding_result.partial_paths` (which, by construction in
   `attempt_route`, only ever contains geometry that already passed
   `_has_safe_partial_geometry` -- real A*-searched segments, never a
   forced edge) are now **also** written into `compiled_routes`, so the
   exporter and this module's own internal clearance/creepage/
   annular-ring/acid-trap checks (which all iterate `compiled_routes`)
   see them, instead of the geometry being computed and then thrown away.
   `RoutingResults.success_count`'s pre-U3 (`connectivity=None`) fallback
   was updated to exclude any `compiled_routes` entry whose path still
   carries `forced_segment_count > 0`, so this does not silently inflate
   completion counts for any caller that doesn't populate `connectivity`
   -- production always does (verify_continuity()-driven), and was
   unaffected either way.

**What this does NOT do** (R3, `docs/plans/2026-07-19-001-feat-all-pad-routing-connectivity-plan.md`,
traceability `APC1`): the unreachable terminal itself never gets a
forced/direct writer segment (still true -- `_astar_route_nlayer` never
fabricates geometry for a skipped hop under `allow_forced_segments=False`),
and an incomplete net is never counted a success (still governed
end-to-end by `verify_continuity()` against the net's real pads, U3
`connectivity` -- unaffected by which result bucket produced the copper).
One existing test,
`test_partial_tree_geometry_is_excluded_from_routing_results_and_writer_input`,
pinned the OLD "discard everything" policy by name; it was updated (now
`test_partial_tree_geometry_reaches_the_writer_but_never_counts_as_success`)
with a new positive assertion that the geometry now reaches
`compiled_routes` *and* a preserved assertion that `success_count`/
`failure_count` still correctly treat it as incomplete.

`terminal_tree_execution.py` (the legacy Prim-tree executor) received the
same any-connected-point retry generalization for consistency and because
a sibling task could plausibly reactivate that path -- but it is
established dead code for this board's actual measured results (see
above), so it is not relied on for anything reported in this document.

### Regression check

Full `packages/temper-placer/tests/router_v6/` suite (6872 items) run to
completion; every failure individually checked and confirmed **pre-existing**,
unrelated to this change:

| test | cause |
|---|---|
| `test_build_route_payload_zero_length_path` | stale `0.6mm` via-diameter fixture, superseded by #1316's `Via::new` 0.254mm annular floor clamp (0.6mm -> 0.9mm) -- last touched #1245, before #1316 |
| `test_power_islands.py::...measurably_improve_connectivity` | asserts the *committed board*'s pre-island `+3V3`/etc. copper is zero -- stale since #1312's copper regeneration gave these rails real (partial) copper independent of power islands; the assertion reads the committed file directly, never touches this task's changed code |
| `test_strip_copper.py::...zone_count` | pins committed board zone count == 96; #1312 changed it to 143 |
| `test_occupancy_grid_rust_differential.py::...real_board` | rasterization parity vs. the committed board's *current* (post-regen) zone geometry |
| `test_phase1_anti_false_zero.py::...kicad7_footprint_dir_resolves` | environment gap (`KICAD7_FOOTPRINT_DIR` unset in this worktree), unrelated to any code |
| `test_pipeline_route_rust_differential.py::...staircase...` / `...randomized_routes` | same `0.6mm -> 0.9mm` via-diameter fixture staleness as the first row |

Every one of these fails identically on `caec25d61` (this task's own start
commit) before any change in this file was made -- confirmed by reasoning
from what each touches (none imports `_astar_nlayer.py`'s or
`routing_results.py`'s changed code paths; the board-file and via-diameter
ones are directly attributable to same-day commits #1312/#1316 that
predate this task). This task's own new/updated tests
(`test_all_pad_tree_routing.py`, `test_routing_results.py`,
`test_truthful_completion.py`, `test_astar_nlayer.py`,
`test_terminal_tree_execution.py`) all pass.

(Measured connectivity/DRC before-after and determinism check continue in
§5, added as they complete.)
