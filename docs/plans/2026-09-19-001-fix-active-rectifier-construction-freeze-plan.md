---
title: Active Rectifier Construction Freeze - Plan
type: fix
date: 2026-09-19
topic: active-rectifier-construction-freeze
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

## Goal Capsule

- **Objective:** Freeze the active-rectifier construction candidate with a decisive verdict: prove it is the right build or prove it is the wrong build.
- **Product authority:** This plan owns construction freeze only: TEA spacing disposition, F2 footprint finalization, and a rerun of the existing active suite on saved bytes.
- **Open blockers:** TEA 2 mm applicability unknown until manufacturer/insulation check; F2 clip/fuse paper verification not yet done; frozen bytes not yet rerun.

## Product Contract

### Summary

Settle the three TEA package gaps against manufacturer guidance and insulation class, replace the provisional F2 footprint with a paper-verified fit, then rerun the current active suite plus KiCad ERC/DRC to freeze or reject the candidate.

### Problem Frame

The active runner now evaluates the board but power entry stays FAIL on three intrinsic TEA gaps (1.94 mm vs 2 mm floor) and the F2 footprint is a provisional assumption. Without a justified disposition for those gaps and a verified fuse fit, the candidate cannot be frozen or honestly rejected, and qualification work has no stable bytes to target.

### Requirements

**TEA spacing disposition**

- R1. The three failing pairs (U1 pads 3-5, 10-12, 14-16) are each checked against the TEA2209T manufacturer layout guidance and the applicable functional insulation requirement.
- R2. The freeze records exactly one outcome per pair: the 2 mm floor does not apply with written justification and a narrowed rule, or the design changes to clear it.
- R3. No pad narrowing or numerical waiver counts as a disposition, and trace moves are not claimed to fix inside-footprint gaps.

**F2 fuse mounting**

- R4. The F2 footprint is replaced with a paper-verified geometry naming the exact clip MPN, hole/slot dimensions and tolerances, fuse fit and engagement, and electrical/thermal ratings checked against the datasheets on file.
- R5. The generator and footprint description retain every dimension and assumption, and the 3D absence and provisional history stay explicitly noted until fit is verified.

**Freeze rerun**

- R6. The frozen verdict reruns the existing active common suite plus KiCad ERC/DRC, stackup, and saved-board/native binding on the final saved bytes, with the source manifest and receipts bound to those bytes.
- R7. A FAIL verdict is a successful outcome when the evidence supports it: the freeze proves right or proves wrong, it does not force green.

### Key Decisions

- **Dual-track TEA until evidence picks a winner** (session-settled: user-directed — chosen over picking disposition or redesign now: applicability unknown). Governs R1, R2.
- **Paper-verified F2 is enough for freeze** (session-settled: user-directed — chosen over physical fit or minimal check: unblocks freeze while clearing stays with Q1/Q2). Governs R4, R5.
- **Current suite defines frozen** (session-settled: user-directed — chosen over adding inputs or demanding thermal replays: keeps construction separate from qualification). Governs R6.

### Acceptance Examples

- AE1. Covers R2, R7. Given the manufacturer check shows the 2 mm floor does not apply to a TEA pair, when the freeze lands, then the narrowed rule carries the written justification and the pair passes under it.
- AE2. Covers R2, R7. Given the 2 mm floor does apply and the footprint cannot clear it, when the freeze lands, then the candidate is recorded as the wrong build for that requirement rather than waived through.
- AE3. Covers R4, R6. Given the F2 footprint is replaced with verified geometry, when the suite reruns, then ERC/DRC, stackup, and binding pass on the new saved bytes and the old receipts are retained as history.

### Success Criteria

- The frozen bytes carry a bound, rerunnable verdict that names right-build or wrong-build with the exact failing requirement cited.
- A reviewer can trace every TEA and F2 claim to a retained source without re-running a measurement.

### Scope Boundaries

- Q1–Q5 qualification (Q1 Mersen application review, Q2 line/internal fault coordination and tests, Q3 differential-surge test, Q4 common-mode path, Q5 commutation/startup/thermal per `zapote/power-entry/CLOSEOUT.md`), thermal replays, surge, bootstrap/startup, cooling, and powered tests stay open and are not part of this freeze.
- No generic harness expansion or checker redesign; the frozen harness is consumed as-is.
- No procurement, fabrication, or enclosure fit beyond the paper footprint check.

### Dependencies / Assumptions

- Depends on retained TEA2209T guidance, ETI/Mersen clip and fuse datasheets, and the current active runner behaving as recorded in `zapote/power-entry/active-rectifier/RUST-INTEGRATION.md`.
- Assumes the existing 0.2 mm / 2 mm / 6 mm construction floors stay in force unless a disposition explicitly narrows them with justification.

### Outstanding Questions

- Resolve Before Planning: which insulation standard and clause actually governs the three TEA pairs on this board?
- Deferred to Planning: exact rerun command set and receipt layout for the frozen bytes.
- Deferred to Planning (review 2026-09-19): confirm the frozen verdict still decides when the governing clause is unresolved at freeze time; state the R7 FAIL-as-success gate so PASS and FAIL cannot both satisfy it vacuously; record which retained F2 assumptions the paper verification re-checks versus inherits; pin runner version/flags/sample handling for the R6 rerun; define the escalation when R2 evidence splits across the dual TEA tracks.

### Sources / Research

- `zapote/power-entry/active-rectifier/RUST-INTEGRATION.md`
- `zapote/power-entry/active-rectifier/VALIDATION.md`
- `zapote/power-entry/active-rectifier/MECHANICAL.md`
- `zapote/power-entry/CLOSEOUT.md`
