---
title: Transform-algebra Exhaustiveness - Plan
type: feat
date: 2026-08-02
topic: transform-algebra-exhaustiveness
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R23)
---

# Transform-algebra Exhaustiveness - Plan

## Goal Capsule

**Objective:** Rotation transform composition is verified exhaustively over the finite angle set the solver emits, replacing the spot coverage of a convention that has already bitten twice.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none.

---

## Product Contract

### Summary

The rotation convention (KiCad R(-theta)) is verified as an algebra, not as spot cases: every composition pair over the solver's finite angle set, every inverse round-trip, every one-hot encoding round-trip, plus property tests at arbitrary angles and a pcbnew-oracle cross-check at non-90-degree angles. Both sanctioned implementations — Python `kicad_transform` and Rust `transform.rs` — carry the same exhaustive suite, kept in lockstep by the existing differential test.

### Problem Frame

The R(-theta) convention was re-implemented wrongly in 12 places, then a second sweep found 12 more sites, and a writer dropped solved rotation entirely. The convention's tests parametrize over a handful of angles — spot coverage that the quadrant-invariance lesson proved insufficient: every board so far uses 90-degree multiples, where R(+theta) and R(-theta) coincide on origin-symmetric geometry, so the wrong sign shipped undetected until a 37-degree oracle test existed. Exhaustive verification over the finite angle set, plus a non-90-degree oracle cross-check, closes the class: a sign flip or composition error fails a closed-form law or a convention-anchored expected value, not a lucky future board.

### Requirements

- R23. **Transform-algebra exhaustiveness** (Formal / Geometry / P1): rotation/mirror transform composition is verified exhaustively over the finite angle set (enumerated or property-tested) — replacing the spot coverage of a convention that has already bitten twice.
- **Success signal:** every composition pair, inverse round-trip, and encoding round-trip over the finite angle set is asserted, and any single violation (sign flip, dropped rotation, composition error) fails the suite.

### Key Technical Decisions

- KTD1. **Exhaustive enumeration is the primary mechanism; property testing covers the general claim.** The solver's angle set is four values, so all 16 composition pairs, 4 inverse round-trips, and 4 one-hot round-trips are enumerated exactly. Rationale: at this domain size enumeration is cheaper and stronger than sampling.
- KTD2. **The algebraic oracle is the closed-form matrix law, not a second numerical implementation.** Composition asserts R(-θ1)·R(-θ2) = R(-(θ1+θ2)) mod 360 and inverse asserts R(θ)^T = R(-θ); convention-anchored expected outputs (e.g. `rotate_local_to_world(5, 0, 90) = (0, -5)`) pin the sign. Rationale: a second numerical implementation could share the same sign bug; closed forms and anchored values cannot.
- KTD3. **Both sanctioned implementations carry the suite: Python `kicad_transform` and Rust `transform.rs`.** The Rust side covers `transform_pin_position`/`transform_pin_positions` and the rotation-matrix family; the differential test keeps the two in lockstep. Rationale: the repo maintains two sanctioned copies (documented in `kicad_transform.py`) and both must satisfy the same algebra.
- KTD4. **A non-90-degree pcbnew-oracle cross-check anchors the general convention claim.** Reuse the `scripts/kicad_pad_rotation_oracle.py` plumbing at angles like 37 and 45 degrees. Rationale: the 90-degree-multiple algebra alone cannot distinguish R(+theta) from R(-theta) on symmetric inputs — the exact masking the second sweep documented; only a real-KiCad anchor at a non-multiple angle does.
- KTD5. **Mirror is recorded as a non-applicability note, not a skipped suite.** No standalone mirror transform kernel exists in `temper_placer.geometry` (grep-verified); bottom-side placement is side-tagged, not mirror-transformed. Rationale: R23 names rotation/mirror composition; the rotation half is exhaustive here and the mirror half is documented as not-applicable-until-a-kernel-exists rather than silently omitted.

### Assumptions

- The "finite angle set" is the solver's {0, 90, 180, 270} (`ROTATION_ANGLES_DEG`/`ROTATION_ANGLES_RAD` in `transform.rs`), the only set the CP-SAT solver emits today.
- The pcbnew oracle (`scripts/kicad_pad_rotation_oracle.py`) remains available for the non-90-degree cross-check; its absence degrades U3 to SKIPPED-with-cause, never PASS.
- One-hot encoding/decoding round-trips are in scope because they are the solver's rotation-encoding surface (`rotation_index_to_onehot`, `rotation_degrees_to_onehot`, `onehot_to_rotation_degrees`).

