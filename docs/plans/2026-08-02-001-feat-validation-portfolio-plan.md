---
title: Validation Portfolio - Plan
type: feat
date: 2026-08-02
topic: validation-portfolio
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# Validation Portfolio - Plan

## Goal Capsule

**Objective:** A prioritized, evergreen portfolio of new validation ideas organized in three tiers (oracle differential, formal guarantees, failure injection) across six domains (placer physics, placer geometry, solve quality, board fab, firmware, CI), giving the long-term goal chain — provably correct placer → fab-ready board → firmware safety → trustworthy CI — a concrete iteration loop.

**Product authority:** temper-placer and firmware maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none — the portfolio is a menu; each idea becomes plannable when pulled.

---

## Product Contract

### Summary

This plan is the menu the project's long-term goals iterate against. It catalogs ~35 new validations as requirements, each assigned one tier (oracle differential / formal guarantees / failure injection), one domain, a priority, and a success signal, anchored to existing machinery. Each idea is pull-to-plan: when capacity allows, an idea is taken from the menu and planned individually.

### Problem Frame

The project already runs one of the densest validation programs in its class — ~40 `check_*.py` gates, 25 CI workflows, BMC-exhaustive physics constraints, PBT and metamorphic suites, induction proofs in four Rust crates, a Wave 4 discipline contract (behavioral A/B + performance A/B per migration). The failures still land. Since July, 1,384 fix commits include a rotation-sign error across 12 call sites that unmasked 102 safety violations, a domain-clearance bbox constraint that was not copper-aware, a courtyard check reporting zero collisions where real DRC found 43, unsound constraint encodings (`weak-nooverlap2d`, `atmostk`, `endpoint-bounding`), a tank capacitor staged off the board while firmware's `PLL_MIN_FREQ_HZ` assumes its 300 nF, and a real C1↔R7 short confirmed in 120/120 DRC runs — with branch protection still disabled, so every gate is advisory.

Three patterns recur across these incidents. First, the abstract model diverges from reality and nothing re-checks it. Second, constraint encodings are trusted until a human reads them closely. Third, gates are trusted to bite until a bug slips through. The long-term goals (provable placer, fab-ready board, safe firmware, trustworthy CI) need an iteration loop, and the loop is validations — checks the project can run and iterate against as goals mature. The existing machinery provides seeds for every tier; what does not exist is the menu that names the checks and their success signals.

### Key Decisions

- D1. **Three-tier structure** (session-settled: user-directed — chosen over oracle-only, formal-first, and injection-first single-emphasis portfolios): oracle differential is the backbone (widest bug class, best seed coverage), failure injection is the trust layer, formal guarantees apply where cheapest (constraint encodings). Governs R1, R5.
- D2. **Forward-looking framing** (session-settled: user-directed — chosen over an incident-anchored portfolio): incidents motivate the tiers, they do not define the ideas; each idea is stated as a check the pipeline runs. Governs R3.
- D3. **Evergreen prioritized menu** (session-settled: user-directed — chosen over a funded roadmap with committed schedule): matches the Wave 4 governance pattern (gated roadmap, opportunistic execution, R5). Governs R4.
- D4. **Full goal chain, four areas** (session-settled: user-directed — chosen over placer-only scope and over adding an agent-scale guardrails section): placer, board, firmware, and CI, with the placer stack split into three catalog domains (physics, geometry, solve quality) and board into fab — six catalog domains in all. Agent-scale remains context, not content. Governs R2, R6.
- D5. **Goal ordering sets budget weighting** (session-settled: user-directed): the provable-placer → fab-ready-board pair receives at least half the catalog; firmware and CI receive their own tiers with less budget. Governs R6.
- D6. **Catalog cap for scannability** (session-settled: user-directed — roughly two ideas per tier-domain cell, priorities P1–P3): "broad" is capped so the menu stays scannable and new ideas replace low-priority ones. Governs R5.

### How This Work Fits Together

<!-- ce-section: work-relationships -->

This plan owns the validation portfolio — the menu of new checks. The surrounding work is the current understanding, not a committed roadmap:

- The portfolio serves the long-term goal chain (provable placer → fab-ready board → firmware safety → CI trust); the goal ordering is inherited from the brainstorm that produced this plan.
- Individual ideas are pulled from this menu into separate plans as capacity allows; each pull reuses this plan's success signals as its acceptance criteria.
- The Wave 4 migration program is a sibling validation program: its discipline contract (behavioral A/B, performance A/B, PBT, metamorphic, induction proofs) is reused as seed machinery for the formal tier.
- The existing gate inventory (~40 check scripts, 25 workflows) is the substrate every idea anchors to.
- Agent-scale guardrails (multi-contributor enforcement) are still to decide as a separate area; not part of this portfolio.

