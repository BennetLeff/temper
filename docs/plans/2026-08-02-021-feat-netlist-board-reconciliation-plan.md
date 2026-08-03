---
title: Netlist↔Board Reconciliation & Mutation - Plan
type: feat
date: 2026-08-02
topic: netlist-board-reconciliation
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R16, R39)
---

# Netlist↔Board Reconciliation & Mutation - Plan

## Goal Capsule

**Objective:** compare the netlist extracted from the actual board file against the design netlist, keyed by sheetpath and instance path, so wholesale renumbering, missing components, and the tank-capacitor class fail regardless of refdes overlap; and inject the identity-defect mutation classes — wholesale renumbering, reused refdes, and dropped nets — into the design netlist so the identity checks and the reconciliation oracle are proven against the classes they exist for.

**Product authority:** temper-placer and board maintainer (single-maintainer project).

**Open blockers:** none.

---

## Product Contract

### Summary

The board's own netlist (extracted from `pcb/temper.kicad_pcb`) becomes a first-class input, compared against the compiled design netlist (`elec/build/default.net`) by instance path and net membership. Component identity stops being a refdes-set-overlap guess and becomes a per-component and per-net reconciliation. A standing mutation corpus proves the reconciliation bites on exactly the classes it exists for — wholesale renumbering, reused refdes, and dropped nets — with the clean netlist passing every check (anti-vacuity).

### Problem Frame

The current identity check (`io/design_bundle_preflight.py::preflight_identity`) compares refdes sets at a 95% overlap threshold. A wholesale renumber is a permutation of the same refdes set, so it passes by construction. A reused designator is invisible to set comparison: on the current board, refdes `C27` names the tank cap (`tank.c_tank3`, Sheetpath property at `pcb/temper.kicad_pcb` line 1307), while the design netlist's `C27` is a different component (`ct_sense.c_filter`) — one ref, two components. A dropped net changes connectivity but not the refdes set. The tank-capacitor class — a netlist component the board does not place in outline — commits silently because nothing compares per-component identity or placement. Ground truth on the current board: `tank.c_tank3` / board `C27` IS present in `pcb/temper.kicad_pcb`, staged off-outline; the defect is placement, not file absence. This is the incident class the handoff records: "Match components by sheetpath, not refdes."

### Requirements

- R16. **Netlist↔board reconciliation oracle** (Oracle / Board / P1): the netlist extracted from the actual board file is compared against the design netlist — wholesale renumbering, missing components, and the tank-capacitor class fail regardless of refdes overlap. Seed: `packages/temper-placer/src/temper_placer/validation/preflight.py`. (verbatim from origin)
  - Success signal: wholesale renumbering, missing components, and the tank-capacitor class each produce a failing reconciliation, independent of any refdes overlap.
- R39. **Netlist-mutation testing** (Injection / Board / P2): wholesale renumbering, dropped nets, and reused refdes are injected and preflight must fail — identity checks are proven against the classes they exist for. (verbatim from origin)
  - Success signal: wholesale renumbering, dropped nets, and reused refdes each fail preflight when injected, and the unmutated netlist passes.

### Key Technical Decisions

- KTD1. **Identity is keyed by sheetpath and instance path, not refdes** — the `elec/domain_manifest.yaml` and `scripts/resync_pcb_netlist.py` convention; refdes is positional, reusable, and set-overlap blind (handoff lesson).
- KTD2. **The design authority is the compiled netlist behind a freshness gate** — `elec/build/default.net` with `check_domain_partition.check_netlist_freshness`; the same authority the identity and domain gates read, so no third netlist opinion.
- KTD3. **The oracle is a new module and gate script; `preflight_identity` stays as a secondary signal** — the overlap check is not deleted but is no longer the identity authority.
- KTD4. **Wholesale renumbering is modeled as a set-preserving permutation** — its owning check is the sheetpath reconciliation, because the 95% refdes-overlap check passes it by construction.
- KTD5. **The dropped-net class is owned by net-level membership reconciliation** — per-net membership diffs (a net whose node set differs between board and design) are in scope for the oracle, giving the dropped-net mutation class its owning check.
- KTD6. **The mutation corpus is a standing CI check with anti-vacuity** — the clean netlist passes every identity check; the corpus-runner shape follows the R38/R19 corpus runners rather than a new pattern.

