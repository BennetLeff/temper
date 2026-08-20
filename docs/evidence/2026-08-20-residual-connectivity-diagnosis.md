<!-- provenance: commit=fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 dirty=false
     Branch agent/residual-connectivity-diagnosis, branched from fd4e73644
     (= origin/main eb5022510 + the two backbone fixes), MIN_BARRIER_WIDTH_MM
     = 12.6 -- the reference configuration the brief's 251/82/36 figures come
     from (docs/evidence/2026-08-19-per-pairing-placement-routed.md §3).
     pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
     identical before this task's first command and after its last; never
     opened for writing. Every board below was emitted to a scratch path
     outside the repo.
     Environment: this worktree's OWN .venv (`make venv-isolate` under
     `env -u CONDA_PREFIX`), check_stale_extensions 10/10 fresh, and all 10
     pyo3 modules import-smoke-tested (the timestamp gate alone does not prove
     loadability -- one crate was in fact found broken mid-session, see §7).
     Machine: 62 GB RAM, >28 GB free; no competing route_board.py during any
     quoted run. No cProfile attached to any quoted run.
-->
---
title: "The residual after the compliant placement: five mechanisms, and Tier 3 is not dead weight"
date: 2026-08-20
module: temper-placer
tags: [router, routing, pad-connectivity, tier3, creepage, diagnosis]
problem_type: routing-completion
status: measured
---

# The residual, diagnosed: five distinct mechanisms, and the Tier-3 premise is false

**Authority: analysis and measurement only.** No router, placer, clearance,
creepage or DRU value was changed. Nothing is fixed here — the residual is
five distinct mechanisms and, per the brief's own standard, reporting each
with its count beats a partial fix to one.

## 0. Headline

| question | answer |
|---|---|
| mechanism split of the **36** | **30** fail on hop 0 · **6** succeed-then-discarded · **0** complete-then-discarded · **0** declined by policy |
| the **13** non-halo nets | **two** mechanisms: **7** blocked by an *already-routed net's* copper stamp, **6** genuinely searched and lost with free endpoints |
| the **57** not-fully-connected | 36 zero-copper + 10 pour-only + **11 partial**, of which **8 are "fake completions"** — the router calls them `routed` |
| does Tier 3 earn its 14.5 s | **The premise is false.** Tier 3 resolves **12 segments** on this placement (0/70 was a property of the *committed placement*, not of Tier 3). It is neither dead weight nor budget-starved. |

**The brief's warning was correct and it fired.** Tier 3 would have been
deleted on the 0-for-70 count. On the compliant placement it resolves 12 of
its 54 calls — a 55 % success rate on the calls whose endpoints are actually
free.

## 1. Everything below is reproduced bit-for-bit

Three independent digests reproduce the published artifacts exactly, so the
instrumentation is proven non-perturbing and the placement chain is proven
identical to the one the brief's figures came from:

| artifact | published | **this session** |
|---|---|---|
| model-E placement written to a board | `bf9dde9a8d15a2bb…` | **`bf9dde9a8d15a2bb…`** |
| committed placement, routed | `697bad8936b3e16d…` | **`697bad8936b3e16d…`** |
| model-E placement, routed | `af99bd04fa5d873c…` | **`af99bd04fa5d873c…`** |

`route_once` counters also reproduce exactly — committed 4907/149/152
segments/vias/zones, model-E 5912/186/124 — and the row-E solve returns
`optimal`, 168 placed, with the identical setbacks (MAINS 4.80, DC_BUS 8.00,
SWITCHING 8.00, TANK 20.00, `all_determinable = False`).

**Harness validation.** Run against the *committed* placement, the
instrumented route reproduces the published mechanism-A decomposition
exactly — **55 fail / 7 partial-discard / 1 complete-discard / 0 policy**,
63 zero-copper nets, 127 edges, Tier 3 70 calls / 0 hits, coarse-to-fine
47 corridors of 376. Every number in
`docs/evidence/2026-08-19-mechanism-a-zero-copper-63-nets.md` reproduces.
The same harness then produced the model-E numbers below.

## 2. Q1 — the mechanism split of the 36 [measured, instrumented production run]

`nets with ≥2 pads = 112`, `zero segment/via copper = 46`, of which **36**
also carry no zone → **82 ratsnest edges**.

| mechanism | committed (63) | **model-E (36)** | edges |
|---|---:|---:|---:|
| **FAIL — A\* declined on hop 0**, nothing ever computed | 55 | **30** | 68 |
| **succeed-then-discard — partial** (hops resolved, later hop declined, whole net dropped) | 7 | **6** | 14 |
| succeed-then-discard — **complete** route discarded by pad-layer landing | 1 | **0** | 0 |
| **declined by policy** (`_should_route`) | 0 | **0** | 0 |

