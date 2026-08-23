<!-- provenance: commit=fbc5ce517fec9bbefcbaf632efa6b0ee4062d047 dirty=UNKNOWN -->
measurement time, branch=fix/component-bounds-pad-extent,
worktree=/home/bennet/Desktop/temper-worktrees/component-bounds-pad-extent.
Measured 2026-08-12 against the pinned pumpkin_engine
(binary_sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e,
source_commit=5bbf650d47, verified via scripts/verify_pumpkin_engine.py exit 0
before every solve below). pcb/temper.kicad_pcb was NOT modified by this
investigation or its fix -- every board write below went to a scratch temp
file, never to pcb/temper.kicad_pcb itself (`git status --short pcb/` empty
throughout). -->

# L1 pad-outside-outline was not a `Component.bounds` derivation bug -- it's a rotation-index-0 write-back bug affecting ~18-21% of a real solve

**Verdict up front.** `check_board_containment.py` reported L1 (`power_in.cmc`)
with a pad fully outside the board outline on a freshly-solved candidate
board. The task's working hypothesis was that `Component.bounds` (the box
`_calculate_footprint_bounds`/`calculate_footprint_bounds` derives from
courtyard graphics + pad extents) does not enclose L1's real pad copper.
**Measured directly: it does, for all 169 real components, with zero
exceptions**, both a weak point-only check and a strong extent-aware check
(pad half-size included). The actual defect is one line downstream:
`CpSatPlacementResult.to_rotations_dict()` (`_encoder_solve.py`) filtered
out any component whose *solved* rotation index was `0` with `if idx`,
treating "solved to absolute 0 degrees" as indistinguishable from "no
rotation data at all". The write-back consumers
(`_apply_placements_to_pcb`, `write_placements_to_pcb`) do NOT treat those
two cases identically: a ref *absent* from the rotations dict keeps its
**pre-solve board angle**; an *explicit* `0.0` writes **absolute rotation
0**. For a non-square component whose pre-solve angle was non-zero, the
old filter silently kept the stale angle while the solver's box
(`x_size`/`y_size`, tied to the solved rotation index via an `AddElement`
swap table) had been sized for the *solved* 0-degree orientation -- the box
the solver verified no longer matched the footprint actually written to
the board. Measured on two independent real-board solves: **30/169
(17.8%)** and **36/169 (21.3%)** components hit this exact mismatch
(solved rotation index 0, non-zero pre-solve board angle, non-square
footprint) in a single solve; writing through the old filtered dict
produced real, physical containment violations (4 and 2 respectively);
writing through the fixed, dense dict produced zero both times.

## 1. Independent verification of the reported defect's class

`check_board_containment.py`'s own docstring and
`docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md` (an
isolation-barrier-constrained Pumpkin solve on the reconciled 168-component
board) independently report the same symptom: **"L1 pad 3 fully outside
the outline near the top edge" + "R60 pad 1 straddling"**, 2 violations
out of 527 checked pads, attributed by that doc's own author to "a
box-approximation CP-SAT model's edge-margin constraint" -- i.e. assumed to
be a `Component.bounds` looseness. This doc re-derives the mechanism from
first principles rather than accepting that attribution.

## 2. `Component.bounds` derivation is sound -- measured, not assumed

`_calculate_footprint_bounds`/`calculate_footprint_bounds`
(`packages/temper-io-types/src/footprint.rs`,
`packages/temper-design-bundle/src/parse_engine.rs:1456`) computes, for
each component, `center_offset = (mean of pad x/y CENTERS)` and then
`half_extent = max(|extent_min - center_offset|, |extent_max -
center_offset|)` over the union of courtyard/fab graphics and pad copper
extents, `bounds = 2 * half_extent`. This construction is symmetric by
definition: whatever `center_offset` is, the returned box always contains
`[extent_min, extent_max]`, because `half_extent >= |extent_min -
center_offset|` and `half_extent >= |extent_max - center_offset|` by the
`max()`. This is a general property, not board-specific.

Measured directly against `pcb/temper.kicad_pcb` (169 components, walked
via `temper_placer.io.kicad_parser.parse_kicad_pcb`), in the LOCAL
(unrotated) frame every `Pin.position`/`Component.bounds` pair is expressed
in:

- **Point-only check** (pad centers only, P9-style):
  `abs(px) > w/2` / `abs(py) > h/2` -- **0/169 components violate.**