### Assumptions

- Seed discrepancy: `validation/preflight.py` contains no netlist↔board comparison today. The existing identity machinery is `io/design_bundle_preflight.py::preflight_identity`, `scripts/ci_identity_check.py`, `scripts/resync_pcb_netlist.py` (sheetpath-keyed reconciliation), and `scripts/check_domain_partition.py::parse_netlist` (design netlist). The plan anchors on those and adds the reconciliation as a new preflight check, so `run_all_preflight_checks` remains the entry surface.
- Board footprints carry the Sheetpath property (per `resync_pcb_netlist.py`); a footprint without a Sheetpath is reported as un-keyable, never matched by guess. Un-keyability is exercised by synthetic tests — the current board has a Sheetpath on every footprint, including the tank cap at line 1307.
- Tank-capacitor class ground truth: `tank.c_tank3` / board `C27` IS present in `pcb/temper.kicad_pcb` (Sheetpath property, off-outline). The current-board verdict for the missing-component finding is therefore PASS-for-missing. The off-board staging is a containment defect owned by the R26 plan (`docs/plans/2026-08-02-022-feat-formal-board-property-verification-plan.md`); the missing-component bite-proof comes from the mutation suite, not the current board.
- "Preflight" spans `run_all_preflight_checks`, `preflight_identity`, and the reconciliation oracle; the corpus asserts failure across this set per class.
- A "dropped net" mutation removes a net's nodes from the design netlist; a "reused refdes" mutation assigns one ref to two components.
- The mutation-corpus units depend on the reconciliation units (in-plan ordering): until the net-level membership reconciliation lands, the corpus records the dropped-net class as pending, never silently skipped.

---

## Implementation Units

Unit mapping (per the merge map in `docs/evidence/2026-08-02-validation-portfolio-review.md`, 025 → 021): surviving 021 U1–U4 keep their IDs; absorbed 025 U1→U5, 025 U2+U4→U6, 025 U3→U7. 025's renumber-class proof folds into U6; 025's renumber/reuse mutation classes are the language-identical bite-proof tests already carried by surviving U4.

### U1. Board-netlist extraction

**Goal:** extract a comparable netlist from `pcb/temper.kicad_pcb`: components with ref, footprint, Sheetpath, and pad-to-net assignments, plus nets.

**Requirements:** R16.

**Dependencies:** none.

**Files:** `packages/temper-placer/src/temper_placer/validation/netlist_reconciliation.py` (new), `packages/temper-placer/src/temper_placer/io/kicad_parser.py` (extend if needed), `packages/temper-placer/tests/validation/test_netlist_reconciliation.py` (new).

**Approach:** Build the board-side netlist from the parsed board model (`parse_kicad_pcb_v6`) using the existing `ParsedPCB.netlist`, adding Sheetpath per footprint (the property `resync_pcb_netlist.py` already writes). Normalize both sides to a common comparison shape.

**Patterns to follow:** the comparison shape in `io/design_bundle_preflight.py`; the Netlist shape in `scripts/check_domain_partition.py::parse_netlist`; the sheetpath handling in `resync_pcb_netlist.py`.

**Test scenarios:**
1. Parsing the current `pcb/temper.kicad_pcb` yields a component list where every footprint resolves a ref and a Sheetpath (the tank cap is present: board `C27` resolves Sheetpath `tank.c_tank3`).
2. A synthetic component with no Sheetpath is flagged as un-keyable, not silently dropped.
3. Pad-to-net extraction matches the board's net table: every pad's net ordinal resolves to the net name.

**Verification:** extraction output is deterministic across two parses of the same board file.

### U2. Sheetpath-keyed and net-level reconciliation

**Goal:** compare board components against design netlist components by instance path, producing missing (design-only), extra (board-only), renumbered (same path, different ref), and ref-reuse findings; and compare per-net membership, producing net-level findings for nets whose node sets differ between the two sides.

**Requirements:** R16, including the net-level membership extension that owns the dropped-net class of R39.

**Dependencies:** U1.

**Files:** `packages/temper-placer/src/temper_placer/validation/netlist_reconciliation.py`, `packages/temper-placer/tests/validation/test_netlist_reconciliation.py`.