---

## Implementation Units

### U1. Exhaustive Python algebra suite

**Goal:** Enumerated and property-based verification of `kicad_transform`'s rotation algebra over the finite angle set.

**Requirements:** R23

**Dependencies:** none

**Files:**
- Modify: `packages/temper-placer/tests/geometry/test_kicad_transform.py`
- New: `packages/temper-placer/tests/geometry/test_kicad_transform_algebra.py`

**Approach:**
1. Enumerate all 16 composition pairs over {0, 90, 180, 270}: assert `rotate_local_to_world` composed with itself equals the closed-form rotation by the sum mod 360, applied to several non-symmetric offsets.
2. Assert inverse round-trips for every angle in the set: `rotate_world_to_local(rotate_local_to_world(p, θ), θ) == p` exactly at 90-degree multiples (closed-form integer entries) and within epsilon generally.
3. Assert convention-anchored expected values at every angle in the set for a fixed offset, extending the existing ground-truth parametrization (which covers one offset at four angles) to several offsets including asymmetric ones.
4. Assert one-hot round-trips over the finite set where the encoding surface is exercised.
5. Add property tests at random non-multiple angles for the general composition and inverse laws.

**Patterns to follow:** the existing parametrized ground-truth tests in `test_kicad_transform.py`; the closed-form expectations at 90-degree multiples in `transform.rs`'s unit tests; the exact-equality-at-multiples discipline.

**Test scenarios:**
1. Composition closure — all 16 pairs: for each (θ1, θ2) in the set and each of several offsets, `R(-θ1)(R(-θ2)(p))` equals the closed-form `R(-(θ1+θ2 mod 360))(p)` within epsilon.
2. Inverse round-trip — all 4 angles: `rotate_world_to_local` inverts `rotate_local_to_world` exactly at 90-degree multiples and within epsilon at 0.
3. Convention anchor — all 4 angles, asymmetric offset (0.5, 0.3): output matches the pcbnew-verified closed form, so a sign flip fails.
4. One-hot round-trip — all 4 angles: degree → one-hot → degree is the identity on the finite set.
5. Property — random angles in [0, 360): composition and inverse laws hold within epsilon.
6. Falsifier — convention flip: substituting R(+theta) into the suite fails the convention-anchor and composition scenarios at 90 and 270 degrees.

**Verification:** The suite passes on the current implementation; the convention-flip falsifier fails it; every scenario names its inputs and expected outcome.

### U2. Exhaustive Rust algebra suite and differential pin

**Goal:** The same algebra holds for the Rust `transform.rs` implementation, and the differential keeps the two sanctioned copies in lockstep over the exhaustive cases.

