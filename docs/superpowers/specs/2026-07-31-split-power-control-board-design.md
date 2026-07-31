# Split Power/Control Board Isolation Design

**Status:** approved design

**Date:** 2026-07-31

**Scope:** replace the current interleaved single-board mains/SELV floorplan
with a power board plus SELV control board, while retaining PD2 as the
conditional production target.

## Decision

The design will use two physically separate boards:

- The **power board** contains AC input, rectification, the DC bus, the IGBT
  bridge, resonant-tank power path, HV-referenced sensing, and the power-board
  side of every reinforced isolator.
- The **control board** contains the MCU, user interface, temperature and
  low-voltage safety sensing, and SELV logic.
- The board-to-board interface carries SELV power and SELV logic only. No AC,
  DC-bus, switch-node, floating gate-drive, or other HV-referenced conductor
  may enter the connector or control board.

This converts the current two-dimensional interleaving problem into a
controlled interface problem. The existing single-board layout is not patched
with an arbitrary keepout.

## Safety and domain contract

The selected production target remains PD2 with an 8.0 mm reinforced
creepage requirement, conditional on the covered, gasketed PCB compartment
specified in the environmental and assembly documents. If that compartment is
not implemented and verified, the design falls back to PD3 and 12.6 mm.

The domain manifest remains the source of intended topology, but it will be
extended to identify board ownership for every declared net and component:

The first implementation increment is now machine-checked in
`elec/domain_manifest.yaml` as `POWER_CONTROL_SELV_INTERFACE`. It enumerates
the ten permitted interface nets and permits only the `SELV` domain. The
netlist domain gate rejects a missing compiled net as a stale contract and
rejects any interface net classified as HV or left unclassified. This is an
interface guard while the two PCB artifacts are being built; it does not
pretend that the legacy one-board PCB has already been physically split.

| Ownership | Allowed contents |
|---|---|
| Power board HV | AC, rectified bus, PWR_RTN, switch node, resonant tank, HV-side gate-drive and sensing nets |
| Power board SELV-side boundary | Outputs of certified isolators before they enter the inter-board interface |
| Control board SELV | MCU, UI, sensors, isolated auxiliary output, control and telemetry nets |
| Board-to-board connector | SELV power, SELV ground, and explicitly enumerated SELV signals only |

The connector is not an isolation component. It is a SELV interface inside the
protected appliance. Galvanic crossing from HV to SELV must occur in a named,
certified isolator whose primary and secondary pins are assigned to the correct
board-side domains.

## Interface design

The implementation will define the interface by signal class before selecting
the final connector:

1. **SELV supply:** isolated auxiliary output and its return, with current,
   fault, and connector derating documented.
2. **Control inputs to the power board:** low-voltage commands that terminate
   in certified isolator inputs on the power board; no command trace may reach
   an HV node without crossing that isolator.
3. **Telemetry to the control board:** signals generated on the SELV side of
   certified power-board isolators or sensors whose entire circuit is SELV.
4. **Protective and service signals:** only signals whose touch voltage,
   return-current path, and fault behavior are explicitly classified SELV.

The connector selection must satisfy, at minimum:

- keyed and mechanically retained mating;
- no exposed or user-accessible HV contact;
- creepage and clearance suitable for the protected-compartment environment;
- contact spacing and pin assignment that keep supply, signal, and return
  groups reviewable;
- a single-fault analysis for reversed, partially seated, and adjacent-pin
  faults; and
- a documented replacement part or controlled end-of-life strategy.

The exact part number is an implementation output constrained by this contract,
not a reason to weaken the domain boundary.

## Mechanical architecture

The power and control boards will occupy separate retained regions of the
appliance. The control-board region will be the gasketed PCB compartment that
earns PD2. It must be outside the coil/heatsink forced-air path and must block
grease, steam, and cooking aerosols through covers, seams, service openings,
and cable penetrations.

The board-to-board harness or connector must have positive strain relief and
must not provide an accidental pollution path between compartments. Assembly
documentation will identify the cover, gasket interface, connector retention,
partition, cable routing, and inspection points.

## Source and data model changes

The implementation is staged so each source remains auditable:

1. Add explicit board ownership and interface declarations to the electrical
   source and domain manifest.
2. Split or duplicate only the necessary schematic hierarchy; do not silently
   move a net between domains to make the manifest pass.
3. Select and document replacement footprints for any isolator or connector
   whose current geometry cannot meet its assigned board-side creepage path.
4. Generate the netlist and schematic artifacts from the source of truth.
5. Create separate power/control PCB artifacts or an explicitly documented
   multi-board representation, with the inter-board interface represented as a
   named, reviewable boundary.
6. Add the physical keepout and routing constraints only after the floorplans
   and component ownership are accepted.

The current mixed-domain set (`C6`, `K1`, `K2`, `K3`, `PS1`, `T1`, `U3`, and
`U7`) is re-evaluated during implementation. A component may remain on the
power board only when its certified isolation geometry and assigned pins are
consistent with the interface contract. A part is not accepted because its
symbol has an isolation annotation.

## Verification contract

The implementation is complete only when all of the following pass:

- every control-board and connector net is classified SELV;
- no HV net is present on the control board or board-to-board connector;
- every HV-to-SELV transition is named and covered by the isolator manifest;
- the connector pinout and cable fault cases have an electrical review record;
- component-level creepage and clearance audits pass using pad geometry;
- each board's KiCad DRC passes without unexplained new errors;
- the physical isolation gate passes for every board boundary and reports no
  unauthorized crossing or intrusion;
- generated netlists, schematics, and manifests are synchronized;
- evidence provenance points to reachable measurement commits;
- every board-changing PR remeasures `drc_ceiling.json` with the required
  sample count and records attributed deltas; and
- the PD2 compartment is verified mechanically before the 8.0 mm target is
  cited as the production figure.

The existing 123 REQ-SAFE-01 findings are not accepted as a baseline. They
must either disappear through the new topology and placement or be individually
resolved with a documented, standards-backed construction decision.

## Delivery sequence

The work will be delivered as small, reviewable changes:

1. **Design/specification:** this document and the board/domain ownership
   contract.
2. **Electrical source:** board partition, interface signals, isolator and
   connector declarations, followed by generated netlist/schematic refresh.
3. **Power-board floorplan:** HV placement, boundary components, physical
   barrier, routing, and DRC/provenance update.
4. **Control-board floorplan:** SELV placement, connector routing, mechanical
   compartment details, and DRC/provenance update.
5. **Integration evidence:** cross-board interface audit, fault review, final
   requirements results, and merge only after required checks are green.

No stage may claim fabrication readiness while a subsequent stage still has an
open physical-boundary gate.

## Non-goals

- Lowering the selected PD2 requirement to fit the current board.
- Exempting the current interleaved placement from the isolation gate.
- Treating a connector, gasket, or software interlock as a substitute for
  reinforced isolation.
- Ratcheting DRC, regression, or requirements ceilings over unexplained
  failures.
