# Controller prototype order package: C51 board, C53 layout (JLC PCB + PCBA)

**Nothing has been ordered, uploaded or paid. Ordering is the owner's decision, and the owner sends the JLC message.**

**One owner decision is open before ordering: CR-2 gate 1b** (§5.1). Everything else in this file is ready.

The C49 package this file used to describe is in git history (ORDER.md before 2026-11-28). It is superseded.

## Board of record

| Item | Value |
|---|---|
| Board | `pcb/controller.kicad_pcb`, sha256 `3efed65cf7fe28ec44d10adf0de652be7a9bdc9edd892fc93f6ca334d5ef5b2e`, branch `controller-c51` |
| Origin | C53 convergence set 11 run 2 (`e82e6140…`, 2 of 3 runs clean on routing code 1be33819a), plus the set 11 review M1 vias at L1.2 (`evidence/convergence.json` `post_proof_change`) |
| Netlist | `frozen/default.net` `8471186c…` (`frozen/build-receipt.json`) |
| Gates | DRC 0 errors / 0 unconnected / parity 0 (27 warnings, LAYOUT.md Results); JLC DFM PASS; 22/22 layout checks; gerbv PASS; `verify_controller.py` 270/270 |
| Reviews | Independent layout review `evidence/c53-set11-review/REVIEW.md` and bring-up pre-mortem `evidence/c53-set11-premortem/PREMORTEM.md`. Dispositions: DECISIONS C53, "set 11 review and pre-mortem" |
| Firmware | `fw/c51-s56-unified` at fbd6f5ca9 (the pre-mortem matched it against this netlist pin by pin and rebuilt it with ESP-IDF 5.3.6; it has not run on hardware) |

## 1. Files to upload

| File | Path | sha256 |
|---|---|---|
| Gerbers + drill (zip; drill maps left out) | `fab/controller-gerbers.zip` | `161b13fca9dfa01dde263c18bf90198d795fe0aedd89bbd8b0bccd8633b8d823` |
| BOM (96 lines) | `fab/bom-jlcpcb.csv` | `bd689c1dad7344df38e5d16c3e309aa6e9ac74855535b75239758cca2f1c8ff0` |
| CPL (342 placements: 331 SMD / 11 THT, all top side) | `fab/cpl-jlcpcb.csv` | `947d00bbc56b5e0cc35841bf521a7a5b722d8e8acbafa43de91557c08b74caa1` |
| Assembly drawing (reference, not uploaded) | `fab/assembly-top.pdf` | `7cc77a172284948e76206b2407e17290ee9680a7480460bfe72f274f75c1fe44` |

`python3 layout/make.py --no-route` regenerates these from the board. The Gerbers re-plot identically apart from their date lines.
The pre-mortem checked this for all 13 layers and both drill files.

## 2. Order form

| Option | Set to |
|---|---|
| Size | 206.0 × 76.0 mm, single board, no panel |
| Layers / stack-up | 6, **JLC06161H-3313**: F.Cu signal / In1 selv_gnd plane / In2 v3v3 pour + signals / In3 signals / In4 selv_gnd plane / B.Cu signal |
| Thickness / copper | 1.6 mm; 1 oz outer, 0.5 oz inner |
| Surface finish | **ENIG** (JLC offers no HASL on FR-4 of 6 or more layers) |
| **Via covering** | **Epoxy filled and capped. Confirm it on the form before paying.** 387 via drills touch an SMD pad and 138 sit inside one (57 in 0603 resistor pads, 16 under the module). With tented or plugged vias, expect solder wicking, tombstoned 0603s and starved IC joints. `fab-notes.md` cites JLC's article (2026-11-10) that this is the free default for 6+ layers. Neither report re-read it, so read the quote page |
| Mask / silk | green / white |
| Impedance control | none (no controlled-impedance nets) |
| Holes | six Ø4.0 mm non-plated holes milled from Edge.Cuts; 5 NPTH hits (J4's 2 pegs, J11's 3 TC2050 holes) |
| Minimum features | track 0.15 mm, clearance 0.15 mm, via 0.6 / 0.3 mm (`evidence/jlc-dfm.json`) |
| Assembly | **Standard PCBA**, top side only. JLC hand-solders the 11 THT connectors. U4 (ESP32-S3-WROOM-1U-N8) is SMT |
| Order remark | "THT connectors: fit each body to the silkscreen outline and pin-1 mark; the key wall follows the silk outline." |

