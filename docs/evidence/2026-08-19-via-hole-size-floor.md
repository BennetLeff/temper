<!-- provenance: branch fix/via-hole-size-floor, worktree
.claude/worktrees/agent-a7a18a2c3f9b117e8, based on origin/main eb5022510.
kicad-cli 10.0.5. pcb/temper.kicad_pcb sha256
26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b, verified
unmodified before and after every step; every candidate board was written to
a scratch path outside the repo. No subagents dispatched; every measurement
below was taken directly. -->

# The router emitted 0.2mm drills against a 0.3mm board minimum. Fixed at `Via::new`.

## 0. Summary

`drill_out_of_range` goes to **zero on both placements measured** — 6 -> 0 on
the committed placement, 4 -> 0 on a second, independently solved one — with
**zero connectivity change on either**. The cost is congestion-dependent and
fully attributed item-by-item: on the committed placement `clearance`
179 -> 199 (+20, all 20 naming one of the six vias whose pad grew), total
775/776 -> 790; on the second placement the board total goes **down**,
517/518 -> 515.

The 0.3mm figure is **not** wrong and was not lowered. It is also **not** a
JLCPCB limit — that is looser (0.15mm) — so §2 records exactly what it is and
where it came from.

---

## 1. Root cause

### 1.1 Where the drill is chosen

`TEMPER_NET_CLASSES["FinePitch"]` (`packages/temper-placer/src/temper_placer/core/design_rules.py`)
and its mirror in `packages/temper-placer/configs/netclass_rules.yaml` — the
file the router actually consumes — both declare:

```
FinePitch:  via_diameter 0.8mm   via_drill 0.2mm     (a 0.30mm annular ring)
```

`router_v6/via_placement.py::place_vias` resolves `via_drill_mm` per net class
from that table, so every via the router places on a `FinePitch` net gets a
0.2mm drill. Measured on a fresh route of the committed board, all six such
vias are on `RTD_SDI` / `RTD_CS_N` / `RTD_SDO`, which
`TEMPER_NET_ASSIGNMENTS` maps to `FinePitch`.

### 1.2 Why 0.2mm survived

The brief's hypothesis is confirmed, and the document that produced the
defect says so in its own words.
`docs/evidence/2026-08-13-via-annular-ring-floor-fix.md` §3 raised every
net-class via **pad** to a uniform 0.30mm ring and states the scope
explicitly: *"all raised to a 0.3mm ring, **drill unchanged in every case**"*.
For `FinePitch` the comment still in `design_rules.py` today reads *"New pad =
drill (0.2mm, unchanged — this is a manufacturability fix to pad geometry,
not a drill/current-capacity change)"*.

That fix therefore moved `FinePitch` from *ring-illegal and hole-illegal*
(0.4/0.2, a 0.10mm ring) to *ring-legal and hole-illegal* (0.8/0.2, a 0.30mm
ring around a 0.2mm hole). The same document's own 130-sample determinism
table records the residue it did not fix, on the very next line from the
categories it did:

```
drill_out_of_range: min=4 max=4 dist={4: 130}
```

The `0.3mm` board rule was known to that work — PR #1142's evidence doc
(`2026-08-13-jlcpcb-fab-capability-envelope.md` §6.1) names it directly:
*"`min_through_hole_diameter` to 0.3mm — this via's 0.1mm ring, 0.4mm
diameter, and 0.2mm drill fail all three"*. Only two of the three were fixed.

### 1.3 Why no guard caught it

* `Via::new` (`packages/temper-orchestration/src/pipeline_route.rs`), added
  2026-08-17, is the choke point every router-emitted via passes through
  (`_adapter_convert`'s marshalling calls it for each `compiled_route.vias`
  entry). It enforced the **annular ring** floor and nothing else, and its
  clamp explicitly leaves `drill` untouched.
* `scripts/check_fab_capability_floor.py`'s P1/P2/P3 all compare
  `(size - drill) / 2` against `min_annular_ring_mm`. None of them looks at
  the drill diameter itself. A 0.2mm drill passes all five properties.
