# PR #460's corrected box is sound; the golden-board short was a writer sign bug — root cause, fix, measurement

<!-- provenance: commit=4a387393ec9e4626fa2ebbf044ecc029ec9e003d dirty=true -->
<!-- base: fix/domain-clearance-copper-aware, includes cherry-picked #470/#471 -->

**Date:** 2026-07-30
**Scope:** `pcb/**` and `elec/src/**` are read-only throughout. No placement was written to
`pcb/temper.kicad_pcb`. All re-solves below run against
`power_pcb_dataset/corpus/temper/temper.kicad_pcb` (the golden-board regression gate's own board)
or scratch-only candidate files.

---

## 0. Verdict up front

**The corrected `comp.bounds` from PR #460 does NOT under-enclose real pad copper.** The Q1/Q2
short reported against this PR is real, reproduces, and is exactly the pair/coordinates reported —
but its root cause is **not** the box, not the generic separation margin, and not something #460
needs to loosen. It is a pre-existing, previously-undiscovered **sign error** in every place this
codebase converts between a CP-SAT box-centre coordinate and a KiCad footprint anchor under
rotation. `domain_clearance.py`'s own soundness proof (box-to-box implies copper-to-copper, given
box ⊇ real pad copper) never does this conversion — it reasons entirely in the box's own symmetric,
rotation-agnostic frame — so **the proof itself is untouched by this finding**. The bug is entirely
in the translation layer that turns a *proven-sound* CP-SAT solution into KiCad text, and separately,
in the *validator's own* copper-to-copper measurement.

---

## 1. Root cause: KiCad rotates a footprint's pads **clockwise**, this codebase assumed CCW