**Quantity:** 5 bare PCBs, 3 assembled (JLC's PCBA minimum is 2). **Confirm JLC's six-layer minimum quantity on the quote page**;
if it is above 5, order the minimum and assemble 3.

## 3. JLC placement preview: check before paying

One designator per LCSC code is enough; the rest of the code follows. The full list is in `fab/fab-notes.md`, "NEEDS-PREVIEW".

1. **THT connectors (set 11 review B1).**
   - The CPL now turns J1, J2, J3, J7, J14 and J15 by 180°, J9 to 0° and J4 to 270°. J4 is placed at its pin-field centre
     (30.935, −67.600).
   - JLC's footprints for these codes are ours turned 180°, body and pin 1 together. The 2026-10-19 preview had kept KiCad's
     rotation because J4's body then hung off the edge. That came from J4's CPL position, which included the pegs, and is now
     fixed.
   - **In the preview, every header's body and key wall should sit on our silk outline without any manual rotation.**
     - J4's body sits on the board-edge side, mating face flush with the edge.
     - J9 is deliberately the other way round from J3; the harness drawing must say so.
   - If any header renders off its silk outline, stop and recheck the code. Do not rotate it by hand to "look right".
   - Why it matters:
     - J7 reversed shorts v3v3 to the UI board's ground, and J15 reversed puts 12 V on the fan's PWM lead;
     - J14 reversed swaps bay_node and ground;
     - J1, J2, J3 and J9 still work reversed, but their keys face the wrong way for the harness.
2. **C1 / C9** (UCD1E101MCL6GS, C445471, 100 µF across 15 V): the "+" mark on the pad toward +X. This code has never been
   seen in a JLC preview.
3. **Codes never seen in a JLC preview:** U11 (C840098), U52 (C148036), Q2 (C82045), D10 (C155248). The pre-mortem's pad fit
   puts all four on our pin 1 (0.04, 0.03, 0.30 and 0.21 mm).
4. **D9** (SS14, C2480): band at the end away from J13 (cathode = pad 1, `evidence/fab-loose-ends/cpl-rotation/D9-C2480.md`).
5. **JLC BOM step:**
   - accept JLC's match on every line, but reject any "similar part" substitution, above all R39 (PTFR0805B430RN9) and the
     0.1 % thin-film resistors;
   - U4 must show as an SMT placement.

## 4. Stock

- **Read 2026-11-27 07:28–07:30Z:** `evidence/c53-order/stock-read.json` (`read_stock.py`; read-only, exact MPN match).
- **Result:** every one of the 96 lines is in stock under its BOM code. Nothing is consigned or owner-fitted.
- The BOM's last column is an older read and has blanks; trust the stock-read file instead.
- **Thin lines.** Re-read them on order day: JLC stock moves daily, and a 5-board build needs 5 of each single part.

| Part | Ref | Stock | Per board |
|---|---|---|---|
| AD8436ARQZ-R7 | U14 | 28 | 1 |
| MCP3202-CI/SN | U15 | 31 | 1 |
| TPS3703A4330DSERQ1 | U3 | 52 | 1 |
| RT0603BRD078K06L | R31 | 68 | 1 |
| TPS389001DSER | U34 | 96 | 1 |
| TLV9031DBVR | U19, U26 | 222 | 2 |

## 5. Owner items before paying

1. **CR-2 gate 1b (decision; LAYOUT.md open item 13).**
   - **The problem:** the routed copper between the pan MAX31865 (U30) and its Rref (R39) is 252.9 mΩ. Its copper tempco adds
     0.074 K at 250 °C over the 60 K board swing. That takes the board terms of gate 1b to **0.493 K against your 0.45 K**;
     the RSS is 0.414 K and passes.
   - **Why it can't be fixed in place:** R39 cannot move to U30's pins as placed.
   - **Options:**
     - (a) accept it for the prototype and fix it in the next layout;
     - (b) re-lay the RTD front end, or split the Rref nets for a Kelvin tie, then re-route and re-prove before ordering.
2. **J4 numbering.**
   - Read circuit 1's position against the pegs on Molex's `430451600_sd.pdf` and record it in DECISIONS.
   - KiCad's and JLC's footprints now agree on pin 1 relative to the body (set 11 review B1). That is not the Molex drawing.
   - J4 cannot be inserted reversed, so only a numbering error in both libraries would transpose the 16 circuits.

## 6. Have ready before the boards arrive

- **First-flash lead (pre-mortem M4).** The board flashes only over USB-Serial-JTAG on the J11 pads.
  - There is no UART download path (RXD0 is UI_MISO) and no VBUS pad, so the board needs 15 V on J13 while flashing.
  - Parts: a Tag-Connect **TC2050-IDC-NL** (and a TC2050-CLIP if the console stays connected).
  - Wire a USB cable or breakout to its ribbon socket: **D− to pin 6, D+ to pin 7, GND to pin 5 or 8, VBUS not connected**.
  - Add two jumpers or buttons: pin 3 (IO0) to GND and pin 2 (EN) to GND.
  - Make and test the lead first. The plug's clearance to C91 (0.17 mm outside the courtyard) was not established.
- **15 V:** a current-limited bench supply for J13 (first power 0.3 A), then PS3 (Mean Well **MPM-90-15ST**, C51; not the IRM-60).
  - J13 has no reverse-polarity protection on the fan branch. Meter the harness polarity first: J13.1 is +15 V.
- **J4 harness buzz:** J4.3 to the power board's 3.3 V, J4.9 to its PERMIT, J4.2 to ground, before mating. The power board
  must be stage 50 or later (J4.1 = BIAS_GOOD, not 15 V).
- **Stand-ins for a bare-board interlock check:**
  - 10 kΩ across J1 and across J2;
  - 100 Ω on J3, wired four-wire;
  - J4.10 to ground.
  PERMIT cannot rise without them.
- **Bring-up checklist:** `evidence/c53-set11-premortem/PREMORTEM.md`, "Bring-up checklist: first power-up". Run it in order and
  stop at the first failure. Two of its notes:
  - One "SAFE MODE" log line after a flash is expected (pre-mortem m3).
  - If RAIL_OK_RB never reads high, measure v3v3 at C20 first: the 3.3 V window is 21 mV at the worst corner (m8).

## 7. Accepted for the prototype (bench or next layout)

These come from the set 11 review. None blocks fab; each is in DECISIONS C53.
- **V_BLOWER:** 0.8 mm at the fan's 2.70 A start/lock maximum is about a 19 K rise by IPC-2221; at the 1.42 A running current
  it is about 6 K (m3).
- **C91:** the module's EN capacitor is 48 mm from the EN pin. The delay still works; move it to the pin at the next placement (m5).
- **U51:** FB runs 6 mm under its SW pour, with two ground planes between (m6).
- **U2 thermal margin at 2.70 A:** bench check (m9).
- **No test points:** rails are probed on pads; J11 is the flash path (m10).
- **ESP32 v3v3 island:** it hangs on two 0.3 mm links; about 12–15 mΩ with 22 µF local (m1).
- **One 2.4 mm dead-end v3v3 stub beside U31:** it carries no connection (DRC `track_dangling`).

The bench and firmware items carried from earlier stages are DECISIONS "Open items" (AD8436 settling, the 2EDR8259X DIS delay
and CT polarity, the rim maximum under a 250 °C hold, the firmware constants and the CR-2 gain calibration in `rtd_convert.c`)
and the block-validator waivers W1–W8 (`evidence/block-validators/WAIVERS.md`).
