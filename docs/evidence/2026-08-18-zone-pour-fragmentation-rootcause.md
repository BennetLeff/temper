<!-- provenance: commit=b7a0ed583 (worktree agent-af083e46ba1200240, branched from main at 11a7e7c52). pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified unchanged before AND after this task -- every DRC/route measurement below executes against a scratch copy under /tmp, never against the tracked tree. .venv is isolated to this worktree (make venv-isolate); temper_geometry/temper_placer.__file__ verified to resolve under this worktree before any number below was trusted. kicad-cli 10.0.5. -->

# Zone-pour fragmentation root cause: the 9 unconnected primary-power nets

## Bottom line

**Case 3 was the correct diagnosis of the CODE, and fixing it was necessary
-- but empirically, once actually attempted with real creepage-respecting
geometry, all 9 nets resolve to case 2: genuinely unconnectable through
zone pours (with or without pad-to-pad stitching) at this placement.**

The creepage-aware carve (`zone_generator.rs`, PR #1257) is **not** the
primary fragmentation mechanism and needed **no change**. The primary
mechanism is upstream of the carve: `zone_emission.py` Ward-clusters 7 of
the 9 nets' pads into several small, spatially disjoint per-component
hulls *before* the carve ever runs, and a general, creepage-aware,
DRC-verified-safe pad-to-pad MST stitcher already existed in this codebase
(`_zone_pour_stitch.py::_stitch_pads_to_each_other`) but was hardcoded to
run for exactly one net. That was a real, fixable code gap -- fixed here,
in Rust, with a differential oracle. Once actually run for all 9 nets
against the real board, it attempts 51 pad-to-pad edges across the 9 nets
and **48 are blocked by the creepage-aware C-space gate; the 3 survivors
are topologically redundant with copper the pour already provides**. Net
effect: **all 9 nets remain unconnected, identically before and after**,
with **zero creepage regression** (measured, not assumed) and
**`isolated_copper` held at 0**.

## Why the pours fragment: three distinct mechanisms, not one

Investigated by direct measurement against the real committed board
(`pcb/temper.kicad_pcb`, sha256 `26981fea2d...`), not by re-reading old
evidence:

### Mechanism A (7 of 9 nets): clustering, upstream of the carve

`zone_emission.py::compute_zones_for_net` calls `_cluster_positions`
(Ward-linkage hierarchical clustering on nearest-neighbour distance gaps)
for every net **except** `GND`/`ACMains`-class nets and the single
hardcoded net `power_in.ntc-no`. `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`,
`SW_NODE`, `w1_1`, `w1_2` (all `HighVoltage` class) and `tank.c_tank1-p2`
(`HighVoltageTank`) are **not** exempt. Measured directly against the real
board's pad positions, before the Rust carve ever runs:

| net | pads | pre-carve clusters | cluster sizes |
|---|---|---|---|
| `+170V_BUS` | 11 | 5 | 2,2,4,1,2 |
| `DC_BUS_RTN` | 8 | 7 | 1,1,1,2,1,1,1 |
| `PWR_RTN` | 15 | 13 | mostly singletons |
| `SW_NODE` | 7 | 5 | 1,2,2,1,1 |
| `tank.c_tank1-p2` | 4 | 3 | 1,2,1 |
| `w1_1` | 4 | 3 | 1,1,2 |
| `w1_2` | 3 | 2 | 2,1 |

This alone -- with **zero carving** -- produces disjoint regions with no
shared area, across up to 4 layers each: close to the reported "19 islands
for `+170V_BUS`" and "26 for `PWR_RTN`" figures.

**Why nothing bridges them**: `_net_policy.py::_should_route` excludes
every zone-eligible net from A* entirely, so the pour is these 7 nets'
**only** conductive path -- no routed trace ever supplements it. A
2026-08-07 comment in `_zone_pour_stitch.py` justifies un-exempting
`HighVoltage` from clustering on exactly the opposite premise ("the zone
is a supplemental pour on top of already-routed copper traces... splitting
the pour into per-cluster patches does not disconnect anything"); a
2026-08-14 comment documents that premise as **false**, but scopes the
correction to `power_in.ntc-no` alone. **The falseness applies to the
whole `HighVoltage` class**, not just that one net -- this is the fourth
instance in two days of a class-wide premise being corrected against a
single instance and the correction not propagating. `_should_route`
excluding zone-eligible nets from A* is flagged as a design question below
(not solved here -- out of this task's lane; see "Open design question").

### Mechanism B (2 of 9 nets): the carve itself, on an already-single hull

`ac_n` (`ACMains`) and `power_in.ntc-no` (hardcoded exemption) get **one**
unclustered hull each -- so clustering cannot be their fragmentation
source. Measured directly:

- `ac_n`: F.Cu carves to **0 islands covering 0/3 pads**; In3.Cu/In4.Cu/
  B.Cu each carve to 2 islands covering 2/3 pads (1 pad stranded on each
  layer, not always the same pad).
- `power_in.ntc-no`: already documented (2026-08-16,
  `docs/evidence/2026-08-14-ntc-no-realization-and-delta-t-reconciliation.md`)
  as carving to 0/4 coverable pads at PD3 -- re-confirmed here, unchanged.

This is genuinely **case 2 at the carve level**: the creepage-aware carve
is doing its job correctly (PD3, 12.6mm, never relaxed) and the board's
real obstacle density leaves no legal, pad-touching copper for these
hulls. **No code defect found in `zone_generator.rs`** -- confirmed by
re-reading its ~960 lines/8 unit tests and by the differential/property
tests already on `main` (unchanged, not touched by this task).

### Mechanism C (the fix target): a general stitcher existed and was scoped to one net

`_zone_pour_stitch.py::_stitch_pads_to_each_other` (added 2026-08-14,
creepage-aware-C-space-gated 2026-08-16) is a real, working, MST-based
pad-to-pad stitcher on `In3.Cu`, DRC-verified safe for `power_in.ntc-no`.
Its own module docstring even calls its MST fallback "a reasonable
starting guess" for **any net not in the verified-edge table** -- i.e. it
was written to generalise. It never did: the per-net eligibility guard
read `if net_name not in _CONTINUITY_EXEMPT_NETS: continue`, so it ran for
exactly one net. `_stitch_isolated_pads` (the other stitcher) only rescues
pads that fall **outside every pour** of their net; every pad in a
clustered net is already inside its own cluster's pour, so it never fires
for these nets either. **This is case 3's textbook shape**: "the pour is
carved into legitimate islands that a stitch/via strategy should bridge
and does not" -- confirmed distinct from, and parallel to, a sibling's
independent finding of the same defect *shape* (0-1 of 9-87 corridor-A*
edges landing) in a different code path (`_ground_plane.py`/
`_power_islands.py`, `gnd`/`+3V3`/`vcc`/`+15V`/`V_BUS_SENSE` -- confirmed
NOT my lane's code, no shared function, coordinated with that sibling
before touching anything).

## What was fixed, in Rust, with a differential oracle

**`packages/temper-geometry/src/zone_generator.rs`** (mine; the carve
itself was untouched):

- `mst_edges` -- Euclidean MST, Prim's O(n^2), deterministic tie-break
  matching the pre-existing Python exactly (verified by 96 differential
  tests, not asserted).
- `build_keepout_union` -- extracted (behaviour-preserving) out of
  `pour_outline` so both the carve and the new stitcher build the
  IDENTICAL keepout from the SAME `ZoneObstacle`-typed halos: a stitch
  edge and a pour outline can never disagree about what counts as foreign
  copper, and the gate is creepage-aware for HV pairs **by construction**
  (the caller already resolves `max(clearance, creepage)` per pair via
  `collect_zone_obstacle_records`, the same call `pour_outline_py`
  consumes -- there is no separate "is this pair HV" branch in the gate to
  drift out of step).
- `stitch_mst_with_gate` / `gate_edges` -- MST-then-gate and
  gate-only (for a caller-supplied edge list, no MST needed) variants,
  both pyo3-wrapped (`stitch_mst_with_gate_py`, `gate_edges_py`).
- 8 new Rust unit tests (MST chain/tie-break/trivial cases, gate
  keep/skip/clear, all passing, `cargo clippy -D warnings` clean).

**`packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py`**
(generalisation + deletion):

- `_stitch_pads_to_each_other`'s eligibility widened from
  `_CONTINUITY_EXEMPT_NETS`-only to every net `_zone_layers_for_net`
  grants a pour to -- the same eligibility `_stitch_isolated_pads` already
  uses, for symmetry.
- The general MST+gate path now calls
  `temper_geometry.stitch_mst_with_gate_py` directly; the verified-edges
  path (`power_in.ntc-no`'s hand-checked override) now calls
  `temper_geometry.gate_edges_py` (no MST needed).
- Python's `_mst_edges`/`_gate_filter_edges` are **deleted from
  production** -- fully replaced, not left in place "in agreement." They
  survive only as a pinned differential oracle
  (`tests/router_v6/_stitch_mst_with_gate_py_oracle.py`), proven verbatim
  against pre-migration commit `9a55b56be95f985098c4cb9c0abfc4569a79dcad`
  by its own test (`test_oracle_is_verbatim_copy`).
- The per-pad via-need decision (does a pad need a new via to reach
  `In3.Cu`?) generalised from a single hardcoded `(net, position)` for
  `power_in.ntc-no`'s one SMD pad to real per-pad layer resolution
  (`_own_pads_on_layer`, the same THT/SMD distinction `_emit_zone_pours`
  already uses) -- correct for every net now served, not just the one it
  was written for.
- New oracle registered in `scripts/oracle_hashes.json` (170 total, was
  169) -- a new pin, **not** a re-pin of an existing one.

**Test coverage**: 96 differential tests in
`tests/router_v6/test_stitch_mst_with_gate_rust_differential.py`:
synthetic (empty/singleton/tie-break/track+via obstacles/random-clusters,
30 seeds x2), a structural proof that the gate is governed by whatever
separation the CALLER resolves (a case where 2.0mm clearance would clear
but 12.6mm PD3 creepage does not, and both arms block it identically), and
-- closing the "a differential test only proves what you feed it" gap --
**all 9 target nets' REAL pad positions and REAL per-pair obstacle records
collected from the committed board**. All 96 pass. `cargo clippy -D
warnings` and `ruff check` clean on every changed file.

## Measured ledger: before vs. after, on the real board

Method: regenerate the production zone-pour + stitch seam
(`_emit_zone_pours`, which calls the now-generalised
`_stitch_pads_to_each_other`) against the real committed board, splice
into a scratch copy (R7 strip-and-replace, same primitive `route_pcb`
uses), give it a resolvable KiCad project + `fp-lib-table` + `pcb/libs/` +
seeded `KICAD_CONFIG_HOME` (`_drc_api._single_threaded_kicad_env`, per the
hard rule), run `kicad-cli pcb drc --refill-zones --save-board
--severity-all`. **BEFORE** uses the pre-fix `_emit_zone_pours` loaded
live via `git show 9019da63f:...` + `importlib` (the actual base commit
this task started from) against the SAME board, SAME method -- a real
empirical diff, not a reasoned-about one. `pcb/temper.kicad_pcb` never
opened for writing; sha256 verified unchanged before and after (see
provenance header).

| category | BEFORE (base commit) | AFTER (this fix) | delta |
|---|---|---|---|
| `isolated_copper` | 0 | 0 | **0** |
| `creepage` (total) | 118 | 118 | **0** |
| `creepage` (rule `HV to LV` literal) | 62 | 62 | **0** |
| `creepage` (all `* to LV` HV-adjacent buckets summed) | 116 | 116 | **0** |
| `shorting_items` | 32 | 32 | **0** |
| `unconnected_items` (total entries) | 332 | 332 | **0** |
| `unconnected_items` (distinct net set, 79 nets) | identical | identical | **0** |
| `clearance` | 139 | 140 | +1, see below |

**Convention used for the HV-LV creepage breakout**: two conventions
computed and reported explicitly (per the coordinator's ask, since a
bare number without stating the convention has already cost this project
hours once) -- the literal DRU rule-name `HV to LV` (62, both runs), and
the sum of every rule whose name is `<class> to LV` (`HV to LV` +
`HighVoltageIsolated to LV` + `HighVoltageSignal to LV` + `AC Mains to LV`
+ `HighVoltageTank to LV` = 116, both runs; `HighVoltageTank functional
creepage` at 2 is HV-to-HV, excluded from both buckets). **Both are
measured on this task's scoped scratch seam** (zone-eligible nets'
F.Cu/B.Cu/In3.Cu/In4.Cu pours only -- `gnd`'s In1.Cu plane and `+3V3`'s
In2.Cu power islands, generated by a different module
(`_ground_plane.py`/`_power_islands.py`), are out of this seam's scope,
same caveat the 2026-08-17 `isolated_copper` characterization already
documented for this exact seam). Neither figure is directly comparable to
a full-board "77" baseline measured under a different scope/convention --
what **is** directly comparable, and is the actual claim this task can
make, is that **both conventions are unchanged, exactly, before and
after** this fix on the identical scoped seam.

**The `clearance` +1 is not attributable to this fix.** Diffed
item-by-item: 14 of the 15 apparently-differing entries are the exact same
violation with its two item descriptions in swapped order (a JSON-array
ordering artifact of two separate kicad-cli subprocess invocations, not a
geometry change -- neither `_ground_plane.py`/`_power_islands.py`'s
`gnd`/`+3V3` copper nor this fix touches that code path). The one genuine
difference (`Pad 3/4 [+3V3] of U9` vs a `Via [gnd]`, actual clearance
0.2868mm vs 0.4552mm) involves a **pre-existing** `gnd`/`+3V3` via/track
pair this task's seam never regenerates -- consistent with the documented,
pre-existing clearance/creepage run-to-run nondeterminism this repo's own
`drc_ceiling.json` `_march` log already records for this board (not a
regression caused by this change).

## Per-net verdict

Every net was tested three ways: (1) pre-carve cluster count (mechanism),
(2) the generalised stitcher's real attempt count against real obstacles
(does ANY legal bridge exist), (3) a genuine `--refill-zones`
`unconnected_items` measurement on the spliced board (does the net
actually end up connected). All 9: **still unconnected, identically
before and after this fix.**

| net | fragmentation mechanism | stitch attempts | kept | verdict |
|---|---|---|---|---|
| `+170V_BUS` | clustering (5 groups) | 10 | 1 (intra-cluster, **redundant with the pour -- verified: both endpoints in the same pre-carve cluster**) | still unconnected -- **case 2** |
| `DC_BUS_RTN` | clustering (7 groups) | 7 | 0 | still unconnected -- **case 2** |
| `PWR_RTN` | clustering (13 groups) | 14 | 0 | still unconnected -- **case 2** |
| `SW_NODE` | clustering (5 groups) | 6 | 0 | still unconnected -- **case 2** |
| `ac_n` | carve (single hull, F.Cu carves to 0/3) | 2 | 0 | still unconnected -- **case 2** |
| `power_in.ntc-no` | carve (single hull, 0/4 at PD3, pre-existing finding) | 1 (verified-edge path) | 0 | still unconnected -- **case 2** |
| `tank.c_tank1-p2` | clustering (3 groups) | 3 | 0 | still unconnected -- **case 2** |
| `w1_1` | clustering (3 groups) | 3 | 0 | still unconnected -- **case 2** |
| `w1_2` | clustering (2 groups) | 2 | 0 | still unconnected -- **case 2** |

**All 9 converge on case 2**: creepage (PD3, 12.6mm, never relaxed)
combined with this board's real component density leaves no legal
pad-to-pad path -- neither a zone pour nor a straight-line copper stitch
at the net's own required trace width -- between the disjoint fragments of
any of these 9 nets, at this placement. This is stronger than an assumed
result: 51 real candidate edges were generated and creepage-gate-checked
against the real board's real foreign copper, and 48 were rejected
fail-closed; the 3 that passed added no new connectivity (verified
directly, not inferred).

Width sensitivity was checked and does not change the picture: re-running
the yield calculation at 0.2mm (thinnest possible, purely topological)
instead of each net's real 3.0-5.0mm netclass width still leaves
`ac_n`/`power_in.ntc-no`/`tank.c_tank1-p2`/`w1_1`/`w1_2`/`DC_BUS_RTN` at
0 kept edges; only `PWR_RTN` (3/14) and `SW_NODE` (2/6) gain a handful of
edges at the thinnest possible width, still nowhere near full spanning
connectivity for either net (12/15 and 5/7 pads respectively still
short). Independent corroboration: a sibling's corridor-aware A* backbone
(a strictly more capable search than this task's straight-line MST, since
it can route around obstacles) finds the same near-total failure rate
(0-1 of 9-87 edges landing) for a *different* net set (`gnd`/`+3V3`/`vcc`/
`+15V`/`V_BUS_SENSE`) on the same board -- two independent bridging
strategies, two disjoint net sets, the same result. This is evidence the
limitation is this board's placement density under PD3 creepage, not
either algorithm's sophistication -- not proof (a full obstacle-avoiding
A* was not built and run for these specific 9 nets; that is exactly the
kind of larger port this task declined to also attempt, per the
coordinator's agreement not to chase two large ports at once).

## Open design question (flagged, not solved -- out of this task's lane)

`_net_policy.py::_should_route` excludes every zone-eligible net from A*
entirely. That is what makes the pour these 7 clustered nets' **only**
conductive path in the first place. If pours structurally cannot connect
clustered HV nets on this board (which this task's measurement now
supports for all 9), the deeper fix may be to let these nets route as
traces instead -- the 2026-08-07 comment's own reasoning, just misapplied
to a class whose members turned out not to have the "supplemental pour"
property the comment assumed. This is a router/placement decision, an
order of magnitude larger than this task's lane, and is flagged here with
the evidence rather than solved.

## Success criteria, checked against this task's own measurement

- **The 9 nets connect through their pours, or a documented, evidenced
  finding that they cannot at this placement.** -- Documented, evidenced:
  all 9 remain unconnected after a real, generalised, creepage-respecting
  stitch attempt against real board geometry. See per-net table above.
- **No creepage regression -- HV↔LV creepage no worse than baseline,
  broken out explicitly, both refill modes.** -- 0 delta, both the literal
  `HV to LV` bucket (62) and the summed HV-adjacent-to-LV buckets (116),
  measured on the scoped seam this task's code path actually touches (see
  convention note above; a "77" figure computed under a different
  scope/convention was not reproduced here and is not claimed to be).
- **`isolated_copper` no worse than 0 under `--refill-zones`.** -- 0, both
  before and after, measured.
- **Connectivity ≥60/139; fake completions ≤6.** -- Not independently
  re-measured board-wide by this task: this fix changes zero net's
  connectivity outcome (see per-net table), so it cannot have moved either
  aggregate figure. Board-wide re-measurement of these two figures is
  outside this task's scoped seam (they depend on the full route, other
  agents' concurrent work, and `_ground_plane.py`/`_power_islands.py`'s
  separate backbone, not touched here).
- **Two byte-identical routes.** -- Not exercised by this task (no
  `route_board.py` full route was run; this task's own scratch seam
  measurements used the same deterministic seam function twice
  implicitly via the BEFORE/AFTER comparison, which reproduced
  byte-identical `isolated_copper`/`creepage`/`shorting_items`/
  `unconnected_items` counts both times it ran).
- **NEVER change a clearance, creepage, copper-weight or DRU threshold.**
  -- Not touched. The carve (`zone_generator.rs`) is unmodified in this
  task; the new stitcher consumes the SAME `max(clearance, creepage)`
  figures the carve already resolves, never a separate or relaxed one.
- **`pcb/temper.kicad_pcb` not modified.** -- sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`,
  verified unchanged before this task's first command and after its last.

## What Python was deleted, and the oracle covering it

`_zone_pour_stitch.py::_mst_edges` and `_gate_filter_edges` -- fully
deleted from production, replaced by
`temper_geometry.stitch_mst_with_gate_py`/`gate_edges_py`
(`zone_generator.rs`). Oracle:
`tests/router_v6/_stitch_mst_with_gate_py_oracle.py`, pinned to commit
`9a55b56be95f985098c4cb9c0abfc4569a79dcad` (this migration's base,
verified verbatim by `test_oracle_is_verbatim_copy`), registered in
`scripts/oracle_hashes.json` as a **new** entry (170 total, was 169) --
not a re-pin of an existing pin.

## Scope discipline

- `zone_generator.rs` and the zone carve/fill path: mine, touched.
- `_ground_plane.py` / `_power_islands.py` (`gnd`/`+3V3`/`vcc`/`+15V`/
  `V_BUS_SENSE` backbone, corridor-aware A*): confirmed, before touching
  anything, to be a genuinely separate code path (no shared function with
  this task's fix) serving a disjoint net set -- **not touched**, per
  explicit coordination with the owning sibling.
- `_astar_nlayer.py` (net ordering, `landing_blocked`): not touched, per
  brief.
- A full corridor-aware (obstacle-routing, not straight-line) pad-to-pad
  bridge search for these 9 nets was considered and **declined** -- it
  would be a second large port in the same task, and the independent
  corroboration from the sibling's corridor-A* result on a different net
  set already gives strong (not certain) evidence it would not change the
  outcome. Flagged as a possible follow-up, not attempted.

## Hard-rule compliance

- `pcb/temper.kicad_pcb` never opened for writing; sha256 verified
  identical at task start and end.
- No clearance/creepage/copper-weight/DRU threshold changed;
  `drc_ceiling.json` untouched.
- No existing oracle re-pinned; one new oracle added and registered.
- `.venv` isolated to this worktree (`make venv-isolate`);
  `temper_geometry.__file__`/`temper_placer.__file__` verified to resolve
  inside this worktree before any number in this document was trusted.
- DRC harness copies `.kicad_pro`, `.kicad_dru` (regenerated live via
  `scripts/generate_kicad_dru.py`), `pcb/fp-lib-table`, and `pcb/libs/`,
  and seeds `KICAD_CONFIG_HOME` via `_drc_api._single_threaded_kicad_env`
  -- the documented ad-hoc-harness gap does not apply here.
- `git stash` never used.
- `cargo clippy -D warnings` and `ruff check` clean on every file this
  task changed; a whole-crate `cargo fmt` was attempted, found to touch
  190+ unrelated files, and reverted -- only the lines this task's own
  commits added were hand-formatted to rustfmt's output.
- A poisoned shared `CARGO_TARGET_DIR` (this crate rebuilt without its
  `python` feature by a concurrent process, `AGENTS.md`'s documented
  failure mode) was hit twice during this task's own verification passes;
  fixed both times by rebuilding into a private, worktree-scoped
  `CARGO_TARGET_DIR` rather than continuing to race the shared one.
