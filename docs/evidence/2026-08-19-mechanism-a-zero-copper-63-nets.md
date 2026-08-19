<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false -->

# Mechanism A: why A* emits nothing for 63 nets (127 ratsnest edges)

**Date:** 2026-08-19. **Base:** `origin/main` @ `eb5022510d8f1272adf0a27d76c849aa2bb6e210`.
Worktree `.claude/worktrees/agent-a5c5c155cec61da0a`, branch
`worktree-agent-a5c5c155cec61da0a`.
`pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
verified **before and after** every measurement. **The board was never
opened for writing.** Env: `make venv-isolate` in this worktree
(`unset CONDA_PREFIX`), all 10 pyo3 crates rebuilt.

Harness committed alongside: `2026-08-19-mechanism-a-instrument-route.py`
(observe-only monkeypatches over the production `route_board.route_once`
call) and `2026-08-19-mechanism-a-analyze.py`.

Every claim below is labelled **[measured]** (it came out of a real
production route) or **[read]** (source reading only, not yet executed).

---

## Headline

**Nothing declines these 63 nets by policy. 55 of them fail, and 8 of
them succeed and are then thrown away.**

| bucket | nets | edges | what actually happened |
|---|---:|---:|---|
| **fail — A\* declined on hop 0**, no geometry ever computed | **55** | **104** | no tier resolved even the first pad-to-pad hop |
| **succeed-then-discard — partial** | **7** | **21** | A\* resolved 1–3 hops cleanly; a later hop declined; the router discarded *the whole net*, including the hops it had already solved |
| **succeed-then-discard — complete** | **1** | **2** | `RTD_HW_FAULT`: both hops resolved at Tier 1, `forced_segment_count == 0` — a **finished route** — discarded by the pad-layer landing check |
| **decline by policy (`_should_route`)** | **0** | **0** | none; all 8 `_should_route` exclusions carry a zone and are therefore outside this 63 |

**The common property is real and it is not a router property.** For
**50 of the 63**, at least one of the net's **own pads is unreachable on
the pad's own layer** because it sits inside a *foreign* net's required
creepage distance. Measured live, inside the run, between
`_unblock_net_pads` (which frees the pad) and
`_stamp_foreign_creepage_halos` (which blocks it again): **182 of the 498
own-layer pad cells belonging to declined nets are freed and then
re-blocked by a foreign creepage halo — 36.5%.** Those pads sit
1.3–13.8 mm from the offending foreign copper, against a stamped halo
radius of 12.9–17.1 mm (the DRC-graded PD3 figure for every HV↔LV class
pair is **12.6 mm**, plus the searching net's own width/clearance
erosion).

This is the routing-side manifestation of the placement defect
`docs/evidence/2026-08-18-pour-only-nets-placement-diagnosis.md` §3b
measured from the other direction ("152 of 420 SELV pads currently sit
inside the 12.6mm HV halo"). Two independent measurements, one on static
placement geometry and one inside the router's live C-space, land on the
same cause.

**`tank-out` is fully explained.** Both of its pads are inside foreign
halos on every layer; the A\* kernel rejects both endpoints after **1
iteration**, eight times; Tier 3 rejects the segment in 5.6 ms without
searching. It has zero zones for a *separate* reason (§6).

---

## 0. What the instrumented run proves about the path itself

**[measured]** Three full routes of the production board through
`scripts/route_board.py`'s default recipe (`route_once`, no net-batching,
no pruning, `enable_nlayer_astar_spike=False`), with observe-only
patches. All three reproduce the established baseline **bit-for-bit**:
the written board's sha256 is
`6d4e17337bcf2633fb256f3da4d6fe981c91123827eff715a2c8aa870d195981` on
every run, i.e. exactly the briefed baseline digest. The instrumentation
is observe-only and this is the real production route, not a
reconstruction of it.

```
segments=4553  vias=169  zones=151     wall 219.0s / 218.8s / 216.7s
routed_paths=34  failed_nets=71  partial_paths=10
tier_tally = primary_2d 26, alternate_2d 30, nlayer_via_3d 0,
             declined 70, nlayer_via_3d_calls 70, attempts 126
