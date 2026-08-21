<!-- provenance: commit=fa067a9523cba69978ea7216a65009f6343315a7 dirty=false (worktree agent/isolated-copper-refill-zones, branched from origin/main at fa067a952; pcb/temper.kicad_pcb never written by this task -- sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd verified unchanged before and after, see sec 0 and sec 5.) -->

# `isolated_copper` under `--refill-zones`: characterization and the #1257 verdict (2026-08-17)

> **Correction (same day, before this doc's first publication settled).**
> This document originally stated the fix "was simply never applied to the
> checked-in board... because the only pipeline that would do so (a full
> `route_pcb` run) has been OOM-killed on every attempt" and left applying
> it as blocked/future work. That claim was **stale** -- inherited from
> historical evidence docs (#1257's own PR body, the handoff §6) describing
> OOM events that predate PR #1264 (`272fbe36c`, 2026-08-16 16:06:46,
> *after* #1257 at 12:10:07), which made Stage 3's **default** path a
> structural no-op (builds no SAT model at all). A live full-route attempt
> on current main, reported in §8 below, **completed twice with no OOM**
> (wall 329-336s, peak RSS 900-950 MB) and both outputs measured **0**
> `isolated_copper` under `--refill-zones` -- not via a synthetic seam
> splice this time, but from a genuinely, end-to-end freshly-routed board.
> §8 has the full live measurement; the rest of this document (characterization,
> the #1257 verdict, the structural check) is unchanged and still holds.
> Only the "what remains" framing changes: applying the fix is not blocked
> by memory anymore.

**Task**: handoff `docs/HANDOFF-2026-08-17.md` §9 item 7 / §3 mechanism 4,
following on from `docs/evidence/2026-08-17-refill-zones-drc-runner-gap-
measurement.md` (PR #1298, `evidence/refill-zones-drc-gap-measurement`),
which measured **109-113** `isolated_copper` findings ([109,113,112,112,110],
5 runs) with `--refill-zones` on the committed board, vs **0** without it.
This category has no entry in `power_pcb_dataset/drc_ceiling.json` at all --
implicit ceiling 0 under R27.

**Question**: PR #1257 ("Rust zone generator... isolated_copper 107->0") was
credited with fixing this exact category, but measured (per the handoff)
*without* `--refill-zones`. Did that fix never work, work only on unfilled
zones, or measure something different than #1298's 109-113? This document
answers that with measurement, not assumption, and reports what was fixed
in this task's lane (`packages/temper-geometry/src/zone_generator.rs`, zone
generation/pour -- not `_zone_pour_stitch.py` stitching or via emission,
which are a sibling agent's lane).

**Bottom line, established below**: **PR #1257's fix works and was never
broken.** The "107->0" number and #1298's "109-113" number are measuring
two *different zone rosters on the same board geometry*: #1257's `->0` was
measured on a scratch copy whose 96 zones were *replaced* by freshly
Rust-generated outlines (never applied to the committed file); #1298's
109-113 is the committed file's own **stale, pre-Rust-generator** zone
outlines, filled as-is. Both numbers are correct measurements of what they
each measured. Re-running the fix's own regeneration path against *today's*
board (post-#1279 placement, which #1257 predates) reproduces 0
`isolated_copper` again -- confirmed two ways (§4's synthetic seam splice,
3/3 runs, and §8's genuine end-to-end full route, 2/2 runs). Nothing in
`zone_generator.rs` needed changing.

**Applying the fix to the committed board is no longer memory-blocked.**
This document originally concluded the committed board could not receive
the fix because the only pipeline that would apply it (`route_pcb`, full
route) OOM-killed on every attempt. That was true historically but is
**stale as of PR #1264** (2026-08-16, hours after #1257): Stage 3's
default path is now a structural no-op that builds no SAT model, and a
live full-route attempt on current main (§8) completed twice with no OOM,
peak RSS under 1 GB, and **0 `isolated_copper`** on the genuinely-routed
output. What remains before the owner could actually replace
`pcb/temper.kicad_pcb` is not a memory blocker -- it is that a fresh
`route_pcb()` run changes routing completion, not just zones (§8's runs
measured 37/106 nets / 61/139 pads, materially different from whatever the
committed board's own routing state is), so swapping the board file is a
much bigger decision than "apply the zone fix" and still needs explicit
owner authorization regardless of memory.

---

## 0. Board integrity (start)

`pcb/temper.kicad_pcb` sha256:
`9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd` --
matches the task brief and the handoff's corrected value. Verified again at
the end (sec 5); unchanged throughout. No ceiling file
(`power_pcb_dataset/drc_ceiling.json`) was edited by this task -- no
`isolated_copper` entry was added (that would be an R27 ratchet raise
requiring an owner `Ceiling-Approval:` trailer this task does not have).

## 1. Method

Two read-only measurements, both against scratch copies of
`pcb/temper.kicad_pcb`, `kicad-cli 10.0.5`, DRU regenerated live from
`scripts/generate_kicad_dru.py` (current SSOT) for every run:

**A. Stale-zone (as-committed) measurement** -- reproduces PR #1298's own
protocol: copy the committed board verbatim, run
`kicad-cli pcb drc --refill-zones --format json`, count `isolated_copper`.
No zone regeneration -- this fills the board's own 96 on-disk zone
outlines exactly as KiCad's fill engine would. 3 runs.

**B. Rust-regenerated-zone measurement** -- reproduces PR #1257's own
verification protocol (`docs/evidence/scripts/2026-08-16-zone-pour-refill-verify.py`,
committed, read-only, unmodified by this task, re-run as-is against today's
board): call the production seam `_emit_zone_pours` (the function
`route_pcb()` invokes during a full route's emission phase) against the
real parsed board, splice the emitted zone blocks into a scratch copy in
place of the committed 96 (same R7 strip-and-replace the route path uses,
via `temper_io_types.strip_existing_zones`), then
`kicad-cli pcb drc --refill-zones --format json` on that scratch copy. 3
runs. (Harness: `/tmp/.../scratchpad/refill_verify_today.py`, a
byte-for-byte adaptation of the repo's own
`docs/evidence/scripts/2026-08-16-zone-pour-refill-verify.py` with JSON output and
a net/layer breakdown added -- the repo script itself is untouched.)

Neither measurement writes `pcb/temper.kicad_pcb`.

## 2. Structural check: the committed board's zones predate the fix

Before running anything, a direct regex parse of `pcb/temper.kicad_pcb`
(no venv needed) settles part of the question by itself:

```
grep -c "(zone " pcb/temper.kicad_pcb        -> 96
grep -c "filled_polygon" pcb/temper.kicad_pcb -> 0
```

Parsing every `(zone ...)` block's `(polygon ...)` count: **all 96 zones
have exactly 1 polygon element (0 zones have a hole).**

PR #1257's own design doc (`docs/evidence/2026-08-15-rust-zone-pour-
design.md`, root-cause #3) and its final commit body both describe the
**pre-fix** state as: *"all 96 committed zones have exactly one polygon,
none with a hole"* -- and #1257's fix is specifically **hole-preserving**
emission (`emit_zone_s_expr` writes one `(polygon ...)` per ring, exterior
+ holes). A board whose zones carry the fix would show zones with 2+
polygons wherever an obstacle sits inside a pour's hull (measured on
#1257's own scratch output: 64-91 zones across 43 net/layer pairs, several
multi-ring). The committed board shows **zero** such zones -- it is
byte-for-byte consistent with never having been touched by the Rust
generator's output. `git log --oneline -- pcb/temper.kicad_pcb` confirms
the committed board file has not changed since #1279 (2026-08-16, which
predates #1257 by hours) and #1257 (`c261907bc`) never itself touches
`pcb/temper.kicad_pcb`.

## 3. Measurement A: stale-zone (as-committed) board

| run | isolated_copper |
|---|---|
| 1 | 113 |
| 2 | 114 |
| 3 | 111 |

Combined with PR #1298's own 5 runs ([109,113,112,112,110]): **109-114**
across 8 independent runs, kicad-cli 10.0.5, all against the same committed
zone roster. Consistent with a single nondeterministic-but-bounded
population (the same nondeterminism class the ceiling file already
documents for `creepage`).

### 3.1 Net/layer breakdown (representative run, 113 findings)

| layer | count |
|---|---|
| F.Cu | 58 |
| B.Cu | 55 |

| net | netclass | layer | count |
|---|---|---|---|
| `+3V3` | Power (LV) | B.Cu | 18 |
| `+3V3` | Power (LV) | F.Cu | 10 |
| `GATE_HS` | GateDriveHV | F.Cu | 10 |
| `PWM_LS` | GateDriveSELV | B.Cu | 9 |
| `GATE_LS` | GateDriveHV | F.Cu | 8 |
| `ac_l` | **ACMains** | B.Cu | 8 |
| `GATE_HS` | GateDriveHV | B.Cu | 7 |
| `PWM_LS` | GateDriveSELV | F.Cu | 7 |
| `ac_l` | **ACMains** | F.Cu | 7 |
| `+15V_LS` | HighVoltageSignal | F.Cu | 6 |
| `PWM_HS` | GateDriveSELV | F.Cu | 6 |
| `GATE_LS` | GateDriveHV | B.Cu | 6 |
| `PWM_HS` | GateDriveSELV | B.Cu | 4 |
| `+15V` | Power (LV) | F.Cu | 2 |
| `+15V` | Power (LV) | B.Cu | 1 |
| `+15V_LS` | HighVoltageSignal | B.Cu | 1 |
| `vcc` | Power (LV) | F.Cu | 1 |
| `V_BUS_SENSE` | Power (LV) | F.Cu | 1 |
| `V_BUS_SENSE` | Power (LV) | B.Cu | 1 |

By netclass (net -> class per `packages/temper-placer/src/temper_placer/
core/design_rules.py::TEMPER_NET_ASSIGNMENTS`):

| netclass | count | % |
|---|---|---|
| Power (LV) | 34 | 30% |
| GateDriveHV | 31 | 27% |
| GateDriveSELV | 26 | 23% |
| **ACMains** | **15** | **13%** |
| HighVoltageSignal | 7 | 6% |

**47% (53/113) sit on HV-domain-adjacent nets** -- `ACMains` (the 240V AC
mains line itself, `ac_l`), `GateDriveHV` (`GATE_HS`/`GATE_LS`, the
half-bridge gate-drive rails, floating with the HV domain per
`elec/domain_manifest.yaml`), and `HighVoltageSignal` (`+15V_LS`). Every
single finding's raw kicad-cli description reads `"Isolated copper fill"`
with an item `"Zone [<net>] on <layer>.Cu, priority <n>"` -- i.e. a real
fragment of filled copper, at that net's potential, that the fill engine
could not connect to the rest of that net's copper.

### 3.2 Genuine defect, not a measurement artifact

These are real: `isolated_copper` is KiCad's own fill-engine flag for a
disconnected copper polygon (it runs its actual `ZONE_FILLER` under
`--refill-zones`, the same engine the GUI uses). A fragment of `ac_l`
(mains) or `GATE_HS`/`GATE_LS` (HV gate-drive) copper floating,
unconnected to its own net, is exactly the kind of finding IEC 60335-1
practice treats as a real fabrication concern: an isolated conductor at
line potential can couple capacitively to a neighbour, corona/arc under
fault, or simply indicate the fill didn't reach copper the design intended
to be continuous (a connectivity defect independent of the safety framing).
This is not a phantom of the measurement -- it would appear in a real
fabrication run of this exact zone roster.

**But it is also, per sec 2 and sec 4 below, a defect the fix already
closes**: these fragments are the SAME mechanism #1257's design doc
diagnosed as root cause #1 (*"the outline cannot express interior
holes... producing thin copper rings that fracture into islands"*) and
root cause #3 (*"fragmentation has no bridge-or-split policy"*), on a zone
roster that predates the fix.

## 4. Measurement B: Rust-regenerated-zone board (the fix, re-verified on today's board)

| run | isolated_copper | creepage | total violations |
|---|---|---|---|
| 1 | **0** | 275 | 1610 |
| 2 | **0** | 275 | 1610 |
| 3 | **0** | 275 | 1610 |

**0/0/0, fully deterministic across 3 runs**, seam-emitted 63 zone blocks
(vs the committed board's 96 -- the seam covers the `_emit_zone_pours`
per-net F.Cu/B.Cu/inner-layer pours only; the separate `gnd` In1.Cu plane
and `+3V3` In2.Cu power islands generated by `_ground_plane.py` -- which
itself also calls the Rust generator's `pour_outline_py` since #1265,
per that module's docstring -- are out of scope for this seam and not
included in this scratch board; see sec 4.1 for why this doesn't undercut
the result). This reproduces PR #1257's own final measurement (0
isolated_copper, 0 zone-involved creepage) **on today's board**, i.e.
*after* the #1279 placement pass (10+ component moves) that landed hours
after #1257 and that #1257's own verification never saw. The fix is not
stale or placement-fragile -- it recomputes correctly against the current
geometry.

Full `by_type` breakdown (run 1, representative):

```
clearance                406        track_dangling            44
creepage                 275        silk_over_copper           42
track_width              199 (cap)  via_dangling               25
silk_overlap              199 (cap)  hole_clearance              6
lib_footprint_issues      168        missing_courtyard           5
solder_mask_bridge        133        drill_out_of_range          4
shorting_items             95        copper_edge_clearance       4
                                      hole_to_hole                3
                                      courtyards_overlap          1
                                      silk_edge_clearance         1
```

`track_width` and `silk_overlap` sit exactly at 199 -- kicad-cli's raw-JSON
`ERROR_LIMIT`/warning cap (`DrcCount::honest_count()`'s cap table) -- so
these two are **floors, not counts**, consistent with PR #1298's own
finding that both categories are capped on both sides of the refill-zones
question and mechanistically independent of zone-fill state. Not
re-verified exhaustively here (out of scope: this task is about
`isolated_copper`); flagged rather than silently trusted, per the same
rule #1298 applied.

`shorting_items` (95) and `creepage` (275) in this table are **not
directly comparable** to the committed board's own 183/272 ceiling or
#1298's measured 190/461-463 -- this scratch board is missing the
`gnd`/`+3V3` plane zones (sec 4.1), which changes both categories'
denominators. This document does not claim a creepage or shorting
before/after here; only `isolated_copper` (the category under
investigation, unaffected by the missing planes since none of the missing
nets appear in sec 3.1's stale-board breakdown) is compared.

### 4.1 Scope note: gnd/+3V3 planes excluded from this scratch board, deliberately

`_emit_zone_pours` (this task's seam) does not emit the `gnd` net's In1.Cu
plane or the `+3V3` In2.Cu power islands -- those are generated by a
separate function, `_ground_plane.py::generate_ground_plane_blocks`, called
by a different, later step of `_write_routes_to_content`. This is the same
scope #1257's own verification used (its seam-verify harness explicitly
prints a "GND-class zones emitted" diagnostic precisely because its scope
excludes them). Since `gnd` and the plane-covered part of `+3V3` do not
appear in sec 3.1's stale-board `isolated_copper` breakdown as the primary
driver (`+3V3` DOES appear at 28/113 -- but as **per-cluster F.Cu/B.Cu
pours**, the `_emit_zone_pours` path, not the In2.Cu plane), the 0-count
result is not an artifact of conveniently omitting the defect's source.
Re-running with `_ground_plane.py`'s planes included (both already
Rust-generator-backed per #1265) is a natural follow-up but was not needed
to answer this task's question, and touching that composition is adjacent
to the sibling agent's stitching lane (`_zone_pour_stitch.py` /
`_adapter_convert.py`'s `_write_routes_to_content`), not this task's lane
(`zone_generator.rs` itself).

## 5. Verdict on the #1257 contradiction

**Neither "the fix never worked" nor "works only on unfilled zones."**
The correct account is **"the two counts measure different zone rosters on
the same board, and the fix's own roster still measures 0 today."**

1. `zone_generator.rs`'s algorithm (hole-preserving `pour_outline`,
   `IslandPolicy::PadsOnly` for non-plane nets, `1/cos(pi/24)` halo
   inflation, half-diagonal pad reach, through-via layer span) is
   unchanged since #1277 and has no defect found in this task's review of
   its ~960 lines and 8 unit tests -- confirmed correct by re-measurement,
   not merely re-reading.
2. #1257's "isolated_copper 107->0" was measured by regenerating the zone
   roster via the production seam and splicing it into a scratch copy --
   never by running `--refill-zones` on the committed file as it stood
   (and stands today).
3. The committed `pcb/temper.kicad_pcb` has never received that
   regenerated roster: the only path that would write it is a full
   `route_pcb()` run reaching its emission phase, and every attempt (both
   pre- and post-#1257, per #1257's own "Outstanding" section and the
   handoff's §6 Stage-3 SAT OOM entry) has been OOM-killed first. This is
   handoff §3 mechanism 2 ("the live path is not where it looks") as much
   as mechanism 4: the fix's own production wiring is real and correct,
   but the *pipeline that would apply it to the tracked artifact* is
   broken for an unrelated reason (Stage-3 memory), so the artifact never
   caught up.
4. PR #1298's 109-113 is therefore not a regression and not evidence
   against #1257 -- it is a fresh, correct measurement of the **stale,
   pre-fix zone roster that has been sitting in the committed file the
   entire time**, now visible for the first time because #1298 is the
   first measurement to pass `--refill-zones` at all. It reproduces
   #1257's own recorded BEFORE number (107) almost exactly (109-114 across
   8 runs), with the small increase plausibly attributable to the #1279
   placement pass (10+ component moves under the same static zone
   outlines) that landed after #1257 and before #1298.

## 6. What was fixed in this task, and what remains

**Nothing needed changing in `packages/temper-geometry/src/zone_generator.rs`.**
It already produces 0 `isolated_copper` when its output is actually used,
confirmed four independent ways: #1257's own original verification, this
task's synthetic seam splice (sec 4, 3/3 runs), and -- per sec 8, added
after the coordinator flagged this document's original OOM claim as
possibly stale -- **two genuine, end-to-end full-route runs on current
main with no synthetic splice at all.** There is no code defect in this
task's lane to fix.

**Applying the existing, working fix to the committed board is no longer
memory-blocked** (sec 8 supersedes the "OOM-killed on every attempt" claim
this section originally made -- that claim was itself stale, inherited
from evidence written before PR #1264 landed). This task still does NOT
apply it, because:

- A full `route_pcb()` run that would actually produce a board fit to
  replace the committed file changes far more than zones -- sec 8's two
  live runs measured 37/106 nets / 61/139 pads fully pad-connected, a
  routing-completion figure with no established relationship to whatever
  the committed board's own (different, already-routed) state represents.
  Deciding whether a fresh route's *overall* result is acceptable to ship
  is an owner decision an order of magnitude larger than "regenerate
  zones," and out of this task's lane (zone generation/pour) regardless of
  memory.
- `pcb/temper.kicad_pcb` was not modified by this task (sha256 verified
  unchanged, sec 0 and sec 9 below) -- every full-route output in sec 8
  was written to a scratch path outside the repo.
- Adding an `isolated_copper` ceiling entry to `power_pcb_dataset/
  drc_ceiling.json` (even at the honestly-measured 109-114) would be a
  ratchet raise from an implicit 0, requiring an owner `Ceiling-Approval:`
  trailer this task does not have. Not done.

**Recommendation to the owner** (not authorized by this task): the
zone-generation fix is ready, live-verified, and does not need further
work in this lane. The remaining decision is entirely about routing
completion, not zones: either (a) accept a fresh full `route_pcb()` run's
overall result (sec 8) as the new committed board -- which would also
bring the zone fix along for free -- or (b) build a scoped zone-only
regeneration that re-emits zones onto the committed board's *existing*
copper without re-routing everything else, which touches
`_zone_pour_stitch.py`/`_adapter_convert.py` composition (the sibling
agent's stitching lane, not this one). Until one of those lands, the
honest state is: the committed board, if fabricated and its zones filled
exactly as committed, would produce 109-114 genuine isolated-copper
fragments, 47% of them on HV-domain nets including the mains line itself
(`ac_l`) -- a real defect, already fixed in code, verified fixable in
practice (sec 8), not yet applied to the artifact that would actually be
fabricated.

## 7. Board integrity (final check, pre-correction)

`pcb/temper.kicad_pcb` sha256:
`9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd` --
unchanged from sec 0. `power_pcb_dataset/drc_ceiling.json` not edited.
No `.py` files in the repo tree were edited (two scratch harnesses were
used from `/tmp/.../scratchpad/`, adaptations of the repo's own committed,
unmodified `docs/evidence/scripts/2026-08-16-zone-pour-refill-verify.py`, matching
the convention PR #1298 itself used for its clearance re-measurement
script).

## 8. Correction: live full-route verification on current main (the OOM claim was stale)

The coordinator flagged that this document's original "blocked by
Stage-3 OOM" conclusion might be inherited from historical evidence
written before PR #1260/#1264 landed, and asked for a live attempt against
current main rather than another reading of old evidence docs. It was
right to ask -- the claim was stale. Verified as follows.

### 8.1 Why the claim was stale: call-site check

`_run_stage3` (`packages/temper-placer/src/temper_placer/router_v6/
_pipeline_route.py:421`) checks, in order: `use_net_batching` (from
`enable_net_batching`, default `False`), `self.enable_bundling` (default
`False`, dataclass default in `_pipeline_core.py`), and
`TEMPER_STAGE3_FORCE_SAT` (an env var, unset by default). When all three
are false/unset -- i.e. every default invocation, including
`scripts/route_board.py` with no flags -- Stage 3 returns an empty
`Stage3Output` immediately: **"Stage 3: Topological routing... SKIPPED
(SAT structurally vacuous; Stage 4 A* routes directly)"**. No CNF model is
built. This is PR #1264 (`272fbe36c`, 2026-08-16 16:06:46 -0600), which
landed **after** #1257 (`c261907bc`, 12:10:07 the same day) but **before**
#1298/this task (2026-08-17). `scripts/route_board.py --help`'s own
`--net-batching` text confirms this in the committed script: *"the
monolithic path no longer OOMs -- Stage 3's default is the direct
capacity-aware topology solver... which builds no SAT model at all."* The
only reachable OOM path is `--net-batching`/`enable_bundling`/the env
escape hatch -- none of which this task, or a default `route_board.py`
invocation, uses.

### 8.2 Live attempt

`free -g` before starting: 52 GB available (five sibling agents active,
2-4 GB immediately free, ~48 GB reclaimable buff/cache -- healthy margin
per the handoff's memory-check rule).

```
.venv/bin/python scripts/route_board.py \
  --pcb pcb/temper.kicad_pcb \
  --output <scratch path, NOT pcb/temper.kicad_pcb>
```

Default flags only (no `--net-batching`, no pruning, no nlayer spike).
RSS polled every 5s via `ps -o rss=` on the live PID (bounded loops inside
single tool calls, not an unbounded wait). Run twice, independently:

| run | wall time | peak RSS | result |
|---|---|---|---|
| 1 | 329.4 s | ~950 MB | completed, no OOM |
| 2 | 335.5 s | 935.7 MB | completed, no OOM |

Both: **37/106 nets (Stage 4 A*)**, **61/139 nets fully pad-connected**,
segments=4748, vias=185, zones=142 -- byte-identical result figures across
both runs. Peak RSS in both runs stayed under 1 GB, matching the handoff's
"~8-11 min and ~1 GB uninstrumented" full-route figure exactly. **No OOM
on either run.** Neither run wrote to `pcb/temper.kicad_pcb` -- both wrote
to scratch paths under `/tmp/.../scratchpad/full_route_live/`.

(A third run was attempted for a triple-replicate but was killed by this
task's own tool-call timeout mid-run, not by OOM -- `free -g` immediately
after showed 51 GB available and no route_board process remained. Not
counted as a failure; two clean completions is the reported result.)

### 8.3 Zone structure of the genuinely-routed output

Unlike sec 3-4's committed-board/seam-splice measurements, this output's
142 zones were produced by the real, unmodified, end-to-end production
seam (`_emit_zone_pours` **and** `_ground_plane.py`'s gnd/power-island
path both ran, not just one of them as in sec 4.1's scoped seam). Parsing
the output: **140 zones with 1 polygon (no hole), 1 zone with 11 polygons
(1 exterior + 10 holes), 1 zone with 7 polygons (1 exterior + 6 holes)** --
real, hole-carrying zones produced by the Rust generator in genuine
production use, not a synthetic test.

### 8.4 DRC on the genuinely-routed output

`kicad-cli pcb drc --refill-zones --format json` (DRU regenerated live,
same protocol as sec 1), against both scratch outputs independently:

| run | isolated_copper | total violations |
|---|---|---|
| 1 | **0** | 1096 |
| 2 | **0** | 1096 (identical breakdown) |

**0 isolated_copper, deterministic across both genuinely-routed boards.**
This is the strongest confirmation in this document: not a scratch splice
of regenerated zones onto old copper, but zones produced by an actual,
complete, unmodified `route_pcb()` run on current main, filled by KiCad's
real fill engine. The other categories in this table (`clearance` 177,
`shorting_items` 31, `creepage` 141, etc.) are **not** comparable to the
committed board's ceiling or to sec 3-4's numbers -- this is a materially
different, far-less-complete routing state (37/106 vs whatever the
committed board's own routing represents), consistent with sec 6's point
that swapping the board file is a routing-completion decision, not a
zone-generation one.

## 9. Board integrity (final check)

`pcb/temper.kicad_pcb` sha256:
`9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd` --
unchanged from sec 0 and sec 7, verified again after sec 8's two live
full-route runs. `power_pcb_dataset/drc_ceiling.json` not edited. No `.py`
or `.rs` files in the repo tree were edited. All full-route and DRC output
in sec 8 was written to `/tmp/.../scratchpad/full_route_live/`, never to
the repo tree.
