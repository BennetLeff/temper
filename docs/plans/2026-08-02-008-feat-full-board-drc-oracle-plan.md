---
title: Full-board DRC Oracle Differential - Plan
type: feat
date: 2026-08-02
topic: full-board-drc-oracle
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R11)
---

# Full-board DRC Oracle Differential - Plan

## Goal Capsule

**Objective:** A differential gate that re-runs every committed placement through real `kicad-cli` DRC and compares the placer's internal clearance/courtyard models violation-by-violation, so model-vs-reality divergence fails at commit time.

**Product authority:** temper-placer maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none. Per-type tolerance bands are measured at pull time per the portfolio's deferred question (origin's "Per-idea oracle divergence thresholds (R9, R11) — measured at pull time"), using the ceiling convention already documented in `power_pcb_dataset/drc_ceiling.json`.

---

## Product Contract

### Summary

Every placement that ships — the golden-board regression placements and the committed board — is measured by two independent engines on the same written artifact: the placer's internal temper-drc checks and real `kicad-cli` DRC. Violation records are normalized to a common shape, mapped per rule class, and compared within measured tolerance bands. A per-class delta beyond its band fails the run.

### Problem Frame

`CourtyardCheckStage` reported zero courtyard collisions while `kicad-cli` DRC found 43 on the identical export, through two stacked bugs: a Shapely 2.x `STRtree.query()` index-vs-object-identity no-op, and a courtyard extraction strategy that silently matched 0 of 149 real footprints. The internal model was trusted until a human read it closely. This idea makes the re-check permanent: the abstract model is compared against reality on every committed placement, not when someone happens to investigate.

### Requirements

- R11. **Full-board DRC oracle differential** (Oracle / Geometry / P1): every committed placement is re-run through real `kicad-cli` DRC (all-track-errors, sampled per the ceiling convention) and the placer's internal clearance/courtyard models are compared violation-by-violation — the "model says zero, real DRC says 43" class fails at commit time.
- **Success signal:** a placement whose internal model reports zero (or fewer than banded) clearance/courtyard violations while real `kicad-cli` DRC reports more fails at commit time.

### Key Technical Decisions

- KTD1. **Violation-level matching with per-type tolerance bands, not strict equality.** `kicad-cli` counts vary run-to-run on a byte-identical board (`clearance` 499-501 per the ceiling record), and internal check names do not map 1:1 to `kicad-cli` types. Records are matched on (rule class, component pair, location), and the per-type count delta is compared against a measured band. Rationale: strict equality would flake on the one genuinely nondeterministic category the ceiling file already documents.
- KTD2. **Tolerance bands reuse the `drc_ceiling.json` convention (observed range over N samples, max+1 headroom), never new ad-hoc thresholds.** Rationale: one sampling convention for the whole repo; the ceiling file already carries the measured ranges per type.
- KTD3. **Both engines run on the same written board artifact, not on synthetic exports.** The internal checks run on the written `.kicad_pcb` via the parsed-PCB board-dict path; `kicad-cli` DRC runs on the same file. Rationale: comparing solver positions against `kicad-cli` on a synthetic export would skip the write path and miss the very class this idea exists for.
- KTD4. **Unmodeled `kicad-cli` classes are excluded with an attributed cause, never silently.** `kicad-cli` emits track/via classes (e.g. `tracks_crossing`, `via_diameter`, `hole_clearance`) that the internal model does not model; these stay governed by the existing ceiling ratchet. Rationale: mirrors the ceiling file's "debt, not budget" discipline — exclusions are named, not absorbed.

### Assumptions

- The internal model's covered classes are those the temper-drc check suite already implements: courtyard overlap/containment, component overlap, clearance, zone containment, creepage, and the remaining standard checks listed in `create_standard_drc_oracle`.
- The exact rule-class mapping (which `kicad-cli` type maps to which internal check) is confirmed at implementation against the committed board's measured types, using the mapping table in U2 as the starting point.
- The differential gate is advisory on the golden-board regression tests' existing DRC thresholds until the per-type bands are measured; it does not change the golden-board pass/fail thresholds themselves.

---

## Implementation Units

### U1. Differential harness