The complete-route-discard case (`RTD_HW_FAULT` on the committed board) is
gone: on model-E that net now routes — and lands in the fake-completion
bucket of §4 instead.

Nothing is filtered upstream on either board: 112 channel paths, 112 into
`_compute_net_order`, 105 admitted by `_should_route`, and
`_astar_reconstruct.run_astar_pathfinding` is entered **0** times
(`_astar_nlayer` is the production path, entered once).

## 3. Q2 — the 13 that are not halo-blocked [measured]

Per-net headline verdict over the 36, from grid state sampled live between
`_unblock_net_pads` and `_stamp_foreign_creepage_halos`, restricted to each
pad's own layer:

| verdict | committed (63) | **model-E (36)** |
|---|---:|---:|
| own pad inside a **foreign creepage halo** | 50 | **23** |
| own pad under an **already-ROUTED net's copper stamp** | 1 | **7** |
| endpoints free — A\* frontier/budget, no path at this width | 12 | **6** |

**The 13 are two different mechanisms, and one of them is new.**

### 3a. Seven nets: blocked by an already-routed net's copper (net ordering, no rip-up)

`discharge.k_dis1-coil1`, `discharge.k_dis1-coil2`, `discharge.k_dis2-coil1`,
`hb.gate_hs.driver-p2`, `sclk`, `sdo`, `vcc`.

This bucket went **1 → 7**. It is a *consequence of the placement working*:
63 nets now route where 34 did before, so there is far more earlier-laid
copper to claim a later net's pad. This is order-dependent self-blocking, and
the router has no recourse — `_astar_route_with_ripup`'s `ripped_ids` is
inert under the unconditional fail-closed `_allow_forced_segments() → False`
policy. **This is the population most likely to hide a genuine router defect,
and it is the one that grows as placement improves.**

### 3b. Six nets: endpoints free, the search genuinely lost

`PWM_LS`, `RTD_SCK`, `WDT_RESET_N`, `safety.ocp2-line`, `safety.ovp-line`,
`safety.uvlo_logic-line` — every own-layer pad cell `free_after_both`, so
neither a halo nor a foreign stamp explains them. `safety.uvlo_logic-line`
is the interesting one: its tier log is `['nlayer_via_3d', 'declined']` —
**Tier 3 resolved its first hop** and a later hop then failed.

Of the model-E decisive searches belonging to the 36, **25 are
budget-exhausted with both endpoints free** — the only subset a larger budget
could conceivably change. The other 136 are geometry.

## 4. Q3 — the 57 not-fully-connected, and the 8 fake completions [measured]

`139 − 82 = 57`. They are **not** one population:

| bucket | nets |
|---|---:|
| zero copper **and** zero zone (the §2/§3 set) | **36** |
| zero copper, **zone only** (pour-dependent; the audit is deliberately zone-blind) | **10** |
| **PARTIAL — has copper, not all pads joined** | **11** |

Across the 11 partial nets only **32 of 176 pads attach (18.2 %)**. But the
11 split again, and the split is the finding:

* **3 are the plane nets** — `gnd` 11/88, `+3V3` 4/50, `+15V` 1/10. All three
  declare an In1.Cu/In2.Cu zone; `pads_connected` is a pure segment+via graph
  verdict that cannot credit pour fill, and the 2026-08-19 `--refill-zones`
  measurement already established that filling rescues **zero** nets. Not
  pursued, per the brief.
* **8 are nets the router reports as `routed`** — `GATE_LS`, `RTD_HW_FAULT`,
  `V_BUS_SENSE`, `bias`, `power_in.bypass_relay-coil1`, `refin_n`,
  `safety.ovp.comp-inp`, `vbias`.

### 4a. The fake completions have one cause, and it is a real router defect

Every one of the 8 has **exactly `pads_connected == 2`**, regardless of
whether it has 3, 4 or 5 pads — and in every case the channel path's
waypoints *do* cover all of the net's pads (3 waypoints for 3 pads, 5 for 5).
The router emitted 513–5541 path points per net and reported success.

`_attempt_pad_layer_landing` (`_astar_nlayer.py:646`) inspects **only
`segments[0]` and `segments[-1]`** — the route's first and last emitted
points. It has no notion of an intermediate pad. A multi-pad net routed as a
chain pad₁→pad₂→pad₃ therefore never gets a landing via at pad₂: the copper
passes over it on the wrong layer, the pad stays electrically isolated, and
because `blocked_ends` is empty the net is still reported `routed`.

