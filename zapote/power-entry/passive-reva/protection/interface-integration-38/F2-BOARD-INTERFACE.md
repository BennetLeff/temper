# Rev38 F2 board-to-holder interface candidate

Status: **exact connector candidate found; footprint and fault-current acceptance OPEN**. F2 remains the off-board Mersen `A70QS50-14F` in `US141/Z331153`; this note selects no alternate holder or fuse.

## Candidate: Phoenix Contact 1017526

The [Phoenix Contact `TDPT 16/ 2-SC-10,16-ZB` product record](https://www.phoenixcontact.com/en-pc/products/pcb-terminal-block-tdpt-16-2-sc-1016-zb-1017526) identifies order number **1017526**, a two-position PCB screw terminal with two distinct potentials. It can be the *board end* of the dedicated VD-out/VB-return cable pair. Position 1 would carry `VD_LOCAL` to the holder input; position 2 would return holder output to `VB_BANK`. Neither position is HOT0, and the block does not replace F2.

| Published property | Exact-part evidence | Rev38 disposition |
| --- | --- | --- |
| Nominal current and insulation | 76 A, 1000 V for IEC III/2; 800 V for III/3; cULus listing table gives 58 A, 600 V for B/C | Above the 50 A fuse nameplate as a nominal component screen. Confirm the intended residential certification category and DC application; ratings do not establish fault-current withstand or PCB trace capacity. |
| Wire and assembly | 0.75–16 mm² rigid/flexible, AWG 20–6; 18 mm strip; 1.4–1.7 N·m screw torque | Select one conductor size and insulation/termination method for the actual cable and holder, then qualify bend radius, strain relief and assembly torque. |
| Temperature | −40 to 105 °C operation **subject to current derating**; housing PA, CTI 600, UL94 V-0 | Measure local enclosure and terminal temperature at worst sustained and pulsed load. The 76 A nominal figure is not an all-temperature permission. |
| Insulation geometry | Manufacturer states 8 mm minimum clearance and 8 mm creepage for III/2, 1000 V/8 kV; III/3 is 8 mm clearance and 10 mm creepage at 800 V/8 kV | Check adjacent live structures, solder pads, copper and enclosure in the native board; the terminal's internal figures do not prove board spacing. |
| Board pattern | 10.16 mm pitch, **zigzag W pinning**, two 1 × 0.9 mm solder pins per potential, 3.5 mm solder-pin length, manufacturer PCB hole diameter **1.85 mm** | These published values are insufficient to place all four pad centers. Obtain Phoenix's exact drilling drawing or ECAD model and map each pair to its potential before assigning a native footprint. No generic straight-row 10.16 mm footprint is justified. |

The product page also lists a 21.34 × 31.9 mm board-facing envelope and 31.2 mm installed height. The [manufacturer's generated product PDF](https://www.phoenixcontact.com/en-gb/products/printed-circuit-board-terminal-tdpt-16-2-sc-1016-zb-1017526?type=pdf) repeats the same dimensions and ratings. Its catalogue text specifies the zigzag pattern and hole size but does not provide machine-readable pad-center coordinates; no Rev38 library footprint exists for 1017526. The manufacturer drawing/CAD and a footprint pad-to-terminal continuity check are therefore required before native placement.

## Circuit and assembly boundary

The joined schematic presently represents `f2` as a two-pin series element, `f2.diode` on `VD_LOCAL` and `f2.bank` on `VB_BANK`. A native PCB must also represent the **separate board terminal block** and cable pair. For 1017526, model each of its two potentials with its two physical solder pins tied to the correct net (or use verified duplicate pad numbers if the export bridge supports them). The off-board F2 stays in the assembly schematic/BOM; a board-only netlist may terminate at two distinct terminal potentials, but its evidence must trace the external holder path back to the joined circuit. Putting the existing `temper:A70QS50_ETI_CH14_Prototype` clip footprint on the board would contradict the selected US141 holder.

Before promoting this candidate, close four specific inputs:

1. Get the manufacturer drilling/CAD data and verify the four pad coordinates, pad-to-potential map, hole/annular-ring tolerances, courtyard and copper spacing in KiCad. Check whether a 10.16 mm two-position block leaves adequate clearance and creepage between the solder lands at the required fault and installation voltages.
2. Set the intended cable gauge, insulation, termination, restraint, enclosure routing and holder terminal details. Include both cable/contact resistance and inductance in the F2 capacitor-discharge and thermal analysis.
3. Establish the maximum continuous, pulsed and prospective fault current at this interface, then obtain a justifiable short-time withstand/temperature-rise basis for the block, joints, copper and cable. The catalogue's nominal current and its statement that short-time withstand was tested provide no numeric fault envelope.
4. Confirm the applicable voltage/category and listing basis for the residential product, including whether the cULus 600 V table covers the required DC use. The selected F2 fuse's DC clearing/let-through and minimum-breaking-current questions remain separately open under the [retained disposition](../DISPOSITION.md).

Until these are closed, retain the `TBD_REVIEW_ONLY` F2 footprint in `pfc_power.ato`; do not silently use the provisional PCB clips or claim a physical F2 interface PASS.
