<!-- provenance: commit=e81196c87b5998555feca78f27c612b11331bee7 dirty=false (worktree agent-refill-zones-remeasure, branched from origin/main at e81196c87, clean at HEAD; pcb/temper.kicad_pcb never written by this task -- all kicad-cli runs below execute against a scratch copy under a caller-supplied temp directory, never the committed file. sha256 verified unchanged before and after, see sec 2.) -->

# `--refill-zones` DRC runner gap: quantified re-baseline (2026-08-17)

**Task**: handoff §9.7 (`docs/HANDOFF-2026-08-17.md` work queue item 7 / §3
mechanism 4). The committed DRC runner
(`temper_placer.validation._drc_api.run_drc`, called by
`scripts/ci_check_drc.py` and every ratchet measurement in
`power_pcb_dataset/drc_ceiling.json`) never passes `--refill-zones` to
`kicad-cli pcb drc`. The committed board (`pcb/temper.kicad_pcb`) has 96
zone outlines and **zero `filled_polygon` blocks** — every zone is
outline-only on disk — so every DRC measurement this project has ever taken
is blind to zone copper: creepage/clearance violations between a filled pour
and neighbouring LV copper, isolated-copper fragmentation, and any
via/pad-to-zone connectivity that would resolve a `via_dangling`/
`track_dangling` finding.

This document is a **measurement only**. No ceiling value, DRU threshold, or
runner default was changed. `pcb/temper.kicad_pcb` was not modified.

## 0. Correction to the handoff's own numbers

