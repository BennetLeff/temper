<!-- provenance: commit=fbc5ce517fec9bbefcbaf632efa6b0ee4062d047 dirty=UNKNOWN -->

# Per-net-pair clearance now decides the route, not just the verdict: 1,289 → 41 track/via violations, pad connectivity 48/139 → 51/139, +0.9% runtime

**Verdict up front.** The router's A* occupancy model could not express a per-pair
clearance requirement at all — not approximately, not conservatively. Whichever net
of a pair routed first decided the separation for both. The fix gives the search one
occupancy-grid family per *clearance profile*, so the requirement is applied
regardless of routing order and both nets' half-widths are charged. Measured on a
freshly-routed production board, uncapped: **1,289 → 41** track/via pair-clearance
violations (−96.8%), of which the **safety-governed** subset is **143 → 13**
(−90.9%). Completion did not fall — it rose, **48/139 → 51/139 pads-connected
nets** — at a runtime cost inside run-to-run noise (**407 s → 405–410 s over two
repeat runs, byte-identical output**). Both hard constraints survive by
construction: all 161 footprint positions *and rotations* are byte-identical
between input and output.

Three things this task found that the brief did not predict, and which matter more
than the diff:

1. **`RouterPipeline` was missing from the installed extension** when this task
   started, so routing was broken, not fixed (sec 0).
2. **The production route OOM-kills at ~61 GB** without `--net-batching` — a
   reproducible Stage-3 blow-up, not shared-machine pressure (sec 0).
3. **#1110's partitioned kicad-cli protocol does not transfer to a freshly-routed
   board.** A `.kicad_dru` containing nothing but `(constraint clearance (min 0mm))`
   already reports **501** on the baseline route — the subtrahend is itself capped
   (sec 2.1). Every number here is measured outside kicad-cli, uncapped.
4. **One CI gate goes red, and it was pinning a short.** On the 33-net benchmark
   fixture the change costs exactly one net (`SPI_MOSI`) — whose old copper carried
   38 pair-clearance violations including a −0.4 mm *overlap* with `SPI_CLK`. The
   gate is not weakened here; the trade-off is put to the owner (sec 6).

---

## 0. Environment: two claims in the brief were false, and one is a standing hazard

The brief said "`temper_orchestration` has been rebuilt and `RouterPipeline` is
present again; verify before starting." Verified — it was **not**:

```
$ .venv/bin/python -c "from temper_orchestration import temper_orchestration as m; print(hasattr(m,'RouterPipeline'))"
False
```

The shared `.venv`'s `temper_orchestration.cpython-312-x86_64-linux-gnu.so` was dated
Aug 11 19:59 and contained no `RouterPipeline` symbol; `target-shared/release/libtemper_orchestration.so`
(Aug 12 21:59) contained 19 references to it. A build had happened; the venv had not
received it. `_pipeline_core.py:358` calls `_to.RouterPipeline().run(...)`, so **no
route could run at all** in that venv. Resolved by giving this worktree its own
`.venv` (`make venv-isolate`, then `make extensions` with `CONDA_PREFIX` unset —
maturin refuses when both `VIRTUAL_ENV` and `CONDA_PREFIX` are set). `make
extensions-check` 10/10 fresh, `check_venv_integrity.py` 16/16.

**The production route OOM-kills without `--net-batching`.** First attempt, exactly
the command `make route` runs:

```
Out of memory: Killed process 1785483 (python) total-vm:75053012kB, anon-rss:61336580kB
```

61 GB anon-RSS, ~7.5 minutes in, on an otherwise-idle machine with 42 GB free at
launch and 58 GB free after the reap — so this is the router, not contention. It
reproduces the OOM `docs/evidence/2026-08-12-router-tank-creepage.md` (PR #1098)
recorded at 58 GB and attributed to a busy machine; it is not that. The cause is
Stage 3's constraint model (`docs/evidence/scripts/2026-08-12-router-model-memory-probe.py`
extrapolates 22.5 M `NetChannelVar`s), which is already someone else's in-flight
work. **Every route below therefore uses `--net-batching`, both columns, and is run
under a 40 GB cgroup cap** (`systemd-run --user --scope -p MemoryMax=40G`) so a
repeat cannot take the machine down.