* `docs/hardware/FAB_CAPABILITY.md` §5's machine-readable block does carry
  `min_drill_mm: 0.15`, but nothing reads it, and 0.2mm clears it anyway —
  the binding figure is the board's own 0.3mm, which no gate checks.

---

## 2. Is 0.3mm the right figure? (asked before changing code)

**Verdict: 0.3mm stands, and it is the binding constraint — but it is the
repo's own design minimum, not a fabricator limit.** Both halves matter.

| Source | Figure | Status |
|---|---|---|
| `pcb/temper.kicad_pro` `design_settings.rules.min_through_hole_diameter` | **0.3mm** | The board's declared minimum; what kicad-cli enforces as `drill_out_of_range` |
| `docs/hardware/FAB_CAPABILITY.md` §1 row 2b / §5 `min_drill_mm` | 0.15mm | JLCPCB published, fetched 2026-08-13, flagged "more costly" for 2+ layer |
| `docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md` §6.2 | 0.70mm | Smallest **component** through-hole drill actually on the board (R55) |

Provenance of the 0.3mm figure, checked rather than assumed:
`git log -S'"min_through_hole_diameter"' -- pcb/temper.kicad_pro` returns a
single commit, `651927a8e` ("syncing dec 15", 2025-12-15) — a ~4000-line bulk
sync, with no derivation attached anywhere in-tree. So:

* **It is not fab-sourced.** JLCPCB would build a 0.2mm hole. Reported as a
  finding, exactly like the previous agent's `fab_sourced=False` flags on the
  two 0.5mm figures.
* **It is nonetheless correct to conform to it, not to lower it.** It is
  stricter than the fab floor, which is the safe direction; nothing on this
  board needs a hole below it (the smallest *component* drill is 0.70mm, and
  the only sub-0.3mm holes anywhere are these router vias); and 0.3mm is
  already the board's single most common via drill (the `Default`, `Signal`
  and `HighSpeed` classes and `kicad_pro`'s `Default` net class all use
  0.9mm/0.3mm). Conforming costs one standard drill size on six vias.

**The inversion the brief asked about did not occur.** If the 0.15mm fab
figure were the operative one, the fix would have been to correct
`min_through_hole_diameter` instead — it is not, because a board's declared
minimum being *stricter* than its fabricator's is a design choice, not an
error, and 0.3mm is met by the rest of the board without effort.

**Second, latent instance, not fixed here (see §7):** `pcb/temper.kicad_pro`'s
`Differential` net class declares `via_drill 0.25mm` (0.85/0.25, also a 0.30mm
ring) — likewise below the 0.3mm minimum. It is a `kicad_pro`-only class with
no entry in `TEMPER_NET_CLASSES` or `netclass_rules.yaml`, so no routed via
uses it today; `Via::new`'s floor would correct one if a route ever produced
it, but the declaration itself is still wrong.

---

## 3. The fix

`Via::new`, `packages/temper-orchestration/src/pipeline_route.rs`. One new
constant and one new clamp, ahead of the existing annular clamp:

```rust
const MIN_THROUGH_HOLE_DIAMETER_MM: f64 = 0.3;   // pcb/temper.kicad_pro

// (1) hole size, BEFORE (2)
let drill = if drill < MIN_THROUGH_HOLE_DIAMETER_MM { MIN_THROUGH_HOLE_DIAMETER_MM } else { drill };
// (2) annular ring  (pre-existing, unchanged)
let diameter = if diameter - drill < 2.0 * MIN_ANNULAR_RING_MM { drill + 2.0 * ANNULAR_RING_TARGET_MM } else { diameter };
```

**The ordering is load-bearing, and it is the coupling the brief flagged.**
Raising a drill shrinks the ring for a fixed pad. `FinePitch`'s 0.8/0.2 is a
legal 0.30mm ring; clamping the hole alone gives 0.8/0.3, a **0.25mm** ring —
0.004mm below the 0.254mm annular floor, i.e. trading a `drill_out_of_range`
for an `annular_width`. Running the ring clamp second re-pads to **0.9/0.3**,
byte-identical to what `Signal`/`HighSpeed`/`Default` already declare
directly.

