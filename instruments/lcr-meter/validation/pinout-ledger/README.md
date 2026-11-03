# Pinout ledger, Rev F (2026-11-03)

This check covers every multi-pin or polarized part on the Rev F board. For each one it asks three questions:

- **Pinout:** does each pad's net fit the function the manufacturer's datasheet gives that pin?
- **Land pattern:** does the footprint match the datasheet land pattern or package drawing?
- **JLC part:** is the LCSC part in the JLC BOM really that package and variant, and is it turned the right way in the CPL?

`validation/independent_check.py` already proves that design.json, the board pads and the schematic netlist agree. This check covers the datasheet side, which nothing else checked.

## Files

- **[ledger.json](ledger.json):** the datasheet facts for each part:
  - document, URL, SHA-256 of the PDF and the page or table used;
  - the pin table;
  - the land-pattern numbers;
  - the net each datasheet function must carry on this board.

  For the RP2040, the expected nets come from `firmware-rev-e/src/pins.h` GPIO numbers. Each GPIO number is mapped to a package pin through the datasheet pin list, not through design.json. Vendor PDFs are not committed; each one is cited by URL and SHA-256 (fetched 2026-11-03).
- **[pinout_check.py](pinout_check.py):** compares ledger.json with design.json, the board (read with pcbnew), the JLC BOM and CPL, and the committed LCSC/EasyEDA records in `sources/placement-library/`. It writes [pinout-check.json](pinout-check.json) and exits 1 on any FINDING, or if any part other than a non-polar R or C is missing from the ledger. To run it:

  ```
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 validation/pinout-ledger/pinout_check.py
  ```

  `--ledger PATH` runs it against another ledger. A seeded ledger with nine planted errors produced eight FINDINGs and one coverage failure; one of the nine (a renamed exposed pad) was not a real error and correctly passed. The eight caught:
  - EN on the wrong net;
  - BAT54S anode and cathode swapped;
  - LED cathode reversed in the JLC placement;
  - wrong RP2040 pitch;
  - relay row span 10.16;
  - one USB-C pad moved 0.5 mm;
  - TAC5112 exposed pad 2.45;
  - flash package SOIC-150.

  The coverage failure was the dropped SS14 row.

## What each part row checks

- **Identity:** the MPN and LCSC number in design.json and in the JLC BOM, and the MPN and package in the LCSC/EasyEDA record.
- **Pin names:** the names in `design.json` `pinouts` match the datasheet names.
- **Nets:** every pad is on the net its datasheet function needs. NC and DNC pins must be open (or on GND where the datasheet allows it). Named support parts must sit on function nets: ILIM resistor, VREF capacitor, CC pull-downs, and so on.
- **Board land pattern:**
  - pad count;
  - pitch;
  - row span between pad centres;
  - pin-1 pad size;
  - exposed-pad size;
  - absolute pad positions (USB-C, BNC, TAC5112 corner pads);
  - pin-1 quadrant;
  - counter-clockwise pad numbering seen from the top.
- **JLC orientation:** the LCSC part's own pads (EasyEDA record, which is what JLC places from), turned by the CPL rotation, must land on board pads of the same function within 0.4 mm. This also covers 2-pin parts: a polarity flip shows up as a 1.5 mm miss.

## Result

**0 FINDINGs. 22 PASS, 5 NOTE**, 27 part rows covering 56 parts and 333 individual checks. No pin is on a net that contradicts its datasheet. Every footprint matches its land pattern within the tolerances below, and every JLC placement lands pad for pad.

