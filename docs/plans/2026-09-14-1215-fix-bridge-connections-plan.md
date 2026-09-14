---
title: "Bridge connection redesign - Plan"
type: fix
date: 2026-09-14
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: code
---

# Bridge connection redesign - Plan

## Goal Capsule

Produce a reviewable bridge-connection alternative that reduces electrical and thermal bottlenecks while preserving the power-entry circuit.
Use agent-directed KiCad edits and the existing Rust validators.
The board owner delivers candidate bundles; the coordinator promotes a candidate only after the physical-model and cooling comparisons are reviewed.

---

## Product Contract

### Summary

Compare the existing package with improved copper routing, then evaluate one alternate bridge package if the original leads or pad spacing impose the limiting geometry.

### Problem Frame

The four 2.5 mm bridge necks fail the current screen and have only 2.14 K nominal modeled PCB margin.
The surrounding 4-to-6 mm trace repair did not resolve these local connections.

### Requirements

- R1. Preserve the electrical function, exact net/pin semantics and current/voltage requirements of power-entry.
- R2. Produce an explicit before/after census for all four connections, including copper length, width, thickness, pad annulus, drill and layer use.
- R3. Compare no more than three candidates including the baseline; do not introduce a placer or router algorithm.
- R4. Any package substitution must use exact manufacturer pinout, mechanical dimensions and ratings, with dated DigiKey/Mouser identity and availability evidence.
- R5. Candidate evidence must come from the saved candidate bytes and expose unsupported checks.
- R6. Candidate selection requires the common thermal criteria in Shared baseline and handoff; a better nominal temperature alone is insufficient.

---

## Planning Contract

- KTD1. Start with shorter and wider direct connections using the same GBU2510A package because this separates routing losses from package limitations.
- KTD2. Evaluate a mechanically mountable alternate bridge only if direct connection geometry remains limiting; higher advertised current rating alone is not selection evidence.
- KTD3. Keep alternatives under `zapote/power-entry/bridge-redesign/`; the existing maintained candidate remains the baseline until coordinator integration.
- KTD4. Do not teach the thermal importer a new geometry by replacing its pinned constants. The model owner provides an explicit reviewed-variant path.

### Ownership and dependencies

Own `zapote/power-entry/bridge-redesign/**`, including variant KiCad files, local libraries, changed source snippets, renders, native exports and comparison report.
Do not edit thermal Rust, maintained candidate/source-build directories, the cooling contract or the unit registry.
Use the current native KiCad/Python adapter. Consult `zapote/AGENTS.md` and `zapote/skills/README.md` before construction and retain applicable memory selection/delivery receipts.
U1–U2 may start immediately; final thermal ranking in U3 depends on physical-model U1–U3 and cooling-assembly U2.
If a substitution requires atopile changes, include a variant source copy and reproducible build receipt; never present a CAD-only symbol replacement as a fully source-bound build.

---

## Implementation Units

### U1. Establish actual bottlenecks

**Requirements:** R1, R2. **Dependencies:** none.
**Files:** new `zapote/power-entry/bridge-redesign/baseline.md`, `variants.json`, and source identity/native evidence under the same directory.
**Approach:** Trace each bridge pin through pad, annulus, solder connection, neck and adjacent copper. Identify the shortest/widest feasible paths while accounting for clearance, creepage and assembly access.
**Patterns:** `zapote/power-entry/evidence/native-copper-12.json`, `evidence/copper-repair-2026-09-12/parent-manufacturing.json`.
**Verification:** Compare dimensions and physical pin/net identity against native KiCad exports. Identify layers and current-sharing assumptions explicitly.
**Test expectation:** No new software behavior; verify through independent native extraction and existing checks.

### U2. Build bounded alternatives

**Requirements:** R1–R5. **Dependencies:** U1.
**Files:** `zapote/power-entry/bridge-redesign/variants/same-package/**`; if justified, `variants/alternate-package/**`; `parts.md`.
**Approach:** Use explicit KiCad edits. Try direct wide copper first. Add backside copper or parallel paths only with modeled layer transitions and actual plated connections. Preserve insulation distances. For an alternate package, verify native model transfer compatibility with the model owner before spending effort on a full reroute.
**Verification scenarios:**
1. Every bridge terminal retains the correct electrical endpoint in both schematic and board.
2. No unconnected copper, net short, library-resolution failure or schematic-parity regression.
3. Pad/trace transitions and drilling remain physically manufacturable.
4. A current-sharing credit has a defensible distribution model; nominal parallel area alone does not count.
5. Unsupported package geometry produces an explicit unevaluated result, never a reused baseline pass.
**Output:** Candidate bundles with exact source identities, native ERC/DRC/parity, physical stackup/manufacturing results and top/bottom renders.

### U3. Compare and recommend

**Requirements:** R2, R5, R6. **Dependencies:** U2 plus the model and cooling handoffs.
**Files:** `zapote/power-entry/bridge-redesign/comparison.md`, `handoff.json`.
**Approach:** Submit frozen candidate manifests to the model owner. Tabulate branch resistance, loss, peak copper/FR4/solder/package temperature, uncertainty range and outstanding native/Rust findings. Separate geometry-only benefit from cooling changes.
**Verification:** Compare baseline and variants under identical current, inlet and model assumptions. If the integration inputs are pending, hand back the frozen candidates and explicitly leave this unit incomplete.
**Test expectation:** No duplicate solver or new acceptance logic in this report.

---

## Verification Contract

Use native KiCad ERC with all severities and DRC with all-track-errors, schematic parity and all severities, complete local libraries and pinned runtime.
Run the existing Rust electrical, physical-stackup, manufacturing and current checks on each candidate through the production adapters.
The coordinator runs `make -C zapote check-units` on the selected integrated candidate and investigates any new finding.
Never waive the four screen failures through a thermal report; document their separate disposition.

---

## Definition of Done

At least one modified, source-bound candidate is saved with native evidence and a reproducible change record.
All four connections are accounted for; the comparison distinguishes improved, unresolved and unsupported cases.
The thermal recommendation remains pending until U3 has real source-bound results.
Abandoned production edits are removed; rejected candidate evidence remains clearly labeled.
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
