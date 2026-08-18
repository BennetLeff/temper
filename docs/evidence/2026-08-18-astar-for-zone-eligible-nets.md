<!-- provenance: commit=84629b2fc0fae4d8aa464239dbb5bda3d17484d0 dirty=true -- the working-tree dirt at measurement time is EXACTLY the change under test (`_net_policy.py` plus the three tests it re-pins), landed together with this document in the very next commit; the BASELINE arm was measured with those files at their committed 84629b2fc state and self-verifies that fact by recording `_should_route`'s 8-net exclusion list. Worktree agent-af083e46ba1200240, branch worktree-agent-af083e46ba1200240. pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified unchanged before AND after this task -- it was never opened for writing; every route below writes to a scratch path under /tmp. .venv isolated to this worktree (make venv-isolate); temper_placer.__file__ and temper_geometry.__file__ verified to resolve inside this worktree before any number below was trusted, and temper-geometry was rebuilt into a private CARGO_TARGET_DIR after the shared target-shared was found poisoned (no `python` feature). kicad-cli 10.0.5; DRC harness copies pcb/fp-lib-table + pcb/libs/ and seeds KICAD_CONFIG_HOME via _drc_api._single_threaded_kicad_env (lib_footprint_issues reads 13 / lib_footprint_mismatch 26, NOT the 168/0 signature of the misconfigured-harness trap). -->

# Does corridor A* connect the 9 zone-eligible nets? Measured: no.

## Bottom line

**No.** With the zone-eligibility exclusion removed from
`_net_policy.py::_should_route`, A* attempts **8 of the 9** nets (the
ninth, `power_in.ntc-no`, stays excluded by `_CONTINUITY_EXEMPT_NETS`)
and lands **zero** paths for any of them. The routed board is
**byte-identical** to the baseline -- same `content_sha256`
`571eb852552869fd5158ddba1da549d23df737cb55ab5b7f9ac27e82f39c3e26`, same
4554 segments, same 170 vias, same 151 zones. Connectivity is unchanged
at 60/139. Every deterministic DRC category is unchanged, including
`shorting_items` (39) and `isolated_copper` (2).

