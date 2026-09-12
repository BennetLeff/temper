# Standalone gate drive and power entry, with a harness demonstration

The user requested both boards through the existing Zapote harness and a visual
demonstration. Build two separate units from base bb0fcd6de. Do not integrate or
energize the cooker, order parts, or publish externally. Commit reviewed work
locally. The earlier 100 × 80 mm gate-drive and 180 × 140 mm power-entry figures
are planning allowances, not fixed limits or measured results.

## Gate-drive unit

Own `elec/src/gate_drive_unit.ato` and `zapote/gate-drive/`. Reconcile the active
UCC21550BDWK circuit and its verified package pin map, high/low gate networks,
dead-time setting, primary-side PERMIT shutdown, and properly separated output
returns. The rejected ISO7741 qualification candidate is evidence of gaps, not
permission to adopt it as an approved replacement. A local implementation may
correct donor defects using manufacturer evidence without changing production
files. Resolve the isolated supply boundary explicitly; no primary/secondary
ground connection, invented transformer winding, or unexplained 15 V rail.
Use existing local bootstrap/decoupling only when its recharge, UVLO and supply
reference assumptions are stated and validated. Exact added supply parts require
manufacturer pin, rating, package and working-voltage evidence.

Required evidence: exact source/native parts and physical pin nets; disjoint
control/high-side/low-side domains and declared creepage/clearance profile;
native saved-board stackup and geometry; gate-loop and bypass placement checks;
source-bound enable polarity, disabled/floating-input behavior, complementary
drive and dead-time bounds. Device/isolator capabilities must match the claimed
prototype construction; no assertion of production insulation qualification.
Power-ramp, bootstrap startup, actual timing and loaded switching remain explicit
unrun physical tests. Show gate, Kelvin return, supply and host connectors.

## Power-entry unit

Own `elec/src/power_entry_unit.ato` and `zapote/power-entry/`. Retain the
1,800 W nominal AC-input product target. The corrected energy-balanced doubler
model failed input RMS and capacitor-ripple limits. It is rejected evidence.
The selected replacement is a 120 VAC active CCM boost PFC with UCC28180D,
389.615 V setpoint, 180 uH Würth 760800301 and four 560uF/450V capacitors.
At 120 V, 15 A and PF 0.99, real input is 1,782 W; input foldback, HOT isolated
15 V bias, precharge/relay sequencing and integration supervision remain external.
No midpoint exists. AUX/CONTROL/PERMIT returns are HOT bus-minus referenced.

The current 53-part source-build-18 includes the reviewed return/shunt topology, exact
BAT54H cathode pin, compensated control-loop model and default-disabled permit.
Source/native/schematic parity is checked separately from physical copper.
The selected large inductor and heat-dissipation/service envelopes require a
230 × 190 mm prototype allowance; final cooker fit is not established.

At this bounded construction checkpoint, native ERC is clean, placement DRC has
zero geometry/parity findings, and 94 unconnected links remain. Rust correctly
rejects copper connectivity. Do not accept or export for fabrication. A subsequent
routing attempt must place the switching loop deliberately, size current paths,
apply a voltage/domain-specific clearance profile, and demonstrate native and Rust
connectivity before any acceptance. Thermal, EMI, insulation, loaded switching,
control-loop and line-foldback evidence remain unrun.

## Shared harness and demonstration

Root owns shared Rust registrations, tests and cross-unit documentation. New
engineering verdicts are Rust. Reuse native KiCad editing and explicit route
recipes; do not introduce or invoke a placer/router algorithm. Workers may
author unit-specific Rust files in their isolated worktree and propose public
registration edits separately. Every accepted model must reject coherent edits
to the actual source/native graph, rather than merely compare fixed text or
return constant success. Retain failed attempts and exact hashes.

Before construction, select notes from interlock-lessons-v1 using Rust memory
preparation and preserve the actual dispatch packet. Each initial worker attempt
has a 90-minute deadline and at most eight saved route candidates; hand back
the best candidate and real blockers at that boundary instead of retrying
indefinitely. The coordinator may start a separately bounded repair attempt
after diagnosing the failure. Only the assigned worker writes its board.

Finish each unit with source compilation, strict source/native/schematic parity,
Rust positive and mutation tests, native ERC and DRC (all severities, all track
errors, schematic parity), real saved-board stackup and rendered inspection.
Read ERC at sheets[].violations. Full physical qualification stays INDETERMINATE
where its required evidence is missing; the demonstration labels that clearly.

Provide a local, viewable demonstration comparing both actual boards, showing
their measured sizes, schematic/3D artifacts, connector roles, passing checks,
and examples of deliberately broken wiring rejected by the Rust validators.
If construction fails, show the actual failing board/report rather than a
fabrication-ready mockup. Freeze the exact accepted artifacts and update the
roadmap, interfaces and versioned memory with verified lessons.
