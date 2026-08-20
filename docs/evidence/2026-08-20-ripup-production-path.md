<!-- provenance: commit=bc3a19b063a26eb0eabc880494d1133496f0cdfb dirty=false
     Branch agent/ripup-production-path, branched from
     origin/agent/per-pairing-placement-route (bc3a19b06) -- the "best current"
     tip the brief names, which is fd4e73644fec24b26a0c0c4ec51f5c7573c151e4
     (= origin/main + the two backbone fixes) plus the per-pairing
     placer/creepage work. The whole A* core this document is about --
     _astar_nlayer.py, _astar_ordering.py, _astar_search.py,
     _astar_reconstruct.py, _net_policy.py, astar_grid.py, _pipeline_route.py,
     route_stage.py, stage4_orchestrator.py -- is BYTE-IDENTICAL to
     origin/main (591a0e993b74da946415c113e65bb1ac3654d4c3) at this commit:
     `git diff origin/main HEAD -- <those files>` is empty, re-verified after
     origin/main advanced mid-session. The only router_v6 delta vs origin/main
     is the four backbone/zone-pour files, none of which this document's
     conclusions depend on.
     pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
     identical before this task's first command and after its last; never
     opened for writing. Every board written here went to a scratch path
     outside the repo.
     Environment: this worktree's OWN .venv (`make venv-isolate` under
     `env -u CONDA_PREFIX`), extensions rebuilt after the base change,
     check_stale_extensions 10/10 fresh AND all 10 pyo3 modules
     import-smoke-tested -- neither of which was sufficient, see Sec 7.
     No competing route_board.py during any quoted run; 62 GB RAM, >24 GB free.
     No production code changed. Analysis and measurement only.
-->
---
title: "Rip-up-and-retry on the production router path: absent, not merely unreported"
date: 2026-08-20
module: temper-placer
tags: [router, routing, ripup, net-ordering, fail-closed, diagnosis]
problem_type: routing-completion
status: measured
---

# Rip-up is not inert on the production path. It is absent.

**Authority: analysis and measurement only.** No router, placer, clearance,
creepage, DRU or ordering value was changed. Nothing is fixed here.

## 0. Headline

| question | answer |
|---|---|
| **Does rip-up-and-retry run on the production path?** | **No.** In **five** full production routes — two placements, two route-time creepage tables, three net orderings — `_unmark_route_blocked` (the only function in the codebase that un-stamps routed copper) was called **0** times, **0** of 105 nets were attempted twice, every `attempted_ripups` was `0`, and no failure carried `rip_up_limit`. |
| **Is the mechanism absent, or merely unreported?** | **Absent.** `attempted_ripups=0` at `_astar_nlayer.py:1493` is an *honest literal*, not a dropped counter: `_astar_nlayer` has no reroute queue, no second pass, and does not even import `_unmark_route_blocked`. |
| **Is the rip-up decision computed?** | **Yes — and discarded.** `_identify_blocking_nets` ran 43× (model-E) / 70× (committed), returned a non-empty blocker set 66× on the committed board naming **33 distinct already-routed nets**, and every one was dropped one statement later into a diagnostic-only `blocker_history`. |
| **Why is the only real rip-up implementation never reached?** | Two independent reasons, both measured. It lives in `_astar_reconstruct.run_astar_pathfinding`, and (a) the 6-layer board routes through `_astar_nlayer` instead, and (b) the rip-up-capable stage chain `Stage4Orchestrator → RouteStage → run_astar_pathfinding` is **constructed and never run** — `_pipeline_route.py:893-902` calls only the *static* `assemble_pathfinding_result(state)` on a freshly-built `BoardState`, never `orchestrated.run(state)`. Measured: `Stage4Orchestrator.run` 0 calls, `RouteStage.run` 0 calls, `assemble_pathfinding_result` 1 call returning `None`. |
| **What does its absence cost?** | **At most 4 nets of the 39 stuck (17 of 83 ratsnest edges); realistically 3.** Only 3 of the 4 were shown recoverable at all, and **every measured way of collecting them cost more nets than it won**. 32 of the 39 are foreign-creepage-halo blocked, which rip-up cannot touch. |
| **Could net ordering substitute?** | **No — measured, and it is zero-sum.** Two order permutations rescued 3 and 2 of the victims and broke 9 and 6 other nets respectively; in both, the demoted *blockers* (`cs_n`, `sdi`) became the new victims. Fully-connected nets went 79 → 74 and 79 → 75. |

