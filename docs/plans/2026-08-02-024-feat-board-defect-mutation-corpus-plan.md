---
title: Board-Defect Mutation Corpus - Plan
type: feat
date: 2026-08-02
topic: board-defect-mutation-corpus
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R38)
---

# Board-Defect Mutation Corpus - Plan

## Goal Capsule

**Objective:** inject the real defect classes — component off-board, pad short, creepage crossing — into a copy of `pcb/temper.kicad_pcb` and prove each fails at least one gate, so the gates that protect the board are proven on the actual board file.

**Product authority:** temper-placer and board maintainer (single-maintainer project).

**Open blockers:** none.

---

## Product Contract

### Summary

A standing corpus takes the committed board, applies one deterministic defect mutation per class, and asserts the owning gate fails. The clean board must pass every gate. The gates that protect the board carry proven bite on the real file.

### Problem Frame

Gates are trusted until a bug slips through. The courtyard check that reported zero collisions where real DRC found 43, and the C1 pad2↔R7 pad2 short present in 120/120 runs, are the incident class: protection is asserted, not demonstrated. The real defect classes are known — the tank cap staged off-board, the C1 pad2↔R7 pad2 short, the DC_BUS↔LV_CONTROL creepage crossing — and each must be injected into a copy of the actual board and must fail its owning gate.

### Requirements

- R38. **Board-defect mutation corpus** (Injection / Board / P1): the real defect classes (component off-board, pad short, creepage crossing) are injected into a copy of the board and each must fail a gate — the gates that protect the board are proven on the actual board file. (verbatim from origin)
  - Success signal: each injected defect class fails at least one gate when run against a copy of `pcb/temper.kicad_pcb`, and the unmutated board passes every gate in the corpus.

### Key Technical Decisions

- KTD1. **Mutations are deterministic seeded transforms on a run-time copy of the committed board** — `pcb/temper.kicad_pcb` content never changes, so the DRC ceiling re-measurement convention stays inert (the corpus triggers no re-measurement).
- KTD2. **Each defect class names its owning gate in a table** — a class with no owning gate is a corpus error, not a pass; the mapping is the corpus's contract.
- KTD3. **Mutated boards are derived artifacts (hashed seeds), never committed** — the corpus re-derives from the committed board on every run, so board drift cannot rot it silently.
- KTD4. **The short class is asserted through the DRC measurement path** — `temper_placer.validation._drc_api.run_drc` with `--all-track-errors`, so the C1↔R7 class is deterministic (120/120 precedent).

### Assumptions

- Defect-to-gate mapping: off-board → the R26 containment invariant (until R26 lands, the `courtyards_overlap` and `copper_edge_clearance` DRC categories are the owning gate); pad short → the `shorting_items` DRC category via `run_drc`; creepage crossing → the REQ-SAFE-01 creepage gate, enforced at `design_value_mm` 10.0 per the handoff threshold note.
- The corpus runs where kicad-cli is available, the same constraint as the DRC gates; without kicad-cli it fails closed with a GATE ERROR, matching the anti-vacuity convention.
- Mutating a board copy does not require the board-change-to-DRC-ceiling-remeasurement step, because the committed `pcb/temper.kicad_pcb` is byte-identical.

---

## Implementation Units

### U1. Board mutation harness

**Goal:** deterministic seeded transforms that produce a mutated copy of `pcb/temper.kicad_pcb` for each defect class: a component moved off-board, two pads shorted, a creepage-crossing pair.

**Requirements:** R38.

**Dependencies:** none.

**Files:** `scripts/board_defect_mutator.py` (new), `scripts/manifest.yaml` (entry), `scripts/tests/test_board_defect_mutator.py` (new).

**Approach:** Copy the committed board to a temp path. Apply one named mutation: move a footprint's `(at x y)` outside the Edge.Cuts outline (off-board), rewrite a pad's net ordinal to join another pad's net (pad short), or move one component of a known pair to reduce pad distance below the creepage threshold (creepage crossing). Seed the transform deterministically and record a content hash of seed and mutated board.

**Patterns to follow:** the board sexp editing patterns in `scripts/resync_pcb_netlist.py`; footprint `(at ...)` and ref extraction in `io/kicad_parser.py`; the scratch-mutation-then-revert discipline in `scripts/tests/test_gen_repo_state.py`.

**Test scenarios:**
1. The off-board mutation moves exactly one named footprint outside the outline and changes no other footprint position.
2. The pad-short mutation joins exactly two named pads onto one net and changes no other pad net.
3. The creepage-crossing mutation moves exactly one component of a named pair and preserves every other footprint.
4. Two runs with the same seed produce byte-identical mutated boards.
5. The unmutated copy is byte-identical to the committed board.

**Verification:** the harness unit tests pass, and each mutation's diff is minimal and named.

### U2. Defect-to-gate mapping and corpus runner

**Goal:** a corpus runner that, for each defect class, runs the owning gate set against the mutated board and asserts at least one gate fails; the clean board must pass all gates.

**Requirements:** R38.

**Dependencies:** U1.

**Files:** `scripts/check_board_defect_corpus.py` (new), `scripts/manifest.yaml` (entry), `scripts/tests/test_check_board_defect_corpus.py` (new).

