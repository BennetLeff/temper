---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: "four Zapote unit plans dated 2026-09-23 and their U2 review"
title: "Zapote parallel units: next digital milestone"
date: 2026-09-23
execution: code
---

# Zapote parallel units: next digital milestone

## Goal and authority

Advance the auxiliary, discharge, inverter and cooling tracks one independently reviewable step beyond the U2 screens in `docs/evidence/2026-09-23-zapote-parallel-u2-review.md`. The four existing unit plans retain product requirements and standalone digital-construction definitions of done. This plan specifies the next **bounded digital evidence** milestone. It cannot grant a high-voltage circuit selection, physical safety claim, or whole-cooker acceptance.

The active Rev38 power-entry checkout is moving and may contain uncommitted work. Every new screen must name the exact committed source or saved-file SHA-256 it uses, distinguish provisional live inputs, and require replay when the source changes. Do not edit Rev38. A result is `conditional`, `rejected`, or `indeterminate` against declared inputs; an omitted load, waveform, return or fault path never becomes zero or a pass.

## Reviewed approach

| Unit | Next result reachable now | Construction or physical result still gated |
| --- | --- | --- |
| Auxiliary | Lab-only, low-voltage HOT rail-order connector fixture and executable fault matrix for AUX/logic5 sequencing. | Physical mating/captures need a reviewed Rev38 native pad map **and a separately reviewed isolation/instrumentation setup**; HOT producer choice needs complete loads and fault waveforms. |
| Discharge | Parameterized, source-locked validation gate for the two-island candidate, with fault-specific results and thermal handoff. | Candidate native circuit needs an adopted discharge rule, exact orderable parts, a qualified coil rail and installed thermal path. |
| Inverter | Coupled VB/VD bank and half-bridge/tank transient screen with explicit source, F2 and gate-off schedules. | Operating frequency, switching parts and native circuit need measured loaded coil/pan impedance and VB/gate/fault-loop waveforms. |
| Cooling | Typed Rust candidate/fault gate that rejects mixed package models and unqualified airflow, including discharge heat during fan loss. | Fan circuit/trip setting needs selected rail/fan, installed flow, mounting and stop-latency measurements. |

These are real executable artifacts and negative controls. An analytical fixture may reject an impossible assumption; it may not certify an installed circuit. Use existing Rust owners where practical; no new Python single source of truth. The auxiliary connector fixture is the only planned Atopile source and must have no AC, VD, VB or PFC power connection. HOT0 is a mains-referenced return on an energized Rev38 board: this milestone permits the fixture only with a standalone, mains-disconnected/unenergized DUT and isolated current-limited sources. Any later live-board hookup needs a separate isolation/instrumentation review.

## Implementation units

### P1. Auxiliary rail-order laboratory fixture

Own `zapote/auxiliary/rail-order-fixture-01/**` and `zapote/auxiliary/evidence/rail-order*`. Freeze the committed Rev38 driver-stage net names and the current provisional gate-enable-corner source by hash. Construct a small standalone Atopile connector/test-point fixture for independent, current-limited `AUX_PROTECTED` and `HOT_LOGIC5` inputs sharing HOT0, and observation only at `DRIVER_PERMISSION`, `ENA_NODE`, `EN_SHUNT_BASE`, `PFC_PWM`, `STW_GATE`, `HOT_RUN_Q` and `HOT_SESSION_Q` as present in the frozen source. Label it LAB ONLY. Use it only on a standalone, mains-disconnected DUT with isolated current-limited supplies; its HOT0 becomes hazardous if joined to energized Rev38 even though the fixture carries no AC net. Physical mating to any powered Rev38 board is outside this milestone and requires separate pad, isolation, instrument and operator-protection review. Do not connect a SELV return or bypass a protection element.

Add a Rust source/netlist check and a deterministic rail-order event matrix. Reject a HOT/SELV join, hidden AUX↔logic5 tie, unintended power feed into a probe, missing observation, fault-masked ENA and rail recovery treated as ARM. Exercise AUX-first, logic5-first, partial logic5, either-rail loss, repeated hiccup/brownout, stuck-high request and recovery without deliberate re-arm. The digital result is fixture connectivity and expected observations, **not** proof of actual gate shutdown timing or source adequacy. If exact pad mapping prevents compileable fixture construction, complete the source-bound event matrix and report the precise interface blocker instead of inventing a connector.

### P2. Discharge candidate selection gate

Own `zapote/discharge/**`; extend `evidence/discharge_screen.rs` rather than introducing competing discharge arithmetic. Add an executable scenario interface and `evidence/selection-gate.md` with a bench-qualification protocol. Accept only explicit scenario inputs for initial/max voltage, target voltage/time, VD/VB and direct inverter capacitance, F2 state, contact release, pickup, hold and dropout bounds, coil-rail recovery/chatter schedule, component tolerance/drift, mains isolation and single-fault policy. Historical 34 V/60 s is an illustrative input, never the embedded product requirement. Report `conditional`, `rejected` or `indeterminate` with reasons and resistor watts/joules.

