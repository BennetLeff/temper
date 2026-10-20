# Manufacturing instructions — revision A prototype

**Do not approve assembly using an unchecked CPL preview.** Native CAD passes, but the physical prototype and vendor component zero-angle conventions require final review. No files have been uploaded and no purchase has been made.

## Fabrication

- Finished outline:80.00 ×65.00 mm, rectangular, four Ø3.2 mm unplated mounting holes.
- Four copper layers, order **F.Cu / In1.Cu GND / In2.Cu power / B.Cu**. Standard JLCPCB FR-4 stackup,1.6 mm finished thickness,1 oz outer copper and standard inner copper. No controlled-impedance requirement, blind/buried vias or via-in-pad process.
- Green solder mask, white top silkscreen, ENIG preferred for fine-pitch assembly. Lead-free HASL is a lower-cost option only after assembler acceptance for the 0.5 mm USB pads.
- Through vias are0.60/0.30 mm generally and0.45/0.20 mm in USB routing. Minimum routed trace width0.20 mm, design clearance0.15 mm. Copper-to-hole0.20 mm follows published JLC capability; hole-to-hole0.25 mm, copper-to-edge0.30 mm. No DRC exclusions or ignored violations were added.
- USB shell holes are plated routed slots. Use the separate PTH/NPTH Excellon files; preserve G85/routed-slot geometry as exported. Do not convert slots to round holes. Four mounting holes and two USB locating holes are NPTH.
- Drill/place origin is lower-left outline corner: board coordinate(50,115), exported(0,0). Positive placementY points upward. Gerber and drill exports use the same origin.
- Supply the Gerber zip. Do not substitute the preview PNG/SVG/PDF for fabrication data. Empty bottom silkscreen is intentional; all components are on top.
- Request ordinary vendor process rails/tooling/fiducials if required for assembly. These are removable manufacturing aids and do not create a second functional instrument PCB. The board's narrow USB-edge placement needs supported handling. The assembler must return depanelized80×65 mm boards and preserve connector edge clearance.

The standard stackup is intentionally not treated as a precise RF transmission-line design. In1 ground is continuous beneath both signal layers; In2 has separate3V3D/3V3A pours. Confirm the offered fabrication stackup before order release. [JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities/) checked 2026-10-20 lists0.20 mm NPTH-to-track clearance.

## Assembly

`bom-jlcpcb.csv` and `cpl-jlcpcb.csv` cover45 top-side placements. Do not fit J2,J3,JP1–JP4 in automated assembly; fit the six TSW-102-07-G-S headers by hand after inspection. They remain in`bom-complete.csv`. The mixed-technology USB connector J1 is included in SMT placement; solder its shield anchors as required by the assembler. Do not substitute a visually similar USB footprint or an AD8606 from another manufacturer.

Fit one removable2.54 mm jumper cap on JP1 only at bring-up. No range jumper is fitted by the PCB BOM. J3 is a power test connector and must never receive a shunt. R/C reference labels are on the assembly/F.Fab drawing to avoid cramped silkscreen. IC pin1 marks and range labels remain on the top silk.

`orientation-audit.csv` records native angles, verified LCSC EasyEDA offsets, final CPL angles and pad1 positions. U1/U2/U3/U4/U5/D1 use a +270° correction; Y1 uses0° and J1 retains its native180°. These corrections came from the numbered pads of each exact LCSC-owned library entry, not a generic package-family guess. See `validation/placement-audit.md`. Native KiCad rotation is counterclockwise as an assembly angle, while pcbnew transforms child coordinates using its native convention. Do not apply a family-wide90° correction without checking the actual LCSC component drawing. Check each keyed IC, oscillator and USB connector against the vendor placement preview and the included assembly drawing. Passive R/C polarity is immaterial. An incorrect top/bottom or180° setting can destroy the board even if the BOM matches.

## Release checks and remaining qualification

Native ERC, DRC, schematic parity, source/netlist/PCB pin mapping, placement coordinates and BOM membership are checked. Gerber copper/plane/mask renders were visually inspected. The manufacturing outputs are usable prototype fabrication files; they are not a production release. Outstanding physical checks: actual vendor placement preview, assembler DFM, USB enumeration/suspend behavior, analog waveform stability, calibrated accuracy and fixture behavior. Follow`docs/bring-up.md`.
