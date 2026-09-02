<!-- provenance: commit=9085ff1b746db71d9849b594930327d6b03af97f dirty=true (persistent main commit for PR #1378 carrying this evidence and the described fix; the original record states that _ground_plane.py + test_ground_plane.py were uncommitted alongside this doc at measurement time).
pcb/temper.kicad_pcb was NEVER written by this task -- every kicad-cli run below
executes against a byte-for-byte scratch copy under a task-owned temp directory;
sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
unchanged before and after every experiment (asserted in-process, not by eye). -->

# `via_dangling` 25 -> 111: attribution, enumeration, and the plane-stitch fallback (2026-08-18)

Follow-on to `docs/evidence/2026-08-17-via-dangling-25-real-defects.md` (the 25
characterisation) and PR #1298 (`--refill-zones` null result). Issue #1370.

## 0. Bottom line

* The committed board reads **`via_dangling` = 111** against a
  `warnings_by_type` ceiling of **25** (`power_pcb_dataset/drc_ceiling.json`;
  it is a WARNING category, not an error -- the brief's "ratchet ceiling of 25"
  is in `warnings_by_type`, not `violations_by_type`).
* **All of the growth is one commit**: `23b5daf8d` (**PR #1312**, "regenerate
  the board's copper") took it 25 -> 106. #1279/#1299 contributed 0, #1316
  contributed 0, #1333 +3, #1334 +2. Per-commit series in sec 2.
* It is **not** growth of the old defect -- it is **total population
  replacement**. The 25 were signal-net vias from the `via_layer_pair`
  `("F.Cu","B.Cu")` fallback; #1307 fixed that and **all 25 are gone**. The 111
  are a brand-new class: plane-stitch vias on 5 plane nets.
* **83 of the 111 (75%) are an artifact** of the committed board carrying **zero
  filled zone polygons**. `--refill-zones` takes 111 -> 28, deterministically.
* **28 are genuine** and survive `--refill-zones`.
* Root cause of the largest genuine group: `_ground_plane._find_via_drop_point`'s
  **pass-2 fallback**, which emitted a stitching via *outside its own net's pour*
  when no pour-inside point existed. **Fixed** here (fail closed). Measured on
  the committed board: `via_dangling` 111 -> 86, and 28 -> 13 under refill;
  total DRC violations 778 -> 691, `unconnected_items` unchanged at 0.
* The **`via_layer_pair` hardcoded-`("F.Cu","B.Cu")` lead is DISPROVED for this
  population** (sec 4.2) and the **`drop_redundant_vias` lead is DISPROVED**
  (sec 4.1) -- both measured, not argued.
* **No ceiling was re-baselined.** The +86 delta is reported, not absorbed.

## 1. Measurement conditions (stated for every number below)

No `route_board.py` was run and **no cProfile was attached** -- every number is a
`kicad-cli pcb drc` measurement over an existing board file, not a routing run.
Machine load average 3.6-6.8 throughout (24-core box); the counts are
deterministic across repeats, so load did not move them.

Protocol per AGENTS.md "Measurement Instruments That Lie":
scratch copy of the board; sibling `.kicad_pro`; sibling `fp-lib-table` +
`sym-lib-table`; `.kicad_dru` **regenerated** from `scripts/generate_kicad_dru.py`
(33208 bytes, 18 `clearance` + 6 `creepage` + 12 `track_width` rules);
`--all-track-errors`; single-thread `KICAD_CONFIG_HOME` pin
(`_single_threaded_kicad_env`); kicad-cli **10.0.5**; **3 runs, intersected**.

Harness validity checks (both required, both passed): `lib_footprint_issues`
read **16**, not the 168 no-`fp-lib-table` signature; `creepage` read **106**,
not the 0 no-DRU signature. `silk_overlap` reads exactly **199** = the
`ERROR_LIMIT` cap, i.e. saturated -- its true value is unknown and it is
excluded from every claim here.

`via_dangling` measured **[111, 111, 111]**; the flagged-UUID sets were
identical across all 3 runs (intersection == union == 111), so this category is
deterministic on this board.

## 2. Per-commit series -- the bisection

Constant DRU/project/lib-tables across all six boards, so the only variable is
the board file. `via_dangling` is a pure connectivity check and is unaffected by
DRU content.

| commit | PR | board sha256 | vias | segments | `via_dangling` | delta | `track_dangling` |
|---|---|---|---|---|---|---|---|
| `c1f7025d3` | (ceiling board) | `9c1f4a37b03c` | 44 | 2149 | **25** | -- | 44 |
| `aec4bf1f8` | #1299 | `bf2dbb3dcd48` | 44 | 2149 | **25** | 0 | 44 |
| `23b5daf8d` | **#1312** | `33205399398f` | 188 | 4644 | **106** | **+81** | 0 |
| `968d1a33d` | #1316 | `6ac8b1ca8a64` | 176 | 4712 | **106** | 0 | 0 |
| `342e1bd08` | #1333 | `cb5184eae9fe` | 167 | 4990 | **109** | +3 | 8 |
| `11a7e7c52` | #1334 (HEAD) | `26981fea2dbc` | 169 | 4553 | **111** | +2 | 0 |

**PR #1312 accounts for 81 of the 86.** PR #1279 touched no board file at all.
Board = 4553 segments / 169 vias at HEAD (the figure four agents agreed on).

## 3. Enumeration of all 111

Rows resolved by item **UUID** against the board's own `(via ...)` records, not
by kicad-cli's free-text net label (unreliable per the 2026-08-17 doc sec 2.2).
111/111 resolved; 111 **distinct** vias, i.e. one row each, 66% of the board's
169 vias.

They are strikingly uniform -- **one group, not 111 independent defects**:

* **layer pair**: `("F.Cu","B.Cu")` for all 111 (100%)
* **geometry**: size 1.0mm / drill 0.4mm for all 111 (100%)
* **kind**: through-via for all 111

| net | # | net's own segments | segment layers | zone layer |
|---|---|---|---|---|
| `gnd` (48) | 61 | 82 | F.Cu only | **In1.Cu** |
| `+3V3` (4) | 33 | 98 | F.Cu only | **In2.Cu** |
| `vcc` (158) | 9 | 0 | -- | **In2.Cu** |
| `+15V` (1) | 5 | 0 | -- | **In2.Cu** |
| `V_BUS_SENSE` (23) | 3 | 0 | -- | **In2.Cu** |

Exactly 5 nets, and they are **exactly** the board's inner-plane nets. By
contrast the 58 *unflagged* vias are `blind` vias at 0.9/0.3 on signal nets with
real `In3.Cu`/`In4.Cu` transitions -- a completely different, healthy population.

The 1.0/0.4 `("F.Cu","B.Cu")` signature identifies the emitter uniquely. Only
two code sites emit it, and their split matches the counts exactly:

* `router_v6/_ground_plane.py:1126` (`PLANE_LAYER = "In1.Cu"`) -> `gnd`: **61**
* `router_v6/_power_islands.py:719` (`PLANE_LAYER = "In2.Cu"`) -> the 4 rails: **50**
* 61 + 50 = **111**

(The third raw-via emitter, `_zone_pour_stitch.py:834`, parameterises its layer
correctly off `_STITCH_LAYER` and contributes none.)

## 4. Classification, by measurement

### 4.0 The 2x2 that settles it

| board variant | `--refill-zones` | `via_dangling` |
|---|---|---|
| committed | no | **111** |
| committed | **yes** | **28** |
| via layer pairs corrected to `F.Cu`/`In1.Cu` + `F.Cu`/`In2.Cu` | no | **111** |
| via layer pairs corrected | **yes** | **28** |

### 4.1 DISPROVED: `drop_redundant_vias` (lead 1)

It **is** reached on the production path (`_pipeline_route._run_stage5:1053`).
But it is measurably not the cause: it landed in #1316, which removed 12 vias
from the board (188 -> 176) and moved `via_dangling` by **exactly 0**
(106 -> 106). *Latent hazard worth a separate ticket, not observed here*: it
dedupes on quantised **position only, ignoring the layer pair**, so a legitimate
stacked pair (e.g. `F.Cu->In3.Cu` + `In3.Cu->B.Cu` at one point) would lose a
member. No such pair exists on this board.

### 4.2 DISPROVED: the `via_layer_pair` `("F.Cu","B.Cu")` fallback (lead 2)

The #1307 fix **worked**: all 25 of the old signal-net dangling vias are gone,
and none of the 17 old nets appears in the 111.

For the *new* population the hardcoded pair is **not** the mechanism, and this
is measured rather than reasoned: rewriting all 111 vias' layer pairs to the
plane layer their own generator declares (`gnd`->`F.Cu`/`In1.Cu`, rails->
`F.Cu`/`In2.Cu`) changed `via_dangling` by **exactly 0**, both with and without
refill (sec 4.0). A through-via already spans In1/In2 physically; declaring it
`F.Cu`/`B.Cu` is cosmetically wrong but electrically irrelevant here.

### 4.3 ARTIFACT (83 of 111, 75%): unfilled zones

`pcb/temper.kicad_pcb` contains **151 zones and 0 `filled_polygon` blocks**.
`_drc_api.run_drc` does not pass `--refill-zones`, so kicad-cli sees no plane
copper at all and every plane-stitch via looks unconnected.

Verified by an independent geometric reconstruction, not just by the count:
refilled with `--refill-zones --save-board`, then point-in-polygon each via
against its own net's fill -- **82 of the 83** land inside their net's plane
pour (the 83rd is 0.406mm outside). These vias do what they were designed to do.

Reconciles PR #1298 rather than contradicting it. Same experiment, same harness:

| board | no refill | refill |
|---|---|---|
| `c1f7025d3` (#1298's board) | 25 | **25** |
| `aec4bf1f8` | 25 | **25** |
| `23b5daf8d` (#1312) | 106 | **24** |
| `11a7e7c52` (HEAD) | 111 | **28** |

PR #1298's null result was **correct on the board it measured** and became stale
the moment #1312 introduced the In1/In2 pours and 100+ plane-stitch vias.

### 4.4 GENUINE (28 of 111): vias that reach at most one layer

All 28 survive `--refill-zones` (deterministic, 3/3, intersection == union).
`gnd` 14, `+15V` 4, `vcc` 4, `+3V3` 3, `V_BUS_SENSE` 3. An independent
reconstruction of each via's copper contacts (this net's tracks, pads with
footprint rotation applied, other vias' pads, and the refilled pours) agrees
with KiCad on every one of the 28:

| contacts | count | reading |
|---|---|---|
| plane fill only | 13 | connected on exactly one layer |
| **nothing on any layer** | **10** | a drilled hole connected to nothing |
| F.Cu only | 5 | connected on exactly one layer |

15 of the 28 sit **outside** their own net's filled pour (median 52mm, max
211mm away -- not a near-miss).

*Model limitation, stated rather than hidden*: for 29 of the 83 artifact vias
the same reconstruction finds only one contact layer while KiCad finds two, so
it is conservative -- most likely missing fill thermal-relief spokes. It is
corroboration for the 28, not the primary evidence; the primary evidence is the
DRC measurement.

## 5. Root cause and fix

`_ground_plane._find_via_drop_point` (imported and shared by `_power_islands`)
searched twice: pass 1 required the via footprint inside the net's pour; **pass 2
dropped that requirement**, justified in its own docstring by

> "a via outside the pour can still be joined by the F.Cu MST backbone, so
> connectivity never regresses -- the plane just does not add to it"

That justification is false on this board. The F.Cu backbone it assumes is not
guaranteed to exist: on the committed board `mst_edges` **drops 72 backbone
edges** for the four `_power_islands` rails alone (48 `+3V3`, 12 `vcc`, 9
`+15V`, 3 `V_BUS_SENSE`) because they cross the HV keepout and cannot be
detoured -- it logs "the backbone may be a forest, not a single tree". A pass-2
via can therefore reach neither the plane nor the backbone, which is exactly the
10 vias contacting nothing at all.

This is the **same shape** as the `via_layer_pair` defect #1307 fixed: *a
fallback that emits a via it has no geometric basis for, instead of declining to
emit one.* Same fix discipline -- fail closed:

```python
if pour_region is not None:
    return _search(require_pour=True)   # was: fall through to pass 2
return _search(require_pour=False)
```

Instrumented on the committed board (read-only, generators called directly):

| generator | vias before | vias after | pass-2 (outside pour) before -> after |
|---|---|---|---|
| `_ground_plane` (gnd) | 66 | 64 | 2 -> 0 |
| `_power_islands` (4 rails) | 58 | 40 | 18 -> 0 |

Pass-1 counts are **unchanged** (64 and 40): the fix removes exactly the
unjustifiable vias and nothing else.

Attributable effect on the committed board (dropping the 25 vias whose footprint
is not inside their own pour, on a scratch copy):

| variant | refill | `via_dangling` | `unconnected_items` | `track_dangling` | `clearance` | total |
|---|---|---|---|---|---|---|
| baseline | no | 111 | 0 | 0 | 179 | 778 |
| **fix** | no | **86** | **0** | **0** | **122** | **691** |
| baseline | yes | 28 | 0 | 0 | 180 | 721 |
| **fix** | yes | **13** | **0** | **0** | **123** | **644** |

**No category shift** -- unlike the 2026-08-17 via deletion, which pushed ~23
findings into `track_dangling`. `unconnected_items` stays 0 and `track_dangling`
stays 0, i.e. the dropped vias were carrying no connectivity. Collateral falls
are real: `clearance` -57, `copper_edge_clearance` -3, `hole_clearance` -1,
`shorting_items` -1.

The board is not regenerated here (no board-write authorisation), so the
committed board still carries these vias; the fix takes effect on the next route.

## 6. Remaining, NOT fixed here

* **13 vias inside their pour with no F.Cu-side copper.** These need the MST
  backbone to actually reach them; the 72 dropped backbone edges are a routing
  problem, not a via-emission one. Out of this lane.
* **The 83 unfilled-zone artifacts.** The board file ships with 0 filled
  polygons while declaring 151 zones. Worth deciding deliberately: either the
  board should be committed filled, or the ceiling protocol should measure with
  `--refill-zones`. Changing the ceiling protocol is out of scope here and would
  move many categories at once (total 778 -> 721) -- it must not be done to make
  a number look better.
* **Two tests fail on unmodified `origin/main`**, both asserting the production
  board has *no* `gnd`/`+3V3` copper before the generator runs -- untrue since
  #1312 regenerated the board's copper. Verified pre-existing by reverting this
  fix and re-running (`2 failed, 1 passed` both ways):
  `test_ground_plane.py::TestGenerateGroundPlaneOnRealBoard::test_gnd_plane_improves_real_board_pad_connectivity`
  and
  `test_power_islands.py::TestGeneratePowerIslandsOnRealBoard::test_power_islands_are_expressible_and_measurably_improve_connectivity`.
  Another unattributed #1312 casualty; belongs with #1370.

## 7. Ceiling

Not touched. Measured deltas vs `power_pcb_dataset/drc_ceiling.json` (same
no-refill protocol the ceiling was measured with), for the record only:
`via_dangling` **+86** (25 -> 111), `copper_edge_clearance` +7,
`lib_footprint_issues` +3, `drill_out_of_range` +2; and large falls elsewhere
(`clearance` -938, `track_width` -393, `creepage` -166, `shorting_items` -144,
`track_dangling` -44). Six board-changing PRs landed without re-measuring; that
is issue #1370's subject and is left to it.
