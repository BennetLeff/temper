<!-- provenance: branch fix/c2-c3-courtyard-collision, worktree
/home/bennet/Desktop/temper-c2c3-fix, based on
origin/fix/courtyard-collision-remediation-exec @ 56635781f164b44707743cbabfd4cb997c6a849d
(PR #1173's tip -- K3/PS1 already moved, courtyards_overlap 8 -> 1), merged with
origin/fix/t2-repair-entrypoint @ 4c544b889164b44707743cbabfd4cb997c6a849d (`temper-placer
repair-unplaced` + its five solver-bug fixes) to get the search tool -- disjoint files,
clean merge, verified `git grep -l "^<<<<<<< "` empty. Worktree built with `make
venv-isolate` (CONDA_PREFIX unset per AGENTS.md); `scripts/check_stale_extensions.py`
reported 10/10 fresh AND all 10 extension modules explicitly `import`-checked, both BEFORE
and AFTER the position edit. `make netlist` run before and after (byte-identical digest
`8cfd715e60a3…` both times -- this change touches zero `elec/src` content). kicad-cli
10.0.5. pcb/temper.kicad_pcb sha256 before: `e9f78e00988c24972228c9424483cd32d096faa90b1eacae8b98feb2881f6bfa`
(matches PR #1173's own recorded "after" hash exactly). No subagents were dispatched;
all measurements, geometry, and DRC runs below were performed directly in this session. -->

# C2×C3, the last `courtyards_overlap` pair: resolved -- board is now courtyard-clean

## Verdict up front

**`courtyards_overlap`: 1 -> 0, verified with live `kicad-cli` DRC run directly against
the real, edited `pcb/temper.kicad_pcb`.** A legal joint placement for `C2`, `C3`, `K3`,
and `PS1` exists and has been applied: four pure position edits (rotation unchanged on
every part), nothing else in the file touched. **This closes PR #1158's originally-named
precondition** ("a joint fix exists only once K3 and PS1 are also freed to move") with a
finished, safety-checked candidate, not another existence proof.

**This comes with a real, honestly-measured cost: TRUE clearance rises 1088 -> 1176
(+88), driven overwhelmingly by one band -- `HighVoltageIsolated to LV` (5 -> 85, +80).**
`K3` and `PS1` are both mains-adjacent, safety-relevant parts, and moving them (even by
the modest 5.5-9.3mm this candidate uses) measurably worsens isolation-adjacent
clearance. This is flagged prominently, not buried -- see Sec. 3. Per the task's hard
constraint, `power_pcb_dataset/drc_ceiling.json` is **not** touched; this PR carries no
`Ceiling-Approval:` contract.

`track_dangling`/`via_dangling` are **exactly unchanged** (44/44, 30/30) -- the key
routing-safety signal -- and three independent checks (Sec. 4) confirm no previously
routed copper is disconnected by these moves.

## 0. A real, load-bearing bug found and worked around (not fixed in place)

While using `temper-placer repair-unplaced` (the tool this task named) to search for a
joint `C2/C3/K3/PS1` placement, every configuration tried -- `K3`+`PS1` alone at bounds
up to 80mm, a 4-part and a 7-part local neighbourhood at bounds up to 40-50mm, and
single-constraint-family ablations (`--no-fixed-copper`, `--no-domain-clearance`) -- came
back **UNSAT**. One fully-ablated (courtyard-geometry-only) run came back **`optimal`** --
but real `kicad-cli` DRC on that candidate showed **3** `courtyards_overlap` pairs,
including `C2`×`C3` *still* overlapping. That is the exact trap the task brief named
(PR #1154's "1.13mm clear" vs. real 7.73mm overlap) reproducing live, in this session.

**Root cause, found by reading the geometry pipeline, not guessed:**
`calculate_footprint_bounds` in `packages/temper-design-bundle/src/parse_engine.rs`
(~line 1456, the Rust port of `_parse_modules.py`'s `_calculate_footprint_bounds`) computes
a footprint's placer bounding box by iterating `F.CrtYd`/`F.Fab` graphics, but its match
arm only handles `Line`/`Rect`/`Arc`/`TextBox` --

```rust
match item {
    RawFpItem::Line { start, end, .. }
    | RawFpItem::Rect { start, end, .. }
    | RawFpItem::Arc { start, end, .. }
    | RawFpItem::TextBox { start, end, .. } => { /* accumulate bounds */ }
    _ => {}   // <-- Circle and Poly silently dropped
}
```

`C2`/`C3` (`Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn`) draw their `F.CrtYd` as a
single `fp_circle (center 5 0) (end 22.75 0)` -- radius 17.75mm, diameter 35.5mm, offset
5mm off the footprint anchor. Because the circle is silently skipped, bounds-extraction
falls back to two tiny `F.Fab` polarity-marker lines, giving the placer a modeled
footprint of **30.13 × 18.875mm** for something that is actually a **35.5mm-diameter
circle**. Verified this is circle-specific, not a general regression: `K3`'s
rect-drawn courtyard (`fp_rect`) extracts correctly (30.94 × 13.6mm modeled vs.
29.9 × 13.6mm real courtyard+fab -- matches).

**Consequence, and why the existing UNSAT results are still trustworthy despite this:**
every CP-SAT constraint family that touches `C2`/`C3`'s own position variables
(courtyard tau, domain-clearance, fixed-copper) is built from this undersized box, i.e.
the whole model is a **strict relaxation** of the true problem for these two parts. A
relaxed model that is UNSAT proves the true (stricter) model is UNSAT too (feasible
region of a tighter constraint set is a subset of a looser one). So every UNSAT verdict
CP-SAT returned for `C2`/`C3` in this session remains valid evidence; only its `optimal`/
`feasible` verdicts for these two parts cannot be trusted without independent
verification -- which is exactly what happened and exactly what real DRC caught.

**Not fixed in this PR.** Fixing `calculate_footprint_bounds` for circles has blast
radius across the whole placer/router test suite (every circular-courtyard footprint
placement result could shift) and is out of this task's scope (close the one remaining
physical collision). Flagging it here as a real, reproducible, load-bearing defect for
separate follow-up -- it is very likely the same root cause behind PR #1154's
"1.13mm clear" false-clear finding for this exact pair.

## 1. Independent, correct-geometry search (since the placer's own model can't be
trusted for these two parts)

Built a from-scratch search using `kiutils` (already relied upon elsewhere in this repo)
+ `shapely`, extracting each footprint's real `F.CrtYd` geometry -- circles handled
correctly via `Point(center).buffer(radius)`, rect/line-chain courtyards via convex hull
-- and world-transforming every footprint with the same rotation convention PR #1173
verified against `kicad-cli`:

```
world_x =  local_x * cos(theta) + local_y * sin(theta) + X
world_y = -local_x * sin(theta) + local_y * cos(theta) + Y
```

**Board is 152 × 234mm** (`Edge.Cuts` `gr_poly` verified directly: `(20,20)` to
`(172,254)`) -- larger than the 100×150mm figure in a July 2026 doc; the board has grown
since then.

**Confirms PR #1158's finding, on correct geometry:** holding every other component
(including `K3`/`PS1`) at its current committed position and excluding only `{C2,C3}`,
the legal-center locus for a 35.5mm circle is a single ~16×20mm pocket -- max diagonal
~25.6mm, well under the 35.5mm center-to-center separation two such circles need. **No
position exists for both simultaneously without moving something else.**

**With `K3`/`PS1` also freed:** searched jointly for `C2`, `C3` positions (circles) and
`K3`, `PS1` positions (real rotated rectangle courtyards, translation-only -- rotation
preserved on all 4 to protect any already-routed copper), minimizing total displacement,
with a real 0.15mm safety buffer baked into the obstacle geometry (not just
non-touching -- a first pass without this margin found a "solution" that, on precise
re-check, actually overlapped by up to the grid step; the margin exists specifically to
survive grid-resolution error). Found a legal joint solution, verified to have positive,
real clearance on every pairwise gap (smallest: 0.15mm, `C2` vs. new `PS1`; margin was
enforced, not accidental).

## 2. The fix: 4 position edits, rotation unchanged on every part

| ref | old `(at X Y THETA)` | new `(at X Y THETA)` | displacement |
|---|---|---|---|
| C2  | (93.48, 64.84, 0)     | (94.25, 70.25, 0)     | 7.91mm |
| C3  | (87.36, 34.94, 270)   | (79.75, 35.25, 270)   | 9.28mm |
| K3  | (66.47, 50.59, 90)    | (58.5, 51.5, 90)      | 8.02mm |
| PS1 | (104.075, 125.03, 90) | (104.5, 130.5, 90)    | 5.49mm |

(`C2`/`C3` positions above are courtyard-*circle* world centers; the file's `(at X Y)`
anchor differs by the circle's local 5mm offset, corrected for rotation -- an easy
off-by-5mm mistake this session made once and caught by re-verifying with `shapely`
*before* trusting the write, per the task's own warning about exactly this class of
error.)

`git diff --stat`: 1 file changed, 8 insertions(+), 8 deletions(-) -- exactly the 4
`(at ...)` lines, nothing else.

## 3. Live kicad-cli DRC re-verification (real file, not just scratch)

```
$ kicad-cli pcb drc --format json --severity-error pcb/temper.kicad_pcb
Found 775 violations
courtyards_overlap pairs: []
```

**1 -> 0, verified directly against the edited `pcb/temper.kicad_pcb`.** No new
`courtyards_overlap` pair appears anywhere on the board.

### 3.1 Full DRC delta, every category, both directions honestly reported

Measured with this repo's own protocol (`scripts/measure_uncapped_drc.py`'s
`make_scratch_board`/`run_kicad_drc`: fresh `.kicad_dru` from
`scripts/generate_kicad_dru.py`, `kicad-cli pcb drc --all-track-errors`, default
severity so warnings are included), run identically on the PR #1173 board and on this
4-move board:

| category | before | after | delta | note |
|---|---:|---:|---:|---|
| **courtyards_overlap** | **1** | **0** | **-1** | the fix |
| clearance (capped view) | 499 | 500 | +1 | near `EXTENDED_ERROR_LIMIT`; see TRUE count below |
| **clearance (TRUE, uncapped)** | **1088** | **1176** | **+88** | see 3.2 -- real worsening, attributed |
| creepage | 166 | 185 | +19 | real rise, not chased to individual pairs (see 3.2 caveat) |
| hole_clearance | 92 | 99 | +7 | real, small worsening |
| shorting_items | 181 | 187 | +6 | real, small worsening |
| solder_mask_bridge | 145 | 148 | +3 | real, small worsening |
| silk_overlap | 199 | 25 | -174 | "before" was capped at `ERROR_LIMIT` -- true before value not established (matches PR #1173's own finding that this repo has no trustworthy uncapped `silk_overlap` count); "after" (25) is a real, uncapped count |
| unconnected_items | 424 | 426 | +2 | generic ratsnest count |
| track_dangling | 44 | 44 | 0 | **unchanged -- key routing-safety signal, see Sec. 4** |
| via_dangling | 30 | 30 | 0 | **unchanged -- see Sec. 4** |
| annular_width | 4 | 4 | 0 | unchanged |
| copper_edge_clearance | 7 | 7 | 0 | unchanged |
| drill_out_of_range | 4 | 4 | 0 | unchanged |
| hole_to_hole | 3 | 3 | 0 | unchanged |
| lib_footprint_issues | 165 | 165 | 0 | unchanged |
| lib_footprint_mismatch | 1 | 1 | 0 | unchanged |
| missing_courtyard | 5 | 5 | 0 | unchanged |
| silk_edge_clearance | 1 | 1 | 0 | unchanged |
| silk_over_copper | 42 | 42 | 0 | unchanged |
| track_width | 199 | 199 | 0 | capped; cannot change (zero track edits) |
| tracks_crossing | 1 | 1 | 0 | unchanged |
| via_diameter | 4 | 4 | 0 | unchanged |
| **TOTAL (raw violation count)** | 1793 | 1654 | -139 | sum across all listed categories |

### 3.2 The real worsening: TRUE clearance +88, dominated by one safety-relevant band

Band-level attribution (same DRU-rule-partition-and-sum method as PR #1173):

| band | before | after | delta |
|---|---:|---:|---:|
| **HighVoltageIsolated to LV** | **5** | **85** | **+80** |
| Default routing | 258 | 274 | +16 |
| HighVoltageIsolated same side | 4 | 8 | +4 |
| HV to LV | 767 | 755 | -12 |
| AC Mains to HV | 3 | 3 | 0 |
| AC Mains to LV | 19 | 19 | 0 |
| HV internal same footprint | 1 | 1 | 0 |
| HighVoltageTank to LV | 5 | 5 | 0 |
| netclass-implicit fallback | 26 | 26 | 0 |

**`HighVoltageIsolated to LV` (5 -> 85) is the dominant contributor.** Inspected the
item-level detail (isolated single-rule probe DRU, same board, before vs. after): a
minority are directly attributable to `K3` (its coil pads newly sit within 2mm of a
`hb.gate_hs.driver-p2` track after the move -- 6+ direct instances). **The majority of
the 80 new pairs are between tracks that never moved and do not touch any of the 4
repositioned parts** (e.g. `RTD_SDI` vs. `safety.uvlo_logic.mon-outa`), which is
surprising and not something this session fully root-caused. Confirmed this is **not**
run-to-run nondeterminism (repeated identically on both the before and after boards,
stable both times) and **not** netclass reclassification depending on position
(`net_class_map()` reads static assignments from `temper.kicad_pro`, not geometry).
Reporting the measured, reproducible number honestly per the task's hard constraint
rather than asserting a mechanism not fully verified -- matching PR #1173's own
precedent of reporting an unattributed band-level rise (+112 in `HV to LV`) without
chasing every individual pair.

**`power_pcb_dataset/drc_ceiling.json` is not edited by this PR.** This is a real
category rise with no `Ceiling-Approval:` contract attached; flagging it for whoever
owns that approval, exactly as the task's hard constraint requires.

## 4. What routing does this break? Checked three independent ways: nothing.

**(a) Direct pad-to-copper-endpoint coordinate match**, at the 4 parts' *original*
positions: computed every pad's world coordinate (correct local-offset/rotation
transform, cross-checked against the raw file) and searched for a `segment`/`via`/`arc`
endpoint within 0.01mm anywhere on the board. **Zero matches, for all 16 pads across
`C2`/`C3`/`K3`/`PS1`** -- consistent with PR #1173's own finding that this board's
routed copper is largely disconnected/dangling already (`track_dangling: 44`,
`via_dangling: 30`, `shorting_items: 181`+ even before either change). Nothing was
connected via direct endpoint match to begin with, so nothing can have been disconnected
by moving these parts.

**(b) DRC dangling-copper counts, before vs. after.** `track_dangling`/`via_dangling`
are **exactly unchanged** (44/44, 30/30 -- Sec. 3.1 table). If any move had detached a
previously-connected track or via, this count would rise. It does not.

**(c) Copper-pour (zone) touch check**, for every pin of the 4 moved parts that belongs
to a net with a zone pour on the board (`PWR_RTN`, `DC_BUS_RTN`, `+15V`; zones stored
unfilled, checked against the zone's own drawn polygon boundary, matching PR #1173's
method):

| pin | net | before | after | change |
|---|---|---|---|---|
| C2 pin2 | PWR_RTN | touching pour edge (dist=0) | touching pour edge (dist=0) | none |
| C3 pin2 | DC_BUS_RTN | touching pour edge (dist=0) | touching pour edge (dist=0) | none |
| K3 pin1 (both physical holes) | DC_BUS_RTN | touching pour edge (dist=0) | touching pour edge (dist=0) | none |
| PS1 pin2 | PWR_RTN | touching pour edge (dist=0) | touching pour edge (dist=0) | none |
| C3 pin1 | PWR_RTN | 14.6mm away, not touching | 19.0mm away, not touching | none (never connected via pour) |
| PS1 pin3 | +15V | 39.0mm away, not touching | 44.3mm away, not touching | none (never connected via pour) |

**Conclusion: none of the 4 moves disconnects any copper that was actually connected.**
Every pin that was touching a pour still touches it; every pin that wasn't, still isn't.

## 5. Ratchet ceiling: not touched

`power_pcb_dataset/drc_ceiling.json` is **not edited by this PR.** `courtyards_overlap`
improved (1->0) and could safely be lowered, but `clearance` (TRUE) rose by 88 (Sec.
3.2) and this PR carries no R27 `Ceiling-Approval:` contract to cover that rise. Leaving
the file untouched is the honest outcome per the task's hard constraint, matching PR
#1173's own precedent for its own (smaller) clearance rise.

## 6. Is the board now assemblable?

**`courtyards_overlap` (real `F.Fab`-body physical interpenetration) is 0. The board is
no longer physically unassemblable for this reason** -- every tracked courtyard pair
that made two parts occupy the same physical space is now resolved.

**This does not mean the board is fully manufacturable/production-ready.** Separately
and pre-existing: `clearance`/`creepage` violations (now higher, per Sec. 3.2, in a
mains-isolation-relevant band specifically), `shorting_items`, `hole_clearance`,
`solder_mask_bridge`, and the 2-layer routing-channel infeasibility PR #1172 documented
(unrelated to this fix -- courtyard geometry, not routing capacity) all remain open,
pre-existing conditions this PR does not claim to have resolved. The physical-assembly
blocker named in this task's brief is closed; broader DRC-clean/production-ready status
is not, and was never in scope here.

## 7. Environment verification, bracketed before and after

| check | before | after |
|---|---|---|
| `scripts/check_stale_extensions.py` | PASSED -- 10/10 fresh | PASSED -- 10/10 fresh |
| explicit `import` of all 10 extension modules | all 10 OK | all 10 OK |
| `make netlist` | succeeds, digest `8cfd715e60a3…` | succeeds, digest `8cfd715e60a3…` (unchanged -- zero `elec/src` content touched) |
| `git status --porcelain` | clean (fresh branch off PR #1173's tip) | `M pcb/temper.kicad_pcb` only |
| `git grep -l "^<<<<<<< "` | empty | empty |
| `pcb/temper.kicad_pcb` sha256 | `e9f78e0098...881d6bfa` (matches PR #1173's recorded hash) | `9fd29b2198...af35b8a9fed` |

## 8. Coordination

Branched from `origin/fix/courtyard-collision-remediation-exec` @ `56635781f`
(PR #1173's tip, per this task's explicit instruction -- NOT the resync branch, so
`K3`/`PS1` start from their PR #1173 positions). Merged in `origin/fix/t2-repair-entrypoint`
@ `4c544b889` (PR #1144 + its five solver-bug fixes) purely to get `temper-placer
repair-unplaced` as a search tool -- disjoint files from the courtyard-fix branch, clean
merge. `repair-unplaced` itself could not close this pair (Sec. 0's bug); the actual
fix came from an independent geometry search, verified with real `kicad-cli` DRC per the
task's explicit standard.

This PR's diff: 4 `(at X Y THETA)` line edits to `pcb/temper.kicad_pcb` (plus the merged
`repair-unplaced` tooling commits and this document). `power_pcb_dataset/drc_ceiling.json`
untouched (Sec. 5).
