<!-- provenance: commit=4154597c4f4c3401ca3b42f6ccb0b11cfcd56db0 dirty=false -->
<!-- The stamp above is the commit whose tree these measurements were taken in --
this document's own parent, i.e. the last code commit of the branch -- rather than
the document's own SHA, which cannot be written into the file it names. That tree is
byte-identical in every router-relevant file to the tree the
route and campaigns actually ran against -- verified file by file after this branch
was rebased onto origin/main c47761757 mid-work (occupancy_grid.py, clearance_floor.py,
_pipeline_core.py, _astar_reconstruct.py, io/_parse_nets.py, generate_kicad_dru.py,
netclass_rules.yaml, pcb/temper.kicad_pcb all IDENTICAL across the rebase, and the
regenerated DRU hash unchanged). The 5 commits origin/main gained during this work
touch only placer/cp_sat/ and temper-orchestration -- nothing under router_v6/, io/,
pcb/ or the DRU generator -- so no measurement here was invalidated by them.
-->

<!-- Measured 2026-08-12 in worktree /home/bennet/Desktop/temper-clearance-reland,
branch feat/router-clearance-floor-reland, branched from origin/main c87492f38 (the
#1100 revert). Board under study: PR #1082's heatsink placement, placed board sha256
7e1dd81f05185adfcad7b5d05020a140eb06faf643d3e11830b08e54f0b40f2a -- the SAME file
#1095 and #1099 routed, re-verified by hash here, not re-solved, so placement does not
move. pcb/temper.kicad_pcb NOT modified: sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 unchanged,
`git status --short pcb/` empty before and after every step.
.kicad_dru regenerated from scripts/generate_kicad_dru.py::generate_dru on this branch,
sha256 bad860a0d199e5b4fa35d0643ba68dae1ddecc50ae5f854c27832139b60e6ae4 -- BYTE-IDENTICAL
to origin/main's, which is the point: the DEFAULT_ROUTING_CLEARANCE_MM change is
emission-neutral. It is NOT #1095's ed81027e; see sec 4 for why every board in the
table was re-graded rather than compared across rule files.
pumpkin_engine sha256 7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e
source_commit 5bbf650d47d3a07fffd10a44e7c06c43a0a800bd; scripts/verify_pumpkin_engine.py
--require exit 0. kicad-cli 10.0.5 via the ~/.local/bin shim (#1086).
Routing: scripts/route_board.py --net-batching --batch-size 10, PYTHONPATH pinned to
this worktree's temper-placer so the measured code is the changed code.
NO ceiling entry written; power_pcb_dataset/drc_ceiling.json NOT modified. -->

# The clearance-floor re-land, and the boundary bug it exposed: 191 zero-gap shorts are gone, `clearance` still does not move

> **Four verdicts up front.**
>
> **1. #1095's substance is re-landed, ported rather than merged.** #1100
> reverted it because merge conflicts were resolved with `git add -A` after
> fixing only some files, committing `<<<<<<< HEAD` markers into
> `_pipeline_core.py` and `_encoder_solve.py` and leaving `main` unable to
> parse. The analysis was never in question. The conflict in
> `_pipeline_core.py` is a trap: a ~190-line region present on #1095's branch
> and absent on `main` that *presents as an addition* and is not one — see
> sec 1.
>
> **2. The guard fix is required, not optional, and it works.** #1095's width
> correction makes `build_occupancy_grid`'s inflation exactly `0.100`, and the
> guard read `if inflation_mm > 0.1`. Strict `>`. The C-space erosion was
> skipped in its entirety at precisely the production value, freeing **94,837
> cells across the four layers** that `main` reserves. Board C's DRC reports
> **191 clearance violations at `actual 0.0000 mm`** — real shorts.
> With the guard fixed: **0**. `shorting_items` falls with them, 199 -> **98**,
> and total errors 1312 -> **1048**, the lowest of any board in this series.
>
> **3. `clearance` does not move, and that is not a failure.** It is **499** on
> board E, against 499–503 measured across every board routed from this
> placement under three different clearance models. It is a property of the
> **placement**, established independently by #1052,
> `docs/plans/2026-08-12-001`, #1095 sec 6.4 and now here. The committed board
> — a *different* placement — sits at 402 under the same rules, which is the
> same statement seen from the other side. Reporting `clearance ≈ 500` as a
> regression of a router change would be wrong.
>
> **4. Pad connectivity — and this is pad connectivity, said out loud, not
> topology-solved nets.** **55/139 -> 51/139 (#1095) -> 48/139 (this PR).**
> Every honest reservation costs completion; 94,837 cells the router had been
> treating as free are cells touching real copper, and a net that could only
> close through them could only close by overlapping something. The cost is
> real and it is the price of the 191 shorts.

---

## 1. The port, and the union-merge trap in `_pipeline_core.py`

`git diff 226b210c1 d60caadd5` (#1095's merge base to its last good commit)
touches 11 files. Nine of them are byte-identical between that merge base and
current `main`, so they port by checkout. Two have moved: `generate_kicad_dru.py`
(+318 lines from #1084 and #1096) and `scripts/manifest.yaml`, and both took the
change by hand.

`_pipeline_core.py` is the one that matters.

**What the conflict looks like.** #1095's branch carries a ~190-line inline
`route_pcb`/`run()` orchestration body that `main` does not have. A three-way
merge presents it as an addition on the branch side, and "keep both" is the
reflex.

**What it actually is.** Commit `330aa7123` (orchestration-port unit U-G)
restructured `run()` to delegate stage sequencing to Rust —
`temper-orchestration`'s `RouterPipeline` pyclass — and *deleted* that inline
body, moving its Stage-0 marshalling into a module-level `_run_stage0_setup`.
#1095's branch predates it. So the region is not new work being added; it is
**old work `main` deliberately removed**. Checked rather than assumed: the
pre-#1095 version of that file contains **zero** occurrences of
`start_time = time.time()`, the inline body's own signature.

A keep-both-sides resolution would have resurrected the deleted body and undone
the U-G migration — a far worse outcome than the conflict markers #1100
reverted, because it would have parsed.

**What #1095 actually changed in that file**, isolated with
`git diff d60caadd5^..d60caadd5` and its siblings, is one deleted statement and
its comment:

```python
-                    dr.default_clearance_mm = 0.15
```

That statement now lives in `main`'s `_run_stage0_setup` instead of the inline
body. Deleting it there, with #1095's explanatory comment carried over, is the
whole of the port. `main`'s restructured file is otherwise untouched.

### 1.1 Two oracles, updated in lockstep

Both differential oracles carry their own copy of a corrected value, and both
pin the **migration contract** — shim output == pre-migration output — not the
**value**. A deliberate value correction has to land on both sides or the
differential starts asserting the defect:

| oracle | carried | treatment |
|---|---|---|
| `tests/io/_parse_engine_py_oracle/_parse_nets.py` | `default_trace_width = 0.25` | -> `0.2`, as in #1095's own `d60caadd5` |
| `tests/router_v6/_pipeline_core_py_oracle.py` | `dr.default_clearance_mm = 0.15` | deleted, same reasoning |

The second is additionally **digest-pinned** by
`test_oracle_body_matches_pinned_digests`. The re-pin
(`8d3221be…` -> `3a719cb2…`) is logged in place next to the constant, so a
future reader sees why the "verbatim" file moved.

## 2. The gate, mutation-verified

`scripts/check_router_clearance_floor.py` asserts five properties; P4 walks
`router_v6/`'s AST for any `*.default_clearance[_mm] = <literal>` below the
floor, so a reformatted or renamed-variable reintroduction is still caught.

Green on this tree:

```
DRU default-routing clearance floor: 0.2mm
  P1 OK  netclass_rules.yaml default_clearance_mm = 0.2
  P2 OK  temper.kicad_pro Default clearance = 0.2
  P3 OK  emitted 'Default routing' rule = 0.2mm
  P4 OK  0 literal default-clearance assignment(s) in router_v6/, none below 0.2mm
  P5 OK  _extract_design_rules() default_clearance_mm = 0.2
PASS  (exit 0)
```

**Mutation.** A gate that has only ever been green proves nothing. Restoring
`c87492f38`'s (pre-fix `main`'s) `_pipeline_core.py` under an otherwise
unchanged tree:

```
  P4: .../router_v6/_pipeline_core.py:84 assigns default_clearance_mm = 0.15,
      below the 0.2mm DRC floor -- the router would reserve less than the DRC
      grades against, producing clearance errors by construction
FAIL: 1 violation(s)  (exit 1)
```

It catches the real defect, at the real line, on the real tree. Its own 10 unit
tests pass.

## 3. The boundary bug: `if inflation_mm > 0.1`

### 3.1 The mechanism

`OccupancyGridStage` builds every layer's C-space with

```python
base_inflation = pcb.design_rules.default_trace_width_mm / 2.0
grid = build_occupancy_grid(routing_space, inflation_mm=base_inflation)
```

and `build_occupancy_grid` eroded the free area under

```python
if inflation_mm > 0.1:  # Threshold to avoid tiny/empty buffers
```

While `default_trace_width` was 0.25 the inflation was 0.125 and the guard
passed. #1095's correction to 0.20 — itself right, three declared sources say
0.2 — makes it exactly **0.100**, and `0.1 > 0.1` is False. The reservation is
not reduced; it is **switched off**.

### 3.2 What the threshold was actually protecting against — both halves, measured

Its comment names two hazards. Both were measured directly, on the #1082 placed
board's four production routing spaces, rather than assumed:

**"tiny" does not exist.** A negative buffer at any magnitude the router could
plausibly pass is valid, non-empty, and free:

| inflation | t (all 4 layers) | valid | empty | area lost |
|---:|---:|---|---|---:|
| 1e-9 | 0.042s | yes | no | 0.000000% |
| 1e-6 | 0.034s | yes | no | 0.000010% |
| 1e-4 | 0.035s | yes | no | 0.001046% |
| 1e-3 | 0.034s | yes | no | 0.010459% |
| 1e-2 | 0.046s | yes | no | 0.104724% |
| 0.05 | 0.058s | yes | no | 0.524582% |
| 0.1 | 0.045s | yes | no | 1.051328% |

and the grid it produces is graded, not degenerate — F.Cu free cells with the
erosion forced on: 890,622 (none) / 890,588 (1e-9) / 890,518 (1e-3) / 889,035
(0.01) / 875,527 (0.05) / 857,988 (0.1) / 853,530 (0.125) / 826,651 (0.2) /
794,555 (0.3). Monotone, no cliff, no boundary artefact.

**"empty" is real, but two orders of magnitude away.** Eroded area by layer:

| inflation | F.Cu | In1.Cu | In2.Cu | B.Cu |
|---:|---:|---:|---:|---:|
| 0.1 | 8603.4 | 34742.5 | 34742.5 | 8899.6 |
| 1.0 | 6047.9 | 32836.7 | 32836.7 | 6917.2 |
| 5.0 | 595.8 | 21129.1 | 21129.1 | 2164.5 |
| 10.0 | **EMPTY** | 9439.0 | 9439.0 | 406.3 |
| 20.0 | EMPTY | 2149.5 | 2149.5 | **EMPTY** |
| 50.0 | EMPTY | **EMPTY** | **EMPTY** | EMPTY |

The first layer to empty does so at **10mm**, 100× the threshold. A 0.1mm
magnitude test is far too small to catch the hazard it names and, as it turned
out, exactly the wrong size to be harmless.

### 3.3 The predicate chosen

```python
check_area = routing_space.available_area
if inflation_mm > 0:
    check_area = routing_space.available_area.buffer(-inflation_mm, quad_segs=4)
    if check_area.is_empty:
        logger.warning(...)
```

Two decisions, both from the measurements above rather than from taste:

* **`> 0`, not a magnitude.** Any positive inflation is a real reservation.
  There is no cost to guard against on the small side (0.042s, 0.000000% area)
  and a magnitude test cannot express the hazard on the large side.
* **An empty erosion is KEPT, not discarded.** It means no trace of that width
  fits anywhere on the layer, so blocking the layer is the true answer.
  Falling back to the un-eroded area there would emit copper that violates by
  construction — precisely the defect class this whole change is about. It is
  logged so the cause is visible instead of surfacing as mass A* failure.

### 3.4 Board effect of restoring the erosion

Through the production grid builder, at exactly the inflation
`OccupancyGridStage` passes (0.1, from the corrected 0.2mm width). "Before" is
`inflation_mm=0.0` because that is precisely what the old predicate did:

| layer | grid cells | free BEFORE | free AFTER | reclaimed | % of grid |
|---|---:|---:|---:|---:|---:|
| F.Cu | 3,712,800 | 890,622 | 857,988 | 32,634 | 0.88% |
| In1.Cu | 3,712,800 | 3,491,810 | 3,474,343 | 17,467 | 0.47% |
| In2.Cu | 3,712,800 | 3,491,810 | 3,474,343 | 17,467 | 0.47% |
| B.Cu | 3,712,800 | 914,262 | 886,993 | 27,269 | 0.73% |
| **TOTAL** | **14,851,200** | **8,788,504** | **8,693,667** | **94,837** | **0.64%** |

By construction these are the cells hugging an obstacle boundary — the ring a
0.2mm trace centred on which overlaps the obstacle by up to 0.1mm.

### 3.5 Regression tests, and what they do not cover

Four tests in `tests/router_v6/test_occupancy_grid.py`.
`test_erosion_applies_at_exactly_the_production_inflation` is the one that pins
the defect, and is mutation-verified: reinstating `> 0.1` fails it
(`assert 10000 < 10000`) and fails nothing else in the file.

`test_erosion_is_monotonic_in_inflation` is recorded in its own docstring as
**not** catching this: discarding the erosion below a threshold makes the
sequence flat there, and flat is still sorted. It constrains the shape of a
future replacement predicate and is not counted as coverage it does not
provide.

## 4. Why every board was re-graded, rather than compared across rule files

#1095's campaigns were run against a `.kicad_dru` of sha256 `ed81027e…`. This
branch's regenerates to `bad860a0…`. The difference is **not** from this PR:
this branch's DRU is byte-identical to `origin/main`'s, which is the check that
`DEFAULT_ROUTING_CLEARANCE_MM` is emission-neutral (`0.2` formats to `0.2`).
It is #1084's resonant-tank `HighVoltageTank` creepage rules, which landed
after #1095's base and add ~77 lines of new conditions.

Grading a new board against `bad860a0…` and comparing it to numbers taken
against `ed81027e…` would silently attribute #1084's creepage rules to this
change. So **every** board in the table below was re-graded here, from its own
committed artefact, under one rule file, with one harness.

The harness also stages `fp-lib-table` and `libs/` beside the board, which
#1095's did not. That changes `lib_footprint_*` **warnings** only, and it is
applied uniformly to every board, so the error columns stay comparable.
#1095's published figures are quoted where useful but are never mixed into a
row with these.

## 5. The combined table

### 5.1 Per-category DRC, N=130 per board, one DRU, one harness

Medians over 130 `kicad-cli` samples, `[min–max]` where the category varied.
Every board graded here, in this worktree, against
`.kicad_dru` `bad860a0…` with `fp-lib-table` and `libs/` staged. `committed`
is `pcb/temper.kicad_pcb` as it ships (a **different placement** — it is here
as the ceiling's own subject, not as a peer of the other three).

| category | ceiling | committed | heatsink | boardC | boardE |
|---|---:|---:|---:|---:|---:|
| `clearance` | 386 | 402 [401–402] | 501 [499–507] | 500 [499–502] | **499 [499–501]** ❌ +113 |
| `track_width` | 199 | 199 | 199 | 199 | **199** ⚠️ at ceiling |
| `shorting_items` | 199 | 199 [199–200] | 137 | 199 [199–202] | **98** ✅ |
| `solder_mask_bridge` | 154 | 154 | 49 | 204 [199–209] | **65** ✅ |
| `creepage` | 186 | 200 [198–200] | 112 [110–112] | 105 [103–105] | **83 [81–83]** ✅ |
| `hole_clearance` | 105 | 105 | 89 | 54 | **58** ✅ |
| `courtyards_overlap` | 11 | 11 | 19 | 19 | **19** ❌ +8 |
| `copper_edge_clearance` | 10 | 10 | 13 | 16 | **9** ✅ |
| `tracks_crossing` | 1 | 1 | 6 | 5 | **4** ❌ +3 |
| `annular_width` | 4 | 4 | 6 | 4 | **4** ⚠️ at ceiling |
| `drill_out_of_range` | 4 | 4 | 6 | 4 | **4** ⚠️ at ceiling |
| `via_diameter` | 4 | 4 | 6 | 4 | **4** ⚠️ at ceiling |
| `hole_to_hole` | 3 | 3 | 0 | 0 | **2** ✅ |
| **TOTAL errors** | 1266 | 1296 [1294–1296] | 1143 [1139–1149] | 1312 [1307–1319] | **1048 [1046–1050]** |
| TOTAL warnings | — | 489 | 496 | 482 | **472** |
| `unconnected_items` | — | 428 | 326 | 333 | **340** |

sample counts: committed N=130, heatsink N=130, boardC N=130, boardE N=130
board sha256: committed 6928b7c8…, heatsink 9c912b9e…, boardC 38510f36…, boardE 34626f88…
dru  sha256: bad860a0…

**Read the ceiling column with care.** `drc_ceiling.json` was measured at
`f70296adc…` against an **older** rule file. Under `main`'s current DRU the
**committed board itself** is over it — `clearance` 402 vs 386,
`creepage` 200 vs 186, total 1296 vs 1266 — with no router change involved.
That is a pre-existing staleness on `main` created by #1084/#1096 landing new
DRU rules, and it is **recorded, not fixed, here**: `drc_ceiling.json` is
untouched by this PR and no `Ceiling-Approval:` trailer is written.

**Board E's result.** Total errors **1048**, the lowest of any board in this
series and **264 below board C**, with `shorting_items` 199 -> **98**,
`solder_mask_bridge` 204 -> **65**, `creepage` 105 -> **83** and
`copper_edge_clearance` 16 -> **9**. Against the (stale) ceiling it breaches
three categories rather than board C's five, and `clearance` remains the
dominant breach at +113 — see sec 6.

The harness reproduces #1095 where the rules did not move: the heatsink board
re-graded here gives `clearance` **501 [499–507]** and total **1143
[1139–1149]**, matching #1095's published `501 [499–505]` / `1143 [1140–1147]`.
That is the control that says the re-grade is measuring the same thing #1095
measured, and it is why the boards whose numbers *did* move (committed:
1264 -> 1296) can be attributed to the rule file rather than to the harness.

### 5.2 Connectivity — **pad connectivity**, which is what this row is

Every board routed from the identical placed board (`7e1dd81f…`) with
`scripts/route_board.py --net-batching --batch-size 10`. #1095's A/B/C figures
are its own; **E** is this branch.

| | heatsink | A | B | C | **E** |
|---|---:|---:|---:|---:|---:|
| **pad-connected (PRIMARY)** | **55/139** | **51/139** | **49/139** | **51/139** | **48/139** |
| fake-completion | 59 | 50 | 50 | 55 | **47** |
| honest-gap | 25 | 38 | 40 | 33 | **44** |
| topology-solved nets (secondary) | 86/102 | 73/102 | 71/102 | 78/102 | **67/103** |
| segments emitted | 4497 | 3410 | 3207 | 3638 | **2929** |
| vias | 58 | 60 | 48 | 40 | **44** |
| zones | 84 | 84 | 84 | 84 | **112** |
| route wall time | 431.4s | 543.9s | 445.9s | 491.9s | **433.5s** |

**Pad connectivity falls 55 → 51 → 48.** #1095 already paid 55 → 51 for
reserving honestly; the guard fix pays another 3. That is the expected
direction and it is the whole trade: 94,837 cells that the router was treating
as free are cells adjacent to real copper, and a net that could only close
through them could only close by overlapping something.

The `103` denominator on E versus `102` on C is not a metric change: it is
`_should_route()` excluding 7 zone-covered power/HV nets instead of 8. `gnd`
is attempted on E and fails, where on C it was excluded outright.

### 5.3 Where the violations went — the mechanism, resolved to width pairs

Every `clearance` violation whose two items are both `Track`, resolved back to
its `(segment …)` by uuid so the **width pair** is known. This is the check
that separates "the reservation is wrong" from "the reservation is one-sided".

| | heatsink | C | **E** |
|---|---:|---:|---:|
| track–track `clearance` errors | 407 | 135 | **354** |
| ... **same-width** pairs | **311** | 15 | **2** |
| ... mixed-width pairs (0.20 × 0.508) | 96 | 120 | 352 |
| `actual 0.1500` bucket | 136 | 0 | **0** |
| `actual 0.1972` bucket | 149 | 0 | **0** |
| `actual 0.0000` (zero-gap, i.e. shorts) | 0 | **191** | **0** |
| pad–track pairs | 58 | 280 | **93** |
| pad–pad pairs | 0 | 22 | **0** |

**Read the same-width row, not the total.** The defect #1095 diagnosed is a
same-width defect: two Default tracks stamped at a pitch the rasteriser chose
for their own width. It is **311 → 15 → 2**, i.e. gone. The `0.1500` and
`0.1972` buckets that were 285 of the heatsink board's 505 are **0** on both C
and E.

**E's higher track–track total is 352 mixed-width pairs, all 0.2000 × 0.5080**,
and that is a *named, already-documented* limitation rather than a new defect.
`clearance_floor.blocking_clearance_mm` assumes the neighbour has the **same
width** as the net being stamped, so a 0.2mm trace laid beside a 0.508mm rail
under-reserves by `(0.508 − 0.2)/2 = 0.154mm`. The arithmetic shows up
literally in the buckets: `0.200 − 0.154 = 0.046` -> the **`0.0460` bucket
(70)**, and the 0.5mm-pitch case `0.5 − 0.1 − 0.254 = 0.146` -> the **`0.1460`
bucket (52)**. #1099 sec 7 named exactly this and proposed the two-sided form
`w_self/2 + c + w_other/2`; it needs a board-scale measurement of its own and
is not in this PR.

So E trades 191 **shorts** for 232 more mixed-width **proximity** violations of
a kind that has a known fix. That is a good trade and it is stated as a trade,
not as a win.

## 6. `clearance` is a placement property, for the seventh time

`clearance` on the #1082 heatsink placement, across every copper realisation
anyone has produced from it — five clearance models, a 35% spread in emitted
segments, one number:

| board | clearance model | segments | `clearance` |
|---|---|---:|---:|
| heatsink | 0.15 floor, 0.25 width (pre-#1095) | 4497 | 501 |
| A | 0.2 floor | 3410 | 502 |
| B | + 0.20 width | 3207 | 500 |
| C | + rasteriser-derived reservation | 3638 | 500 |
| **E** | + C-space erosion restored | **2929** | **499** |

(A and B are #1095's own figures; heatsink, C and E are re-graded here.)

And the same statement from the other side: the **committed** board — a
*different placement* — sits at **402** under the identical rule file. The
number tracks the placement, not the router.

This is the fifth independent route to that conclusion (#1052 from the
corridor-mask side, `docs/plans/2026-08-12-001` from construction
insensitivity, #1095 sec 6.4, #1099's board-neutrality result, and this).
**`clearance ≈ 500` is not this PR's regression and no routing parameter will
move it.** Presenting it as a failure of the clearance work would be a
misreading, and it is called out here precisely so the next reader does not
make it.

## 7. Verification

Run before every commit, all three commits:

```
git status --porcelain                                        # no stray work
git grep -l "^<<<<<<< " -- '*.py' '*.rs' '*.yaml' '*.yml' '*.json'   # EMPTY
compileall over packages/ and scripts/                        # ALL PARSE OK
```

The second is the one #1100 existed to catch. It is empty on every commit of
this branch, and every `.py` under `packages/` and `scripts/` compiles.

| check | result |
|---|---|
| `scripts/check_router_clearance_floor.py` | **exit 0**, P1–P5 |
| ... mutation: pre-fix `_pipeline_core.py` restored | **exit 1**, P4 fires at `:84` |
| `scripts/tests/test_check_router_clearance_floor.py` | 10 passed |
| `tests/router_v6/test_occupancy_grid.py` | 12 passed |
| ... mutation: `> 0.1` reinstated | 1 failed (`assert 10000 < 10000`), 11 passed |
| `scripts/check_manifest_gate.py` | PASSED, 155 entries |
| `scripts/check_netclass_class_param_correspondence.py` | passed, 0 mismatches |
| `scripts/gen_domain_models.py --check` | all match |
| `scripts/check_evidence_provenance.py` | 83 violations, **down 1** — this PR adds two evidence files and both carry a stamp |
| `ruff check router_v6/` | 8 findings, **identical to `origin/main`**, none in this PR's files |
| `scripts/verify_pumpkin_engine.py --require` | exit 0, sha `7ff153f4…` |
| `pcb/temper.kicad_pcb` | sha `6928b7c8…` unchanged, `git status --short pcb/` empty |
| `power_pcb_dataset/drc_ceiling.json` | not in the PR diff |

**Test-suite status, stated with its limitation.** An early full run of
`tests/router_v6/` + `tests/deterministic/` gave **667 passed, 1 failed** —
`test_bundle_analyzer.py`, which is **8 failed / 2 passed on clean `main`**
(`'Graph' object has no attribute 'edges_with_data'`), i.e. not this PR.
Partway through the session a concurrent process rebuilt the shared venv's
compiled extensions, after which `deterministic_phase` lost
`footprint_radius_py` and a swathe of `router_v6` marshalling tests went red.
That is environmental and it was checked rather than assumed: run against
**clean `main`** and against **this branch**, the same selection gives
**20 failed on both**, with this branch also passing the 4 tests it adds
(main 13 passed, branch 17 passed). Same failures, same count, both arms.

`tests/router_v6/test_temper_production_board_routing.py` is a second
monolithic-route OOM (killed the first full run, exit 137) and is excluded
for the same reason #1099 gave for the old ratchet.

## 8. What is not settled

* **`test_production_board_routing_drc_regression` — status changed while this
  PR was in flight, and it WAS run.** #1099 measured it three times on an
  otherwise idle 62 GB box: three kernel OOM kills, peak `anon-rss` 61.4 GB,
  `pytest` exit 137, because it called `route_pcb()` without
  `enable_net_batching`. **#1101 (`c47761757`) landed on `main` during this
  work and switched it to the net-batching path**, which is also what
  `scripts/route_board.py`'s documented recipe uses. That makes it a live gate
  on this PR — it routes `pcb/temper.kicad_pcb`, whose routing this PR changes
  — so it was run rather than skipped.

  **Result: `1 passed in 426.45s`, exit 0**, peak sampled RSS **2.66 GB**
  (against #1099's 61.4 GB on the monolithic path — #1101's fix holds).
  `completion_rate=0.0680, unrouted=96`, **exactly** the figures #1101
  recorded for this path on `main`, so this PR does not move that path's
  completion. All three assertions pass:
  `shorting_items <= 178`, `unconnected_items <= 463`, `total <= 1514`.

  The third one is the interesting one. **#1101's own measurement on `main`
  put `total` at 1621 — 107 over the bar** — and its evidence document
  explicitly anticipates "a future reader hitting a red `total` assertion".
  On this branch that assertion is green. Stated with its limit: the exact
  passing value is not recoverable from a green run (the test prints
  `sample.total` only in the failure message), so what is established is
  `total <= 1514` here against `1621` recorded there, not a precise delta.
  The `main` arm could **not** be re-run in this session for a same-day A/B:
  a fresh worktree at `c47761757` fails at import with
  `module 'temper_orchestration' has no attribute 'RouterPipeline'` — the
  shared venv's compiled extension is built from the development worktree,
  not the checkout. So the comparison is against #1101's published figure,
  not against a re-measurement, and is labelled accordingly.
* **`OTHER_NET_CLEARANCE_MM = 0.05`** in `_ground_plane.py`/`_power_islands.py`
  is untouched here. #1099 fixes it and stacks behind this PR; it also
  established that those modules are not reachable from `route_pcb()`, so the
  fix is board-neutral through the production route and cannot be what put the
  zero-gap violations on board C.
* **`test_full_pipeline_run_surfaces_the_same_unexplained_gap`** is red on
  `PWM_H` on the 33-net fixture, as #1095 recorded. #1099 sec 7 measured that
  the board *can* route it at correct clearance and that it is squeezed out by
  the 23 nets ahead of it. Not re-litigated here.