- **Extent-aware check** (pad half-size included, P10-style, the stronger
  test): `abs(px) + pad_w/2 > w/2` / `abs(py) + pad_h/2 > h/2` -- **0/169
  components violate.**

L1's specific numbers, matching the task's report exactly: `bounds =
(51.0, 28.0)` mm, `_center_offset_y = 11.5` (the mean of pad-center y
positions 0 and 23), courtyard `fp_rect (-25.5 -2.5)-(25.5 25.5)` -- the
symmetric construction gives `half_width = max(25.5, 25.5) = 25.5`,
`half_height = max(|-2.5-11.5|, |25.5-11.5|) = max(14, 14) = 14`, i.e.
`(51, 28)`, and L1's real pad copper (all 4 pads, radius 1.7mm) sits
strictly inside `[-25.5,25.5] x [-2.5,25.5]` in the local frame. No
violation exists at this level for L1 or any other component.

This is locked in as a regression test:
`tests/placer/cp_sat/test_geometry_constraints_pbt.py::test_real_board_bounds_enclose_pads_extent_aware`.

## 3. The real mechanism: solved rotation index 0 dropped from the write-back dict

`CpSatPlacementResult.to_rotations_dict()` (`_encoder_solve.py`, pre-fix):

```python
return {ref: idx * 90.0 for ref, idx in self.rotations.items() if idx}
```

`self.rotations` is dense (every solved component gets an entry, 0-3,
populated by `CpSatModel.solve()`). The `if idx` filter drops every entry
whose value is `0` -- a **falsy-filter bug**: Python's `if idx` cannot
distinguish "the solver decided this component belongs at absolute
rotation 0" from "there is no rotation information for this ref at all".

The docstring justified this as safe: *"absence and explicit-zero are
handled identically by [the] consumer"* (`_apply_placements_to_pcb`).
**That claim is false, checked directly against the consumer's own code**
(`router_v6/_adapter_convert.py`):

```python
target_angle = rotations.get(ref) if rotations else None
...
if target_angle is None:
    # No solved rotation for this ref: preserve its existing angle exactly
    ...
else:
    new_angle = target_angle % 360.0   # 0.0 here writes an EXPLICIT 0-degree angle
    ...
```

`0.0 is not None` -- an explicit `0.0` writes absolute rotation 0 (and
reorients every pad to match); a *missing* ref preserves the footprint's
**pre-solve board angle**, unconditionally. `io/_write_board.py`'s
`write_placements_to_pcb` has the identical branch. So dropping a genuine
rotation-index-0 decision from the dict is not equivalent to declaring it
explicitly -- it silently substitutes a *different, stale* angle.

The self-consistency round-trip oracle
(`validation/placement_roundtrip.py::_check_footprint`) cannot catch this:
its own "expected angle" computation uses the exact same fallback --
`rotations.get(ref, _template_fp_angle(template))` -- so a dropped
rotation-index-0 decision and the writer's stale-angle fallback agree with
each other by construction. The oracle was structurally blind to this
defect class before this fix (comment fixed in this same PR; behavior of
the oracle itself is intentionally left generic -- see its updated
comment).

**The production `temper optimize` CLI never had this bug.** It builds its
own dense mapping directly (`cli/__init__.py`):

```python
rotation=cp_result.rotations.get(ref, 0) * 90.0
```

for *every* solved ref -- always explicit, never the sparse
`to_rotations_dict()` shape. The bug's blast radius was
`to_rotations_dict()`'s callers: `tests/placer/cp_sat/test_regression_drc.py`
(the golden-board fixture DRC regression test) and
`tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py` (which
duplicated the identical `if idx` pattern inline rather than calling
`to_rotations_dict()`), plus any evidence/spike script that copied that
test's pattern (e.g. the isolation-barrier Pumpkin placement doc cited in
Sec 1, which reused this exact test's `_build_constraints`/write-back
shape).

## 4. Measured scale: not one component, a real fraction of the board

Two independent solves of the real 169-component board
(`pcb/temper.kicad_pcb`, unmodified, read-only), same courtyard + netclass
constraint set `test_golden_board_pumpkin_real_board.py` builds, solved
with the pinned `pumpkin_engine`:

| Run | Components solved to rot=0 with non-zero pre-solve angle | Of those, non-square (bounds-swap matters) | Real `check_board_containment.py` violations, pre-fix write | Post-fix write |
|---|---:|---:|---:|---:|
| Natural (unconstrained) solve | 30 / 169 (17.8%) | 30 / 30 | 4 (U27 x3 pads, R31) | 0 |
| L1 forced to rot=0 via a `fixed_rotation` constraint | 36 / 169 (21.3%) | 36 / 36 | 2 (R20, U27) | 0 |

