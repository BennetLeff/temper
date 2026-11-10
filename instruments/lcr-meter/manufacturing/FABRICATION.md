# Manufacturing instructions: Rev G100 engineering prototype

**Revision G100** is Rev G on Rev F's 100 × 100 mm outline:
- Rev G is Rev F with protected jacks: TVS, photoMOS switches, series resistors and a residual-voltage sense ([rev-g-plan.md](../docs/rev-g-plan.md)).
- G100 is that circuit re-laid by hand on 100 × 100 mm ([rev-g100-plan.md](../docs/rev-g100-plan.md)).
- The owner chose G100 over Rev G (100 × 110 mm) on 2026-11-10.
- Its only netlist changes against Rev G are J5 removed and the datasheet-audit additions D29, TP22 and C15.

Earlier revisions must not be mixed with this package:
- Rev F's package is on `study/lcr-in-box`;
- Rev E's is archived in `rev-e/`.

No manufacturer upload, placement-preview approval or order has been performed. The order steps are in [rev-g100-handoff.md](../docs/rev-g100-handoff.md).

## Fabrication

### Layers, material and stackup

- **Layers:** **F.Cu / In1.Cu GND plane / In2.Cu signals, power and GND pour / B.Cu signals and GND pour.** The In2 and B.Cu pours stay out of the analog core.
- **Material:** FR-4, **TG 135–140** (JLC's 4-layer default).
- **Stackup:** JLC04161H-7628, 1.6 mm finished.
- **Copper:** 1 oz outer, 0.5 oz inner.
- **Finish:** ENIG, for the 0.4 mm-pitch RP2040 and the exposed-pad packages.

### Outline and holes

- **Outline:** 100.00 × 100.00 mm (board coordinates x 50–150, y 45–145).
- **Mounting holes:** four 3.2 mm NPTH at (54, 54), (146, 54), (54, 141) and (146, 141).
  - Only GND copper lies within 3.5 mm of a hole, so metal standoffs are fine.
- **Sides:** all components are on top. Empty bottom silk is intentional.

### Vias, clearances and teardrops

- **Clearance:** design clearance 0.15 mm.
- **Vias:** every via has a **0.30 mm drill**: 435 vias (367 × 0.60 mm, 27 × 0.55 mm and 41 × 0.45 mm pads; 240 on GND).
  - This is JLC's standard "0.3mm/(0.4/0.45mm)" option. Do not select the 0.2 or 0.25 mm option.
- **Via covering: "Plugged"** (JLC's free 4-layer default; Tented is greyed out). Do not order POFV.
  - The only vias in SMT lands are the 33 exposed-pad thermal vias: U1 (8), U11 (6), U12 (6), U13 (9) and U14 (4).
  - They sit under paste windows, and JLC's plugging fills them. The TI package notes allow vias under paste that are "filled, plugged or tented".
  - X-ray the exposed-pad parts on the first build.
  - `validation/via-in-pad-process.json` records the check with the board hash.
- **Teardrops:** every via and pad carries a KiCad teardrop (1147 teardrop zones). Do not remove them in CAM.

### Plane voids, drills and origin

- **Plane voids:** keep the deliberate voids around the op-amp signal pins and feedback networks. Do not merge or redraw them in CAM.
- **Drills:** use the separate plated and non-plated Excellon files.
  - PTH: 461 holes (435 vias, four J1 shell slots, 2 × 1.0 mm, 4 × 1.2 mm and 16 × 1.4 mm for the BNCs).
  - NPTH: 6 holes (two 0.6 mm J1 pegs, four 3.2 mm mounting holes).
  - The USB shell slots must stay routed slots.
- **Origin:** the drill and placement origin is the lower-left outline corner, board (50, 145), exported (0, 0). Positive exported placement Y points up. Gerber, drill and CPL share it.

### Fabrication input and fiducials

- **The Gerber zip is the fabrication input.** It also holds:
  - the fabrication drawing (`temper-lcr-User_Drawings.gbr`, also `fab-drawing.pdf`);
  - the IPC-D-356 netlist (`temper-lcr.d356`).
- **Fiducials:** three global fiducials (FID1–FID3) sit near three corners, so no rail fiducials are needed.

### Edge rails

**Order option "Edge rails added by JLCPCB", with V-cut rails on the LEFT and RIGHT edges only.**
- Every edge has SMT copper within 2 mm (table below), so JLC's line needs rails.
- No rail on the front edge: the BNC barrels overhang it.
- No rail on the back edge: SMT lands are 0.45 mm from it.

| Edge | Nearest SMT land (to edge) | Other edge parts | Rail |
|---|---|---|---|
| Front, y 45 (BNC edge) | D4 0.40 mm | BNC J3, J7–J9 overhang | none |
| Back, y 145 | C82 0.45 mm (C80 0.65, R7 0.73, R80 0.78) | SW2 1.1 mm | none |
| Left, x 50 | R110 1.53 mm | J1 USB-C shell overhangs 0.2 mm, ≥ 0.9 mm above the board | V-cut |
| Right, x 150 | L2 0.95 mm | | V-cut |

**Copper to the outline is ≥ 0.4 mm everywhere** (`validation/rev-g100/edge-clearance.json`):
- The closest copper is the 5V corner on In2, at exactly 0.40 mm from the left and back edges. In2 sits 0.21 mm above the bottom surface, where a 30° V-cut groove one third of the board deep is about 0.09 mm wide, so the cut does not reach it.
- On the right edge, the nearest copper is the B.Cu GND pour at 0.50 mm.

## Assembly

### What JLC fits

- **SMT:** **248 top-side placements**, including the four TQ2SA relays, the TAC5112, the four TLP172AM photoMOS switches and the U16 TPS2553 USB switch.
- **Hand-fitted by JLC:** the four SAMZO BNC-KYWE-295-W4-N right-angle BNCs (J3, J7, J8, J9; C41416668), through-hole.
  - They are in `bom-jlcpcb.csv` and `cpl-jlcpcb.csv` with rotation 0. The EasyEDA record matches the footprint exactly on all five pads; the next-best orientation is 7.16 mm off.
  - Each barrel must face the front edge. The square pad pattern does not key the part, so check the preview and the silk opening mark.
- **JLC BOM:** 80 lines.
- **Complete BOM:** 253 components, 252 fitted.
- **Not fitted:** J4 (SWD header) is DNP. Firmware loads over USB, and the header can be soldered by hand if SWD is ever needed.
- **Power:** there is no DC jack; the board is powered from USB-C VBUS.

### Placement-preview checks

Do not use the viewer's arrow buttons: they move the selected part.

- **From Rev F (its preview of 2026-10-30 passed C117, U17, U1, K1–K4 and the +/− marks of D5–D8 and D15–D20):**
  - **C117:** the + terminal (pad 1, the chamfered corner) is on the south land, toward the back edge.
  - **U17** (LM3880): pin 1 at the north-west land; CPL offset 180°, as for U16.
  - **Y1:** orient by pad geometry, because the chamfer mark is unreliable. Pins 1 / 3 are the crystal, 2 / 4 the lid; 90° off means no USB.
  - **K1–K4:** rotation and stripe against pad 1.
  - **D4** (side-looking LED): lens toward the front edge, pad 1 (cathode) toward the left mounting hole.
  - **D18:** rotated 180° from D15–D17 on purpose; its anode is on GND.
- **New on Rev G / G100:**
  - **U18–U21** (TLP172AM): pin 1 (anode) as on the silk.
  - **D28** (BAV99): pin 3 toward DUT_LO.
  - **D29** (SS14, the −12 V clamp): cathode (pad 1, the silk bar) on GND.
  - **Q7.**
  - **The BNCs:** barrels toward the front edge.
  - The TVS diodes D21–D24 and the second-stage clamps are bidirectional and have no polarity.
- **Rotations the second layout review asked to confirm:** U5, D1, U16, U17, U3 and U15. The SOT-23-5 and SOT-23-6 offsets differ by vendor; a rotated regulator is a dead board.

### Process notes

- **K1–K4 (TQ2SA):** a single reflow; no ultrasonic cleaning; no silicone near the relays (Panasonic ASCTB14E p.19).
- **C117:** one reflow at a 260 °C peak.
- **Stencil:** 0.10–0.12 mm, for U1's 0.4 mm-pitch QFN.
- **J1:** a mixed-technology USB connector in SMT assembly. Its shield anchors must be soldered.

### Orientation records

`orientation-audit.csv` records, for each placed part:
- native rotation;
- library correction;
- final CPL angle;
- pin-1 location.

The corrections come from each LCSC part's EasyEDA pad numbering (`sources/placement-rev-c.json`).

## Prototype release

Before packaging, these must pass on the final source files (`sh validation/rev-g100/gates.sh`):
- native ERC and DRC;
- schematic / PCB parity;
- BOM membership and placement coordinates.

Before approving assembly, complete the vendor placement preview, including the exposed-pad via treatment.

These remain prototype tests:
- physical stability;
- source-off noise;
- codec acquisition;
- calibrated accuracy;
- the relay state check.

Bring-up is [bring-up-rev-e.md](../docs/bring-up-rev-e.md), then [bring-up-rev-g.md](../docs/bring-up-rev-g.md) Part B.
