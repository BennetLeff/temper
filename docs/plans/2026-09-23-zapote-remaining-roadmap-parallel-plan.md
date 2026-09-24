---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: "Zapote roadmap and four 2026-09-23 unit plans"
title: "Zapote remaining roadmap: parallel readiness and construction work"
date: 2026-09-23
execution: code
---

# Zapote remaining roadmap: parallel readiness and construction work

## Goal and boundary

Advance roadmap milestones 5–9 concurrently where their inputs are independent. Deliver the furthest reproducible **digital** artifact possible for each remaining unit and for integration/release preparation. A checker may reject an invalid connection or missing evidence, but cannot turn a missing measurement into a selected circuit or an unassembled board into a tested appliance. The active Rev38 protection/restart checkout is separate, moving and read-only for this work. Source claims bind committed bytes at `25715e6bb` or explicit file hashes; changes require replay.

The four existing unit plans define each unit's final standalone digital construction acceptance. This plan does not weaken them. The roadmap orders actual composition after standalone unit acceptance, release after a frozen complete board, and physical verification after assembly. These dependencies still apply even while readiness work runs in parallel.

## Reachable results and hard gates

| Workstream | Result to implement now | Gate to the next physical or native construction milestone |
| --- | --- | --- |
| Auxiliary | Source-locked rail/domain/load completeness and startup-dependency gate, with explicit missing-envelope verdicts. | Complete HOT/SELV/isolated-bias/fan loads and fault waveforms; selected protected source, parts, branch protection and isolation policy. |
| Discharge | Evidence-linked qualification completeness gate and full fault/topology sweep; bare `*_verified` booleans cannot grant a conditional hardware verdict. | Adopted service voltage/time rule, bounded VD/VB and inverter capacitance, qualified coil rail/contact DC life, installed fan-off heat path. |
| Inverter | Source-locked measurement-readiness gate for loaded coil/pan, VB/VD, gate stop, F2 and short-loop evidence. | Actual impedance and waveform bounds, selected switch/cap/frequency and physical fault containment. |
| Cooling/fan | Fan/rail/fault-interface gate with time-domain adverse cases and global sensing-validity handoff. | Selected fan and rail, startup/stall/tach data, installed airflow, temperature-lag/trip window, joined stop timing. |
| Programming/UI | Reconcile MCU firmware/native pin and domain claims; build only a conditional SELV programming interface candidate if the existing pin/boot contract supports it. | Resolve USB versus GPIO19/20, IO17, I²C isolation, product UI controls, connector/ESD and enclosure/access requirements. |
| Integration | Source-locked typed cross-unit connection and acceptance-readiness matrix. | Accepted native units and a new voltage-sense interface suitable for the ~390 V Rev38 bus; all rail, return, stop, thermal and mechanical contracts settled. |
| Release and assembled test | Fail-closed digital evidence manifest and staged, explicitly unperformed hardware-test protocol. | Frozen integrated board, exact BOM/fab artifacts, full suite/ERC/DRC, assembled article and qualified measurement campaign. |

The accepted voltage-sense J1 is an old 170 V half-bus, 0–250 V interface with a different return contract. Directly connecting it to Rev38 `VB_BANK/HOT0` is a **blocked** integration edge, not a mapping to be renamed. The accepted gate-drive `PERMIT` is inverter-specific; PFC RUN is not its substitute. `SENSOR_LIVE` needs an integration owner across all relevant sensing units. Existing MCU source, firmware pin declarations and control-assembly artifacts conflict on USB IO19/20 and fault/LED assignments; do not call that MCU assembly accepted or attach a new UI to it without reconciliation.

## Implementation units and ownership

### R1. Auxiliary U3 readiness