**Approach:** Load the design netlist via `check_domain_partition`'s parser behind the freshness gate. Key both sides by instance path. A path present in design but absent in the board is a missing component (tank-capacitor class). A path present in both with different refs is a renumber. Two board components sharing a ref is a reuse. A net present in design but absent in the board, or a net whose design-side node set differs from the board side, is a net-level membership finding (dropped-net class). Report each as a finding with severity.

**Patterns to follow:** the manifest-keyed verification in `check_refdes_identity_stability.py`; `scripts/check_domain_partition.py::parse_netlist`.

**Test scenarios:**
1. A synthetic design component at instance path X with no board counterpart yields a MISSING finding naming the path and ref (tank-capacitor class; on the current board this class is PASS-for-missing because `tank.c_tank3` is present off-outline).
2. The same instance path with a different ref on each side yields a RENUMBERED finding naming both refs.
3. Two board components with the same ref yield a REUSE finding.
4. A board component with no design counterpart yields an EXTRA finding.
5. A net whose design-side node set differs from the board side yields a NET-MEMBERSHIP finding naming the net and the differing nodes (dropped-net class).
6. A net present in design with no board counterpart yields a NET-MISSING finding.
7. An identical board and design netlist yield zero findings.

**Verification:** the reconciliation over the real board and a fresh design netlist reports zero findings on the current pair (PASS-for-missing on the tank-cap class) and zero false positives on components that match by path; each synthetic class is caught by its owning finding.

### U3. Reconciliation gate and CI wiring

**Goal:** a gate fails on any missing, extra, renumbered, reused, or net-level membership finding, wired into the board gates job, with preflight as the entry surface.

**Requirements:** R16.

**Dependencies:** U2.

**Files:** `scripts/check_netlist_board_reconciliation.py` (new), `scripts/manifest.yaml` (entry), `packages/temper-placer/src/temper_placer/validation/preflight.py` (extend `run_all_preflight_checks`), `packages/temper-placer/tests/validation/test_preflight.py` (extend).

**Approach:** Add a preflight check that runs the U2 reconciliation and produces ERROR findings for each class. Add a check script wrapping it for CI, with fail-closed exit codes and a freshness gate on the design netlist. Register the script in `scripts/manifest.yaml`.

**Patterns to follow:** the production-board invocation in `scripts/ci_identity_check.py`; the exit-code contract in `scripts/check_drc_ceiling_approval.py`; the `scripts/manifest.yaml` convention.

**Test scenarios:**
1. `run_all_preflight_checks` over the real board and a fresh netlist reports zero reconciliation findings (the tank-cap class is PASS-for-missing on the current board; the off-board staging is a containment finding owned by the R26 gate, not this reconciliation).
2. The check script exits non-zero when any reconciliation class fires and zero when the board and netlist agree.
3. A stale design netlist fails closed (GATE ERROR) rather than comparing against an old design.

**Verification:** the gate's verdict on the current board is documented (PASS-for-missing on the tank-cap class, per the portfolio's known-finding registry convention), and the script has a `scripts/manifest.yaml` entry.

### U4. Component-level bite proof against the mutation classes

**Goal:** wholesale renumbering, dropped components, and reused refdes are each proven to fail the reconciliation gate at the unit level.

**Requirements:** R16.

**Dependencies:** U3.

**Files:** `packages/temper-placer/tests/validation/test_netlist_reconciliation_mutations.py` (new).

**Approach:** Apply deterministic seeded mutations to a parsed board or netlist copy — a refdes permutation preserving the refdes set, a dropped component, a duplicated ref — and assert the reconciliation reports the class and the gate fails. This is the component-level half of the standing mutation suite; the netlist-level harness and corpus runner are U5–U7.

**Patterns to follow:** the scratch-mutation-and-revert precedent in `scripts/tests/test_gen_repo_state.py`; the R38 board-defect corpus shape.

**Test scenarios:**
1. A wholesale renumber (permutation of refs within a prefix) yields RENUMBERED findings and a failing gate, even though the refdes set is unchanged.
2. Removing one component from the board side yields a MISSING finding and a failing gate.
3. Assigning one ref to two components yields a REUSE finding and a failing gate.
4. The unmutated board and netlist still pass (anti-vacuity).

**Verification:** the mutation suite passes and the anti-vacuity control passes on the clean pair.

### U5. Netlist mutation harness

