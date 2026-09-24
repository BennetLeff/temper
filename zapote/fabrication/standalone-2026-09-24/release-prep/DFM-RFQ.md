# Five-board prototype fabrication and assembly RFQ

**Status 2026-09-24:** proposed vendor and review packet; no vendor DFM acceptance, quote, order, or assembly instruction approval has been received. Preserve the frozen source/Gerber identities in `../manifest.json`.

## Proposed route

PCBWay is the proposed single fab/assembler for a five-piece prototype lot of each separate board, with customer-consigned or hybrid-sourced exact parts where its purchasing service cannot allocate them. Its [PCB capability table](https://www.pcbway.com/capabilities.html) lists the required layer counts, 1.6 mm thickness, copper weights and 0.3 mm drill size; its [assembly capability page](https://www.pcbway.com/assembly-capabilities.html) lists five-piece minimum, mixed SMT and through-hole assembly. Its [assembly file list](https://www.pcbway.com/helpcenter/pcb_assembly_ordering/What_files_are_requested_for_assembly_production_.html) calls for Gerber, BOM and centroid files. These published ranges are screening evidence, not DFM acceptance of these Gerbers or footprints.

| Separate board | Lot | Size mm | Layers and declared Cu target | Nominal thickness | Plated drill tools mm | Requested process |
| --- | ---: | ---: | --- | ---: | --- | --- |
| RTD | 5 | 60.1×60.1 | 4 × 35 µm | 1.6 mm | 0.30, 0.71, 0.95 | FR-4, ENIG, two-side mask, top legend; confirm inner dielectric 0.20/1.04/0.20 mm or analyze electrical impact of vendor stackup |
| Current sense | 5 | 80.05×83.05 | 2 × 70 µm | 1.6 mm | 0.30, 0.95, 3.00 | FR-4, ENIG, two-side mask, top legend; **no primary J1 termination at assembler** |
| Thermal sense | 5 | 100.1×45.1 | 2 × 70 µm | 1.6 mm | 0.30, 0.95, 1.00 | same base process |
| Interlock | 5 | 100.1×65.1 | 2 × 70 µm | 1.6 mm | 0.30, 0.95 | **DFM hold: 0.15 mm copper spacing** |
| Gate drive | 5 | 100.1×80.1 | 2 × 70 µm | 1.6 mm | 0.30, 0.95, 1.00, 1.10 | same base process; approve U1 physical envelope |

All sizes/drill tools and saved stackups come from the frozen package's Gerbers, drill reports and stackup reports. The copper figures are KiCad's declared layer thicknesses; the fab must state its finished-copper construction. ENIG and FR-4 are **RFQ choices**, not existing accepted constraints; vendor confirmation and any effect on contact, soldering, impedance and insulation is required. No panel outline, rails, fiducial design or assembly datum has been accepted. Do not edit the submitted artwork or silently change finished copper weight, drill plating, solder mask, pad size, package, or parts. Return proposed manufacturing changes as marked DFM comments for design review.

## Interlock exception, measured

PCBWay's [70 µm outer-copper table](https://www.pcbway.com/capabilities.html) places 7–8 mil spacing in its normal/medium bands; its stated lower limit is 6 mil (0.1524 mm). The interlock source rule is 0.15 mm (5.906 mil). On a temporary *copy* of its project, raising only the project/net-class minimum clearance to 0.20 mm and rerunning KiCad 10.0.4 DRC produced **six clearance errors, zero opens** (retained in `interlock-drc-at-0p20mm.json`): five 0.150 mm gaps among U4 pads, and one 0.190 mm gap from B.Cu vcc track to via. The original accepted Gerbers were not modified. This rules out treating the saved 2 oz interlock artwork as normal-process acceptable. Ask PCBWay whether its advanced process explicitly accepts the **actual 0.150 mm finished gap** at U4 with 70 µm finished copper, and what inspection/yield conditions apply. If it cannot, revise copper weight/footprint/layout and repeat the source acceptance plus exports before RFQ release. No silent 1 oz substitution is allowed.

Reproduction: copy `zapote/interlock/candidate/` outside the source tree; change `section.kicad_pro` `board.design_settings.rules.min_clearance` and each `net_settings.classes[].clearance` to at least `0.20`; run `kicad-cli pcb drc --all-track-errors --severity-all --format json --output drc-0p2.json section.kicad_pcb` in the copied project. The saved result is an engineering probe, **not** a vendor's DFM verdict.

## Questions requiring written fab/assembler disposition

1. Confirm exact finished copper weight and laminate build for each board, including RTD dielectric distances, minimum feature/space and finished hole/plating tolerance. State any required design edit before tooling. Return stackup drawing.
2. Inspect the interlock's six measured sub-0.20 mm gaps at 70 µm copper; explicitly accept or reject 0.150 mm U4 pad spacing. Do not round 0.150 mm to nominal 6 mil without tolerance assessment.
3. Confirm Gerber/drill registration, solder-mask webs at fine-pitch U4 and RTD U6, minimum annular rings, board-edge constraints, and panelization/rails/fiducials. Return marked artwork for any compensation.
4. Confirm mixed SMT/THT build sequence, exact component orientation and pin-1 view for all connectors and custom packages, and the vendor-specific centroid origin/rotation mapping. The supplied `positions.csv` is a native KiCad export, not approved machine programming.
5. Confirm exact manufacturer/MPN allocation from `assembly-bom.csv`; report any shortages without substitution. Current J1 is copper lands, not an installable BOM part. Exclude harnesses, PT100 probe, NTC assemblies, current primary termination and gate load from PCB assembly quote unless separately specified.
6. Provide first-article inspection records for stackup/copper/hole sizes, assembled polarity, continuity and optical solder review. Powered test is outside this RFQ.

The five board folders in `../` are the Gerber/drill/BOM/position/artwork attachments. `assembly-bom.csv` is the reconciled procurement input; `sourcing-snapshot.json` records catalog leads and unresolved allocations. `HARNESS-MECHANICAL.md` defines test-fixture wiring and physical hold points.

**Release gate:** Written DFM acceptance for the frozen artwork, allocated exact-part BOM, accepted centroid/panel drawing and an approved inspection plan are required before placing a fabrication/assembly order. Separate electrical qualification is still required before cooker use.