Own `zapote/auxiliary/**`. Reconcile committed Rev38 rail branches and all known consumers in the existing rail ledger. Add a machine-readable input inventory, Rust completeness/graph gate and receipt. Each consumer has domain, return, source identity, steady/start/pulse/dropout/fault bounds and evidence class; missing values are explicit `UNKNOWN`, never zero. Distinguish HOT AUX, HOT_LOGIC5, SELV 15/3V3, inverter isolated bias and fan rail. Test hidden HOT0↔SELV join, omitted direct AUX branch, source startup depending on PFC RUN, protection bypass, rail recovery mistaken for ARM, and H1/H2 local margins mistaken for total supply adequacy. Source selection stays indeterminate when dynamic loads or insulation policy are missing. No energized fixture hookup.

### R2. Discharge U3 qualification readiness

Own `zapote/discharge/**`. Add an evidence manifest with source hashes and reviewable records for the adopted criterion, exact part variants, maximum island voltage/capacitance, coil waveform/contact life, fan-off mounted heat, F2/sense/service/rearm and detached inverter energy. Each claim names evidence kind, article/case and parameter range, raw-record hash, and independent adoption/review identity. A self-authored manifest alone only establishes completeness and byte integrity; without independently reviewed physical evidence, the hardware verdict remains `indeterminate` even when all rows are present. Extend or wrap the existing gate so bare `*_verified=true` cannot create a conditional result without matching evidence identity. Sweep the existing fault variants across F2 open/closed and mains isolated/attached; retain the distinction between `rejected` and `indeterminate`. Reject a stale source, direct 15.75 V feed to a 12 V/15 V-max coil, missed island, mains-live RC deadline and restart from equal charged VD/VB. Do not author a selected native circuit while the product rule and parts remain unqualified.

### R3. Inverter U3 measurement readiness

Own `zapote/inverter/**`. Add a typed measurement manifest, Rust source/completeness gate, adverse scenario set, saved output and capture protocol. Require coil/pan article identity, loaded complex impedance and uncertainty over frequency/current/temperature, no-pan and pan-placement/removal states; VB/VD startup/ripple/surge/source bounds; loaded gate/PERMIT/rail-loss current-zero captures; F2 and direct-bank fault-loop evidence; local capacitance and exact part limits. Reject free-air L as loaded, a single favorable pan as product envelope, historical 47 kHz as selected, 390 V nominal as maximum, PWR_RTN as Rev38 return, gate-off as instantaneous current zero, and F2 as a direct-bank-short interrupter. Synthetic control rows may validate the checker but cannot qualify parts or a native inverter.

### R4. Cooling/fan U3 readiness

Own `zapote/thermal/cooker-envelope/**` and new files within that subtree. Add a source-bound fan/electrical-interface gate and timed fault matrix. Keep Sanyo and two-Sunon candidates distinct. Require terminal voltage, startup/stall current, per-fan tach, actual airflow/pressure evidence, blocked-inlet detection independent of tach, sensor accuracy/lag and a nonempty trip window. Preserve J1-4 low/high/leakage and power-off behavior as requirements, not proven electronics. Cooling produces a validity contribution to J2-5; it cannot claim global `SENSOR_LIVE` high. Negative controls cover one missing tach, plausible tach with blocked flow, rail brownout, stuck line, fault-held reset, auto-recovery and one invalid sensor among valid peers. No fan/control native circuit until supply, fan variant and trip requirements are selected.

### R5. Programming/UI standalone interface candidate

Own new `zapote/programming-ui/**` and its dedicated unit plan only. Bind legacy Atopile, firmware pin declarations and MCU artifact identities in a pin/domain ledger. Surface USB IO19/20 versus GPIO19/20 relay/fault allocations, IO17 fault versus LED, IO0 boot strap, and the unbuilt I²C isolator claim as blocked decisions. A conditional UART TXD0/RXD0 plus EN/IO0 SELV service candidate may be captured in Atopile and checked against a generated netlist; it does not decide product UI or claim that the MCU assembly is accepted. A programmer-triggered ESP reset is a power-stage event: before service access can be electrically acceptable, require either verified energy isolation/discharge before connector access or measured reset-to-both-stage-stop with no automatic rearm. Rust negative controls reject swapped directions, held-low EN/IO0, duplicate pin allocation, missing 3V3/return, false isolation, powered-off I/O backfeed and a reset that leaves the stage permission latched. If source/native construction needs an invented connector, stop at the source-bound contract and state the exact blocker.

