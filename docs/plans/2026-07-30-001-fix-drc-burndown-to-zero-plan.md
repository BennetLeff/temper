---
title: DRC Burn-Down to Zero - Plan
type: fix
date: 2026-07-30
topic: drc-burndown-to-zero
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# DRC Burn-Down to Zero - Plan

## Goal Capsule

- **Objective:** Drive the board's DRC error count from 1346 to zero through placer/router capability, run as safety-ordered campaigns over a floor that cannot loosen.
- **Product authority:** This artifact owns the burn-down target, what counts as progress, the enforcement mechanism, and how a violation that layout cannot fix is escalated. It does not own the placer/router capabilities themselves — those belong to the provable-safety plan's outstanding units.
- **Open blockers:** None. Two questions are deferred to planning.

---

## Product Contract

### Summary

Burn the board's 1346 DRC errors down to zero, category by category in safety-first order, with every gain locked in automatically so the count can only fall.
Reductions come from placer/router capability rather than hand layout, so the committed board stays the gate while router output is the means.
A violation that no layout change can fix escalates to a named decision rather than persisting quietly.

### Problem Frame

The board measures 1346 DRC errors across 13 categories, and until recently almost none of them were visible.

Creepage constraints were not emitted at all, so the mains-insulation category read zero. The netclass assignments KiCad actually consults did not match the Python model — the live 170 V bus, mains line and neutral, the switching node and the power return all resolved to no class and inherited low-voltage spacing. A netclass could be declared while emitting no rules. Each of those was fixed in the last day, and the count rose as a result: nothing was created, the instrument stopped under-reporting.

The repository already states the target. `power_pcb_dataset/drc_ceiling.json` carries `_goal: "error_ceiling: 0. Every number below is debt to pay down, not budget to spend."` What it lacks is anything that makes the debt fall. The ceiling may only decrease and a raise needs a `Ceiling-Approval:` trailer, but nothing requires a decrease, so the number can sit still indefinitely while the gate stays green.

That failure mode is documented across this repo, not hypothetical. `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md` audited ten baseline-enforcing artifacts and found half decorative — `continue-on-error: true`, a disabled feature flag, or a code path never invoked — with the recurring pattern being "freezing current badness into a file instead of fixing it." The DRC ceiling is one of the ten.

### Key Decisions