run_astar_pathfinding_nlayer entered: 1
_astar_reconstruct.run_astar_pathfinding entered: 0
```

* `_astar_nlayer.py` is the production path, entered exactly once;
  `_astar_reconstruct.run_astar_pathfinding` is **never entered**.
  Confirms the brief's premise by execution, not by grep.
* The instrumentation is non-perturbing: identical copper, identical
  tier tally across runs.
* Grids handed to A\*: `['B.Cu', 'F.Cu', 'In3.Cu', 'In4.Cu']`.
  `channel_paths=112`, `net_order=112`, `routable=105`,
  `excluded_by_should_route=7` (of the mapped 112).

**Nothing is filtered away upstream.** All 112 nets with ≥2 pads get a
channel path, all 112 enter `_compute_net_order`, and every one of the
105 that `_should_route` admits reaches `_astar_route_nlayer` with ≥2
waypoints. There is no batching, grid-selection or `validator_input`
step that silently drops a net. **[measured]**

---

## 1. The 63, exactly

**[measured]** `pad_connectivity_audit.audit_pcb_file` on this run's own
output: 112 nets with ≥2 pads; 39 carry segment/via copper; 33 are fully
pad-connected; **73 have no segment/via copper at all**, of which **63
also have no zone** — contributing **127** ratsnest edges
(`Σ (pad_count − 1)`). This reproduces the briefed 63/127 exactly.

The 10 zero-copper nets that *do* carry a zone, and are therefore outside
the 63: `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `ac_n`,
`hb-gnd`, `power_in.ntc-no` (all seven excluded from A\* by
`_should_route`), plus `tank.c_tank1-p2`, `w1_1`, `w1_2` (A\*-attempted
*and* poured — the name-classifier gap already recorded in the 2026-08-18
doc §1).

Netclass census of the 63: `Default` 37, `FinePitch` 10,
`HighVoltage` 5, `Power` 5, `HighVoltageSignal` 4,
`HighVoltageIsolated` 2. Pad counts: 2 pads ×23, 3 ×23, 4 ×13, 5 ×2,
6 ×1, 7 ×1. **No netclass, pin-count or layer property partitions the
set** — the shared cause is geometric, not categorical.

---

## 2. Decline vs fail vs discard — the answer

`_astar_route_nlayer` runs the four-tier cascade per waypoint hop and
records exactly one `SegmentTier` per hop. Under production policy
(`_allow_forced_segments` is unconditionally `False`), the first hop no
tier resolves causes an **immediate return** of a `RoutePath3D` carrying
`forced_segment_count = 1`; `attempt_route` then returns
`_forced_segment_decline(...)` and **the entire net's geometry is
dropped** (kept only in `partial_paths`, which the writer never reads).
**[read: `_astar_nlayer.py:557-570` (the fail-closed early return), `1436-1440` (the net-level discard); measured: below]**

**[measured]** Per-net tier logs for the 70 declined nets:

* **61 nets** declined on hop 0 — the tier log is exactly `["declined"]`.
  Nothing was ever computed for them.
* **9 nets** declined on hop ≥ 1, after resolving earlier hops. Their
  discarded geometry:

| net | tier log | path points | vias | length mm | hops A\* had already solved |
|---|---|---:|---:|---:|---:|
| `I_SENSE` | primary,primary,alternate,**declined** | 1826 | 2 | 213.2 | 3 |
| `+3V3` | alternate,primary,**declined** | 1495 | 1 | 152.7 | 2 |
| `safety-line` | alternate,**declined** | 1347 | 2 | 151.4 | 1 |
| `ina` | alternate,**declined** | 1210 | 2 | 132.7 | 1 |
| `safety.thermal.comp-inp` | primary,**declined** | 415 | 0 | 47.7 | 1 |
| `en` | primary,**declined** | 296 | 0 | 32.3 | 1 |
| `io0` | primary,**declined** | 244 | 0 | 27.2 | 1 |
| `+15V` | primary,**declined** | 188 | 0 | 22.0 | 1 |
| `bias` | primary,**declined** | 7 | 0 | 0.6 | 1 |
| **total** | | **7028** | **7** | **≈780** | **12** |

* **1 net** — `RTD_HW_FAULT` — is a different shape again: tier log
  `["primary_2d", "primary_2d"]`, `forced_segment_count == 0`, 320 path
  points, a **completed** route. It was discarded by
  `_attempt_pad_layer_landing` (`failure_reason =
  pad_layer_landing_blocked:end`), which converts a net-level landing
  failure at one end into a whole-net decline.

Seven of the nine partial-discard nets and `RTD_HW_FAULT` end with
literally zero copper on the board — that is the **8 succeed-then-discard
nets / 23 edges** in the headline table. (`+15V` and `+3V3` are not in
the 63 because the In2.Cu power-island generator later gives them copper
by a different mechanism.)

**This is measured, not inferred:** the router computed 7348 path points
of real, clearance-respecting A\* geometry for those 8 nets, and the
written board contains zero segments for any of them.

---

## 3. Why the 55 fail: the endpoint is not free

