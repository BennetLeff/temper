# Rev G plan: Rev F with protected jacks, on 100 × 110 mm

Rev G is Rev F with a protection network on the four BNC jacks: one normally open TLP172AM switch per jack, a jack TVS at each jack, and a series resistor and second-stage clamp behind each switch. Firmware closes the switches only when the rails are up and the jacks read near 0 V. The protection network was designed in `../validation/rev-g-protection/` (phases 1–7). This document records the schematic and layout step and its decisions.

**Status (2026-11-09): laid out, hand-routed, every board gate clean. Not orderable.** These steps remain before ordering:
- an independent review of the frozen export;
- the parasitic extraction of the jack band and the stability matrix on it (Open items);
- JLC's placement preview;
- any Rev F bring-up finding on the nodes Rev G touches.

`manufacturing/` and `previews/` on this branch stay Rev F. The Rev G evidence is in `../validation/rev-g/`. Rev F stays intact and orderable on `study/lcr-in-box`.

## 1. What changed against Rev F

**Board.** The outline is 100 × 110 mm at x 50–150, y 45–155. `cad/tools/rev_g.py` builds Rev G from Rev F's own source (`rev_f.py`) and routes (`rev_f_routes.py`), then applies one transform:
- Every point below y = 57 moves 10 mm toward the back. This covers parts, track points, vias, zones, keep-outs (by centroid), holes, fiducials and test pads.
- J3 / J7 / J8 / J9 (the BNCs), D4 and R12 stay where they are.
- The protection goes in the new 10 mm band, y 57–67, between the BNC row and Rev F's first analog parts.

Rev F's hand routes are therefore kept as coordinate transforms, and no autorouter is involved. `validation/rev-g/copper-shift-delta.json` checks this. 361 of Rev F's 400 analog-net items are identical after the transform. The rest lie inside y 51–77.5: the DUT_HI, HPOT, LPOT and DUT_LO ends at the jacks, plus a 2.3 mm SOURCE_FB bend that the craft pass split the other way round (2.24 mm instead of 2.30 mm; SOURCE_FB is not an extracted net).

**Protection network** (all on the new schematic sheet `protect`; values from `../validation/rev-g-protection/README.md`, "Schematic delta"):

| Refs | Part | Connection |
|---|---|---|
| D21–D24 | H4V5HD3B, SOD-323 (C20615803) | JK_HCUR / JK_HPOT / JK_LPOT / JK_LCUR to GND, at each BNC centre pin |
| U18–U21 | TLP172AM (C2152276) | switch jack side to ISO_x. The north pin faces the jack: 4 on HCUR / LCUR, 6 on HPOT / LPOT |
| R122 / R125 | 10 Ω CRCW0805-HP (C844598) | ISO_HCUR – DUT_HI, ISO_LCUR – DUT_LO |
| R123 / R124 | 100 Ω CRCW0603-HP (C844725) | ISO_HPOT – HPOT, ISO_LPOT – LPOT |
| D25–D27 | H3V3LD5B, SOD-523 (C20615817) | DUT_HI, HPOT, LPOT to GND |
| C119 / C120 | 1 nF C0G (C106246) | HPOT, LPOT to GND |
| D28 | BAV99 (C2500) | pin 3 DUT_LO, pins 1 and 2 GND (an antiparallel pair) |
| R105 / R106 | 1 kΩ (moved) | JK_HCUR – JK_HPOT, JK_LCUR – JK_LPOT, on the jack side |
| K4, R107 | (moved) | COM2 (pin 8) and COM1 (pin 3) on JK_HCUR, NO1 (pin 4) on JK_HPOT (the phase 7 reference bypass); R107 REF_A – JK_LCUR |
| R126 / R129, R127 / R130, R128 / R131, C121 / C122 | 1.5 MΩ, 240 kΩ, 240 kΩ, 100 nF | jack senses: JK_HCUR (JK_LCUR) – JACK_HC (JACK_LC); to 3V3; to GND; to GND |
| R132 / R133 | 300 Ω (C23025) | VRLY – LED string 1 (U19 HPOT, then U18 HCUR); VRLY – string 2 (U20 LPOT, then U21 LCUR) |
| Q7, R134, R135 | AO3400A, 100 Ω, 100 kΩ | ISO_SINK (both string ends) switched to GND; gate from GPIO 15 (ISO_DRIVE) |

