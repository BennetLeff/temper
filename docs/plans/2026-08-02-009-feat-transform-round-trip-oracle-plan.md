---
title: Transform Round-trip Oracle - Plan
type: feat
date: 2026-08-02
topic: transform-round-trip-oracle
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R12)
---

# Transform Round-trip Oracle - Plan

## Goal Capsule

**Objective:** Every placement write is re-parsed and its pad geometry compared against the solver's model, so the rotation-convention class — sign error across call sites, un-applied solved rotation — cannot ship.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none.

---

## Product Contract

### Summary

A round-trip oracle that takes a solver placement record plus the written `.kicad_pcb`, re-parses the file, extracts per-footprint and per-pad geometry, and compares it against the geometry the solver's model implies under the sanctioned `kicad_transform` convention. The oracle runs after every production write path and fails on any mismatch beyond canonicalization and float epsilon.

### Problem Frame

`_apply_placements_to_pcb` dropped solved rotation unconditionally for its entire existence — its regex reused the footprint's old angle token and the function had no rotation parameter at all. A second, entangled defect meant its callers never converted CP-SAT's box-center position back to the footprint's KiCad anchor, so the written geometry never matched the solver's model for asymmetric-center components. Both defects shipped because no check ever re-parsed a written board and compared it against the model; DRC-count regressions surfaced only when a future PR happened to introduce non-90°-multiple rotation choices. The round-trip oracle makes write-vs-model agreement a direct, immediate assertion.

### Requirements

- R12. **Transform round-trip oracle** (Oracle / Geometry / P1): every placement write is re-parsed and pad geometry compared against the solver's model — the rotation-convention class (sign error across call sites, un-applied solved rotation) cannot ship.
- **Success signal:** a written board whose footprint angles or pad geometry differ from the solver's model fails the round-trip oracle immediately after the write.

### Key Technical Decisions

- KTD1. **The reference model is the solver's placement record transformed by `kicad_transform`'s sanctioned convention.** Expected footprint positions and pad centers are computed from (positions, rotations, parsed template pad offsets) via `place_local_to_world`. Rationale: the oracle tests the writer against the convention, while the convention's own correctness is pinned separately by the pcbnew-oracle tests — the two claims stay independent.
- KTD2. **Comparison is exact modulo canonicalization, not tolerance-banded.** Angles are normalized mod 360, zero angles map to the omitted-token form, and float comparisons use epsilon. Rationale: a dropped rotation or sign flip is an exact, structural difference; a tolerance band would let the class this idea exists for hide inside the band.
- KTD3. **Every production write path is covered.** `write_placements_to_pcb` (the CLI writer), `_apply_placements_to_pcb` (the `route_pcb` path), and `state_to_placements` each get oracle coverage. Rationale: the two writers have different geometry contracts (center-offset subtraction) and different incident histories; one covered path does not vouch for the other.
- KTD4. **The oracle consumes the written file, not an in-memory representation.** The board is re-parsed from disk with `parse_kicad_pcb_v6`. Rationale: an in-memory compare would share the writer's own conventions and could not detect serialization loss.

### Assumptions

- The solver's model is represented by a placement record of per-component (position, rotation in degrees) plus the parsed template's pad offsets and center-offset attributes; `CpSatPlacementResult.to_rotations_dict()` is the canonical rotation source for the CP-SAT path.
- Pad local `(x, y)` offsets are not rewritten by the writers (KiCad rotates them at load time); the oracle therefore compares pad world positions and pad body angles, not pad local offsets.
- The pcbnew-oracle tests (`scripts/kicad_pad_rotation_oracle.py` plumbing) remain the authority for the convention's correctness at arbitrary angles; this plan's oracle assumes the convention and checks the writer against it.

---

## Implementation Units

### U1. Round-trip comparator

**Goal:** A function that takes a solver placement record and a written board path, re-parses the board, extracts per-footprint and per-pad geometry, and compares it against the expected model with canonicalization.

**Requirements:** R12

**Dependencies:** none

**Files:**
- New: `packages/temper-placer/src/temper_placer/validation/placement_roundtrip.py`
- New: `packages/temper-placer/tests/validation/test_placement_roundtrip.py`