### R6. Integration readiness

Own new `zapote/integration/**` and its dedicated plan. Create a source-locked manifest of unit acceptance status and typed ports (domain, return, direction, voltage/current envelope, fault default and timing evidence), binding each port to real source/netlist/native pin-pad-net identity where that artifact exists. A manually typed compatible domain without corresponding native identity cannot grant readiness. Rust checks emit per-edge `blocked`, `indeterminate`, or `ready for design` plus a deterministic matrix. Reject stale or absent files, HOT0↔SELV joins, direct 170 V sensing on 390 V bus, PFC RUN used as inverter PERMIT, absent global `SENSOR_LIVE`, equal VD/VB as proof of F2 continuity, and omitted fan-off discharge heat. Enumerate every sensing-validity contributor and cooling/interlock fault through to both PFC inhibit and inverter PERMIT, including unpowered and open-wire defaults; missing links remain blocked. Model the separate gate-drive `HV_RETURN` to Rev38 `HOT0` low-side Kelvin connection as **indeterminate** until the join location, isolated-bias and return-current path are reviewed; it may not silently merge with `CTRL_GND` or carry bank current in a gate lead. `Ready for design` is permission to start composition only after all required native units and contracts are accepted; it is never a whole-board pass. Do not edit an integrated PCB.

### R7. Release and hardware-test readiness

Own new `zapote/release/**` and its dedicated plan. Add a fail-closed manifest/checker with a closed registry of mandatory roles for the frozen cooker: unit and integrated sources, integrated PCB, firmware, adopted Rust suite, native ERC/DRC, exact BOM, fab/assembly outputs, and isolation, stop, discharge and thermal obligations. Every role receives explicit `PASS`, `FAIL`, `INDETERMINATE`, or `NOT_RUN`; a missing role cannot disappear from the denominator. Bind every present artifact and tool identity by SHA-256. Its current stage is `preintegration`; empty identity fields are absent evidence, not fabricated hashes. A hash proves file identity only: release status must be derived from replayed checks or machine-generated receipts that bind the exact command, exit code, input-board hash, tool version and raw output. A handwritten `PASS` field is never release evidence. Mutations reject altered bytes, duplicate or omitted roles, standalone-board substitution and a forged all-pass release verdict. Produce a physical test-record template and unperformed stages: article inspection/isolation, current-limited low-voltage rails, isolated energy-limited HV DC, controlled PFC, inverter load/pan, thermal endurance and cross-unit faults/restart/service. Entry to energy-limited HV DC explicitly requires measured default-off on control loss and independently verified VD and VB discharge/stop paths; later stages have their own prerequisites. Each stage requires prior evidence, article/firmware/BOM identity, instrument calibration/uncertainty, raw waveform hashes, stop criteria and correction/retest chain. Do not record any physical stage as run.

## Coordination, review and verification

Implementation workers have separate isolated worktrees and disjoint owned paths. They are not alone in the repository; none may revert another's work or edit the active Rev38 checkout. Each worker returns changed files, exact source identities, command/output evidence, negative controls and blockers, and does not merge or claim cross-unit acceptance. The coordinator reviews and integrates each branch in dependency order, resolves any source-hash drift caused by an earlier integration, independently replays focused tests and commits the integrated artifacts. Shared CAD and common Rust crate files remain coordinator-owned unless explicitly reassigned sequentially.

Review the plan before implementation for unsafe promotion of model results, false completed statuses, missing failure paths and incompatible cross-unit assumptions. After implementation, review executable verdicts with adversarial mutations. A data or hardware dependency is recorded as a precise gate, not guessed to keep an agent busy. Existing full-board DRC or historical Temper boards are not a Zapote release oracle.

## Definition of this round

Each of R1–R7 has a reproducible artifact and an honest verdict or a verified source/interface blocker. The release readiness inventory and physical protocol explicitly show that milestones 7–9 are not completed. Progress beyond this round is allowed only when the missing measurements, accepted unit sources, integration revision and assembled hardware actually exist.