Neither clamp can lower anything: both are one-sided `if below-floor` raises,
and NaN compares false and passes through exactly as before.
`MIN_ANNULAR_RING_MM` (0.254) and `ANNULAR_RING_TARGET_MM` (0.3) are
untouched.

**Why here and not (only) in the net-class table.** The 2026-08-17 fix's own
docstring records the lesson: PR #1159/#1173 *"fixed the netclass tables, not
the router's own via emission, which is how PR #1312's copper regeneration
still produced 56 sub-floor vias from a stale, un-migrated default three
call-frames upstream of `Via::new`"*. A table edit is placement- and
call-path-dependent; a constructor guard is not. §7 records the table edit
that should still follow.

**Tests** (5 new, `packages/temper-orchestration/src/pipeline_route.rs`,
registered in the generated wasm registry via
`scripts/gen_wasm_test_registry.py --crate temper-orchestration`):

| Test | Pins |
|---|---|
| `via_new_enforces_hole_size_floor_on_the_exact_finepitch_pair` | 0.8/0.2 -> 0.9/0.3, and that the ring clamp ran second |
| `via_new_hole_floor_never_shrinks_a_drill` | 0.4 / 0.5 / 0.6 drills pass through byte-identical |
| `via_new_leaves_a_drill_exactly_at_the_hole_floor_untouched` | 0.3 is inclusive; 0.9/0.3 is not perturbed |
| `via_new_output_always_satisfies_both_floors` | 90-point sweep: every constructed via clears BOTH floors and no drill is ever shrunk |
| `emit_s_expr_reflects_the_hole_size_floor_clamp` | the guard cannot be bypassed by emitting directly |

`cargo test -p temper-orchestration --lib pipeline_route`: **21 passed, 0
failed.**

---

## 4. Measurement

### 4.1 Protocol

* Route: `scripts/route_board.py --pcb <board> --output <scratch>`, the
  production `router_v6.adapter.route_pcb` entry point.
* DRC: the committed harness protocol —
  `docs/evidence/2026-08-19-per-pairing-route-measure-board.py`, which stages
  board + `temper.kicad_pro` + `fp-lib-table` + `libs/` into a scratch dir,
  regenerates the DRU **in-process** from `scripts/generate_kicad_dru.py`
  (never writing `pcb/temper.kicad_dru`), and runs
  `kicad-cli pcb drc --all-track-errors --format json` under a pinned
  single-thread `KICAD_CONFIG_HOME`. **3 samples per board**; every count
  below was identical across all 3 except where stated.
* Environment: `make venv-isolate` under `env -u CONDA_PREFIX`;
  `make extensions-check` **PASSED — 10/10 fresh** immediately before the
  measurement runs. (`temper-geometry` was poisoned mid-session by a plain
  `cargo test` on a dependent crate — the exact failure its gate message
  describes — and was recovered with `cargo clean -p temper-geometry` plus a
  rebuild in a private `CARGO_TARGET_DIR`.)

**Baseline reproduction.** The pre-fix route of the committed board
reproduces the brief's reference digest exactly: **4553 seg / 169 vias / 151
zones, sha256 `6d4e17337bcf2633fb256f3da4d6fe981c91123827eff715a2c8aa870d195981`**.
The router is deterministic here, so every delta below is attributable.

### 4.2 Drill histogram

**Committed placement** (`pcb/temper.kicad_pcb`, 169 vias):

| size / drill | ring | before | after |
|---|---|---|---|
| 0.8 / **0.2** | 0.30 | **6** | **0** |
| 0.9 / 0.3 | 0.30 | 39 | 45 |
| 1.0 / 0.4 | 0.30 | 124 | 124 |
| **below `min_through_hole_diameter` 0.3** | | **6** | **0** |

**Second placement** (§4.5, 122 vias):

| size / drill | ring | before | after |
|---|---|---|---|
| 0.8 / **0.2** | 0.30 | **4** | **0** |
| 0.9 / 0.3 | 0.30 | 32 | 36 |
| 1.0 / 0.4 | 0.30 | 85 | 85 |
| 1.1 / 0.5 | 0.30 | 1 | 1 |
| **below `min_through_hole_diameter` 0.3** | | **4** | **0** |

