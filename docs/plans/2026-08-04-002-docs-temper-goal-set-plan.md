---
title: Temper Goal Set - Plan
type: docs
date: 2026-08-04
topic: temper-goal-set
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# Temper Goal Set - Plan

## Goal Capsule

- **Objective:** Define the goal set that carries this project to a Temper board file worth signing off on — five goals covering the Rust consolidation, the WASM verification tier, scaled DRC/ERC checking, board design completeness, and geometric convergence. This plan sets the goals and their done conditions; it does not schedule them.
- **Product authority:** temper maintainer.
- **Open blockers:** The board-design goal (R11–R15) is design and procurement work, not a coding task, and `docs/STRATEGY.md` states it should not be delegated to an agent. Whether scaled checking runs per-change or continuously is unresolved and is recorded under Outstanding Questions.

---

## Product Contract

### Summary

Five goals. The Rust consolidation, the WASM verification tier, and scaled DRC/ERC checking are the machine; a complete protection chain and convergence to zero violations are the outcome. The terminal artifact is a board file the maintainer would authorize for fabrication — not fabricated hardware.

### Problem Frame

`docs/STRATEGY.md` records that the critical path is design completion and that the board cannot be fabricated: of seven protection gates, three are fixed and none are validated on hardware; OVP-01 senses the half-bus and can never trip; IGBT desaturation protection does not exist while nineteen BOM lines cost it; the BOM is unusable in both directions; and the router's output carries roughly 120 shorts and 499 clearance violations. It also records that four SPICE runs found more real defects than a month of router work.

The same document declared the verification layer "not trustworthy yet, but now honest," and that claim has decayed since. Creepage is dropped when netclass rules convert to the router's internal shape, is read back as `0.0`, and is never passed to the one function that would consume it — so a 6.0 mm creepage requirement is reserved only coincidentally, because the netclass declares an equal `clearance`. The gate that would catch this measures a board file with no design-rule sidecar beside it, so `creepage` cannot appear as a category at all. The `kicad-cli` oracle every DRC baseline is measured against was installed unpinned from a rolling PPA and had already moved. Of thirty `continue-on-error` masks across the workflows, twenty-seven carry ticket ids the repository itself documents as placeholders.

Underneath both is a structural gap: there is no goal set, so effort flows to whatever is most legible rather than to what advances a gate. Work on throughput and tooling can run indefinitely without moving the board closer to fabrication, and nothing in the repository currently says so.

### Key Decisions

