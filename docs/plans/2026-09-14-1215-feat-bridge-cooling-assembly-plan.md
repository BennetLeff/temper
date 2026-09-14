---
title: "Bridge cooling assembly comparison - Plan"
type: feat
date: 2026-09-14
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: knowledge-work
---

# Bridge cooling assembly comparison - Plan

## Goal Capsule

Find a buildable cooling arrangement that gives the bridge useful temperature margin without consuming an unreasonable fraction of the cooker enclosure.
Deliver sourced assembly alternatives and quantitative requirements for the physical-model comparison.
The coordinator selects the assembly after reviewing fit, thermal evidence and unresolved qualification work.

---

## Product Contract

### Summary

Compare the present Wakefield/two-Sunon concept with a smaller dedicated cooler and an enclosure-level shared-airflow arrangement.
Keep power-entry electrical architecture unchanged in this batch.

### Problem Frame

The present concept reserves about 170 × 160 × 95 mm and has only 5 K nominal junction margin.
Its installed airflow, contact resistance, mounting orientation and protection response have not been established.

### Requirements

- R1. Compare no more than three cooling concepts including the existing baseline.
- R2. Use exact manufacturer curves, dimensions and mounting guidance for shortlisted parts, with dated DigiKey/Mouser availability evidence.
- R3. Calculate bridge loss and the allowable thermal-resistance budget over declared operating conditions and uncertainty.
- R4. Account for duct pressure, installed airflow, recirculation, mounting, mains insulation and the heat loads of any shared cooler.
- R5. Identify a feasible temperature supervision/shutdown window including sensor error, placement, lag and overshoot.
- R6. Provide a machine-readable parameter envelope and mechanical placement drawing for the model/board owners.
- R7. Distinguish calculated suitability, physical fit and hardware qualification; none can substitute for another.

---

## Planning Contract

- KTD1. Reuse the existing `zapote/thermal/cooling-sources/` evidence as the baseline. New parts need their own exact sources, not another suffix's curve.
- KTD2. Compare smaller dedicated cooling and shared cooker airflow before adding fan quantity or heatsink mass. A shared system includes all concurrent heat loads and allocated inlet temperatures.
- KTD3. Supply candidate contracts as proposals under a new directory; never relabel the v1 exact-assembly contract or its retained result.
- KTD4. Prefer simple mounting with vendor-supported contact geometry. A custom spreader or clamp requires a dimensioned concept and explicit tolerance/contact assumptions.
- KTD5. Do not claim that a fan's free-air flow occurs at its shutoff pressure or that two parallel fans double pressure.

### Ownership and dependencies

Own `zapote/thermal/cooling-options/**`, including sources, comparison, drawings and proposed parameter contracts.
Do not edit Rust, CAD, v1 evidence/contract, shared README or unit registry.
Coordinate candidate package dimensions with the board owner early; provide a baseline-compatible proposal even if a replacement package remains unsettled.
The physical model supplies final heat-partition results; they refine this plan's budget without erasing its assumptions.
Firmware/interlock implementation, full enclosure CAD, full-cooker CFD and topology replacement such as bridgeless PFC are deferred.

---

## Implementation Units

### U1. Establish loss and packaging budgets

**Requirements:** R2–R4. **Dependencies:** none.
**Files:** `zapote/thermal/cooling-options/loss-budget.md`, `sources/README.md`, `envelope.md`.
**Approach:** Check the exact bridge diode behavior against the PFC current waveform. Show nominal and conservative justified losses rather than treating 40 W as proven. Determine available orientations from saved PCB/bridge geometry and existing cooker packaging constraints.
Supply source data for the physical-model plan's KTD7 loss-input record: exact MPN, datasheet bytes/page/curve, temperature range and tolerance support. The model owner owns Rust loss recomputation and production profile binding.
**Verification:** Independently check diode loss integration/estimation and thermal-resistance arithmetic. Record unavailable guaranteed curves or missing enclosure dimensions as uncertainty, not favorable defaults.
**Test expectation:** This is an engineering study; use reproducible calculations and dimensional checks rather than duplicating Rust acceptance logic.

### U2. Compare cooling concepts