The routed-board diff on the committed placement is **12 lines — the six
vias, nothing else.** Positions and tstamps are byte-identical; only `(size)`
and `(drill)` changed. The router's search is unaffected because the guard
sits at emission, downstream of pathfinding (A* still sees the net class's
0.8mm `via_diameter`). On the second placement the diff is 12 lines too: the
four vias (8 lines) plus **two vertices of one zone outline**, shifted by
0.046mm — consistent with a pour hull that tracks via pad radius (+0.05mm),
reported rather than assumed away.

### 4.3 Per-category DRC, committed placement

3 samples each. `silk_overlap` is at its `ERROR_LIMIT` saturation floor of
199 on both sides and is **not** quoted as a result.

| Category | before | after | delta |
|---|---|---|---|
| **`drill_out_of_range`** | **6** | **0** | **-6** |
| `clearance` | 179 | 199 | **+20** |
| `copper_edge_clearance` | 11 | 11 | 0 |
| `hole_clearance` | 33 | 33 | 0 |
| `hole_to_hole` | 0 | 0 | 0 |
| `shorting_items` | 39 | 39 | 0 |
| `creepage` | 106 | 106 | 0 |
| `via_dangling` (warn) | 111 | 111 | 0 |
| `silk_overlap` (warn) | 199 [SATURATED] | 199 [SATURATED] | — |
| `silk_over_copper` (warn) | 42 | 42 | 0 |
| `lib_footprint_mismatch` (warn) | 26 | 26 | 0 |
| `lib_footprint_issues` (warn) | 13 | 13 | 0 |
| `missing_courtyard` (warn) | 5 | 5 | 0 |
| `solder_mask_bridge` | 4 | 4 | 0 |
| `courtyards_overlap` | 1 | 1 | 0 |
| `silk_edge_clearance` (warn) | 1 | 1 | 0 |
| **total violations** | 775 / 776 / 776 | 790 / 790 / 790 | +14 |
| `unconnected_items` | 339 | 339 | **0** |

`clearance` (199) is far below kicad-cli's ~500 report cap, so it is a real
count, not a saturated one.

### 4.4 The +20 `clearance`, attributed item-by-item

Not asserted — measured. Counting violations that name a via at one of the
six positions the fix rewrote:

| Category | before: total / naming a touched via | after: total / naming a touched via |
|---|---|---|
| `clearance` | 179 / **3** | 199 / **23** |
| `drill_out_of_range` | 6 / **6** | 0 / 0 |
| every other category | unchanged / **0** | unchanged / **0** |

+20 total, +20 attributable. Every one is a pad-to-track pair in the
congested RTD/SPI corner, at 0.128–0.182mm against 0.2mm rules
(`Default routing`, netclass `GND`), e.g.

```
Clearance violation (rule 'Default routing' clearance 0.2000 mm; actual 0.1819 mm)
  * Via [RTD_CS_N] on F.Cu - B.Cu  @ (33.065, 31.020)
  * Track [PWM_HS] on B.Cu, length 0.1000 mm  @ (32.65, 30.25)
```

**This is a real cost and it is stated as one.** It is forced arithmetic, not
a choice: a 0.3mm drill cannot sit in a 0.8mm pad and clear the 0.254mm
annular floor (that ring is 0.250mm), so the pad must grow. The judgement
made here is that a hole the board cannot be drilled with is a hard
fabrication blocker, while these 20 are ~0.05mm of rerouting in an area this
repo already scopes to the separate router-congestion effort. Not silently
absorbed, and no clearance rule was touched to hide it.

### 4.5 Second placement

**Which placement, and why not model-E.** The referenced model-E placement is
produced by `isolation_barrier.barrier_setbacks()` with `per_pairing=True` at
a 20.0mm tank-creepage configuration. Neither `barrier_setbacks` nor
`per_pairing` exists on `origin/main` (they live on
`analysis/per-pairing-placer-solve`), and HEAD's
`DEFAULT_TANK_CREEPAGE_MM` is 10.0mm, not 20.0mm. Reproducing model-E would
require merging that branch, which this task forbids. Attempted anyway with
HEAD's own barrier + T1/T2 straddle exemption: **`infeasible` in 25.6s** — the
per-pairing setbacks are what make row E solvable, and they are not here.