| Part | Refs | Result | Datasheet (cited) | Evidence | Finding / note |
|---|---|---|---|---|---|
| RP2040 (C2040) | U1 | PASS | RP2040 Datasheet: 5.2.2.2 pin list, 1.4.3 GPIO functions, 5.1.1 footprint | All 57 pads. The firmware GPIOs land on the right package pins: I2C0 on GPIO8/9 (F3), UART0 on GPIO28/29 (F2), ADC0/1 on GPIO26/27. TESTEN is on GND, USB_DP/DM go through 27 Ω (R3/R4), XOUT goes through R10 1 k, QSPI_SS has the R7 pull-up. Land: 0.20 × 0.875 pads on 0.40 mm pitch, centres 6.875 mm apart (exactly (7.75 + 6.00) / 2), ePad 3.20 | — |
| GD25Q16ESIGR (C2922792) | U2 | PASS | GigaDevice GD25Q16E Rev 1.1: Table 1 (p.5); section 9 ordering "S: SOP8 208mil"; 10.2 package | The pin map matches the RP2040 QSPI SDn → IOn wiring. The "S" package code is 208 mil, matching the 5.3 mm footprint and the LCSC record (SOP-8_L5.3). The pads (2.775–4.40 mm from centre) cover the lead foot (3.10–4.05 mm worst case) | — |
| AP2112K-3.3 (C51118) | U3, U15 | PASS | Diodes DS39724 Rev 2-2: Pin Descriptions (SOT25); suggested pad layout | Pin 1 VIN, 2 GND, 3 EN (tied to VIN), 4 NC (open), 5 VOUT on both regulators | Board pads are 1.325 long against 0.80 suggested, extending inward; not gross |
| OPA197IDBVR (C221351) | U5 | PASS | TI SBOS737C: DBV pinout and Pin Functions (p.3–4); DBV0005A land pattern | OUT 1, V− 2, +IN 3, −IN 4, V+ 5 match design.json kind "OPA810" by name. Supplies ±12 V | — |
| OPA2810IDGKR (C2864204) | U6, U7 | PASS | TI SBOS789C: Pin Functions (p.3); DGK0008A land pattern | Both amplifiers on both parts: U6A unity-gain source driver, U6B / U7B followers, U7A TIA with +IN on GND | — |
| TPS7A4901DGNR (C16430) | U11 | PASS | TI SBVS121E: Pin Functions (p.4); DGN0008D land pattern | DNC (pin 7) and NC (pin 3) open. EN on IN is allowed. PowerPAD on GND ("left open or tied to ground"). EP 1.57 × 1.89 exact | — |
| TPS7A3001DGNR (C33835) | U12 | PASS | TI SBVS125D: Pin Functions (p.4) | Same as U11 for the negative regulator. PowerPAD on GND is allowed ("left open or tied to GND"), not IN | — |
| TPS65131RGER (C87663) | U13 | PASS | TI SLVS493E: Figure 5-1, Table 5-1 (p.3); RGE0024B land pattern | All 25 pads checked. PSP/PSN on GND (forced PWM). BSW open. NC pins 12 and 20 open. VREF has C84 220 nF and R84, as Table 5-1 asks. Thermal pad on GND. EP 2.45 exact | Pads run 0.175 mm further out than TI's (same inner edge); not gross |
| TAC5112IRGER (C44853692) | U14 | PASS | TI SLASF24A: Table 5-1 (p.4–6); RGE0024R land pattern | All 29 pads, including corner pads A1–A4 on VSS at the TI positions (±1.725 mm, 0.25 mm square). ADDR on GND (address 0x50, as the firmware expects). Land matches TI exactly (0.6 × 0.24, 3.8 mm, EP 2.1) | — |
| TPS2553DBVR (C55266) | U16 | PASS | TI SLVS841G (Oct 2026; same table as rev F): Table 5-1 | IN 1 and EN 3 on VBUS: correct only because the TPS2553 enable is active-high, and BOM, design and LCSC record all say TPS2553. ILIM pin 5 has R110. FAULT is open drain, left open | — |
| LM3880MF-1AA (C486059) | U17 | PASS | TI SNVS451M: Pin Functions (p.3), 6.5 IEN 7 µA, 8.2.1 sequence 1-2-3 | FLAG1 (first) drives ENP, FLAG2 drives ENN, FLAG3 open. EN carries only C116, which the internal 7 µA pull-up charges | — |
| SRV05-4, R+O second source (C7420376) | D1 | PASS | Hongjiacheng SRV05-4 Rev 2.1: p.1 function diagram; p.3 pad layout | This is the LCSC part's own datasheet, not Semtech's. Pin 5 is the rail (USB_VBUS), pin 2 GND, pins 1, 3, 4, 6 I/O (D+ / D−) | — |
| BAT54S, R+O second source (C7420333) | D11–D14 | PASS | Hongjiacheng "BAT54 THRU BAT54S" Rev 2.0: p.1 function diagram (read at 600 dpi); p.3 pad layout | Pin 1 = anode 1 on GND, pin 2 = cathode 2 on 3V3A, pin 3 = common on the clamp node | The LCSC/EasyEDA symbol labels the pins "1 K1, 2 K2, 3 A", which is a BAT54A pinout. That symbol is wrong; the datasheet and the board agree. JLC places by pad geometry, which matches |
| AO3400A (C20917) | Q2–Q6 | PASS | AOS AO3400A Rev 3: p.1 top view | Gate 1 is on the gate net, source 2 on GND, drain 3 on the coil minus side. The sheet prints no pin numbers; the pin-1 dot is at G, which gives the JEDEC SOT-23 order. The LCSC symbol agrees | — |
| SS14, MDD (C2480) | D2, D3 | PASS | MDD Rev 2025A3: polarity "band denotes cathode"; suggested pad layout | Boost diode: cathode on RAW_P. Inverter diode: cathode on SW_N. JLC places cathode on cathode | KiCad pads run 0.45 mm further in and out than MDD's; not gross |
| 1N4148WS, CJ (C2128) | D5–D9 | PASS | CJ BAV16WS/1N4148WS (A, May 2011) | Cathodes on VRLY and anodes on the drains (flyback). The EasyEDA cathode pad and silk bar land on board pad 1 | No land pattern in this sheet |
| KT-0603R (C2286) | D15–D20 | PASS | KENTO KT-0603R Rev A.0: p.2 package and pads | KENTO and EasyEDA call the anode pin 1; KiCad calls the cathode pad 1. The JLC check maps vendor pin 2 (cathode) to board pad 1: the cathode lands on GND (on LED_N12 for D18, which is reversed on purpose) | — |
| LTST-S270KFKT (C160472) | D4 | NOTE | Lite-On DS22-2000-209 Rev E: p.1, suggested lands 1.1 × 1.1 mm with a 0.9 mm gap | Land is exact. Cathode on GND. JLC pad 1 lands on pad 1 | D4 is not among the parts the 2026-10-30 preview passed. Check lens direction and cathode in the final preview |
| ABM8-272-T3 (C20625731) | Y1 | NOTE | Abracon drawing 456603 rev IR: p.2 | Crystal on pads 1 and 3 (diagonal) to XIN and XTAL_OUT, lid pads 2 and 4 on GND. Land 1.4 × 1.2 at 2.2 mm | The datasheet says the chamfer may be on pin 1, 3 or 4. A 90° placement would put the crystal across the two GND pads, so check pad 1 by geometry in the preview |
| TYPE-C-31-M-12 (C165948) | J1 | PASS | HRO drawing (2020-12-08): pin table and recommended PCB layout | All 16 contact positions match the drawing within 0.00 mm, in HRO's order. CC1 and CC2 each have a 5.1 k pull-down (R1, R2). D+ and D− are joined across both rows. SBU open, shell on GND | — |
| TQ2SA-L2-5V-Z (C2684450) | K1–K4 | NOTE | Panasonic ASCTB14E 201911, p.11: SA-type pad, 2-coil latching schematic (top view, reset condition) | Land is exact: 1.0 × 2.94 mm pads, 2.54 pitch, 9.56 mm between rows. Pin 1 matches the "SA" drawing. Coil "+" pins 1 and 10 are on VRLY; pins 5 and 6 go to the drivers. The range resistor sits on NO pins 4 and 7, which close only after SET (reset condition: 3-2 and 8-9 closed) | Panasonic does not label which coil is SET; it draws the 1–5 coil open and the 6–10 coil filled. The board, like prior audit RC-03, takes 1–5 as SET. If that is wrong, nothing is damaged and firmware can work around it: pulse the shared RESET line to set all four relays, then the per-relay lines to drop the unwanted ones. Bring-up: pulse RNG_SET_LO alone and check SOURCE_BUF–RG100 continuity |
| BNC-KYWE-295-W4-N (C41416668) | J3, J7–J9 | PASS | SAMZO BNCKYWE-P03900 rev A1 | Legs on the 8 × 8 mm square, centre pin at the centre: position error 0.00 mm. Shell on GND | Fitted by hand. Holes are 1.4 mm against 1.2 mm drawn, which is loose but fits (prior audit RC-11) |
| FNR5040S4R7MT (C167963) | L1, L2 | PASS | Changjiang FNR catalog: FNR5040S row, Fig.3 land | 1.4 × 4.2 mm pads at 3.7 mm (a 2.3 + b 1.4), exact | — |
| GZ2012D101TF (C1015) | FB1 | NOTE | none retrieved | Non-polar 0805 ferrite between 5V and 5VA | No primary datasheet: the LCSC/JLC links return an HTML page. Checked against the LCSC package and EasyEDA land only |
| TS-1088-AR02016 (C720477) | SW1, SW2 | PASS | XunPu drawing REV A | 1.05 × 2.0 mm pads at 4.45 mm (5.50 outer, 3.40 inner), exact. BOOTSEL through R8 1 k to QSPI_CS; RESET on RUN | — |
| PCG1A331MCL1GS (C433208) | C117 | NOTE | Nichicon PCG catalog excerpt (2 pp.) | Pad 1 (+) on 5V. The EasyEDA "+" pad lands on pad 1 | Nichicon's land-size pages (18–19) are not in the LCSC excerpt. Land checked against the EasyEDA record only (6.95 vs 6.53 mm between pad centres) |
| TSW-102-07-G-S, DNP (C7402729) | J4–J6 | PASS | Samtec F-224 | Net sanity: SWCLK/SWDIO go to RP2040 pins 24/25, UART_TX/RX to GPIO28/29 | Not fitted |

Tolerances, chosen to flag gross errors, not IPC fillet detail:

- pitch ±0.03 mm;
- row span between pad centres ±0.5 mm (±0.25 mm for QFNs, tighter where the footprint copies the drawing);
- pad size 0.6–2× the datasheet value;
- exposed pad ±0.06 mm;
- absolute positions ±0.02 mm;
- JLC pad landing within 0.4 mm.

## Not verified

- **Gaps in the sources:**
  - The GZ2012D101TF datasheet was not retrieved.
  - The Nichicon PCG land-pattern pages were not retrieved.
  - The AOS AO3400A sheet prints no pin numbers.
  - The 1N4148WS sheet gives no land pattern.
- **TQ2SA SET/RESET coil:** identified from Panasonic's drawing convention, not from a printed label.
- **Physical orientation on the reel:** the JLC check proves that JLC's own library footprint, at the CPL angle, lands on the right pads. It cannot prove that JLC's library footprint matches the physical part on the reel. The placement preview remains the last check, especially for D4 and Y1.