Three functions convert between a component's CP-SAT box-centre (`Component.initial_position`'s
convention — the point the solver actually reasons about) and its raw KiCad anchor
(`(at X Y ANGLE)`, the point the *pads' own stored local offsets* are rotated around), each via a
`rotated_cx`/`rotated_cy` calculation:

| Function | Direction | Consumer |
|---|---|---|
| `io/_parse_modules.py::_extract_components_from_pcb` | anchor → centre (read) | `Component.initial_position` (CP-SAT `AddHint`) |
| `io/_write_board.py::write_placements_to_pcb` / `state_to_placements` | centre → anchor (write) | `pcb/temper.kicad_pcb`'s real, shipped write path |
| `router_v6/_adapter_convert.py::_apply_placements_to_pcb` | centre → anchor (write), **new this task** | `test_golden_board_drc_regression` and `route_pcb` |
| `requirements/validators/_copper.py::_rotate` | local pad offset → world (read, for measurement) | REQ-SAFE-01's copper-to-copper check |

All four used the **same** formula, standard CCW-positive trigonometry:

```
rotated_x = cx*cos(theta) - cy*sin(theta)
rotated_y = cx*sin(theta) + cy*cos(theta)
```

**This is not what KiCad does.** Verified directly against `pcbnew` (KiCad's own placement engine —
not kiutils, not a re-derivation): loaded via KiCad's bundled Python
(`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
-c "import pcbnew"`), a synthetic footprint at a non-axis-aligned angle (37°) with a local pad
offset of `(10, 4)` places that pad at **`(10.393615, -2.823608)`** mm — to 6 decimal places, the
prediction of

```
rotated_x = cx*cos(theta) + cy*sin(theta)
rotated_y = -cx*sin(theta) + cy*cos(theta)
```

i.e. `R(-theta)` in the standard convention above — KiCad rotates a footprint's pads **clockwise**
by its stated angle, not counter-clockwise. The CCW formula's prediction for the same input,
`(5.579095, 9.212693)`, is a different point entirely; a DRC probe test (placing a second footprint
at each candidate point and checking which one `kicad-cli pcb drc` reports as overlapping U1's pad)
independently confirms the same answer. The two conventions coincide only at 0°/180° — which is
exactly why this went unnoticed: on `pcb/temper.kicad_pcb`, this bug is silent for any component
whose rotation is a multiple of 180° or whose `center_offset` is `(0, 0)`, and it self-cancels
across a read→write round trip whenever a component's rotation doesn't *change* (see §3). It only
produces a real position error when a component with nonzero `center_offset` is *newly* rotated to
90° or 270° — precisely what a from-scratch CP-SAT solve does.

---

## 2. Reproducing the Q1/Q2 short — and showing it is this bug, not the box

`test_golden_board_drc_regression` solves the corpus board from scratch (`seed=42`, deterministic on
this host — 5 repeated runs of the full solve produce byte-identical `result.positions`/
`result.rotations`) and writes it via `_apply_placements_to_pcb`. Before this task's cherry-picks,
that function never applied a solved rotation at all (PR #471 built the mechanism but left it
unwired, precisely because wiring rotation alone — without the matching position-frame conversion —
**makes DRC worse**, per that PR's own measurement). Reproducing PR #460's reported regression
exactly, on this exact solve:

- **Pre-existing (before any fix in this task):** `Q1 rot=0, Q2 rot=3 (270°)`. Writing with no
  rotation/offset correction (the code as it stood): `shorting_items: 1` (an *different*,
  already-documented pair, `C_CT_FILT`/`U_OPAMP_CT` — see
  `docs/evidence/2026-07-30-domain-clearance-copper-aware-fix.md` §7.1; both have `center_offset=0`
  so only the missing-rotation half of this bug bites them).
- **Wiring PR #471's rotation mechanism alone** (no `center_offset` correction — the state before
  this doc's fix): `shorting_items: 4`, including, verbatim, **the exact Q1/Q2 short originally
  reported**:
  ```json
  {"description": "Items shorting two nets (nets DC_BUS+ and SW_NODE)",
   "items": [{"description": "PTH pad 2 [DC_BUS+] of Q1", "pos": {"x": 30.3, "y": 147.15}},
             {"description": "PTH pad 2 [SW_NODE] of Q2", "pos": {"x": 29.3, "y": 148.7}}],
   "severity": "error", "type": "shorting_items"}
  ```
  Q1 (`center_offset=(5.45, 0)`, `rot=0`) and Q2 (`center_offset=(5.45, 0)`, `rot=270°`) are both
  `TO-247-3_Horizontal` — pad 2 sits exactly at each component's box centre in the shifted frame
  (`center_offset` cancels pad 2's local offset exactly, since the footprint's 3 pads are evenly
  spaced). Writing rotation without the matching `center_offset` inversion moves Q2's whole footprint
  (pads included) to a position computed for a *different* frame than the one its pads are stored
  in, and the resulting mismatch physically overlaps Q1 and Q2's PTH pads. **This is the writer bug,
  reproduced exactly — not a box or margin problem**: `domain_clearance.py`/`handlers/separated.py`
  are not in this solve's critical path for this pair at all (DC_BUS+/SW_NODE are both HV, so no
  domain-clearance constraint is emitted for it, and Q1/Q2 are the same net class, so no netclass
  `SeparatedConstraint` is emitted either — confirmed by reading `netclass_constraints.py`'s
  `ca == cb: continue`). The only thing separating Q1 and Q2 in the CP-SAT model is the bare
  `AddNoOverlap2D` (0 margin, `model.py:218`) over `comp.bounds` — and that constraint's own box
  positions (`x_center`/`y_center`, the *centre* convention) were fully honored by the solve; only
  the **write-back to KiCad text** discarded the frame.
- **With the correct (clockwise, pcbnew-verified) sign in the offset inversion, PLUS the rotation
  write PR #471 already built** (this doc's actual fix): `shorting_items: 0`.

## 3. Why this was invisible until now

- `write_placements_to_pcb` (the real ship path for `pcb/temper.kicad_pcb`) carried the identical
  wrong-sign formula. It was never caught because: (a) reading a board (`_parse_modules.py`) and
  writing it back (`_write_board.py`) use the *same* wrong sign, so `center_offset`'s error term
  cancels algebraically in any round trip where a component's rotation does not change between read
  and write — which covers virtually all historical usage, since nothing wired solved-rotation
  writing into the production path's typical call pattern until very recently; and (b) for a
  component whose rotation *is* a multiple of 180°, `sin(theta) = 0` and the two sign conventions
  produce an identical result regardless.
- `requirements/validators/_copper.py::_rotate` used the **same wrong sign**, and its own docstring
  said so explicitly ("R(+theta) — the convention this repo's own KiCad parser ... and writer ...
  both use") — i.e. it was deliberately kept *consistent* with the buggy convention rather than
  checked against KiCad itself. Self-consistency between two wrong functions produces a validator
  that agrees with itself and with the (also wrong) writer, and disagrees with reality only for
  components where it matters — 90°/270° rotation, nonzero `center_offset`.

## 4. `pcb/temper.kicad_pcb` already has 18 real components in the affected class

Checked directly (`_rotation_deg` and `_center_offset_x/y` attributes from parsing the committed
production board): **18 components carry both a 90°/270° rotation and a nonzero `center_offset`**
today — `C1, C24, C25, C4, C8, F1, J1, K3, PS1, R1, R11, R12, R13, R60, RT1, T1, U1, U6`. Every one
of these has had this sign bug latent in `initial_position` (used only for CP-SAT's `AddHint`
warm-start — not a hard constraint, and not consumed by the validator) and, more importantly, in the
validator's own `_copper.py::_rotate` — i.e. their **measured** REQ-SAFE-01 clearance/creepage
figures were being computed from a mirrored pad position.

---

## 5. The fix

Four files, one formula, corrected everywhere it appears (all now cite the same pcbnew measurement):

1. **`router_v6/_adapter_convert.py::_apply_placements_to_pcb`** (new `components=` parameter this
   task adds): inverts `center_offset` using the correct clockwise convention, at whichever rotation
   the centre was actually computed at (`rotations.get(ref)` when supplied, else the footprint's
   existing angle — matching `to_rotations_dict()`'s sparse convention, which omits rotation-index-0
   refs). `route_pcb` threads a matching `components=` parameter through. Omitting `components=`
   (the default) reproduces prior behavior byte-for-byte — every existing call site not touched by
   this task is unaffected.
2. **`io/_write_board.py::write_placements_to_pcb`** and **`state_to_placements`**: same formula
   correction. This is the function `pcb/temper.kicad_pcb` actually ships through — previously
   latent (per §3), now correct for any future re-solve that rotates one of the 18 affected
   components.
3. **`io/_parse_modules.py::_extract_components_from_pcb`**: read-side correction (the exact inverse
   of #2, required for a read→write round trip to recover the original anchor under the *new*,
   correct sign). No-op for any component at 0°/180° (18/168 = 10.7% of `pcb/temper.kicad_pcb`'s
   components are actually affected in each direction); does not feed the validator (`Pin.position`,
   consumed by REQ-SAFE-01, is computed independently, in the unrotated local frame, and is
   unaffected by this change — confirmed by inspection, not assumed).
4. **`requirements/validators/_copper.py::_rotate`**: same formula correction. This is the one that
   matters for safety measurement: REQ-SAFE-01's copper-to-copper distance for all 18 affected
   components was being computed at the wrong (mirrored) pad position.

**Test wiring:** `test_golden_board_drc_regression` now passes `rotations=result.to_rotations_dict()`
and `components=netlist.components` to `_apply_placements_to_pcb` — both together, never one alone
(per PR #471's own finding that rotation-only makes DRC worse, reproduced in §2 above).

**Why this is not a loosening of anything in PR #460:** `domain_clearance.py`, `handlers/separated.py`,
and `_calculate_footprint_bounds` are untouched. The box-containment proof never performs a
centre↔anchor conversion (it stays entirely in the box's own frame — a box being symmetric around its
centre is rotation-sign-agnostic, since swapping `w`/`h` under any 90° multiple preserves symmetry
regardless of which rotation direction is "positive"). Nothing about the corrected, tighter bounds
changed; the translation layer around it is now honest.

---

## 6. Measurement

### 6.1 Golden-board regression gate (`test_golden_board_drc_regression`)

Full solve of `power_pcb_dataset/corpus/temper/temper.kicad_pcb`, `seed=42`, deterministic
(confirmed: identical `positions`/`rotations` across 5 repeated solves). `kicad-cli pcb drc`,
`shorting_items` and `solder_mask_bridge`, N=5 runs on the same written file per state (scatter is
`kicad-cli`'s own, not the solve's — see `test_regression_drc.py`'s own documented protocol):

| State | shorting_items (5 runs) | median | solder_mask_bridge | total violations |
|---|---|---|---|---|
| PR #460 alone (no rotation/offset write at all) | 1,1,1,1,1 | **1** | 1 | 41 |
| + PR #471's rotation write, WITHOUT center_offset fix | 4,4,4,4,4 | **4** | 2 | 49 |
| + this fix (rotation AND center_offset, correct sign) | 0,0,0,0,0 | **0** | 0 | 41 |

`test_golden_board_drc_regression` **passes** with this fix (`shorting == 0`, `mask_bridge == 0`,
`placement_fixable = 8` from unrelated `clearance` violations, well under the `<= 15` gate).
Confirmed stable over 3 repeated full pytest runs (not just repeated `kicad-cli` calls on one file).

No pre-existing-rotation-writer residue remains to report separately (§7 of
`docs/evidence/2026-07-30-domain-clearance-copper-aware-fix.md`'s `C_CT_FILT`/`U_OPAMP_CT` case —
that pair's own shorting_items violation is gone in the table above too, since it was the *same*
class of bug, just the rotation-only half of it).

### 6.2 Production board (`pcb/temper.kicad_pcb`, committed, no CP-SAT solve)

`test_production_board_drc_regression` does not run CP-SAT and never calls the writer this fix
touches (`route_pcb(parsed_stub, {}, ...)` — empty placements, board's own coordinates used as-is).
**Expected and confirmed unaffected.** `kicad-cli pcb drc`, N=5, this checkout:

| Metric | 5 runs | median | test's documented baseline (N=15, 2026-07-29) | gate |
|---|---|---|---|---|
| shorting_items | 87, 89, 83, 87, 76 | **87** | median 68, range 66–87 | ≤ 90 (pass) |
| total | 1256, 1250, 1250, 1243, 1241 | **1250** | median 1234, range 1232–1258 | ≤ 1260 (pass) |

`test_production_board_drc_regression` **passes**, unchanged in cause from before this task (the
committed board file is byte-identical; this fix touches no file under `pcb/**`).

### 6.3 REQ-SAFE-01 validator (`test_temper_board_clearance_compliance`, real board, no solve)

This test is a pre-existing, documented failure this task's hard constraints forbid silencing
(`pcb/temper.kicad_pcb` needs an actual re-placement to close it — out of scope here, as PR #460's
own evidence doc states). What changed is the **measured count**, because §1's validator-side fix
(`_copper.py::_rotate`) corrects the pad position used for 18 real, already-rotated, already-offset
production components:

| State | REQ-SAFE-01 violations | unique (pair, boundary, metric) records |
|---|---|---|
| Before this fix (PR #460 baseline, matches its evidence doc exactly) | 98 | 73 |
| After this fix (`_copper.py::_rotate` corrected) | **102** | 79 |

The +4 net is not uniform growth: of the 18 affected components' pairs, **9 pairs gained a violation
that was being missed** (`F1<->C30`, `F1<->R70`, `F1<->TP1`, `R12<->K3`, `R30<->L2`, `U6<->D4`,
`U6<->R18`, `U6<->R2`, `U7<->R67`) and **4 pairs lost one that was a false positive**
(`C22<->L2`, `R20<->R78`, `R5<->R41`, `U8<->C32`); the remaining shared pairs (`C17<->C30`,
`C22<->C28`, `C23<->U27`, `C27<->C18`, `C27<->R25`, `C27<->R29`, `R30<->C30`) keep the same
violation but at a corrected distance. **Net direction is toward more reported violations, not
fewer** — the sign bug was net *hiding* real hazards, the unsafe direction, not manufacturing
phantom ones. This is a real, measured, safety-relevant correction to the validator itself, found as
a direct consequence of tracing PR #460's regression to ground truth (`pcbnew`) instead of stopping
at internal self-consistency. `pcb/temper.kicad_pcb` was not modified to produce this number; it is
purely a measurement correction.

This 102 does not match the task brief's cited "main currently reports ~109 at the operative
PD3/12.6mm figure" — expected, since this branch is deliberately stacked on an older `main`
(`ed5ee134`, predating several since-merged safety/creepage config changes on `main`, per this
task's own instruction not to rebase onto the very latest `main`) rather than tracking `main`'s
current tip. The 98→102 delta above is the correct, apples-to-apples, same-commit comparison for
this specific fix.

---

## 7. Regression tests

New: `TestApplyPlacementsToPcbCenterOffset` in `tests/router_v6/test_adapter.py` (4 tests) —
pcbnew-verified anchor/rotation numbers for an asymmetric-`center_offset` footprint, confirmed to
fail (3 of 4, `TypeError`/wrong-anchor) on the pre-fix code via controlled reversion, matching PR
#460's own precedent for a "regression test that fails without the fix."

```
uv run pytest packages/temper-placer/tests/router_v6/test_adapter.py::TestApplyPlacementsToPcbCenterOffset -v
# 4 passed
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression -q
# 1 passed (0 shorting_items) -- 3 repeated full-pytest runs, all pass
uv run pytest packages/temper-placer/tests/io/ -q
# 275 passed, 8 skipped, 1 xfailed -- matches PR #460's own baseline exactly
uv run pytest packages/temper-placer/tests/requirements/ -q
# 293 passed, 5 skipped, 1 pre-existing failure (test_temper_board_clearance_compliance,
# now 102 violations -- see Sec 6.3; not silenced, matches PR #460's forbidding-modification instruction)
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py -q
# 21 passed -- matches PR #460's own baseline exactly
```

---

## 8. Reproduction

```bash
git fetch origin && git checkout -b fix/generic-separation-soundness origin/fix/domain-clearance-copper-aware
uv sync --all-packages
make netlist
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression -q
uv run pytest packages/temper-placer/tests/router_v6/test_adapter.py::TestApplyPlacementsToPcbCenterOffset -v
```

The pcbnew ground-truth check (KiCad's own placement engine, not this repo's code) used to derive
and verify the correct rotation sign:

```bash
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 -c '
import pcbnew, tempfile
content = """(kicad_pcb (version 20240108) (generator "t") (generator_version "9.0")
  (general (thickness 1.6)) (paper "A4")
  (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
  (setup (pad_to_mask_clearance 0)) (net 0 "") (net 1 "NET1")
  (footprint "test:FP" (layer "F.Cu") (tstamp 00000000-0000-0000-0000-000000000001)
    (at 0 0 37.0000)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
    (attr through_hole)
    (pad "1" thru_hole circle (at 0 0) (size 1 1) (drill 0.5) (layers "*.Cu" "*.Mask") (net 1 "NET1"))
    (pad "2" thru_hole circle (at 10 4) (size 1 1) (drill 0.5) (layers "*.Cu" "*.Mask") (net 1 "NET1"))
  ))"""
with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as f:
    f.write(content); path = f.name
board = pcbnew.LoadBoard(path)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        print(pad.GetNumber(), pad.GetPosition().x/1e6, pad.GetPosition().y/1e6)
'
# pad "2" -> 10.393615 -2.823608  (R(-37deg) of (10,4); R(+37deg) predicts (5.579095, 9.212693))
```