**Removed:** J6 (the optional UART header) and its UART_TX / UART_RX nets.

**Parts:**
- 253 components and 247 SMT placements, against Rev F's 223 / 216.
- 77 SMT lines (69 on Rev F), of which 31 are extended (27 on Rev F). The four new extended lines are the TLP172AM, the two thin-film resistors and the 1 nF C0G, about $12 of feeder fees per order.
- Catalog SMT cost $49.10 per board, against $45.43.

## 2. Gates (2026-11-09, board `f3976936…cccf`)

The board's analog copper was frozen at `b956ee70…981d`. The only later change is the TLP172AM footprint's 3D model path, which now points at the exact-part model from the LCSC record (`cad/tools/models_3d.py`, fit RMS 0.05 mm) because KiCad 10 ships no SO-4 model at the old path. ERC, DRC, the fab pass, the via audit, the independent check, the pinout ledger and the firmware pins were rerun on the new file; the rest depend only on copper and the netlist.

| Check | Result | Evidence |
|---|---|---|
| Pre-DRC (`rev_g.py --check`, `temper_boardkit.craft` rules) | 0 violations, 0 unconnected | `../build/rev-g-predrc.json` (regenerated) |
| KiCad ERC / DRC / unconnected / schematic parity | 0 / 0 / 0 / 0 | `../validation/rev-g/erc.json`, `drc.json` |
| JLC fab pass (`jlcpcb-4layer-1oz`) | PASS | `../validation/rev-g/fab-check.json` |
| DFM via audit | 33 exposed-pad thermal vias only | `../validation/rev-g/via-in-pad-process.json` |
| Independent audit (`independent_check.py g`) | 744 pins, 12 relief pins, 0 findings. The Rev G topology check covers jack → switch → series R → Rev F node for all four jacks, and TIA_SUM unchanged | `../validation/independent-verification-rev-g.json` |
| Gerber-level netlist (Rev G Gerbers, drill and IPC-D-356 exported to `build/rev-g-gerbers.zip`) | 0 shorts, 0 opens, 0 floating copper over 143 nets; minimum different-net gap 0.150 mm; the self-test catches a planted short, open and floating island | `../validation/rev-g/gerber-netlist-check.json` |
| Pinout ledger (`ledger-rev-g.json`) | 25 PASS, 6 NOTE, 0 FINDING; nothing uncovered. New rows: TLP172AM, H4V5HD3B, H3V3LD5B, BAV99; Q7 in the AO3400A row | `../validation/pinout-ledger/ledger-rev-g.check.json` |
| Firmware pins | 81 pass, 0 findings (with the Rev G drive and sense traces); four mutations caught | `../validation/firmware-pins/` |
| Drive budget | every check PASS (section 4) | `../validation/rev-g-protection/drive-budget.json` |
| Passive ratings | 92 capacitors, 94 resistors, 0 findings (R121's hot-plug note as on Rev F) | `../validation/rev-g/passive-ratings-check.json` |
| Paste, USB FS, supply copper | 0 findings each; USB 44.8 / 51.7 mm, skew 48 ps; supply nets 0 FAIL | `../validation/rev-g/{paste-check,usb-fs-check,current_check}.json` |
| Layout audit, edge clearance, pours | written; edge copper ≥ 0.50 mm on the V-cut edges (Rev F's) | `../validation/layout-audit-rev-g.json`, `../validation/rev-g/{edge-clearance,pour-report}.json` |
| CPL rotations (`placement_offsets.py`) | TLP172AM 270° (RMS 0.05 mm, next 4.84 mm); H4V5HD3B 0° (0.02); H3V3LD5B 0° (0.05); BAV99 180° (0.28: LCSC's wide SOT-23 land, below); Q7 as Q6 | `../sources/placement-rev-c.json` |
| Stability, Rev F board parasitics + Rev G network lumped (`revgcng100`), rerun with the 1.5 MΩ sense | worst drive 47.76°, HIGH 57.90°, LOW 57.17°, TIA 69.92°, the same as with 1 MΩ | `../validation/stability-full-chain/summary-revgcng100.md` |

## 3. Enclosure

The board grows 10 mm toward the back, and the front face does not change:
- The box becomes **110 × 120 × 36 mm** (Rev F 110 × 110).
- The BNC holes, the D4 lens and the front plate are unchanged.
- The USB-C cut-out moves from 77 to **87 mm** behind the front edge, on the same (left) wall. J1 is at y 132.
- The mounting-hole pattern becomes **92 × 97 mm** (holes at y 54 and 151).
- `../validation/rev-g/board-envelope.json` (`board_envelope.py` on Rev G):
  - the board measures 100.05 × 110.05 mm, and the BNCs are still the tallest parts (13.75 mm) and reach 18.48 mm past the front edge;
  - H1 / H2 (front) are clear of M3 hardware, with H2 3.5 mm from JK_HPOT on B.Cu;
  - H3 / H4 keep Rev F's 1.8 mm to the B.Cu GND pour, so the insulating standoffs are still needed;
  - J1 is flush with the left edge at y 127.5–136.5.

## 4. Firmware

`../firmware-rev-e/` builds Rev G with `-DLCR_REV_G=1` (README, "Rev G jack guard").
- **Divider constants** follow the board: `JG_RTOP_G_PPM` 13 500 000 and `JG_RTOP_RBIAS_PPM` 6 250 000. The conversion is now in ppm, because R_TOP / R_BIAS = 6.25 is not an integer.
- **Close window:** `JG_STABLE_POLLS` is 7 (35 ms), against 33 ms of filter settling from a clamped jack.
- **UART:** Rev G defines no UART pins.
- **Verification:**
  - The host test passes at both sample rates.
  - The Rev G image builds with `-Werror`.
  - Built at one path, HEAD's source and this tree give byte-identical Rev E/F UF2s. The committed UF2s differ from a fresh build only in the `__DATE__` string of the binary info.

**Drive budget** (`drive_budget.py` now reads R101, R132 / R133 and the dividers from `design.json`):
- 5.03 mA per LED at the 4.32 V rail minimum and VF max, against 5 mA recommended.
- 4.59 mA during the four-coil RESET pulse (112 mA on R101, rail at 4.30 V), above the 3 mA IFT. The coils still get 4.17 V, against 3.75 V must-operate.
- 10.9 mA at 5.5 V and VF min.

## 5. Decisions

| Date | Decision | Basis |
|---|---|---|
| 2026-11-09 | **Rev G schematic and layout start now, ahead of Rev F bring-up (owner).** Supersedes the 2026-11-08 sequencing in `rev-g-protection/README.md` | Owner request: "can you start it now". The reason for the old order still stands: Rev G sits on Rev F's most sensitive nodes. So a Rev F bring-up finding on those nodes is applied to Rev G before Rev G is ordered, and Rev G is not called orderable before then |
| 2026-11-09 | **100 × 110 mm: Rev F below y 57 moved 10 mm back as a rigid transform; the protection in the new band** | Keeping 100 × 100 would have meant re-placing Rev F's analog parts and re-extracting the whole board. The transform keeps every hand route and every analog distance outside the band, as `copper-shift-delta.json` shows. The cost is 10 mm of box depth |
| 2026-11-09 | **Sense divider 1.5 MΩ / 240 kΩ / 240 kΩ** (R111 and R83 lines already on Rev F's BOM), instead of the study's 1 MΩ / 200 kΩ / 249 kΩ | No new BOM line, so no feeder fees. The changes are all small or improvements: full scale −20.6 to +23.9 V (±16.5 V before); about 11 mV per code; 1.0 µA of bias into a jack (1.6 before); filter 11.1 ms (10 before); and a lighter load on LCUR. The accuracy tables move by at most 0.0001 % (`normal_operation.py`), and stability is unchanged. The firmware stable window grows from 6 to 7 polls to keep covering the settling |
| 2026-11-09 | **LED strings fed from VRLY (after R101, 1 Ω), not from the 5 V trunk** | VRLY copper is already in the band at the relay coil pins; the 5 V trunk is not. The cost is R101's drop: the steady minimum falls from 5.07 to 5.03 mA (above 5 mA). During a RESET pulse it is 4.59 mA, still above the 3 mA IFT, so the switches stay closed through a range change |
| 2026-11-09 | **J6 (UART header) removed** | The jack senses need ADC2 / ADC3 (GPIO 28 / 29). GPIO 0 / 1 cannot leave U1: the I2S_DIN via and the 3V3 F.Cu block its pins 2 / 3, and GPIO 16 / 17 and 20 / 21 are blocked too. The firmware never enabled UART stdio. The console is USB CDC, and SWD (J4) stays for debugging. Supersedes phase 7's "UART moves to GPIO 0 / 1" |
| 2026-11-09 | **Net names follow the firmware pins: JACK_HC, JACK_LC, ISO_DRIVE; ISO_SINK for the string ends** | `firmware_pins_check.py` then needs no name exceptions for Rev G |
| 2026-11-09 | **Sense divider split: GND legs and filter capacitors at the band's west end (C121 / R128 / C122 / R131 at x 55.4, y 59–64); 3V3 legs west of J4 next to U1 (R127 / R130 at y 121.6); the senses run on In2 down the west edge (x 51.6 / 53.0) and on 0.15 mm B.Cu lanes past J1 (x 55.2 / 55.75)** | The I2C B.Cu bundle north of U1 left no room for GND vias at the ADC pins. With the 100 nF at the jack end, a transient is filtered before it travels the board. Above about 15 Hz the 100 nF sets the node impedance (1.6 kΩ at 1 kHz, 1.6 Ω at 1 MHz), and In1 GND sits above the run. A 50 Hz pickup would be filtered like the 46 Hz tone (0.30 of it), against a 1 V close threshold |
| 2026-11-09 | **Footprints: `LCR:D_SOD-323_HJC` (HJC suggested layout, 0.80 × 0.80 pads, gap 1.40; silk bar 0.15 mm off pad 1); `LCR:Toshiba_11-4M1S` (KiCad SO-4 renumbered 1/3/4/6); KiCad D_SOD-523 unchanged** | KiCad's D_SOD-323 pads (0.6 × 0.45) are under HJC's minimums. Toshiba prints no land pattern, but LCSC's own record lands on the renumbered SO-4 within 0.05 mm (`cad/tools/make_rev_g_footprints.py`, pinout ledger) |
| 2026-11-09 | **BAV99 on KiCad SOT-23, not LCSC's wide land** | Our rows are 1.875 mm apart, against Nexperia's reflow footprint at 2.0 (Fig. 8; pads within 0.062 mm of it). LCSC's record (LS2.8) is wider still, so its pads fall up to 0.40 mm outside ours, symmetric about the centroid JLC places by. Recorded as a NOTE for the placement preview |
| 2026-11-09 | **Evidence in `validation/rev-g/`; `manufacturing/` and `previews/` stay Rev F until the review passes** | As Rev F did before its promotion (`rev-f-plan.md` §5, 2026-10-29): a study branch does not leave an orderable package for an unreviewed board. The BOM / CPL / orientation CSVs are kept there as evidence (no Gerbers) |
| 2026-11-09 | **Protection screen, accuracy and stability models carry the 1.5 MΩ sense** (`protection_screen.py` `parts_jackside`) | The models describe the board as built |

## 6. Open items before Rev G is orderable

1. **Parasitic extraction of the band, then stability on it.** The windows outside the band are Rev F's copper moved (`copper-shift-delta.json`), so their zoom ratios carry over. The whole board and the band windows (DUT_HI, HPOT, LPOT and DUT_LO up to the series resistors, R107 / K4) are re-solved; the result feeds a stability mode on the Rev G board.
2. **Independent review** of the frozen export (a fresh reviewer with the files, not these conclusions).
3. **Placement preview** at JLC: D28 pin 3 toward DUT_LO; U18–U21 pin 1 (anode) orientation; D4 and Y1 as on Rev F.
4. **Rev F bring-up** findings on the band nodes; confirm the TLP172AM COFF and the TVS capacitances (`rev-g-protection/README.md`, "Open items").