**Goal:** deterministic seeded mutations over the parsed compiled design netlist: a wholesale renumber (set-preserving permutation), a dropped net, and a reused refdes.

**Requirements:** R39.

**Dependencies:** none.

**Files:** `scripts/netlist_mutator.py` (new), `scripts/manifest.yaml` (entry), `scripts/tests/test_netlist_mutator.py` (new).

**Approach:** Parse `elec/build/default.net` with `check_domain_partition`'s parser. Apply one named mutation to a copy: permute refs within a prefix (renumber), remove a net's nodes (dropped net), or duplicate a ref across two components (reuse). Record the seed and the mutated netlist shape deterministically.

**Patterns to follow:** `scripts/check_domain_partition.py::parse_netlist`; the ref-prefix discovery in `scripts/check_refdes_identity_stability.py`; the scratch discipline in `scripts/tests/test_gen_repo_state.py`.

**Test scenarios:**
1. The renumber mutation permutes refs within one prefix and preserves the refdes set exactly.
2. The dropped-net mutation removes exactly one net's nodes and changes no other net.
3. The reused-refdes mutation makes exactly two components share one ref.
4. Two runs with the same seed produce identical mutations.
5. Each mutation on the current netlist produces a parseable mutated netlist.

**Verification:** the harness unit tests pass, and each mutation is minimal and named.

### U6. Netlist-mutation corpus assertions

**Goal:** run the identity check set against each mutation and assert the owning check fails per class; document the class-to-check mapping, including the overlap-blind renumber class and the dropped-net class's net-level owner.

**Requirements:** R39.

**Dependencies:** U5 (and U2/U3 in-plan, the reconciliation oracle as kill oracle).

**Files:** `scripts/tests/test_netlist_mutation_corpus.py` (new), `packages/temper-placer/tests/validation/test_netlist_reconciliation_mutations.py` (extend), `docs/evidence/2026-08-02-netlist-renumber-proof.md` (new).

**Approach:** For each mutation, run the identity check set (`preflight_identity`, `run_all_preflight_checks`, and the U2/U3 reconciliation). Assert the owning check fails: dropped net → net-level membership finding; reused refdes → REUSE finding; renumber → the sheetpath oracle's RENUMBERED finding (the overlap check alone cannot fail it). Record which check owns which class. The renumber case is the corpus's headline class: assert the overlap check passes while the sheetpath oracle fails, and record the demonstration in the evidence doc.

**Patterns to follow:** the reconciliation's mutation tests; the verification tiers in `scripts/check_refdes_identity_stability.py`; the provenance conventions for `docs/evidence`.

**Test scenarios:**
1. The dropped-net mutation fails the reconciliation with a NET-MEMBERSHIP finding naming the missing net.
2. The reused-refdes mutation fails the reconciliation with a REUSE finding naming the ref.
3. The renumber mutation fails the sheetpath oracle with RENUMBERED findings.
4. The renumber mutation passes `preflight_identity`'s 95% overlap check, documenting that the overlap check structurally cannot see this class.
5. The unmutated netlist passes every check (anti-vacuity).
6. The evidence doc records the exact renumber permutation and both check verdicts.

**Verification:** the assertion tests pass, the class-to-check table is documented, and the evidence doc is committed with provenance.

### U7. Corpus runner and CI wiring

**Goal:** a standing check that rebuilds a fresh netlist, applies the corpus, and asserts the failures; wired into CI with a manifest entry.

**Requirements:** R39.

**Dependencies:** U6.

**Files:** `scripts/check_netlist_mutation_corpus.py` (new), `scripts/manifest.yaml` (entry), `.github/workflows/` (board gates job).

**Approach:** The runner reuses the corpus-runner shape of the R38 board-defect corpus (`scripts/check_board_defect_corpus.py`) and the R19 incident corpus (`scripts/check_incident_corpus.py`) rather than introducing a new pattern: per-class expected-failing check, anti-vacuity control on the clean artifact, fail-closed on a missing tool or stale input. It enforces netlist freshness, applies each mutation, runs the identity check set, and fails the run if any class is uncovered or any check fails on the clean netlist. Wire it into the board gates workflow; follow the actionlint convention.

