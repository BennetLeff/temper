<!-- provenance: commit=e81196c87b5998555feca78f27c612b11331bee7 dirty=false
     Board measured: pcb/temper.kicad_pcb sha256
     9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd (unchanged
     before and after this work -- verified by direct sha256sum, see Sec 6).
     kicad-cli 10.0.5, --all-track-errors, single-thread KICAD_CONFIG_HOME pin,
     PD3 DRU regenerated from scripts/generate_kicad_dru.py at the measured
     commit (byte-identical to the committed pcb/temper.kicad_dru -- confirmed
     via `git status`/`git diff --stat` showing no change after running the
     generator). ALL candidate moves below were measured against SCRATCH COPIES
     under /tmp, never against the tracked pcb/temper.kicad_pcb. This document
     is analysis and proposal only; pcb/temper.kicad_pcb was NOT modified. -->
---
module: pcb
tags: [placement, creepage, drc, pd3, board-outline, re-examination, analysis-only]
problem_type: placement-fix
---

# 2026-08-17: Re-examining the 12 "placement-infeasible" PD3 creepage violations (§9.2)

**Date:** 2026-08-17. **Authority:** analysis and proposal only — `pcb/temper.kicad_pcb`
was NOT modified (owner has not granted board-write authorization for this task). Every
candidate below was built and DRC-verified in throwaway scratch copies under
`/tmp/claude-1000/.../scratchpad/drc_scratch*`, outside the repo tree, and the tracked
board's sha256 (`9c1f4a37…`) is confirmed unchanged before and after (Sec 6).