That predicts "connected == the two termini". Tested against the audit's own
union-find on the routed board:

| pad role | in the connected group |
|---|---|
| **terminus** (first/last waypoint) | **15 / 16** |
| **intermediate** | **1 / 12** |

**30 of 32 pad outcomes follow the rule.** The 12 unattached pads on these 8
nets are exactly the 12 intermediate pads. The single double-exception is
`safety.ovp.comp-inp`, the only one of the 8 with a via-rich (6-via)
multi-layer path.

This is a distinct mechanism from everything in §2/§3, it is invisible to
`failed_nets` (these nets are in `routed_paths`), and it is the reason
"routed" and "connected" disagree.

## 5. Q4 — Tier 3: the premise is false [measured]

| | committed placement | **model-E placement** |
|---|---:|---:|
| Tier-3 calls | 70 | **54** |
| Tier-3 **resolved segments** | **0** | **12** |
| Tier-3 wall time | 14.6 s (7.0 % of 207.7 s) | **7.9 s (3.8 % of 210.8 s)** |
| whole-run `tier_tally.resolved` | 56 | **112** |

**Tier 3 is neither dead weight nor budget-starved.** Its 0-for-70 was a
property of the *non-compliant placement*, which fed it 70 calls of which 48
had a blocked terminal. Given a compliant placement it resolves 12 segments —
and `safety.uvlo_logic-line` (§3b) is a net whose first hop only exists
because Tier 3 found it.

### 5a. Where its time actually goes, and why it is a *dispatch* problem

Terminal occupancy sampled at each Tier-3 call, on the terminal's own layer:

| terminal state | committed | **model-E** | model-E hits |
|---|---:|---:|---:|
| both terminals free | 22 | **22** | **12** |
| GOAL cell blocked | 21 | 11 | 0 |
| BOTH terminals blocked | 18 | 16 | 0 |
| START cell blocked | 7 | 5 | 0 |
| terminal out of bounds | 2 | 0 | 0 |

**Every hit comes from the "both terminals free" bucket — 12 of 22, a 55 %
success rate.** Tier 3 works exactly when it is given a satisfiable problem.

**A blocked goal is unsatisfiable at any budget**, and this is proven by
execution, not read off the source
(`2026-08-20-tier3-blocked-goal-proof.py`). In a 4-layer grid that is
**100 % free except one single blocked goal cell**:

```
goal free            found=True     1.0 ms
goal blocked, 200k   found=False  128.5 ms
goal blocked, 1M     found=False  567.1 ms
goal blocked, 4M     found=False  564.2 ms      <- not a budget effect
start blocked, 1M    found=True     0.7 ms      <- the asymmetry
```

The reason is structural: a node is pushed only after `is_free`, the goal is
detected only on *pop*, and both moves that can enter `(gx,gy,gl)` — the
same-layer step and the via — test `grids[gl].is_free(gx,gy)`. So no path can
exist, at any budget, on any number of layers. Nothing short-circuits it:
`route_segment_3d`'s only terminal check is a loop whose body is `continue`,
a no-op the Rust port faithfully reproduces (and says so).

On model-E that costs **3.83 s of Tier 3's 7.94 s (49 %)** across **27 of 54
calls**; on the committed board, 7.56 s of 14.63 s across 39 of 70. Tier 3's
budget is *not* the problem — it already receives the span-scaled
`max(per_net_max_iter, 200_000)` (500 000 on 38 of 54 calls).

### 5b. The one-line precheck is NOT a no-op — measured

The obvious fix — skip the call when the goal cell is blocked — **is a
regression as stated**, and this was caught by execution before proposing it:

```
start == goal, cell BLOCKED  -> found = True     (today)
```

A degenerate zero-length hop whose shared start/goal cell is blocked
*succeeds* today, because the start is seeded into the frontier
unconditionally and immediately satisfies the goal test. A precheck must
therefore be guarded `start != goal`.

**Deliberately not shipped.** It closes zero nets, buys ~1.8 % of route wall
time, and belongs at the Python Tier-3 call site rather than in the Rust
kernel — the kernel is under a **bit-exact f64 parity contract** with the
pinned `_astar_nlayer_py_oracle.py` (`test_astar_nlayer_rust_differential.py`
compares path/via coordinates as hex and the grid fingerprint), and re-pinning
that oracle is forbidden. Recorded here with its guard so whoever takes it
starts from the measured version, not the naive one.

## 6. Coarse-to-fine, re-measured [measured]