**Approach:**
1. Build a comparator that accepts (positions, rotations, template components, written board path).
2. Re-parse the written board with `parse_kicad_pcb_v6` and extract per-footprint `(at, angle)` and per-pad `(world position, body angle)`.
3. Compute expected geometry from the template: pad world position via `kicad_transform.place_local_to_world`, pad body angle as `new_fp_angle + intrinsic`, matching `_reorient_pads`' own convention.
4. Canonicalize both sides (angle mod 360, zero-angle omission, epsilon float compare) and report a per-component mismatch list.

**Patterns to follow:** `io/_parse_modules.py` parsing conventions; `io/_write_board.py`'s center-offset subtraction and `_reorient_pads`' intrinsic-angle math; `kicad_transform.place_local_to_world` as the single sanctioned rotation formula.

**Test scenarios:**
1. Identity write (all rotations zero): re-parsed geometry equals the model exactly.
2. Rotation 180 on a symmetric part: footprint angle and every pad body angle shift by 180; oracle reports no mismatch.
3. Rotation 90 on a part with an intrinsic pad angle (pad at 90 within a footprint rotated to 180): expected pad angle is 180, not 90; oracle matches the written value.
4. Rotation normalizing to zero: a 360-equivalent angle writes with the angle token omitted; canonicalization makes the oracle PASS.
5. Center-offset component (asymmetric pad set, e.g. a TO-247-style three-pad part): expected anchor is model position minus the rotated center offset; oracle matches the written anchor.
6. Falsifier — dropped rotation: a written board with the solver's rotation not applied yields a mismatch on footprint angle and pad bodies; the oracle FAILS.
7. Falsifier — sign flip: a board written with R(+theta) instead of R(-theta) yields a mismatch at non-symmetric offsets; the oracle FAILS.

**Verification:** The unit suite passes, including the two falsifier cases that must FAIL the oracle; every public function in the new module is exercised (no new `.coverage-allowlist` entries).

### U2. Per-writer oracle coverage

**Goal:** Each production write path round-trips through the comparator, with the incident-class falsifiers asserted to fail.