**Requirements:** R1–R4, R6, R7. **Dependencies:** U1.
**Files:** `zapote/thermal/cooling-options/comparison.md`, `proposals/*.json`, `drawings/`, `sources/`.
**Approach:** Produce one unchanged-baseline row and two materially distinct concepts. Compare volume, mass where sourced, cost/stock snapshots, noise where sourced, electrical power, required airflow, sink/interface resistance, package mounting and serviceability.
**Verification scenarios:**
1. Installed flow follows a supported fan/system operating point or is explicitly an unverified requirement.
2. Shared airflow accounts for upstream air heating and other simultaneous dissipations.
3. Part envelopes and bridge orientation fit the saved-board concept without fictitious horizontal mounting.
4. Any below-ambient passive result or resistance budget that omits an interface is rejected.
5. A smaller cooler is ranked under the same heat load and inlet conditions as the baseline.
**Output:** Dimensioned SVG or mechanical drawing, sourcing links and hashes, thermal envelope distinguishing target/typical/guaranteed/unknown fields. Coordinate its schema with the model owner.

### U3. Define fault supervision and recommend

**Requirements:** R3–R7. **Dependencies:** U2 and model feedback for final numerical ranking.
**Files:** `zapote/thermal/cooling-options/protection.md`, `recommendation.md`, `handoff.json`.
**Approach:** Evaluate one-fan failure, both fans lost, blocked duct with tach still present and elevated inlet air. Establish candidate sensor positions and derive a trip window from worst-case normal temperature, trip uncertainty and shutdown overshoot.
**Verification:** Demonstrate either a nonempty protective operating window or a design inadequacy requiring more cooling/lower normal loss. Do not pick an elevated trip point to hide a narrow margin.
**Output:** Ranked recommendation, model inputs, exact remaining tests for airflow/contact/temperature and explicit additional electrical/mechanical integration needs.
**Test expectation:** No claim of implemented protection; no invented time-to-trip without a validated transient model.

---

## Verification Contract

Retain primary datasheets with page/curve references, source dates and hashes.
Check dimensions and arithmetic independently, and compare under identical declared operating conditions.
Published absolute maxima do not establish product operating limits.
Qualification requires later physical temperature/airflow/fault evidence; report it NOT RUN.

---

## Definition of Done

Three concepts, or a documented reason that fewer are technically viable, have comparable sourced budgets and packaging drawings.
The recommendation identifies margin, evidence quality, unresolved heat paths and the protection window.
The model owner receives explicit machine-readable assumptions and bounds for the selected shortlist.
No purchased hardware, fabricated assembly or implemented protection is implied by this design handback.
## Shared baseline and handoff

Baseline: commit `a4509b26bcc399a2df379d5263eb668c8552a0d4`.
Board: `zapote/power-entry/candidate/section.kicad_pcb`, SHA-256 `84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317`.
The retained result is `zapote/thermal/bridge-cooling.md` and its linked 20-case evidence.
It predicts 100.48–107.86 °C locally with the declared design connections and 125.09–147.77 °C with quarter conductance.
These are conditional calculations, not hardware measurements.
Four `DRC.PFC.BRANCH_COPPER` findings remain open.

Keep 15 A branch RMS and 40 °C cooling inlet as comparison inputs.
This is the existing 1,800 W nominal AC-input class, not a promise of 1,800 W delivered to the DC bus; preserve the input-current limit and current waveform.
Treat the 40 W bridge loss allowance as an assumption to check against the PFC waveform and exact-part behavior.
The existing 110 °C PCB and 125 °C junction ceilings remain in force; they are engineering limits, not independently established assembly ratings.
Do not lower load, increase temperature limits, assign more favorable contacts, or suppress findings to obtain acceptance.
A proposed comparison objective is at least 15 K nominal headroom below each ceiling, plus compliance across a justified uncertainty envelope.
This headroom objective is a design-ranking assumption, not a new safety certification or replacement for uncertainty analysis.

The three plans are:
- Connections: `docs/plans/2026-09-14-1215-fix-bridge-connections-plan.md`.
- Physical model and harness: `docs/plans/2026-09-14-1215-feat-bridge-physical-model-plan.md`.
- Cooling assembly: `docs/plans/2026-09-14-1215-feat-bridge-cooling-assembly-plan.md`.

Each owner works in an isolated worktree and stages only owned files.
No owner overwrites historical evidence or another owner's work.
Coordinator owns integration, `zapote/validation/units.json`, maintained-candidate promotion, shared README/AGENTS/memory updates, and final common-suite evidence.
Owners commit their bounded deliverables and report exact paths, hashes, verification, unresolved assumptions and dependency handoffs.
A partial handback is labeled partial, never completed.
Hardware purchasing, fabrication and powered tests are outside this batch.

---
