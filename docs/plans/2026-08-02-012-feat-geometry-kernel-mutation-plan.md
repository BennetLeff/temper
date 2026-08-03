---
title: Geometry-Kernel & Writer Mutation - Plan
type: feat
date: 2026-08-02
topic: geometry-kernel-mutation
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R34, R35)
---

# Geometry-Kernel & Writer Mutation - Plan

## Goal Capsule

**Objective:** Geometry kernels (rotation, bbox, pad offsets) are mutated and the oracle differential must catch each mutation; transform errors are likewise injected into the placement writers and the round-trip oracle must fail. Both halves carry a proven kill set that doubles as a maintenance canary — compute kernels and the write path are held to the same proven-bite standard.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none. The writer family depends on the round-trip oracle (R12, plan 2026-08-02-009) and on this plan's own harness; the center-offset class waits on the deferred R22 fix as a documented EQUIVALENT-with-reason exclusion. All are named as unit dependencies or classifications, not open questions.

---

## Product Contract

### Summary

A mutation harness applies hand-curated defect mutants — the repo's own incident classes — to the Rust geometry kernels, rebuilds the crate, and runs the owning differential suite as the kill oracle. The same harness carries a writer family that applies the transform-error classes to the two placement writers (`write_placements_to_pcb` and `_apply_placements_to_pcb`) and runs the R12 round-trip oracle (plan 2026-08-02-009) as its kill oracle. Every mutant must be killed (the differential, or the round-trip oracle, fails) or be explicitly recorded as behaviorally equivalent with a documented reason. A mutant that escapes is a first-class finding: the owning suite gains a discriminating test. The harness runs in CI as a canary for the Rust migration and for the write path.

This is the merged R34 + R35 artifact: the writer-error injection catalog (R35, formerly plan 2026-08-02-013) is folded in as a writer family of the kernel mutation harness (R34, formerly plan 2026-08-02-012), per the merge map in `docs/evidence/2026-08-02-validation-portfolio-review.md`.

### Problem Frame

The migration's differential suites pin Rust kernels bit-exactly against verbatim Python oracles, and they are strong — but nothing proves they would catch a regression. A mutation the differential silently tolerates (a sign flip masked by symmetric inputs, a dropped term that happens to stay within tested bounds) is exactly the class that has bitten twice in this repo: the rotation sign error survived quadrant-only tests, and the courtyard detector's silent no-op survived until real DRC contradicted it.

The write path is the least-guarded transform surface in the repo: `_apply_placements_to_pcb` dropped solved rotation for its entire existence, and `write_placements_to_pcb`'s pre-#412 pad-body omission caused 60 intra-component copper shorts. The round-trip oracle (R12) closes the detection gap; without injection, nothing proves the oracle actually bites. Folded into the same harness, the two sides complete the loop: the error classes are re-injected and each kill oracle must fail on them — compute kernels and the write path are held to the same standard, and the mutation suite doubles as a maintenance canary.

### Requirements

- R34. **Geometry-kernel mutation testing** (Injection / Geometry / P2): geometry kernels (rotation, bbox, pad offsets) are mutated and the oracle differential must catch each mutation — the mutation suite doubles as a maintenance canary for the Rust migration.
- **Success signal:** every mutant in the catalog is killed by the oracle differential (or recorded as behaviorally equivalent with a documented reason), and the harness runs as a repeatable canary.
- R35. **Writer-error injection** (Injection / Geometry / P2): transform errors are injected into the placement writer and the round-trip oracle must fail — the write path is held to the same standard as compute.
- **Success signal:** every injected transform error in the writer catalog fails the round-trip oracle, and the injection run is repeatable and CI-invocable.

### Key Technical Decisions