**Goal:** A reusable comparator that runs both DRC engines on one board file, normalizes both engines' violation records to a common shape, and emits a per-rule-class mismatch report.

**Requirements:** R11

**Dependencies:** none

**Files:**
- New: `packages/temper-placer/src/temper_placer/validation/drc_differential.py`
- New: `packages/temper-placer/tests/validation/test_drc_differential.py`
- Fixtures: `packages/temper-placer/tests/fixtures/` (seeded board fixtures)

**Approach:**
1. Build a function that takes a `.kicad_pcb` path and runs both engines: the internal checks via `DRCOracle._build_board_dict_from_parsed_pcb` (reusing the parsed-PCB path `ci_closure_test.py` already uses) and `kicad-cli` via `temper_placer.validation._drc_api.run_drc` (which already passes `--all-track-errors`).
2. Normalize both engines' outputs into one record shape: rule class, severity, component pair, location.
3. Match records across engines on (rule class, component pair, location within tolerance) and report per-class counts plus the mismatch delta.
4. Handle oracle unavailability explicitly: a missing `kicad-cli` binary yields a SKIPPED-with-cause verdict, never a silent pass.

**Patterns to follow:** `drc_oracle.py`'s parsed-PCB board-dict builder; `_drc_api.py`'s `DrcError` normalization and ref/net extraction; `ci_closure_test.py`'s reuse of the board-dict path; the ceiling file's `measured_via` convention for recording how a number was measured.

**Test scenarios:**
1. Same-board both-engine run on the committed board: both engines complete without raising, and the report contains one row per emitted rule class.
2. Synthetic clean placement (components spread with wide margins): internal model reports zero violations and `kicad-cli` reports zero for the mapped classes; the differential verdict is PASS.
3. Synthetic overlap pair (two components with touching courtyards): the internal `CourtyardCheck` reports at least one violation, `kicad-cli` reports `courtyards_overlap`; the two records match on (rule class, component pair).
4. Model-zero/DRC-positive fixture re-encoded from the D3/C4 pair (an `fp_circle` courtyard offset from origin and an `fp_line` rectangle courtyard, exercising the pre-fix extraction classes): the internal model reports zero courtyard violations while `kicad-cli` reports `courtyards_overlap` greater than zero; the differential verdict is FAIL with a per-class delta beyond band.
5. `kicad-cli` unavailable (simulated by hiding the binary): the harness reports SKIPPED-with-cause and does not emit PASS.

**Verification:** The unit suite above passes; the D3/C4 fixture is confirmed to fail the differential while a clean fixture passes; no new `.coverage-allowlist` entries are needed because every public function in the new module is exercised by the suite.

### U2. Rule-class mapping and tolerance bands

**Goal:** A mapping from every `kicad-cli` violation type the board emits to either an internal check or an attributed exclusion, plus measured per-type tolerance bands.

