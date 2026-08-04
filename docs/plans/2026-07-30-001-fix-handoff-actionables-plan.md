---
title: Handoff Actionables Integration - Plan
type: fix
date: 2026-07-30
topic: handoff-actionables-integration
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# Handoff Actionables Integration - Plan

## Goal Capsule

- **Objective:** Carry the verified handoff actions from a fresh `origin/main` worktree into a source-and-board state that can be measured and reviewed without stale artifacts.
- **Product authority:** This plan owns the pairwise creepage instrument, removal of the unused mains-ZCD crossing, source-to-board identity reconciliation, and provenance-qualified reporting of the current standard status.
- **Open blockers:** None for the scoped code and board reconciliation. Current-edition IEC clause verification remains a prerequisite for any later insulation redesign.

## Product Contract

### Summary

Integrate the reusable HV↔SELV creepage measurement tool, remove the unused mains-ZCD optocoupler and dedicated circuit, then bring the KiCad board into agreement with the freshly built electrical source. Preserve the separate CT/comparator current-ZCD path used for ZVS timing.

### Problem Frame

The handoff identified a useful measurement tool and a source-side deletion, but the source and board were intentionally left out of sync. The board therefore cannot be treated as evidence for the post-deletion safety state until the electrical artifact is rebuilt and the board is reconciled from that exact source.

The handoff also surfaced protective-impedance conclusions read from an older IEC 60335-1 edition. The current IEC catalog identifies Edition 6.0, so clause-level conclusions from Edition 5.2 or older text must not be promoted into a redesign decision without current text.

### Key Decisions

- KD1. **Source changes precede board reconciliation.** (session-settled: user-approved — chosen over applying the older board-resync branch wholesale: the board has moved and stale measurements are unsafe.) Governs R3, R4, R6.
- KD2. **Delete only the unused mains-ZCD crossing.** (session-settled: user-approved — chosen over retaining an unconsumed barrier crossing: the dedicated signal has no firmware consumer while the CT/comparator ZVS path remains load-bearing.) Governs R2, R5.
- KD3. **Treat current IEC clause conclusions as unverified until the current text is available.** (session-settled: user-approved — chosen over reconstructing Edition 6.0 from withdrawn older text: the standard is authoritative and the current text is paid/unavailable here.) Governs R7.

### Requirements

**Measurement and source behavior**

- R1. The repository provides a reusable pairwise HV↔SELV creepage measurement tool with tests covering anti-vacuity, threshold comparisons, body classification, sorting, attribution, and the rotation-convention regression.
- R2. The electrical source removes the mains-ZCD optocoupler and only its dedicated divider, clamp, pull-up, and wiring; the CT/comparator current-ZCD path used for ZVS remains unchanged.

**Artifact synchronization**

- R3. The electrical netlist is rebuilt from the resulting source before any board identity or safety measurement is interpreted.
- R4. The KiCad board is reconciled against that rebuilt source using the current worktree as the base, and no older board-wide rewrite is applied without checking its edits against the current board.
- R5. The final source, netlist, and board agree on component identities, nets, and the deletion's physical consequences.

**Evidence and safety boundaries**

- R6. Every reported measurement is tied to the final worktree commit and regenerated inputs, with expected failures distinguished from unexplained regressions.
- R7. Documentation records IEC 60335-1:2020 Edition 6.0 as the current catalog entry and does not assert the older clause mapping as current-edition fact.

### Key Flows

- F1. Source-to-board reconciliation
  - **Trigger:** The source-side U3 deletion and measurement tool are integrated.
  - **Steps:** Rebuild the netlist; compare identities; reconcile the board; run consistency and safety checks; record any remaining failure against this worktree's commit.
  - **Outcome:** A synchronized board or a specifically attributed blocker.
  - **Covers R2, R3, R4, R5, R6.**

- F2. Measurement reuse
  - **Trigger:** A future creepage threshold or board revision needs a cross-domain result.
  - **Steps:** Run the committed tool against the exact board and source inputs; inspect the threshold comparison and classifications; retain the commit and input provenance.
  - **Outcome:** A reproducible measurement rather than an ad-hoc count.
  - **Covers R1, R6.**

### Acceptance Examples

- AE1. Pairwise measurement is trustworthy.
  - **Covers R1.**
  - **Given:** The committed synthetic fixtures and the current tool implementation.
  - **When:** The targeted measurement tests run.
  - **Then:** They pass and fail closed on missing or empty HV/SELV inputs.

- AE2. U3 removal does not remove ZVS timing.
  - **Covers R2.**
  - **Given:** The rebuilt source after deletion.
  - **When:** the firmware and electrical signal inventories are checked.
  - **Then:** the mains-ZCD-only symbols and pin are gone, while the CT/comparator capture path and its firmware consumers remain.

- AE3. Board status is ref-pinned.
  - **Covers R3, R4, R5, R6.**
  - **Given:** the final worktree commit and a freshly built netlist.
  - **When:** board consistency and safety checks run.
  - **Then:** a pass is reported only for matching artifacts, and any failure names the exact remaining mismatch rather than being described as a generic post-deletion count.

- AE4. Standards status is not overstated.
  - **Covers R7.**
  - **Given:** the official IEC publication metadata and unavailable paid current text.
  - **When:** the evidence note is reviewed.
  - **Then:** Edition 6.0 is identified as current, while clause-level insulation conclusions remain explicitly unverified.

### Scope Boundaries

- **In scope:** The pairwise creepage tool, the source-side U3 deletion, fresh netlist generation, board reconciliation, targeted gates, and evidence updates needed to make those results auditable.
- **Deferred for later:** Any PD2/PD3 insulation redesign, C6 topology change, protective-earth construction, or clause-level compliance decision requiring current IEC text.
- **Outside this work:** Remote PR merge coordination when GitHub is unreachable and unrelated board-placement or routing redesign.

### Standards Status

- The current-edition metadata and access limitation are recorded in
  [`docs/evidence/2026-07-30-iec-60335-1-current-status.md`](../evidence/2026-07-30-iec-60335-1-current-status.md).
- No clause-level conclusion from the withdrawn Edition 5.2 text is promoted
  as a current Edition 6.0 requirement.

### Dependencies / Assumptions

- The repository's electrical build tooling is available in this environment.
- Board reconciliation can be performed through the documented source-to-board flow without treating the older resync branch as authoritative.
- The official IEC publication page is sufficient to establish edition metadata, not to verify paid clause text.

### Outstanding Questions

- **Deferred to Planning:** Which existing source-to-board generation command produces the authoritative current board artifact, and which targeted gates are valid after the board is regenerated?
- **Deferred to Planning:** Whether remote PRs can be merged must be handled separately from this isolated worktree if network access returns.