So the second placement is the closest HEAD-native equivalent: the same
CP-SAT entry point (`solve_placement`), same seed 42, tank creepage at HEAD's
own default, isolation barrier off. **`optimal`, 32.1s, 168/168 placed**,
round-trip PASS (168 components / 521 pads), board containment PASS.
`pcb/temper.kicad_pcb` verified unmodified across the solve. It is a
materially different board — 3749 vs 4553 segments, 122 vs 169 vias, and a
completely different layer distribution (`In3.Cu` 1869 vs 1349, `B.Cu` 614 vs
1247). It is a **measurement vehicle for placement-independence, not a
proposed board**: it carries no isolation barrier and its `creepage` count is
correspondingly worse (222).

Per-category, 3 samples each. Nothing here is saturated: `silk_overlap` is 6,
`clearance` 123–124, both far from their caps.

| Category | before | after | delta |
|---|---|---|---|
| **`drill_out_of_range`** | **4** | **0** | **-4** |
| `clearance` | 124 | 123 | **-1** |
| `shorting_items` | 9 | 10 | +1 |
| `solder_mask_bridge` | 1 | 2 | +1 |
| `creepage` | 222 | 222 | 0 |
| `copper_edge_clearance` | 7 | 7 | 0 |
| `hole_clearance` | 12 | 12 | 0 |
| `hole_to_hole` | 0 | 0 | 0 |
| `via_dangling` (warn) | 75 | 75 | 0 |
| `silk_over_copper` (warn) | 12 | 12 | 0 |
| `silk_overlap` (warn) | 6 | 6 | 0 |
| `lib_footprint_mismatch` (warn) | 26 | 26 | 0 |
| `lib_footprint_issues` (warn) | 13 | 13 | 0 |
| `missing_courtyard` (warn) | 5 | 5 | 0 |
| `track_dangling` (warn) | 1 | 1 | 0 |
| `silk_edge_clearance` (warn) | 1 | 1 | 0 |
| **total violations** | 517 / 518 / 518 | 515 / 515 / 515 | **-2 / -3** |
| `unconnected_items` | 338 | 338 | **0** |

Same item-level attribution as §4.4, against this board's four touched via
positions: `drill_out_of_range` 4/4 -> 0; `clearance` naming a touched via
16 -> 15; the one new `shorting_items` and the one new `solder_mask_bridge`
each name a touched via. Everything else: 0 involvement, 0 delta.

**The trade in §4.4 is congestion-dependent, not intrinsic.** On this less
congested placement the same +0.1mm pad growth costs +2 and saves 4 — the
board total goes **down**. The committed placement's +20 is the price of six
enlarged pads landing in its densest corner, not a property of the fix.

### 4.6 Connectivity did not regress

**Committed placement** — every figure identical before and after:

| Metric | before | after |
|---|---|---|
| nets fully pad-connected (PRIMARY) | **60/139** | **60/139** |
| A*-routed nets | 34/105 | 34/105 |
| fake-completion | 6 | 6 |
| honest gap | 73 | 73 |
| `unconnected_items` (kicad-cli) | 339 | 339 |
| segments / vias / zones | 4553 / 169 / 151 | 4553 / 169 / 151 |

**Second placement** — likewise identical before and after:

| Metric | before | after |
|---|---|---|
| nets fully pad-connected (PRIMARY) | **53/139** | **53/139** |
| A*-routed nets | 29/105 | 29/105 |
| fake-completion | 8 | 8 |
| honest gap | 78 | 78 |
| `NetRouteResult` connected / zone-dep / partial / failed | 53 / 8 / 8 / 70 | 53 / 8 / 8 / 70 |
| `unconnected_items` (kicad-cli) | 338 | 338 |
| segments / vias / zones | 3749 / 122 / 127 | 3749 / 122 / 127 |