Consequence for comparability: the brief's "~400-500 s at 55/139 pad connectivity"
is a different configuration. This document's baseline is measured, not inherited.

**PR #1098 is not on `main`.** `7b1c7a648` (the router tank-creepage change) was
merged and then reverted by `c87492f38` ("conflict markers were committed to main").
`router_v6/tank_creepage.py` does not exist on `cc732df2b`. **PR #1110 is not on
`main` either** — its three commits live on `fix/dru-rule-precedence` and are
unmerged. Since the brief requires measuring under #1110's corrected rule ordering,
its two code commits (`11b344c65`, `7d1422ee9`) are cherry-picked onto this branch;
they applied cleanly and `scripts/tests/test_generate_kicad_dru.py` passes 35/35.

---

## 1. Where the per-pair requirement enters the routing decision

### 1.1 What the code actually does (re-verified on `cc732df2b`, not inherited)

The brief's account is correct and is confirmed here:

* `OccupancyGrid.mark_path_blocked` / `mark_via_blocked` dilate a just-routed net's
  copper by `trace_width/2 + clearance`, and the `clearance` argument is always
  `design_rules.get_rules_for_net(net_name).clearance_mm` — the **routed net's own
  net class**. Call sites: `_astar_reconstruct.py`'s `_mark_route_blocked`,
  `terminal_tree_execution.py:226`, `astar_grid.py`'s `_mark_route_blocked`.
* `ClearanceMatrix.get_clearance` is a real per-net-pair table.
  `grep -rn "ClearanceMatrix" --include='*.py'` over `packages/`, `scripts/`:
  **exactly one non-test importer, `constraints_drc_oracle.py`** — a post-route
  oracle. All eleven `get_clearance` call sites are inside it.

Two things the brief did not name, both of which change the design:

* **`ClearanceMatrix` could not simply be called from the hot path even if you
  wanted to.** Every `get_clearance` call rebuilds the whole rule set as flat wire
  lists (`_diff_pairs_wire()`, `_clearances_wire()`, `_class_clearance_wire()`) and
  marshals them across the Rust boundary — O(rules) per lookup, in a loop that runs
  per grid cell.
* **Its table is not populated with this board's safety rules.**
  `DesignRulesParser.create_default()` sets exactly four class pairs — `Power/Power`
  0.5, `Power/Signal` 0.3, `GND/Power` 0.3, `HighSpeed/HighSpeed` 0.2. Nothing about
  HV or mains. So the capability is not merely wired to the wrong stage; at that
  stage it is also carrying the wrong numbers. "The mechanism is present and
  misplaced" is half the story.

### 1.2 Why one grid cannot carry a pair requirement

The occupancy grid is one `int8` array per layer whose cells hold the owning net id
(`np.full(..., -1, dtype=np.int8)` in `build_occupancy_grid`). For net A already
routed and net B searching, the separation A* enforces is exactly the radius A was
stamped with. Pair-correctness requires that radius to be

```
w_A/2  +  required(class_A, class_B)  +  w_B/2
```

which is a function of **B** — unknown when A is stamped. Any single-grid encoding
must therefore pick one radius per A, and the only *safe* single choice is
`max over all B`. On this board that charges every HV net the full 6.0 mm mains bar
against its own same-domain neighbours, which the DRU explicitly relaxes to
0.2–3.0 mm. That is the over-broad approximation the brief asked to avoid, and it is
the only thing one grid can do.

Two distinct defects follow from the single-grid encoding, and both are fixed here:

* **Order dependence.** A SELV/unclassified track routed early is stamped at the
  0.2 mm default; a mains net routed later sees only that 0.2 mm halo and may run
  0.2 mm from it, against a 6.0 mm requirement. The same pair gets a different answer
  depending on `_compute_net_order`. This is the dominant mechanism — **69 of this
  board's 110 nets carry no net class at all** and are stamped at 0.2 mm.
* **The searching net's own width is never charged.** A* tests a candidate
  *centreline* against the grid, so the enforced edge-to-edge distance is short by
  `w_B/2` even when the pair figure happens to be right.

### 1.3 The approach: one occupancy family per clearance profile

