# Manufacturing instructions — revision C engineering prototype

Revision C is the **TI TIDA-060029 based, 140 × 100 mm board**. Revisions A and B are archived and must not be mixed with this package. No manufacturer upload, placement-preview approval or order has been performed.

## Fabrication

- Four layers: **F.Cu / In1.Cu GND / In2.Cu signals and power / B.Cu**. FR-4, 1.6 mm finished thickness, 1 oz outer copper and standard inner copper. ENIG is recommended for the 0.4 mm-pitch RP2040 and exposed-pad packages. Confirm the offered stackup before release.
- Finished outline 140.00 × 100.00 mm. Four 3.2 mm NPTH mounting holes. All components are on top. Empty bottom silk is intentional.
- Design clearance 0.15 mm; narrow local tracks 0.15 mm. General vias 0.60/0.30 mm, with local 0.55/0.25 mm and 0.45/0.20 mm vias. Native DRC is authoritative for final geometry.
- **Order resin-filled, copper-capped, planarized via-in-pad (POFV).** Fifteen intended SMT-land vias are present: U1.57, U8.17, U9.17, U10.13, U10.15, U10.33, U13.25, R3.2, C107.1, C109.1 and the grounded pads of C62, C63, C68, C69 and C75. The ADC capacitor vias provide short charge-return loops. Plain tenting or solder-mask plugging is not an equivalent flat solderable surface. The 2026-10-20 JLC instant quote prices POFV at $18.28 plus $3.48 via plating for five boards ([cost estimate](../docs/cost-estimate.md)). `validation/via-in-pad-process.json` audits every through-via drill against every native SMT pad and records the exact board hash. Obtain vendor DFM acceptance before assembly.
- Keep the deliberate plane voids around the high-speed amplifier signal pins and feedback networks. Ground remains a plane elsewhere. Do not merge or redraw these voids during CAM preparation.
- Use the separate plated and nonplated Excellon drill files. USB shell and DC-jack slots must remain routed slots, not substituted round holes. Review the slot maps against the supplied connector drawings.
- Drill/place origin is lower-left outline corner, board coordinate (50,150), exported (0,0). Positive exported placement Y points upward. Gerber, drill and CPL use the same origin.
- The Gerber zip is the fabrication input. Preview PNG/SVG/PDF files are for inspection only. Request removable vendor process rails/tooling/fiducials if required, returning depanelized 140 × 100 mm boards. This does not add another functional circuit board.

## Assembly

The JLC BOM and CPL cover **173 top-side SMT placements**. The complete BOM contains **184 fitted components**. Hand fit J2–J6 and JP1–JP6: one DC jack and ten 2-pin headers. Use fully seated Samtec SNT-100-BK-G shunts on the specified TSW-102-07-G-S headers. Two removable jumper shunts, DUT leads/fixture, regulated 5 V supply and USB cable are external accessories, not fitted PCB components.

J1 is a mixed-technology USB connector included in SMT assembly; its shield anchors must be soldered. J2 uses the exact DC-005 2.0 mechanical drawing and custom numbered pads: pad4 tip/input, pad3 sleeve/ground, pad2 switched contact left unconnected. Do not substitute a similarly named jack without checking its drawing.

At first bring-up fit **JP1 and JP4 only**, selecting the matched 100 Ω source/feedback range. Change ranges with power removed. Fit only one source jumper and its matching feedback jumper. J3 is the DUT connector; J4/J5 debug and J6 UART must never receive range shunts.

`orientation-audit.csv` records native rotation, exact-library correction, final CPL angle and pad1 location. Corrections come from numbered pads of each exact LCSC-owned EasyEDA entry. See `validation/placement-library-audit.md` and `sources/placement-rev-c.json`. Check every keyed device against the final JLC placement preview and `previews/assembly-top.png`; native KiCad angle alone is not a vendor zero-angle guarantee. R/C values and references are on the assembly drawing, while critical labels remain on silk.

## Prototype release

Native ERC/DRC, schematic/PCB pin parity, BOM membership and placement coordinates must pass on the final source files before packaging. Review the actual exported copper, plane, solder-mask and drill plots. Before assembly approval, complete vendor DFM and the component-orientation preview, including exposed-pad via treatment. Physical stability, source-off noise, ADC acquisition and calibrated accuracy remain prototype tests described in `docs/bring-up.md`.
