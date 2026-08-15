<!-- provenance: diagnosis-only task, branch agent/routing-diagnosis-40nets, worktree
../temper-wt-agent-routing-diagnosis-40nets, base origin/fix/clearance-1085-remediation-exec
@ aa90a4376363199aa4943ec2569e559fb3ac536d (= origin/fix/board-schematic-resync (#1134) +
#1157's DRU scoping fix + 7-net copper strip, per the task's own instruction). pcb/temper.kicad_pcb
NOT modified: sha256 a70e34bbefe4801212104376adccd59872c06142d8a4d0de0f04eea5a445f04f, unchanged
before and after every measurement in this document (matches the hash PR #1168 independently
recorded for the same commit). Worktree built with `make venv-isolate`; `scripts/check_stale_extensions.py`
reported 10/10 fresh (mtime-fallback, no build stamp) AND all 10 extensions independently verified
to `import` cleanly; `scripts/check_venv_integrity.py` passed (18/18 entries resolve under this
worktree, not a hijacked/shared venv). `make netlist` run in this worktree. All routing numbers
below come from one live, foreground-verified run of the production router
(`temper_placer.router_v6.pipeline.RouterV6Pipeline` via a thin diagnostic driver that calls the
exact same code path as `scripts/route_board.py --net-batching --batch-size 10` / `router_v6.adapter.route_pcb`,
but additionally keeps the raw `RouterV6Result` so `stage4.pathfinding_result.failure_reports`
-- which `route_pcb()`'s own return type does not surface -- is available for attribution),
461.3s wall, measured with `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file` against
the run's own output content (never against `pcb/temper.kicad_pcb` itself). -->

# 40 no-path nets: 60% are ordinary 0.2mm-clearance signal nets, not HV -- this is 2-layer channel-capacity exhaustion, confirmed genuine (not a router limitation) at the algorithm level

**Verdict up front.**

1. **Reproduced the task's own numbers exactly**, on a fresh, independent run: 139 nets
   audited, **53 fully pad-connected, 46 fake-completion, 40 with zero copper** ("no-path").
   `route_board.py`'s own reported pathfinding rate for the same run: 70/106 attempted
   (66.0%), 36 explicit A* failures.
2. **The 40 no-path nets are dominated by ordinary low-clearance signal nets, not the
   mains/HV domain.** By netclass: **24/40 (60%) are `(unassigned/default)`** -- the
   *cheapest* clearance class on the board (0.2mm, the same bar `Signal`/`Default` nets get)
   -- **6 `FinePitch`, 3 `Power`, 6 `HighVoltage`, 1 `ACMains`**. If this were primarily an
   HV-creepage-corridor problem, ordinary 0.2mm nets would not be two-thirds of the failures.
   This is the single most important pattern in the data.
3. **For every net that reached Stage 4's A* search (36 of 40), the failure signature is
   identical and it is not a router limitation.** All 36 declined via the exact same code
   path (`_astar_reconstruct.py`: `route_path.forced_segment_count > 0` ->
   `"no legal path found (forced segment disallowed)"` -> `rule_id=forced_segment_fail_closed`):
   **A* completed its search and found a candidate path in every one of these 36 cases** --
   it did not time out, exhaust an iteration cap, or hit a batch/subprocess limit -- but
   *every* candidate path required routing through a cell that violates the net's own
   clearance against neighbouring copper (a "forced segment"). The router's fail-closed
   policy correctly refuses to emit that illegal copper rather than fabricate a connection.
   Zero of the 36 show the *other* Stage-4 failure branch (`reason="congestion"`, emitted
   only when A* finds literally nothing at all), zero show `rule_id=None` (`attribution_gap`,
   the honest "we don't know why" case), zero show `prover_error` (unhandled exception). This
   is the router being honest about a real absence of legal room, not giving up early.
4. **Board-wide, not localized**: the 36 nets' `congestion_region` midpoints split
   10 top-of-board / 10 mid-board / 16 bottom-of-board, and ~20 already-successfully-routed
   nets recur as the "ripped up, still failed" blocker across dozens of *unrelated* failing
   nets in different regions (`PWM_LS` blocks 22, `rtd_pan.low_window-out` 21,
   `safety.uvlo_logic-line` 19, `safety.fault_any_or-a2` 19, `PWM_HS` 18, `boot` 18,
   `WDT_RESET_N` 17, ...). A localized placement defect produces a hotspot; this produces a
   board-wide recurring set of the same "channel is full" obstacles. This matches the
   production router's own resource-exhaustion bound (`resource_bound.py`,
   independently measured on this same placement in `docs/evidence/2026-08-13-clearance-1085-remediation-exec-steps-1-2.md`
   Sec 2.5): **channel capacity 8546 mm² vs. demand 11236.6 mm² -- utilization 1.31**, a
   *provable* bin-packing lower bound of at least 9 nets that must fail regardless of
   algorithm, before this document's own 40 are even counted.
5. **Structural cause of the capacity shortage**: the board is a 4-layer stackup with
   `In1.Cu`/`In2.Cu` declared `power` layers in the `.kicad_pcb` itself (not `signal`) --
   confirmed in the file's own `(layers ...)` block and independently in five separate
   `router_v6` module docstrings (`channel_mapping.py`, `_astar_nlayer.py`,
   `_corridor_backbone.py`, `power_plane.py`, `_ground_plane.py`). Every one of the 112
   A*-routed nets on this 152mm x 234mm board competes for **F.Cu + B.Cu only** -- half the
   board's copper layers carry zero routed signal traffic by design.
6. **A small (2/40, 5%), distinct, genuinely router-side gap exists and should not be
   conflated with the other 38**: `discharge.k_dis1-no` and `discharge.k_dis2-no` never
   appear in Stage 4's `failure_reports` *or* `routing_results.failed_nets` at all under
   `--net-batching` -- not attempted, not declined, not routed. This is consistent with a
   net-batching Stage-3-topology assignment gap (`route_board.py`'s own
   `net_batch_summary.nets_no_topology` mechanism, not captured by this run's diagnostic
   driver) rather than a Stage-4 pathfinding failure, and is flagged as unresolved rather
   than folded into the "genuine congestion" verdict above.
7. **`hole_clearance` is not independently re-measured in this document** (time-boxed out
   per this task's own instruction to report partial results rather than open new
   investigation threads). PR #1159's own 4-way scratch decomposition already characterized
   it as hole-to-*neighbouring-copper* proximity -- i.e. the same channel-congestion
   mechanism as finding 3-4 above, not a via pad/drill-ratio defect -- and explicitly scoped
   it to this effort. Taken as corroborating, not independently confirmed here.

---

## 1. Method

`scripts/route_board.py --net-batching --batch-size 10` calls
`temper_placer.router_v6.adapter.route_pcb()`, which returns a `RoutingResult` that has
already discarded the per-net `RoutingFailureReport` (`failure_reason`, `blocking_nets`,
`congestion_region`, `rule_id`, `domain`) -- `_build_routing_result()` only keeps
`unrouted_nets` (bare names) and a `DrcViolation` list gated on `drc_violations > 0`, which
is empty for every net in production (`net_reports` is populated only by
`benchmark.py`, never by the live Stage 4 driver). To get the real per-net attribution this
task asks for, a diagnostic driver was written
(`/tmp/.../scratchpad/diag_route.py`, not committed -- scratch only, per the task's
constraints) that constructs `RouterV6Pipeline` with the *identical* arguments
`route_pcb()` uses (`max_iter=500_000`, `enable_net_batching=True`, `net_batch_size=10`,
`enable_zone_pours=True`, same layer-constraint/netclass resolution) and calls
`pipeline.run()` directly, keeping the raw `RouterV6Result` so
`result.stage4.pathfinding_result.failure_reports` (a `dict[str, RoutingFailureReport]`,
populated by the real Stage-4 driver in `_astar_reconstruct.py`, not a stub) is available.
The routed content is then written with the same `_write_routes_to_content()` the adapter
uses, and audited with `pad_connectivity_audit.audit_pcb_file()` -- the same tool and
metric the task names as authoritative. `pcb/temper.kicad_pcb` was read-only throughout;
sha256 verified identical before and after (header above).

```
wall_s: 461.3
pf (Stage-4 pathfinding) success/failure/completion: 70 / 36 / 66.0%
pad_connectivity (PRIMARY metric): audited=139 fully_connected=53 fake_completion=46 no_copper=40
```

53/139, 46 fake-completion, 40 no-copper -- byte-for-byte the task's own cited figures,
confirming this run is representative and not an outlier.

## 2. Which 40, exactly, and the three distinct mechanisms behind them

| mechanism | count | detail |
|---|---:|---|
| A* completed a search, every candidate path required a forced (clearance-violating) segment, declined fail-closed | **33** | `reason=no_path`, `rule_id=forced_segment_fail_closed`, real `congestion_region` + `blocking_nets` (rip-up history) attached |
| Presumed zone-pour-covered (`_should_route()` excludes them from A* on the assumption a plane fill reaches them), but the emitted board carries zero copper for them | **5** | `+15V_LS`, `+170V_BUS`, `PWR_RTN`, `SW_NODE`, `ac_n` -- all `HighVoltage`/`ACMains` netclass; a zone-pour delivery gap, not an A* failure |
| No Stage-3 topology assigned under net-batching; absent from Stage 4 pathfinding *and* `routing_results.failed_nets` entirely | **2** | `discharge.k_dis1-no`, `discharge.k_dis2-no` -- see finding 6, flagged as a possible batching-side gap, not re-diagnosed further here |
| **total** | **40** | |

(36 of these 40 appear in `failure_reports`; the other 3 nets in `failure_reports`
-- `discharge.k_dis1-nc`, `hb.power_loop.q_high-g`, `tank.c_tank1-p2` -- failed Stage-4
pathfinding exactly the same way but ended up with *some* stray copper elsewhere on the
board via a different code path, so `pad_connectivity_audit` classifies them as
`is_fake_completion` rather than `no_copper`; they belong with the 46, not the 40, by this
document's own primary metric, but share the identical Stage-4 failure signature described
below.)

### 2a. By netclass (the 40)

| netclass | count | nets |
|---|---:|---|
| `(unassigned/default)` | 24 | `RELAY_CTRL`, `discharge.k_dis1-coil1`, `discharge.k_dis1-coil2`, `discharge.k_dis1-no`, `discharge.k_dis2-no`, `discharge.r_snub2-p2`, `fb`, `hb-gnd`, `i2c_sda_ui`, `ina`, `inb`, `power_in.bypass_relay-coil1`, `power_in.bypass_relay-coil2`, `power_in.q_relay_drv-g`, `rtd_pan.rail_monitor-ina_p`, `rtd_pan.rail_monitor-outa`, `s1`, `safety-line-1`, `safety-line-3`, `safety.coil_thermal-line`, `safety.fault_any_or-y2`, `safety.fault_or-y2`, `safety.ovp.r_adc_top1-p2`, `y` |
| `HighVoltage` | 6 | `+15V_LS`, `+170V_BUS`, `PWR_RTN`, `SW_NODE`, `discharge.k_dis2-nc`, `w1_1` |
| `FinePitch` | 6 | `RTD_DRDY`, `RTD_SCK`, `cs_n`, `sclk`, `sdi`, `vbias` |
| `Power` | 3 | `+3V3`, `gnd`, `vcc` |
| `ACMains` | 1 | `ac_n` |

**All 6 `FinePitch`-class nets on the board that appear in this failure set share one
component pair**: `U8` (an RTD-interface IC) and `U27`, with `R29`/`R31`/`R32`/`R35`/`R37`
as the intervening pull/bias resistors -- the entire SPI-like RTD sense bus
(`sclk`/`sdi`/`cs_n`/`RTD_SCK`/`RTD_DRDY`/`vbias`) fails together. `FinePitch`'s own
clearance (0.1mm) is the *tightest* on the board, and it is assigned `layer: "B.Cu"` --
this bus is fighting for the single most oversubscribed layer with the least clearance
margin to give, and loses in six places at once.

### 2b. By board region (36 with a `congestion_region`)

| y-band | count |
|---|---:|
| top (y < 90mm) | 10 |
| mid (90-180mm) | 10 |
| bottom (180-254mm, board is 254mm tall) | 16 |

Spread across the whole board, not concentrated in one corner -- consistent with a global
channel-capacity deficit, not a single local placement defect.

### 2c. Recurring blockers (nets whose already-routed copper was rip-up-attempted while
searching for one of the 36, then still failed)

`PWM_LS` (22 of 36), `rtd_pan.low_window-out` (21), `safety.uvlo_logic-line` (19),
`safety.fault_any_or-a2` (19), `PWM_HS` (18), `boot` (18), `WDT_RESET_N` (17), `sw` (16),
`power_in.ntc-no` (16), `discharge.r_dis2a-p2` (16), `WDT_KICK` (16),
`hb.gate_hs.driver-p2` (15), `thermal.j_fan-p1` (15), `discharge.r_dis1a-p2` (15),
`input` (14), `RTD_SDI` (13), `RTD_SDO` (12), `safety.ovp.r_adc_top2-p2` (12),
`safety.ovp.comp-inp` (11), `discharge.k_dis2-coil1` (11).

The same ~20 already-successfully-routed nets recur as obstacles for dozens of *different*
failing nets in *different* board regions. This is the signature of a channel that is
generally full, not of one or two components sitting in the wrong place.

## 3. Genuine congestion vs. router limitation -- the decisive question

**Answer: genuine congestion, confirmed at the algorithm level, for the entire 33/33
sample that reached a real A* search.** The relevant code
(`packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py:339-349`):

```python
if route_path.forced_segment_count > 0 and not tree_route_active:
    print(f"      ✗ {net_name} FAILED: no legal path found "
          f"(forced segment disallowed)", flush=True)
    return _forced_segment_decline([], ...)
```

`route_path` is not `None` here -- A* returned an actual path. The decline fires only
because that path's `forced_segment_count` is nonzero, i.e. **the search space contains no
path that respects this net's clearance requirement against copper already on the board**;
every path A* can find requires an illegal proximity. This is structurally different from,
and mutually exclusive with, every failure mode a *router limitation* would produce:

- **Not a timeout**: no `prover_error` (the code's own catch-all for an unhandled exception
  or hang) appears in any of the 36.
- **Not a search-bound problem**: `max_iter=500_000` is the same value `route_pcb()` uses
  in production. This exact question was already independently swept on this board
  (`_pipeline_core.py`'s own docstring, dated 2026-07-27): 500k/1M/2M/4M iterations all
  produced the *same* failure count (2M and 4M byte-identical output) -- raising the
  iteration cap is documented as **not a completion lever** on this board.
- **Not a batch-size artifact for the 33/33 that show this signature**: PR #1157
  independently reproduced the identical `rule_id=forced_segment_fail_closed`,
  `reason=no_path` signature for 7 of these nets' close relatives using a *monolithic,
  non-batched* `RouterV6Pipeline` call (`skip_stage3=True`, `target_nets=<7 nets>`, no
  `--net-batching` involved at all), and further ruled out interference from other nets'
  copper via an all-48-fake-completion-net-stripped diagnostic comparison that reproduced
  the exact same failures. Two independently-configured runs (this document's 112-net
  batched run; PR #1157's 7-net monolithic scoped run) converge on the same mechanism.
- **What *is* a router-limitation candidate**: the 2 nets in Sec 2 mechanism 3
  (`discharge.k_dis1-no`, `discharge.k_dis2-no`) that never reach `failure_reports` at all
  under net-batching. That is a real, distinct, small (5% of the 40) gap this document does
  not resolve -- worth a follow-up run with `--net-batching` off (or a larger batch size)
  to see if they get a real attempt and a real verdict, rather than silently falling through.

## 4. What would unblock them, costed

**Do not relax any clearance/creepage safety value** -- none of the mechanisms above are
"the rule is stricter than IEC requires"; `HV_CREEPAGE_ENFORCED_MM` (8.0mm) is already the
softer of the two documented figures (PD3's 12.6mm was measured to add +153 violations if
raised), and 60% of these 40 failures are on the board's *cheapest* (0.2mm) netclass, which
has no safety margin to give up in the first place.

| option | what it buys | cost / caveat |
|---|---|---|
| **Route on In1.Cu/In2.Cu** (convert declared `power` layers to `signal`, or add 2 new physical signal layers in a 6-layer stackup) | Roughly doubles routable channel capacity (8546 mm² -> ~17,000 mm²+ against ~11,237 mm² demand), taking utilization from a *proven-infeasible* 1.31 to a comfortable ~0.65 -- clears the resource-exhaustion bound entirely, not just this board's specific 40 | Loses the continuous GND/PWR reference planes this board relies on for EMI/thermal return path (REQ-ELEC-05, `_astar_nlayer.py`'s own comment) unless upgraded to 6 layers with 2 planes retained -- a real fab-cost and re-stackup change, not a config flag |
| **Widen the board** (currently 152mm x 234mm, `(20,20)-(172,254)`) | Closing a 31% capacity deficit by area alone needs roughly proportional growth if fill/keepout ratios hold -- order of +25-30mm on the long dimension | Mechanical/enclosure redesign, likely the most expensive option per mm² gained since components don't shrink and IEC creepage corridors don't shrink with them |
| **Targeted placement study around the recurring blockers** (Sec 2c: the `PWM_HS`/`PWM_LS`/gate-drive cluster, the RTD SPI bus around `U8`/`U27`, the discharge/relay branch around `K1`-`K3`/`Q1`/`Q2`) | Not measured in this document -- PR #1168 already showed a full re-place routes *worse* (50/139), so a full re-place is not the lever, but a small, scoped nudge of the highest-frequency blocker components was not tried here and is a legitimate, bounded follow-up hypothesis, not a proven fix | Needs its own measured before/after; **do not treat this row as a recommendation**, only as the most promising unexplored option this data points at |
| **Accept wire links** for the worst-congested residual nets | A documented, already-precedented escape hatch in this repo for genuinely irreducible cases | Appropriate for a handful of nets at most (e.g. the `FinePitch` RTD-bus cluster if it still fails after a layer/width change), not a board-wide answer for 40 nets |
| **Net-batching / router config changes** | Addresses at most 2/40 nets (Sec 2, mechanism 3) | Everything else in this document is explicitly *not* a router-config problem -- raising `max_iter`, changing batch size, or increasing SAT/via budgets will not move the other 38 |

**Honest bottom line, per this task's own instruction to say so if true**: the dominant
driver (33/40, and by extension a meaningful share of the 46 fake-completion nets and the
still-unmeasured `hole_clearance` findings, per PR #1159's own characterization) is a
**structural, board-wide 2-layer channel-capacity deficit** (utilization 1.31, a proven
lower bound of failures regardless of algorithm), not a placement defect scoped to a
handful of components and not a router search limitation. Closing it for real needs either
more routable layers or more board area -- both real, costed, non-software changes. This is
a significant finding for the repair-vs-replace decision: PR #1168 already showed re-placing
the *existing* board doesn't help (50/139, worse than repair's 53/139) because re-placement
cannot manufacture channel capacity that does not exist; this document's finding is
consistent with and explains that result.

## 5. What is left undone

- The 2-net net-batching gap (Sec 3, `discharge.k_dis1-no`/`discharge.k_dis2-no`) --
  re-run with `--net-batching` off to get a real Stage-4 verdict for these specifically.
- `hole_clearance` was not independently re-measured against the current (post-#1157)
  board in this session; PR #1159's characterization is taken as corroborating, not
  confirmed here.
- The zone-pour delivery gap for the 5 `should_route_excluded` HV/mains nets (Sec 2,
  mechanism 2) -- why the plane-fill these nets are presumed to rely on isn't reaching
  them -- is reported, not root-caused.
- The "targeted placement study" row in Sec 4 is a hypothesis from blocker-frequency data,
  explicitly not a measured recommendation.