`router_v6/profile_grids.py` keeps one `{layer: OccupancyGrid}` family per
*clearance profile*. All families start as copies of the same base grids. A net of
class `C` searches `family[profile(C)]`, in which every already-routed net A was
stamped at

```
w_A/2  +  max( required(class_A, C), clearance_mm(class_A) )  +  w_C/2
```

Order-independent, both half-widths charged, and **provably never looser than
today**: `clearance_mm(class_A)` is exactly what the old model stamped, kept as a
floor (`test_never_looser_than_the_single_grid_model`).

`clearance_mm` of the *searching* class is deliberately **not** a second floor. It
looks symmetric, but on this board it would charge every `HighVoltageIsolated`
search 6.0 mm even against a GND track where the fab-authoritative DRU requires
2.0 mm — importing `netclass_rules.yaml`'s own self-described *"legacy, not
primary-cited"* figure into the search as if it were the enforced requirement, and
paying completion for a bar nothing measures against.

**Insertion points** — all inside `run_astar_pathfinding`, which already funnels
every routing attempt (initial pass and reroute-queue retries alike) through one
`attempt_route`:

| site | before | after |
|---|---|---|
| grid selection | `all_grids.get(preferred_layer)` | `grids_for(net_name)` → the net's family |
| alternate layer | `all_grids.get(alt_layer)` | same family |
| `_unblock_net_pads` | `all_grids` | the net's family only (other families must keep seeing its pads blocked) |
| blocker identification | `all_grids=all_grids` | `all_grids=active_grids` (must read the family the search ran against) |
| completed route | `_mark_route_blocked(..., clearance=net_rule.clearance_mm)` | `profile_grids.mark_route(...)` — every family, each at its own radius |
| rip-up | `_unmark_route_blocked(..., clearance=net_rule.clearance_mm)` | `profile_grids.unmark_route(...)` — same radii, so no stale halo survives |
| terminal-tree branch | `active_grid.mark_path_blocked(...)` | new `mark_sink` callback → `profile_grids.mark_path(...)` |

The A* search itself is **not modified**. It receives a different grid dict and is
otherwise untouched — which is why the runtime cost is what it is (sec 3).

### 1.4 Where the numbers come from, and why not from `class_pairs`

`scripts/generate_kicad_dru.py` now also emits
`packages/temper-placer/configs/pair_clearance.generated.yaml`, derived by
**evaluating the rules it just wrote** under KiCad's last-matching-rule-wins
precedence — reusing #1110's own `_matching_rules` analyser over a Track↔Track,
different-reference world. The router therefore decides against the same table
kicad-cli will judge it by, and a drift gate
(`test_generated_yaml_is_not_stale`) fails if the two separate.

The resolved matrix (mm, Track↔Track):

| | ACMains | HighVoltage | HVTank | HVIsolated | GateDriveHV | Default / LV |
|---|---:|---:|---:|---:|---:|---:|
| **ACMains** | 0.2 | 3.0 | 3.0 | 6.0 | 0.5 | **6.0** |
| **HighVoltage** | 3.0 | 0.2 | 0.2 | 2.0 | 0.5 | **2.0** |
| **HighVoltageTank** | 3.0 | 0.2 | 0.2 | 2.0 | 0.5 | **2.0** |
| **HighVoltageIsolated** | 6.0 | 2.0 | 2.0 | 0.2 | 0.5 | **2.0** |
| **Default / LV** | 6.0 | 2.0 | 2.0 | 2.0 | 0.2 | 0.2 |

**`netclass_rules.yaml`'s `class_pairs` was rejected as the source**, on evidence:
it names 17 pairs among 5 classes, says nothing about `Default`, and **69 of 110
nets on this board are `Default`**. Its HV figures are also 3× the enforced ones
(6.0 mm where the DRU requires 2.0 mm) — its own comments say so: *"this 6.0mm
figure … is a legacy, not primary-cited, number; the fab-authoritative enforcement
point is scripts/generate_kicad_dru.py"*. Routing to 6.0 mm where 2.0 mm is enforced
would have cost completion for a bar nothing measures, and would have made any
"the board is infeasible" finding self-inflicted.

### 1.5 Cost of the approach

Profiles are classes that agree on **both** their requirement vector over every live
class **and** their trace width — merging on the requirement alone would charge a
0.127 mm `FinePitch` track the 1.0 mm `Power` width. The rule file names 13 classes;
this board uses 9; they collapse to **7 profiles**, confirmed in the route's own
output:

