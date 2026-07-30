---
title: Resolve Current Board Clearance Debt - Plan
type: fix
date: 2026-07-30
topic: current-board-clearance-debt
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code-and-board
---

# Resolve Current Board Clearance Debt - Plan

## Goal Capsule

- **Objective:** Reduce the current board's REQ-SAFE-01 clearance debt without trading it for a routed-board DRC regression.
- **Current baseline:** 115 violations across 78 component pairs at the current 12.6mm reinforced requirement; 10 components remain unclassified by the full fixture.
- **Decision boundary:** A placement-only CP-SAT reshuffle is not acceptable for the routed board. Any candidate must be evaluated together with its routing consequences.

## Product Contract

### Requirements

- R1. Every candidate is measured against a freshly rebuilt netlist and a ref-pinned board commit.
- R2. The placement method either minimizes displacement from the current board or explicitly includes routing feasibility; a free full-board reshuffle is not a shippable result.
- R3. A candidate may land only when REQ-SAFE-01 decreases without an unexplained increase in DRC ceilings, routed shorts, or unconnected items.
- R4. The ten currently unclassified components are classified from the source/domain manifest or remain fail-closed; no proximity finding is silenced by an exemption without a documented electrical reason.
- R5. Same-footprint violations are treated as footprint/layout fixes, not placement wins. The current intrinsic set includes C6, K1, K2, K3, T1, and U6.
- R6. Any board change updates `power_pcb_dataset/drc_ceiling.json` in the same change after the prescribed 120-sample measurement, and all source/board consistency gates pass.

### Key Flows

#### F1. Route-aware placement repair

1. Build the current full-domain constraint set and identify the movable violating pairs.
2. Generate a minimum-displacement or routing-aware candidate, retaining all existing copper constraints.
3. Re-route the affected nets, or reject the candidate if the route pass is not available.
4. Run the full safety, copper-consistency, provenance, and DRC gates.

#### F2. Intrinsic and classification cleanup

1. Resolve the ten unclassified references against the electrical source and domain manifest.
2. For each same-reference violation, inspect footprint geometry and choose a footprint or source change.
3. Rebuild, reconcile, and remeasure after each physical change.

### Acceptance Examples

- AE1. A candidate that lowers 115 REQ-SAFE-01 violations but increases routed `shorting_items` or `unconnected_items` is rejected and documented.
- AE2. A candidate with all movable pairs clear but C6/K1/K2/K3/T1/U6 still failing is reported as incomplete until those footprint issues have an approved disposition.
- AE3. The six proximity findings below the 12.6mm margin are either moved/classified or have an explicit source-backed exemption; the gate does not become green through a blanket allowlist.
- AE4. A landed board change has a matching DRC-ceiling provenance hash and 120-sample measurement in the same commit.

## Scope Boundaries

- **In scope:** current-board clearance repair, source/domain classification, route-aware candidate evaluation, intrinsic footprint dispositions, and required evidence/gate updates.
- **Deferred:** any current-edition IEC clause interpretation beyond the standards-status evidence already recorded; no threshold relaxation is part of this plan.
- **Not acceptable:** writing either previously measured free-reshuffle candidate into `pcb/temper.kicad_pcb` without a routing pass.

## Dependencies / Assumptions

- The existing CP-SAT placement model and routed-board DRC tools remain available.
- A route-aware candidate may require a new solver objective/API or a separate placement-and-routing workflow; this plan does not assume that either already exists.
- Footprint-intrinsic findings may require library/source changes and therefore their own board remeasurement.

## Open Questions

- Can the placement model encode minimum displacement while preserving enough slack for all full-domain constraints?
- Can the router repair the affected nets without disturbing the board's existing copper and DRC ceiling?
- Which of the six intrinsic findings are package-geometry changes versus deliberate isolator construction constraints?