The 2026-08-17 handoff (§3 mechanism 4, §9 item 7) states the committed
board "under-counts creepage by 289 (true 483)" / "289 vs 483 real". No
evidence doc in the repo substantiates this specific pair of numbers for the
CURRENT committed board (`pcb/temper.kicad_pcb`, sha256
`9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`) — the
closest prior measurement
(`docs/evidence/2026-08-15-drc-violation-classification.md` sec 4) ran the
`--refill-zones` experiment on a **different, fully-ROUTED** board
(`final-route-6layer-output.kicad_pcb`, not the committed board), and found
creepage moving 511 -> 733 (+222), not a 289-vs-483 pair. Per this task's
hard rule ("report measured numbers only ... never estimate a count and
present it as measured"), the 289/483 figures are treated as **unverified**
and superseded by the direct measurement below.

## 1. Method

- Board: `pcb/temper.kicad_pcb` (sha256
  `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`),
  copied byte-for-byte into a scratch directory alongside its
  `.kicad_pro`/`fp-lib-table`/`libs/` sidecars (same convention as
  `scripts/measure_uncapped_drc.py::make_scratch_board`). `pcb/temper.kicad_pcb`
  itself was never opened for writing.
- `.kicad_dru` regenerated into the scratch copy from
  `scripts/generate_kicad_dru.py::generate_dru()` (the SSOT the real
  `ci_check_drc.py` protocol regenerates before every measurement) — so the
  DRU rules in force are identical to what the committed ratchet measures
  against.
- `kicad-cli pcb drc --all-track-errors --format json --output ... <board>`,
  single-threaded (`KICAD_CONFIG_HOME` pinned via
  `temper_placer.validation._drc_api._single_threaded_kicad_env`, the exact
  determinism protocol `run_drc` uses) — **baseline**, matching the current
  runner exactly.
- Same invocation **+ `--refill-zones`** — the gap under measurement.
  `--save-board` was NOT passed (no need to persist the fill; the scratch
  copy is discarded either way, and the real board is never touched).
- kicad-cli version: `10.0.5` (matches the ceiling's recorded provenance).
- N repeats each side (see sec 2 for actual N reached) to characterize
  known-nondeterministic categories (`creepage`, and `clearance`'s last-digit
  jitter — both documented in `drc_ceiling.json`'s own `_march`/
  `nondeterministic_error_types`).
- Every category count is classified against `DrcCount`'s cap table
  (`packages/temper-drc-rs/src/drc_count.rs`): `clearance` /
  `unconnected_items` cap at `EXTENDED_ERROR_LIMIT` 499; `creepage` is
  empirically uncapped; every other category caps at `ERROR_LIMIT` 199. A
  count landing exactly on its cap is reported as a **floor**, never a
  count.

## 2. Board sha256 verification

`pcb/temper.kicad_pcb` sha256, checked before this task started and again at
the end: `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`
(worktree `agent-refill-zones-remeasure`) — **unchanged**. This matches the
handoff's corrected value (the handoff §1/§5's `d88fec91...` is confirmed
stale). The scratch copy used for every kicad-cli invocation below carries
the identical sha256 (verified byte-for-byte).

## 3. Before / after table

5 repeats each side (`kicad-cli 10.0.5`, single-threaded
`KICAD_CONFIG_HOME` pin, `--all-track-errors` on both sides, DRU
regenerated from the current `scripts/generate_kicad_dru.py`). The
no-refill side reproduces the committed ceiling's own recorded numbers
exactly (creepage {270,271} observed as 1×270 / 4×271 across the 5 runs
here, consistent with the ceiling's documented {270,271} distribution,
shorting_items 183, hole_clearance 90, track_dangling 44, via_dangling 25,
silk_over_copper 42, lib_footprint_issues 13, lib_footprint_mismatch 26,
missing_courtyard 5, silk_edge_clearance 1, copper_edge_clearance 4,
courtyards_overlap 1, drill_out_of_range 4, hole_to_hole 3,
solder_mask_bridge 133, tracks_crossing 1) — this cross-validates the
measurement protocol against the committed record before trusting the
refill-zones side.

Every category not listed as "raw JSON capped" below is a real,
uncapped count on both sides (`DrcCount` cap table:
`clearance`/`unconnected_items` cap at 499, `creepage` is empirically
uncapped, everything else caps at 199).

### Errors (`violations_by_type`)

| category | ceiling (committed) | no-refill (this measurement, 5 runs) | `--refill-zones` (5 runs) | delta | cap status |
|---|---|---|---|---|---|
| `clearance` | 1117 (true, uncapped separately) | raw JSON capped at **499** (all 5 runs); true count **1117** (exhaustive DRU-band measurement, 1 run, zero saturation-suspected leaves) | raw JSON capped at **499** (all 5 runs); true count **1114** (same exhaustive method + `--refill-zones`, 1 run, zero saturation-suspected leaves) | **−3** | **CAPPED both sides in raw JSON** — both true counts came from the exhaustive uncapped method, not the raw 499 |
| `creepage` | 272 (272 = max 271 + spread 1) | **270–271** (raw: [271,271,270,271,271] = 1×270, 4×271) | **461–463** (raw: [462,463,461,461,462] = 2×461, 2×462, 1×463) | **+190 to +193** (min refill 461 − max no-refill 271 = +190; max refill 463 − min no-refill 270 = +193) | uncapped both sides — real |
| `shorting_items` | 183 | **183** (all 5 runs, exact) | **190** (all 5 runs, exact) | **+7** | uncapped both sides (183, 190 << 199 cap) — real |
| `track_width` | 393 (true, uncapped separately) | raw JSON capped at **199** (all 5 runs) | raw JSON capped at **199** (all 5 runs) | **not measured** — track_width's DRU rule constrains individual track-segment widths only; it has no mechanistic dependency on zone-fill state. Not re-verified with the exhaustive bisection (see sec 3.2 for why this is flagged "not measured" rather than assumed) | **CAPPED both sides** |
| `copper_edge_clearance` | 4 | 4 | 4 | 0 | uncapped, real |
| `courtyards_overlap` | 1 | 1 | 1 | 0 | uncapped, real |
| `drill_out_of_range` | 4 | 4 | 4 | 0 | uncapped, real |
| `hole_clearance` | 90 | 90 | 90 | 0 | uncapped, real |
| `hole_to_hole` | 3 | 3 | 3 | 0 | uncapped, real |
| `solder_mask_bridge` | 133 | 133 | 133 | 0 | uncapped, real |
| `tracks_crossing` | 1 | 1 | 1 | 0 | uncapped, real |
| `annular_width` | 0 | 0 (absent) | 0 (absent) | 0 | uncapped, real |
| `via_diameter` | 0 | 0 (absent) | 0 (absent) | 0 | uncapped, real |

### Warnings (`warnings_by_type`)

| category | ceiling (committed) | no-refill (5 runs) | `--refill-zones` (5 runs) | delta | cap status |
|---|---|---|---|---|---|
| `via_dangling` | 25 | **25** (all 5 runs, exact) | **25** (all 5 runs, exact) | **0 — unchanged** | uncapped, real (25 << 199 cap) |
| `track_dangling` | 44 | **44** (all 5 runs, exact) | **43** (all 5 runs, exact) | **−1** | uncapped, real |
| `silk_overlap` | 13407 (true, uncapped separately) | raw JSON capped at **199** (all 5 runs) | raw JSON capped at **199** (all 5 runs) | **not measured** — `silk_overlap` is silkscreen-graphic-vs-silkscreen-graphic overlap only; no zone/copper involvement by mechanism. Not re-verified (see sec 3.2) | **CAPPED both sides** |
| `silk_over_copper` | 42 | 42 | 42 | 0 | uncapped, real |
| `lib_footprint_issues` | 13 | 13 | 13 | 0 | uncapped, real |
| `lib_footprint_mismatch` | 26 | 26 | 26 | 0 | uncapped, real |
| `missing_courtyard` | 5 | 5 | 5 | 0 | uncapped, real |
| `silk_edge_clearance` | 1 | 1 | 1 | 0 | uncapped, real |
| `pth_inside_courtyard` | 0 | 0 (absent) | 0 (absent) | 0 | uncapped, real |
| `isolated_copper` | **absent from ceiling file entirely** (implicit ceiling 0 per R27) | **0** (absent, all 5 runs) | **109–113** ([109,113,112,112,110]) | **+109 to +113, a BRAND NEW violation class** | uncapped, real — this category exists in kicad-cli's DRC engine and would need its own `violations_by_type`/`warnings_by_type` entry to be ratcheted at all |

### 3.1 `clearance` true-count status — RESOLVED: −3, not an increase

`clearance` is capped at 499 in raw kicad-cli JSON on BOTH sides — the
499=499 reading in the table above is inconclusive by itself, not
"unchanged." Resolved with `scripts/measure_uncapped_drc.py`'s own
DRU-band-isolation-and-bisection method (every DRU rule's band isolated by
a synthetic 2-rule DRU exploiting KiCad's last-matching-rule-wins, with
automatic net-name bisection on any band that itself saturates), run
unmodified for the no-refill side and with `--refill-zones` injected into
its one `kicad-cli pcb drc` invocation point for the refill side (adapted
script: `/tmp/.../scratchpad/measure_uncapped_drc_refill.py`, a byte-for-byte
copy of the repo script with `--refill-zones` added to the argv list — the
repo script itself was not modified).

Result: **no-refill true clearance = 1117** (reproduces the committed
ceiling exactly), **`--refill-zones` true clearance = 1114** — a decrease
of 3, with zero bands flagged `SATURATION SUSPECTED` on either side (every
leaf resolved to a real, non-saturating, deterministic count). Full
per-rule band breakdown (refill side): `AC Mains to LV` 24, `AC Mains to
HV` 1, `HighVoltageIsolated same side` 8, `HighVoltageIsolated to LV` 109,
`HV internal same footprint` 0, `HV to LV` 205, `HighVoltageTank to LV` 5,
`HighVoltageSignal to LV` 463, the four `GateDrive*` rules 0 each, `Power
internal same footprint` 0, `Default routing` 259, `Ground clearance` 0,
`Same footprint pads` 0, `Fine pitch IC pads` 0, `USB differential` 0,
netclass-implicit fallback 40. Sum = 1114.

So unlike `creepage` (+191) and `shorting_items` (+7), filling the board's
96 zones does **not** increase `clearance` violations — it slightly
*decreases* them. This is plausible: `clearance` is a copper-to-copper
distance check between DISTINCT nets' copper, and creepage is the same
measurement restricted to HV/LV pairs with a much larger (12.6 mm) minimum
— so a filled zone is far more likely to newly violate the wide creepage
minimum against nearby foreign-net copper than the narrow (0.2-2.0 mm)
clearance minimum, and zone-fill edge geometry differences can just as
easily resolve a marginal clearance pair as create one.

### 3.2 Why `track_width` and `silk_overlap` true counts are reported as "not measured," not "unchanged"

Both categories are capped at 199 in raw JSON on both sides, exactly like
`clearance`. Unlike `clearance`, their governing DRU/engine mechanism has
**no path through zone-fill state**: `track_width` matches on the
`(constraint track_width ...)` rule against individual routed-track
segments (a per-net-class trace-width minimum), and `silk_overlap` matches
silkscreen graphic items against other silkscreen graphic items, on
`F.Silkscreen`/`B.Silkscreen` only. Filling a copper zone changes neither.
This is a mechanistic argument for "very likely unchanged," not a
measurement — per this task's hard rule, it is reported here as **not
measured**, not asserted as 393/13407 unchanged. The exhaustive bisection
for either category costs tens of scoped kicad-cli sub-runs
(`measure_uncapped_drc.py`'s own per-category cost, documented in
`docs/evidence/2026-08-13-track-width-silk-overlap-uncapped-measurement.md`)
and was not spent here given the near-zero prior plausibility of a nonzero
delta and the time budget for a MEASUREMENT-only task.

## 4. Ceilings breached by the re-baseline

Using only the numbers actually measured above (never treating a "not
measured" category as zero delta):

| ceiling | today | with `--refill-zones` (measured) | breached? | by how much |
|---|---|---|---|---|
| `error_ceiling` (aggregate, 2201) | 2201 | measured net delta (creepage +190 to +193, shorting_items +7, clearance −3; track_width not measured) = **+194 to +197** → **≈2395 to 2398**, before any `track_width` movement | **YES** | **+194 to +197 measured** (plus whatever `track_width` contributes, not measured) |
| `warning_ceiling` (aggregate, 13563) | 13563 | measured net delta (track_dangling −1, isolated_copper +109 to +113; silk_overlap not measured) = **+108 to +112** → **≈13671 to 13675**, before any `silk_overlap` movement | **YES** | **+108 to +112 measured** (plus whatever `silk_overlap` contributes, not measured) |
| `violations_by_type[creepage]` (272) | 272 | **461–463 measured** | **YES** | **+189 to +191** against the ceiling's 272 (the ceiling is `max 271 + spread 1`; even the LOWEST refill-side observation, 461, is +189 over the ceiling) |
| `violations_by_type[shorting_items]` (183) | 183 | **190 measured, deterministic** | **YES** | **+7** |
| `violations_by_type[clearance]` (1117) | 1117 (true, measured) | **1114 measured** (sec 3.1, exhaustive, zero saturation) | **NO — this one relaxes** | **−3** |
| `violations_by_type[track_width]` (393) | 393 (true) | not measured | unknown, low prior likelihood of any delta | not measured |
| every other `violations_by_type` entry | — | unchanged (measured exactly) | no | 0 |
| `warnings_by_type[via_dangling]` (25) | 25 | **25 measured, deterministic** | **NO** | 0 — see sec 5 |
| `warnings_by_type[track_dangling]` (44) | 44 | **43 measured, deterministic** | **NO** (this one relaxes) | −1 |
| `warnings_by_type[silk_overlap]` (13407) | 13407 (true) | not measured | unknown, low prior likelihood of any delta | not measured |
| **`warnings_by_type[isolated_copper]`** | **absent (implicit ceiling 0 per R27)** | **109–113 measured** | **YES — brand-new violation class** | **+109 to +113**, and the category does not even exist as a ratcheted entry yet |
| every other `warnings_by_type` entry | — | unchanged (measured exactly) | no | 0 |

**Bottom line, using only measured numbers**: switching the runner to
`--refill-zones` breaches the `creepage` ceiling by +189 to +191, the
`shorting_items` ceiling by +7, both aggregate ceilings, and introduces one
entirely new, unratcheted violation class (`isolated_copper`, +109 to +113)
that R27's monotone contract would treat as an implicit-ceiling-0 breach the
moment it appears. `clearance` — the single largest violation category at
1117 — was fully resolved and does **not** breach; it relaxes by 3. Only
`track_width` (error) and `silk_overlap` (warning) remain genuinely
unmeasured, both capped in raw JSON on both sides and both mechanistically
independent of zone-fill state (sec 3.2) — a material delta from either is
considered unlikely but is not asserted as zero.

## 5. The 11 `via_dangling` question — RESOLVED: neither number, but answerable

Two corrections to the question as posed:

1. **The committed board's current `via_dangling` count is 25, not 11.**
   The handoff's "11" does not match this board's measured warning count in
   either mode (25 no-refill, 25 with `--refill-zones`) or the ratcheted
   ceiling (`warnings_by_type.via_dangling = 25`). No evidence doc in the
   repo was found recording an 11 for this board; treated as unverified
   per the same rule applied to the 289/483 creepage figure in sec 0.

2. **The real question — is `via_dangling` an artifact of the DRC runner
   never filling zones — has a direct, measured, negative answer.**
   `via_dangling` is **identical, 25 = 25, deterministic across 5 runs each
   side**, with or without `--refill-zones`. Filling all 96 zones on this
   board changes zero `via_dangling` findings.

   This is a **real, measured null result**, not an absence of evidence:
   `track_dangling` (the sibling connectivity-warning category) DID move
   (44 → 43) under the identical experiment, and `isolated_copper` appeared
   from nothing (0 → 109-113) — so the experiment is sensitive to
   zone-fill-driven connectivity changes in general. `via_dangling` simply
   isn't one of them on this board.

   **Verdict: the 25 `via_dangling` findings on the committed board are
   real defects — vias connected on only one layer, or not connected at
   all — not a zone-fill measurement artifact.** They do not sit inside
   any zone's fill area in a way that `--refill-zones` would resolve. Fixing
   them requires routing/via-placement changes, not a DRC runner flag.
   (This is also consistent with prior-session findings on other board
   snapshots — `docs/evidence/2026-08-15-via-type-emission-fix.md` sec on
   the +6 via_dangling delta explicitly frames newly-honest via_dangling
   findings as "the router's real remaining defects in via placement,"
   never as zone-fill artifacts.)

## 6. Recommendation to the owner

**Do not flip the runner default without a deliberate, fully-costed
re-baseline PR — but do not treat this as a close call either.** The
measured evidence:

- `--refill-zones` is **strictly more correct**: it is the same zone-fill
  engine `kicad-cli pcb drc --refill-zones` and the GUI use
  (`pcbnew.ZONE_FILLER`), and the committed board has 96 zone outlines with
  **zero fill data on disk** — every ratchet measurement to date has been
  blind to all zone copper. This is not a close call on correctness.
- The re-baseline is **not free, but it is now fully known**: it moves
  `creepage` (+189 to +191, the single most safety-relevant category on a
  mains-voltage board), `shorting_items` (+7, real shorts), and introduces
  a wholly new `isolated_copper` warning class (+109 to +113) that has no
  ceiling entry at all today. It *relaxes* `clearance` by 3 and
  `track_dangling` by 1. R27's monotone contract would need a
  `Ceiling-Approval:` PR that raises THREE ceiling values (`error_ceiling`,
  `creepage`, `shorting_items`) and adds one brand-new entry
  (`isolated_copper`), with the measured-live provenance this document
  supplies, before the runner could switch over without breaking CI
  outright. `track_width` and `silk_overlap` remain unmeasured (both
  mechanistically independent of zone fill — sec 3.2) and should be spot-
  checked before the ceiling PR lands, though neither is expected to move.
- The `via_dangling` question this task was also asked to resolve has a
  clean, negative, measured answer: those 25 findings are real routing
  defects, not a runner artifact — so switching `--refill-zones` on will
  **not** make that category disappear. It is worth fixing in the router,
  not in the DRC runner flags.

**Recommended sequencing, in the owner's hands, not authorized by this
task**:
1. If the owner decides to switch the runner default, do it as its own PR
   that ONLY changes `scripts/ci_check_drc.py`'s (or
   `_drc_api.run_drc`'s) invocation, carries the `Ceiling-Approval:`
   trailer, a fresh 120-sample `creepage` re-measurement (this document's 5
   samples are a scoping measurement, not the R27-required 120 the R27
   contract requires for a nondeterministic category), and a new
   `isolated_copper` ceiling entry from a standing start — never silently
   folded into an unrelated PR. `clearance`'s exhaustive true-count method
   (sec 3.1) should be re-run once more at that time as its own
   confirmation sample, since this document's single exhaustive run is a
   scoping measurement, not a multi-sample provenance record either.
2. Alternatively, the owner may decide the zone-fill blind spot is
   important enough to fix via zone REDESIGN first (the 2026-08-15 routed-
   board classification doc already found real fill-fragmentation defects
   — 167 isolated islands on a routed board, 109-113 on the bare committed
   board measured here) before ratcheting the runner onto real fill data,
   so the new ceiling reflects a board that is meant to look this way,
   not a snapshot of known-fragmenting pours.