## 1. Provenance and controls

Controls, run before anything was concluded.

| control | measured at | expected | **this session** |
|---|---|---|---|
| committed placement, routed | `fd4e73644` (flat-12.6 route-time creepage) | `697bad89…`, 4907 seg / 149 vias / 152 zones | **`697bad8936b3e16ed5168dfe113aead82c2ca93152a345e10df663883c30f370`, 4907 / 149 / 152** |
| model-E placement written to a board | `bc3a19b06` | `bf9dde9a8d15a2bb…` | **`bf9dde9a8d15a2bb4b0a6126e5ee318fe5e7b34a0e36b5cc1c17e6a620f4bc01`** |
| row-E solve | `bc3a19b06` | `optimal`, 168 placed, T1+T2 relaxed | **`optimal`, 168 placed, 39.1 s** |
| `pcb/temper.kicad_pcb` sha256 before / after | both | `26981fea…c110b` | **identical, both** |

**The instrumentation is proven non-perturbing** by the first row: with every
probe attached, the committed board comes back with the published counters
*and* byte-identical content. That control was taken at `fd4e73644` — the
base this branch started from, before it was moved forward to `bc3a19b06` to
obtain the per-pairing placer needed for the model-E solve. The router core
is byte-identical across both.

*(Note on a published digest: the residual-connectivity diagnosis — branch
`agent/residual-connectivity-diagnosis`, commit `f0ef0e089`, not merged and
so not a path in this tree — quotes this board as `697bad8936b3e16d…`; the
actual 16-hex prefix is `697bad8936b3e16e`. The full digest is above. All
three counters match exactly, so this is a transcription slip in that
document, not a divergence.)*

### 1a. One control does **not** reproduce, and the reason is a real finding

The model-E **route** does not reproduce the published `af99bd04…` /
5912 / 186 / 124 at this base. It gives **`128d5c3202c583ff…`, 6166 / 194 /
96** — *more* copper, not less.

The cause is not the router. `bc3a19b06` replaces the route-time pair-creepage
table with the per-pairing figures:
`packages/temper-placer/configs/pair_creepage.generated.yaml` changes from a
**flat 12.6 mm** for every listed pair to **4.8 mm** for the `ACMains|*`
pairs and **8.0 / 20.0 mm** for the `*|HighVoltage*` pairs
(and `zone_pour_creepage.generated.yaml` likewise). Those numbers are the
radii `_astar_nlayer`'s halos and stamps are built from, so the routed result
is expected to move. The published 36-net / 7-net figures belong to the
**flat-12.6 route-time table** (the `fd4e73644` half of
`docs/evidence/2026-08-19-per-pairing-placement-routed.md` §3), not to this
tip.

**Direct confirmation.** Routing the *committed* placement at `bc3a19b06`
collapses it: **758 segments / 52 vias / 73 zones, 11 of 105 nets routed**
(vs 4907 / 149 / 152 and 34 routed at `fd4e73644`). The per-pairing table
raises `*|HighVoltage*` creepage from 12.6 mm to **20.0 mm**, which the
non-compliant committed placement cannot absorb — while the compliant
model-E placement routes *better* under it (6166 / 194, 61 routed). That is
strong independent evidence for the compliant placement, and it settles that
the discrepancy is the creepage table, not the harness.

**The published population is reconciled net-by-net, not waved away** — see
§3a. Nothing in this document depends on which table is in force: the rip-up
counters are **0 in all five routes**, across both tables and both
placements, and the blocked-by-earlier-copper population is the *same named
nets* in both.

## 2. Q1 — does rip-up run? [measured, instrumented production route]

Two full `route_board.route_once` runs — the same call the default recipe
makes — under observe-only monkeypatches that count calls and record
arguments. Both boards were routed from scratch (existing copper stripped,
as `route_once` does by default).

### 2a. The counters [measured]