**[measured]** Anatomy of the *declining* hop for all 70 declined nets,
Tier 1 (the preferred layer, searched in the net's own width family
grid):

| Tier-1 outcome on the declining hop | nets |
|---|---:|
| an endpoint grid cell was **already blocked** → the search could not have succeeded | **45 (64%)** |
| both endpoints free, search ran and lost | 25 (36%) |

Tier 2 (every other layer) on the same hop: **37 of 70** nets had **no
alternate layer** on which both endpoints were free. Tier 3
(`_route_segment_3d`, the N-layer via-aware 3D search): **70 calls, 0
successes**, 14.5 s of wall time; 19 of those calls returned in under
20 ms, i.e. rejected the endpoints without searching. Tier 3 resolved
**zero** segments in all three runs here; the `TierTally` docstring
records the same 0/70 from an independent 2026-08-18 measurement.

**[measured]** Iteration counts recovered by wrapping
`temper_rust_router.astar_kernel_3d_py`, which returns `(path, iters)`
that the Python front-end discards. Each `_segment_search` issues exactly
**two** kernel calls, because `enable_coarse_to_fine` is `True` in
production (`_pipeline_core.py:148`) and `_astar_route_nlayer` passes no
`net_id`, so `net_id == -1` and `_segment_search` always takes the
coarse-to-fine branch: phase 1 is a coarse search on the 4× downsampled
grid at the *default* 1,000,000 budget, phase 2 is either the
corridor-restricted fine search or the unrestricted fallback, both at the
net's own span-derived budget. **[measured — caller frames captured
live]** Phase 2 is the decisive one.

Phase 1 (coarse, n=376): corridor found 47, endpoints rejected 103,
searched and failed 226. The corridor phase is therefore doing almost
nothing — 87.5% of segments fall through to the unrestricted fallback.

Phase 2, the decisive search (n=376; `PATH FOUND` = 56 exactly reproduces
`tier_tally.resolved`, an independent check that the join is correct):

| decisive outcome | × endpoint state | all | of the 63 |
|---|---|---:|---:|
| path found | endpoints free | 55 | 11 |
| path found | an endpoint blocked | 1 | 0 |
| **miss, rejected after 1 iteration** | endpoint blocked | **103** | **78** |
| **miss, frontier exhausted** — provably no path | endpoint blocked | 56 | 42 |
| miss, frontier exhausted | endpoints free | 70 | 57 |
| miss, **budget** exhausted | endpoint blocked | 31 | 26 |
| miss, **budget** exhausted | endpoints free | **60** | **47** |

**Only 47 of the 261 decisive searches belonging to the 63 (18%) could
conceivably be changed by a larger budget** — those are the ones that hit
their iteration cap with *both* endpoints free. They touch 26 nets, and
every one of those nets has other hops that fail for a different reason.
The other 203 misses are geometry: 146 of them cannot succeed at any
budget because an endpoint cell is not free.

The grids are not globally full: the `Default`/`FinePitch` family
(64 + 13 nets, static erosion 0.30 mm) is **89.8% free on F.Cu and 92.9%
free on each inner layer**. The failure is local, at the pads.

---

## 4. Where the blocked endpoint comes from — the root cause

