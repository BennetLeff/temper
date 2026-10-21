# Manufacturing instructions — revision E engineering prototype

Revision E is the **TI TIDA-060029 based, 140 × 105 mm board** with the TAC5112 codec front end, relay ranges and four-terminal BNC jacks ([rev-e-plan.md](../docs/rev-e-plan.md)). Revisions A–D are superseded and must not be mixed with this package. No manufacturer upload, placement-preview approval or order has been performed.

## Fabrication

- Four layers: **F.Cu / In1.Cu GND / In2.Cu signals and power / B.Cu**. FR-4, 1.6 mm finished thickness, 1 oz outer copper and standard inner copper. ENIG is recommended for the 0.4 mm-pitch RP2040 and exposed-pad packages. Confirm the offered stackup before release.
- Finished outline 140.00 × 105.00 mm (board coordinates x 50–190, y 45–150). Four 3.2 mm NPTH mounting holes. All components are on top. Empty bottom silk is intentional.
- Design clearance 0.15 mm; narrow local tracks 0.15 mm. **Every via has a 0.30 mm drill** (272 vias: 167 × 0.60 mm, 35 × 0.55 mm and 70 × 0.45 mm pads), JLC's standard "0.3mm/(0.4/0.45mm)" via option; the board rules enforce a 0.30 mm minimum hole and 0.075 mm minimum via annular ring. Do not select the 0.2 or 0.25 mm minimum-via option: it adds cost and is not needed. Native DRC is authoritative for final geometry.
- **Order resin-filled, copper-capped, planarized via-in-pad (POFV).** 34 vias sit in SMT lands: the exposed pads U1.57 (8), U11.9 (6), U12.9 (6), U13.25 (9) and U14.25 (4, the TAC5112), and R3.2. Plain tenting or solder-mask plugging is not an equivalent flat solderable surface under an exposed pad. The 2026-10-20 JLC instant quote prices POFV at $18.28 plus $3.48 via plating for five boards ([cost estimate](../docs/cost-estimate.md)). `validation/via-in-pad-process.json` audits every through-via drill against every native SMT pad and records the exact board hash. Obtain vendor DFM acceptance before assembly.
- Keep the deliberate plane voids around the op-amp signal pins and feedback networks. Ground remains a plane elsewhere. Do not merge or redraw these voids during CAM preparation.
- Use the separate plated and nonplated Excellon drill files. USB shell and DC-jack slots must remain routed slots, not substituted round holes. Review the slot maps against the supplied connector drawings.
- Drill/place origin is lower-left outline corner, board coordinate (50,150), exported (0,0). Positive exported placement Y points upward. Gerber, drill and CPL use the same origin.
- The Gerber zip is the fabrication input. Preview PNG/SVG/PDF files are for inspection only. Request removable vendor process rails/tooling/fiducials if required, returning depanelized 140 × 105 mm boards. The BNC barrels overhang the top edge: no rail on that edge after depanelization. This does not add another functional circuit board.

## Assembly

The JLC BOM and CPL cover **191 top-side SMT placements**, including the four TQ2SA relays and the TAC5112. The complete BOM contains **199 fitted components**. JLC hand fits J2–J9: one DC jack, three TSW-102-07-G-S 2-pin headers (J4–J6) and four SAMZO BNC-KYWE-295-W4-N right-angle BNCs (J3, J7, J8, J9; C41416668). Each BNC's barrel faces the top edge; its square pad pattern does not key it, so follow the silk opening mark. DUT leads/fixture, regulated 5 V supply and USB cable are external accessories, not fitted PCB components.

J1 is a mixed-technology USB connector included in SMT assembly; its shield anchors must be soldered. J2 uses the exact DC-005 2.0 mechanical drawing and custom numbered pads: pad4 tip/input, pad3 sleeve/ground, pad2 switched contact left unconnected. Do not substitute a similarly named jack without checking its drawing.

Ranges are latching relays K1 (100 Ω), K2 (5 kΩ) and K3 (100 kΩ) under firmware control; the firmware selects 100 kΩ at boot because a latching relay keeps its last state through power-off. K4 switches the on-board 1 kΩ reference across the jacks for `REFCAPTURE`; every RESET opens it. The DUT connects to the four BNCs, left to right on the top edge J3 HCUR, J7 HPOT, J8 LPOT, J9 LCUR (silk labels); J4/J5 are debug and J6 UART.

`orientation-audit.csv` records native rotation, exact-library correction, final CPL angle and pad1 location. Corrections come from numbered pads of each exact LCSC-owned EasyEDA entry. See `validation/placement-library-audit.md` and `sources/placement-rev-c.json`; the Rev E parts' offsets come from `cad/tools/placement_offsets.py`. Check every keyed device against the final JLC placement preview and `previews/assembly-top.png`; native KiCad angle alone is not a vendor zero-angle guarantee. R/C values and references are on the assembly drawing, while critical labels remain on silk.

## Prototype release

Native ERC/DRC, schematic/PCB pin parity, BOM membership and placement coordinates must pass on the final source files before packaging. Review the actual exported copper, plane, solder-mask and drill plots. Before assembly approval, complete vendor DFM and the component-orientation preview, including exposed-pad via treatment. Physical stability, source-off noise, codec acquisition and calibrated accuracy remain prototype tests. `docs/bring-up.md` is the Rev D procedure (jumpers, ADS9224R); a Rev E bring-up procedure (relay ranges, codec self-test, protocol 3) is not written yet.
