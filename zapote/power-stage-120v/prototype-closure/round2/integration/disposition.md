# Round 2 integration disposition — 2026-10-04

**Decision: preserve native19 as the reviewed engineering baseline; do not
create or order a native20 board from these studies.** Neither electrical
handoff selects a main-board component or circuit change. The current
Atopile change corrects an unsupported timing comment only; a fresh compile
produced byte-identical native19 netlist and CSV, identical resolved component
objects, and a passing 142-component/89-net source audit. The historical
native19 board, schematic, exports and verification receipts are unchanged.
See [source-comment verification](source-comment-verification.json). This is
an integration decision, not a fabrication or powered-use release.

## Evidence accepted for this decision

| Workstream | Revision-matched finding | What it closes | What it does not close |
| --- | --- | --- | --- |
| D17 | [Native19 extraction and finite-energy study](../d17/README.md), board SHA-256 `3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`: 2,102 copper primitives, 308 barrels, corrected actual R5 endpoints, two meshed legs with 3,542,432/4,207,066 tetrahedra and passing topology/port checks. | Replaces copied native18 geometry and tests the direction of stored-energy risk. The source comment correction removes a false 0.35 µs worst-case assertion. | Both field matrices are `NOT_SOLVED`; no installed current-extinction limit, Kelvin impedance or fault survival. Its 428.342 V bus, 136.149 A current and 1320.767 V capacitor maxima are **separate diagnostic cases** with unmeasured initial states, not a combined product corner. |
| D22 | [Two-way nonlinear DM inlet diagnostic](../d22/README.md), 30 new ngspice 45.2 transients, six refinements. A regularized constant-power diagnostic at 100/120/140 V RMS draws 23.01/17.66/16.13 A and dissipates 54.64/22.32/17.14 W in the selected 5 W damper; conductance-shaped cases draw 14.50/12.21/10.54 A and dissipate 0.119/0.173/0.236 W. A 140 V crest connection reaches 367.62 V on the bus with gates disabled, or 391.53 V with damper open. | Demonstrates that the control law and passive charging strongly affect inlet current, damper heat and bus stress. Establishes a precharge/inrush design requirement and the need for raw bus and input-current access. | The load laws are diagnostics, not deployed firmware; the 10 Ω/20 ms precharge experiment selects no part or timing. No MOV/diode/switch dynamics, common-mode or switched RF recomputation, supplier hot limits, fault coordination or physical tests. D22 holds filter and PCB powered release. |
| Native19 CAD and source | Existing [native19 verification](../../../native-19/verification/) and [measurement inventory](measurement-access.md). | Stable 142-part/89-net PCB and schematic comparison article, with documented DRC/ERC/parity state and candidate electrical contacts. | Existing 3D bodies are provisional; pad-derived contacts are not verified fixture access. Native18 cooling, old imported R4 PCB and nominal edge contact are not installed native19 qualification. |
| Cooling | [Round2 native19/R4 cold CAD](../cooling/README.md) imports all 142 native19 references and produces a valid 564-solid STEP (SHA-256 `8bf5c193596f1ec688b0c81312a5fc03388ab802d5027f8254f59b51e7028198`). Its [verification record](../../../../../output/temper-prototype-closure/round2/cooling/verification.json) pins the source and interface and accepts 16 modeled thread engagements with zero unexpected nominal intersections. | Provides a concrete contact-bearing sink, separate measured shims, carrier datums, ducts, inlet and PE allocations for an engineering fit study. The PE braid no longer intersects the filter, fan or cradle in the final nominal check. | The old PCB tray/lid were removed from the collision set without a replacement protective chamber. Fuse service-door projection intersects the coil support/coil/ferrite envelope, so top removal is required for that service concept. Contact force, delivered flow, thermal rise, insulation, cable routing and tolerance fit remain unqualified. |

## Decisions that determine the next actual revision

1. **Inlet and startup topology.** Select whether the filter, fuse, switch,
   precharge/bypass and interruption path reside in a protected inlet module,
   harness or main PCB; identify exact parts and terminal pinout before a PCB
   footprint is assigned. Check the control law and pan/line operating
   envelope against the 15 A RMS input allocation, including low-line and
   no-load connection. Qualify inrush, reclose, welded/bypassed contact,
   resistor overtemperature, fuse/wire coordination, MOV energy and bus
   ratings. D22's experimental 10 Ω and 20 ms cannot be copied into a BOM.
2. **Fault path.** Pin controller/interlock source revision, fault polarity,
   rail-loss behavior, connector load, latch reset and the command-to-current-
   extinction budget. Determine whether the conditional 74AHC30PW,118
   interlock ECO is controller-side or needs a power-board interface change.
   Retain R5's four-terminal split and capture actual differential reference
   displacement; ±1 mV is a proposed allocation for ±1 A trip accuracy,
   not a measured or adopted requirement. A shorted bridge device requires
   an independent energy-interruption disposition.
3. **Solved and measured physics.** Solve and converge both native19 legs,
   including relevant bulk and Kelvin-current paths, or repeat extraction on
   the changed board. Couple line, bridge, DC bus, actual controller and tank
   initial states. Use the installed coil/pan, sink and PE geometry for thermal
   and common-mode/RF checks. Measure raw bus, input current, gate pins,
   Kelvin current, tank state and protection timing on an instrumented guarded
   first article before claiming numerical safety margins.
4. **Installed mechanical interface.** Use the native19 populated STEP in a
   single frame with the R4 exterior, sink, fan, inlet module, insulation,
   conductor routes, PE path, board restraint and a protective PCB chamber.
   The current round2 cooling interface omits the old R4 covered tray and lid
   from its collision import. A replacement barrier and service cover must be
   modeled before a zero-collision result can claim installed fit. Retain the
   now-clear PE braid path and qualify its dedicated bond. Clamp
   force, ceramic/shim interface, device seating, thermal growth, fan flow,
   supplier tolerances and retention force remain physical qualification.

## Controlled promotion to native20

Create `native-20/` only after a selected, reviewable electrical or mechanical
ECO changes the native19 board. Record the approved circuit/interface decision
and primary component/drawing identities first. Recompile the Atopile source,
audit the component/net/footprint/MPN projection, then route a new board
without modifying native19. Re-run typed ERC, three saved-board all-track
DRC/zone-refill checks, opens, parity, 3D/body and test-access review on the
new hashes. Update cooling CAD and both-leg extraction to the new board.
Revisit insulation rules using the actual startup/surge voltage basis and
applicable product classification. A clean DRC, nominal collision screen or
digital simulation alone does not authorize fabrication or energization.

The [round1 integration packet](../../../../../docs/research/mit-product-design/resolution/integration/README.md)
still supplies supplier drawing, first-article inspection, market/earthing and
full-size cleaning-trial templates. Their revision-specific 135-part/native18
and historical R4 assumptions must be rebaselined before use.