**Headline result: 5 of the 7 flagged component-pairs (9 of 14 individual DRC creepage
violations) have a verified, zero-regression, sub-2mm placement nudge. 2 pairs (5
violations: C22×R26, C6×U1) remain genuinely infeasible as a placement nudge** — matching,
and with harder data reinforcing, the finding in
`docs/evidence/2026-08-16-board-enlargement-left-column-redesign.md` (PR #1279).

**Addendum (same day):** the first version of this document reported the combined
verification's `clearance` category as "499→499, +0, no category increased" — a capped
raw-JSON reading that cannot distinguish "flat" from "substantially worse." Sec 2.2.1 now
measures the true, uncapped count directly (1117→1114, a decrease). The "zero-regression"
claim above was correct, but was not yet earned when first written; it is now.

---

## 0. Correction to the "12" figure, and the two named worst cases

`docs/HANDOFF-2026-08-17.md` §9.2 and §11 both say "12 placement-infeasible creepage
violations." Live, direct re-measurement (Sec 1) finds **14** individual DRC `creepage`
violations across the same 7 component-pairs PR #1279 flagged as the residue. The
PR #1279 evidence doc's own per-violation table (`2026-08-16-board-enlargement-left-column-
redesign.md` §4) already itemizes them as 3+4+2+2+1+1+1 = **14**; its prose summary line
("12 of agent 94's 38 … remain") appears to be an uncorrected arithmetic slip carried
forward into the newer handoff without re-verification — exactly the "stale ground truth"
failure mode `docs/HANDOFF-2026-08-17.md` §3 mechanism 5 warns about. This document uses
the directly re-measured, live-DRC-confirmed number (14) throughout, and flags the
discrepancy here rather than silently repeating it.

The two worst cases named in the task brief are confirmed exactly:

- **C22×R26**: 3.57–4.16mm actual (measured 3.5711 / 3.6317 / 4.1625mm across 3 pad
  pairs), 12.6mm PD3 required. Matches "3.6–4.2mm" as given.
- **C6×U1**: 4.76–7.10mm actual (measured 4.7560 / 7.0997mm across 2 pad pairs), 12.6mm
  PD3 required. Matches "4.8–7.1mm" as given.

Both remain **genuinely infeasible** after this re-examination (Sec 4).

---

## 1. The 14 violations, current state (live-measured)

All 7 pairs require **12.6mm** (PD3 reinforced, HV/HighVoltageIsolated/HighVoltageSignal
↔ LV — `packages/temper-placer/configs/pair_creepage.generated.yaml`). None of the 14
involve the 10.0mm tank figure (`HighVoltageTank` class) — no tank-domain component is
among the 7 pairs.

| # | pair | violations | actual (mm) | shortfall (mm) | geometric blocker |
|---|---|---:|---|---|---|
| 1 | C22×R26 | 3 | 3.57 – 4.16 | −8.4 to −9.0 | C22's east escape is filled by C4's 35mm snap-in body (C4 centre (86.46,188.34), r=17.5mm, edge reaches x=68.96 — already at C22's own x=68.49); R26 boxed by R23/C6/C1/U16/R6 |
| 2 | C22×U16 | 4 | 10.72 – 12.45 | −0.15 to −1.9 | **FIXED** (Sec 2) — C22 dy=+2.0mm clears all 4 |
| 3 | C6×U1 | 2 | 4.76 – 7.10 | −5.5 to −7.8 | C6 has zero collision/violation-free displacement anywhere on the board (± 30mm swept); U1's only escapes (36mm+) leave the #1248 K1/RT1/U1/U2 ampacity pour-hull cluster |
| 4 | C1×U9 | 2 | 11.98 – 12.40 | −0.2 to −0.6 | **FIXED** (Sec 2) — C1 dx=+1.0 dy=+0.5mm clears both |
| 5 | C1×C6 | 1 | 12.51 | −0.09 | **FIXED** (Sec 2) — C6 dx=+1.0 dy=−0.25mm (combined with #4's C1 move) clears it |
| 6 | C20×R51 | 1 | 11.70 | −0.9 | **FIXED** (Sec 2) — R51 dx=+1.5mm clears it (moving C20 instead creates other-category regressions — Sec 3) |
| 7 | K3×U27 | 1 | 11.94 | −0.66 | **FIXED** (Sec 2) — U27 dx=−1.0mm clears it, plus improves 3 unrelated categories |

Distances and required figures are copper-to-copper pad-edge distances (never package/
courtyard bounding boxes), taken directly from live `kicad-cli pcb drc` JSON output —
see Sec 5 for the measurement method and its cross-check against an independent
geometric re-implementation.

---

## 2. Proposed moves — 5 of 7 pairs, verified zero-regression

All five moves were combined into a single scratch board and DRC-verified together
(Sec 6). Coordinates are absolute board positions, in mm, `(x, y, rotation)`:

| ref | from | to | Δ | fixes |
|---|---|---|---|---|
| **C22** | (68.490, 189.100, 270°) | (68.490, 191.100, 270°) | dy=+2.00 | C22×U16 (4 violations, all cleared) |
| **C1** | (51.490, 214.220, 90°) | (52.490, 214.720, 90°) | dx=+1.00, dy=+0.50 | C1×U9 (2 violations, both cleared) |
| **C6** | (65.990, 201.760, 270°) | (66.990, 201.510, 270°) | dx=+1.00, dy=−0.25 | C1×C6 (1 violation, cleared — note this move is tuned to compensate for C1's move above; see Sec 2.1) |
| **R51** | (33.230, 97.290, 90°) | (34.730, 97.290, 90°) | dx=+1.50 | C20×R51 (1 violation, cleared) |
| **U27** | (34.100, 47.960, 90°) | (33.100, 47.960, 90°) | dx=−1.00 | K3×U27 (1 violation, cleared) |

No rotation changes, no footprint substitutions, no outline changes. Every move is
≤2.06mm in magnitude — well inside the "nudge" regime PR #1279 already used for its
26-pair left-column fix. None of the 5 refs (C22, C1, C6, R51, U27) is a designator PR
#1279 already moved.

### 2.1 Why C1 and C6 must move together

C1's move (which clears C1×U9) independently makes C1×C6 *worse* (12.51mm → 11.62mm,
still just a violation, not a new one — C1×C6 was already in the baseline violation set
touching C1). C6's move alone (dx=+0.25mm) clears C1×C6 at C1's *original* position but is
insufficient once C1 has also moved. Re-solving for C6's minimum displacement **with C1
already at its new position** gives dx=+1.00, dy=−0.25 (a 1.25mm move instead of 0.25mm) —
this is the version reported in the table above and is the one live-DRC-verified in the
combined board (Sec 6). C22, R51, and U27 are spatially isolated from this pair (>15mm away
in every case) and do not interact with it or each other.

### 2.2 Combined verification result (live kicad-cli DRC, all 5 moves applied)

| category | baseline (committed board) | all-5-moves | delta |
|---|---:|---:|---:|
| creepage | 271 (raw JSON, uncapped — empirically this category never saturates on this board) | 261 | **−10** |
| clearance | raw JSON capped at **499** both sides — see Sec 2.2.1 for the true, uncapped count | raw JSON capped at **499** | raw JSON: +0 (**uninformative — see below**) |
| hole_clearance | 90 | 86 | **−4** (bonus — U27 relief) |
| shorting_items | 183 | 180 | **−3** (bonus — U27 relief) |
| solder_mask_bridge | 133 | 130 | **−3** (bonus — U27 relief) |
| courtyards_overlap | 1 | 1 | +0 |
| every other category | — | — | +0 |
| **TOTAL (raw JSON)** | **1870** | **1850** | **−20 (raw JSON only — see Sec 2.2.1 for the corrected total)** |

Reproduced twice (identical 1850/261/499 both times — see Sec 6). Every category above
except `clearance` is a real, uncapped count on this board (`clearance`/`unconnected_items`
cap at kicad-cli's `EXTENDED_ERROR_LIMIT` 499; everything else caps at `ERROR_LIMIT` 199;
`creepage` is empirically uncapped — cap table per `packages/temper-drc-rs/src/drc_count.rs`,
cross-checked against `docs/evidence/2026-08-17-refill-zones-drc-runner-gap-measurement.md`).
`hole_clearance` (90/86), `shorting_items` (183/180), and `solder_mask_bridge` (133/130) are
all well under their 199 cap on both sides, so their deltas are real. The 3 "bonus"
reductions come from relieving U27's own local congestion when it moves 1mm away from K3 —
not required by this task, but confirm the move is a net board improvement outside creepage.

**`clearance` at 499=499 is NOT evidence of "no change."** 499 is `EXTENDED_ERROR_LIMIT`, a
saturation cap — the entire reason `DrcCount::honest_count()` returns a `Result` rather than
a bare integer is that a capped value cannot be read as a real count. Both sides landing on
the identical cap is consistent with clearance staying flat, and equally consistent with it
getting substantially worse — the raw JSON cannot tell those apart. This is resolved directly
in Sec 2.2.1, not asserted from the capped reading.

#### 2.2.1 True, uncapped `clearance` count — resolved: −3, not an increase

Measured with `scripts/measure_uncapped_drc.py`'s own exhaustive DRU-band-isolation-and-
bisection method (unmodified — the same instrument
`docs/evidence/2026-08-17-refill-zones-drc-runner-gap-measurement.md` used to establish the
1117 baseline this document's Sec 5.2 already cited but had not yet re-run against the
moved board). Every DRU rule's band is isolated by a synthetic 2-rule DRU exploiting KiCad's
last-matching-rule-wins, with automatic net-name bisection on any band that itself saturates;
a band landing exactly on `ERROR_LIMIT`/`EXTENDED_ERROR_LIMIT` is flagged
`SATURATION SUSPECTED` rather than trusted. Invoked via
`UNCAPPED_DRC_REPO_ROOT=<scratch fakeroot>/pcb/... scripts/measure_uncapped_drc.py
dru-category clearance --dru-file pcb/temper.kicad_dru --scratch-dir <scratch>` — the script
itself was not modified; `UNCAPPED_DRC_REPO_ROOT` (a variable the script already reads,
default `REPO_ROOT`) was pointed at a throwaway directory under `/tmp` containing a copy of
`pcb/temper.kicad_pro`/`fp-lib-table`/`libs/` plus either the committed
`pcb/temper.kicad_pcb` byte-for-byte (baseline) or the all-5-moves scratch board from Sec 2
(combo) as `pcb/temper.kicad_pcb` — `pcb/temper.kicad_pcb` in this worktree was never opened
for writing by this measurement.

| board | true clearance | zero `SATURATION SUSPECTED` bands? | reproduced |
|---|---:|---|---|
| baseline (committed, sha256 `9c1f4a37…`) | **1117** | yes | matches the sibling doc's 1117 exactly |
| all-5-moves | **1114** | yes | 2/2 runs identical (1114, 1114) |

**Delta: −3, a decrease.** Per-rule band breakdown, baseline → all-5-moves (only rules that
moved are non-trivial; all 12 other rules are 0 on both sides or unchanged):
`AC Mains to LV` 24→23 (−1), `HighVoltageIsolated same side` 8→9 (+1), `Default routing`
260→258 (−2), `netclass-implicit fallback` 40→39 (−1); unchanged: `AC Mains to HV` 1,
`HV to LV` 207, `HighVoltageTank to LV` 5, `HighVoltageSignal to LV` 463,
`HighVoltageIsolated to LV` 109, all four `GateDrive*` rules 0, `HV internal same footprint`
0, `Power internal same footprint` 0, `Ground clearance` 0, `Same footprint pads` 0,
`Fine pitch IC pads` 0, `USB differential` 0. Sum (all-5-moves band values):
23+1+9+109+0+207+5+463+0+0+0+0+0+258+0+0+0+0+39 = 1114.

**Honest conclusion: the true clearance count does not increase from these 5 moves — it
decreases by 3, alongside the 9 creepage violations cleared.** This is plausible for the same
reason the refill-zones doc gives for its own clearance decrease: these are small (≤2.06mm)
translations of already-isolated SMD/THT pads, and a move that increases separation from one
neighbour by design (to clear a 12.6mm creepage bar) does not preferentially decrease
separation from a *different* neighbour at the much narrower 0.2–2.0mm clearance floor — if
anything the opposite is slightly more likely, and the exhaustive measurement confirms that
here. **No category in the combined verification increases** once `clearance` is read
correctly (uncapped) instead of at its saturated raw-JSON value — revising the Sec 2.2
"No category increased" claim, which was asserted from the capped reading and should not
have been.

Creepage went from 14 violations touching the 7 named pairs down to 5 (all in the two
infeasible pairs), i.e. **9 individual violations cleared** by these 5 moves — the
apparent "−10" delta above is 9 target-pair violations cleared plus 1 unrelated pair
(R51×R15, not one of the 7, already violating in the baseline at 12.06mm) tightening from
one already-violating state to another (worse, 11.31mm, but not new — already counted).

---

## 3. What did NOT work — rejected candidates, and why the search tool needed live-DRC gating

The geometric screening tool built for this task (Sec 5.1) checks creepage, clearance
(pad-pad), courtyard collision, and board-outline containment — but **not** track/via
geometry or KiCad's shorting_items/solder_mask_bridge checks directly. Two findings from
this session show why every accepted candidate above was additionally required to pass
live `kicad-cli` DRC before being reported as a fix, not just the geometric screen:

- **C20 alone** (dx=−1.5mm) passes the geometric screen (0 added creepage/clearance,
  0 courtyard collisions) but live DRC shows shorting_items +5 and solder_mask_bridge +5 —
  a real regression from a track-geometry interaction the pad-only geometric model cannot
  see. **Rejected.** This is why R51 (not C20) is the proposed fix for pair #6 — moving
  the *other* member of the pair avoids the regression entirely and was not tried in the
  original #1279 analysis (which only attempted moving C20).
- Two capped/near-threshold categories (`clearance`, capped at kicad-cli's own
  `EXTENDED_ERROR_LIMIT=499`) and marginal creepage pairs elsewhere on the board (e.g.
  J2×PS1 at 12.31mm, a pair neither this task nor any of the 5 moves touches) show
  **run-to-run measurement noise of ±3 total violations** on the byte-identical,
  unmodified, committed board (4 repeat DRC runs: 1870, 1870, 1873, 1870 total). This
  matches the project's own documented DRC non-determinism
  (`docs/evidence/2026-08-04-drc-measurement-determinism.md`). Every accepted candidate's
  delta in this document exceeds that noise band by a wide margin (creepage deltas of
  −1 to −10, deterministic across repeats) except one +1 clearance blip (R51's move,
  499→500 on a single run, raw JSON) that reproduced as 499 on a second run — inside the
  observed noise band. **This blip is a symptom, not the actual finding**: the raw
  `clearance` reading is capped at 499 on every run, on both boards, regardless of noise —
  a saturated value carries no information about the true count whether or not it also
  jitters near the cap. The two effects are separate and both point the same way (raw
  `clearance` cannot be trusted), which is exactly why Sec 2.2.1 measures the true,
  uncapped count directly instead of reasoning from the raw JSON reading at all.

---

## 4. The 2 pairs that remain genuinely infeasible

### C22×R26 (3 violations, 3.57–4.16mm vs 12.6mm)

- **R26 alone**: the nearest zero-violation displacement is **27mm+** away
  (e.g. dx=−1, dy=−26 → (62.97, 164.18)), landing R26 in a completely different
  neighbourhood near R4/R6. Swept ±30mm on a 1mm grid; nothing closer works.
- **C22 alone**: the nearest zero-violation displacement is **18mm+** away
  (e.g. dx=+7, dy=+11 → (75.49, 200.10)). C4's 35mm-diameter snap-in body
  (centre (86.46, 188.34), r=17.5mm) fills the direct escape route east of C22 — its edge
  already reaches x=68.96, past C22's own x=68.49 — forcing any viable C22 relocation
  around C4 entirely, into R4's neighbourhood.
- **Group move**: C22 and R26 moving together as a rigid pair cannot help — a rigid
  translation preserves the *internal* distance between the two, which is exactly what's
  short. Only relative motion between them helps, and that's what the two searches above
  already tested.
- **Why this isn't "just" an 18–27mm nudge**: C22 is a 0603 bypass capacitor on
  `hb.gate_hs.driver-p1-1`/`-p2` — the half-bridge gate-driver switching node. Relocating
  it 18mm+ from the driver IC it decouples is not a placement question but a functional
  one (loop inductance/EMI at the switching node); R26's 27mm move is the same problem for
  the `I_SENSE`/`+3V3` divider it belongs to. **Confirmed genuinely infeasible as a
  placement nudge** — the historical finding (C4's body blocks the escape) is upheld and
  quantified.

### C6×U1 (2 violations, 4.76–7.10mm vs 12.6mm)

- **C6 alone**: **zero** zero-violation displacements found anywhere on the board, swept
  ±30mm on a 1mm grid (2401 candidates tried). C6 is fully boxed.
- **U1 alone**: the nearest zero-violation displacement is **36mm+** away
  (dx=+25, dy=−11 → (85.00, 207.00)) — landing immediately adjacent to/inside C4's
  35mm body's neighbourhood and outside the #1248 K1/RT1/U1/U2 ampacity cluster whose
  26mm pad-span pour-hull geometry is load-bearing (PR #1248, reaffirmed in PR #1279 §6
  "No U1 move — only clean displacement breaks the ampacity cluster").
- **Confirmed genuinely infeasible as a placement nudge**, consistent with and reinforced
  by the PR #1279 finding.
- **Board outline degree of freedom**: does not apply to either pocket. Both C22×R26 and
  C6×U1 are interior (>60mm from every board edge); PR #1279's left-edge enlargement
  precedent only helped because R5/U7/C23 were already edge-adjacent. A cascading
  multi-component re-placement (e.g. relocating C4 itself, or the whole #1248 cluster) was
  considered but not attempted: it exceeds "placement nudge" scope, risks re-opening
  thermal/mounting/EMI constraints on C4 and the ampacity cluster that are outside this
  task's data, and is exactly the "genuine board redesign" category both this task and
  PR #1279 already correctly assign these two pairs to.

---

## 5. Verification method

### 5.1 Geometric screen (fast, used to shortlist candidates)

A standalone tool (`/tmp/.../scratchpad/search.py`, not committed — a throwaway harness
per this repo's own convention for this kind of one-off measurement, `scripts/
measure_cross_domain_creepage.py`'s docstring) reuses this repo's own canonical,
production primitives rather than re-deriving geometry:

- `temper_placer.geometry.kicad_transform.rotate_local_to_world` — the sanctioned
  **R(−θ)** local-offset→world-position convention, confirmed against real `kicad-cli`
  output (see that module's own docstring); pad angle is taken as absolute, per the same
  convention `scripts/check_pad_orientation.py` uses.
- `temper_placer.core.pad_geometry.pad_pair_distance` — exact shape-aware,
  rotation-aware copper-to-copper pad distance (Rust-backed, `temper-geometry`).
- `temper_placer.router_v6.pair_creepage.load_pair_creepage_table` — the generated PD3
  creepage-by-netclass-pair table, keyed off `pcb/temper.kicad_pro`'s
  `net_settings.netclass_assignments` (the same source KiCad's own DRC uses).
- `temper_placer.router_v6.pair_clearance.load_pair_clearance_table` — same, for the
  universal clearance floor.
- `temper_placer.core.courtyard.Courtyard`/`check_overlap` — rotation-aware F.CrtYd
  polygon collision.

For a candidate move, the tool checks: (1) zero new creepage violations touching the
moved component(s) against every other pad on the board (not just the target partner);
(2) zero new clearance violations, same denominator; (3) zero courtyard collisions against
every other footprint; (4) all moved pads remain ≥0.3mm inside the board outline. A bug
was found and fixed during this work: the outline parser's first version used a
non-greedy regex that silently dropped the polygon's last vertex, halving the reported
board area (19188mm² instead of the correct 38376mm²) and producing false "off-board"
flags on components that were nowhere near an edge (caught by cross-checking
`outline.area` against `width×height` by hand — see `search.py`'s `get_outline_polygon`
docstring for the fix).

### 5.2 Live kicad-cli DRC (authoritative, gates every accepted candidate)

Every candidate reported as "fixed" above was additionally built into a scratch copy
(`shutil.copy`, never `pcb/temper.kicad_pcb` itself — same discipline as
`scripts/measure_uncapped_drc.py`'s `make_scratch_board`) and measured with the repo's
own `run_drc` protocol: `kicad-cli pcb drc --all-track-errors --format json`, a
single-thread `KICAD_CONFIG_HOME` pin, and the PD3 DRU regenerated at this commit
(byte-identical to committed). Full category-by-category counts were diffed against 4
repeat baseline runs of the unmodified board to establish the noise floor (±3 total,
concentrated in the capped `clearance` category and a small number of marginal
already-near-threshold pairs elsewhere on the board — none touching any of the 5 moved
components) before accepting any candidate's delta as real.

**A second, independent discrepancy was found and resolved in favour of live DRC**: the
geometric model (Sec 5.1) and live `kicad-cli` disagree by ~0.85–1.6mm specifically for
THT `rect`-shaped pads carrying `remove_unused_layers` (e.g. U1's TO-220 pad 1, J2/PS1's
connector pads) — the geometric model's exact rectangle-corner distance formula reports a
*larger* gap than kicad-cli measures. This was traced far enough to rule out a rotation-
convention bug (every other pair — including 6 of the 7 target pairs, all involving 0603/
SOT-23/1206 SMD pads or plain circular THT pads — matches kicad-cli to within 0.001mm
using the identical formula) but not far enough to identify kicad-cli's exact internal
treatment of `remove_unused_layers` THT rect pads. **Live kicad-cli's number is used
throughout this document** (it is the actual DRC gate the project enforces and the number
that reproduces the historical PR #1279 figures exactly — 4.76–7.10mm for C6×U1, matching
"4.8–7.1mm" verbatim); the geometric model was used only for candidate screening, never as
the final figure. This discrepancy does not affect any of the 5 proposed moves (none
involves a THT rect pad with `remove_unused_layers` as the geometrically-modeled member)
but is worth a follow-up note for anyone extending this geometric tool to THT-heavy areas
of the board.

### 5.3 Uncapped `clearance` (authoritative for the one category that saturates on both sides)

Live `kicad-cli` JSON (Sec 5.2) is authoritative for every category except `clearance`,
which is capped at `EXTENDED_ERROR_LIMIT=499` on both the baseline and every candidate
board measured in this document — a capped value read as a count is exactly the failure
mode `DrcCount::honest_count()` (`packages/temper-drc-rs/src/drc_count.rs`) was built to
make unrepresentable. For `clearance` specifically, Sec 2.2.1 uses
`scripts/measure_uncapped_drc.py dru-category clearance` (unmodified script; a scratch
`UNCAPPED_DRC_REPO_ROOT` fakeroot substitutes the candidate board) — the same exhaustive
DRU-band-isolation-and-bisection instrument
`docs/evidence/2026-08-17-refill-zones-drc-runner-gap-measurement.md` used to establish
the 1117 baseline this document originally cited without re-running against the moved
board. No other category in this document's tables reads at or near its cap (`hole_clearance`
90/86, `shorting_items` 183/180, `solder_mask_bridge` 133/130 are all ≤86% of their 199
cap; `creepage` is empirically uncapped), so `clearance` is the only category that needed
this treatment.

---

## 6. Board integrity check

```
before: 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd  pcb/temper.kicad_pcb
after:  9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd  pcb/temper.kicad_pcb
```

Identical. `git status`/`git diff --stat` confirm no working-tree changes to
`pcb/temper.kicad_pcb` (or any file) at any point during this work. All DRC runs in
Sec 2–4 were against scratch copies under `/tmp/claude-1000/.../scratchpad/drc_scratch*`,
built via `shutil.copy` of the committed board plus a single-line `(at x y angle)`
text substitution, never a write to the tracked file.

---

## 7. Honest count

- **14** individual PD3 creepage violations, live-measured, across the 7 flagged pairs
  (not 12 — Sec 0).
- **9 violations (5 of 7 pairs) have a verified, zero-regression, ≤2.06mm placement nudge**:
  C22×U16, C1×U9, C1×C6, C20×R51, K3×U27. "Zero-regression" here means what it should:
  every one of the 19 DRC categories this document checked is flat or improved, *including*
  `clearance`, whose true uncapped count (Sec 2.2.1) was measured directly rather than read
  off a saturated raw-JSON value — it decreases by 3 (1117→1114), it does not increase. This
  is a real finding, not an assumption: a set of ≤2.06mm component moves plausibly *could*
  have traded creepage clearance for pad-pad clearance violations elsewhere, and that
  possibility was closed by measurement, not by omission.
- **5 violations (2 of 7 pairs) remain genuinely infeasible as a placement nudge**:
  C22×R26 (3), C6×U1 (2). Both were re-searched over a much wider envelope (±30mm) than
  the original 0.25mm-grid local search that first flagged them, using a courtyard- AND
  creepage-aware checker per this task's brief, and both are confirmed structurally boxed
  by the same fixed power components PR #1279 already identified (C4's 35mm snap-in body;
  the #1248 ampacity cluster's load-bearing pour-hull geometry) — not by a gap in the
  original local search. The board-outline degree of freedom that unlocked PR #1279's
  24-pair fix does not apply here: neither pocket is edge-adjacent.
- These 5 remaining violations should stay classified as "needs physical board redesign"
  in `docs/HANDOFF-2026-08-17.md` §9.2 — this re-examination does not change that
  classification, only the count it applies to (5, not 12) once the 9 nudge-fixable
  violations are separately landed.

## Files

- This document.
- No other files changed. `pcb/temper.kicad_pcb` was not modified (Sec 6).