Negative controls must cover separate VD/VB paths after F2 opens, combined capacitance and conductance when F2 stays closed, an inverter-side disconnected capacitor, one resistor/contact open or short, AUX loss while mains still feeds VD/VB, 15.75 V direct feed to a 12 V coil whose datasheet maximum is 15 V, repeated AUX brownout/recovery that chatters or recloses the contact against a charged bus without DC-life and timing evidence, and equal nonzero VD/VB readings offered as restart proof. Do not turn a source-current omission into RC decay. A fault that engages the resistor while the fan is off requires an installed thermal path; the RH50 mounted rating's 536 cm² chassis fixture cannot be credited automatically. A conditional Atopile candidate follows only if exact resistor order codes, coil supply and selection criteria are established.

### P3. Coupled bank/tank transient screen

Own `zapote/inverter/**`. Add a deterministic Rust model with scenario input, saved output and independent analytical oracles under `zapote/inverter/evidence/`, plus a conditional report `zapote/inverter/U2-TRANSIENT.md`. The state includes VD and VB capacitor voltage, tank current and capacitor bias. Model an ideal 50% half bridge, a declared nonnegative VD source-current command clipped by explicit current and power limits (no reverse source flow), F2 fixed-open or fixed-closed, passive bleed, and PWM/PERMIT/gate-loss delay as declared inputs. A source-off schedule commands zero current. Resolve diode/freewheel state explicitly or mark that interval indeterminate; do not assert instantaneous current zero on gate disable. An F2 opening at nonzero interconnect current has unmodeled inductive/arc/snubber energy and cannot receive a conservation verdict across the transition. Either start an open-F2 case from a declared post-open VD/VB state and account for externally transferred energy, or add a qualified interconnect-current and interruption model; otherwise report the opening interval `indeterminate`. Reject F2 reclosing at unequal node voltages unless the interconnect R/L path is modeled. The failed-short bank loop remains unbounded until its real topology and R/L are supplied.

Cases: cap bias at zero and steady VB/2, low loaded L/C with stiff versus limited/off source, no-pan/weak-pan, PWM or gate-rail loss, F2 opening while VD source persists, F2-open VB droop and VD rise, source loss, and direct inverter local-C energy. Verify energy conservation within each fixed F2 topology, source-off RC behavior and timestep convergence; include negative controls for wrong historical midpoint, missing loaded-coil bound, overrating and claiming current stops at command time. Report transient duration and a conservation ledger: source and stored energy, declared resistive coil/pan/bleed losses, and an explicit **unallocated device/capacitor/switching-loss** term. Hand only modeled ohmic locations to cooling/discharge; missing switching, diode, capacitor, frequency and thermal data leave their heat indeterminate. Modelled waveforms are scenario sensitivities; no device or capacitor thermal pass follows from ideal switch/diode physics.

### P4. Cooling and fan-fault Rust gate

Own `zapote/packages/zapote-thermal/src/cooker_envelope.rs`, its `lib.rs` registration and `tests/cooker_envelope.rs`, plus `zapote/thermal/cooker-envelope/**`. Keep GBU-395, GBU-392 and GBJ-392 as distinct typed candidates. Require evidence class and exact package/sink/fan identities. A free-air fan endpoint cannot substitute for installed fin-path flow; missing whole-cooker heat, support path, pressure curve or heat destination yields `indeterminate` or `invalid`, not a passing assembly.

Reproduce the retained conditional 120.0 °C GBU-395, 118.64 °C GBU-392 and 59.639 °C GBJ-392 screens without mixing package networks. Mutate inlet and shared heat so GBJ's fixed 60 °C FEM boundary is invalidated. Add an explicit AUX-loss/mains-attached/fan-off discharge case: 21.33/27.0 W intact or 32.0/40.5 W with one short at 400/450 V, with an unqualified chassis path. Test paired J1-4 Heatsink fault and J2-5 SENSOR_LIVE outputs: cooling rail loss, sensing-rail loss, sensor invalidity, reset and open wire must each map to fault-high and/or sensing-invalid as applicable, with no healthy permission. Exercise startup grace without PERMIT, stall and auto-recovery latch, and fresh deliberate reset after full power loss without claiming durable fault memory. Record the logical interlock → Rev38/inverter permit truth table, while leaving actual downstream stop timing unqualified. Preserve J1-4 voltage/leakage and J2-5 validity contracts as requirements, not electrically proven properties of an unbuilt driver. Fan-circuit construction and trip timing remain blocked on selected rail/fan and installed transient evidence.

## Coordination and verification

P1, P2, P3 and P4 own disjoint files and can execute in parallel after this plan's review. Each worker is not alone in the repository, must not revert another's work, and must not commit; the coordinator reviews and commits the combined result. Keep external Rev38 sources read-only. Any shared interface change is reported to the other owners before their final model is frozen.

For each unit, retain reproducible command/fixture input and a negative control that would have failed the incorrect U2 assumption. The coordinator independently reruns targeted Rust/Atopile checks, source hashes, saved-output replay, formatting and diff checks, then reviews the cross-unit matrix and commits the result. Do not run full-board qualification or claim an assembled cooker test.

## Definition of this milestone

Each unit has an executable saved-byte artifact, an adverse-case receipt and a clear conditional/rejected/indeterminate verdict. The review record explains any model correction, remaining blocker and cross-unit handoff. A unit may stop early at a precise verified interface blocker only if further circuit work would require invented voltage, load, connection or geometry. Standalone digital construction acceptance remains a later milestone unless the unit's original plan's source/native/Rust criteria are actually satisfied.