### Requirements

#### Portfolio contract

- R1. The portfolio is organized in three tiers — oracle differential (Tier 1), formal guarantees (Tier 2), failure injection (Tier 3) — and every idea carries exactly one tier assignment.
- R2. The catalog covers six domains along the goal chain: placer physics, placer geometry, solve quality, board fab, firmware, CI.
- R3. Every idea is framed forward-looking as a check the pipeline runs, never as a response to a named incident; incidents motivate tiers, they do not define ideas.
- R4. The portfolio is an evergreen prioritized menu: every idea carries a priority (P1 / P2 / P3), and no schedule or sequencing is committed.
- R5. The catalog is capped at roughly two ideas per tier-domain cell (about 35 total) to stay scannable; a new idea replaces a lower-priority one rather than extending the list.
- R6. Budget is placer-heavy per the goal ordering: placer and board domains together receive at least half the catalog.
- R7. Every idea names its success signal — the observable that proves the check bites — so a cold reader can pull it into planning without inventing behavior.
- R8. Every idea anchors to existing machinery (validation modules, check scripts, plans, conventions) as its seed, named by repo-relative path.

#### Tier 1 — Oracle differential (validate the validators)

- R9. **Thermal solver oracle differential** (Oracle / Physics / P2): every solve's thermal scorer output is compared against an MFEM reference solve on a subsampled grid — drift beyond a measured bound fails the run. Seed: `packages/temper-placer/src/temper_placer/validation/mfem_compare.py`.
- R10. **SPICE estimator oracle differential** (Oracle / Physics / P2): fast estimator outputs are periodically re-derived against a full reference solve on representative snapshots — estimator error bounds are measured, not assumed. Seed: `packages/temper-placer/src/temper_placer/validation/spice_pipeline.py`.
- R11. **Full-board DRC oracle differential** (Oracle / Geometry / P1): every committed placement is re-run through real `kicad-cli` DRC (all-track-errors, sampled per the ceiling convention) and the placer's internal clearance/courtyard models are compared violation-by-violation — the "model says zero, real DRC says 43" class fails at commit time. Seed: `packages/temper-placer/src/temper_placer/validation/drc_oracle.py`.
- R12. **Transform round-trip oracle** (Oracle / Geometry / P1): every placement write is re-parsed and pad geometry compared against the solver's model — the rotation-convention class (sign error across call sites, un-applied solved rotation) cannot ship. Seed: `docs/evidence/2026-07-30-placement-writer-rotation.md`.
- R13. **Quality-vs-human oracle** (Oracle / Solve quality / P2): extracted human reference layouts are compared against solver output on functional-grouping and symmetry criteria — layout quality is measured against a human baseline, not self-scored. Seed: `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py`.
- R14. **Optimality lower-bound oracle** (Oracle / Solve quality / P3): a relaxation-based lower bound on the objective is computed per solve — a gap beyond a measured threshold flags weak search, separating "valid" from "good".
- R15. **Fab-rule oracle** (Oracle / Board / P2): the manufacturing ruleset (annular ring, solder mask, edge clearance) is layered as a second oracle on top of electrical DRC — fab-readiness is measured against fab rules, not only electrical rules.
- R16. **Netlist↔board reconciliation oracle** (Oracle / Board / P1): the netlist extracted from the actual board file is compared against the design netlist — wholesale renumbering, missing components, and the tank-capacitor class fail regardless of refdes overlap. Seed: `packages/temper-placer/src/temper_placer/validation/preflight.py`.
- R17. **Hardware-in-the-loop oracle** (Oracle / Firmware / P2): the state machine runs on real or emulated hardware against golden transition traces — every state/event pair is exercised outside host-based tests. Seed: `firmware/test/build/test_state_machine_only`.
- R18. **Firmware-assumption contract oracle** (Oracle / Firmware / P1): every firmware config constant with a board derivation (e.g., `PLL_MIN_FREQ_HZ` from tank capacitance) is reverse-checked against the actual board's components — hardware and firmware cannot disagree about a load-bearing value. Seed: `firmware/config.yaml`.
- R19. **Incident corpus oracle** (Oracle / CI / P1): every past incident is re-encoded as a seeded artifact (mutated board, mutated constraint, mutated workflow) that CI must fail on — the historical record becomes a permanent regression corpus. Seed: `scripts/check_vacuous_gates.py` and `docs/evidence/`.