- KD1. **The whole error set, not a safety subset.** All 13 categories to zero, matching the ceiling file's own stated goal, rather than stopping at the insulation-spacing categories. (session-settled: user-directed — chosen over creepage-only or insulation-only scoping.) Governs R1.
- KD2. **Campaigns over a floor, not a ratchet alone.** A gate that only prevents growth produces stasis; a campaign supplies direction and an end condition. Governs R6, R7.
- KD3. **Safety order, not count order.** Creepage at 312 precedes clearance at 499, because clearance's larger figure is mostly low-voltage pairs with a far weaker safety argument. Governs R7.
- KD4. **The board is the gate, the router is the means, and they must stay reconcilable.** (session-settled: user-directed — chosen over measuring the board alone, which would let a hand fix improve the number until the next re-route undoes it.) Governs R2, R3, R4.
- KD5. **Unfixable-by-layout escalates rather than persists.** A violation proven beyond layout becomes a named decision — change the part, or accept with published justification. (session-settled: user-directed — chosen over splitting package-bound violations into a separate workstream, which risks their being forgotten.) Governs R9.
- KD6. **The system fixes the board; a person does not.** (session-settled: user-directed — inherited from the provable-safety plan's no-human-in-the-loop position, which is what makes this capability work rather than a layout task.) Governs R8.

### Requirements

**Target and measurement**

- R1. The board reaches zero DRC errors across all categories. Warnings are excluded from the target.
- R2. The enforced count is DRC measured on the committed `pcb/temper.kicad_pcb`.
- R3. Router output remains reconcilable with the committed board within a declared divergence tolerance, and that divergence is tracked as a number that may not grow.
- R4. The divergence between router output and the committed board is measured and published before any tolerance is declared, because it is currently unknown.

**Enforcement**

- R5. No change may increase the aggregate error count or any per-type count.
- R6. A run that measures below the recorded ceiling tightens that ceiling to the measured value without a `Ceiling-Approval:` round trip, so every gain is locked in when it happens.
- R7. Categories are burned to zero one at a time in a declared safety-first order, with categories outside the active campaign held at their current values.

**Source of fixes**

- R8. Reductions come from placer/router capability. A hand edit to the committed board does not count as progress against this plan.
- R9. A violation established as unfixable by layout escalates to a documented decision with a named owner, recording either the part change required or the justification for accepting it.

**Reporting**

- R10. Every run reports prover coverage alongside the violation count, so a falling count with stalled coverage is visible rather than indistinguishable from real progress.

### Key Flows

- F1. A campaign runs to closure
  - **Trigger:** The next category in the safety-first order is opened.
  - **Steps:** Its violations are enumerated and attributed; placer/router capability is improved until the category measures zero; each intermediate run tightens the ceiling; categories outside the campaign are checked for non-increase.
  - **Outcome:** The category reads zero, its ceiling is zero, and the closure is recorded with evidence.
  - **Covers R1, R5, R6, R7, R8.**

- F2. A violation turns out to be beyond layout
  - **Trigger:** A violation resists every layout and routing change because its geometry is internal to a package.
  - **Steps:** The finding is recorded with the measured distance and the requirement it fails; it is raised as a decision with a named owner; the owner either specifies a part change or publishes a justification for accepting it.
  - **Outcome:** The violation is either scheduled for a hardware change or carries a written justification. It does not sit unexplained in the count.
  - **Covers R9.**

### Acceptance Examples

- AE1. Progress in one category may not be paid for by another
  - **Covers R5.**
  - **Given:** A change that removes 20 creepage violations and adds 3 solder-mask bridges.
  - **When:** The gate evaluates it.
  - **Then:** It fails, because a per-type count increased.

- AE2. A gain is locked in without asking
  - **Covers R6.**
  - **Given:** A run measuring 1300 errors against a recorded ceiling of 1346.
  - **When:** The run completes.
  - **Then:** The ceiling becomes 1300 with no `Ceiling-Approval:` trailer required, since it tightened rather than loosened.

- AE3. A hand fix does not count
  - **Covers R8.**
  - **Given:** The committed board is edited directly to clear a clearance violation, with no placer or router change.
  - **When:** Progress is assessed.
  - **Then:** The reduction is not credited to the burn-down, because the next re-route would reintroduce it.

- AE4. A package-bound violation cannot sit quietly
  - **Covers R9.**
  - **Given:** A creepage violation between two pins of a single package, where the pin pitch is physically below the requirement.
  - **When:** The campaign covering that category attempts closure.
  - **Then:** Closure is blocked until the violation carries either a specified part change or a published justification with a named owner.

- AE5. Falling violations with stalled coverage is visible
  - **Covers R10.**
  - **Given:** A run where the violation count drops and prover coverage is unchanged.
  - **When:** The run reports.
  - **Then:** Both numbers are shown, so the reader can tell copper was moved rather than proven safe.

<!-- ce-section: work-relationships -->
### How This Work Fits Together

This plan owns the burn-down of board DRC defects. The breakdown below is the current understanding, not a committed roadmap.

- Provable-safety place-and-route (`docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`)
  - Depends on its outstanding units for the capability this plan consumes — DRC as prover-soundness authority, the coverage ratchet, and unattended deterministic runs
  - Shares the no-human-in-the-loop position that makes this capability work rather than layout work
- Baseline artifact burn-down (`docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md`)
  - Shares the DRC ceiling as an artifact, but targets the enforcement mechanism rather than the board defects
  - Can proceed independently of this plan
- Hardware revision for package-bound violations
  - Depends on R9's escalations to define what part changes are actually required
  - Still to decide: whether that becomes its own plan or rides an existing hardware track

### Dependencies and Assumptions

- The 1346 figure and its category breakdown are measured on the branch carrying the netclass and rule corrections, not on `main`. Landing those corrections is a prerequisite for this plan's baseline to be real.
- The creepage figure of 312 is measured against PD3's 12.6 mm, which replaced PD2's 8.0 mm on 2026-07-30. Revisiting that determination moves the target.
- Some violations are known to be beyond layout before the work starts. `scripts/generate_kicad_dru.py` records that the TO-247's 1.95 mm edge-to-edge pin gap is below the reinforced-insulation requirement, that this is "a real violation this rule is now expected to report, not a bug in this rule", and that resolving it "needs a BOM/footprint/placement change, none of which this script performs." Zero therefore has a hardware dependency this plan cannot close alone.
- The divergence between router output and the committed board is assumed to be large and is currently unmeasured. Figures of 51 and 52 of 96 nets appear in prior documents, but both were measured on a board with copper pours manually stripped, and the source plan states neither should be treated as authoritative.

### Scope Boundaries

**Deferred for later**

- The 683 DRC warnings. Errors first; warnings may become a later campaign.
- Gating on prover coverage. It is reported under R10, not enforced.

**Outside this plan**

- The placer and router capabilities themselves, which belong to the provable-safety plan's outstanding units.
- The baseline-artifact burn-down, which targets enforcement mechanisms rather than board defects.
- Fabrication and assembly concerns beyond what DRC measures.

### Outstanding Questions

**Deferred to Planning**

- The safety-first campaign order beyond its first two entries. Creepage precedes clearance by KD3; where the remaining eleven categories fall is a sequencing decision planning can make from the measured counts and hazard classes.
- Whether the divergence tolerance under R3 is expressed as unrouted-net count, segment difference, or violation delta. R4 requires the measurement first, and the right unit will be clearer once it exists.

### Sources

- `power_pcb_dataset/drc_ceiling.json` — the `_goal` text that states the target and the rule that ceilings may only decrease.
- `scripts/generate_kicad_dru.py:682-725` — the TO-247 pin-gap comment establishing that some violations need a BOM, footprint or placement change.
- `docs/evidence/2026-07-30-creepage-205-triage.md` — per-bucket triage of the creepage category: genuine crossings, package-bound gaps, rule artifacts, and protective-impedance nodes.
- `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md` — the audit of ten baseline artifacts and the freezing-badness pattern this plan's enforcement model is designed against.
- `docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md` — the place-and-route contract this plan consumes capability from.
