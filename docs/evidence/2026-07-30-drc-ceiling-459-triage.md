<!-- provenance: commit=3bddb8d065b4c95c82797420136bd370676a351b dirty=false -->

# Triaging `main`'s red DRC ratchet: all 7 regressed categories are a correct-board consequence of #459, none are new measurement noise

Base: `origin/main` at `3bddb8d065b4c95c82797420136bd370676a351b` ("Merge pull
request #423 from BennetLeff/docs/pour-derivation-rule"), confirmed clean
(`git status` empty) before any measurement below. `kicad-cli 10.0.4`,
matching `drc_ceiling.json`'s recorded `tool_versions.kicad-cli` exactly (no
version-mismatch caveat applies to any number in this doc).

## Summary (read this first)

`scripts/ci_check_drc.py --backend kicad-cli` fails on `main` today:
aggregate `867 > 845` ceiling, 5 error categories and 2 warning categories
over their per-type ceilings. All 7 trace to a single commit,
`8bf18b41` ("fix(pcb): resync board designators/footprints against
elec/src and pcb/libs (#459)"), whose own evidence doc
(`docs/evidence/2026-07-30-board-resync-against-source.md`) claims the
regression is a deliberate, correct-board consequence of fixing 6 stale
embedded footprints, and says re-measuring `drc_ceiling.json` was
"explicitly ... a separate deliverable" left undone on purpose. That claim
is verified here independently, not accepted on faith, using a stricter
method than the PR's own (identity-normalized across the mid-PR designator
renumbering — see Methodology) and using the actual gate script CI invokes.

**Verdict: all 7 categories are (2) correct-board consequences. Zero are
real regressions. Zero are new measurement noise** (18 total runs; only
`clearance` scattered, exactly reproducing the ceiling's own documented
499-501 range — no new nondeterministic category found). Nothing is
fixed here: there is no code or `pcb/temper.kicad_pro` defect to fix, and
the physical geometry that drives these counts lives in
`pcb/temper.kicad_pcb`, which this task is barred from touching (and
which a human, not an agent, should be adjusting for a mains-connected
HV board). Recommended ceiling values are in
[§5](#5-recommended-ceiling-values-not-applied-here).

## 1. Reproducing the failure on the stated base

```
$ PYTHONPATH=.../packages/temper-placer/src .venv/bin/python scripts/ci_check_drc.py --backend kicad-cli
FAIL: temper: DRC FAIL
  aggregate errors 867 exceeds ceiling 845 (+22)
  per-type errors (source: kicad-cli): 5 categories over ceiling (0 new, 5 regressed):
    [   ] copper_edge_clearance 15 > 13 (+2)
    [   ] courtyards_overlap 16 > 11 (+5)
    [   ] hole_clearance 102 > 101 (+1)
    [   ] shorting_items 118 > 113 (+5)
    [   ] solder_mask_bridge 69 > 64 (+5)
  per-type warnings (source: kicad-cli): 2 categories over ceiling (0 new, 2 regressed):
    [   ] lib_footprint_issues 9 > 8 (+1)
    [   ] pth_inside_courtyard 9 > 8 (+1)
```

Exact match to the task brief. `git log -- pcb/temper.kicad_pcb` on `main`
identifies the last commit to touch the board as `8bf18b41`
(`fix(pcb): resync board designators/footprints against elec/src and
pcb/libs (#459)`), parent `27ecfee4`.

## 2. What #459 and its own evidence doc claim

`8bf18b41`'s message and `docs/evidence/2026-07-30-board-resync-against-source.md`
(§8, "`golden-check` / `temper_production_baseline.yaml` ratchet") both
claim: 6 embedded footprints (U3, C6, U7, plus C25/C26 discovered during
verification) were stale copies that never received corrections already
landed in `elec/src`/`pcb/libs`; propagating them, at unchanged anchor
positions, increases 5 KiCad DRC categories because "a bigger,
datasheet-correct part sitting at an unchanged anchor point necessarily
has less clearance to unchanged neighbours than the smaller, wrong part it
replaced." The doc explicitly declines to re-measure `drc_ceiling.json`
in the same PR, citing its own `Ceiling-Approval:` gate
(`scripts/check_drc_ceiling_approval.py`) as requiring a separate,
human-approved deliverable. This doc is that deliverable's evidence.

## 3. Methodology

**Old/new board pair.** `git worktree add --detach` (never `git stash`,
per constraint) at `27ecfee4` (parent of `8bf18b41`) gives a byte-identical
pre-#459 board with its own `.kicad_pro`/`fp-lib-table`/`libs/` — required
because a bare board file without its project sibling silently falls back
to kicad-cli's built-in rule severities instead of this project's
`rule_severities` overrides (documented pitfall in the cited doc's own
§8, "Verifying the composition"). Both boards' `.kicad_dru` were
regenerated from the one SSOT script (`scripts/generate_kicad_dru.py`)
and hash-compared: **identical**, `9e31c3c5...` on both, ruling out the
stale-DRU measurement artifact the PR's own doc separately warns about.

**Old board reproduces the pre-PR baseline.** `run_drc()` (the same
function `DrcRatchet` and `scripts/ci_check_drc.py` call) on the old board
gives **842-843 errors / 683 warnings**, matching the PR doc's own
independently-recorded "unmodified, pre-this-PR board" figure of 842
almost exactly (843 here reflects the same `clearance` ±1 scatter the
ceiling already documents).

**Identity-normalized diffing (the correction this doc adds).** A naive
diff by bare reference designator is wrong here: `8bf18b41`'s own message
says 13 C-designators shifted by one slot (`tank.c_tank3` was inserted
ahead of them). Verified directly — `C33` on the old board is
`rtd_pan.c_rail_monitor`; `C33` on the new board is `rtd_pan.c_window_and`,
a different physical part entirely. A first pass diffing by raw designator
found spurious "regressions" attributed to `C33` (`shorting_items` +2,
`solder_mask_bridge` +2) and `C27` (`lib_footprint_issues` +1) — both
artifacts of this renumbering, not real component changes. Building a
designator→sheetpath map from each board's own `(property "Reference"
...)`/`(property "Sheetpath" ...)` pairs and normalizing every DRC
violation's component list through it before diffing removes the
artifact entirely (§4 below shows the corrected result).

**Physical corroboration.** For every touched footprint, the embedded
`.kicad_pcb` geometry was diffed directly (not just trusted from the PR
doc) and cross-checked against `elec/src`'s current source of truth, and
each component's `(at x y rot)` was confirmed byte-identical old vs. new
(0 of the 6 anchor points moved) — see §4 per category.

**Noise sampling.** `run_drc()` invoked 18 times (3 + 15) on the
as-committed board via `temper_placer.validation._drc_api.run_drc`
(`--all-track-errors`, same as the ceiling's own measurement convention).

## 4. Per-category verdict

All 5 error categories and both warning categories: **(2) correct-board
consequence.** Evidence per category:

### `copper_edge_clearance` 13 → 15 (+2)

100% driven by `C1` (`power_in.c_x2`). Old footprint
`Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm` (5mm-pitch disc stub) →
new `Capacitor_THT:C_Rect_L18.0mm_W7.0mm_P15.00mm_FKS3_FKP3` (18×7mm MKP
box, 15mm pad pitch) — matches `elec/src/modules.ato:741`'s
`c_x2.footprint` exactly (MPN `B32922C3224M289`, X2-rated 310V safety
cap). Position/rotation unchanged (`155.82, 252.48, 180` both boards).
Two new instances, both on `C1`:
`Board edge clearance violation (... edge clearance 0.5000 mm; actual
0.3200 mm)` — the real part's larger body now sits closer to the board
edge than the wrong, undersized disc footprint did.

### `courtyards_overlap` 11 → 16 (+5)

Identity-normalized diff: all 5 new pairs involve only `C1`
(`power_in.c_x2`), `C25`/`C26` (`tank.c_tank1`/`tank.c_tank2`) —
`(C25,K3)`, `(C1,R7)`, `(C26,U21)`, `(C25,C5)`, `(C25,C26)`. C25/C26's
footprint changed from the stale `Capacitor_THT:C_Rect_L41.5mm_W20.0mm_
P37.50mm_MKS4` (WIMA rect, pre-#413 part) to
`temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal` — matching
`elec/src/modules.ato:518`'s `c_tank1.footprint` for the CDE
942C16P1K-F axial part that replaced the WIMA FKP1 (elec/src comment:
"PR #410 re-sourced c_tank1/c_tank2 to CDE 942C16P1K-F"). All 3 anchor
positions (C1, C25, C26) unchanged.

### `hole_clearance` 101 → 102 (+1 on the ceiling; +8 against the true pre-#459 board)

**The ceiling comparison here is misleading and worth flagging on its
own.** Old-board live measurement gives `hole_clearance = 94`, not the
ceiling's recorded 101 — 21 commits landed between the ceiling's
`measured_at_commit` (`66ae51fc`) and #459's parent (`27ecfee4`), and
none of them re-measured `drc_ceiling.json` (that gate has been stale
against this category independently of #459: it already shows
"unratcheted slack" — see below). Identity-normalized diff against the
correct pre-#459 baseline shows the true delta is **+8, 100% on `U3`**
(`power_in.zcd_opto`), e.g.: `Hole clearance violation (rule 'Via hole
clearance' clearance 0.2500 mm; actual 0.0000 mm)` ×4,
`actual 0.0050 mm` ×3, `actual 0.0258 mm` ×1. `U3`'s footprint changed
`Package_DIP:DIP-6_W7.62mm` → `DIP-6_W10.16mm`
(confirmed in the committed board: line 7884, `layer "F.Cu"`), matching
`elec/src/components.ato:550`'s `H11L1.footprint` exactly. The source
comment (components.ato:533-539) gives the reason: on the 7.62mm
package the LED anode (pin 1, HV) and ZCD output (pin 4, SELV) have only
6.020mm copper-to-copper separation against the 8.0mm
`MIN_BARRIER_WIDTH_MM` isolation gate in
`scripts/check_isolation_keepout.py`; the 10.16mm package gives 8.560mm.
**This footprint change is a safety-isolation fix, not a placement
change** — position unchanged (`118.82, 107.02, 0` both boards). The
reason the *ceiling* only shows +1 is that hole_clearance separately
improved by 7 (94 vs. the stale 101) from unrelated commits in the 21
between `66ae51fc` and `27ecfee4` (nothing in this task's scope), which
happened to mostly offset #459's real +8. Both facts are recorded in
§5's recommended value.

### `shorting_items` 113 → 118 (+5)

Identity-normalized: `U3` +4, `(C1, R7)` +1. `U3` examples:
`Items shorting two nets (nets ZCD_ISO and safety.coil_thermal-line)`,
`(nets safety.coil_thermal-line and +3V3)`, `(nets safety.coil_thermal-line
and ZCD_ISO)`, `(nets gnd and safety.coil_thermal-line)` — the wider DIP-6
body's outer pins are now closer to the neighboring `safety.coil_thermal`
copper than the narrower body's were. `(C1, R7)`: `Items shorting two nets
(nets ac_n and zcd)` — C1's larger MKP body now overlaps R7's copper.
Zero involvement from `U7` despite the PR doc's own attribution table
crediting it with +1 here — see §6.

### `solder_mask_bridge` 64 → 69 (+5)

Identity-normalized: `U3` +4 (`Front solder mask aperture bridges items
with different nets` ×4, same wider-body cause as above), `(C1, R7)` +1.
Zero involvement from `U7` (see §6).

### `lib_footprint_issues` (warning) 8 → 9 (+1)

Net effect of gains and losses, both fully attributable: `C25`, `C26`,
and the newly-staged `tank.c_tank3` (`C27`) each contribute +1 (their
new footprints are project-local (`temper:` prefix) rather than a
standard KiCad library nickname, which kicad-cli flags); `C1` and `C6`
each contribute -1 (their corrected footprints resolve cleanly). Net
+3-2 = +1.

### `pth_inside_courtyard` (warning) 8 → 9 (+1)

`(C1, R7)` +1 — same larger-C1-body cause as `courtyards_overlap` and
`solder_mask_bridge` above; a plated through-hole now falls inside a
neighboring courtyard it previously cleared.

## 5. Noise sampling: no new nondeterministic category

18 runs of `run_drc()` (3 then 15, `--all-track-errors`, as-committed
board, no changes in between): **all 5 regressed error categories and
both regressed warning categories are exactly constant across all 18
runs, zero scatter.** Only `clearance` varies, observed 499 (11/18) or
500 (7/18) — squarely inside the ceiling's documented 499-501 historical
range, confirming (not merely repeating) `nondeterministic_error_types`'
existing claim that `clearance` is the *only* nondeterministic category.
**No new nondeterministic category was found** — an explicit negative
finding, not an assumption.

```
run 1..3:   867/867/867 errors (clearance 499,499,499)
run 4..15:  867×6, 868×4 (clearance 499/500 1:1 with the +1)
hole_clearance: [102]*15   shorting_items: [118]*15   solder_mask_bridge: [69]*15
copper_edge_clearance: [15]*15   courtyards_overlap: [16]*15
lib_footprint_issues: [9]*15   pth_inside_courtyard: [9]*15
```

## 6. Where this doc's re-derivation differs from #459's own evidence

`docs/evidence/2026-07-30-board-resync-against-source.md`'s own
per-component table (its §8) attributes `hole_clearance: U3:8, U7:2`,
`shorting_items: U3:4, U7:1, C1:1`, `solder_mask_bridge: U3:4, U7:1,
C1:1`. Direct comparison of every DRC violation touching
`hb.gate_hs.driver` (U7) on the old vs. new board (full listing, not
summarized) shows **U7's violation set is unchanged in count** for all
three categories (2/2/1 old, 2/2/1 new — only which specific neighbor
instance is reported shifts slightly, an artifact of U7's pad width
shrinking from 2.05mm to 1.65mm while its pitch widened, not a net
change). U7's own courtyard did widen (±5.93mm → ±5.95mm, confirmed by
diffing the embedded footprint block), but it does not net-drive any of
the 5 regressed categories on this board. This does not change the
verdict (still 100% correct-board consequence, still zero unwatched
components) — it corrects which of #459's 6 touched footprints is
responsible for which category, useful if a future PR needs to
attribute this differently.

## 7. Recommended ceiling values (not applied here)

Per the task's hard constraint, `power_pcb_dataset/drc_ceiling.json` is
**not edited** and no `Ceiling-Approval:` trailer is authored here — that
is the human's call. The values below are what a from-scratch, honest
re-measurement of the current board (matching this repo's own established
convention, e.g. the `2026-07-29-pad-rotation-remeasure` and
`2026-07-29-creepage-admitted` `_march` entries) would set:

| field | current | recommended | why |
|---|---|---|---|
| `error_ceiling` | 845 | **870** | `368` (sum of all 11 deterministic error categories below, 18/18 samples) `+ 502` (`clearance`'s existing ceiling, unchanged — same formula the `2026-07-29-creepage-admitted` entry used: `842 - 499 + 502 = 845`; here `867 - 499 + 502 = 870`) |
| `violations_by_type.copper_edge_clearance` | 13 | **15** | §4, 18/18 samples |
| `violations_by_type.courtyards_overlap` | 11 | **16** | §4, 18/18 samples |
| `violations_by_type.hole_clearance` | 101 | **102** | §4, 18/18 samples (true delta from the correct pre-#459 baseline is +8, but the ceiling's own field currently reads 101, one component of a separately-stale figure — see §4's `hole_clearance` note) |
| `violations_by_type.shorting_items` | 113 | **118** | §4, 18/18 samples |
| `violations_by_type.solder_mask_bridge` | 64 | **69** | §4, 18/18 samples |
| `warnings_by_type.lib_footprint_issues` | 8 | **9** | §4, 18/18 samples |
| `warnings_by_type.pth_inside_courtyard` | 8 | **9** | §4, 18/18 samples |

Optional (decreases only, no approval required, included for completeness
since this repo's convention records every measured category rather than
only the ones that regressed): `warning_ceiling` 683 → **680**,
`warnings_by_type.lib_footprint_mismatch` 28 → **25**,
`warnings_by_type.missing_courtyard` 7 → **5** (all three improved,
unrelated to #459's own explanation but consistent with it — fewer
footprint/courtyard mismatches after 6 stale copies were corrected).
`clearance` (502), `annular_width`, `creepage`, `drill_out_of_range`,
`hole_to_hole`, `tracks_crossing`, `via_diameter`, and the remaining
warning categories are all unchanged and need no action.

`nondeterministic_error_types` needs no structural change: still exactly
`clearance`, still 499-501 (this run's 18 samples: 499-500, a subset of
the historical range).

## 8. What was fixed vs. deferred

**Nothing fixed.** Every regressed category traces to a footprint that
`elec/src`/`pcb/libs` already specify correctly and that #459 correctly
propagated onto the board; there is no code or `pcb/temper.kicad_pro`
defect driving any of the 7 categories. The remaining path to a green
gate is (a) a human applying §7's ceiling values with a
`Ceiling-Approval:` trailer, and/or (b) an eventual PCB layout pass
(`pcb/temper.kicad_pcb`, explicitly out of this task's reach) to open
clearance around U3's wider body and C1/C25/C26's larger ones — the same
kind of human PCB-design decision this repo has already deferred once,
for `tank.c_tank3`'s own placement, in #459 itself.

## Reproduction

```bash
PYTHONPATH=$(pwd)/packages/temper-placer/src .venv/bin/python scripts/ci_check_drc.py --backend kicad-cli

# pre-#459 comparison board (never git stash; detached worktree instead)
git worktree add --detach /tmp/wt-pre459 27ecfee4
# regenerate matching .kicad_dru in both trees from the one SSOT script,
# then run temper_placer.validation._drc_api.run_drc() on each and diff
# by (reference -> sheetpath) identity, not raw reference designator.
```