Per net, `attempt_route` does exactly three things to the grid before
searching: `_unblock_net_pads` (frees the net's own pad discs, static
`-1` cells only), then `_stamp_foreign_creepage_halos` (re-blocks every
*foreign* obstacle's halo over cells that are currently free), then
searches. **[read]**

**[measured]** Grid value at every one of the declined nets' own pad
centres, sampled immediately after each of those two calls, restricted to
the pad's **own layer** (the only layer the pad physically has copper on)
— 498 (pad, layer) cells over the 70 declined nets:

| own-layer pad cell state | cells | share |
|---|---:|---:|
| free after both steps — reachable | 250 | 50.2% |
| **free after `_unblock_net_pads`, then blocked by `_stamp_foreign_creepage_halos`** | **182** | **36.5%** |
| already claimed by an earlier-routed net's copper stamp (`net_id > 0`) | 60 | 12.0% |
| unresolvable (out of frame) | 6 | 1.2% |

`_stamp_foreign_creepage_halos` flipped cells `0 → −1` for **81 of the
105** routable nets, median 476 cells per net.

Per-net headline verdict over the 63:

| first matching cause | nets |
|---|---:|
| **own pad inside a foreign creepage halo** | **50** |
| A\* frontier exhausted — no path at this net's width/clearance | 12 |
| own pad under an already-routed net's copper stamp | 1 |

The router is behaving exactly as designed here. `_stamp_foreign_creepage_halos`'s
own docstring names this outcome: *"the routing net's own pads … stay
free unless a foreign halo genuinely covers them (in which case the
honest answer is that the pad cannot be reached)."* **This is a
fail-closed creepage verdict delivered at the pad.**

### 4a. Which halo, and how big

**[measured]** The stamped halo radius is
`family_static_inflation + pair_creepage(searching class, obstacle class)`
where `family_static_inflation = width/2 + max(clearance, 0.2)`. The
DRC-graded creepage table (`pair_creepage.default_creepage_table()`) is
**12.6 mm for every HV-class ↔ LV-class pair** (`HighVoltage`,
`HighVoltageSignal`, `HighVoltageTank`, `HighVoltageIsolated`, `ACMains`
against `Default`/`Signal`/`FinePitch`/`Power`/`GateDriveSELV`/`GND`),
and 10.0 mm tank↔tank. So an ordinary `Default` signal net (inflation
0.30 mm) has a **12.9 mm** halo stamped around every HV pad on the board.

Nearest foreign obstacles to the unreachable pads (centre-to-centre, a
lower bound — pads have extent):

```
sclk        pad (166.60,171.01)  2.44mm to safety.ovp.r_div_top1-p2 (HighVoltage), halo 12.9mm
input       pad ( 89.08,137.56)  1.27mm to +15V_LS (HighVoltageSignal) and hb-gnd (HighVoltage)
k_dis1-no   pad (137.32, 72.21)  5.04mm to PWR_RTN (HighVoltage)
r_snub2-p2  pad ( 42.14,112.95)  3.49mm to hb.power_loop.q_high-g (HighVoltageSignal)
tank-out    pad ( 36.10,124.48) 13.00mm to tank.c_tank1-p2 (HighVoltageTank), halo 14.5mm
tank-out    pad ( 46.36,141.23) 13.82mm to gnd (Power), halo 17.1mm
```

### 4b. The placement already violates this, before any copper exists

**[measured]** Over the 523 netted pads on the committed board, **187 pad
pairs are closer, centre-to-centre, than the creepage their two classes
require**, involving **74 distinct nets**. **44 of the 63** mechanism-A
nets are among them.

```
Default        <-> HighVoltage           71 pairs
HighVoltage    <-> Power                 52
Default        <-> HighVoltageSignal     18
Default        <-> HighVoltageIsolated   16
FinePitch      <-> HighVoltage           15
HighVoltageIsolated <-> Power             7
HighVoltageTank<-> Power                  3
HighVoltageSignal <-> Power               3
Default        <-> HighVoltageTank        2
```

Centre-to-centre is an *upper* bound on the real copper-to-copper gap, so
every count is a lower bound on the real violation count. This
independently reproduces, from the router's own netclass tables, the
placement finding in
`docs/evidence/2026-08-18-pour-only-nets-placement-diagnosis.md` §3a/§3b
("39 of 59 pads", "152 of 420 SELV pads inside the 12.6mm HV halo") and
extends it from the 9 pour-only nets to the 63 A\*-routed ones.

**No router change fixes this.** A net whose pad is inside another net's
required creepage can only be routed by violating that creepage.

---

## 5. `tank-out`, end to end

**[measured]**

* `_should_route("tank-out") == True` — not by design. Its netclass is
  `HighVoltage` with `routing_strategy = plane_required`, so
  `_zone_layers_for_net` grants it a pour; but `is_hv_net("tank-out")`
  returns **False** (name-classifier gap), so `_net_policy._should_route`
  never consults the pour gate and sends it to A\* as well.
* Family `(5.0, 2.0, 'HighVoltage')` → static erosion **4.5 mm**, leaving
  46.3% of F.Cu and 64.3% of each inner layer free.
* **0 of its 5 own-layer pad cells survive the foreign-halo stamp.** Both
  pads are inside foreign halos on every layer.
* A\* kernel: **8 invocations, every one returning after 1 iteration**
  (endpoints rejected). Tier 3: rejected in 5.6 ms.
* Tier log: `["declined"]` on hop 0. Zero copper.
* Zero zones for an unrelated reason — see §6.

---

## 6. Why `tank-out` also has zero *zones* (secondary, and it is not the 63's cause)

**[measured]** Exactly 5 of the 16 zone-eligible nets emit no zone:
`tank-out`, `safety.ovp.r_adc_top1-p2`, `r_adc_top2-p2`,
`r_div_top1-p2`, `r_div_top2-p2`. **All five have exactly 2 pads.**

`zone_emission._cluster_positions` returns a **single cluster for any net
with ≤2 pads** (`if len(positions) <= 2: return [list(positions)]`), so a
2-pad HV net gets one board-spanning hull — up to 134 mm across for
`r_adc_top1-p2` — regardless of pad separation. **[read + measured]**
`compute_zones_for_net` does produce that hull for all five
(reproduced directly). The zone is then lost inside the Rust
`pour_outline_py` PadsOnly carve at PD3 creepage, i.e. the same
"PD3-honest zone refusal" already named for three of these four OVP nets
in `docs/evidence/2026-08-16-capstone-final-route.md` §3.

This is why `tank-out` shows zero copper *and* zero zones; it is not why
the other 62 do.

---

## 7. What this rules out

**[measured, each of these was tested and is false]**

* Not upstream filtering. Every net with ≥2 pads reaches A\* with ≥2
  waypoints; `_should_route` removes nothing that lands in the 63.
* Not search budget. Only 47 of 261 decisive searches on these nets
  (18%) are budget-limited with reachable endpoints; the rest are
  geometry.
* Not global congestion. The Default family's grids are ~90% free.
* Not net ordering alone. Only 1 of the 63 fails because an
  earlier-routed net's stamp covers its pad (60 of 498 pad cells, but
  only one net where that is the *first* cause).
