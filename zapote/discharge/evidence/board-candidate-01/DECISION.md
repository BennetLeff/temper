# Discharge board candidate 01 — design hold

Date: 2026-09-23. Status: **NO PRODUCT PCB; design-freeze gate open**. This is a decision record, not a schematic, BOM, routed board, physical test, or release approval.

## Source boundary checked

The committed Rev38 source under `zapote/power-entry/passive-reva/protection/interface-integration-38/elec/src/` declares `VD_LOCAL -- F2 -- VB_BANK` with `HOT0` common return (`pfc_power.ato:70–126`, `power_entry_integrated_38.ato:60–75`). VD holds 22 µF + 470 nF candidate film capacitance; VB holds four 560 µF candidate electrolytics. `f2_detector.ato:115–130` senses both nodes for F2-related protection, but the joined source declares no output/service connector or dedicated discharge-control/status port. The current committed source is protected by `../source-inputs.sha256`; the active separate Rev38 checkout is not an input to this decision. The VD/VB capacitor totals, tolerance and energy are in `../../energy-islands.md`.

The prior U2 candidate has two four-element 200 kΩ VD strings and a single NC contact feeding two two-element 7.5 kΩ VB branches, with existing Rev38 resistors left in place. It is a **topology screen**. At 450 V, +100 µF direct inverter C and a 5 s contact allowance, its ideal 450 → 34 V / 60 s illustrative screen has only 0.45 s F2-open VB margin; one VB resistor open takes 114.10 s. One contact failing open removes both fast VB branches. That alone rules out representing the present layout as a fault-qualified fast discharge board. The 450 V number is a capacitor rating-edge sensitivity, not the allowed operating envelope.

## Exact decisions needed before copper

| ID | Decision / evidence artifact | Owner to supply | Why layout or topology can change |
| --- | --- | --- | --- |
| G1 | Adopted post-power-off service voltage and time for VD, VB and any detached inverter island, with applicability and measurement method | Product/safety authority | Sets resistance, energy, thermal and restart thresholds. The historical half-bus target is not transferable. |
| G2 | Maximum operating and fault-transient VD/VB voltages, source current while mains attached, F2 clearing/open behavior | Rev38 power-entry owner | Determines resistor count/spacing, contact DC duty, continuous fault heat and whether a passive source can recharge either island. |
| G3 | Maximum direct inverter input C, detached C, disconnect position and bridge-short behavior | Inverter owner | Sets bank energy, creates possible third island, may demand another discharge path and sense point. |
| G4 | Acceptance after one open resistor/contact and an open sense path; service lockout/rearm rule | Product/safety authority + controls owner | A single NC contact common to both VB branches cannot satisfy a normal fast deadline after contact-open failure. |
| G5 | Coil or gate-bias source min/nom/max over operating, brownout and mains-attached AUX loss; loaded release time | Auxiliary + discharge owners | The screened Coto 12 V coil has 15 V maximum while a proposed AUX upper bound is 15.75 V; direct feed is invalid. Typical release is not a worst-case bound. |
| G6 | Exact switch and resistor order codes, DC switching life, pulse/repeated energy, chassis contact, four-resistor aggregate heat and fan-off temperature | Discharge + cooling owners | The RH50 40 W at 70 °C uses a specified 536 cm² chassis; a bare PCB and stopped fan do not inherit it. |
| G7 | Independent absolute VD and VB observation while powered off, open-sense detection, and deliberate restart inhibit/rearm; define connector/access geometry | Rev38 + service/controls owners | F2 detector equality and a dead HOT comparator cannot authorize service or restart. Direct HOT0 wiring must retain the isolation boundary to SELV UI. |

Each item needs an identified article, source/part revision, test range and independent review. A filled placeholder or catalog headline alone does not close it. Run the existing `qualification.rs` manifest gate for measurements; it deliberately stays indeterminate without external physical review.

## Required interface request to Rev38 / integration

1. Reserve **separate** VD-to-HOT0 and VB-to-HOT0 rated discharge connections on the correct sides of F2. Do not bridge VD and VB through the discharge board or its measurement harness. The allowed connector scheme, wire fault protection, PCB creepage and access rules must be designed with the frozen voltage envelope.
2. Provide a bounded active-path hold supply or control input if that topology survives G1–G6. Define the default on AUX brownout/loss and mains-attached operation as physical circuit behavior. No MCU-only discharge trigger is sufficient.
3. Provide independent absolute residual-charge evidence for VD and VB, or define a verified technician measurement procedure and no automatic rearm. A sense-open, supply loss or unknown reading maps to unsafe/unknown; `VD = VB > 0` is not a restart permit. The F2-state observation is separate from absolute voltage.
4. Identify any downstream inverter disconnect and its isolated-capacitor access and observation path. The board interface cannot be finalized while `C_inv` and this topology are unknown.

This request is an interface contract for the **next Rev38/integration revision**. It asserts no such port is present now and does not edit the active Rev38 work.

## Verification performed and remaining

The existing digital gate has a saved 45-case F2/mains/fault sweep and rejects source hash drift, missing VD/VB paths, a mains-live RC deadline, equal-charged restart and a detached unbled inverter island. It establishes preparation, not discharge safety. The next measured sequence is: freeze G1–G4; bench-check exact DC contact and coil under a current-limited isolated article; measure installed resistor temperature with fan off and mains-source equivalent stress; then construct the product standalone unit and run the `../../bench-qualification.md` protocol. Until those inputs exist, `source-build-01` and native KiCad files are intentionally absent.

This decision was replayed with `shasum -a 256 -c ../source-inputs.sha256` (all five Rev38 source files matched), `rustc --edition=2021 --test ../discharge_screen.rs` (27 tests passed, including the nested qualification tests), and `discharge_screen --case ../isolated-illustrative.case` (exit 2, **INDETERMINATE**). Commands were run from the repository root with the corresponding full `zapote/discharge/evidence/` paths. `qualification.rs` is included by `discharge_screen.rs` and is not a standalone crate root.