**Patterns to follow:** the freshness gate in `scripts/check_domain_partition.py`; the anti-vacuity discipline of `scripts/check_vacuous_gates.py`; the corpus-runner shape of `scripts/check_board_defect_corpus.py` and `scripts/check_incident_corpus.py`; the `scripts/manifest.yaml` convention.

**Test scenarios:**
1. A stale netlist fails the runner closed (GATE ERROR), never a clean pass.
2. A mutation class whose owning check passes fails the corpus run as uncovered.
3. The clean netlist passes every check (anti-vacuity control).
4. The workflow passes actionlint.

**Verification:** the corpus passes with all three classes covered, and the CI job runs it.

---

## Verification Contract

- `uv run pytest packages/temper-placer/tests/validation/test_netlist_reconciliation.py packages/temper-placer/tests/validation/test_netlist_reconciliation_mutations.py scripts/tests/test_netlist_mutator.py scripts/tests/test_netlist_mutation_corpus.py` passes.
- `uv run --no-sync python scripts/check_netlist_board_reconciliation.py` passes on the current board (PASS-for-missing on the tank-cap class) and fails closed on a stale netlist.
- `uv run --no-sync python scripts/check_netlist_mutation_corpus.py` passes with all three classes covered and the clean netlist green.
- `uv run python scripts/import_linter_gate.py` passes.
- No new zero-coverage public functions in `temper_placer/` (reconciliation and corpus code are exercised by tests).
- New scripts have `scripts/manifest.yaml` entries; the workflow passes actionlint.

---

## Definition of Done

- Reconciliation reports missing, extra, renumbered, reused, and net-level membership findings keyed by instance path and net.
- The tank-capacitor class ground truth is recorded: `tank.c_tank3` / board `C27` is present off-outline, so the reconciliation's current-board verdict is PASS-for-missing; the off-board staging is owned by the R26 plan.
- Wholesale renumbering, dropped nets, and reused refdes each fail preflight when injected; the renumber class is proven to fail the sheetpath oracle while passing the overlap check.
- The clean netlist passes every identity check (anti-vacuity).
- New scripts have `scripts/manifest.yaml` entries.
- Dead-end or experimental code from implementation is removed from the diff.

---

## Scope Boundaries

- `preflight_identity`'s 95% overlap check stays but is demoted to a secondary signal, not the identity authority.
- The oracle reports reconciliation failures; it does not fix the board.
- The corpus mutates netlist copies; it never edits `elec/src` or the committed netlist.
- The corpus proves checks bite; it does not fix the identity checks' blind spots beyond the reconciliation oracle.

### Deferred to Follow-Up Work

- Replacing `preflight_identity` entirely — deferred until the reconciliation oracle has bite-proven history.
- Injecting mutations into the compiled board netlist (board-side identity) — owned by the R38 board-defect corpus (`docs/plans/2026-08-02-024-feat-board-defect-mutation-corpus-plan.md`).
- Hardening the reconciliation gate and the mutation corpus to merge-blocking — pending bite-proven history and branch-protection rollout.

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` (R16, R39)
- `docs/evidence/2026-08-02-validation-portfolio-review.md` (021/025 verdicts, ground-truth corrections, merge map)
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` (sheetpath-not-refdes lesson; refdes reuse; tank-cap ground truth)
- `packages/temper-placer/src/temper_placer/io/design_bundle_preflight.py` (preflight_identity, 95% overlap)
- `packages/temper-placer/src/temper_placer/validation/preflight.py` (R16 seed)
- `scripts/ci_identity_check.py` (production identity invocation)
- `scripts/check_domain_partition.py` (design netlist parser and freshness gate)
- `scripts/resync_pcb_netlist.py` (sheetpath-keyed reconciliation)
- `scripts/check_refdes_identity_stability.py` (identity verification tiers)
- `scripts/check_vacuous_gates.py` (anti-vacuity discipline)
- `packages/temper-placer/src/temper_placer/io/kicad_parser.py` (parse_kicad_pcb_v6)
- `docs/plans/2026-08-02-024-feat-board-defect-mutation-corpus-plan.md` (R38 corpus-runner shape)
- `docs/plans/2026-08-02-032-feat-incident-corpus-oracle-plan.md` (R19 corpus-runner shape)
- `docs/plans/2026-08-02-022-feat-formal-board-property-verification-plan.md` (R26 owner of the off-board staging)
