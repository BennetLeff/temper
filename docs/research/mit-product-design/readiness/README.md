# Temper: path to manufacturing release

Prepared 2026-10-04. This packet follows the MIT-informed design corrections in
`dea4649ff466cf36b49a0523d8232c94c317b163`. It separates the next build from a
production release. No assembled Temper hardware or physical test results have
been supplied; an unperformed test remains open.

## The next decision

The user selected **a few engineering prototypes to test** on 2026-10-04.
The immediate objective is a small, revision-matched engineering build: one
electrical source, one corresponding native PCB, and one populated mechanical
assembly with selected cooling, protection, interfaces and harnesses. A cold
mechanical mockup can proceed separately where it does not depend on the power
stage. A prototype fabrication decision and permission to energize that
prototype are separate decisions with separate evidence.

Build and instrument the first unit before completing its siblings, so an
early electrical or packaging correction need not be repeated across the
whole cohort. Assign distinct serials and test roles: an instrumented bring-up
unit, a closed-assembly thermal/control/service unit, and separately allocated
fault or destructive specimens as the test plan requires. Final quantities
follow the agreed test matrix and supplier quotes; no order is authorized here.

The existing R4 STEP is useful for review and cold fit work. It is not the
integrated assembly of the current power board. Native-18 is the current
routed electrical intake; the HOT5 source correction adds parts that are not
on that board. Reconcile these revisions before producing a manufacturing BOM
or sending a board/enclosure pair to suppliers as one design.

## Workstreams

| Work | Required result | Dependency |
| --- | --- | --- |
| Power envelope | A supported coil/capacitor/control operating range, exact component limits, and a characterization plan | Real coil/pan data and selected-part limits; simulations alone do not qualify the range |
| PCB and protection | Source-to-board parity, implemented fault chain, appropriate physical rules, inspection/probe access and reproducible outputs | Settled circuit changes, mounting/cooling interfaces and applicable insulation basis |
| Mechanical integration | Current board, cooling, controls, inlet, harness and support structure in a checked assembly; two-sided actuation and seal stacks | Selected parts, supplier drawings, electrical/thermal allocations |
| Manufacturing and validation | Build sequence, critical-characteristic inspections, traceable BOM/drawings, qualification and production-screen records | Revision freeze and supplier process review; physical results before release |

Four Astra agents produced the linked domain reports; a fifth independently
reviews the combined result. An individual domain's check does not override
another domain's requirements.

- [Power envelope and characterization](power/README.md): reconciles both
  current detectors and supplies blank coil/pan measurement records and
  exact-part supplier questions. The 45 A model is now explicitly a historical
  comparison; it overlaps the shunt path's conditional static trip band.
- [PCB integration plan](pcb/README.md): maps the seven HOT5 additions and
  U8's changed footprint/pin routing, records fresh identity/DRC/ERC checks,
  and identifies mounting, test-access and schematic-symbol work. The native
  board has not been changed.
- [Mechanical packaging and controls](mechanical/README.md): four checked
  space studies locate cooling conflicts while preserving the exterior. The
  collision-free rear-space study still lacks a thermal connection. The knob
  proposal needs a supplier-supported travel/force limit before CAD changes.
- [Manufacturing and test packet](manufacturing/README.md): assembly traveler,
  critical-characteristic inspections, supplier request inputs, instruments
  and per-build evidence records for the requested prototype cohort.

## Work before the first prototype order

1. **Characterize the coil and pans and obtain capacitor application limits.**
   Use low-energy fixtures now. Reconcile the desired power range with both
   current-protection paths; do not raise protection thresholds to recover an
   assumed model result.
2. **Choose a realizable board-to-sink assembly inside the R4 exterior.**
   Obtain a complete sink/fan/clamp drawing and performance basis; coordinate
   device contacts, board retention, fan supply, duct and harness before
   final routing or sheet-metal fabrication.
3. **Implement and review the matched electrical design.** Integrate HOT5,
   replace the U8 footprint and affected routes, restore meaningful pin types
   in the schematic, and resolve the documented Kelvin split using the
   intended net-tie construction. Repeat parity and physical checks on that
   exact board. Add deliberate mounting and probe access.
4. **Close the control and material selections.** Confirm switch safe stroke
   and force; build the local click-stack coupon. Select real button/display
   interfaces, glass, membrane, adhesive and seal processes, with supplier
   limits and inspectable datums. Cold mockups can proceed in parallel.
5. **Release a supplier-reviewed engineering package and test station.**
   Quote the first unit and additional units separately. Freeze matched
   source/PCB/BOM/CAD/firmware revisions, assembly instructions and inspection
   records. Bring up the first unit under the test engineer's staged limits
   before completing and exercising the remaining specimens.

These are the next work orders, with evidence requirements in the linked
reports. The current packet does not close them by documenting them. New STEP
files in `output/temper-manufacture-readiness/mechanical/` are space studies,
not replacement manufacturing assemblies.

## Stage exits

1. **Cold mockup:** clearly identify nonfunctional parts and material substitutes.
   Check fit, control reach, assembly/tool access and service sequence. Do not
   infer thermal, insulation, seal or load qualification from a printed fit part.
2. **Engineering fabrication:** agree the operating envelope and design inputs;
   reconcile source, PCB, BOM and CAD; resolve physical interference and critical
   tolerance stacks; obtain supplier review of the actual fabrication package.
   Preserve explicit experimental objectives and unresolved qualification work.
3. **Controlled powered prototype:** the responsible electrical engineer approves
   the setup and staged test procedure, including independent interruption,
   protective bonding/insulation and measurement methods. Verify protection,
   startup and rail sequencing before expanding the operating envelope. Record
   actual revisions, waveforms, loads and test conditions.
4. **Learning pilot:** incorporate prototype findings into a frozen build package,
   assemble with the intended supplier/process, and demonstrate repeatable
   critical characteristics and defect detection. Choose pilot quantity from
   the variation and failure questions being tested; one working unit does not
   establish process capability.
5. **Production release:** close qualification and applicable market compliance,
   approve controlled substitutions and supplier processes, and establish
   per-unit production tests, traceability, rework and change-control rules.
   Physical changes affecting a tested function trigger an explicit retest decision.

## Ownership

The engineering friend can review the package and take an electrical,
mechanical or integration-owner role according to their expertise. The project
owner decides product tradeoffs, target volume and commercial scope. Suppliers
confirm their material/process capability and part-specific limits. The
responsible test engineer and qualified safety/compliance reviewer set and
accept the applicable physical tests. Agent calculations and checks support
those decisions; they do not stand in for measurements or sign-off.

No supplier has been contacted and no fabrication order has been placed by
this work. Draft requests are prepared for review and sending by the owner.
