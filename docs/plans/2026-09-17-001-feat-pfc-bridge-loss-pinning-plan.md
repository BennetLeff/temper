---
title: PFC Bridge Loss Pinning - Plan
type: feat
date: 2026-09-17
topic: pfc-bridge-loss-pinning
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
---

# PFC Bridge Loss Pinning - Plan

## Goal Capsule

- **Objective:** Replace the input bridge's assumed 0.85/1.30 V forward-drop band with a curve-integrated loss pinned tightly enough to rank rectifier architectures.
- **Product authority:** The project engineer. This unit owns the bridge's *electrical* loss only. Architecture ranking, the bridge's thermal/mounting work, and the switching measurement are separate units, not active scope here.
- **Bar:** Uncertainty small relative to the 5-15 W differences between rectifier candidates (passive GBJ, lower-drop passive, parallel passive, active/synchronous, bridgeless).
- **Open blockers:** Stage 2 is powered bench work, which the PFC experiment campaign does not authorize; it needs its own approval. Stage 1 stands alone if that lags.

---

## Product Contract

### Summary

Pin the passive input bridge's real loss so rectifier architectures can be ranked against a number instead of an assumed band. Stage 1 digitizes the per-element forward-characteristics curve already present in the retained datasheet and integrates it over the C1 rectified waveform at 25 °C. Stage 2 confirms the temperature dimension with a DC forward-drop sweep. Stage 3 is the uncertainty budget. The curve-integrated loss replaces the constant-drop term in its existing single home.

### Problem Frame

The input bridge is the largest loss term that no independent comparison has challenged: about 28.30 W at C1 nominal, derived from a single datasheet test point (1.05 V at 12.5 A, 25 °C) applied as a constant drop across a 60 Hz rectified waveform whose current spans zero to tens of amps.

The model records why it is a guess: `zapote/packages/zapote-harness/src/pfc_candidates.rs` states the retained datasheet "has no forward-drop curve and no high-temperature point", so an 0.85/1.30 V band is carried as an explicit assumption. That statement is false. Page 3 of the retained PDF carries Fig. 2, "Typical Forward Characteristics, Per Element", on a log current axis at T_J = 25 °C. The curve is nonlinear: forward drop is roughly 0.7 V near 1 A and about 1 V at 12.5 A. So the constant-drop term is wrong in shape, not only in value, and the 0.85/1.30 V band does not represent a shape error.

On a ~28.30 W term, that band spans roughly 23-35 W. That is a 12 W uncertainty on the largest unchallenged term, comparable in size to the entire frequency debate the campaign retired. Ranking rectifier architectures through an unresolved term of that size would repeat the mistake the campaign already paid for with the switching model, where two models disagreed by ~1.45x and no candidate could be ranked.

The absence was missed because `pdftotext` returns the datasheet's numeric tables and silently drops its plots. The claim "the source has no curve" was really "my extractor showed me no curve".

### Key Decisions

- **Curve-integrated loss over a single effective drop.** (session-settled: user-approved — chosen over the effective-drop shortcut: the datasheet curve is nonlinear in current, so one scalar keeps the shape error the ranking bar cannot tolerate.)
- **Staged, source-first.** (session-settled: user-approved — chosen over bench-primary: read the free source-only signal before spending a bench authorization.)
- **Tight enough to rank architectures, not merely a bound.** (session-settled: user-directed — chosen over a bound-only or best-available bar: the pinned loss exists to enable candidate ranking.)
- **One home for the bridge-loss term.** Governs R6. The curve-integrated loss replaces the constant-drop term where it already lives; a second bridge-loss implementation would drift from the first.
- **Thermal, mounting and contact work stays with the GBJ thermal study.** This unit supplies the electrical loss that work consumes; it does not re-open the study's scope.

### Requirements

**Evidence**

- R1. Stage 1 digitizes Fig. 2 from the retained GBJ2510-F datasheet at its recorded content hash, and records the digitization method and its estimated reading error.
- R2. The claim that the retained datasheet has no forward-drop curve is corrected at its source comment and in any document that repeats it.
- R3. Stage 2 measures forward drop against current on the actual GBJ2510-F at a cold and a hot case temperature across the waveform's current range; it records the fixture, the measurement method and how each temperature was established and verified.
- R4. Every reported number carries an evidence class — measured, source-bound, modelled, or assumed — and no number is reported under a stronger class than its provenance supports.

**Loss model**

- R5. Bridge loss is integrated over the C1 rectified waveform using forward drop as a function of instantaneous element current, at each C1 line voltage and at each temperature measured in R3.
- R6. The curve-integrated loss replaces the constant-drop term in its existing location; no second bridge-loss implementation is introduced.
- R7. A regression demonstrates that, given a constant forward-drop curve, the integrated model reproduces the previous constant-drop result.
- R8. The number of conducting elements in the line path is stated, and any parallel-element or parallel-bridge current-sharing assumption is declared explicitly with its effect reported rather than averaged away.