Every affected component in both runs was non-square (`w0 != h0`), i.e.
the rotation mismatch is geometrically consequential for every one of
them, not just the handful that happened to sit close enough to the board
edge to register as an outline violation. The visible
`check_board_containment.py` failures are the tip of a much larger
correctness gap: for every affected component NOT near an edge, its real
pad copper was still displaced relative to the box every
`SeparatedConstraint` (courtyard clearance, netclass separation, domain
clearance -- see `domain_clearance.py`'s soundness proof, which explicitly
assumes "box contains real copper at the placed position") verified safe.
The soundness proof was correct about the box; the defect was that the
written board did not consistently correspond to that box.

Both tables' natural/forced solves are reproducible; the forcing
constraint (`{"type": "fixed_rotation", "component": "L1", "rot": 0}`) was
used only to make L1 itself exhibit the defect deterministically for
inspection -- the natural, unconstrained solve already hits the same
mechanism on 30 other components without any forcing.

## 5. The fix

`_encoder_solve.py::CpSatPlacementResult.to_rotations_dict()` is now dense
-- every solved ref gets an entry, including rotation index 0:

```python
return {ref: idx * 90.0 for ref, idx in self.rotations.items()}
```

`test_golden_board_pumpkin_real_board.py`'s inline duplicate of the same
`if idx` pattern is fixed identically. Stale comments in
`validation/placement_roundtrip.py`, its Rust-differential Python oracle,
and `tests/router_v6/test_adapter.py` (which cited the old sparse
contract as the reason for `_apply_placements_to_pcb`'s own "missing ref =
keep old angle" fallback) are corrected to describe the fallback as a
generic default for genuinely-absent data, not a consequence of
`to_rotations_dict()`'s shape.

## 6. Why this fix cannot change feasibility or move any component

`to_rotations_dict()` is a pure, read-only transform of
`self.rotations` -- a dict already fully populated by the time
`CpSatModel.solve()` returns. It runs strictly **after** the solve: it
touches no constraint, no variable, no objective, and reads no board
geometry. Consequently:

- **The solve itself is byte-identical** with or without this fix -- same
  constraints, same solver, same positions, same rotation indices chosen.
  Isolation-barrier feasibility (all 8 isolators, PD2/8.0mm bar) is
  unaffected because the fix sits entirely downstream of
  `add_isolation_barrier_to_model`.
- **No component's POSITION changes.** The fix only affects the `rotation`
  field of the `PlacementUpdate` a caller builds from
  `to_rotations_dict()`'s output, for the specific subset of refs whose
  solved rotation index is `0` and whose pre-solve board angle differs
  from 0 -- for those, the written angle is corrected from the stale
  pre-solve value to the solved absolute-0 value (with pads re-oriented to
  match, via the writers' existing `_reorient_pads`/
  `_reorient_pads_in_footprint_block` delta logic). Every other component
  (a solved rotation index of 1/2/3, or a pre-solve angle that was already
  0) is written identically before and after this fix.
- Measured (Sec 4): the natural real-board solve moved **zero**
  positions and changed the **written angle** of exactly the 30
  mismatched refs -- a targeted correction, not a broad placement change.

## 7. Detectability

`tests/placer/cp_sat/test_geometry_constraints_pbt.py` gained two new
tests:

- `test_real_board_bounds_enclose_pads_extent_aware` (P11): walks all 169
  real components, asserts `Component.bounds` (local frame) encloses
  every pin's full copper extent. Locks in Sec 2's measurement as a
  regression guard on the derivation itself.
- `test_rotation_index_zero_must_not_be_dropped_from_write` (P12): a
  synthetic non-square, pre-rotated (90deg) footprint solved to absolute
  rotation 0. Directly demonstrates the mechanism: writing through the
  pre-fix `if idx`-filtered pattern (kept inline in the test itself, so
  the regression guard survives even if the buggy pattern is fully
  deleted from source) must fail (asserted); writing through
  `CpSatPlacementResult.to_rotations_dict()` must pass (asserted). Verified
  directly: reverting `to_rotations_dict()` to the pre-fix `if idx` form
  and re-running this test fails with `pad 1 bounds
  (99.000,107.000)-(101.000,109.000) outside the solved box
  (90.000,97.000)-(110.000,103.000)` -- a guard that has actually been
  seen to fail, not merely asserted to.