| counter | committed placement (@`fd4e73644`) | model-E placement (@`bc3a19b06`) |
|---|---:|---:|
| `run_astar_pathfinding_nlayer` entered | **1** | **1** |
| `_astar_reconstruct.run_astar_pathfinding` entered | **0** | **0** |
| `astar_pathfinding.run_astar_pathfinding` entered (the *other* binding — see 2c) | — | **0** |
| `Stage4Orchestrator.run` | — | **0** |
| `RouteStage.run` (the stage that would call the rip-up router) | — | **0** |
| `assemble_pathfinding_result` calls / non-`None` returns | — | **1 / 0** |
| `_mark_route_blocked` (copper **stamped**) | 306 | 549 |
| **`_unmark_route_blocked` (copper ripped up)** | **0** | **0** |
| `_identify_blocking_nets` (the rip-up trigger) | 70 | 43 |
| paths returned with `forced_segment_count > 0` | 70 | 43 |
| `_allow_forced_segments()` returning True | **0 / 105** | **0 / 105** |
| nets attempted more than once | **0** | **0** |
| distinct `attempted_ripups` values across all failure reports | `[0]` | `[0]` |
| failures with `failure_reason == "rip_up_limit"` | 0 | 0 |
| rip-up / reroute / unmark symbols visible in `_astar_nlayer`'s namespace | **`[]`** | **`[]`** |

Three further full routes read the same. The two ordering variants of §3b:
`unmark_calls` 0 / 0, `retried_nets` 0 / 0, `attempted_ripups` `[0]` / `[0]`,
`identify_blocking_nets` 49 / 47. The committed placement re-routed at
`bc3a19b06` (§1a's collapsed 758-segment run, the most congested state
measured): `unmark_calls` **0**, `retried_nets` **0**, `attempted_ripups`
`[0]`, `identify_blocking_nets` **94** — i.e. the rip-up trigger fired on
almost every net and still nothing was ripped.
**Five routes, zero rip-ups.**

*Positive control for the stage-4 probes:* `Stage4Orchestrator.run` and
`RouteStage.run` register nothing, but `assemble_pathfinding_result` —
patched in the same block, on the same class — registers **1 call**. The
patches were live; the two methods simply were never called.

The last row is the whole finding in one line. `_astar_reconstruct`,
`_astar_search` and `astar_pathfinding` each expose
`_astar_route_with_ripup` and `_MAX_REROUTE_ATTEMPTS_PER_NET`;
`_astar_nlayer` — the module that actually routes this board — exposes
none of them and does not import `_unmark_route_blocked` at all.

### 2b. Absent, not unreported — and the decision *is* computed first

`_astar_nlayer.attempt_route` does compute a rip-up list
(`_astar_nlayer.py:1417-1423`):

```python
ripped_ids: list[int] = []
if route_path and route_path.forced_segment_count > 0:
    blockers = _identify_blocking_nets(channel_path, list(active_grids.values()))
    if blockers:
        ripped_ids = sorted(blockers)
blocker_names = [id_to_net.get(rid, f"Unknown-{rid}") for rid in ripped_ids]
blocker_history.setdefault(net_name, set()).update(blocker_names)
```

…and then never acts on it. Nine lines later the same `forced_segment_count
> 0` condition returns `_forced_segment_decline(...)`. `ripped_ids` reaches
exactly one consumer: `blocker_history`, which is copied into
`RoutingFailureReport.blocking_nets` — a diagnostic list.

| | committed | model-E |
|---|---:|---:|
| `_identify_blocking_nets` calls | 70 | 43 |
| …returning a **non-empty** blocker set (a non-empty `ripped_ids`, built and dropped) | **66** | **31** |
| failure reports carrying `blocking_nets` | 66 | 31 |
| distinct nets nominated for rip-up | **33** | **59** |
| nominated nets that were routed at that moment | **33 / 33** | **59 / 59** |
| `_unmark_route_blocked` calls | **0** | **0** |

On the committed board `PWM_LS` was nominated 52 times, `i2c_scl_ui` and
`safety-line-3` 51 each. **The router identifies precisely what to rip,
records it in a report, and rips nothing.**

**This is the "absent vs merely unreported" answer the brief asked for.**
`attempted_ripups=0` is not a dropped counter — there is nothing to count.
The single `for net_name in routable_nets:` loop at `_astar_nlayer.py:1495`
visits each net once; there is no `reroute_queue`, no `while` drain, no
`del routed_paths[...]`, and no un-stamp. Measured confirmation: 0 of 105
nets were handed to `_astar_route_nlayer` more than once.