**Requirements:** R23

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-geometry/src/transform.rs` (test module)
- Modify: `packages/temper-placer/tests/geometry/test_kicad_transform_rust_differential.py`

**Approach:**
1. Add Rust tests for the composition and inverse laws over `ROTATION_ANGLES_RAD`, mirroring U1's enumeration, on `rotate_point` and the `transform_pin_position` family.
2. Assert `transform_pin_position`'s convention-anchored values at every angle in the set (its existing single 90-degree case becomes the seed of the enumeration).
3. Extend the differential suite to run the exhaustive angle set, not just spot angles, comparing Python `kicad_transform` and Rust `transform_pin_position` per (angle, offset) pair.
4. Keep one-hot round-trip assertions for the Rust encoding functions.

**Patterns to follow:** `transform.rs`'s existing test module conventions (epsilon asserts, closed-form expectations); `test_kicad_transform_rust_differential.py`'s lockstep pinning; Rust best practices — borrow over clone, no `unwrap` outside tests, and the `catch_unwind` boundary convention at pyo3 surfaces.

**Test scenarios:**
1. Rust composition closure — all 16 pairs on `rotate_point`: closed-form law holds within epsilon.
2. Rust inverse round-trip — all 4 angles on `rotate_point`: exact at multiples.
3. Rust convention anchor — `transform_pin_position` at all 4 angles with an asymmetric offset: matches the pcbnew-verified closed form.
4. Differential — exhaustive angle set: Python and Rust produce identical outputs for every (angle, offset) pair in the enumeration.
5. One-hot round-trip — Rust `rotation_degrees_to_onehot` → `onehot_to_rotation_degrees` is the identity on the finite set.
6. Falsifier — Rust sign flip: swapping `transform_pin_position` to R(+theta) fails the anchor and differential scenarios.

**Verification:** `cargo test` in `packages/temper-geometry` passes; the differential suite passes; the sign-flip falsifier fails both.

### U3. Non-90-degree oracle cross-check

**Goal:** The general convention claim (the law the exhaustive 90-degree suite alone cannot distinguish) is anchored against real KiCad at non-multiple angles.

**Requirements:** R23

**Dependencies:** U1

**Files:**
- New: `packages/temper-placer/tests/geometry/test_transform_algebra_pcbnew_oracle.py`
- Reuse: `scripts/kicad_pad_rotation_oracle.py` plumbing

**Approach:**
1. Reuse the pcbnew-oracle batch plumbing already used by `test_rotation_convention_remaining_sites_oracle.py` and `test_rotation_convention_oracle.py`.
2. At angles like 37 and 45 degrees, compare `rotate_local_to_world`'s output against pcbnew's actual placement for the same local offset and origin.
3. Assert the composition law at a non-multiple angle against the oracle result, so the general law is externally anchored, not just internally consistent.
4. Degrade to SKIPPED-with-cause when the pcbnew oracle is unavailable.

**Patterns to follow:** the oracle-batch construction and tolerance (5e-06) in `test_rotation_convention_remaining_sites_oracle.py`; the falsifier-proof pattern (revert → fail) documented in the rotation-sign evidence doc.

**Test scenarios:**
1. Convention anchor at 37 degrees, offset (0.5, 0.3) about (12.0, -4.0): `rotate_local_to_world` matches pcbnew within the oracle tolerance.
2. Convention anchor at 45 degrees: same match.
3. Composition law at a non-multiple angle: the composed result matches the oracle's single-step rotation by the summed angle.
4. Falsifier — sign flip at 37 degrees: R(+theta) output (e.g. (12.218773, -3.459502) for the documented case) fails the oracle comparison.
5. Oracle unavailable: the suite reports SKIPPED-with-cause and does not emit PASS.

**Verification:** The oracle suite passes; the sign-flip falsifier fails; SKIPPED-with-cause is the only non-failing outcome when the oracle is absent.

---

## Verification Contract

- `uv run pytest packages/temper-placer/tests/geometry/test_kicad_transform_algebra.py` — exhaustive Python algebra.
- `cargo test` in `packages/temper-geometry` — exhaustive Rust algebra.
- `uv run pytest packages/temper-placer/tests/geometry/test_kicad_transform_rust_differential.py` — Python/Rust lockstep over the exhaustive set.
- `uv run pytest packages/temper-placer/tests/geometry/test_transform_algebra_pcbnew_oracle.py` — non-90-degree oracle cross-check.
- `uv run python scripts/check_no_raw_rotation_trig.py` — the guarded-file lint stays green (this plan adds no raw trig).
- `make extensions-check` — the Rust test changes do not alter crate sources; the gate stays green.

---

## Definition of Done

- The exhaustive Python and Rust suites cover all composition pairs, inverse round-trips, and one-hot round-trips over the finite angle set.
- The differential pins Python and Rust over the exhaustive set.
- The non-90-degree pcbnew-oracle cross-check anchors the general convention claim.
- Every falsifier (convention flip, sign flip) demonstrably fails its suite.
- The mirror half is recorded as a non-applicability note, not a silent omission.

---

## Scope Boundaries

**In scope:** rotation composition over the solver's finite angle set, in both sanctioned implementations, plus the general-convention oracle anchor.

**Deferred to Follow-Up Work**

- Mirror transform composition — no mirror kernel exists today (Assumption KTD5); the note records the position until one lands.
- Extending the exhaustive set to finer angle grids the solver may one day emit — the property tests already cover arbitrary angles; a new finite set would extend the enumeration.
- The `scripts/check_no_raw_rotation_trig.py` guarded-file list — unchanged; this plan adds tests, not call sites.

---

## Sources / Research

- `packages/temper-placer/src/temper_placer/geometry/kicad_transform.py` — the Python sanctioned implementation.
- `packages/temper-geometry/src/transform.rs` — the Rust sanctioned implementation and its existing unit tests.
- `packages/temper-placer/tests/geometry/test_kicad_transform.py` — the spot coverage this plan replaces with enumeration.
- `packages/temper-placer/tests/geometry/test_kicad_transform_rust_differential.py` — the lockstep differential to extend.
- `docs/evidence/2026-07-30-rotation-sign-remaining-sites.md` — the quadrant-invariance masking lesson and the oracle-batch precedent.
- `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md` — the ground-truth experiment establishing R(-theta).
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the origin (R23).