**Requirements:** R12

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/tests/io/test_kicad_writer.py` (`write_placements_to_pcb`, `state_to_placements`)
- Modify: `packages/temper-placer/tests/router_v6/test_adapter.py` (`_apply_placements_to_pcb`)

**Approach:**
1. For `write_placements_to_pcb`: write a placement with mixed rotations and center-offset components to a scratch board, re-parse, and run the comparator; assert PASS.
2. For `_apply_placements_to_pcb`: exercise the `rotations=` parameter introduced by the placement-writer-rotation fix; assert PASS when rotations are supplied and exact angle preservation when `rotations=None`.
3. For `state_to_placements`: write a full state and round-trip.
4. Add falsifier scenarios that reproduce the historical classes against each writer: rotation dropped, pad bodies not re-oriented, center offset not subtracted.

**Patterns to follow:** `TestApplyPlacementsToPcbRotation`'s seven cases in `test_adapter.py`; `_write_board.py`'s docstring contract for bounding-box-center coordinates.

**Test scenarios:**
1. `write_placements_to_pcb` with mixed {0, 90, 180, 270} rotations on asymmetric parts: oracle PASS after re-parse.
2. `write_placements_to_pcb` with a center-offset component: written anchor differs from model position by the rotated offset, and the oracle (which subtracts it) PASSES.
3. `_apply_placements_to_pcb` with `rotations=result.to_rotations_dict()`: oracle PASS.
4. `_apply_placements_to_pcb` with `rotations=None`: every footprint angle is byte-identical to the template; oracle PASS (no rotation requested).
5. Falsifier — rotation dropped in `write_placements_to_pcb` (mutant that skips the angle update): oracle FAILS on footprint angle.
6. Falsifier — pad bodies not re-oriented (pre-#412 class): oracle FAILS on pad body angles.
7. Falsifier — center offset not subtracted (pre-#460 position-frame class): oracle FAILS on footprint position for the asymmetric component.
8. Falsifier — `_apply_placements_to_pcb` called without rotations on a solve that chose non-zero rotations: oracle FAILS (the exact 2026-07-30 incident class).

**Verification:** All per-writer suites pass; the four falsifier scenarios demonstrably FAIL the oracle; the existing writer and adapter suites stay green.

### U3. After-write oracle wiring

**Goal:** The comparator runs automatically after the production write paths in test and CLI flows, so write-vs-model divergence is caught at the write site.

**Requirements:** R12

**Dependencies:** U1, U2

**Files:**
- Modify: `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` (golden-board writes)
- Modify: `packages/temper-placer/src/temper_placer/cli/` (the `temper optimize` writer path)

**Approach:**
1. Add an oracle assertion after each golden-board write in the regression tests: re-parse the written artifact and assert PASS before any DRC measurement.
2. Invoke the comparator from the CLI writer path after `write_placements_to_pcb` completes, failing the command on mismatch.
3. Keep the comparator call explicit in the `route_pcb` chain's tests so the place-route loop's internal gate and final write are checked against the same model.

**Patterns to follow:** `test_regression_drc.py`'s golden-board flow; `_loop_routing.py`'s gate-check pattern; the writer's existing center-offset contract.

**Test scenarios:**
1. Integration: the golden-board regression test writes, re-parses, and reports PASS on the current committed state.
2. Integration: the CLI writer runs a solve and the post-write oracle assertion holds.
3. Falsifier: substituting the rotation-drop mutant board into the golden-board flow fails the regression test at the oracle assertion, before DRC counts are compared.
4. Regression: the golden-board test's existing DRC thresholds are unchanged by the added assertion.

**Verification:** Golden-board and CLI tests pass with the oracle in place; the falsifier substitution fails at the oracle assertion; `scripts/import_linter_gate.py` passes.

---

## Verification Contract

- `uv run pytest packages/temper-placer/tests/validation/test_placement_roundtrip.py` — comparator suite.
- `uv run pytest packages/temper-placer/tests/io/test_kicad_writer.py` — writer round-trips.
- `uv run pytest packages/temper-placer/tests/router_v6/test_adapter.py` — adapter writer round-trips.
- `uv run pytest packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` — golden-board oracle assertion.
- `uv run python scripts/import_linter_gate.py` — import boundary check.
- Coverage gate: new public functions in `placement_roundtrip.py` are exercised by the unit suite; no new `.coverage-allowlist` entries.

---

## Definition of Done

- The comparator exists, is canonicalized, and is unit-tested.
- All three production write paths round-trip with PASS on current behavior.
- The four incident-class falsifiers demonstrably FAIL the oracle.
- The oracle runs after golden-board writes and from the CLI writer.
- No new `.coverage-allowlist` entries; import linter green.

---

## Scope Boundaries

**In scope:** footprint position/angle and pad world-position/body-angle agreement for the temper board's write paths.

**Deferred to Follow-Up Work**

- The `route_pcb` position-frame conversion (center-offset subtraction) being wired into `route_pcb` callers — the oracle detects the divergence; the fix is a separate architectural change per the origin evidence doc's R22 triage.
- Round-tripping silkscreen, courtyard, and zone geometry — this oracle covers the transform classes the idea names.
- Cross-repo round-trips for corpus boards beyond the temper board.

---

## Sources / Research

- `docs/evidence/2026-07-30-placement-writer-rotation.md` — the incident this oracle exists for (seed).
- `docs/evidence/2026-07-30-rotation-sign-remaining-sites.md` — the sign-error sweep across call sites.
- `packages/temper-placer/src/temper_placer/geometry/kicad_transform.py` — the sanctioned convention the oracle checks writers against.
- `packages/temper-placer/src/temper_placer/io/_write_board.py` — `write_placements_to_pcb`, `_reorient_pads`, `state_to_placements`.
- `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py` — `_apply_placements_to_pcb`.
- `packages/temper-placer/tests/router_v6/test_adapter.py` — the `TestApplyPlacementsToPcbRotation` precedent.
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the origin (R12).