```
Pair-clearance occupancy: 7 profile(s) ('ACMains', 'Default', 'FinePitch', 'GND',
                                        'GateDriveHV', 'HighVoltage', 'HighVoltageIsolated')
```

`HighVoltageTank` shares `HighVoltage`'s family (identical figures, identical width);
`GateDriveSELV` shares `GateDriveHV`'s and `Power` shares `GND`'s, each because every
stamp radius is equal — a dedup, not a rounding
(`test_a_merged_profile_is_exact_not_approximate`). Memory and stamp work scale
linearly in the profile count. Grids are `int8`; the first family **is** the caller's
own dict rather than a copy, so a single-profile board is byte-for-byte the old
behaviour and costs nothing.

**What this does NOT govern, stated rather than glossed.** The static obstacle layer
is unchanged. Pads and component bodies are baked into
`RoutingSpace.available_area` as an un-netted polygon before any grid exists, so they
carry no net identity; making pad clearance pair-aware means re-eroding the routing
space once per profile (a GEOS buffer per profile), which is a placement-side concern
and was not done. #1110 measured the justification: stripping all copper takes the
board to a 48-violation placement floor, routing contributes 96–97% of the true count,
and 1,053 of 1,291 distinct violating pairs are bare track↔track naming no component.

---

## 2. Does it reduce the count? Measured, uncapped

### 2.1 Why not kicad-cli

