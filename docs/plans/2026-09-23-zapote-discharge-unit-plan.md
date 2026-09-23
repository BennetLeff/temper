---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
title: "Zapote bus and local-reservoir discharge unit"
date: 2026-09-23
execution: code
---

# Zapote bus and local-reservoir discharge: requirements

## Problem and boundary

Rev38 separates a roughly 390 V bank node VB from a diode-side VD reservoir by F2. The legacy full-board `BusDischarge` spans two approximately 170 V half-buses. Its contact and resistor network cannot be reused without checking voltage, energy, interruption and what remains charged after F2 opens. This unit owns the discharge paths and observability for **each retained energy island**. Rev38 owns F2, protection and restart authorization; the inverter later adds its own input capacitance and possibly other stored energy.

## Approaches considered

1. Passive bleeders on every island: simple and independent of logic, but dissipate continuously and may be too slow at worst-case capacitance.
2. Normally engaged active paths plus passive backup: prompt discharge on power loss with explicit failure cases, at the cost of contacts or semiconductor stress and control sequencing. **Preferred for evaluation** because it can express a power-loss response without MCU action.
3. One bank-wide active path: fewer parts, but F2 opening can strand VD and an inverter-side disconnect can create another island.

The actual topology and numeric time/voltage threshold require a frozen energy inventory and adopted product requirement. Earlier half-bus values are historical, not a 390 V acceptance claim.

## Requirements

- **D1. Island map:** enumerate VB capacitors, VD reservoir and any downstream bus capacitors with maximum initial voltage, tolerance, energy and isolation element between them.
- **D2. Discharge scenarios:** model mains removal, normal stop, auxiliary loss, F1/F2 open, welded/open contact, failed resistor or switch, and reconnection while residual charge remains.
- **D3. Default behavior:** required discharge must start without MCU firmware after loss of its control supply. Any deliberate hold-off while operating must have a physical, fail-low control contract.
- **D4. Component envelope:** bound initial current, pulse energy, sustained dissipation, DC contact/switch duty, voltage sharing, temperature and assembly clearances using exact parts.
- **D5. Observability:** state how VD and VB are measured or otherwise verified before service and restart. Equality of two voltages is not proof of F2 continuity or of zero stored energy.
- **D6. Standalone evidence:** source-derived circuit, routed unit, Rust checks with failed-element mutations, native checks and reproducible evidence. Physical discharge timing remains a separate measured qualification.

## Acceptance examples

1. With F2 open at the initial maximum charge, the model evaluates VD and VB separately and rejects any topology that only discharges one side.
2. Removing auxiliary power invokes the intended discharge path without a firmware command.
3. A welded-open active contact or open resistor is reported as an uncovered failure rather than a passing nominal discharge.
4. A restart request with residual charge cannot be promoted merely because VD and VB are equal.

## Source anchors

- `zapote/power-entry/passive-reva/protection/interface-integration-38/PFC-POWER.md`
- `zapote/power-entry/passive-reva/protection/interface-integration-38/STATUS.md`
- `elec/src/modules.ato` (`BusDischarge`, historical split-bus module)
- `docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md`
- `docs/evidence/2026-07-28-discharge-relay-isolation.md`

## Planning contract

Owned artifacts live under `zapote/discharge/`, with source under `zapote/discharge/source-build-01/`. The existing `elec/src/modules.ato:BusDischarge` is a historical comparison, not source authority for the new circuit. Rev38 F2, VD/VB and restart logic are external inputs. Rust rules belong with the existing Zapote Rust validators; tests use `zapote/packages/zapote-erc/tests/discharge.rs` unless U1 identifies a more specific owner.

### U1. Freeze energy islands and requirement

Write `zapote/discharge/energy-islands.md` and `zapote/discharge/interface-contract.md`. Derive VB, VD, F2 and any downstream capacitance from the saved Rev38 source, including tolerances and maximum voltage. Identify physically accessible nodes and the adopted post-power-removal voltage/time requirement from project authority. If no applicable requirement is established, retain it as a decision gate and do not size a circuit to a borrowed number.

**Check:** an F2-open drawing has separate VD and VB charge paths; a single-open bleeder and loss of control supply each have a stated observable outcome. The source commit and part identities are recorded.

### U2. Choose topology and verify worst-case discharge

Compare passive-only, active plus passive and per-island alternatives. Evaluate RC or current-limited discharge across C/V/R tolerances, charge state, temperature, DC contact/switch ratings, pulse energy and continuous-fault dissipation. Include the inverter's declared local capacitance as a parameter; rerun if it changes. The output is one circuit choice or an evidence-backed blocker, not an arbitrary fast-path target.

**Check:** analytical and simulation fixtures under `zapote/discharge/evidence/` cover mains loss, F2 open, partial charge, stuck/open contact, open resistor and restart with residual charge. `zapote/packages/zapote-erc/tests/discharge.rs` rejects a missing VD or VB path and a control-only default state.

### U3. Construct and accept the standalone unit

Capture exact selected parts in Atopile, produce native schematic/board and route the standalone unit. Validate source/native identity, isolated control boundary, DC spacing, copper connectivity, thermal placement and F2 separation using Rust plus native checks. Record the physical discharge timing and fault-injection protocol for the later assembled test.

**Check:** source and board hashes bind to the same accepted unit, fault mutations fail, and `zapote/discharge/ACCEPTANCE.md` distinguishes digital construction from measured safe-discharge performance.

## Verification contract and definition of done

U1 starts now. U2 needs U1's adopted requirement and Rev38 energy map. U3 needs U2's exact part/topology disposition. The unit closes on a routed, reproducibly checked standalone discharge circuit with all energy islands accounted for. Any Rev38 capacitor/F2 or inverter input-capacitor change triggers U1/U2 replay. Physical service and discharge claims wait for measurement.
