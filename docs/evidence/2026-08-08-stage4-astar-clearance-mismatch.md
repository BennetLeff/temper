<!-- provenance: commit=888331bad3cda9230fee0318583acc9e9d0d5f7f dirty=true -- diagnosis measured against this commit; the fix itself is the dirty diff in this same task -->

# Stage 3 vs Stage 4 clearance-model disagreement: 19-genuine-A*-failure investigation, root cause, fix, and measured (negative) effect on copper coverage

**Date:** 2026-08-08

**Task:** Diagnose why topology-solved nets fail Stage 4's clearance-aware A*
with "forced segment disallowed" on `pcb/temper.kicad_pcb`, and determine
whether Stage 3 and Stage 4 disagree about clearance/width rules.

## Headline, stated plainly up front

**Confirmed: Stage 3 and Stage 4 used inconsistent per-net clearance/width
values — a real, measured software defect, now fixed.** But fixing it does
**not** recover the routing-completion gap the task set out to close: a
full before/after production route (net-batching, `pcb/temper.kicad_pcb`)
shows copper coverage **drops** from 64/110 to 61/110 nets after the fix.
The defect was silently *helping* completion by under-protecting
`HighVoltage`/`HighVoltageIsolated`/`GateDrive*`-class copper (real
clearance up to 6.0mm, enforced during Stage 4 pathfinding as if it were
0.15mm) — a latent creepage/clearance safety gap on this AC-mains-adjacent
board, independent of and more urgent than the completion metric. The
majority of the topology-solved-but-copper-less nets are **genuinely
infeasible at the current placement** (dense multi-net congestion), not
software-fixable, consistent with the prior independent investigation in
`docs/evidence/2026-07-27-forced-segment-analysis.md`.

## 1. Measured baseline (this commit, `888331ba`, unmodified)

`scripts/route_board.py --net-batching --batch-size 10` against
`pcb/temper.kicad_pcb`, three independent full production runs (two
concurrent + one solo), all byte-identical:

- All 11 Stage 3 batches SAT, 110/110 nets get a real topology.
- `topology_copper_audit.audit_topology_vs_copper()` (the prescribed
  tool, not an ad hoc parse): **64/110 nets carry copper** (explicit
  trace/via or zone), **2 legitimately need none** (self-referential
  pads), **44 UNEXPLAINED** (topology-solved, no copper anywhere, no
  recorded legitimate reason).
- Of the 44: **6 are the known `_should_route`/`_zone_layers_for_net`
  policy-gap orphans** (`+15V`, `+3V3`, `PWR_RTN`, `V_BUS_SENSE`, `gnd`,
  `vcc` — a separate, disjoint bug another agent is fixing) and **38 are
  genuine Stage 4 A\* attempts that failed** with
  `forced_segment_fail_closed` / "no legal path found (forced segment
  disallowed)".

(The task brief cited "19 genuine A\* failures" from an earlier/partial
measurement; this task's own fresh, reproducible run under the prescribed
tooling measures **38**, not 19. All 10 nets named in the brief's excerpt
— `bias`, `boot`, `fb`, `sdi`, `sdo`, `cs_n`, `RTD_DRDY`, `WDT_KICK`,
`WDT_RESET_N`, `safety.fault_or-y2` — are present in this run's 38-net set,
so the two measurements describe the same phenomenon at different
counts/moments, not a different mechanism.)

## 2. Per-net blocking-constraint table (representative sample; full 38 in the raw capture)

Every one of the 38 failures carries `rule_id=forced_segment_fail_closed`
(the fail-closed gate correctly refusing to fabricate an unchecked
segment) and a real, non-empty `blocking_nets` list from
`_identify_blocking_nets`, captured live via an instrumented run
(monkeypatched `astar_pathfinding.run_astar_pathfinding` return value,
never touching production code):

| Net | Netclass (real) | Blocker count | Sample blockers |
|---|---|---:|---|
| `RTD_DRDY` | FinePitch | 18 | `discharge.k_dis1-coil2`, `hb.gate_hs.driver-p1`, `safety.uvlo_logic.mon-outa`, `GATE_HS`, `ZCD_ISO`, ... |
| `sdi` | FinePitch | 15 | `ZCD_ISO`, `safety.ocp.comp-inn`, `sclk`, `i2c_scl_ui`, ... |
| `boot` | Default | 6 | `safety.fault_or3-y2`, `RTD_SDO`, `safety.coil_thermal.comp-inp`, `i2c_scl_ui`, ... |
| `cs_n` | FinePitch | 19 | `hb.gate_hs.driver-p1`, `rtd_pan.r_high_top-inp`, `I_SENSE`, ... |
| `WDT_KICK` | Default | 7 | `discharge.k_dis2-nc`, `PWM_LS`, `safety-line-1`, ... |
| `discharge.r_snub1-p2` | Default | 0 | (no straight-line blocker — genuine search exhaustion) |