The router does **not** depend on the illegal geometry, on either placement:
the ten vias across the two boards stayed at their exact positions and kept
their layer pairs, so every path they close still closes. Zero connections
lost.

---

## 5. Test-suite effect

A fixed 23-file selection covering every via-geometry and route-emission
test, run identically in the pre-fix and post-fix builds (the pre-fix build
was produced by `git checkout` of the two changed files and a rebuild; **no
`git stash` was used**):

```
pre-fix : 10 failed, 521 passed
post-fix: 10 failed, 521 passed      <- same ten test names
```

The ten are pre-existing and none is caused by this change:

* 7 in `test_adapter_convert_marshal_rust_differential.py` /
  `test_pipeline_route_rust_differential.py` and 1 in
  `test_via_output_writer.py` — all the **2026-08-17 annular clamp** diverging
  from `_adapter_convert_py_oracle.py` / a `(size 0.6000)` fixture. Their
  inputs are drill 0.3 and 0.4, both at or above the new floor, so this
  change cannot touch them; the failure text is identical before and after.
* 2 in `test_design_rules_rust_differential.py`
  (`test_module_constants_identical`, `test_create_temper_design_rules_identical`)
  — a `net_class_assignments` disagreement, unrelated to via geometry.

**No pinned oracle was edited, re-pinned, deleted or consolidated.**

Gates, run directly against the fixed tree:

| Gate | Result |
|---|---|
| `scripts/check_fab_capability_floor.py` | **PASS** — P1 169 board vias, P2 14 net-class templates, P3 2 generator constants, all >= 0.254mm ring; P4/P5 the 0.28mm DRU rule |
| `scripts/check_stale_extensions.py` (`make extensions-check`) | **PASS** — 10/10 fresh |
| `scripts/gen_wasm_test_registry.py --crate temper-orchestration --check` | **PASS** — up to date, 1039 tests / 19 modules |
| `cargo test --lib pipeline_route` (temper-orchestration) | **21 passed, 0 failed** |
| `scripts/check_netclass_class_param_correspondence.py` | **FAILS, pre-existing and untouched** — 1 mismatch, `HighVoltageSignal.via_diameter` 1.0 (design_rules.py) vs 0.8 (kicad_pro). This change edits no net-class table, so it neither causes nor clears it. It is also the gate that makes §7's table fix indivisible. |

`cargo fmt --check` is **not** usable as a signal on this crate: every one of
its 58 source files and 11 test files drifts at HEAD, before this change.

---

## 6. The other two defects: root-caused, not fixed

### 6.1 Same-net vias stacked below the 0.5mm hole-to-hole figure

**Measured: `hole_to_hole` is 0 on all four routed boards here** (both
placements, before and after), and the static census (every via + every
through-hole pad, pairwise, edge-to-edge) finds **zero** pairs closer than
0.5mm on any of them. This defect does not reproduce in this branch's
configuration; the 2/2 the brief cites are on the model-E board that §4.5
could not reproduce.

The mechanism question the brief asked is nonetheless answerable from the
code. `router_v6/via_placement.py::drop_redundant_vias` quantizes positions
to `tolerance_mm = 0.02` and drops a via whose bucket already holds a same-net
hole. Two distinct limitations:

1. **It is a bucket match, not a distance test.** Two vias 0.019mm apart can
   round into adjacent buckets and both survive — a false negative against
   its own stated "coincident" goal, independent of the tolerance value.
2. **The tolerance cannot simply be raised to 0.5mm.** Its soundness argument
   — *"the kept/pre-existing hole already provides every electrical path the
   dropped via would"* — holds only **at** coincidence, because only then are
   the dropped via's trace endpoints already at the kept via's position. At,
   say, 0.3mm apart, dropping one leaves a 0.3mm gap in the trace and breaks
   the net. Raising the tolerance would trade `hole_to_hole` violations for
   silent connectivity loss.

The correct shape is drop-**and-bridge**: remove the near-coincident via and
emit a same-net stub joining the two points on both layers — exactly the
`needs_stub` mechanism `_ground_plane.py::_find_via_drop_point` already
implements for offset via drops. Not attempted here, because with 0
violations on both boards there is nothing to measure a fix against.