- KTD1. **Mutants are hand-curated from the repo's incident classes, not randomly generated.** The kernel catalog families are sign flip, convention flip (R(+theta)/R(-theta)), dropped term, index/offset off-by-one, and swapped axes. Rationale: the repo's past failures define the defect space; random mutants would mostly test the compiler, not the suite.
- KTD2. **The mutated side is the Rust kernel; the kill oracle is the differential suite against the Python reference.** Rationale: the Rust side is the migration target whose regression the canary must catch; mutating Python would test oracle self-consistency, not migration safety. (This objection applies to the kernel catalogs only — the writer family's object is the Python writer itself and its oracle is external; see KTD7.)
- KTD3. **The harness applies a mutant to a scratch copy of the crate, rebuilds it, and runs the owning differential suite, recording kill/escape per mutant.** The working tree stays clean. Rationale: an in-tree mutation would corrupt the workspace; a scratch copy keeps the canary repeatable and CI-safe.
- KTD4. **An escaped mutant is a defect in the suite, treated as a first-class finding.** Either the mutant is behaviorally equivalent (documented and removed) or the owning suite gains a discriminating test (the canary function). Rationale: the point of the exercise is to find what the differential does not catch.
- KTD5. **Kernel scope is the three families the idea names: rotation, bbox, pad offsets.** Concretely `transform.rs`'s rotation family, `get_rotated_bounds`/`AABB` bbox family, and `pad_geometry.rs`'s pad-offset/support-radius family, plus the Python `kicad_transform` rotation surface whose kill oracle is the ground-truth and pcbnew tests.
- KTD6. **The writer family's kill oracle is the R12 round-trip oracle (plan 2026-08-02-009).** Mutants are applied to the writer, a board is written, re-parsed, and compared against the solver's model. This is an explicit cross-plan dependency: plan 009's U1 (`packages/temper-placer/src/temper_placer/validation/placement_roundtrip.py` plus its suite) is declared as a dependency of units U5–U7, not assumed. Rationale: the oracle is the write-path truth check the injection exists to prove; no new comparison mechanism is invented.
- KTD7. **The writer family reuses this plan's mutation harness rather than a new mechanism.** The harness gains a `--family writer` mode that applies mutants to the Python writer modules in a scratch copy. Rationale: one mutation harness, two catalogs; the working tree stays clean in both.
- KTD8. **The writer catalog is the incident class itself: rotation dropped, convention sign flip, pad-body angle not shifted, and angle-delta off-by-one.** The center-offset class is **excluded** from the writer catalog until the deferred R22 fix, and classified EQUIVALENT-with-reason up front: the current `_apply_placements_to_pcb` writes raw box-center, so "center offset not subtracted" is behaviorally equivalent to the shipped code (per `docs/evidence/2026-07-30-placement-writer-rotation.md`; the review's ground-truth correction records the divergence as current status quo, not a mutation). The class re-enters the catalog as a live mutant once the R22 fix wires center-offset subtraction into the adapter path. Rationale: the catalog is built from what actually shipped, matching the KTD1 discipline — and a mutant that reproduces shipped behavior verbatim is a recorded equivalence, not a catalog entry.
- KTD9. **Both production writers are covered.** `write_placements_to_pcb` (CLI path) and `_apply_placements_to_pcb` (`route_pcb` path) have different contracts and different incident histories. Rationale: one covered writer does not vouch for the other; each carries its own kill set.
- KTD10. **A mutant that escapes the oracle is a defect in the oracle, treated as a first-class finding.** Either the mutant is behaviorally equivalent (documented) or the oracle gains a discriminating case. Rationale: identical to the KTD4 standard — the point is to find what the oracle does not catch.
- KTD11. **The venv is restored after every mutant with a content-hash assertion.** `maturin develop --release` installs the mutated kernel into the shared venv, so "working tree clean" does not cover the venv (review ground-truth correction). After each mutant — or once, at end of run — the harness either rebuilds the unmutated crate into the venv or snapshots/restores the installed extension, and asserts the restored content-hash matches the stamp recorded by `scripts/write_extension_stamps.py` (the stamp `scripts/check_stale_extensions.py` compares against). A restore that leaves a stale `.so` fails the run. Rationale: a mutant build left in the venv poisons every subsequent import in the shared venv — the exact shared-mutable-state hazard the stamping gate exists for.
- KTD12. **Per-PR family runs; the full catalog on a schedule, with a wall-time budget.** A PR touching a kernel or writer file runs only the affected family (`--family rotation|bbox|pad-offsets|writer`) as its gate; the full-catalog run is a scheduled canary (nightly) rather than a per-PR block. The full-catalog run must complete within a wall-time budget measured and recorded in U1 (target ≤ 60 minutes, dominated by Rust rebuilds; writer-family mutants are near-instant since Python needs no rebuild) — if the measured budget is exceeded, the scheduled full run splits by family. Rationale: kernel mutants each pay a crate rebuild, so gating every PR on the full catalog would make the canary the slowest check in CI; the split keeps the development loop tight while the scheduled run keeps the complete kill set fresh.

### Assumptions

- The differential suites named in each family's `VERIFICATION.md` section are the kill oracles; where a family has no differential suite yet, its ground-truth or pcbnew-oracle tests serve.
- The rebuild step follows `make extensions`'s `--no-sync` discipline so a mutant build cannot evict unrelated installed extensions.
- The harness runs per family; a full run over all families is the CI canary, and per-family runs are the development loop.
- The R12 oracle exists and passes on the current writers before injection begins; units U5–U7 depend on it (plan 2026-08-02-009, U1).
- The mutation harness exists and supports a writer-family mode; extending it is in scope here, not re-implementing it.
- The Python writer modules are mutated by scratch-copy source transformation (no rebuild step needed, unlike the Rust kernels); the harness's Rust rebuild path is skipped for the writer family.
- The geometry sequencing spine from the portfolio review (009 → 011 → this plan → writer family) is followed; the writer family's units land after plan 009's oracle exists.

---

## Implementation Units

Unit numbering: the surviving plan's U1–U4 keep their IDs; the absorbed plan 2026-08-02-013's units map U1→U5 (writer-family harness mode), U2→U6 (`write_placements_to_pcb` catalog), U3→U7 (`_apply_placements_to_pcb` catalog).

### U1. Mutation harness

**Goal:** A repeatable harness that applies a mutant to a scratch copy of a kernel, rebuilds, runs the owning tests, and reports kill/escape — and restores the venv afterward.

**Requirements:** R34

**Dependencies:** none

**Files:**
- New: `scripts/check_geometry_kernel_mutations.py`
- Modify: `scripts/manifest.yaml` (entry for the new script)

**Approach:**
1. Implement a harness that, given a mutant descriptor (target file, search/replace transformation), copies the crate source to a scratch directory, applies the transformation, rebuilds via the extension-build path, and runs the owning test module.
2. Record per-mutant outcomes: KILLED (at least one test failed), ESCAPED (all tests passed), or EQUIVALENT (behaviorally identical by inspection, documented).
3. Exit nonzero when any mutant escapes without an EQUIVALENT record.
4. Support a `--family` selector and a `--ci` mode that runs the full catalog.
5. Restore the venv after each mutant (or at end of run): rebuild the unmutated crate into the venv or snapshot/restore the installed extension, asserting the restored content-hash matches the stamp recorded by `scripts/write_extension_stamps.py`. A restore that leaves a stale `.so` fails the run — "working tree clean" does not cover the venv (KTD11).

**Patterns to follow:** `scripts/check_stale_extensions.py`'s crate discovery and rebuild discipline; `scripts/write_extension_stamps.py`'s content-hash stamping for the restore assertion; `make extensions`'s `--no-sync` maturin invocation; the differential-suite naming convention (`test_*_rust_differential.py`) for locating kill oracles.

**Test scenarios:**
1. A known-killed mutant (rotation sign flip on `transform_pin_position`): the harness reports KILLED and exits 0.
2. A no-op mutation (whitespace change): the harness reports ESCAPED and, lacking an EQUIVALENT record, exits nonzero.
3. An EQUIVALENT-recorded mutant: the harness reports EQUIVALENT and exits 0.
4. Missing target file in the mutant descriptor: the harness fails loudly, not silently.
5. The working tree is byte-identical before and after a run.
6. A mutant build left in the venv (simulated restore failure): the run fails on the content-hash/stamp assertion — never a silent stale `.so`.

**Verification:** The harness's own scenarios pass; a run leaves the working tree clean and the installed extension restored (content-hash matches the stamp; `make extensions-check` reports 0 STALE); the manifest entry is present and `scripts/trace_invocations.py` refreshes the invocation graph. The full-catalog wall-time budget (KTD12, target ≤ 60 minutes) is measured and recorded here.

### U2. Rotation-kernel mutant catalog

**Goal:** Every mutant in the rotation family is killed or documented.

**Requirements:** R34

**Dependencies:** U1; plan 2026-08-02-011 (R23) U1 — creates `packages/temper-placer/tests/geometry/test_kicad_transform_algebra.py`, the exhaustive-algebra kill-oracle file this unit extends (declared per the 012 review; the file does not exist until 011's U1 lands).

**Files:**
- Modify: `scripts/check_geometry_kernel_mutations.py` (catalog data)
- Modify: `packages/temper-placer/tests/geometry/test_kicad_transform_rust_differential.py` (discriminating tests for escapes, if any)
- Modify: `packages/temper-placer/tests/geometry/test_kicad_transform_algebra.py` (discriminating tests, if any)

**Approach:**
1. Catalog mutants for `transform.rs`'s rotation family: sign flip (R(+theta) instead of R(-theta)), dropped rotation term (identity), axis swap, angle off-by-one.
2. Catalog the Python `kicad_transform` rotation surface with the ground-truth and pcbnew tests as kill oracle.
3. Run the harness per mutant; record kills and add discriminating tests for any escape.
4. Assert the final catalog has zero undocumented escapes.

**Patterns to follow:** the mutation-test-proves-degenerate-kernel-violates-property pattern in `test_bottleneck_geometry_pbt.py`'s mutation notes; the sign-flip falsifier scenarios in the exhaustive algebra suite (plan 2026-08-02-011).

**Test scenarios:**
1. Sign flip on `transform_pin_position`: KILLED by the differential (Python/Rust mismatch at a non-symmetric offset).
2. Dropped rotation term on `transform_pin_position`: KILLED by the differential at every non-zero angle.
3. Sign flip on `kicad_transform.rotate_local_to_world`: KILLED by the ground-truth convention-anchor test at 90 degrees.
4. Axis swap on `rotate_point`: KILLED by the composition or anchored-value scenarios.
5. Any escape found: a discriminating test is added and the mutant is re-run as KILLED.

**Verification:** The rotation family reports 100% kill (plus documented EQUIVALENT entries); the differential and algebra suites remain green on the unmutated tree.

### U3. Bbox-kernel mutant catalog

**Goal:** Every mutant in the bbox family is killed or documented.

**Requirements:** R34

**Dependencies:** U1

**Files:**
- Modify: `scripts/check_geometry_kernel_mutations.py` (catalog data)
- Modify: `packages/temper-placer/tests/geometry/` (discriminating tests for escapes, if any)

**Approach:**
1. Catalog mutants for the bbox family: half-width/half-height dropped, corner-order swap, min/max reduction flipped, and rotated-bounds ignoring the angle.
2. Run the harness per mutant against the owning differential and geometry suites.
3. Add discriminating tests for escapes and assert zero undocumented escapes.

**Patterns to follow:** the existing `test_geometry.py` / `test_drc_inflate.py` bbox coverage; the AABB reduction-order comments in `transform.rs`.

**Test scenarios:**
1. Half-width dropped in `get_rotated_bounds`: KILLED by a bbox test at a non-square rectangle.
2. Rotation ignored in `get_rotated_bounds`: KILLED at 45 degrees where the AABB must grow by the diagonal.
3. Min/max reduction flipped: KILLED by a bounds test on negative-coordinate rectangles.
4. Corner-order swap in `rotate_rectangle_corners`: KILLED by a corner-order assertion.
5. Any escape found: a discriminating test is added and the mutant is re-run as KILLED.

**Verification:** The bbox family reports 100% kill (plus documented EQUIVALENT entries); the geometry suites remain green on the unmutated tree.

### U4. Pad-offset-kernel mutant catalog

**Goal:** Every mutant in the pad-offset family is killed or documented.

**Requirements:** R34

**Dependencies:** U1

**Files:**
- Modify: `scripts/check_geometry_kernel_mutations.py` (catalog data)
- Modify: `packages/temper-placer/tests/core/test_pad_geometry_pbt.py` or the pad-geometry differential (discriminating tests for escapes, if any)

**Approach:**
1. Catalog mutants for the pad-offset family: center offset not applied, local-offset sign flip, support-radius term dropped, corner radius mis-set.
2. Run the harness per mutant against the pad-geometry differential and PBT suites.
3. Add discriminating tests for escapes and assert zero undocumented escapes.

**Patterns to follow:** the pad-geometry PBT properties in `packages/temper-geometry/VERIFICATION.md` (support_radius never under-reports, bounding_radius upper bound); the `test_pad_geometry_rust_differential.py`-style bit-exact pins.

**Test scenarios:**
1. Center offset not applied: KILLED by the differential at a non-zero offset pad.
2. Local-offset sign flip: KILLED by the differential at an asymmetric pad.
3. Support-radius term dropped: KILLED by the PBT support-radius never-under-reports property.
4. Corner radius mis-set: KILLED by the PBT bounding-radius upper-bound property.
5. Any escape found: a discriminating test is added and the mutant is re-run as KILLED.

**Verification:** The pad-offset family reports 100% kill (plus documented EQUIVALENT entries); the pad-geometry suites remain green on the unmutated tree.

### U5. Writer-family harness mode

**Goal:** The mutation harness supports a writer-family mode that applies a mutant to a scratch copy of a writer module and runs the round-trip oracle suite as the kill oracle.

**Requirements:** R35

**Dependencies:** U1 (this plan's harness); plan 2026-08-02-009 (R12) U1 — the round-trip comparator (`packages/temper-placer/src/temper_placer/validation/placement_roundtrip.py`) and its suite (`packages/temper-placer/tests/validation/test_placement_roundtrip.py`) are the writer family's kill oracle, declared explicitly per KTD6.

**Files:**
- Modify: `scripts/check_geometry_kernel_mutations.py` (writer-family mode)

**Approach:**
1. Add a `--family writer` mode that applies a source-level mutant to a scratch copy of `io/_write_board.py` or `router_v6/_adapter_convert.py`.
2. For each mutant, run the round-trip oracle test suite (from plan 2026-08-02-009) against the scratch-copied writer and record KILLED/ESCAPED/EQUIVALENT.
3. Reuse the harness's report and exit-code contract: nonzero on any undocumented escape.
4. Confirm the working tree stays byte-identical after a writer-family run. Python writers need no rebuild; the harness's Rust rebuild path is skipped for this family.

**Patterns to follow:** the harness structure and report format; the scratch-copy discipline; the round-trip oracle suite's test layout.

**Test scenarios:**
1. Writer-family run with no mutants: exits 0 and leaves the tree clean.
2. A known-killed writer mutant (rotation dropped): the harness reports KILLED.
3. A no-op mutation: reports ESCAPED and exits nonzero without an EQUIVALENT record.
4. A mutant targeting a missing symbol: fails loudly, not silently.

**Verification:** The harness scenarios pass; the tree is clean after runs; the manifest entry already covers the shared script (no new entry needed).

### U6. `write_placements_to_pcb` mutant catalog

**Goal:** Every injected transform error against the CLI writer is killed by the round-trip oracle or documented as equivalent.

**Requirements:** R35

**Dependencies:** U5; plan 2026-08-02-009 U1 (the round-trip oracle suite).

**Files:**
- Modify: `scripts/check_geometry_kernel_mutations.py` (catalog data)
- Modify: `packages/temper-placer/tests/validation/test_placement_roundtrip.py` or `packages/temper-placer/tests/io/test_kicad_writer.py` (discriminating cases for escapes, if any)

**Approach:**
1. Catalog mutants for `write_placements_to_pcb`: rotation dropped (footprint angle left at template value), sign flip (R(+theta) written), pad-body angle not shifted (the pre-#412 class), and angle-delta off-by-one (delta written as `new - old - 1`).
2. The center-offset class is not cataloged: recorded EQUIVALENT-with-reason up front (KTD8) and deferred until the R22 fix; no oracle run is attempted against it on this path.
3. Run the harness per mutant against the round-trip oracle.
4. Add discriminating oracle cases for any escape and assert zero undocumented escapes.

**Patterns to follow:** the writer's center-offset and `_reorient_pads` contracts; the R12 falsifier scenarios in plan 2026-08-02-009's U2.

**Test scenarios:**
1. Rotation dropped: oracle FAILS on footprint angle and pad bodies for a non-zero rotation solve.
2. Sign flip: oracle FAILS at a non-symmetric offset (e.g. 90 degrees with an asymmetric pad).
3. Pad-body angle not shifted: oracle FAILS on pad body angles (the pre-#412 shorting class).
4. Angle-delta off-by-one (e.g. delta written as `new - old - 1`): oracle FAILS.
5. Any escape found: a discriminating oracle case is added and the mutant is re-run as KILLED.

(Note: the former center-offset scenario is dropped from this catalog; the class is recorded EQUIVALENT-with-reason per KTD8 and re-enters with the R22 fix.)

**Verification:** The CLI-writer family reports 100% kill (plus the documented EQUIVALENT center-offset exclusion); the writer and oracle suites remain green on the unmutated tree.

### U7. `_apply_placements_to_pcb` mutant catalog

**Goal:** Every injected transform error against the `route_pcb` writer is killed by the round-trip oracle or documented as equivalent.

**Requirements:** R35

**Dependencies:** U5; plan 2026-08-02-009 U1 (the round-trip oracle suite, exercised through the adapter path).

**Files:**
- Modify: `scripts/check_geometry_kernel_mutations.py` (catalog data)
- Modify: `packages/temper-placer/tests/router_v6/test_adapter.py` (discriminating cases for escapes, if any)

**Approach:**
1. Catalog mutants for `_apply_placements_to_pcb`: rotation dropped (the exact 2026-07-30 incident — ignore the `rotations=` parameter), sign flip, pad re-orientation omitted, and angle-preservation branch broken.
2. The center-offset class is recorded EQUIVALENT-with-reason up front (KTD8): the current writer writes raw box-center, so "center offset not subtracted" is behaviorally equivalent to shipped code — no mutant is cataloged until the R22 fix wires the subtraction into the adapter path.
3. Run the harness per mutant against the round-trip oracle exercised through the adapter path, following plan 009's scoped adapter-path PASS claim (components without center offset — the review's fix-before-execution item 2).
4. Add discriminating oracle cases for any escape and assert zero undocumented escapes.

**Patterns to follow:** the `TestApplyPlacementsToPcbRotation` cases and the `rotations=None` preservation contract; the R12 falsifier for the un-applied-rotation class.

**Test scenarios:**
1. Rotation dropped (mutant that ignores `rotations=`): oracle FAILS on footprint angle for a solve that chose non-zero rotations — the 2026-07-30 class re-injected.
2. Sign flip in the footprint-angle write: oracle FAILS at 90 degrees with an asymmetric pad.
3. Pad re-orientation omitted (mutant that skips `_reorient_pads_in_footprint_block`): oracle FAILS on pad body angles.
4. Angle-preservation branch broken (mutant that rewrites angles even when `rotations=None`): oracle FAILS the byte-preservation case.
5. Any escape found: a discriminating oracle case is added and the mutant is re-run as KILLED.

**Verification:** The adapter-writer family reports 100% kill (plus the documented EQUIVALENT center-offset exclusion); the adapter and oracle suites remain green on the unmutated tree.

---

## Verification Contract

- `uv run python scripts/check_geometry_kernel_mutations.py --ci` — full catalog run (rotation, bbox, pad-offsets, and writer families); exits nonzero on any undocumented escape.
- Per-family runs (`--family rotation`, `--family bbox`, `--family pad-offsets`, `--family writer`) — the development loop and the per-PR gate for the affected family.
- `uv run pytest packages/temper-placer/tests/geometry/` and the pad-geometry/bbox suites — green on the unmutated tree.
- `uv run pytest packages/temper-placer/tests/validation/test_placement_roundtrip.py` — the writer family's kill oracle stays green on the unmutated tree.
- `uv run pytest packages/temper-placer/tests/io/test_kicad_writer.py` and `packages/temper-placer/tests/router_v6/test_adapter.py` — writer suites green on the unmutated tree.
- `make extensions-check` — 0 STALE after harness rebuilds; the venv restore step asserts the installed extension's content-hash matches the stamp (`scripts/write_extension_stamps.py`); `make extensions` rebuilds use `--no-sync` per the extension-build convention.
- Full-catalog scheduled run completes within the wall-time budget measured in U1 (target ≤ 60 minutes; writer-family mutants are near-instant, Rust rebuilds dominate).
- `uv run python scripts/import_linter_gate.py` — import boundary check.
- `scripts/manifest.yaml` — the new script has an entry; `scripts/trace_invocations.py` refreshed.
- Working-tree check: byte-identical before and after a run (kernel and writer families).

---

## Definition of Done

- The harness exists, is manifest-registered, leaves the working tree clean, and restores the venv extension (content-hash matches the stamp) after every run.
- Rotation, bbox, pad-offset, and writer families each report 100% kill, with every escape either behaviorally equivalent (documented) or closed by a new discriminating test.
- The center-offset class is recorded EQUIVALENT-with-reason in the writer family and re-enters the catalog with the R22 fix.
- The 2026-07-30 rotation-drop class is re-injected and the round-trip oracle fails it.
- Both production writers carry catalogs with 100% kill (plus documented EQUIVALENT entries).
- The full-catalog run is CI-invocable and green within the wall-time budget; per-PR family runs are the development loop.
- No kernel or writer source changes outside the scratch copies; all existing suites green.

---

## Scope Boundaries

**In scope:** rotation, bbox, and pad-offset kernel families in the Rust crate, the Python `kicad_transform` rotation surface, and transform-error injection into `write_placements_to_pcb` and `_apply_placements_to_pcb` judged by the R12 round-trip oracle.

**Deferred to Follow-Up Work**

- Mutant catalogs for kernels outside the three named families (e.g. creepage, grid raster, bottleneck) — the harness generalizes; new catalogs are follow-up pulls.
- Automating mutant generation from a seed (random mutation with operator filtering) — hand-curation from incident classes is the deliberate first standard.
- The center-offset writer mutant — recorded EQUIVALENT-with-reason until the deferred R22 fix wires center-offset subtraction into `route_pcb`/`_apply_placements_to_pcb`'s callers; it re-enters the writer catalog as a live mutant once the fix lands.
- Injection into serialization paths beyond the two writers (zones, silkscreen, courtyard emission) — the round-trip oracle covers pad/footprint geometry; other surfaces are separate follow-ups.
- Mutating the R12 oracle itself — oracle self-mutation is a distinct canary (the R34/R35 pattern applied to the validator), not part of this plan.
- A CI gate that blocks merge on an escaped mutant — the harness's nonzero exit is the enforcement; hard-gating on a schedule is a follow-up decision.

---

## Sources / Research

- `packages/temper-geometry/src/transform.rs` — rotation and bbox kernels (mutation targets).
- `packages/temper-geometry/src/pad_geometry.rs` — pad-offset kernels (mutation target).
- `packages/temper-geometry/VERIFICATION.md` — the differential/PBT suites that act as kill oracles and the properties the mutants are checked against.
- `packages/temper-placer/src/temper_placer/io/_write_board.py` — `write_placements_to_pcb` and `_reorient_pads` (writer-family mutation targets).
- `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py` — `_apply_placements_to_pcb` (writer-family mutation target).
- `docs/evidence/2026-07-30-placement-writer-rotation.md` — the rotation-drop and center-offset incident class (seed for the writer catalog and the EQUIVALENT-with-reason exclusion).
- `scripts/check_stale_extensions.py`, `scripts/write_extension_stamps.py`, and `make extensions` (AGENTS.md) — the rebuild/stamp discipline the harness follows and the restore step asserts against.
- `scripts/manifest.yaml` — the script-manifest convention.
- `docs/plans/2026-08-02-009-feat-transform-round-trip-oracle-plan.md` — the R12 kill oracle for the writer family (cross-plan dependency).
- `docs/plans/2026-08-02-011-feat-transform-algebra-exhaustiveness-plan.md` — R23; its U1 creates `test_kicad_transform_algebra.py`, the rotation-family kill-oracle file this plan's U2 extends.
- `docs/evidence/2026-08-02-validation-portfolio-review.md` — the review: R35 → 012 merge map, ground-truth corrections (venv restore), fix-before-execution items 2 and 13.
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the origin (R34, R35).
