---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
title: "Zapote auxiliary power unit"
date: 2026-09-23
execution: code
---

# Zapote auxiliary power unit: requirements

## Problem and boundary

Rev38 has a compiled HOT logic5 and protected AUX consumer network, but no selected, joined protected AUX producer. The legacy full-board `AuxSupply` describes a separate isolated 15 V SELV rail fed from a half-bus. Their supply sides, return domains, startup order and load budgets differ. This unit must establish which source produces each rail before a standalone schematic can be accepted.

This goal owns supply production, protection at the supply boundary, explicit outputs and standalone construction evidence. Rev38 owns its PFC protection/restart logic. Cooker-board integration and physical qualification remain later goals.

## Approaches considered

1. One multi-output source for HOT and SELV: fewer assemblies, but insulation, startup and failure coupling become one design problem.
2. Independent HOT and SELV sources: clear domains and failure isolation, at the cost of more assemblies and input coordination. **Preferred starting architecture for evaluation**, subject to the confirmed unit scope.
3. HOT-only source now, SELV later: smallest immediate dependency for Rev38, but leaves gate-drive, interlock, fan and MCU supply integration unresolved.

No source topology or part is selected by this requirements document. The legacy IRM-10-15 and Rev38 protected-AUX screens are candidate inputs, not an accepted assembly.

## Requirements

- **A1. Rail ownership:** inventory every HOT and SELV rail consumer, its return, steady load, startup pulse, dropout tolerance and required operating sequence. Distinguish measured, source-derived and assumed values.
- **A2. Cold start:** identify a source available at the required point in the AC/precharge sequence; no rail may require PFC RUN to create the rail needed to authorize PFC RUN.
- **A3. Failure behavior:** loss, brownout, overvoltage, partial power and return of power must drive the relevant permits and gate enables to documented safe states. A supply hiccup must not count as deliberate restart.
- **A4. Insulation and grounding:** specify the HOT-to-SELV boundary and the exact return domains; connect neither return by assumption.
- **A5. Electrical envelope:** source, clamp/protection, load and cable must share one worst-case voltage/current/temperature/transient budget. Record any vendor or physical data needed to close it.
- **A6. Standalone evidence:** accepted source identity, compiled Atopile source, native board, Rust checks with adverse cases and reproducible receipts. Mark dynamic and physical qualification separately.

## Acceptance examples

1. In a cold-start model, the rails needed for authorization rise before any PFC RUN command, and a rejected model with circular startup dependencies fails.
2. A missing source, missing return, swapped isolation domain or bypassed output protection fails its corresponding construction check.
3. A rail interruption followed by recovery leaves restart disarmed until the explicit Rev38 protocol allows it.
4. The unit's load ledger includes Rev38's current direct AUX branches and updates when that source changes; stale totals fail review.

## Open decision

Confirm whether this unit covers both HOT PFC bias and isolated SELV 15 V, or whether those are two separate standalone supply goals. The work can begin with a shared rail inventory while that decision is pending.

## Source anchors

- `zapote/power-entry/passive-reva/protection/interface-integration-38/STATUS.md`
- `zapote/power-entry/passive-reva/protection/interface-integration-38/HOT-RAILS.md`
- `zapote/power-entry/passive-reva/protection/interface-integration-38/AUX-OVP-WINDOW.md`
- `elec/src/modules.ato` (`AuxSupply`, historical full-board module)
- `zapote/gate-drive/INTERFACES.md`; `zapote/interlock/INTERFACES.md`

## Planning contract

The standalone rail inventory and source-selection record live under `zapote/auxiliary/`. The selected circuit will live under `zapote/auxiliary/source-build-01/`; Rust engineering rules belong in `zapote/packages/zapote-erc/` (or an existing Rust owner found during U1), with a thin adapter only if required. The PFC Rev38 files remain an external input and are not owned by this unit. Each acceptance record binds the Rev38 input revision and generated source/native hashes.

The review found a supply-domain ambiguity. U1 covers both HOT and SELV consumers for inventory; a decision at U1 exit chooses one combined implementation or two separately accepted supply units. Circuit selection cannot proceed on an implicit merged rail.

### U1. Reconcile rails and dependencies

Create `zapote/auxiliary/rail-ledger.md` and `zapote/auxiliary/interface-contract.md`. Trace every consumer from Rev38, accepted gate drive/interlock, existing buck/MCU and cooling candidates. Record min/nominal/max and pulse load only where evidenced; unknowns remain explicit. Draw the power and return domain graph, including AC entry before precharge and the exact isolation crossing. Decide the single versus separate source boundary using the graph and state the rationale.

**Check:** a second reader can trace every listed current to a source file or measurement, and can identify all missing loads without interpreting them as zero. Cross-check Rev38's direct AUX branch count against `AUX-WINDOW.md`.

### U2. Select and model source/protection candidates

For each selected supply unit, choose exact producer and protection candidate(s) using manufacturer limits. Calculate source/cable/consumer voltage and current corners, startup load waveform, dropout, surge and thermal limits. Model loss/return of source and a hiccup restart against Rev38's re-arm semantics. A source with only nominal load data cannot pass this unit.

**Check:** keep analytical inputs and expected reject cases under `zapote/auxiliary/evidence/`; tests in `zapote/packages/zapote-erc/tests/auxiliary.rs` reject missing return, crossed HOT/SELV boundary, unprotected output and circular startup graph. Vendor-model transients are evidence classed separately from guaranteed limits.

### U3. Construct and check the standalone circuit

Build the selected Atopile unit under `zapote/auxiliary/source-build-01/`, generate native artifacts, place and route a standalone board, and verify saved-byte source identity, ERC, DRC, native copper/domain boundaries and Rust rules. Export explicit rail/interface connector and BOM records. Re-run U2 when a part or source changes.

**Check:** accepted source/netlist/native hashes agree, adverse pin/return mutations fail, and the unit acceptance record lists unresolved startup, thermal, insulation and bench obligations without promoting them to a pass.

## Verification contract and definition of done

U1 may start now. U2 waits for the rail-ownership decision and actual load envelopes. U3 waits for U2's circuit selection. The standalone goal closes only when all three units have reproducible source/native/Rust evidence and an explicit digital construction verdict. Physical rail waveforms and insulation qualification remain subsequent measured work. Changes in Rev38, inverter gate demand or cooling fan load trigger ledger and protection rechecks.
