# Rust ERC/DRC integration audit — 2026-10-02

The problem is mixed: some code is connected and executed, some is connected but
lacks required inputs, some is standalone, and some currently has tests only.
A registered function or passing test suite is not evidence that it checked this
120 V PCB. This audit separates those states.

Scope: current Zapote public ERC/DRC modules, their harness/CLI callers, the
five maintained unit candidates, the 120 V source audit/parity workflow, and
Temper's default Rust rule registry. This is not a claim to have executed every
Rust helper in Temper or requalified all historical solver studies.

## Execution paths

| Surface | Actual connection | Result / limit |
|---|---|---|
| Temper `temper-drc-rs` registry | 27 registrations in `rules::create_default_registry`; pyo3 `run_drc`; production callers in `temper_placer.validation.drc_runner`, `drc_oracle`, and the ratchet | Real integration in Temper. Not automatically run on Zapote/120 V; not rerun in this audit. `PowerDomainCheck` is an explicitly unregistered stub. |
| Zapote source circuits and unit ERC/DRC | `zapote-unit-run` → `runner::evaluate/run`; RTD, current-sense, thermal-sense, interlock, gate-drive | Fresh common run completed on all five; all indeterminate, none failed. Physical and software/input gaps remain explicit. |
| Saved board binding and stackup | `native_binding::validate`, `stackup::validate_board` in common runner; `zapote-board` standalone | Executed in common run. `check-boards` and `board-check` still mean stackup only. |
| Manufacturing P2 | Native `validation/p2/extract.py` → Rust `manufacturing::validate_with_population` | Live geometry and evaluated populations in all five reports. Prototype limits do not constitute vendor/process qualification. |
| Domain clearance | `gate_drive` harness → `domain_clearance::validate` | Wired for gate-drive; separate from the 120 V plan-view barrier. |
| Domain pin contract / power integrity P1 | `runner` gate-drive branch → `p1::run` → `domain_contract`, `power_integrity` | Runs, but 103 gate-drive power findings remain indeterminate: branch RMS current, via capacity, physical pad entries/current sharing, and barrier evidence gaps. |
| Switching P3 | `runner` gate-drive branch → `p3::run` → `switching::validate` | Runs. Current loop bounding boxes are explicitly not loop area/inductance; authored area/noise limits are missing. |
| Operating limits | `p3::run` calls `operating_limits::validate(None, None)` | Integrated call, missing thermal and shutdown timing inputs. Not acceptance. Applies to gate-drive/current-sense/interlock in current runner. |
| Power-stage electrical models | Gate-drive ERC calls power-stage model functions, including dead-time calculation | Model-based calculations; not a native 120 V waveform/current extraction pipeline. |
| Branch-current graph | `power_branches::analyze` | Only test callers found in current Zapote tree (`branch_cut_oracle` plus module tests); no board runner consumer. |
| Pad/contact geometry and capacity | `power_contact::entry/capacity_a` | Only test callers found; the P1 report still says actual entry/current/neck validation is unimplemented. |
| Pad escape | `zapote-pad-escape` CLI → `pad_escape::plan` | Standalone caller accepting supplied JSON; not a common saved-board acceptance rule. |
| Fault loop | `zapote-fault-loop` CLI → `fault_loop::loop_inconsistencies` | Standalone source-netlist/assignment check; necessary connectivity only, not actual branch-current proof. |
| 120 V source audit | `power-stage-120v/audit.rs` consumes frozen netlist/BOM/resolved identity | Fresh PASS: 135 components, 83 nets; 53 mutation/regression tests passed. Frozen source inputs, not fresh Atopile compilation. |
| 120 V native parity | `tools/check_native_parity.py` → `zapote-power-native-parity` | Fresh PASS against native-17 presentation PCB; 135 components, 368 source pins, 388 connected copper pads including 20 duplicate physical pads. |
| 120 V barrier | `tools/barrier_check.py` → `zapote-power-barrier` → `power_barrier` | Existing real native copper caller and retained native-17 receipts. Not rerun here; its coarse export is unsuitable for capacitance/current distribution. |
| New layout feedback | `check` → `check-layout` → live pcbnew snapshot → Rust `native_layout` | Fresh native-17 run and deliberate saved-board mutation proof. See NATIVE.md for exact metrics and omissions. |
| Original nine layout model kernels | `zapote-layout-quality BOARD < scenarios.json` → `layout_quality::report::run` | Still model-input based. Native feedback directly reuses track resistance and plate-capacitance calculations; it does not fabricate the inputs needed by the other electrical/thermal/3D kernels. |

The legacy registry includes clearance, body/courtyard overlap, containment,
trace/via spacing, connectivity/floating pins, isolation/creepage, loop/noise/
ground-plane screens, thermal constraints/vias, solder keepout, parallel runs,
stitching, copper pullback, barrier/slots, thermal relief, teardrops, partial
discharge, pad entry and split-plane checks. Those names describe separate rules,
not equivalent physics fidelity. The [historical inventory](../validation/inventory-2026-09-12.json)
records their individual scopes and limitations. This audit confirmed the 27
registrations and production call sites; it does not promote them into Zapote.

## Fresh common run

Command: `make -C zapote check-units`, using KiCad 10.0.4 CLI and its Python
runtime, with `RUN_DIR=/private/tmp/zapote-unit-integration-audit-01`.
The runner attempted all five units and returned 2 (indeterminate); make returned
nonzero. All five native ERC/DRC sections passed. Required thermal/timing inputs,
branch-current models, interfaces and hardware qualification remain missing.

| Unit | Native footprints / traces / vias | Overall |
|---|---:|---|
| RTD | 36 / 207 / 55 | Indeterminate |
| Current-sense | 21 / 88 / 28 | Indeterminate |
| Thermal-sense | 27 / 162 / 44 | Indeterminate |
| Interlock | 25 / 212 / 135 | Indeterminate |
| Gate-drive | 20 / 91 / 17 | Indeterminate |

[Structured summary](native-evidence/unit-audit-summary.json) includes each
section's distinct unresolved messages and manufacturing evaluation population.
[Full run archive](native-evidence/unit-run.tar.gz) retains inputs, hashes,
commands, native reports, errors and unit reports. Counts of findings or evaluated
pairs are not counts of independent engineering rules.

The **120 V board is not in `validation/units.json`**. This change adds its native
layout feedback to `make check`; it does not silently reuse the smaller gate-drive
unit's source contract or claim that all of P1/P2/P3 now qualify the full bridge.

## Remaining integration work

1. Build a 120 V acceptance spec with its own source/interface/operating contracts
   and register the applicable existing gates under that spec. Keep source parity,
   barrier and native ERC/DRC evidence together rather than assuming standalone
   receipts are executed by the five-unit runner.
2. Reconstruct and discretize native zone/pad/via conductors, including interior
   junctions. Connect `power_contact` and `power_branches` to actual board-derived
   graphs and source-defined load cases. A tree cannot determine parallel sharing.
3. Feed extracted mutual/shared inductances and adopted operating slews into gate,
   Kelvin and return models for both bridge legs; supply decoupling component
   parasitics/effective values and complete current loops.
4. Connect assembly loss/thermal-transfer models and actual 3D bodies/tolerances.
   Separately retain unknown physical cooling, hardware and qualification inputs.
5. Port remaining applicable Temper rules with their exact board requirements and
   independent oracles. Registering all 27 under defaults is not a sound port.

These gaps remain tracked in issue #1628. The new native command is useful
placement/routing feedback now; full-board engineering acceptance is unfinished.