The brief's "helps 47 of 376" reproduces exactly on the committed board and
**improves markedly on the compliant one** — the pre-pass is placement-
sensitive too, not uniformly useless:

| coarse phase-1 outcome | committed (n=376) | **model-E (n=392)** |
|---|---:|---:|
| corridor found | 47 (12.5 %) | **89 (22.7 %)** |
| endpoints rejected | 103 | 86 |
| searched and failed | 226 | 217 |

## 7. An environment hazard worth recording

Mid-session `temper_geometry` became unimportable —
`ImportError: dynamic module does not define module export function
(PyInit_temper_geometry)` — while `check_stale_extensions.py` reported it
**fresh 10/10**. Its `#[pymodule]` sits behind `feature = "python"`, and the
shared cargo target dir had a cached artifact built without it (the failure
mode AGENTS.md warns about). `make extensions` alone did not fix it; it took
a rebuild under a private `CARGO_TARGET_DIR`.

**The freshness gate cannot see this**, so every measurement in this document
was additionally guarded by import-smoke-testing all 10 modules, and by
re-routing the committed board *after* the rebuild and confirming it still
produced `697bad8936b3e16d…`. Adding a load check to
`check_stale_extensions.py` would close the gap.

## 8. What this rules out, and what it does not

* **Not policy.** 0 of the 36 are declined by `_should_route`, on both boards.
* **Not upstream filtering.** All 112 multi-pad nets reach A\* with ≥2 waypoints.
* **Not zone fill.** Already settled at `--refill-zones`: it rescues zero nets.
* **Not Tier 3 being dead.** It resolves 12 segments here.
* **Not one residual mechanism.** It is five: foreign creepage halo (23),
  already-routed stamp (7), genuine search failure with free endpoints (6),
  terminus-only landing / fake completion (8), pour-dependent (10).

**No net is closed by violating a clearance.** The 23 halo-blocked nets can
only route through another net's required creepage, which is the finding, not
a thing to fix in the router. The two indeterminate pairings stay fail-closed
at 20.0 and 8.0 mm and every verdict touching them is CONDITIONAL.

## 9. Reproduce

```bash
env -u CONDA_PREFIX make venv-isolate
.venv/bin/python scripts/check_stale_extensions.py            # 10/10
.venv/bin/python -c "import temper_geometry"                  # see §7

# control (committed placement) -- must reproduce 697bad89… and 55/7/1/0
.venv/bin/python docs/evidence/2026-08-20-residual-instrument-route.py \
    --repo "$PWD" --out /tmp/trace_c.json --board-out /tmp/routed_c.kicad_pcb
.venv/bin/python docs/evidence/2026-08-20-residual-analyze.py \
    --trace /tmp/trace_c.json --board /tmp/routed_c.kicad_pcb --repo "$PWD" --label committed

# model-E board: solve on the per-pairing tip (bc3a19b06), then route at 12.6
#   -> placement board must be bf9dde9a…, routed board must be af99bd04…
.venv/bin/python docs/evidence/2026-08-20-residual-instrument-route.py \
    --repo "$PWD" --pcb /tmp/board_E.kicad_pcb \
    --out /tmp/trace_E.json --board-out /tmp/routed_E.kicad_pcb
.venv/bin/python docs/evidence/2026-08-20-residual-analyze.py \
    --trace /tmp/trace_E.json --board /tmp/routed_E.kicad_pcb --repo "$PWD" --label model-E

# Tier-3 structural proofs (seconds, no board needed)
.venv/bin/python docs/evidence/2026-08-20-tier3-blocked-goal-proof.py
.venv/bin/python docs/evidence/2026-08-20-tier3-precheck-edge-case.py
```

## 10. Hard-rule compliance

* `pcb/temper.kicad_pcb` never opened for writing; sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
  before the first command and after the last.
* No clearance, creepage, copper-weight, loop-area, ampacity, annular-ring,
  drill or DRU threshold read for adjustment, changed, or reasoned around.
* No check weakened: no test skipped, `xfail`ed, deleted or relaxed; no
  ratchet raised; no allowlist broadened; no `continue-on-error`, `|| true`,
  `# type: ignore` or `# noqa` added. **No production code changed at all.**
* `power_pcb_dataset/drc_ceiling.json` untouched and not re-baselined.
* No `_*_py_oracle.py` deleted, consolidated or re-pinned.
* `git stash` not used; no pushed history rewritten.
* The instrumentation is additive and observe-only; its `--pcb` flag defaults
  to the committed board, so the original invocation reproduces the original
  output. Proven non-perturbing by three byte-identical digests (§1).