**Requirements:** R11

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/validation/drc_differential.py` (mapping table and band data)
- Modify: `packages/temper-placer/tests/validation/test_drc_differential.py`

**Approach:**
1. Encode the starting mapping table: `courtyards_overlap` and `pth_inside_courtyard` map to the courtyard checks; `clearance` maps to the clearance check; `shorting_items` maps to the component-overlap check; `copper_edge_clearance` maps to the zone-containment/edge checks; `creepage` maps to the creepage check.
2. Record the remaining types the committed board emits (e.g. `tracks_crossing`, `via_diameter`, `drill_out_of_range`, `hole_clearance`, `hole_to_hole`, `annular_width`, `solder_mask_bridge`) as excluded with the cause "not modeled by the internal engine; governed by the ceiling ratchet".
3. Derive per-type tolerance bands from the ceiling file's measured data: observed range over the documented sample count, with max+1 headroom for the nondeterministic category per the file's own `_march` convention.
4. Assert the mapping table covers every key in the ceiling record's `violations_by_type` and `warnings_by_type` for the temper board.

**Patterns to follow:** `power_pcb_dataset/drc_ceiling.json`'s `nondeterministic_error_types` block and `category_source` field; `_drc_api.py`'s rule-type strings as the canonical `kicad-cli` names.

**Test scenarios:**
1. Mapping completeness: for every type key in the ceiling record's `violations_by_type` and `warnings_by_type`, the mapping table yields exactly one outcome (mapped check or exclusion-with-cause).
2. Band derivation: N samples of `kicad-cli` on the committed board produce per-type observed ranges that equal or cover the ceiling record's documented ranges.
3. Within-band fluctuation (`clearance` at observed max): the differential verdict is PASS.
4. Beyond-band delta on a mapped type (fixture forcing `courtyards_overlap` above band): the differential verdict is FAIL.
5. An excluded type appearing in the report: the differential ignores it and the verdict is computed over mapped classes only.

**Verification:** All mapping and band tests pass; the derived bands match the ceiling file's recorded numbers for the temper board.

### U3. Gate wiring on committed placements

**Goal:** The differential runs on the golden-board regression placements and the committed board, failing on any per-class delta beyond band.

**Requirements:** R11

**Dependencies:** U1, U2

**Files:**
- Modify: `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` (golden-board placements)
- Modify: `scripts/ci_check_drc.py` (committed board, `--backend kicad-cli` path)

**Approach:**
1. Add a differential assertion to the golden-board regression tests: after each golden-board write, run the harness and assert PASS for all mapped classes.
2. Extend `scripts/ci_check_drc.py`'s `kicad-cli` backend to also emit the differential verdict for `pcb/temper.kicad_pcb`, mapping a beyond-band verdict to a nonzero exit.
3. Keep the seeded D3/C4-style fixture in the differential suite as the permanent regression corpus entry for this incident class.

**Patterns to follow:** `ci_check_drc.py`'s existing exit-code contract (0 = pass, 1 = ceiling exceeded); `test_regression_drc.py`'s golden-board write flow; the ceiling file's `measured_via` provenance style.

**Test scenarios:**
1. Integration: the golden-board regression test writes a placement, the differential runs on the written artifact, and the verdict is PASS on the current committed state.
2. Integration: `scripts/ci_check_drc.py --backend kicad-cli` emits the differential verdict for the committed board and exits 0.
3. Falsifier: with the D3/C4 fixture substituted as the board under test, the wired gate exits nonzero.
4. Regression: the golden-board test's existing DRC thresholds are unchanged by this wiring.

**Verification:** The golden-board suite and `ci_check_drc.py` both pass on the current tree; the falsifier fixture fails the wired gate end-to-end; `scripts/import_linter_gate.py` passes.

---

## Verification Contract

- `uv run pytest packages/temper-placer/tests/validation/test_drc_differential.py` — harness, mapping, and band tests.
- `uv run pytest packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` — golden-board differential assertion.
- `uv run python scripts/ci_check_drc.py` — committed-board ratchet and differential verdict.
- `uv run python scripts/import_linter_gate.py` — import boundary check.
- Coverage gate: new public functions in `drc_differential.py` are exercised by the unit suite; no new `.coverage-allowlist` entries.

---

## Definition of Done

- The harness, mapping, and bands exist and are unit-tested.
- The differential runs on the golden-board regression placements and the committed board.
- The model-zero/DRC-43-style fixture demonstrably fails the gate.
- No new `.coverage-allowlist` entries; import linter green.
- The ceiling file's numbers are unchanged (this plan reads them, it does not ratchet them).

---

## Scope Boundaries

**In scope:** internal clearance/courtyard/overlap/creepage classes on the committed board and golden-board placements.

**Deferred to Follow-Up Work**

- Violation-text-level matching (message-string equality) — rule-class/component/location matching suffices for the incident class.
- Extending the differential to track/via classes the internal engine does not model — those stay ceiling-governed.
- Tolerance calibration for boards beyond the temper board — measured per board at pull time.
- Absorbing R11 into a standalone always-on CI gate independent of the golden-board tests.

---

## Sources / Research

- `packages/temper-placer/src/temper_placer/validation/drc_oracle.py` — the internal-model oracle (seed).
- `packages/temper-placer/src/temper_placer/validation/_drc_api.py` — the `kicad-cli` runner with `--all-track-errors`.
- `power_pcb_dataset/drc_ceiling.json` — the sampling convention and per-type measured ranges.
- `scripts/ci_check_drc.py` — the existing committed-board DRC gate this plan extends.
- `docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md` — the incident class.
- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the origin (R11).
