---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
title: "Zapote cooling and mechanical envelope unit"
date: 2026-09-23
execution: code
---

# Zapote cooling and mechanical envelope: requirements

## Problem and boundary

Prior bridge-cooling studies contain source-bound numerical candidates, but installed airflow, enclosure fit and complete PFC/inverter loss remain unknown. This track turns those studies into a shared mechanical and thermal envelope for separately constructed units. It owns a fan/duct/support concept and fan-fault signal contract. It does not certify a whole cooker or modify Rev38's electrical protection.

## Approaches considered

1. Extend only the existing bridge sink: smallest scope, but other PFC and inverter heat may invalidate its inlet and airflow assumptions.
2. Establish a whole-cooker loss/space ledger and compare independent and shared airflow paths while retaining the existing bridge models as controls. **Preferred** because it exposes cross-unit clashes without forcing integration layout now.
3. Freeze one shared fan/heatsink assembly immediately: convenient for CAD, but current loss and enclosure data are insufficient to justify its sizing.

## Requirements

- **C1. Heat ledger:** record each existing unit's loss estimate, evidence class, operating point and open measurements. Keep bridge, PFC switch/diode/inductor, inverter, aux and fan terms separate.
- **C2. Spatial envelope:** collect board outline, heat-source package orientation, sink, duct, fan, connector, insulation, support and service-clearance constraints. Mark unknown enclosure geometry explicitly.
- **C3. Airflow:** compare installed pressure/flow paths, inlet heating and recirculation. Free-air CFM or catalog thermal resistance alone cannot pass.
- **C4. Fault response:** specify tach/airflow/temperature input behavior, power-loss default and the interlock producer/consumer link. Separate warning and shutdown evidence.
- **C5. Evidence:** retain candidate identity and source files, reproducible thermal calculations, negative cases and a physical qualification protocol. A digital model may remain indeterminate for assembly applicability.

## Acceptance examples

1. A concept that assumes a fan's free-air CFM at a loaded sink without a pressure curve is rejected as unqualified.
2. A sink that relies on PCB leads for mechanical support fails the envelope review.
3. Missing inverter loss or enclosure clearance remains an open integration input, not a zero in the heat budget.
4. Loss of fan health maps to the standalone interlock's appropriate fault input and documented stop behavior.

## Source anchors

- `zapote/thermal/cooling-options/README.md`; `zapote/thermal/cooling-options/recommendation.md`
- `zapote/thermal/bridge-cooling.md`
- `zapote/power-entry/passive-reva/cooling/README.md`
- `zapote/interlock/INTERFACES.md`
- `elec/src/modules.ato` (`ThermalSystem`, historical fan circuit)

## Planning contract

Owned work lives under `zapote/thermal/cooker-envelope/`. Reuse existing `zapote/thermal/cooling-options/` and `zapote/thermal/bridge-cooling.md` as distinct candidate/model records. The fan source and any new numerical rule live in an existing Zapote Rust owner when its ownership is identified. The interlock fault-input interface is external; this track specifies its producer but does not alter the interlock's accepted board.

### U1. Assemble source-bound heat and space ledgers

Create `zapote/thermal/cooker-envelope/loss-ledger.md` and `zapote/thermal/cooker-envelope/space-ledger.md`. Trace each heat term, exact source revision, operating point and certainty. Keep the GBU and GBJ studies, their heatsinks/fans and their different boundary conditions separate. Record PFC, inverter, auxiliary and fan power as known, bounded or unknown. Capture each package/sink/duct footprint, orientation, support and insulation space claim; leave enclosure fit indeterminate until CAD is available.

**Check:** no blank term becomes zero, no free-air fan rating becomes installed flow, and the two bridge candidates are never combined into one false model. The ledger is inspectable without running an FEM solve.

### U2. Compare concepts with matched inputs

Evaluate independent versus shared airflow and the retained bridge concepts using an explicit loss/ambient/pressure range. Update or reuse the Rust thermal runner for calculations only after U1 binds input identities. Dimension a provisional duct, support and service envelope, preserving separate PCB and chassis load paths. Identify the minimum enclosure information needed for fit.

**Check:** model and fault scenarios in `zapote/packages/zapote-thermal/tests/cooker_envelope.rs` reject missing heat terms, mixed candidate identities, free-air-as-installed-flow and mechanically unsupported sinks. Record numerical sensitivity and an indeterminate result when data cannot support a ranking.

### U3. Define fan circuit and fault interface

Specify fan supply and tach/airflow/temperature producer, startup and stall behavior, filtering and the interlock fault interface. Construct a standalone fan control/sensing circuit if its electrical requirements are settled; otherwise retain a reviewed interface contract and open part-selection gate. Record the later physical airflow, thermal and fault-injection protocol against one identified assembly.

**Check:** missing/failed fan health cannot be interpreted as healthy; control-circuit source/native/Rust checks are required for any built circuit. Physical qualification remains `NOT RUN` until an assembled duct and heat sources are measured.

## Verification contract and definition of done

U1 starts now using retained evidence. U2 waits for candidate-specific losses and space inputs, and U3 uses the selected fan operating envelope. This track closes its standalone digital work with an evidence-backed cooling concept, mechanical envelope and checked fan fault interface. Assembly fit and thermal performance remain separate physical qualifications. Rev38 loss changes, inverter loss and auxiliary rail changes trigger ledger updates.