### 6.2 Copper past the 0.5mm board-edge clearance

`copper_edge_clearance` = **11** on the committed placement (7 on the second),
unchanged by this fix. Split by the geometry named:

| Kind | n | Distance to edge | Items |
|---|---|---|---|
| Routed track | 8 | 0.35 – 0.45mm | `safety-line-2` on In3.Cu (5), `fb` on B.Cu (3) |
| Stitching via | 3 | **0.094 – 0.17mm** | `gnd` (2), `vcc` (1) |

**The 3 via cases have a located root cause.**
`router_v6/_ground_plane.py::_find_via_drop_point`'s `_clear()` predicate
tests

```python
if not board_polygon.contains(footprint):
    return False
```

`contains()` requires the via pad to be **inside** the outline and demands
**zero** edge clearance, against the board's declared
`min_copper_edge_clearance` of 0.5mm. The module already has the right
figure and applies it elsewhere — `BOARD_EDGE_MARGIN_MM = 1.0` insets the
zone pour (`plane_region = board_polygon.buffer(-BOARD_EDGE_MARGIN_MM)`) —
and pass 1 of the search requires the via to sit inside that inset pour. The
leak is **pass 2**, the `require_pour=False` fallback taken when no
pour-inside point exists: it drops the pour requirement and falls back to
bare `contains()`, with no edge margin at all. `_power_islands.py` has the
identical structure (`board_polygon` passed raw to the same helper at
`_power_islands.py:702` while its own `BOARD_EDGE_MARGIN_MM = 1.0` is applied
only to the pour region).

The one-line correction is to inset the polygon that `_clear()` tests
against. It is **not** applied here because it is a fail-closed search: a
tighter containment test can return `None` more often, dropping stitching
vias and costing connectivity, which needs its own before/after route on both
placements to state honestly. Left as a located, reproducible defect rather
than an unmeasured change.

The 8 track cases are a different gap: the A* router has no board-edge
inset concept at all (`grep -rn "edge_clearance" router_v6/` returns only
`bottleneck_geometry.py`'s diagnostic labels and `quality/via_count.py`'s
metric). That is a routing-space change, not a clamp.

---

## 7. Left undone, deliberately

* **The net-class tables still declare the illegal drill.**
  `TEMPER_NET_CLASSES["FinePitch"]`, `netclass_rules.yaml`'s `FinePitch`, and
  `pcb/temper.kicad_pro`'s `FinePitch` (0.8/0.2) and `Differential`
  (0.85/0.25) should all move to 0.9/0.3, and `kicad_pro`'s
  `design_settings.via_dimensions` preset list should drop its 0.8/0.2 and
  0.85/0.25 entries. `Via::new` now corrects every *router-emitted* via
  regardless, so the board is conforming — but a via placed by hand in KiCad
  under the `FinePitch` net class would still be drilled at 0.2mm.

  **This is not done here because it cannot be done without editing a pinned
  oracle**, and this task's brief instructs: *"If it would alter a pinned
  oracle's output, STOP and report."* The lockstep set is forced and
  indivisible: `tests/core/test_design_rules_rust_differential.py::test_module_constants_identical`
  asserts `TEMPER_NET_CLASSES` equal to `tests/core/_design_rules_py_oracle.py`'s
  own copy field-by-field, and
  `scripts/check_netclass_class_param_correspondence.py` fails on any
  `design_rules.py` vs `kicad_pro` disagreement on `via_drill` — so changing
  any one of the four files without the other three turns a gate red.
  Precedent for doing all four exists (`c61db4710`, 2026-08-15, moved
  `FinePitch.trace_width` 0.127 -> 0.2 in `design_rules.py` **and** the
  oracle in one commit), but that is a call for the brief's author to make,
  not to be taken silently under an explicit STOP instruction.