* Not Tier 3 being unreachable — it runs 70 times. It is reached and
  **has a 0% success rate on this board**, which is a separate defect
  worth its own task (14.5 s of wall time for nothing).

---

## 8. Deliberately not fixed

The two succeed-then-discard shapes (§2) look like cheap wins — 23 edges
across 8 nets, geometry already computed and already clearance-checked.
**They were not fixed**, because:

1. `partial_paths` is *deliberately* never written. Its own docstring:
   *"NEVER written to the board … a diagnostic record, not a second
   copper channel."* Emitting it is a policy change on a mains-voltage
   board, not a bug fix, and it would change board copper without any of
   the DRC evidence such a change requires.
2. The `RTD_HW_FAULT` case is the same: `_attempt_pad_layer_landing`
   refusing a route whose end cannot land on its pad's own layer is
   fail-closed by design.
3. Neither would close a single net (`fully_connected` is unchanged for
   all 8), and neither touches the 55-net majority.

**No clearance, creepage, DRU, ampacity or annular-ring threshold was
changed, and no test was weakened.** The 12.6 mm PD3 figure that produces
the finding is reported, not adjusted.

---

## 9. Reproducing

```sh
cd <worktree>
unset CONDA_PREFIX && make venv-isolate

# one instrumented production route (~220s, ~1GB RSS); writes trace JSON
# plus the routed board to a scratch path -- never touches pcb/temper.kicad_pcb
.venv/bin/python docs/evidence/2026-08-19-mechanism-a-instrument-route.py \
    --repo "$PWD" --out /tmp/trace.json --board-out /tmp/routed.kicad_pcb

# decomposition, tier anatomy, endpoint provenance, budget accounting,
# placement creepage census -- prints every table in this document
.venv/bin/python docs/evidence/2026-08-19-mechanism-a-analyze.py \
    --trace /tmp/trace.json --board /tmp/routed.kicad_pcb --repo "$PWD"
```

Wall time ≈ 220 s per route, peak RSS ≈ 0.8 GB. Check for a competing
`route_board.py` first — concurrent routes have been OOM-killed on this
machine.

`sha256sum pcb/temper.kicad_pcb` before and after:
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` — unchanged.

---

## 10. Open questions this pass did not close

* **Coarse-to-fine is doing nothing useful.** It is on by default and
  runs on every segment (`net_id == -1` in `_astar_route_nlayer`, which
  is also what makes the branch reachable at all). Of 376 segments, its
  coarse phase produced a usable corridor **47 times**; the other 329
  fell through to the unrestricted fallback having paid for a downsample
  plus a full coarse A\*. **[measured]** Whether that is a defect or
  merely a cheap-and-useless pre-pass was not quantified in wall time.
* **Tier 3's 0/70 success rate.** It is entered, it searches 250–500 ms
  per call on 51 of 70 calls, it has never resolved a segment on this
  board, and it costs 14.5 s per route. The `TierTally` docstring
  recorded 0/70 on 2026-08-18; this run reproduces it independently.
* The 12 nets whose first failure cause is "frontier exhausted, no path
  at this width" rather than a haloed pad were not individually traced to
  the obstacle that closes their corridor.
* The 47 budget-limited searches over free endpoints (26 nets) were not
  re-run at a larger budget. Note the 2026-08-17 hop-reachability fix
  already raised Tier 3's budget and measured no net recovery.