- **D1. Board correctness splits into design completeness and geometric verification.** (session-settled: user-directed — chosen over a single "converge on a correct board" goal: no checker finds a circuit that was never designed, so bundling them hides the design work behind a verification loop that cannot surface it.) Governs R11–R15, R16–R18.
- **D2. Done means zero violations measured on gates proven to bite.** (session-settled: user-directed — chosen over volume targets alone and over zero alone: a gate that cannot fail cannot certify zero, and counts that rise because an instrument improved are expected mid-flight.) Governs R9, R10, R16, R17.
- **D3. The deliverable is a board file worth authorizing, not fabricated hardware.** (session-settled: user-directed — chosen over carrying through to a board in hand: fabrication and bench validation form the next horizon and would make every goal here harder to judge.) Governs Scope Boundaries.
- **D4. The verification tier does not wait on the Rust consolidation.** (session-settled: user-approved — chosen over strict sequencing: the kernels the tier runs are already Rust, with twelve of fourteen crates compiling to `wasm32`; the consolidation's remaining surface is orchestration, contracts and IO, none of which the tier executes.) Governs R4, R5.
- **D5. `kicad-cli` remains the reference oracle.** (chosen over replacing it with the Rust suite once that suite is fast: interval-based equivalence has to be demonstrated before the reference can be retired, and the Rust suite is the thing under test.) Governs R6, R8.
- **D6. Deprecation is staged, and deleting a differential requires proving its replacements catch what it caught.** (session-settled: user-directed — chosen over deleting a Python shim as soon as its migration lands: the migration's evidence *is* the pinned oracle, so removing it discards the proof that justified the migration. Chosen also over keeping every oracle forever, which would make the consolidation permanent.) Governs R19–R22.

### Requirements

**Rust consolidation**

- R1. Every remaining Python surface reaches a recorded verdict: migrated, retired, or justified-keep.
- R2. Each migration carries both a behavioral A/B and a performance A/B, and both pass before merge.
- R3. A justified-keep names a blocker or a measured verdict; consolidation alone never suffices.

**Verification substrate**

- R4. The pure-Rust rule and property kernels execute as WASM off the shared CI concurrency pool.
- R5. Every finding names the exact artifact it came from by content hash.
- R6. The reference oracle is retired only once the Rust suite demonstrates interval-based equivalence with it.

**Scaled checking**

- R7. Sustained DRC and ERC check volume exceeds what the reference oracle can sustain by at least an order of magnitude.
- R8. The board the tier checks is regenerated from the committed placement, so the input changes when the harness changes.
- R9. Every safety-critical constraint — creepage, clearance, isolation, courtyard, high-voltage separation — has a gate that is demonstrated to fail against a seeded defect.
- R10. A coverage claim is reported as vacuous unless it carries a demonstrated failing case.

**Board design completeness**

- R11. IGBT desaturation protection exists as a designed circuit.
- R12. OVP-01 senses a reference that can trip.
- R13. OCP-02 and THM-02 each have a designed circuit.
- R14. The BOM reconciles against source in both directions, with no costed line lacking a circuit and no wired component uncosted.
- R15. Every footprint required for fabrication is drawn.


**Deprecation**

- R19. A migrated surface passes through three states, and only the first two are reached by a migration landing: the Python module becomes a delegation shim; its pre-migration implementation is retained as the differential's pinned oracle; the shim and oracle are removed. The third is a separate, evidenced decision.
- R20. A differential is removed only when the property and metamorphic suites are shown to catch every mutant it caught. Re-run the migration's mutation campaign with the differential disabled; any mutant that survives keeps the differential.
- R21. A delegation shim is removed only when no consumer imports it, demonstrated by the import gate rather than by search.
- R22. A surface carrying a JUSTIFIED-KEEP verdict is never deprecated while its blocker holds; a deprecation attempt against one is a request to re-decide the verdict under R3, with new evidence.

**Board geometric correctness**

- R16. DRC and ERC violations reach zero on the production board.
- R17. That zero is measured on gates satisfying R9.
- R18. Baselines and thresholds are measured in the environment that enforces them, against a pinned oracle.

### Acceptance Examples

- AE1. **Covers R9, R10.** A gate reports full coverage of a constraint family but no seeded defect has been shown to trip it. The tier reports the coverage claim as vacuous rather than as passing.
- AE2. **Covers R16, R17.** Violations reach zero while one safety-critical constraint's gate has never been demonstrated to fail. The zero does not satisfy the goal, because R17 is unmet.
- AE3. **Covers R18.** A threshold is measured on a maintainer workstation and enforced inside the CI container, and the two environments disagree. The threshold is not considered measured until it is taken where it is enforced.
- AE4. **Covers R9, R16.** A constraint's gate begins applying rules it previously ignored, and the violation count rises. The rise is attributed to the instrument and does not count as a regression, but the goal remains unmet until the count returns to zero.
- AE5. **Covers R11–R13.** The board reaches zero DRC and ERC violations while desaturation protection is still absent. The design-completeness goal is unmet; geometric convergence does not substitute for it.

- AE6. **Covers R20.** A migration's differential has passed continuously and its oracle is proposed for deletion. The mutation campaign is re-run with the differential disabled and one mutant survives, caught previously only by the differential. The oracle stays, and the surviving mutant names the property that is missing.
### Scope Boundaries

- Fabrication, bench validation of the protection gates, and calibrated physics models validated against measurement — the next horizon, and the reason D3 stops at a board file.
- Generalizing the check corpus to a second appliance. `docs/STRATEGY.md` names the corpus as the moat and the cooker as instance #1; carrying the corpus to appliance #2 is beyond this goal set.
- Migrating CI execution to Cloudflare containers-as-runners. Its own trigger is a slow-lane speed threshold that measurement has already cleared, so any remaining case rests on queue contention and is a separate decision.
- Autorouter quality work beyond what R16 requires. `docs/STRATEGY.md` records that place-and-route was not the bottleneck.

### Dependencies / Assumptions

- The Rust consolidation and the verification tier are independent workstreams; only the tier's own substrate proof gates its scaled checking (D4).
- Board design completeness (R11–R15) depends on neither, and is design and procurement work rather than a coding task.
- Every requirement measuring a count assumes a pinned oracle. Without R18, no threshold in this document is meaningful.
- The tier's scaled checking assumes an input that changes when the harness changes (R8); a single sweep of a static artifact answers a question that expires.

### Outstanding Questions

**Resolve Before Planning**

- Q1. Does scaled checking run per change or continuously? The tier was chosen over containers precisely because checking must be continuous and off the shared pool; running it per change reintroduces the coupling it was chosen to escape.
- Q2. Does the board-design goal (R11–R15) proceed in parallel with the verification goals, or does it wait? It shares no dependency with them, but it is the only goal that cannot be delegated.

**Deferred to Planning**

- Q3. Which memory strategy carries the tier below production resolution, given the isolate memory ceiling.
- Q4. Whether the committed-board constants and the DRC ceiling file need the same environment re-measurement as the router-output constants, since they were seeded the same way.
- Q5. Whether creepage is carried into the router's internal rule shape or enforced through a separate path.

<!-- ce-section: work-relationships -->
### How This Work Fits Together

This plan owns the goal set and its done conditions. The breakdown below is the current understanding, not a committed roadmap; later plans may revise, split, merge, or discard any of it.

- Rust consolidation — governed by `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`. Can proceed independently of the verification goals (D4). Enables the eventual retirement of the Python surface the tier does not execute.
- Verification substrate and scaled checking — governed by `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`. Depends on board regeneration (R8), scoped in `docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md`. Enables geometric convergence by making the checking affordable.
- Board design completeness — depends on none of the above. Still to decide: whether it runs in parallel (Q2).
- Board geometric correctness — depends on scaled checking for its evidence and on a pinned oracle for its measurements. Shares the DRC burn-down surface with `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md`.

### Sources / Research

- `docs/STRATEGY.md` — the critical-path reversal, the seven-gate status, the missing desaturation protection, the BOM's two-directional gap, and the statement that the corpus rather than the router is the moat.
- `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` — the consolidation's phases, its discipline contract, and the solver-boundary decision gate.
- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — the tier's requirements, including content-hash addressing and the anti-vacuity rule this document adopts as R10.
- `docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` — what regeneration consists of, and the finding that the build chain contains no placement step.
- `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` — the measured DRC error count and its category breakdown.
- `docs/evidence/2026-08-04-board-regeneration-cost.md` — measured regeneration cost, and the router entry points that do and do not execute.
- `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py` — where creepage is dropped converting to the router's internal rule shape.
- `packages/temper-placer/src/temper_placer/validation/_drc_api.py` — why the all-track-errors flag is load-bearing for measurement determinism.