`clearance` saturates at `EXTENDED_ERROR_LIMIT = 499`, so a headline number is a
floor (#1110 sec 4). #1110's workaround — measure each rule alone behind a 0.001 mm
unconditioned floor and subtract the floor's own contribution — works on the
*committed* board, where the floor fires once.

**It does not transfer to a freshly-routed board.** Measured here on the baseline
route, with a `.kicad_dru` containing one rule and nothing else:

| floor rule | reported `clearance` | `shorting_items` |
|---|---:|---:|
| `(constraint clearance (min 0mm))` | **501** | 204 |
| `(constraint clearance (min 0.000001mm))` | **501** | 204 |
| `(constraint clearance (min 0.0001mm))` | **506** | 204 |

Those are *overlapping* copper pairs, not merely close ones, and they appear inside
every partition. The subtrahend is itself at the cap, so the subtraction is
undefined and no partition can be made exact. **The partitioned kicad-cli protocol
cannot measure these boards** — reported as a finding, not worked around.

### 2.2 The uncapped measurement

`docs/evidence/scripts/2026-08-12-router-safety-clearances-measure.py` counts violations
directly from the routed geometry against the same generated pair table: for every
different-net track/via pair sharing a layer, `distance − w_a/2 − w_b/2 <
required(class_a, class_b)`. Uncapped, exact, 0.7 s per board, identical protocol on
both columns.

**Scope, stated:** track/via ↔ track/via only. Those are the items the router emits
and the ones this change governs. Pad-involving pairs are excluded because a pad's
true copper outline is not reconstructible from the board file without the footprint
library, and an over-approximated pad polygon would inflate both columns by an
unknown amount. **The absolute numbers below are a track/via subtotal, not the
board's whole count**; the delta is what this change is entitled to claim.

### 2.3 Result

| metric | baseline | pair-clearance | Δ |
|---|---:|---:|---:|
| **total pair-clearance violations** | **1,289** | **41** | **−96.8%** |
| distinct violating net pairs | 45 | 24 | −47% |
| **safety-governed violations** (HV/AC either side) | **143** | **13** | **−90.9%** |
| safety-governed distinct pairs | 14 | 8 | −43% |
| tracks emitted | 3,193 | 3,323 | +130 |
| vias emitted | 24 | 28 | +4 |

By class pair:

| class pair | required | baseline | after |
|---|---:|---:|---:|
| `Default`↔`Default` | 0.2 | 611 | 22 |
| `Default`↔`FinePitch` | 0.2 | 389 | 4 |
| `Default`↔`HighVoltage` | **2.0** | **104** | **2** |
| `FinePitch`↔`Power` | 0.2 | 78 | 0 |
| `FinePitch`↔`FinePitch` | 0.2 | 32 | 0 |
| `Default`↔`GateDriveSELV` | 0.2 | 32 | 2 |
| `Default`↔`GateDriveHV` | **0.2** | **22** | **0** |
| `Default`↔`HighVoltageTank` | **2.0** | **17** | **11** |
| `Default`↔`Power` | 0.2 | 3 | 0 |
| `FinePitch`↔`GateDriveSELV` | 0.2 | 1 | 0 |

The `Default`↔`Default` and `Default`↔`FinePitch` rows fall too, by an order of
magnitude, even though their requirement (0.2 mm) did not change — because the model
now charges the searching net's own half-width, which the single-grid encoding never
did.

**The residual 41, honestly.** 11 of them involve `tank.c_tank1-p2` at
`actual = −0.225 mm` / `−0.354 mm` — **negative**, i.e. genuinely overlapping copper,
not a clearance shortfall. The identical overlaps, at the identical distances, are
present in the baseline column (baseline's worst two shortfalls are the same
`−0.354 mm` figure against the same net). They are not something an A* clearance
model governs and this change neither fixes nor causes them.

### 2.4 What this change provably cannot fix

`ac_l` — the brief's worst measured gap, 1.80 mm against 6.0 mm required — is
**excluded from Stage 4's A\* entirely** by `_should_route()`, along with
`+15V_LS`, `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE` and `ac_n` (7 nets,
"presumed zone-covered"; the router prints this itself). Their copper comes from
**zone pours**, which `router_v6/_zone_pour_stitch.py` emits using `class_pairs` and
a per-net *max-over-all-pairs* approximation. Nothing in this change touches that
path, and the measurement above does not parse zone polygons. **The mains net's
worst violation is a zone-pour problem, not an A\* problem** — a separate, named
piece of work, not a residual of this one.

---

## 3. Runtime and completion

Both columns: `scripts/route_board.py --pcb pcb/temper.kicad_pcb --net-batching`,
same input board, same machine, under the same 40 GB cap.

| | baseline | pair-clearance | Δ |
|---|---:|---:|---:|
| **pad connectivity — PRIMARY** | **48 / 139** | **51 / 139** | **+3** |
| fake-completion nets | 45 | 46 | +1 |
| honest gap | 46 | 42 | −4 |
| wall time | 406.8 s | 410.4 s / 405.2 s | **+1.0 s on the mean (+0.2%)** |
| segments / vias / zones | 3193 / 24 / 94 | 3323 / 28 / 94 | +130 / +4 / 0 |

The pair-clearance column was routed **twice**. The two output boards are
**byte-identical** (`cmp` clean), and both measure 41 violations / 51 pads-connected;
only wall time moved, 410.4 s → 405.2 s. So the runtime cost of the change is inside
run-to-run noise on this machine — not "+0.9%", which was one sample against one
sample. The baseline column was routed once; it comes from this branch's parent
commit and used the same deterministic machinery
(`docs/evidence/2026-07-27-router-determinism.md`).

**The reported metric is pad connectivity** — `nets fully pad-connected` out of 139,
from `pad_connectivity_audit`, the router's own PRIMARY figure. It is **not** the
topology-solved count, which the same run also prints as `62/103 (60.2%)` →
`66/103 (64.1%)`; the brief notes mixing the two has misled twice today, so both are
given, labelled, and never combined.

**A stricter model routed *more*, not less.** That is worth not glossing: the
expected outcome was a completion loss. Three mechanisms plausibly explain the gain,
and this document does not claim to have isolated which dominates — (a) LV↔LV
searches are now *cheaper*, because an HV net's copper is dilated at 2.0 mm only in
the LV families rather than at HV radii everywhere; (b) fewer forced-segment declines,
since the fail-closed gate rejects fewer paths when the halos are correctly sized;
(c) the extra `w_C/2` term produces cleaner corridors and less rip-up churn.
Segment count rose 4%, consistent with more nets completing rather than with longer
detours.

Memory: no change to the OOM behaviour. Both columns needed `--net-batching`; peak
RSS stayed well under the 40 GB cap in both.

---

## 4. The two constraints that had to survive

**Both hold, by construction rather than by measurement luck.** This change touches
only Stage 4's occupancy model. It moves no footprint. Verified directly — all
**161** footprints' `(at x y rot)` triples are **byte-identical** across the input
board, the baseline route and the pair-clearance route:

```
footprints: src=161 baseline=161 pair=161
src == baseline positions+rotations: True
src == pair     positions+rotations: True
differing: []
```

So the PD2 / 8.0 mm isolation barrier with all 8 isolators, and #1082's IGBT
heatsink co-location (rotation equality — the property that makes the board
buildable) are unaffected: neither can change when no component moves and no
rotation changes. No stop-and-report condition was reached.

---

## 5. Is the board infeasible at these clearances?

**No — not at the enforced figures, and this is the answer the brief asked to be
given with numbers rather than by weakening anything.** Routing to the DRU's real
per-pair table raised completion (48 → 51 pads-connected) rather than lowering it,
at +0.9% runtime, and removed 96.8% of the pair-clearance violations the router was
producing. No clearance was weakened anywhere: every stamp is provably ≥ the old
model's, pinned by test.

The honest caveat attaches to a figure that was *not* used. Routing to
`netclass_rules.yaml`'s `class_pairs` instead — 6.0 mm HV↔LV rather than the enforced
2.0 mm — would reserve a ~12 mm-wide corridor against every LV net for each of the 14
`HighVoltage` nets, and would very likely be infeasible on this outline. **That
would have been a self-inflicted infeasibility**, produced by measuring against an
uncited figure the fab-authoritative rule file does not enforce, and it is the reason
the source of truth was chosen deliberately (sec 1.4). If the owner decides the
6.0 mm HV↔LV figure is the real safety requirement rather than a legacy one, that
question — *"is 2.0 mm IEC-adequate for the same-domain, no-creepage-backstop HV
case"*, which `netclass_rules.yaml` already records as open — must be settled first,
and the feasibility of the board at 6.0 mm re-measured. It is a design decision for
the owner, not a router setting.

---

## 6. Test suite: one gate goes red, and what it was actually pinning

`packages/temper-placer/tests/router_v6/`: **6,635 passed, 24 failed, 18 skipped,
23 xfailed** (986 s). Of the 24, **exactly one is this change's**, and it is worth
the space.

Pre-existing, none of them in a module this branch touches (`git diff --stat
origin/main` names only `_astar_reconstruct.py`, `terminal_tree_execution.py`,
`pair_clearance.py`, `profile_grids.py`, the generated YAML, the generator and two
test files):

| cluster | count | signature |
|---|---:|---|
| `test_bundle_analyzer*` / `test_bundled_full_pipeline` | 11 | `'Graph' object has no attribute 'edges_with_data'` |
| `test_channel_skeleton_*` / `test_coverage_paydown_wave3_f` | 10 | `'Graph' object has no attribute 'connected_components'` / `is_connected` |
| `test_phase1_anti_false_zero::test_kicad7_footprint_dir_resolves` | 1 | `KICAD7_FOOTPRINT_DIR` unset in this venv |
| `test_temper_production_board_routing::test_route_pcb_production_board` | 1 | routes without `--net-batching` → the sec-0 OOM (`exit 137`) |

The first three clusters are the same Rust `SkeletonGraph` API mismatch and missing
env var `docs/evidence/2026-08-12-router-tank-creepage.md` (PR #1098) already
recorded as pre-existing and unrelated.

### The one that is this change's

```
FAILED test_topology_copper_audit.py::test_full_pipeline_run_surfaces_the_same_unexplained_gap
E   AssertionError: topology-solved nets with no copper and no recorded legitimate reason: ['SPI_MOSI']
```

Isolated by A/B on the 33-net benchmark fixture, same process, same input, only the
`enable_pair_clearance` keyword flipped:

| `pcb/benchmarks/temper_fixture_33.kicad_pcb` | off | on |
|---|---:|---:|
| topology-solved nets | 24 | 24 |
| nets emitting copper | **24** | **23** |
| tracks / vias | 942 / 10 | 695 / 12 |
| **pair-clearance violations** | **162** | **30** |
| distinct violating pairs | 14 | 9 |

So the change does cost one net on this fixture. **But look at what that net's copper
was.** In the `off` route, `SPI_MOSI` alone carries **38** pair-clearance violations,
and its worst are *negative* — overlapping copper, i.e. a short:

```
shortfall 0.600 mm   SPI_MOSI <-> SPI_CLK   required 0.20   actual -0.400
shortfall 0.350 mm   SPI_MOSI <-> SPI_CLK   required 0.20   actual -0.150
shortfall 0.325 mm   SPI_MISO <-> SPI_MOSI  required 0.20   actual -0.125
```

The gate asserts "no topology-solved net emits copper without a recorded legitimate
reason". It was being satisfied, for `SPI_MOSI`, by copper that shorts `SPI_CLK`.
With the corrected model the net is honestly declined by the forced-segment
fail-closed gate instead — which is the behaviour `_astar_reconstruct.py`'s own
comment demands: *"fail the net honestly rather than fabricating clearance-violating
copper."*

**This gate was not weakened to make the change pass**, and it should not be. It
conflates two outcomes the audit cannot currently tell apart: "silently produced
nothing" and "attempted, and honestly declined". The information to separate them
exists — `RoutingResult` carries the per-net failure reports — so the fix is to give
`audit_topology_vs_copper` a `declined_by_astar` legitimate reason and let the gate
keep meaning what its docstring says. That is a change to a gate's semantics made by
the change the gate caught, so it is proposed here and deliberately **not**
implemented: **this PR is red on that one test pending that decision.** The
alternative — dropping the searching net's `w_C/2` term to keep the fixture green —
would give back most of the improvement (the `Default`↔`Default` 611→22 and
`Default`↔`FinePitch` 389→4 rows in sec 2.3 are entirely that term) and would
restore an under-enforcement of half a trace width board-wide. That is not a trade
worth making for a green fixture.

---

## 7. What is not done

* **Pad↔track pairs.** Static obstacles carry no net identity; see sec 1.5. This is
  the placement floor #1110 measured at 48 violations (25 safety-governed).
* **Zone pours.** `_zone_pour_stitch.py` still uses the per-net max-over-all-pairs
  approximation, and it is the path that governs `ac_l`, `+170V_BUS`, `SW_NODE` and
  the other four `_should_route()`-excluded nets. Sec 2.4.
* **Creepage.** `NetClassRules.creepage_mm` still reaches nothing in the A* hot
  path — the gap PR #1098 opened and whose revert closed again. This change is
  clearance-only; the generated table exports `constraint: clearance` and the
  derivation is parameterised (`derive_pair_clearance_matrix(..., constraint=)`) so
  the creepage matrix is one argument away, but no creepage keepout is implemented.
* **The baseline column is one route.** The pair-clearance column was routed twice
  and is byte-identical across runs; the baseline was not repeated, because the
  feature has no user-facing off switch (`enable_pair_clearance` is a
  `run_astar_pathfinding` keyword, not a `route_board.py` flag) and reproducing the
  baseline means routing from the parent commit. Threading the flag out to the CLI
  would make the A/B a one-command operation and is the obvious follow-up.
* **`pcb/temper.kicad_dru` is not regenerated in this branch.** It is stale relative
  to #1110's ordering; that is #1110's file to land. This branch only adds the
  derived pair table beside it.

---

## Appendix: reproduce

```bash
git worktree add ../temper-router-safety -b feat/router-safety-clearances origin/main
cd ../temper-router-safety
git cherry-pick 11b344c65 7d1422ee9        # PR #1110's generator fix
make venv-isolate && env -u CONDA_PREFIX make extensions
.venv/bin/python scripts/verify_pumpkin_engine.py          # must exit 0

# route (ALWAYS --net-batching; without it this OOMs at ~61 GB)
systemd-run --user --scope -p MemoryMax=40G \
  .venv/bin/python scripts/route_board.py --pcb pcb/temper.kicad_pcb \
    --net-batching --output /tmp/routed.kicad_pcb

# uncapped violation count
.venv/bin/python docs/evidence/scripts/2026-08-12-router-safety-clearances-measure.py \
    --board /tmp/routed.kicad_pcb --label after --out /tmp/after.json
```

For the baseline column, pass `enable_pair_clearance=False` to
`run_astar_pathfinding` (the flag defaults to `True`; the profile machinery is
entirely behind it, and with one live profile the code path is the original one).