**Approach:** Define the class-to-gate table (off-board → R26 containment or the courtyard and edge-clearance DRC categories; pad short → `run_drc` `shorting_items`; creepage → REQ-SAFE-01 creepage). Run each mutated board through its owning gates. Fail the corpus run if any class has no failing gate. Run the clean board through every gate; fail if any gate fails on the clean board (anti-vacuity).

**Patterns to follow:** the anti-vacuity discipline of `scripts/check_vacuous_gates.py`; the gate invocation in `scripts/ci_check_drc.py`; the `scripts/manifest.yaml` convention.

**Test scenarios:**
1. Each mutated board fails its owning gate, with the defect class named in the failure.
2. A mutated board that passes every gate fails the corpus run as an uncovered class.
3. The clean board passes every gate in the corpus (anti-vacuity control).
4. A missing kicad-cli fails the corpus closed with a GATE ERROR, not a pass.

**Verification:** the corpus passes with all three classes covered and the anti-vacuity control green.

### U3. Seed corpus from the real defect instances

**Goal:** the initial corpus encodes the real defect instances — the tank cap off-board, the C1 pad2↔R7 pad2 short, and a DC_BUS↔LV_CONTROL creepage pair — with seeds that reproduce each class on the committed board.

**Requirements:** R38.

**Dependencies:** U2.

**Files:** `scripts/board_defect_corpus.yaml` (new seed manifest), `scripts/check_board_defect_corpus.py` (extend), `docs/evidence/2026-08-02-board-defect-corpus.md` (new).

**Approach:** Encode each real defect as a named mutation with a fixed seed referencing the real components (`tank.c_tank3` / board `C27`, C1 pad2 / R7 pad2, a named DC_BUS↔LV_CONTROL pair). Record each class's observed gate failure in the corpus manifest. Content-hash the seed against `pcb/temper.kicad_pcb` so a board change is detected and the corpus re-validated.

**Patterns to follow:** the provenance and `_march` conventions in `power_pcb_dataset/drc_ceiling.json`; evidence-doc provenance stamping.

**Test scenarios:**
1. The off-board seed reproduces the tank-cap class: the mutated board's containment (or courtyard) gate fails.
2. The pad-short seed reproduces the C1 pad2↔R7 pad2 class: `shorting_items` appears in the `run_drc` result.
3. The creepage seed reproduces a DC_BUS↔LV_CONTROL creepage violation at the enforced threshold.
4. The seed manifest's content hash matches the committed board; after a board change it mismatches and the corpus re-derives.

**Verification:** all three seeds reproduce their classes on the current board, with the evidence doc recording each reproduction.

### U4. CI wiring and regression cadence

**Goal:** the corpus runs in CI on a schedule and on board-touching PRs, and re-derives whenever `pcb/temper.kicad_pcb` changes.

**Requirements:** R38.

**Dependencies:** U3.

**Files:** `.github/workflows/` (board gates job), `scripts/manifest.yaml`.

**Approach:** Wire the corpus runner into the board gates workflow so every board-touching run executes the corpus against the PR's board content. The corpus re-derives mutated copies from that content. Register the scripts in `scripts/manifest.yaml`.

**Patterns to follow:** the board gates job conventions in the workflows; the workflow-linting convention in AGENTS.md (run actionlint before pushing workflow edits).

**Test scenarios:**
1. A board-touching change that breaks the clean-board anti-vacuity control fails the corpus job, with the class named.
2. A board-touching change that makes a defect class undetectable fails the corpus job as an uncovered class.

**Verification:** the CI job runs the corpus, and the workflow passes actionlint.

---

## Verification Contract

- `uv run pytest scripts/tests/test_board_defect_mutator.py scripts/tests/test_check_board_defect_corpus.py` passes.
- `uv run --no-sync python scripts/check_board_defect_corpus.py` passes with all three classes covered and the clean board green.
- `uv run python scripts/import_linter_gate.py` passes.
- New scripts have `scripts/manifest.yaml` entries; the workflow passes actionlint.

---

## Definition of Done

- Component off-board, pad short, and creepage crossing are each injected into a copy of `pcb/temper.kicad_pcb` and each fails its owning gate.
- The clean committed board passes every gate in the corpus (anti-vacuity).
- The corpus re-derives from the committed board; no mutated board is committed; the DRC ceiling record is untouched.
- New scripts have `scripts/manifest.yaml` entries.
- Dead-end or experimental code from implementation is removed from the diff.

---

## Scope Boundaries

- The corpus never mutates `pcb/temper.kicad_pcb`; it works on run-time copies.
- The corpus proves gates bite; it does not fix the board's known defects.

### Deferred to Follow-Up Work

- Additional defect classes (netlist-level mutations) — owned by R39's netlist-mutation corpus.
- The R26 formal invariants as the off-board class's owning gate — pending R26 landing.
- Hardening corpus failures to merge-blocking — pending bite-proven history and branch-protection rollout.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R38)
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` (the three real defect classes)
- `scripts/check_vacuous_gates.py` (anti-vacuity discipline)
- `packages/temper-placer/src/temper_placer/validation/_drc_api.py` (run_drc, `--all-track-errors`)
- `scripts/resync_pcb_netlist.py` (board sexp editing patterns)
- `scripts/tests/test_gen_repo_state.py` (scratch mutation, always reverted)
