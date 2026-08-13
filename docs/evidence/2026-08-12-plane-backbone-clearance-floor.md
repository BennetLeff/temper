<!-- provenance: measured 2026-08-12, worktree
/home/bennet/Desktop/temper/.claude/worktrees/plane-backbone, branch
fix/plane-backbone-clearance-floor, branched from origin/fix/clearance-congestion-band
(PR #1095, HEAD d60caadd5) so the two fixes compose. Board under study: PR #1082's
heatsink placement, placed board sha256
7e1dd81f05185adfcad7b5d05020a140eb06faf643d3e11830b08e54f0b40f2a -- the SAME file
#1095 routed, re-verified by hash here, not re-solved. pcb/temper.kicad_pcb NOT
modified: sha256 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
unchanged, `git status --short pcb/` empty before and after every step.
pcb/temper.kicad_dru regenerated from scripts/generate_kicad_dru.py::generate_dru and
byte-identical to the one #1095 measured against, sha256
ed81027eb6186bd69c129364d55fd8ff81c7bc426dd5cb3de94f62c39f1b8293.
pumpkin_engine sha256 7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e
source_commit 5bbf650d47d3a07fffd10a44e7c06c43a0a800bd; scripts/verify_pumpkin_engine.py
--require exit 0. kicad-cli 10.0.5 via the ~/.local/bin shim (#1086).
Routed board D: scripts/route_board.py --net-batching --batch-size 10 from that placed
board, PYTHONPATH pinned to this worktree, sha256
38510f368039a19059de5111404fa5e094520c411c515da9da2c01f9379395fd -- BYTE-IDENTICAL to
#1095's board C. The N=130 DRC campaigns for committed/heatsink/A/B/C are #1095's own,
re-read from their campaign.json records rather than re-run, and reproduce its published
table to the digit; board D needs no campaign of its own because it is the same file.
NO ceiling entry written; power_pcb_dataset/drc_ceiling.json NOT modified. -->

# `OTHER_NET_CLEARANCE_MM = 0.05` was never defensible and is now fixed — and it is **not** what put 170 shorts on board C. That was Stage 4's own obstacle grid, and #1095 turned its reservation off entirely

> **Three verdicts up front.**
>
> **1. 0.05mm was never defensible, and this is not a pour-vs-trace trade.**
> It was introduced (`52c9f176e`, #1033, 2026-08-11) in the *same diff hunk* as
> a comment that reasons its way to **0.5mm** — *"0.5mm is that worst case with
> no extra headroom added, deliberately not padded further"* — and then assigns
> a tenth of the figure the prose had just derived. The generated `.kicad_dru`
> contains **no zone- or pour-specific clearance condition at all** (zero
> occurrences of `Zone` in `scripts/generate_kicad_dru.py`; the only `A.Type`
> conditions are `Pad` and `Track`), and the copper this constant governs is
> **0.4/0.3mm tracks and 0.8mm vias**, not pour fill. So there is no rule to
> split: RULE 10's 0.2mm applies, and 0.05 was 4× under it. Fixed, derived from
> `clearance_floor` rather than restated, plus a gate (P6) that would have
> caught it 31 days ago.
>
> **2. It cannot have caused the 170 pad–track shorts #1095 attributes to it.**
> `_ground_plane.py` and `_power_islands.py` are imported by their own two CLI
> scripts and their tests — **and by nothing on `route_pcb()`'s path**. No board
> in the #1095 series carries a single In1.Cu or In2.Cu zone or a single
> 0.4/0.3mm segment. All 169 distinct tracks in board C's 191 `actual 0.0000 mm`
> violations are **0.2000mm** Stage 4 Default copper. And board **D** — this
> branch, same placed board, same flags — is **byte-identical to board C**
> (sha256 `38510f36…`). The plane-backbone fix is measurably board-neutral
> through the production route.
>
> **3. The real third instance in the production route is
> `build_occupancy_grid`'s C-space, and #1095 switched it off.** Stage 4 reserves
> `default_trace_width/2` — the trace half-width and **zero clearance** — around
> every foreign pad, track and via, against a 0.2mm rule. Since #1095 corrected
> `default_trace_width` 0.25 → 0.20 that inflation is exactly **0.100**, and the
> function guards with `if inflation_mm > 0.1`. Measured on the #1082 placed
> board: `inflation_mm=0.1` produces **a grid identical to `inflation_mm=0.0`** —
> 3,426,152 free F.Cu cells against 3,389,038 at 0.100001. The 37,114 cells
> (1.00% of the F.Cu grid) that `origin/main` reserved are free on #1095's
> branch, and they are exactly the cells hugging an obstacle boundary. Zero-gap
> `clearance` errors across the series: heatsink **0** → A **0** → B **14** → C
> **191**.
>
> **On the two outstanding items.**
> `test_production_board_routing_drc_regression` is **not measurable on this
> machine**: three runs, three kernel OOM kills, peak `anon-rss` **61.4 GB** on
> a 62 GB box with the machine otherwise idle, `pytest` exit 137. That is the
> mechanism behind #1095's "four attempts killed by the session's process
> management" — they were `oom_reaper`, not process management. See §6.
> `test_full_pipeline_run_surfaces_the_same_unexplained_gap` is red on `PWM_H`,
> and the honest answer is **not** "the board cannot route it": measured on the
> fixture with the production Stage 2 construction and a plain flood fill,
> `PWM_H`'s two pads are co-reachable on **all four layers at every clearance up
> to 0.30mm**. See §7.

---

## 1. What `OTHER_NET_CLEARANCE_MM` actually is

It is genuinely "clearance to other nets" — not something else wearing the
name. Every use is a shapely `buffer()`:

| site | role |
|---|---|
| `_ground_plane.py` `_collect_other_net_copper(pcb, "gnd", "F.Cu"/"B.Cu", c)` | buffer foreign copper before the drop-via placement search |
| `_power_islands.py` same, per rail | ditto |
| `_power_islands.py:519` `Point(via).buffer(r + c)` | this rail's new via, as an obstacle for later rails |
| `_power_islands.py:594` `LineString(seg).buffer(w/2 + c)` | this rail's new backbone segment, ditto |

Both directions are the same quantity: the gap between this module's new
copper and another net's copper. Nothing else is hiding under the name.

**But note which reservation shape these are.** They are exact geometry, not
the lattice stamp `clearance_floor.blocking_clearance_mm()` was written for. A
point outside a polygon buffered by `c` is at least `c` away, full stop; there
is no `ceil()` to pre-compensate for. Handing `blocking_clearance_mm`'s output
(0.150 for a 0.20mm Default trace) to a shapely buffer would reserve 0.15mm
against a 0.2mm rule — the original defect re-introduced by over-generalising
its own fix. This PR adds `clearance_floor.required_clearance_mm()` for the
exact-geometry case and documents the split, so both live in one place without
being one number.

## 2. Was 0.05mm ever defensible? No, and the file says so twice over

`git log -L 112,112:_ground_plane.py` gives exactly one commit: `52c9f176e`
("fix(router_v6): close the ground-plane creepage blocker + via/hole
collisions", #1033, 2026-08-11). `259758f6a` (#1047, same day) copies it into
`_power_islands.py`.

The introducing hunk adds the constant and its justification **together**:

```
+# Sized from this board's own netclasses (pcb/temper.kicad_pro
+# net_settings.classes): Default 0.2mm, Power 0.5mm, GateDriveHV/SELV
+# 0.25mm are the classes gnd's new copper can actually land next to ...
+# 0.5mm is that worst case with no extra headroom added, deliberately not
+# padded further: padding it hurts MST routability ...
+OTHER_NET_CLEARANCE_MM = 0.05
```

The prose derives 0.5 and the code says 0.05. That is not a documented trade;
it is a value and its own justification disagreeing by a factor of ten, from
the first commit.

**Why it ended up at 0.05 anyway** is in that commit's own message, §3:

> *"Routing the MST backbone and/or vias around every other net's existing
> F.Cu/B.Cu copper was implemented and measured, but even a near-zero clearance
> margin collapsed gnd connectivity (46/86 -> 7/86)…"*

So 0.05 is a **connectivity concession** — the largest value that still let the
straight-line-MST heuristic connect the net — and the comment was never
rewritten to say so. A concession is a legitimate thing to make; recording it
as a derivation of the correct number is not.

### 2b. Is there a pour-specific rule this should have keyed off instead?

No, and the check is exhaustive rather than rhetorical:

* `scripts/generate_kicad_dru.py` contains **zero** occurrences of `Zone`. Every
  `(condition ...)` it emits keys off `NetClass`, `Reference`, `Pad_Type`, or
  `A.Type == 'Pad'` / `A.Type == 'Track'`. There is no pour clause to write a
  looser number against.
* The copper `OTHER_NET_CLEARANCE_MM` governs is **not** pour fill. It governs
  the MST backbone (`STITCH_TRACE_WIDTH_MM` 0.4mm on F.Cu for gnd, 0.3mm on
  F.Cu for the power rails) and the drop vias (`VIA_SIZE_MM` 0.8mm). Both are
  `Track`/`Via` items and both fire RULE 10.
* The pours these modules emit land on **In1.Cu** and **In2.Cu**, which carry no
  other copper at all — that is the whole premise of both modules. The pour is
  not the thing at risk from this constant, and never was.

**Verdict: raise it.** It is now `required_clearance_mm()` — the DRU floor,
derived from the single place that declares it — and the foreign-copper
obstacle is resolved per NET PAIR (`max(own, other)`) by
`_corridor_backbone.collect_other_net_copper_by_pairwise_clearance`, which the
corridor-aware backbone already used and via placement did not.

That split is itself part of the answer to "how did this survive three
clearance investigations": **there were two obstacle models for one obstacle.**
Whoever read the backbone site saw a correct per-pair polygon and moved on;
whoever read the via-placement site saw the flat constant. There is now one.

## 3. What the fix does to the copper it governs

Both generators run on the #1082 placed board, before (HEAD~1) and after, same
input, same manifest. Gap measured geometrically against the input board's own
foreign copper on the layer each new item lands on — pads at their real
half-extent, tracks at `w/2`, vias at `d/2` — not from a DRC report.

| generator / net | new item | checks | min gap before | min gap after | checks under 0.2mm before → after |
|---|---|---:|---:|---:|---:|
| `gnd` | **drop vias** | 146–160 | 0.0621 | **0.2003** | 30 → **0** |
| `gnd` | backbone segments | 212 / 220 | 0.0000 | 0.0000 | 107 → 103 |
| `+3V3` | **drop vias** | 84–100 | 0.0621 | **0.5196** | 12 → **0** |
| `+3V3` | backbone segments | 197 / 201 | 0.0000 | 0.0000 | 39 → 37 |
| `vcc` | **drop vias** | 22–26 | 0.0703 | **0.5109** | 6 → **0** |
| `vcc` | backbone segments | 35 / 39 | 0.0000 | 0.0000 | 11 → 9 |

**On the copper this constant actually governs — the drop vias — every
under-reservation is gone**, and the power rails land at 0.51mm because the
per-pair resolution gives them the real `Power` class requirement (0.5mm)
rather than any single constant. Cost: `gnd` drop vias 80 → 73 and
`via_unresolved_conflict` 0 → 7, i.e. seven vias now fail closed rather than
being emitted at a standoff the DRC would grade as a violation. `+3V3`/`vcc`
lose 2 each the same way.

**The backbone segments do not move, and that is correct, not a shortfall.**
72 of `gnd`'s 85 MST edges are laid by the keepout-only straight-line/one-bend
**fallback** (`_blocked`), which by construction checks the HV/SELV keepout and
*nothing else* — it never consulted `OTHER_NET_CLEARANCE_MM`. Its reservation
against other-net copper is 0.0mm, which is why 75 segment checks sit at
exactly 0.0000 before and after. That is a **separate, already-documented
incompleteness** (`_corridor_backbone.py`'s module docstring, #1052) — a
straight line through a tree whose hub edges cannot be dropped without
disconnecting everything downstream — and it is not this constant. Naming it
here so it is not later mistaken for a regression of this fix.

## 4. The plane backbone did not put a single track on board C

This is the part of #1095 §6.3 that does not hold, and it is checkable four
independent ways.

**(a) Import graph.** `generate_ground_plane_content` and
`generate_power_islands_content` have exactly three callers between them:
`scripts/generate_ground_plane.py`, `scripts/generate_power_islands.py`, and
`packages/temper-placer/tests/router_v6/test_{ground_plane,power_islands}.py`.
Neither `adapter.py`, `_adapter_convert.py`, `pipeline.py` nor
`_pipeline_core.py` imports either module. `route_pcb()` cannot reach them.

**(b) No inner-layer copper exists on any board in the series.** Zone layers,
counted on the routed files themselves:

| board | zones | segment widths present |
|---|---|---|
| heatsink | F.Cu 42, B.Cu 42 | 0.2500, 0.5080, 0.3048, (4× 0.2000) |
| A | F.Cu 42, B.Cu 42 | 0.2500, 0.5080, 0.3048, (4× 0.2000) |
| B | F.Cu 42, B.Cu 42 | 0.2000, 0.5080, 0.3048 |
| **C** | F.Cu 42, B.Cu 42 | 0.2000, 0.5080, 0.3048 |

No In1.Cu zone, no In2.Cu zone, no 0.4mm segment, no 0.3mm segment, on any of
them. The gnd backbone's own signature (`STITCH_TRACE_WIDTH_MM = 0.4`) appears
zero times.

**(c) The violating tracks are Stage 4's.** Resolving every `Track` item in
board C's 191 `actual 0.0000 mm` clearance violations back to its own
`(segment …)` by uuid: **169 distinct tracks, all `width 0.2000`** (187 item
references on F.Cu, 5 on B.Cu, 0 unmatched). Their lengths are the A* lattice —
0.1000, 0.1414, 0.2000, 0.2828, 0.4243 — not straight MST spans.

**(d) Board D is byte-identical to board C.** Routed on this branch, from the
same placed board (`7e1dd81f…`), same flags, 424.3s: sha256
`38510f368039a19059de5111404fa5e094520c411c515da9da2c01f9379395fd`, the same
value #1095 recorded for C. Same 3638 segments, 40 vias, 84 zones, 78/102 nets,
51/139 pad-connected. That is simultaneously the measurement of this fix's board
effect (**exactly zero**) and an independent reproduction of #1095's board C
from a different worktree on a different day.

## 5. The real third instance: Stage 4 reserves zero clearance from foreign copper

`occupancy_grid.py`'s `OccupancyGridStage`:

```python
base_inflation = pcb.design_rules.default_trace_width_mm / 2.0
grid = build_occupancy_grid(routing_space, inflation_mm=base_inflation)
```

and inside:

```python
check_area = routing_space.available_area
if inflation_mm > 0.1:                       # "Threshold to avoid tiny/empty buffers"
    check_area = routing_space.available_area.buffer(-inflation_mm, quad_segs=4)
```

`routing_space.available_area` is `board − obstacles`, and `build_obstacle_map`
buffers **nothing**: pads, tracks and vias enter at their raw physical extent.
So the entire clearance a Stage 4 path keeps from a foreign pad is whatever
`base_inflation` supplies beyond its own half-width — which is **zero**. This
is the same defect class as the other three, at its widest: a 0.0mm reservation
against a 0.2mm rule, on the one code path that produces most of the board's
copper.

It was harmless-looking while `default_trace_width` was 0.25: inflation 0.125,
guard passes, a 0.25mm trace ends up exactly touching. #1095's width correction
(0.25 → 0.20, itself right — three declared sources say 0.2) makes inflation
exactly **0.100**, and `0.1 > 0.1` is False. Measured on the #1082 placed board,
F.Cu, this branch:

```
dr.default_trace_width_mm = 0.2  ->  base_inflation = 0.1
  inflation_mm=0.0        guard=False   free=3426152  (92.28%)
  inflation_mm=0.1        guard=False   free=3426152  (92.28%)   <-- production
  inflation_mm=0.100001   guard=True    free=3389038  (91.28%)
  inflation_mm=0.125      guard=True    free=3381760  (91.08%)   <-- origin/main
  inflation_mm=0.3        guard=True    free=3308813  (89.12%)   <-- w/2 + 0.2mm
```

`inflation_mm=0.1` and `inflation_mm=0.0` give the **same grid, cell for
cell**. 37,114 F.Cu cells that `origin/main` blocked are free on #1095's branch,
and by construction they are the ring of cells against every obstacle boundary.
A 0.2mm track centred there overlaps the obstacle by up to 0.1mm.

The DRC series says exactly that:

| board | `default_trace_width` | inflation | guard | `clearance` at `actual 0.0000` | pad–track |
|---|---:|---:|---|---:|---:|
| heatsink | 0.25 | 0.125 | pass | **0** | 58 |
| A | 0.25 | 0.125 | pass | **0** | 150 |
| B | 0.20 | 0.100 | **fail** | 14 | 41 |
| **C / D** | 0.20 | 0.100 | **fail** | **191** | 280 |

The lost erosion is the *enabling* condition (it is what makes an overlap
representable at all); fix 3's tighter, correct per-class stamping is the
*amplifier* (board C packs 3638 segments where B packs 3207, so far more paths
end up hugging a pad). Neither alone explains 0 → 191; together they do, and
the guard is the part that is unambiguously a defect.

**Not fixed in this PR, deliberately.** It is a fourth site, it is not the one
this task was scoped to, and correcting it changes the routing of every net on
the board — which would confound the measurement in §4 that makes the
plane-backbone fix's board-neutrality provable. It is now named, measured, and
has a one-line reproduction. It is the single most specific follow-up this
document produces, and on the evidence here it is worth more than the fix this
PR actually lands.

## 6. `test_production_board_routing_drc_regression` — measured, and it is an OOM

Run three times on this branch, the last one **alone on an otherwise idle
62 GB box** with a 20-second RSS sampler attached. Every run was killed by the
kernel, not by the harness — `pytest` exit code **137** (SIGKILL):

```
Aug 12 19:19:41 kernel: oom_reaper: reaped process 1475187 (pytest) ...
Aug 12 19:29:10 kernel: Out of memory: Killed process 1490300 (python)
                        total-vm:77577300kB, anon-rss:60545632kB
Aug 12 19:34:08 kernel: Out of memory: Killed process 1496562 (python)
                        total-vm:77631464kB, anon-rss:61335284kB
Aug 12 19:39:40 kernel: Out of memory: Killed process 1498657 (python)
                        total-vm:77620312kB, anon-rss:61357204kB
```

Sampled RSS on the solo run: 8.8 GB → 17.9 GB → 37.7 GB → **58.9 GB** → killed,
i.e. it doubles every 20 seconds and dies about 90 seconds in. Peak
`anon-rss` **61.4 GB** against 62 GB of RAM and 1 GB of swap: it is not close,
and no amount of headroom on this class of machine changes the outcome.

The test calls `route_pcb()` **without**
`enable_net_batching`, i.e. the monolithic Stage 3 SAT model over all 110
production nets — the configuration `net_batching.py` exists to replace. The
board-scale measurements in this document and in #1095 all use
`--net-batching --batch-size 10`, which peaks around 0.9 GB.

So #1095's "four attempts killed mid-run by the session's process management"
were `oom_reaper`, and no amount of process discipline will change that. The
gate is not currently runnable on this machine and has not been for as long as
the monolithic path has needed 60 GB.

**This is a finding, not a pass.** The `shorting_items` risk #1095 flagged
(137 → 199 on the candidate) is therefore still unverified against that
ratchet, and `PRODUCTION_ROUTER_OUTPUT_SHORTING_ITEMS = 178` is a live risk
that nobody can currently measure. The honest options, in order of preference:

1. Give the test `enable_net_batching=True`. It would then measure the
   configuration every other measurement in this repo uses, at ~0.9 GB — but it
   is a **different artefact**, so the three thresholds (1514 / 178 / 463) would
   have to be re-seeded from measurement, with a `_march`-style record saying
   why. That is a re-baselining decision, not a fix, and it is not mine to make
   silently inside a clearance PR.
2. Leave it as-is and mark it as requiring a machine with >64 GB. That keeps the
   artefact but keeps the gate dark.

Not decided here. Recorded so the next attempt does not spend a fifth run
discovering the same thing.

## 7. `test_full_pipeline_run_surfaces_the_same_unexplained_gap` — `PWM_H`, and the board *can* route it

**Which net.** `PWM_H`, on `pcb/benchmarks/temper_fixture_33.kicad_pcb`. It is
the only failure in the run: `✗ PWM_H FAILED: no legal path found (forced
segment disallowed)`, so it is topology-solved, emits no copper, and the audit
correctly calls that an unexplained gap.

**Why it no longer fits.** `PWM_H` resolves to `GateDriveSELV` (w=0.40mm,
declared clearance 0.25mm). #1095's `blocking_clearance_mm` changes what every
class reserves on the 0.1mm lattice, and for this fixture's classes the changes
are large:

| net | class | w | declared c | pitch before → after | achieved gap before → after |
|---|---|---:|---:|---:|---:|
| `PWM_H`, `PWM_L` | GateDriveSELV | 0.40 | 0.25 | 0.600 → **0.700** | 0.2000 → 0.3000 |
| `GATE_H`, `GATE_L` | GateDriveHV | 0.40 | 0.25 | 0.600 → **0.700** | 0.2000 → 0.3000 |
| `+15V`, `VCC_BOOT` | Power | 1.00 | 0.50 | 1.100 → **1.500** | 0.1000 → 0.5000 |
| `GND` | GND | 1.00 | 0.30 | 0.900 → **1.300** | **−0.1000** → 0.3000 |
| `SW_NODE`, `DC_BUS+` | HighVoltage | 3.00 | 2.00 | 3.600 → **5.000** | 0.6000 → 2.0000 |
| `SPI_CLK`, `I_SENSE` | Default | 0.20 | 0.20 | 0.500 → **0.400** | 0.3000 → 0.2000 |

Note the `GND` row: the old reservation delivered a **negative** gap, i.e. the
router was free to lay a second 1.0mm trace overlapping a GND trace by 0.1mm.
Every non-Default class in this fixture was under-reserving, and correcting all
of them at once consumes a great deal of a 33-net board. `PWM_H` is routed 5th
from last; by then the corridor it used is spent.

**Is "the board genuinely cannot route it" the honest answer? No.** Measured
with the production Stage 2 construction (`compute_routing_space` →
`build_occupancy_grid`) on the stripped fixture — pads and board outline only,
no other net's copper — and a plain 8-connected flood fill, so a negative
result would be a statement about the board and not about A*'s budget:

| trace | clearance | C-space erosion | F.Cu free cells | `PWM_H` pads co-reachable? |
|---:|---:|---:|---:|---|
| 0.4mm | 0.20mm | 0.400mm | 1,427,441 | **yes** (all 4 layers) |
| 0.4mm | 0.25mm | 0.450mm | 1,421,854 | **yes** (all 4 layers) |
| 0.4mm | 0.30mm | 0.500mm | 1,416,547 | **yes** (all 4 layers) |

Both pads sit in the same connected component of free space at the *achieved*
0.30mm gap, on F.Cu and on all three other layers, with 1.4 million free cells
to work in. `PWM_H` is not geometrically excluded at correct clearance. It is
**squeezed out by the 23 nets routed before it**, under a reservation model
that is now honest for every class at once.

**Decision: the test stays red, and the assertion is not widened.** It is
asserting exactly the right thing — a topology-solved net emitted no copper and
nothing recorded a legitimate reason — and it is now telling the truth about a
real capacity outcome rather than an old, too-loose packing. Widening it would
delete the only signal that the corrected reservation costs completion. The
remedies that would make it honestly green, none of which belong in a
clearance PR:

* **Ordering.** `PWM_H` is not routed first and gains nothing from being
  routed late. `_compute_net_order` is congestion-blind to the new
  reservations.
* **Reservation shape.** `blocking_clearance_mm` assumes the *neighbour* has
  the same width as the net being stamped. A 0.40mm GateDriveSELV trace next to
  a 0.20mm Default trace therefore ends up with a 0.400mm gap where 0.250mm was
  required — 0.15mm of over-reservation per pair, paid on every wide-class net.
  A two-sided form (`w_self/2 + c + w_other/2`) is strictly more accurate; it
  needs a board-scale measurement of its own.
* **Recording the reason.** `run_astar_pathfinding` *does* know why `PWM_H`
  produced nothing ("forced segment disallowed"), and
  `topology_copper_audit.py`'s own module docstring already counts that as one
  of its categories ("19 were attempted by Stage 4's A* and genuinely failed to
  find a legal path"). `audit_topology_vs_copper` is never handed the failure
  reports, so it cannot use them. Plumbing them through would move `PWM_H` from
  *unexplained* to *explained-and-failed* — which is a truthful reclassification
  rather than a widened assertion, but it is a change to the audit's contract
  and deserves its own review, not a line in this PR.

## 8. Measurement: the combined per-category table

All boards routed from the identical PR #1082 placed board (sha256
`7e1dd81f…`), all DRC'd at **N=130** with `.kicad_pro` **and** `.kicad_dru`
present beside the board (the #1086 trap: without the `.kicad_dru` the same
board measures 841 errors while reporting "project resolvable: True"). Medians,
`[min–max]` where the category varied. Ceilings are
`power_pcb_dataset/drc_ceiling.json`'s `violations_by_type` for `board_id:
temper`.

`committed`, `heatsink`, `A`, `B` and `C` are #1095's campaigns, re-read from
their `campaign.json` records. **D is this branch**, and it needs no campaign of
its own: it is the same file as C, sha256 `38510f36…`, verified by `diff`.

| category | ceiling | committed | heatsink | A | B | **C = D** |
|---|---:|---:|---:|---:|---:|---:|
| `clearance` | 386 | 386 [385–386] | 501 [499–505] | 502 [499–507] | 500 [499–505] | **500 [499–502]** ❌ +114 |
| `solder_mask_bridge` | 154 | 154 | 49 | 72 | 204 [199–211] | **201 [199–207]** ❌ +47 |
| `shorting_items` | 199 | 199 [199–200] | 137 | 131 | 200 [199–205] | **199 [199–202]** ⚠️ at ceiling |
| `track_width` | 199 | 199 | 199 | 199 | 199 | **199** ⚠️ at ceiling |
| `creepage` | 186 | 184 [182–184] | 112 [110–112] | 94 [92–94] | 90 [88–90] | **105 [103–105]** ✅ |
| `hole_clearance` | 105 | 105 | 89 | 95 | 76 | **54** ✅ −51 |
| `courtyards_overlap` | 11 | 11 | 19 | 19 | 19 | **19** ❌ +8 |
| `copper_edge_clearance` | 10 | 10 | 13 | 4 | 11 | **16** ❌ +6 |
| `annular_width` | 4 | 4 | 6 | 8 | 4 | **4** ✅ at ceiling |
| `drill_out_of_range` | 4 | 4 | 6 | 8 | 4 | **4** ✅ at ceiling |
| `via_diameter` | 4 | 4 | 6 | 8 | 4 | **4** ✅ at ceiling |
| `tracks_crossing` | 1 | 1 | 6 | 6 | 1 [1–2] | **5** ❌ +4 |
| `hole_to_hole` | 3 | 3 | 0 | 1 | 2 | **0** ✅ |
| **TOTAL errors** | **1266** | 1264 [1262–1264] | **1143** [1140–1147] | 1146 [1142–1152] | 1314 [1307–1324] | **1310 [1306–1317]** |
| TOTAL warnings | — | 624 | 631 | 615 | 616 | **617** |
| `unconnected_items` | — | 428 | 326 | 335 | 339 | **333** |

**Connectivity, reported as pad connectivity and labelled as such** —
`pad_connectivity_audit.py`, this repo's declared PRIMARY metric, not net
completion:

| | heatsink | A | B | **C = D** |
|---|---|---|---|---|
| pad-connected (PRIMARY) | 55/139 | 51/139 | 49/139 | **51/139** |
| fake-completion | 59 | 50 | 50 | 55 |
| topology-solved nets | 86/102 | 73/102 | 71/102 | **78/102** |
| route wall time | 431.4s | 543.9s | 445.9s | **424.3s** (D) / 491.9s (C) |

### 8b. Better or worse than 1143? **Worse. 1310 vs 1143, +167.**

Plainly: the combined fix leaves the board worse than the heatsink board by 167
errors, and this PR moves that number by **zero**, because the code it fixes
does not run in the route. Five ceiling breaches (`clearance` +114,
`solder_mask_bridge` +47, `courtyards_overlap` +8, `copper_edge_clearance` +6,
`tracks_crossing` +4). **No `Ceiling-Approval:` trailer is written and none
should be.**

The `+167` decomposes, on the evidence in §5, into: `solder_mask_bridge`
49 → 201 and `shorting_items` 137 → 199, both of which track the 191 zero-gap
overlaps, which track the switched-off C-space erosion. It does **not**
decompose into the plane backbone, which contributed no copper.

`clearance` is unchanged at ~500 and is not expected to move: it has now been
measured at 499–507 across six materially different copper realisations
(2,514–4,497 segments) and three clearance models on this one placement. #1052,
`docs/plans/2026-08-12-001` and #1095 §6.4 all reach the same conclusion from
different directions. It is a **placement** property. Nothing in this PR was
aimed at it and nothing in this PR moved it; that is not a failure of the PR.

## 9. What was NOT done, deliberately

* `power_pcb_dataset/drc_ceiling.json` **not modified**; no `Ceiling-Approval:`
  trailer, no `_march` entry.
* `pcb/temper.kicad_pcb` **not touched** — sha256
  `6928b7c8…` unchanged, `git status --short pcb/` empty throughout.
* Placement **not re-solved**; board D is #1082's placement re-routed, so the
  comparison is routing-only by construction. `courtyards_overlap` is 19 on
  heatsink/A/B/C/D alike: no component moved. Heatsink co-location and the
  PD2/8.0mm isolation barrier are untouched.
* **`build_occupancy_grid`'s inflation guard left unfixed** (§5) — named,
  measured, reproducible in one command, and deliberately not changed here so
  that §4's byte-identity result stays a valid measurement of *this* fix.
* **`test_full_pipeline_run_surfaces_the_same_unexplained_gap` left red** (§7).
  The assertion is not widened. Three named remedies, none landed.
* **`test_production_board_routing_drc_regression` left unmeasurable** (§6). Not
  re-baselined, not marked skip, not given `enable_net_batching` — all three are
  decisions with consequences beyond this PR.
* The `_blocked` straight-line MST fallback's **0.0mm** reservation against
  other-net copper (§3) left alone: it is #1052's lineage, not this constant.