**Uncertainty and acceptance**

- R9. The result carries an explicit uncertainty budget whose terms include digitization error, temperature, element count, and any sharing assumption; the budget is expressed as a number.
- R10. The unit states whether its uncertainty is small relative to the 5-15 W candidate differences it must support; when it is not, the unit reports that it did not meet the bar instead of asserting a ranking.
- R11. When Stage 2's authorization is unavailable, Stage 1's result stands alone and temperature is reported as an explicit residual; it is never filled by a silent assumption.

**Integrity**

- R12. An absence claim about a source document is verified against that document's rendered content, including figures, not only against a text extraction.
- R13. No blanket correction factor is derived from any model-versus-model or model-versus-measurement disagreement; discrepancies are reported per condition and their applicability stated.
- R14. The unit reports the pinned bridge loss against the current 28.30 W constant-drop figure and states explicitly whether the bridge-versus-switch priority ordering changes.
- R15. Overlapping loss boundaries within this unit's scope — notably diode reverse recovery and junction capacitance against forward conduction — are named, and each is either counted once or explicitly excluded.

### Acceptance Examples

- AE1. **Covers R7.** Given a constant forward-drop curve supplied to the integrated model, when its output is compared to the retained constant-drop result at the same C1 point, then the two agree within the stated numerical tolerance.
- AE2. **Covers R11.** Given Stage 2 is unauthorized, when the unit reports, then the 25 °C curve-integrated result is present and the temperature dimension is listed as an explicit residual with no assumed value.
- AE3. **Covers R10.** Given the uncertainty budget exceeds the candidate differences it must support, when the unit reports, then it states that the ranking bar was not met and makes no ranking claim.
- AE4. **Covers R12.** Given a claim that a source lacks a curve, table, or figure, when the claim is checked, then it is checked against the rendered document and not only extracted text.

### How This Work Fits Together

<!-- ce-section: work-relationships -->

This plan owns the bridge's electrical loss. The surrounding breakdown is the current understanding, not a committed roadmap.

- **Rectifier architecture screening** — depends on this plan. It ranks passive GBJ, lower-drop passive, parallel passive, active/synchronous and bridgeless options; it needs this unit's pinned loss as its passive baseline.
- **Bridge thermal, mounting and contact work** — can proceed independently. Owned by the existing GBJ thermal study, which left mounting geometry, installed fan operating point and pad/contact current distribution open.
- **Switching double-pulse measurement** — can proceed independently and in parallel; separately authorized.
- **Broader architecture search (interleaved, bridgeless, totem-pole)** — still to decide. Kept open; not active scope here.

### Success Criteria

- A pinned bridge loss at each C1 line and measured temperature, with a numeric uncertainty budget and an explicit statement of whether it meets the ranking bar.
- The corrected curve claim, so no later reader re-derives the 0.85/1.30 V band from the false premise.
- A regression tying the new integrated model to the retained constant-drop result.

### Scope Boundaries

- **Deferred for later:** ranking the rectifier architectures themselves; correcting the screen's "watts per 0.1 V of forward drop" scoring, which assumes linearity in forward drop and becomes wrong once a curve exists.
- **Outside this unit:** the bridge's thermal, mounting, contact and cooling work; the switching double-pulse measurement; the interleaved/bridgeless/totem-pole studies; any CAD, BOM or production-board change.

### Dependencies / Assumptions

- The retained GBJ2510-F datasheet, SHA-256 `c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02`, at `zapote/power-entry/loss-budget/sources/Diodes-GBJ2510.pdf`.
- The existing matched-power and rectified-waveform model, which supplies the per-line waveform the loss is integrated over.
- Stage 2 requires a bench authorization the PFC experiment campaign does not provide.
- Assumed: the published per-element characteristic is representative of the populated part; no element-to-element or lot variation data exists and none is invented.

### Outstanding Questions

- **Deferred to planning:** the digitization method and its error estimate; the bench fixture, current range and temperature points; where the uncertainty budget is recorded; the numerical tolerance for the R7 regression.

### Sources / Research

- `zapote/power-entry/loss-budget/sources/Diodes-GBJ2510.pdf` — page 3, Fig. 2 (typical forward characteristics, per element, T_J = 25 °C) and Fig. 1 (current derating vs case temperature).
- `zapote/packages/zapote-harness/src/pfc_candidates.rs` — the bridge constant-drop terms, the 0.85/1.30 V band, and the false no-curve comment.
- `zapote/thermal/gbj-study/README.md` — thermal context: the 40 W bridge allowance, 1.0 °C/W RθJC per element, and the fixed-V_F point estimate.
- `zapote/power-entry/loss-budget/campaign/CLOSEOUT.md` and `zapote/power-entry/loss-budget/campaign/LOSS-ACCOUNTING-AUDIT.md` — the error modes this unit's integrity requirements encode.
- `docs/plans/2026-09-17-1342-pfc-experiment-campaign-plan.md` — campaign context and the bridge-screening recommendation.
