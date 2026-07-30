# `_apply_placements_to_pcb` dropped solved rotation: fix, measurement, and why it is not wired on by default

<!-- provenance: commit=251589a463125fe62d6cea14b7f4ac17ae80d44e dirty=false -->
<!-- base: origin/main, worktree fix/placement-writer-rotation -->

**Date:** 2026-07-30
**Scope:** `pcb/**` and `elec/src/**` read-only throughout. No placement was written to any
tracked board. All measurement below runs against `power_pcb_dataset/corpus/temper/temper.kicad_pcb`
(the same board `test_golden_board_drc_regression` uses) or scratch-only candidate files.

---

## 0. The bug

`packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py::_apply_placements_to_pcb`
takes `placements: dict[str, tuple[float, float]]` — position only. `CpSatPlacementResult` (the
CP-SAT solver's result type, `_encoder_solve.py`) separately carries `rotations: dict[str, int]`
(a 4-way index, `*90.0` = degrees). `_apply_placements_to_pcb`'s regex for the footprint's own
`(at X Y [ANGLE])` line explicitly *reuses the captured old angle group unchanged* — so any
component the solver chose to rotate is written at its solved **position** but its **pre-solve**
angle, every time, unconditionally. No caller (`route_pcb`, `_loop_routing.py::_route_placement`
/ `_get_placement_pcb_path`, `test_regression_drc.py`'s two golden-board tests) has ever had a way
to pass a rotation through, because the function itself has no parameter for it.

This is a **different** function from `write_placements_to_pcb` (`io/_write_board.py`), the writer
`pcb/temper.kicad_pcb`'s real write path (the `temper optimize` CLI command) uses. That writer
already threads rotation correctly and already re-orients pads (PR #412, `_reorient_pads`). So this
bug does **not** reach the committed production board — see Sec 5 for exactly where it does reach.

---

## 1. The fix

Added an optional `rotations: dict[str, float] | None = None` parameter to both
`_apply_placements_to_pcb` and `route_pcb`. A ref present in `placements` but absent from
`rotations` (or `rotations=None` entirely, the default) keeps its existing angle **byte-for-byte
unchanged** — verified by keeping the original regex/replacement path completely untouched for
that branch (see `test_no_rotations_arg_preserves_angle_exactly`,
`test_ref_absent_from_rotations_preserves_angle`).

When a ref has a target angle, two things happen, mirroring `_write_board.py::_reorient_pads` (the
kiutils-based precedent) on raw string content instead of a parsed tree:

1. The footprint's own `(at X Y ANGLE)` is rewritten to the new position and angle (angle token
   omitted when it normalizes to 0, matching the kiutils/KiCad convention `_reorient_pads` already
   documents).
2. Every pad inside that footprint has its **own absolute angle** shifted by the same delta
   (`new_fp_angle - old_fp_angle`), via a new `_PAD_AT_RE` regex + `_reorient_pads_in_footprint_block`
   helper. This is required because **a `.kicad_pcb` pad angle is absolute, not offset from the
   parent footprint** — the exact defect class that caused 60 intra-component copper shorts in
   PRs #412/#420/#426 when `write_placements_to_pcb` didn't yet do this. Pad local `(x, y)` offsets
   are left untouched (KiCad auto-rotates those via the footprint's own angle at load time; only
   the pad's own shape-angle field needs the explicit rewrite).

`CpSatPlacementResult.to_rotations_dict()` was added (`_encoder_solve.py`) to convert the solver's
`rotations` index dict to the degrees convention `_apply_placements_to_pcb` expects, factoring out
the ad hoc `cp_result.rotations.get(ref, 0) * 90.0` already duplicated once in `cli/__init__.py`.

**New tests** (`TestApplyPlacementsToPcbRotation`, 7 cases,
`packages/temper-placer/tests/router_v6/test_adapter.py`): footprint angle is written; pad bodies
re-orient by the same delta; an intrinsic pad-to-footprint offset survives a rotation (`90 -> 180`
footprint carries a pad already at `90` to `180`, not to `90`); a rotation that normalizes to 0
omits the angle token; a zero delta leaves pad angles completely untouched (not merely rewritten to
the same value). All 7 fail against the pre-fix code with `TypeError: _apply_placements_to_pcb()
got an unexpected keyword argument 'rotations'` — the parameter did not exist before this fix.

---

## 2. LOC budget for this change

Item 2 of this task (`LOC Cap Gate`) turned out to flag exactly this file
(`_adapter_convert.py`, 1129 lines, `ALLOWLIST_GREW` against a recorded baseline of 1095 — grown by
PR #434's netclass-substring-classification fix). Handled first, by extraction (see the
`LOC_CAP_FIX.md`-equivalent PR description / commit for the full account): `_zone_layers_for_net`,
`_zone_params_for_net`, `_CONTINUITY_EXEMPT_CLASSES`, `_stitch_isolated_pads`, `_emit_zone_pours`,
and `_chamfer_path_points` (~340 lines, a cohesive "which nets get pour treatment and how" seam)
moved to a new `_zone_pour_stitch.py`, re-exported so no import path changed (`adapter.py`'s
`__all__`, `tests/router_v6/test_adapter.py`'s direct imports both unaffected) — precedent: PR #412
(`_astar_reconstruct.py`, 1220 -> 1117 lines via the same move-and-re-export pattern).

That brought `_adapter_convert.py` to 804 lines before this rotation fix, and to **887 lines**
after it — under the 1000 cap with room to spare. The stale allowlist entry was removed entirely
(not just shrunk), paying the debt down rather than re-recording a smaller baseline.

---

## 3. Measurement: does applying the fix improve or worsen DRC?

Methodology: run the **exact same solve** `test_golden_board_drc_regression` runs (corpus board
`power_pcb_dataset/corpus/temper/temper.kicad_pcb`, `seed=42`, same PCL constraints/zones, same
`_UNRESOLVED_REF_POLICY="warn"` downgrade), then build two candidate boards from the **identical**
`placements` dict — one via `_apply_placements_to_pcb(..., rotations=None)` (today's behavior), one
via `_apply_placements_to_pcb(..., rotations=result.to_rotations_dict())` (the fix applied) — and
DRC both with `kicad-cli pcb drc --format json`, median of N=5 each (deterministic writer output,
so N=5 is to catch KiCad DRC's own run-to-run scatter, per `docs/STRATEGY.md`'s standing
methodology).

### 3.1 On origin/main as-is (no other change)

CP-SAT (seed=42) solves 28 of 33 components to a 180° rotation, 0 to 90/270. Median of N=5, both
candidates:

| Candidate | total | shorting_items | mask_bridge | edge_clearance | placement_fixable |
|---|---|---|---|---|---|
| NO-ROTATION (today) | 43 | 0 | 0 | 2 | 10 |
| WITH-ROTATION (fix) | 43 | 0 | 0 | 2 | 10 |

**Identical on every metric, all 5 runs each, zero scatter.** The two boards are *not*
byte-identical (258 diff lines — footprint angles and pad angles genuinely change), but a 180°
rotation of this board's mostly 2/3-pin THT/SMD parts is point-symmetric: the pads swap positions
around the same center, so the physical copper footprint is unchanged. This case is DRC-neutral,
neither an improvement nor a regression.

### 3.2 Reproducing PR #460's exact reported regression

PR #460 (`fix/domain-clearance-copper-aware`, open, not yet merged) changes
`_calculate_footprint_bounds` (`io/_parse_modules.py`) to compute the CP-SAT placement box centered
on the same point (`center_offset`, the pad centroid) the solver actually places at, instead of the
footprint's raw KiCad anchor. Its own evidence doc (`docs/evidence/2026-07-30-domain-clearance-
copper-aware-fix.md`, Sec 7.1) reports this shifts CP-SAT's global solution enough that two corpus
components (`C_CT_FILT`, `U_OPAMP_CT`) land on non-zero rotations for the first time under this
seed, exposing this exact writer bug as a **newly-failing** `test_golden_board_drc_regression`
(`shorting_items: 1, solder_mask_bridge: 1`) — root-caused there, explicitly filed as *this* PR's
job to fix (R22: architectural fix, separate PR).

Reproduced directly: `io/_parse_modules.py` temporarily swapped for PR #460's version (`git show
origin/fix/domain-clearance-copper-aware:...`, restored immediately after measurement — **not**
part of this PR's diff), same solve re-run:

- 21 of 33 components now solve non-zero, including 90°/270° for asymmetric-footprint parts
  (`Q2` TO-247, `U_GATE` SOIC-16W, `D1`, `C_BUS1/2`, `U_LDO_5V`, `J_USB`, `J_COIL`, `C_CT_FILT` at
  270°, `U_OPAMP_CT` at 180° — matching PR #460's own reported rotation choices exactly).
- NO-ROTATION candidate (today's writer): `shorting_items=1`, `solder_mask_bridge=1`, `total=43`,
  `placement_fixable=10` — **reproduces PR #460's reported regression exactly.**

| Candidate | total | shorting_items | mask_bridge | edge_clearance | placement_fixable |
|---|---|---|---|---|---|
| NO-ROTATION (today, = PR #460's reported failure) | 43 | **1** | **1** | 0 | 10 |
| WITH-ROTATION (this fix applied) | 49 | **4** | **2** | 1 | **16** |

All values are medians of N=5, **zero scatter across all 5 runs each direction** (not noise).

**This fix does not resolve `test_golden_board_drc_regression`'s regression. It makes it worse and
adds a new failure mode** (`placement_fixable` 10 -> 16, newly over the test's own `<= 15` gate).
`shorting_items` roughly quadruples (1 -> 4) and moves to a *different* net pair (`GND`/`I_SENSE`
without the fix, vs. four `GATE_H`/`DC_BUS-` shorts with it) — not the same defect relocated, a
different and larger one.

---

## 4. Why "correct" rotation-writing makes this worse: a second, entangled, pre-existing bug

Manually inspected the diff between the two candidate boards for the `Q2`/`U_GATE` footprints
(the ones now producing `GATE_H`/`DC_BUS-` shorts). The rotation write itself is mechanically
correct — footprint angle and every pad's absolute angle both shift by the solved delta, pad
local `(x, y)` untouched, matching what Sec 1's unit tests check. The problem is upstream of
rotation entirely:

`CpSatModel` places each component's box centered at `Component.initial_position`
(`io/_parse_modules.py`), which is **`fp.position + rotate(center_offset, angle)`** — not the
footprint's raw KiCad anchor. `write_placements_to_pcb` (`_write_board.py`, the already-correct
production writer) knows this and explicitly **subtracts the rotated `center_offset`** before
writing `(at X Y)` (its own docstring: "Positions are assumed to be in bounding-box-center
coordinates... center offsets will be extracted and subtracted"). **`_apply_placements_to_pcb`
(and every caller in its chain — `route_pcb`, `_loop_routing.py`) has never done this conversion.**
It writes `placements[ref]` (the raw CP-SAT box-center) directly as the footprint's anchor.

For a component with zero center_offset (pads symmetric about their own centroid) this is harmless
— center and anchor coincide. For one with a nonzero offset — `Q2`'s TO-247, three pads at local
x = 0 / 5.45 / 10.9, `center_offset_x = 5.45mm` — the written anchor is off by
`rotate((5.45, 0), angle)` from where it should be: **up to 5.45mm**, in a direction that changes
with the solved rotation. This position error is identical in both the NO-ROTATION and
WITH-ROTATION candidates (nothing in this PR's diff touches position-writing), so it is not the
*direct cause of the difference* between them — but it means CP-SAT's box-based non-overlap
guarantee never actually held for the **written** geometry of any asymmetric-center component in
the first place, rotated or not. Writing the geometrically-correct rotation on top of a
still-wrong position doesn't restore the guarantee; it just changes which now-correctly-shaped
pads collide with which neighbors, and on this specific solve, that lands on more collisions, not
fewer.

**This is confirmed independently, not just theorized**: PR #460's own evidence doc traces the
identical root cause (Sec 7.1) and reaches the identical conclusion — "a rotation-propagation fix
for a shared writer function is an architectural fix... deserves its own dedicated PR" — and
explicitly did not fix it, filing it as this PR's job. This PR fixes the rotation half of that
diagnosis (proven correct in isolation, Sec 1) but the position-frame half (`center_offset`
subtraction, matching `write_placements_to_pcb`'s already-fixed convention) is a separate,
architectural change to `route_pcb`/`_apply_placements_to_pcb`'s calling contract (it would need
`comp.attributes["_center_offset_x/y"]` threaded through, the same way `write_placements_to_pcb`
receives `components=`) and is **not fixed here** per R22 (Bug-Triage Rule: architectural fixes are
scoped as a separate follow-up, not inlined into this bugfix).

---

## 5. Where this bug does and does not reach

- **`pcb/temper.kicad_pcb` (the real, shipped board): unaffected.** Its write path is
  `write_placements_to_pcb` (`temper optimize` CLI command), a different function that already
  applies rotation, already reorients pads (PR #412), and already does the center-offset
  conversion (`_write_board.py`, unconditionally, since before this task). Nothing in this PR
  changes that path.
- **`test_golden_board_drc_regression` / `test_golden_board_routing_drc_regression`
  (`test_regression_drc.py`): exercised, measured above, left unchanged.** These two tests still
  call `_apply_placements_to_pcb`/`route_pcb` without passing `rotations=` — i.e. they keep
  today's (buggy but measured-neutral-to-mildly-bad) behavior. Wiring the fix into these calls was
  evaluated and rejected: it would turn `test_golden_board_drc_regression` from passing (on
  `origin/main` as-is) to failing outright (Sec 3.2's WITH-ROTATION row exceeds the test's own
  thresholds), which is not an acceptable side effect of a bugfix PR.
  `test_golden_board_routing_drc_regression` is already unconditionally skipped for an unrelated,
  pre-existing reason (KNOWN GAP, completion_rate regression) and was not further exercised.
- **The place->route loop's internal routing-stage DRC gate
  (`placer/cp_sat/_loop_routing.py::_route_placement`) also calls `route_pcb`, and therefore also
  keeps today's (rotation-dropping) behavior.** This is worth flagging operationally, not just for
  this test: because the loop's *gate check* uses this writer while the loop's *final board write*
  (via a completely separate call chain ending in `write_placements_to_pcb`) does not, a candidate
  placement's routing-stage DRC gate can be evaluated against different geometry than what
  eventually gets written for real. Fixing that consistency gap is the same architectural
  follow-up as Sec 4, not addressed here.
- **REQ-SAFE-01** (`test_clearance.py::test_temper_board_clearance_compliance`) does not call
  `_apply_placements_to_pcb`, `route_pcb`, or any CP-SAT solve at all — it validates the board as
  parsed directly. This fix has **zero effect** on it; it is unmeasured here because it is not
  exercised by the changed code, not because it was skipped.

---

## 6. Conclusion / what shipped

- **The rotation-drop bug is real, fixed, and unit-tested** (Sec 1): `_apply_placements_to_pcb`
  and `route_pcb` gained a correctly-implemented, backward-compatible `rotations=` parameter that
  writes both footprint and per-pad absolute angles consistently, mirroring the already-shipped
  `_write_board.py::_reorient_pads` precedent.
- **Applying it is not wired on anywhere by default.** Measured, not assumed: on the one existing
  scenario that exercises a non-trivial (90°/270°) solved rotation on this codebase's only
  from-scratch CP-SAT + corpus-board pipeline, applying the fix makes
  `test_golden_board_drc_regression`'s metrics strictly worse (shorting_items 1->4,
  solder_mask_bridge 1->2, `placement_fixable` newly exceeds its own gate) rather than resolving
  the regression PR #460 reported. Root-caused (Sec 4) to an entangled, pre-existing,
  out-of-scope defect: `_apply_placements_to_pcb`'s callers never convert CP-SAT's box-center
  position back to the footprint's KiCad anchor via the `center_offset` subtraction
  `write_placements_to_pcb` already performs. Per R22, that conversion is a separate architectural
  fix and is not inlined here.
- **No caller's behavior changes as a result of this PR** — `route_pcb`, `_loop_routing.py`,
  and both golden-board tests all keep calling the affected functions exactly as before (no
  `rotations=` argument), so nothing measured above is a live regression risk from merging this
  PR. The capability exists, correctly, for a future PR that also fixes Sec 4's position-frame
  conversion — at which point re-running Sec 3's exact methodology is the right way to decide
  whether to wire it on.

---

## 7. Reproduction

```bash
git fetch origin && git checkout -b fix/placement-writer-rotation origin/main
uv sync --all-packages

# Item 1 unit tests (new + pre-existing, same file):
uv run pytest packages/temper-placer/tests/router_v6/test_adapter.py -q
uv run pytest packages/temper-placer/tests/router_v6/test_adapter.py::TestApplyPlacementsToPcbRotation -q

# Item 1 golden-board DRC gate (left unchanged by this PR, still passes as today):
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression -rA -s

# Item 2:
uv run python tools/loc_cap_check.py   # LOC-CAP-OK, 4 allowlist entries (was 5)
```

The Sec 3.2 A/B driver (`measure_rotation.py`) is scratch-only per this task's instructions (not
committed); its full invocations and output are reproduced verbatim above. The two candidate
boards it wrote are scratch-only and were never written to `pcb/`.