#### Tier 2 — Formal guarantees (provable, not empirical)

- R20. **Soundness-proof register for physics encodings** (Formal / Physics / P1): every physics-gated constraint carries a Chebyshev-style soundness proof (conservative bound or classified approximation error) in one register — the R24 discipline becomes an inventory, not a policy. Seed: `docs/physics-verification-methodology.md`.
- R21. **BMC-exhaustive validation for all encodings** (Formal / Physics / P2): the BMC pattern extends from physics-gated constraints to every CP-SAT encoding — small-N exhaustive verification against a truthful oracle is the default, not the exception. Seed: `scripts/bmc_adoption_gate.py`.
- R22. **Induction-proof coverage for compute crates** (Formal / Geometry / P2): the `VERIFICATION.md` induction convention extends until every crate with recursive or computational structure carries a proof or an explicit non-applicability note — four crates today, all compute crates eventually. Seed: `packages/temper-geometry/VERIFICATION.md`.
- R23. **Transform-algebra exhaustiveness** (Formal / Geometry / P1): rotation/mirror transform composition is verified exhaustively over the finite angle set (enumerated or property-tested) — replacing the spot coverage of a convention that has already bitten twice.
- R24. **Post-solve audit for all constraints** (Formal / Solve quality / P1): the post-solve audit extends from physics-gated surfaces to every encoded constraint — actual values are recomputed post-solve and mismatches fail the run, closing the silent-constraint-drop seam class. Seed: `packages/temper-placer/src/temper_placer/placer/cp_sat/audit.py`.
- R25. **Optimality-gap certificate per solve** (Formal / Solve quality / P3): solver gap is reported and registered per solve with expected-gap bounds per problem class — a worsening gap beyond bound fails, distinguishing tuning drift from real regressions.
- R26. **Formal board-property verification** (Formal / Board / P2): board-level invariants (every net connected, every component inside the outline, pours reaching their nets) are machine-checked with exact graph algorithms rather than heuristics — the off-board-component class is structurally impossible to commit.
- R27. **DRC ceiling as monotone contract** (Formal / Board / P1): `power_pcb_dataset/drc_ceiling.json` raises require an attributed cause and a measured sample, formalized as a checked contract rather than a review convention. Seed: `scripts/check_drc_ceiling_approval.py`.
- R28. **Exhaustive state-machine model check** (Formal / Firmware / P2): the 8-state machine is checked for reachable unsafe states (heating while faulted, invalid transitions from every state) by exhaustive exploration over the transition table — unit tests cannot prove unreachability. Seed: `firmware/transition_table.yaml`.
- R29. **Firmware invariant proofs over the manifest** (Formal / Firmware / P2): load-bearing invariants (power stage disabled under over-temp, sensor fault blocks heating) are proved as state invariants over the machine-readable transition table — the manifest makes the proof machine-checkable.
- R30. **Proven non-vacuity for every CI gate** (Formal / CI / P1): every gate carries a demonstrated failing case (a seed artifact it must reject), upgraded from advisory vacuity checks to a per-gate canary contract. Seed: `scripts/check_vacuous_gates.py`.
- R31. **Closed-form trigger-path verification** (Formal / CI / P2): workflow triggers and required-check manifests are verified as a closed set — a path present in one manifest but not the other is a hard failure, preventing the branch-protection near-miss class. Seed: `scripts/check_required_checks.py` and `.github/required-checks.json`.

#### Tier 3 — Failure injection (every gate must have proven bite)