By contrast `_astar_reconstruct` has the complete mechanism — un-stamp
(`:433`/`:445`), `del routed_paths[ripped_name]`, `reroute_queue.append`,
`ripup_counts[...] += 1` (`:420-455`), a bounded drain
(`:583-598`, `len(routable_nets) * _MAX_REROUTE_ATTEMPTS_PER_NET`), and an
honest `"rip_up_limit"` failure reason for exhaustion. Its
`attempted_ripups=ripup_counts.get(net_name, 0)` at `:541` is a real
counter. **It is entered zero times.**

### 2c. Why the rip-up-capable path never runs — two independent reasons

1. **Layer count.** `_pipeline_route.py:936` sets
   `use_nlayer = self.enable_nlayer_astar_spike or len(available_grids) > 2`.
   This board offers 4 routable signal layers, so `use_nlayer` is True
   regardless of the flag (which is `False` by `route_once`'s default), and
   the `elif pathfinding_result is None:` legacy branch at `:976` is never
   taken. Measured: nlayer entered 1, legacy entered 0.

2. **A stage chain that is built but never run.** Before that branch,
   `_pipeline_route._run_stage4` constructs the orchestrated pipeline whose
   `RouteStage` docstring is literally *"Route nets using A* pathfinding with
   ripup capability"*:

   ```python
   orchestrated = Stage4Orchestrator(verbose=self.verbose)
   state = BoardState(...)
   pathfinding_result = orchestrated.assemble_pathfinding_result(state)
   ```

   `orchestrated.run(state)` is never called. `assemble_pathfinding_result`
   is a `@staticmethod` whose entire body is
   `return getattr(state, "pathfinding_result", None)`, and `state` was
   constructed three lines earlier without that field — so it returns `None`
   **by construction**, which is exactly what makes the nlayer branch below
   fire. Measured: `Stage4Orchestrator.run` 0, `RouteStage.run` 0,
   `assemble_pathfinding_result` 1 call, `None` returned.

**Instrumentation note (a real trap).** `RouteStage.run` and
`_pipeline_route._run_stage4` both resolve the legacy router as
`from ...astar_pathfinding import run_astar_pathfinding` — a *separate*
module-level binding created when `astar_pathfinding` imported it from
`_astar_reconstruct`. Patching only `_astar_reconstruct.run_astar_pathfinding`
(as earlier harnesses did) would report `legacy_entered=0` even if the legacy
rip-up router had run. This document patches **both** bindings plus
`RouteStage.run` and `Stage4Orchestrator.run`; all four read zero.

## 3. Q2 — what the absence costs [measured]

### 3a. The population rip-up would target, and its reconciliation with the published 7

On the model-E placement, **39** multi-pad nets end with zero segment/via
copper *and* zero zone (**83** ratsnest edges). Their verdicts, sampled live
between `_unblock_net_pads` and `_stamp_foreign_creepage_halos` and restricted
to each pad's own layer — the same rule the residual-connectivity diagnosis's
analyzer uses (branch `agent/residual-connectivity-diagnosis`, `f0ef0e089`),
so the buckets are directly comparable:

| verdict | nets | share |
|---|---:|---:|
| own pad inside a **foreign creepage halo** | **32** | 82 % |
| own pad under an **already-routed net's copper stamp** | **4** | 10 % |
| endpoints free — the search genuinely lost | 3 | 8 % |

The 4 are `sdo`, `sclk`, `vcc` and `hb.gate_hs.driver-p2`, together
**17 of the 83 edges**:

| stuck net | edges | routed too late at order# | claimed by (order#) |
|---|---:|---:|---|
| `sdo` | 1 | 18 | `cs_n` (2) |
| `sclk` | 1 | 21 | `sdi` (15) |
| `vcc` | 12 | 88 | `bias` (34), `i2c_scl_ui` (17), `safety.coil_thermal-line` (24), `discharge.q_dis_drv-g` (37) |
| `hb.gate_hs.driver-p2` | 3 | 97 | `GATE_HS` (45) |

**Reconciliation with the published 7** (`discharge.k_dis1-coil1`,
`discharge.k_dis1-coil2`, `discharge.k_dis2-coil1`, `hb.gate_hs.driver-p2`,
`sclk`, `sdo`, `vcc`): my 4 are a strict subset, and the missing 3 are
accounted for exactly, not lost. Under the per-pairing table all three
`discharge.*` nets are *still stuck* — they simply changed bucket, because the
halo verdict takes precedence over the stamp verdict when both apply:

```
discharge.k_dis1-coil1   HALO    own-layer cells: 2 free, 4 halo
discharge.k_dis1-coil2   HALO    own-layer cells: 2 free, 8 halo, 1 stamped (discharge.q_dis_drv-g)
discharge.k_dis2-coil1   HALO    own-layer cells: 1 free, 4 halo, 1 stamped (discharge.q_dis_drv-g)
```

Two of them still carry a stamped pad cell. **Same nets, same mechanism, a
stricter creepage requirement now dominating.** The 7 did not shrink to 4
because the router improved; it shrank because precedence reassigned three
nets to a bucket rip-up cannot help either way.

### 3b. The cost, bounded by execution

The bound comes from two full re-routes that change **net order only** —
every clearance, creepage and fail-closed gate identical, `_allow_forced_segments`
still 0/105 True in both. The orderings are *oracle-informed* (they use the
control run's own blocker attribution), so they are a **measuring instrument,
not a proposed policy**.

| run | routed | segments | vias | fully pad-connected | zero-copper nets | ratsnest edges |
|---|---:|---:|---:|---:|---:|---:|
| **control** | 61 | 6166 | 194 | **79** | **39** | **83** |
| **V1** — the 4 victims promoted to the very front | 55 | 5477 | 156 | 74 | 45 | 93 |
| **V2** — each victim moved just before its earliest blocker | 57 | 5715 | 188 | 75 | 43 | 94 |

**Upper bound: 3 nets / 14 edges.** V1 rescued `sclk`, `sdo` and `vcc` — so
their block genuinely *is* order-dependent, and a working rip-up-and-reroute
is the mechanism that could claim them. V2 rescued `sclk` and `sdo`.

**`hb.gate_hs.driver-p2` is not recoverable this way.** It stayed
zero-copper in *both* variants, including when it routed first on a nearly
empty board. Its pad is under `GATE_HS`'s stamp, but removing that copper is
not sufficient — so 1 of the 4 is misattributed to ordering and is really a
geometry failure.

**Realistic bound: 0–3 nets, and every measured route of it was net-negative.**
Both variants cost more than they won: V1 −5 fully-connected nets, +10 edges;
V2 −4 and +11. In both, the *blockers themselves became victims* — `cs_n` and
`sdi` appear in the newly-stuck set of both runs, and in V1 `cs_n`, `sdi` and
`refin_n` form the entire new stamp bucket. That is the signature of a
congestion-limited board rather than an order-limited one: freeing a pad cell
does not create capacity, it moves the shortage.

**Set against the whole residual, rip-up is worth at most 4 of 39 stuck nets
(10 %), realistically 3 (8 %), and 32 of 39 (82 %) are blocked by a foreign
creepage halo that no rip-up can dissolve** — the halo *is* the clearance
requirement, and ripping the net that owns it just moves the same halo
somewhere else.

## 4. Q3 — is net ordering doing the work rip-up would? [measured]

**No — and this is the outcome the brief hoped for, measured and found false.**
Ordering does not dissolve the self-block; it relocates it.

### 4a. What the live ordering actually orders by

The production ordering call is `_astar_nlayer.py:1207`:

```python
net_order = _compute_net_order(channel_mapping)
```

The *call site* is `_astar_nlayer.py:1207`, but the *implementation* is
`_astar_ordering._compute_net_order`, imported at `_astar_nlayer.py:125`.
`_astar_ordering.py` is therefore very much live; what is dead is
`_astar_reconstruct.py:171`, the other call site. The live call passes
**one** argument, so `bottleneck_widths` defaults to `None`, and the key
reduces to:

* build a conflict graph over waypoint bounding boxes (overlap / smaller
  area > 0.1), take connected components;
* **within** a cluster sort by `(bbox_area ascending, not is_power)` —
  smallest footprint first, power nets a tiebreaker only;
* **between** clusters sort by `(-len(cluster), total area)` — largest
  cluster first.

So the live order is essentially *smallest-bounding-box-first*, and it is
blind to congestion, to pad contention and to net width. The consequence is
visible in §3a's table: `vcc` — 13 pads, 12 edges, the single largest loss in
the residual — lands at position **88 of 105**, behind all four nets that end
up claiming its pads, and `hb.gate_hs.driver-p2` lands at **97**. Both are
wide-footprint nets, which this key sorts last within their cluster.

Two secondary observations, recorded but **not** acted on:

* The `bottleneck_widths` term — whose docstring describes exactly the
  mechanism at issue ("nets with the narrowest routing corridors … must be
  routed before competitors claim their only viable path") — is **dormant on
  every path**, not just this one. `_astar_reconstruct.py:171` forwards it,
  but no production caller ever supplies it, so it is `None` there too.
* `_compute_net_order`'s docstring says "Route isolated clusters first, then
  largest clusters"; the code sorts `-len(c)` first, i.e. largest clusters
  first. Doc/code disagreement, effect unmeasured.

### 4b. Reordering was measured, and it is zero-sum

§3b's two variants are the test. Even the *minimal* perturbation (V2: move
each victim to immediately before its earliest blocker, leaving the rest of
the order untouched) rescued 2 nets and broke 6:

```
V2 rescued     : sclk, sdo
V2 newly stuck : cs_n, sdi, s1, WDT_RESET_N,
                 safety.uvlo_logic-line, safety.uvlo_logic.mon-outa
```

`cs_n` and `sdi` are precisely the two blockers that were demoted. **The
conflict did not dissolve; the pair swapped roles.** V1 shows the same
signature more strongly (3 rescued, 9 broken, and the new stamp bucket is
`cs_n`, `sdi`, `refin_n`).

**This is the structural difference between reordering and rip-up.**
Reordering decides *once* who loses a contested cell. Rip-up gives the loser
a second search on a grid that has changed — which is why it can, in
principle, keep both nets where reordering cannot. Nothing measured here
promises it *would*; §3b's V1/V2 evidence that displaced blockers fail to
re-route is the honest counter-indication, and it is the single most
important input to any decision to build rip-up.

**Recommendation: do not ship an ordering change on this evidence.** Every
ordering permutation tried was net-negative on the board-level metric. If
ordering is revisited, the measurable question is not "which nets first" but
whether the *dormant* `bottleneck_widths` term is worth wiring up — and that
must be measured on a full route before it is believed, because the
`(bbox_area, not is_power)` key it would replace is currently load-bearing
for 61 successfully routed nets.

## 5. Q4 — the fail-closed policy, and what a safe rip-up would need

### 5a. The fail-closed policy is *not* what makes rip-up inert here

The earlier reading — recorded in `_astar_nlayer.py:99-109` and repeated in
`agent/residual-connectivity-diagnosis` — is that
`_allow_forced_segments() → False` makes `_astar_route_with_ripup`'s
`ripped_ids` "always `[]`", so rip-up is *dead code under today's policy*
and would revive if the policy were made conditional again. **Measurement
does not support the premise, and the conclusion is weaker than the truth.**

* The premise is false: with `allow_forced_segments=False` on every one of
  105 nets, `_astar_route_nlayer` still returned **43 paths (model-E) / 70
  paths (committed) with `forced_segment_count > 0`**, `_identify_blocking_nets`
  ran on every one of them, and it returned a **non-empty** blocker set 66
  times on the committed board. `ripped_ids` is emphatically not always `[]`.
* The conclusion is too weak: making `_allow_forced_segments` conditional
  again would **not** revive rip-up on this board, because the production
  module has no rip-up loop to revive. It would only start writing
  clearance-unchecked forced copper — the exact regression
  `docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md` closed.

So: **the fail-closed policy is not the blocker — the missing reroute loop
is.** That distinction matters, because "relax the policy and rip-up comes
back" is a tempting fix that is both unsafe and ineffective.

### 5b. What a safe rip-up in `_astar_nlayer` would have to satisfy

Not proposed here — priced, so that whoever takes it starts from the real
constraints rather than from `_astar_reconstruct`'s two-layer version.

1. **Un-stamp symmetry across width/creepage families.** `_astar_nlayer.py:
   1455-1467` stamps a routed net into **every** family at that family's own
   radius, `max(net_rule.clearance_mm, fam_c, pair_creepage) + fam_w/2`, with
   the net's real `via_diameter_mm`. A rip-up must unstamp with the identical
   per-family radii or it leaves a stale halo — the invariant
   `clearance_floor.py:168-171` states outright ("mark and unmark have to
   agree or ripup leaves a stale footprint behind"). Today's
   `_unmark_route_blocked` takes a *single* `(trace_width, clearance)` pair.
   `profile_grids.ProfileGrids.unmark_route` is the existing per-family
   analogue, but it is built for the legacy two-layer path and does not carry
   `via_diameter`.
2. **Via un-stamping is asymmetric today.** `_mark_route_blocked` stamps vias
   at the net's real `via_diameter` (0.8–1.2 mm on this board);
   `_unmark_route_blocked` un-stamps them at a hardcoded `0.6`
   (`astar_grid.py:353`). Reusing it as-is guarantees a stale via ring.
3. **Un-stamping vias can erase *static* obstacles.** `unmark_segment_blocked`
   consults `static_mask`; `unmark_path` — which `_unmark_route_blocked` uses
   for vias, on **all** layers — explicitly does not
   (`occupancy_grid.py:245-248`, a documented pre-migration asymmetry). A
   naive rip-up could therefore free cells that were board edge, drill or HV
   keepout, making a later route look legal when it is not. **On a mains
   board that is the failure mode that matters**, and it is the reason a
   rip-up must not be ported from the legacy path unexamined.
4. **The re-route must re-clear every constraint the original did.** This one
   is free if 1–3 are right: a re-routed net goes back through the same
   `attempt_route`, so it re-derives its family, its `pair_creepage` (including
   the two indeterminate pairings held at their proven floors of **20.0** and
   **8.0 mm**) and the same fail-closed forced-segment gate. The risk is not
   the re-route; it is the grid state the re-route sees.
5. **Termination and honest reporting already exist** in the legacy path and
   are reusable: `_MAX_REROUTE_ATTEMPTS_PER_NET`, the bounded drain, and the
   `"rip_up_limit"` failure reason with `rule_id=None` so `attribution_gap`
   derives True.

## 6. What this rules out

* **Not "rip-up is inert under the fail-closed policy."** The policy is not
  what stops it (§5a). The production module has no rip-up to be inert.
* **Not "`attempted_ripups=0` is a reporting bug."** It is the honest value:
  0 un-stamps, 0 retries, 0 `rip_up_limit` failures, in five full routes.
* **Not "the legacy path would fix it if we could reach it."** It would be
  reachable only through a stage chain that is constructed and never run
  (§2c), and porting its `_unmark_route_blocked` unexamined would erase
  static obstacles on via cells (§5b.3).
* **Not "better net ordering dissolves the bucket."** Measured net-negative,
  twice (§4b).
* **Not "this is where the residual is."** The order-dependent self-block is
  10 % of the stuck nets. **82 % is the foreign creepage halo**, which is a
  clearance requirement, not a router defect — and the brief's own prohibition
  says so: a net that only routes when a creepage is relaxed *is* the finding.
* **What it does leave open:** whether a *correctly built* rip-up (§5b) could
  keep both the victim and the re-routed blocker where reordering cannot.
  That is the only claim in this area still worth spending a full route on,
  and §3b's displaced-blocker failures argue it will be small.

## 7. An environment hazard: a fresh, importable extension that is still wrong

The prior diagnosis recorded that `check_stale_extensions.py` can report a
crate **fresh** while it is unimportable, and recommended import-smoke-testing
all 10 modules. **That is necessary but not sufficient, and this session hit
the stronger failure.**

After changing the checked-out base, `check_stale_extensions.py` reported
`PASSED -- 10/10 extension module(s) fresh` and all 10 modules
**imported cleanly** — yet the first per-pairing solve died with:

```
AttributeError: module 'temper_design_bundle_python' has no attribute
'resolve_insulation_declaration'
```

The `.so` was newer than every source file (so the mtime gate passed) and
loaded fine (so an import smoke test passed), but it had been built from the
*previous* base and simply did not contain the symbol the newly-checked-out
Python calls. `make extensions` fixed it.

**Rule that follows:** freshness by timestamp and loadability by import are
both blind to a *stale-but-valid* binary. After any base change, rebuild
extensions unconditionally and re-verify against a known digest — which is
what §1's controls do. A symbol-presence check (not just an import) would
close the residual gap in `check_stale_extensions.py`.

## 8. Reproduce

```bash
# Base: agent/ripup-production-path (branched from bc3a19b06). The A* core is
# byte-identical to origin/main; only the 4 backbone/zone files and the
# per-pairing creepage tables differ.
env -u CONDA_PREFIX make venv-isolate
env -u CONDA_PREFIX make extensions            # MANDATORY after any base change, see Sec 7
.venv/bin/python scripts/check_stale_extensions.py            # 10/10 -- necessary, not sufficient
.venv/bin/python docs/evidence/2026-08-20-ripup-extension-smoke.py   # 10/10 loadable

# committed placement. At THIS base (per-pairing creepage) it gives
# 2b0d3610... / 758 seg / 52 vias / 73 zones -- see Sec 1a. The non-perturbation
# control (697bad8936b3e16ed516... / 4907/149/152) is this same command run at
# fd4e73644, i.e. `git checkout fd4e73644 && make extensions` first.
.venv/bin/python docs/evidence/2026-08-20-ripup-probe.py \
    --repo "$PWD" --out /tmp/trace_c.json --board-out /tmp/routed_c.kicad_pcb
.venv/bin/python docs/evidence/2026-08-20-ripup-analyze.py \
    --trace /tmp/trace_c.json --board /tmp/routed_c.kicad_pcb --repo "$PWD" \
    --label committed --emit /tmp/an_c.json

# model-E placement board -- must be bf9dde9a8d15a2bb...
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-solve-model-e.py \
    --rows E --emit /tmp/placement_E.json
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-apply-placement.py \
    --placement /tmp/placement_E.json --output /tmp/board_E.kicad_pcb

# model-E control, then the two ordering variants
.venv/bin/python docs/evidence/2026-08-20-ripup-probe.py --repo "$PWD" \
    --pcb /tmp/board_E.kicad_pcb --out /tmp/trace_E.json --board-out /tmp/routed_E.kicad_pcb
.venv/bin/python docs/evidence/2026-08-20-ripup-analyze.py --trace /tmp/trace_E.json \
    --board /tmp/routed_E.kicad_pcb --repo "$PWD" --label model-E --emit /tmp/an_E.json
.venv/bin/python docs/evidence/2026-08-20-ripup-mkreorder.py /tmp/an_E.json /tmp
.venv/bin/python docs/evidence/2026-08-20-ripup-probe.py --repo "$PWD" \
    --pcb /tmp/board_E.kicad_pcb --reorder /tmp/reorder_promote.json \
    --out /tmp/trace_Ep.json --board-out /tmp/routed_Ep.kicad_pcb
.venv/bin/python docs/evidence/2026-08-20-ripup-probe.py --repo "$PWD" \
    --pcb /tmp/board_E.kicad_pcb --reorder /tmp/reorder_before.json \
    --out /tmp/trace_Eb.json --board-out /tmp/routed_Eb.kicad_pcb

# per-net verdict for any named net, same rule as the analyzer
.venv/bin/python docs/evidence/2026-08-20-ripup-verdict.py /tmp/trace_E.json sclk sdo vcc
```

Each route is ~170–215 s. `--reorder` is the only knob that changes
behaviour; omitting it reproduces the production route exactly.

## 9. Hard-rule compliance

* `pcb/temper.kicad_pcb` never opened for writing; sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
  before the first command and after the last. Every board written by this
  task went to a scratch path outside the repo.
* **No clearance, creepage, copper-weight, loop-area, ampacity, annular-ring,
  drill or DRU threshold was changed, and no net was made to route by
  weakening a check.** The one behaviour-changing knob used
  (`--reorder`) permutes *net order only*; every net still faces the identical
  clearance, creepage and forced-segment gates, and the fail-closed
  `_allow_forced_segments() → False` was measured at 0/105 True in every run.
* The two indeterminate pairings stay at their proven floors of **20.0** and
  **8.0 mm**; §5b's requirements are stated in terms of preserving them, and
  every verdict that touches them remains CONDITIONAL.
* No check weakened: no test skipped, `xfail`ed, deleted or relaxed; no
  ratchet raised; no allowlist broadened; no `continue-on-error`, `|| true`,
  `# type: ignore` or `# noqa` added. **No production code changed at all.**
* `power_pcb_dataset/drc_ceiling.json` untouched and not re-baselined.
* No `_*_py_oracle.py` deleted, consolidated or re-pinned; the Rust A* kernel
  was not touched. §5b deliberately places any future rip-up at the Python
  call site for this reason.
* `git stash` not used; no pushed history rewritten; no `gh pr merge --admin`.
* The probe is additive and observe-only; with `--reorder` omitted it
  reproduces the unmodified production route byte-for-byte (§1).