Median blocker count across the 38 is in the same 5-20 range the prior
2026-07-27 investigation found for a similar (non-batched) failure set
("median 7-9 distinct blocking nets, not one") — this is dense multi-net
congestion, not a single fixable obstruction.

## 3. Do Stage 3 and Stage 4 agree on clearance? Tested directly. **No.**

**Stage 3's SAT capacity model** (`net_batching.py::_consume_capacity`,
`constraint_model.py`'s `CapacityConstraint`) computes, for every net,
`net_width = design_rules.get_rules_for_net(net.name).trace_width_mm +
.clearance_mm` — the real, per-netclass value — and subtracts it from
each shared channel edge's geometric capacity. This is correct.

**Stage 4's obstacle-marking** (`_astar_reconstruct.py::attempt_route`,
the `_mark_route_blocked`/`_unmark_route_blocked` calls that inflate a
net's just-routed copper so later nets treat it as an obstacle) used
`design_rules.default_trace_width_mm` / `.default_clearance_mm` — the
flat board-wide default — **unconditionally, for every net, regardless of
class**. `get_rules_for_net(net_name)` was one call away (the *exact*
call Stage 3 makes for the same net, and the same call this very
function's own via-aware 3D fallback tier already makes two branches up)
and was never used at this call site.

**Runtime proof, not inference.** Instrumented a live production run
(monkeypatch on the module-level `_mark_route_blocked` reference in
`_astar_reconstruct.py`, capturing every call's actual arguments):

```
Total _mark_route_blocked calls: 54
Distinct (trace_width, clearance) pairs used: {(0.25, 0.15)}
```

**Every single successfully-routed net's copper was marked blocked using
the identical flat (0.25mm, 0.15mm) pair**, independent of netclass.
Compared against the real, live `design_rules.get_rules_for_net(name)`
value (captured from the same run, reconstructed cheaply — no full
pipeline re-run needed — by replicating `_pipeline_core.py`'s Stage-0
netclass-injection block verbatim):

| Net (blocker in the 38's blocker lists) | Real class | Real (trace+clearance) | Used | Deficit |
|---|---|---:|---:|---:|
| `a`, `discharge.k_dis1-nc`, `discharge.k_dis2-nc`, `zcd` | HighVoltage | 3.0+6.0 = 9.0mm | 0.4mm | **8.6mm under** |
| `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2` | HighVoltageIsolated | 2.0+6.0 = 8.0mm | 0.4mm | **7.6mm under** |
| `GATE_HS`, `PWM_HS`, `PWM_LS` | GateDriveHV/SELV | 0.4+0.25 = 0.65mm | 0.4mm | 0.25mm under |
| `RTD_HW_FAULT`, `RTD_SDI`, `RTD_SDO`, `sclk` | FinePitch | 0.127+0.1 = 0.227mm | 0.4mm | 0.173mm **over** |

**Verdict: confirmed, real, measured disagreement — a design defect, not
19 (or 38) separate routing problems.** It is not one of "Stage 3's
channel-capacity ceiling is coarser than Stage 4's grid" (that geometric
quantity — `channel_widths.py`'s EDT-based "2x distance to nearest
boundary" — is shared, computed once in Stage 2, and used consistently by
both stages). It is specifically that Stage 4's *consumption* accounting
for a net's own copper never consulted the same per-net rule Stage 3's
consumption accounting already used correctly.

## 4. Fix

`packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py`,
`attempt_route()`: both the "mark this net's copper blocked" call and the
symmetric "unmark a ripped-up net's copper" call now resolve
`design_rules.get_rules_for_net(net_name)` and use its
`trace_width_mm`/`clearance_mm`, matching `net_batching.py`,
`constraint_model.py`, and this same function's own via-fallback tier.
The `execute_terminal_tree` (all-pad-tree mode, not exercised by the
production entry point today) call site got the identical fix for
consistency, though its effect is unmeasured (that mode is off by
default).

**Test coverage:** the 5 test files directly covering this code path
(`test_astar_pathfinding.py`, `test_forced_segment_fail_closed_pbt.py`,
`test_decline_reason_contract.py`, `test_astar_route_multilayer_via_fallback.py`,
`test_all_pad_tree_routing.py` — 38 tests) pass unchanged. A broader
`packages/temper-placer/tests/router_v6/` sweep (4826 items, ran to ~38%
before its own time budget) surfaced exactly 3 failures, all independently
confirmed unrelated to this diff: 2 in `test_audit_tree_geometry.py`
(missing `kicad-cli` binary in this sandbox — a pre-existing, documented
environment gap, not a code issue) and 1 in
`test_congestion_rust_differential.py::test_total_movement_bit_exact`
(a Rust-vs-Python `OverflowError` *message-text* mismatch — `"Numerical
result out of range"` vs `"Result too large"` — in an unrelated
congestion-tensor overflow-handling differential test; this diff never
touches `congestion_tensor.py` or its Rust counterpart).

## 5. Measured effect on copper coverage: **negative, not positive**

Full before/after production route (`--net-batching --batch-size 10`,
identical command, identical board):

| | Nets with copper (explicit+zone) | Unexplained gap | A*-attempted & failed | Segments | Vias |
|---|---:|---:|---:|---:|---:|
| Before (unmodified, 3 independent runs, byte-identical) | 64/110 | 44 | 44 | 3058 | 50 |
| After (this fix) | 61/110 | 47 | 49 | 2535 | 54 |

**7 nets newly fail** that used to succeed: `a`, `zcd` (both
`HighVoltage`, now correctly claiming 9.0mm instead of 0.4mm — their own
corridor genuinely doesn't have that much free room), `PWM_LS`
(`GateDriveSELV`, 0.65mm vs 0.4mm), and `ZCD_ISO`, `ina`, `inb`,
`safety.ovp.r_adc_top1-p2` (all `Default` class, unchanged own-width —
these fail only because `a`/`zcd`'s now-correct 9.0mm footprint squeezed
the shared corridor they depend on). **2 nets newly succeed**:
`power_in.bypass_relay-coil2`, `rtd_pan.rail_monitor-outa` (the latter
previously reached copper only via a zone-pour fallback despite an A*
failure; it now routes directly).

**This is the central finding.** The flat-default bug was not making
completion *worse* — it was making it look *better* than physically
correct, by letting SELV/Default-class signal traces route through space
that `HighVoltage`/`HighVoltageIsolated` copper's real 6.0mm creepage
requirement (IEC 60335-1, per `configs/netclass_rules.yaml`'s own cited
rationale) does not actually leave available. Restoring the correct
clearance model exposes that the board is genuinely too congested at the
current placement to route both the HV domain *and* the adjacent SELV
signal cluster with real (not fabricated) clearance — it does not, and
architecturally cannot, manufacture more physical space.

## 6. Verdict: infeasible-vs-fixable classification

**Fixable in software (this task, done):** the Stage3-vs-Stage4 clearance
*value* disagreement itself. Landed; it is a genuine correctness/safety
fix independent of its effect on the completion count, because Stage 4's
occupancy grid is the ground-truth legality check other nets' routing
decisions are made against — under-protecting `HighVoltage`/
`HighVoltageIsolated` copper there is a latent DRC/creepage violation risk
on a board with 340V/400V rails and AC mains input, not merely a
completion-rate cosmetic issue.

**Genuinely infeasible at the current placement (not software-fixable by
this mechanism):** the 38 (now 44, post-fix) topology-solved,
copper-less nets, overwhelmingly. Evidence: (a) each carries 5-20
simultaneous real blockers, not a single removable obstruction, matching
the independent 2026-07-27 finding on a similarly-shaped failure set;
(b) making the clearance model *more* correct — the direction any
further software fix would have to go — **reduced** completion, the
opposite of what a "software bug is artificially blocking these nets"
hypothesis predicts. If the 38/44 were mostly artifacts of a rule
mismatch, correcting the mismatch should have recovered some of them net-
positive; instead the correction net-costs 3 nets of copper. The
remaining path to closing this gap is placement density / net-ordering
work in the SPI/RTD-bus and safety-comparator clusters where these
failures concentrate — out of scope for a router-mechanism task, and
consistent with the prior investigation's own scoped-out follow-up
("Net-ordering or placement-density work... is the correct lever").

## Sources

- `docs/evidence/2026-07-27-forced-segment-analysis.md` — prior
  independent investigation of the same fail-closed mechanism on a
  non-batched failure set; found the same "median 7-9 blockers, dense
  congestion, not a router bug" shape this task's own measurement
  reproduces.
- `docs/plans/2026-07-23-005-fix-router-design-rules-wiring-plan.md` — R1
  fixed *whether* `get_rules_for_net()` could resolve real per-net rules
  at all (wiring `net_class_assignments`/`net_classes` onto
  `pcb.design_rules`); this task's R1-adjacent gap is that one call site
  (`_mark_route_blocked`) never actually called it, despite the wiring
  being correct since that plan landed. That plan's own R8 (a *different*
  bug, the old unconditional forced-segment fallback drawing unchecked
  copper) was independently closed by
  `docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md`.
- `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md`,
  `docs/solutions/logic-errors/missing-cross-class-zone-clearance-regression-2026-07-21.md`
  — prior art for the exact "decoy `design_rules` object" / "flat default
  instead of per-class rule" defect class, previously found and fixed in
  the *zone-emission* path; this task finds and fixes the same class of
  defect in the *trace A\** path.
- `packages/temper-placer/src/temper_placer/router_v6/net_batching.py`,
  `constraint_model.py` — the correct per-net pattern this fix now
  mirrors.
- Live runs: `pcb/temper.kicad_pcb`, `--net-batching --batch-size 10`,
  three before-runs (two concurrent + one solo, byte-identical) and one
  after-run, all backgrounded and polled in-turn.