- R32. **Constraint mutation suite** (Injection / Physics / P1): each constraint encoding is mutated (sign flip, dropped term, loosened bound) and the mutation must fail the constraint's own tests or post-solve audit — every encoding carries its kill set.
- R33. **Physics-parameter injection** (Injection / Physics / P2): perturbed physics parameters (conductivity, convection, ampacity inputs) must be detected by downstream checks — parameter plumbing is proven live, not assumed.
- R34. **Geometry-kernel mutation testing** (Injection / Geometry / P2): geometry kernels (rotation, bbox, pad offsets) are mutated and the oracle differential must catch each mutation — the mutation suite doubles as a maintenance canary for the Rust migration.
- R35. **Writer-error injection** (Injection / Geometry / P2): transform errors are injected into the placement writer and the round-trip oracle must fail — the write path is held to the same standard as compute.
- R36. **Solution-quality mutation canaries** (Injection / Solve quality / P2): a known-good placement is perturbed (component moved, pair swapped) and quality metrics must move in the expected direction — monotonicity is asserted, not hoped.
- R37. **Dead-parameter injection** (Injection / Solve quality / P1): every gate input is wired then unwired and output must change — the dead-parameter sweep pattern becomes a standing check, not a one-off fix.
- R38. **Board-defect mutation corpus** (Injection / Board / P1): the real defect classes (component off-board, pad short, creepage crossing) are injected into a copy of the board and each must fail a gate — the gates that protect the board are proven on the actual board file.
- R39. **Netlist-mutation testing** (Injection / Board / P2): wholesale renumbering, dropped nets, and reused refdes are injected and preflight must fail — identity checks are proven against the classes they exist for.
- R40. **Transition-table mutation suite** (Injection / Firmware / P1): each transition in the manifest is mutated (wrong target, wrong guard) and the generated tests must fail — the codegen manifest makes mutation cheap and exhaustive. Seed: `firmware/test/gen_transition_table.py`.
- R41. **Firmware fault injection** (Injection / Firmware / P2): sensor faults and timing violations are injected into the running state machine and it must reach the designed safe state — safety behavior is demonstrated, not reviewed. Seed: `firmware/test/test_state_machine_only`.
- R42. **Gate-mutation testing** (Injection / CI / P1): each gate is weakened (threshold loosened, path removed) and its own canary must fail — the trust-the-trust layer proves gates bite. Seed: the incident corpus of R19.
- R43. **Trigger-path mutation** (Injection / CI / P2): a trigger path is removed from a workflow and the drift gate must fail — workflow coverage is proven live, not linted. Seed: `scripts/check_workflow_pr_triggers.py`.

### Key Flows

- F1. Pull an idea into planning
  - **Trigger:** capacity becomes available; an R from the catalog is selected.
  - **Covers:** R4, R7, R8
  - **Steps:** Read the idea's tier, domain, priority, success signal, and seed; plan the idea as its own unit; the seed anchors the first implementation unit.
  - **Outcome:** an implementation-ready plan per idea, with the success signal as its acceptance criteria and no invented behavior.

### Success Criteria

- A cold reader can pull any P1 idea into planning without inventing its success signal (per R7).
- Every idea's seed resolves to a repo path or documented convention (per R8).
- Priorities reflect the goal ordering: P1 items concentrate in the placer and board domains (per R5, R6).
- The menu stays under the ~35-idea cap as ideas are added (per R5).

### Scope Boundaries

**Deferred for later**

- Agent-scale guardrails (multi-contributor enforcement) — surrounding goal, not a portfolio section.
- A committed execution schedule — the menu is pull-to-plan (per R4).
- Implementation of any single idea — each is planned and delivered separately.

**Outside this portfolio's identity**

- Incident-anchored gates — incidents motivate tiers, ideas stay forward-looking (per R3).
- An exhaustive catalog of every possible validation — the cap is a feature (per R5).

### Outstanding Questions

**Deferred to Planning**

- Per-idea oracle divergence thresholds (R9, R11) — measured at pull time, not specified here.
- Mutation suite sizing per encoding (R32, R38) — proportional to encoding complexity, decided per idea.
- Which tier-domain cell gets the first pull — a capacity decision, not a scope decision.

### Sources / Research

- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` — the outstanding-defect and gate-state record that motivates the tiers.
- `docs/solutions/logic-errors/` — the unsound-encoding and model-divergence incident class (courtyard 0-vs-43, `weak-nooverlap2d`, `unsound-atmostk`, `endpoint-bounding`).
- `docs/evidence/2026-07-30-req-safe-01-102-triage.md` and `docs/evidence/2026-07-30-rotation-sign-remaining-sites.md` — the rotation-convention class.
- `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md` — the sibling discipline contract (R1 gate set) reused as seed machinery.
- `docs/physics-verification-methodology.md` — the R24 soundness / BMC / post-solve-audit discipline extended by the formal tier.
- `packages/temper-placer/src/temper_placer/validation/` — the oracle seed inventory (drc_oracle, mfem_compare, helps_battery, preflight, human_reference_extractor).
- `docs/evidence/2026-08-02-validation-portfolio-review.md` — the ce-doc-review outcome: per-plan verdicts, merge map (35 → 29), ground-truth corrections, fix-before-execution list.
- `scripts/` — the gate inventory every idea anchors to.