* **The three Python via-emission sites that bypass `Via::new`.**
  `_ground_plane.py` (`VIA_SIZE_MM 1.0 / VIA_DRILL_MM 0.4`),
  `_power_islands.py` (same) and `_zone_pour_stitch.py` build `(via ...)`
  s-expressions as raw f-strings and never construct a `Via`, so the new
  floor does not cover them. The first two are compliant today (0.4mm).
  `_zone_pour_stitch.py` is **not** guaranteed to be: it takes
  `via_drill = rules.via_drill if rules else 0.4` straight from the net
  class, so a `FinePitch` stitch via would be 0.2mm, and its `else` fallback
  pair is `0.8 / 0.4` — a **0.20mm ring**, below the 0.254mm annular floor,
  the same shape as the stale default the 2026-08-17 fix root-caused in
  `io/_parse_nets.py`. Neither manifests on either board measured here (that
  path is gated by `_CONTINUITY_EXEMPT_NET_SMD_PAD_POSITIONS`), so this is
  reported as a latent defect, not a measured one.

* **`check_fab_capability_floor.py` has no drill-diameter property.** A P6
  asserting every net-class `via_drill` and every generator constant against
  the board's `min_through_hole_diameter` would have caught this defect at CI
  time. Not added here: it would fail immediately on the `FinePitch` /
  `Differential` declarations above, which is exactly the change that is
  blocked on the oracle question.

---

## 8. Compliance

`pcb/temper.kicad_pcb` was **never modified** — sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
before and after every step, including across the CP-SAT solve and both
placement applications; every candidate board went to a scratch path outside
the repo. No requirement was lowered: no clearance, creepage, copper-weight,
loop-area, ampacity, annular-ring, drill or DRU threshold was changed, and
`min_through_hole_diameter` was raised-to, never relaxed.
`MIN_ANNULAR_RING_MM`'s 0.254 is untouched. No test was skipped, xfailed,
deleted or relaxed; no ratchet raised; no allowlist broadened; no oracle
edited or re-pinned; `power_pcb_dataset/drc_ceiling.json` untouched; no
`git stash`. `silk_overlap`'s 199 is flagged as an `ERROR_LIMIT` saturation
floor everywhere it appears and is never quoted as an improvement.

## 9. Reproducing

```bash
env -u CONDA_PREFIX make venv-isolate && make extensions-check

# committed placement
python3 scripts/route_board.py --pcb pcb/temper.kicad_pcb --output /tmp/committed.kicad_pcb

# second placement (solve -> apply -> route). solve_alt_placement.py is this
# branch's own harness; apply-placement.py is borrowed unmodified from
# agent/per-pairing-placement-route @ bc3a19b06.
python3 docs/evidence/2026-08-19-via-hole-size-alt-placement.py --emit /tmp/alt.json
python3 <bc3a19b06>:docs/evidence/2026-08-19-per-pairing-route-apply-placement.py \
    --placement /tmp/alt.json --output /tmp/alt_placed.kicad_pcb
python3 scripts/route_board.py --pcb /tmp/alt_placed.kicad_pcb --output /tmp/alt.kicad_pcb

# drill census + near-coincident hole census (any board, stdlib only)
python3 docs/evidence/2026-08-19-via-hole-size-census.py /tmp/committed.kicad_pcb

# per-item attribution of every category to the vias the fix rewrote
python3 docs/evidence/2026-08-19-via-hole-size-attribution.py \
    --repo . --scratch /tmp/drc --boards /tmp/before.kicad_pcb /tmp/committed.kicad_pcb

# DRC, 3 samples, regenerated DRU + fp-lib-table staging. Harness borrowed
# unmodified from agent/per-pairing-placement-route @ bc3a19b06.
python3 <bc3a19b06>:docs/evidence/2026-08-19-per-pairing-route-measure-board.py \
    --pcb /tmp/committed.kicad_pcb --repo . --label committed --samples 3 \
    --scratch /tmp/drc

# the guard's own tests. NOTE: run with a PRIVATE CARGO_TARGET_DIR -- a plain
# cargo test on this crate compiles temper-geometry without its `python`
# feature and poisons the shared cache for every worktree.
CARGO_TARGET_DIR=/tmp/target-iso cargo test --lib pipeline_route \
    --manifest-path packages/temper-orchestration/Cargo.toml
```
