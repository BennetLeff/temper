---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
title: "Zapote switching and resonant inverter unit"
date: 2026-09-23
execution: code
---

# Zapote switching and resonant inverter: requirements

## Problem and boundary

The existing full-board source has a half bridge and resonant tank, and a separate isolated gate-drive unit passed digital construction checks. Neither establishes a qualified inverter/coil power path on Rev38's VB bus. This unit owns DC-to-resonant conversion, coil/tank interfaces, local protection and a standalone board. Rev38 supplies a bounded bus and bank-ready/stop contract; the gate-drive unit supplies a conditional logic and gate boundary. Pan heating and cooker temperature control require later integration and hardware evidence.

## Approaches considered

1. Rehost the legacy half bridge and tank unchanged: fast source reuse, but it imports assumed coil parameters, outdated bus topology and unresolved switch stress.
2. Reconcile the existing design against measured/declared loaded-coil and Rev38 bus envelopes, then build one standalone candidate. **Preferred** because it retains useful source while rejecting assumptions that no longer fit.
3. Design a fresh inverter topology: potentially useful if reconciliation fails, but higher cost and no current evidence that it is necessary.

## Requirements

- **I1. Input contract:** define allowed VB voltage, ripple, transient, startup and collapse, local bus capacitance and return domain. Do not inherit a 390 V nominal value as a worst-case rating.
- **I2. Resonant contract:** identify coil geometry, unloaded and loaded inductance range, pan/coupling conditions, tank capacitance tolerance, operating frequency range and no-pan behavior. Frequency claims must use loaded inductance.
- **I3. Switching stress:** establish device voltage/current, commutation, startup/stop, no-pan and fault envelopes with model uncertainty visible.
- **I4. Shutdown:** a low or absent PERMIT must stop commanded switching; define the separate response to a failed-short switch, gate-drive loss and a bus that remains energized.
- **I5. Interfaces:** reconcile PWM, PERMIT, 3V3, isolated low-side 15 V and Kelvin gate returns with the accepted standalone gate-drive contract; name any change as a cross-unit revision.
- **I6. Standalone evidence:** compiled source, native layout, actual Rust construction checks, adverse cases and digital acceptance. Loaded switching, EMC, heating and physical timing remain unqualified until measured.

## Acceptance examples

1. A design using the unloaded coil inductance for its operating-frequency claim fails review when the declared loaded range differs.
2. A loss of PERMIT or gate-drive supply cannot leave PWM driving the half bridge in the unit model.
3. The source/native board preserves the exact Kelvin and isolation boundaries; a return swap fails validation.
4. A bus transient beyond a selected device limit is a failing case, not silently clipped to nominal 390 V.

## Source anchors

- `elec/src/main.ato` (`HalfBridge`, `ResonantTank` composition)
- `elec/src/modules.ato` (historical inverter/tank source)
- `zapote/gate-drive/INTERFACES.md`; `zapote/gate-drive/ACCEPTANCE.md`
- `zapote/power-entry/passive-reva/protection/interface-integration-38/PFC-POWER.md`
- `docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`

## Planning contract

Owned work lives under `zapote/inverter/` with source in `zapote/inverter/source-build-01/`. The old full-board half bridge and tank are reuse inputs, not an automatically accepted source. Rev38 and the accepted gate-drive unit own their interfaces. New engineering validation belongs in the Zapote Rust crates, with tests at `zapote/packages/zapote-erc/tests/inverter.rs` or the more specific existing owner U1 identifies.

### U1. Reconcile bus, gate and coil envelopes

Create `zapote/inverter/interface-contract.md` and `zapote/inverter/coil-evidence.md`. Bind Rev38's VB/return and fault/stop signals to the gate-drive connector contract. Inventory legacy tank/coil assumptions and distinguish measured, manufacturer-qualified and illustrative parameters. Derive a bounded loaded-inductance and pan-state matrix or explicitly identify the missing measurement campaign. Define input capacitance for the discharge unit and losses/heat locations for cooling.

**Check:** no frequency, current or ZVS conclusion uses free-air inductance in place of the loaded value. Every bus maximum and gate rail has a source and revision identity. A missing coil bound prevents circuit acceptance while still allowing the interface work to finish.

### U2. Analyze one candidate operating envelope

Use the existing half bridge/tank as the first candidate after U1. Evaluate startup, no-pan, pan coupling range, stop, DC bus transient, gate loss, switching loss, tank capacitor RMS/pulse and failed-switch scenarios. Compare numerical model outputs to independent device/component limits and record model limitations. Select parts and frequency limits only when the envelope is internally consistent.

**Check:** fixtures under `zapote/inverter/evidence/` include negative controls for too-high bus voltage, invalid loaded inductance and loss of gate supply. Rust tests at `zapote/packages/zapote-erc/tests/inverter.rs` reject invalid boundary mappings and out-of-envelope source values. A failed-short switch is reported as beyond gate disable, with its separate interruption path named.

### U3. Construct the standalone inverter unit

Capture the selected source, generate and route the native candidate, preserve gate Kelvin and isolation nets, check copper/thermal/current loops and source/native parity, then issue `zapote/inverter/ACCEPTANCE.md` with a digital construction verdict and exact hashes. A test fixture may use a bounded programmable DC source for later staged hardware work; no mains or heating test is implied by digital acceptance.

**Check:** native and Rust checks pass on the saved bytes; a Kelvin/return swap, disconnected permit and over-limit component mutation fail; the physical qualification list covers loaded switching and heating.

## Verification contract and definition of done

U1 starts now against Rev38 at the recorded base revision. U2 requires bounded bus and loaded-coil inputs. U3 requires U2's selected source and part limits. This unit closes at standalone digital construction acceptance; integration, EMC, assembled heating and temperature control remain separate. Bus capacitor and loss changes flow to discharge and cooling ledgers.