This closes the "untested distinction" the task was scoped around:
straight-line MST stitching (#1341) and obstacle-detouring corridor A*
fail on these nets **identically**, and A* fails without producing a
single segment, so it cannot be trading connectivity against creepage.
The limitation is this board's placement density under PD3 creepage, not
the bridging algorithm's sophistication.

## Two corrections to the task's framing, both measured

### 1. `_should_route` did NOT exclude every zone-eligible net

The premise "`_should_route()` excludes every **zone-eligible** net from
corridor A*" is false as written. The pre-change gate was:

```python
if is_power_net(n) or is_ground_net(n) or is_hv_net(n):
    if _zone_layers_for_net(n):
        return False
```

-- zone-eligible **and** matching a power/ground/HV *name classifier*.
Measured against the real board (16 nets are zone-eligible per the SSOT;
only 8 nets were excluded in total):

| of the 9 target nets | excluded by | A*-eligible before this change? |
|---|---|---|
| `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `ac_n` | the zone-eligibility branch | no |
| `tank.c_tank1-p2`, `w1_1`, `w1_2` | nothing -- all three name classifiers return False | **yes, already** |
| `power_in.ntc-no` | `_CONTINUITY_EXEMPT_NETS` (documented 8GB OOM), not the zone branch | no |

So **3 of the 9 were already being routed by A* in production before this
task started**, and were already failing: all three appear in the
baseline run's `unrouted_nets`. For those three the experiment had
already been run; this task's change cannot and did not affect them.

Removing the branch also makes two nets eligible that are **not** in the
9: `ac_l` (1 pad -- trivially `connected`, never enters pathfinding) and
`hb-gnd` (6 pads -- attempted, failed, `broken`). Reported for
completeness so the +6 in `attempted` reconciles.

### 2. The four `mst_*` counters cannot report on these 9 nets

`mst_edge_count` / `mst_edges_astar_routed_count` /
`mst_edges_fallback_count` / `mst_edges_dropped_count` live on
`PowerIslandResult` (`_power_islands.py`) and `GroundPlaneResult`
(`_ground_plane.py`). Those two generators serve exactly `+3V3`, `vcc`,
`+15V`, `V_BUS_SENSE` (module docstring, `POWER_ISLAND_NETS`) and `gnd`
(`GND_NET_NAME = "gnd"`) -- PR #1339's net set, **disjoint from all 9**.
Those counters are per-*result-object* fields on results those generators
return for those five nets only; there is no code path by which any of
the 9 reaches either generator, so no counter of theirs can ever describe
a target net.

For the record, those generators' own live numbers on this run (their
"edges dropped / edges rerouted" console reports, which is what the four
counters tally) are consistent with #1339 and equally bleak, but they are
about the **other** net set:

| generator / net | MST edges dropped | rerouted via one-bend detour |
|---|---|---|
| `generate_ground_plane_content` (`gnd`) | 74 | 2 |
| `generate_power_islands_content(+3V3)` | 43 | 0 |
| `generate_power_islands_content(vcc)` | 12 | 0 |
| `generate_power_islands_content(+15V)` | 9 | 0 |
| `generate_power_islands_content(V_BUS_SENSE)` | 3 | 0 |

The per-net measurement for the actual 9 is therefore taken from Stage
4's own `PathfindingResult`: a net in `routable_nets` that A* fails lands
in `failed_nets`/`unrouted_nets` with a `RoutingFailureReport`, so
"attempted-and-failed" and "attempted-and-landed" are directly readable
along with the reason.

## The change

`packages/temper-placer/src/temper_placer/router_v6/_net_policy.py` --
the `is_power_net`/`is_ground_net`/`is_hv_net` + `_zone_layers_for_net`
exclusion is deleted; `_CONTINUITY_EXEMPT_NETS` and `_SKIP_NET_PREFIXES`
are the only remaining exclusions. `_should_route`'s excluded-net count
on the production board goes **8 -> 1**.

`_CONTINUITY_EXEMPT_NETS` was deliberately NOT relaxed: routing
`power_in.ntc-no` through A* exhausts an 8GB cap and aborts with
"memory allocation of 4 bytes failed" rather than returning a
route-or-fail verdict (2026-08-14,
`docs/evidence/2026-08-14-ntc-no-realization-and-delta-t-reconciliation.md`).
That is an unresolved router robustness gap, not a routability verdict,
and this task did not attempt to re-trigger it. `power_in.ntc-no` is
therefore the one net of the 9 for which **A* remains unmeasured**, and
is reported as such rather than as a failure.

## Method

`scripts/route_board.py::route_once` (the production `route_pcb` entry
point) against `pcb/temper.kicad_pcb` with its committed copper stripped,
writing to a scratch path; then
`pad_connectivity_audit.audit_pcb_file(Path)` on the written board; then
`kicad-cli pcb drc --all-track-errors --refill-zones --format json
--severity-all` under `_drc_api._single_threaded_kicad_env` with
`fp-lib-table` and `pcb/libs/` copied alongside. Baseline and treatment
differ **only** by the `_net_policy.py` edit; identical harness, identical
board input, same machine, sequential (never concurrent) runs.

## Result 1 -- per-net A* outcome

`should_route` = did A* consider it; `attempted+failed` = present in
`PathfindingResult.failed_nets`; `segs`/`vias` counted by
`pad_connectivity_audit._parse_segments_and_vias` on the written board;
`joined` = `pads_connected` (largest copper-connected pad group).

| net | pads | baseline should_route | A*-run should_route | A* landed a path | segs | vias | joined | audit category |
|---|---|---|---|---|---|---|---|---|
| `+170V_BUS` | 11 | no | yes | **no** | 1 | 1 | 2/11 | zone_dependent_unmeasured |
| `DC_BUS_RTN` | 8 | no | yes | **no** | 0 | 0 | 1/8 | zone_dependent_unmeasured |
| `PWR_RTN` | 15 | no | yes | **no** | 0 | 0 | 1/15 | zone_dependent_unmeasured |
| `SW_NODE` | 7 | no | yes | **no** | 0 | 0 | 1/7 | zone_dependent_unmeasured |
| `ac_n` | 3 | no | yes | **no** | 0 | 0 | 1/3 | zone_dependent_unmeasured |
| `tank.c_tank1-p2` | 4 | **yes** | yes | **no** | 0 | 0 | 1/4 | zone_dependent_unmeasured |
| `w1_1` | 4 | **yes** | yes | **no** | 0 | 0 | 1/4 | zone_dependent_unmeasured |
| `w1_2` | 3 | **yes** | yes | **no** | 0 | 0 | 1/3 | zone_dependent_unmeasured |
| `power_in.ntc-no` | 4 | no | no (`_CONTINUITY_EXEMPT_NETS`) | **not measured** | 0 | 0 | 1/4 | zone_dependent_unmeasured |

`+170V_BUS`'s 1 segment + 1 via is the pre-existing pad-to-pad stitch
survivor from #1341 (present identically in the baseline); it joins 2 of
11 pads and is not new copper from A*.

### How each one failed

Read directly off Stage 4's own `PathfindingResult.failure_reports`, by
wrapping `_astar_nlayer.run_astar_pathfinding_nlayer` as a pass-through
spy around an otherwise unmodified production `route_pcb`. (That is the
live entry point on this board -- `_pipeline_route._run_stage4` picks the
N-layer A* whenever more than two routable signal layers exist, and this
board has four: F.Cu/In3.Cu/In4.Cu/B.Cu. The legacy 2-grid
`run_astar_pathfinding` is never called: measured, 0 invocations.)

| net | domain | `failure_reason` | `rule_id` | ripups | partial path | # blocking nets |
|---|---|---|---|---|---|---|
| `+170V_BUS` | power | `no_path` | `forced_segment_fail_closed` | 0 | no | 18 |
| `DC_BUS_RTN` | power | `no_path` | `forced_segment_fail_closed` | 0 | no | 22 |
| `PWR_RTN` | power | `no_path` | `forced_segment_fail_closed` | 0 | no | 23 |
| `SW_NODE` | hv | `no_path` | `forced_segment_fail_closed` | 0 | **yes** | 17 |
| `ac_n` | hv | `no_path` | `forced_segment_fail_closed` | 0 | no | 1 |
| `tank.c_tank1-p2` | signal | `no_path` | `forced_segment_fail_closed` | 0 | no | 17 |
| `w1_1` | signal | `no_path` | `forced_segment_fail_closed` | 0 | no | 11 |
| `w1_2` | signal | `no_path` | `forced_segment_fail_closed` | 0 | no | 3 |
| `hb-gnd` (not in the 9) | ground | `no_path` | `forced_segment_fail_closed` | 0 | no | 17 |
| `ac_l` (not in the 9) | -- | not attempted (1 pad) | -- | -- | -- | -- |
| `power_in.ntc-no` | -- | not attempted (excluded) | -- | -- | -- | -- |

Every failure is `no_path` attributed to `forced_segment_fail_closed`:
the search ran, found no clearance- and creepage-respecting path, and
declined to fabricate one. That is the correct behaviour
(`_allow_forced_segments` is unconditionally `False`) and it is the
reason no new copper -- and therefore no new creepage exposure -- appears.

Two honest caveats, both read from the same records:

- **`attempted_ripups` is 0 for every one of them.** These nets failed
  against the copper already placed by earlier nets in the ordering,
  without displacing any of it. A rip-up-and-reroute pass, or a net
  ordering that routed these wide HV nets first, is a *different*
  experiment that this one does not rule out.
- **`SW_NODE` produced a partial path** (`in_partial_paths: true`) --
  the only one of the nine that got part of the way. It is still
  `no_path` overall and emitted nothing.

The `blocking_nets` are ordinary SELV signal nets (`GATE_LS`, `PWM_HS`,
`i2c_scl_ui`, `RTD_SDO`, `safety-line-3`, …), which is what a 12.6mm
HV↔LV creepage requirement against a 3.0-5.0mm-wide HV trace predicts:
the obstacle is the mandated separation from low-voltage copper, not a
handful of geometric near-misses.

Aggregate: `attempted` 105 -> 111 (+6: the five excluded target nets plus
`hb-gnd`; `ac_l` is single-pad and never enters pathfinding),
`routed` **34 -> 34 (+0)**, `unrouted` 71 -> 77 (+6). Completion rate
falls 32.38% -> 30.63% purely because the denominator grew while the
numerator did not -- no net lost a route.

## Result 2 -- connectivity delta: zero

| `audit_pcb_file` category | baseline | A*-enabled | delta |
|---|---|---|---|
| `connected` | 60 | 60 | **0** |
| `broken` | 70 | 70 | **0** |
| `zone_dependent_unmeasured` | 9 | 9 | **0** |
| total nets audited | 139 | 139 | 0 |

Per-net audit dicts compare **equal**, not merely equal in aggregate. The
task brief's "79 broken" reconciles as 70 `broken` + 9
`zone_dependent_unmeasured`; the `zone_dependent_unmeasured` set is,
verbatim and in both arms,
`['+170V_BUS', 'DC_BUS_RTN', 'PWR_RTN', 'SW_NODE', 'ac_n',
'power_in.ntc-no', 'tank.c_tank1-p2', 'w1_1', 'w1_2']` -- **exactly** the
9 target nets, no more and no fewer. The router's own Rust
verdicts (`NetRouteResult`, via `verify_continuity`) agree: all 9 are
`zone_dependent` before and after.

## Result 3 -- creepage delta: zero (the +1 is KiCad's own noise)

| category | baseline | A*-enabled | delta |
|---|---|---|---|
| `creepage` (total) | 129 | 130 | +1 |
| `creepage` rule `HV to LV` | 67 | 68 | +1 |
| `creepage` all `* to LV` summed | 127 | 128 | +1 |
| `HighVoltageTank functional creepage` (HV<->HV, 10.0mm) | 2 | 2 | **0** |
| `AC Mains to LV` | 16 | 16 | **0** |
| `HighVoltageIsolated to LV` | 20 | 20 | **0** |
| `HighVoltageSignal to LV` | 17 | 17 | **0** |
| `HighVoltageTank to LV` | 7 | 7 | **0** |

**The +1 is not attributable to this change, and cannot be**: the two
boards are byte-identical files. Measured directly -- 6 repeat DRC runs
on the *single unchanged* `baseline_run1.kicad_pcb`, same harness, same
flags:

```
creepage           128, 129, 130   (values {128,129,130})   NONDETERMINISTIC
HV to LV creepage   66,  67,  68   (values { 66, 67, 68})   NONDETERMINISTIC
clearance                     181  deterministic
shorting_items                 39  deterministic
isolated_copper                 2  deterministic
unconnected_items             264  deterministic
copper_edge_clearance          11  deterministic
hole_clearance                 33  deterministic
```

Both arms' readings (129 and 130) sit inside the same three-value band
produced by one file. This reproduces the repo's own long-standing record
of `creepage` as the single nondeterministic error category
(`power_pcb_dataset/drc_ceiling.json`, upstream KiCad pointer-dedup issue
\#20048). **Creepage is unchanged.** The strongest form of the claim is
structural rather than statistical: A* emitted **zero new copper**, so
there is no new conductor that could owe creepage to anything.

## Result 4 -- shorts and the rest: zero delta

`shorting_items` **39 -> 39**. Every other deterministic category is
identical: `clearance` 181, `copper_edge_clearance` 11,
`courtyards_overlap` 1, `drill_out_of_range` 6, `hole_clearance` 33,
`isolated_copper` 2, `missing_courtyard` 5, `silk_edge_clearance` 1,
`silk_over_copper` 42, `silk_overlap` 199, `solder_mask_bridge` 4,
`unconnected_items` 264, `via_dangling` 28, `lib_footprint_issues` 13,
`lib_footprint_mismatch` 26. The concern that these nets would end up
with both traces and pours does not arise: they got no traces.

### Convention reconciliation: the brief's "creepage floor of 77"

Not reproduced, under either convention, and reported as such rather than
reconciled to. Measured on the same baseline board:

| convention | `creepage` total | `HV to LV` |
|---|---|---|
| `--refill-zones` (used throughout above) | 128-130 | 66-68 |
| **no** `--refill-zones` (3 runs) | 105-106 | 56 |

Neither is 77. The `AC Mains to LV` bucket is what moves most between the
two modes (4 without refill, 16 with) -- i.e. filling the pours is itself
what creates most of the AC-mains creepage exposure, which is worth
knowing independently. `shorting_items` is 39 in **both** modes, and
`isolated_copper` is 0 without refill and 2 with. The "77" figure was
presumably measured under a third scope or an earlier board; whatever it
is, **every number in this document is a like-for-like baseline-vs-
treatment delta measured by one harness in one session**, which is the
claim that matters here, and that delta is zero.

## Result 5 -- determinism

Two full runs per arm, sequential, DRC excluded from the replicate so the
comparison is of route output only:

| | run 1 `content_sha256` | run 2 `content_sha256` | segments | vias | zones | audit 60/70/9 |
|---|---|---|---|---|---|---|
| baseline | `571eb852…3c3e26` | `571eb852…3c3e26` | 4554 | 170 | 151 | identical |
| A*-enabled | `571eb852…3c3e26` | `571eb852…3c3e26` | 4554 | 170 | 151 | identical |

`unrouted_nets`, per-net audit results, `seg_by_net`, `via_by_net` and
`NetRouteResult` dispositions all compare **equal** across every pair.
All four routes produced the *same* board. The baseline replicate
independently confirms it ran the pre-change policy
(`should_route_excluded_nets` listed 8 nets, not 1).

## Result 6 -- test suite: A/B'd, zero regressions

`pytest packages/temper-placer/tests/router_v6 -m "not slow"` run twice
in one scripted pass -- once with the three changed files reverted to
their committed state, once with them restored -- so the comparison is of
the same suite on the same machine in the same session:

| arm | passed | failed | skipped | xfailed |
|---|---|---|---|---|
| pristine (`git checkout --`) | 6870 | 12 | 17 | 25 |
| with this change | 6870 | 13 | 17 | 25 |

The 12 failures are **identical, name for name, in both arms** -- all
pre-existing on this branch, none touched by this change
(`test_ground_plane`, `test_power_islands`, `test_strip_copper`,
`test_u2_stackup_role_ssot` x3, `test_via_output_writer`,
`test_occupancy_grid_rust_differential`,
`test_pipeline_route_rust_differential` x2, `test_quality_metrics_oracle_pin`,
`test_phase1_anti_false_zero`). `test_adapter_convert_marshal_rust_differential.py`
(5 more pre-existing failures) was excluded from both arms after being
confirmed to fail identically on the pristine tree with freshly rebuilt
Rust extensions.

The 13th, `test_constraints_geometry_rust_pbt.py::
test_m1_power_of_two_scaling_is_exactly_equivariant`, is **flaky, not a
regression** -- verified rather than assumed: it has zero references to
`_should_route`/`_net_policy` (grep: 0), and with the Hypothesis example
database cleared it passes 3/3 on the pristine tree and **6/6 on the
modified tree**. Hypothesis found a rare counterexample to this
bit-exactness property during the A/B pass and then replayed it
deterministically from its persisted example DB, which is what made it
look sticky. **Incidental finding worth its own ticket**: that
counterexample is a real latent defect in
`point_to_segment_distance`'s power-of-two scaling equivariance, findable
by re-running that property with enough seeds. It is out of this task's
scope and was not chased.

## Why this is a real negative and not a no-op

A skeptical reading of "byte-identical output" is that the newly-eligible
nets were silently dropped before A* rather than attempted and failed.
Three independent measurements rule that out:

1. `attempted` (`PathfindingResult.success_count + failure_count`) rises
   105 -> 111, i.e. six additional nets entered the ratio.
2. Each of the six appears by name in `unrouted_nets` in the A*-enabled
   run and in neither list in the baseline (`+170V_BUS`, `DC_BUS_RTN`,
   `PWR_RTN`, `SW_NODE`, `ac_n`, `hb-gnd`).
3. `_should_route`'s excluded set, read from the live production
   predicate inside each run, is the 8-net list in the baseline and
   `['power_in.ntc-no']` in the treatment.

And three of the nine (`tank.c_tank1-p2`, `w1_1`, `w1_2`) were reaching
A* and failing *before any change*, which is an independent replication
of the same negative on the same board.

## Hard-rule compliance

- `pcb/temper.kicad_pcb` never opened for writing; sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
  verified before the first command and after the last.
- No clearance, creepage, copper-weight or DRU threshold changed;
  `MIN_BARRIER_WIDTH_MM` untouched; `drc_ceiling.json` untouched.
- No check skipped, xfailed, deleted, or relaxed. Three tests pinned the
  removed policy and were **updated to the new policy with strictly
  stronger assertions**, never weakened:
  `test_hv_net_name_excluded_from_astar_by_should_route` and its AC twin
  asserted only "this net never reached A*"; they now assert the net
  reaches A*, is reported failed, and carries
  `rule_id == "forced_segment_fail_closed"` (i.e. it fails closed instead
  of fabricating copper) -- renamed to `…_reaches_astar_and_fails_closed`
  to match. `test_real_policy_predicates_no_longer_orphan_the_measured_power_ground_nets`
  had `assert not _should_route("PWR_RTN")`; `PWR_RTN` moves into that
  test's own A*-must-route list (exactly as its docstring said it must if
  the exclusion stopped being justified), its zone-eligibility assertion
  is kept unchanged, and a **new** general invariant is added covering
  every listed net: no net may be excluded from A* while also having no
  pour.
- No oracle deleted, consolidated, or re-pinned.
- `git stash` never used.
- No standards value invented; `power_in.ntc-no` is reported as
  **not measured**, not as a failure.

## What this does not establish

- Whether `power_in.ntc-no` is routable by A*. Unmeasured, because the
  attempt OOMs. Fixing that router robustness gap is the prerequisite.
- Whether a *different* placement would let A* connect these nets. Every
  number here is at the committed placement.
- Whether rip-up-and-reroute would change the answer. Every one of the
  nine failed with `attempted_ripups == 0`: they were routed late, into
  copper already committed by other nets, and never displaced any of it.
  Routing the wide HV nets **first** (a net-ordering change) is the
  single most obvious untested lever and is not addressed here.
- Whether the policy change should ship. It is a strict superset of the
  old behaviour (more nets attempted, none rescued, zero copper delta,
  zero DRC delta on this board) and it closes the "orphaned from both
  copper mechanisms" hole as a structural invariant rather than a per-net
  roll-call -- but on *this* board its measured benefit is zero, and its
  measured cost is 6 more nets appearing honestly in `unrouted_nets`
  (completion rate 32.38% -> 30.63%, a denominator effect, not attrition).
  That trade is a reporting-honesty decision for the owner, not a
  routing-quality one.
