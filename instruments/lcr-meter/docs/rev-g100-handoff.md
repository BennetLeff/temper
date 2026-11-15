# Rev G100 handoff (2026-11-10)

The owner chose Rev G100 for the first LCR meter order on 2026-11-10. It is Rev G's protected-jack circuit on Rev F's 100 × 100 mm outline. The board is design-complete and ready to order. Nothing has been ordered, and no board exists. This page says what to do next and where everything is.
- **Reasons:** [rev-g100-plan.md](rev-g100-plan.md) §5.
- **Manufacturing instructions:** [`manufacturing/FABRICATION.md`](../manufacturing/FABRICATION.md).

## What the board does

A USB-powered, four-terminal LCR meter for Temper's own parts: the coil, the pan and the resonant tank.
- **Measurement:** |Z| and phase, so R, L, C and Q, with tones up to 85 kHz.
- **Ranges:** three relay ranges (100 Ω, 5 kΩ, 100 kΩ).
- **Control:** driven end to end by the `temper-lcr` host CLI.
- **Self-checks:**
  - a source-off check on every point;
  - an internal 1 kΩ reference for drift (`refcheck`);
  - a relay state check (`relaycheck`).
- **Protected jacks:** a charged part of about 1 µF at 50 V, or 10 µF at 30 V, does not damage the front end ([rev-g-before-after.md](rev-g-before-after.md)).

## State

- **Branch:** `study/lcr-rev-g100`, worktree `worktrees/lcr-rev-g/instruments/lcr-meter`. Pushed.
- **Board:** `cad/temper-lcr.kicad_pcb`, SHA-256 `0822e8e24ff3728290f0c9bdde0be265a797a50410383ae9804c167c9cc1a4cd`. 100 × 100 mm, 4 layers, hand-routed. Since `49ba0a39…` (2026-11-10), two things changed and the copper did not: J4's DNP flag, and fab note 6 on the drawing layer, which now gives tooling holes instead of edge rails.
- **Gerber zip:** `manufacturing/temper-lcr-gerbers.zip`, SHA-256 `ac6f45a6a8af1b21a5cd7a72e03637d6f95ca536834a5cd39923aa9f26498504`. It is gitignored; `sh validation/rev-g100/gates.sh` regenerates it from the board above. A rerun changes only the creation-date lines, and so the hash: compare the files in `manufacturing/gerbers/`, not the zip hash. It carries the IPC-D-356 netlist `temper-lcr.d356`.
- **Gates** (`sh validation/rev-g100/gates.sh`):
  - pre-DRC 0 and KiCad DRC 0, 0 unconnected, ERC and schematic parity 0;
  - Gerber netlist 0 shorts / 0 opens;
  - current check 0 FAIL, including 3V3A, 5VA and the LDO inputs;
  - drive budget 17 / 17, relay coil 4.169 V in the RESET pulse at VBUS 4.40 V;
  - every other screen 0 findings;
  - the analog core is 403 / 403 identical to Rev G.
- **Reviews:**
  - a datasheet audit (`validation/datasheet-audit-rev-g100/FINDINGS.md`);
  - three independent layout reviews and two re-checks (`validation/rev-g100/independent-*.md`).

  The last review found the board orderable, and its fixes were re-checked clean. A review of this order package (`../validation/rev-g100/package-review-2026-11-15/REVIEW.md`) found the files right and the instructions needing small fixes, now applied.
- **Parts:**
  - 253 components, all fitted;
  - 248 SMT placements plus the four BNCs and J4 (the SWD header, since 2026-11-15), which JLC fits by hand;
  - 81 JLC BOM lines.
- **Estimate for five boards** (`validation/rev-g100/order-estimate-5.json`, JLC prices of 2026-11-10), excluding shipping and tax:

  | Item | USD |
  |---|---|
  | Economic PCBA, including the $25.70 bare boards | 397.96 |
  | JLC hand fit of the BNCs and J4 (parts, joints, labour) | 32.74 |
  | **Total** | **430.70** |

- **Firmware:** `firmware-rev-e/bin/temper-lcr-rev-g.uf2`, the jack-guard build (`LCR_REV_G=1`), or `temper-lcr-rev-g-375k.uf2` at 375 kHz. The default `temper-lcr-rev-e.uf2` never closes the jack switches, so a G100 board measures nothing with it. It has never run on a board.
- **Pre-mortem (2026-11-15,** `../validation/rev-g100/premortem-2026-11-15/`): order now, copper unchanged. It found a firmware bug that would have made every board look dead: the RP2040's reset pull-down held USB_SENSE low, and the firmware waited on it before starting USB. That bug and the jack-sense margin are fixed in firmware, and the bring-up steps it asked for are in [bring-up-rev-g.md](bring-up-rev-g.md), "G100 first power".
- **Host:** `host/bin/temper-lcr-macos-arm64`.

## Stock (JLC, live check 2026-11-15, `../validation/rev-g100/package-review-2026-11-15/live-stock.txt`)

Every line is still in stock for five boards, but several have been falling fast. **Order soon.** If the order slips more than a day or two, buy these into the JLC parts inventory first:
- 22 relays (C2684450), about $45;
- five Y1 crystals (C20625731), about $2. Y1 went from 675 to 0 within one day on 2026-10-30 (the Rev F quote record), and it was at 328 at 14:13 on 11-15;
- five TPS65131RGER (C87663), about $17. JLC stocks no alternate: the Q1 variants have 3 and 5.

The optimization review (`../validation/rev-g100/optimization-review-2026-11-15/`) has the live stock at 14:13 on 11-15, with drop-in alternates for the LM3880, OPA2810 and R123 / R124.

| Part | Need (5 boards) | 11-10 | **11-15** |
|---|---|---|---|
| TQ2SA-L2-5V-Z (C2684450), K1–K4 | 20 | 1,269 | **209** |
| TPS65131RGER (C87663), U13 | 5 | 755 | **187** |
| LM3880MF-1AA (C486059), U17 | 5 | 388 | 245 |
| ABM8-272-T3 (C20625731), Y1 | 5 | 850 | 368 |
| TAC5112IRGER (C44853692), U14 | 5 | 83 | 73 |
| OPA2810IDGKR (C2864204), U6 U7 | 10 | 170 | 168 |
| BNC-KYWE-295-W4-N (C41416668) | 20 | 267 | 639 |

If the order shows a shortfall, pre-order the part from LCSC into the JLC parts inventory. Do not substitute:
- **Y1:** R10 / C12 / C13 are tuned to this crystal (RP2040 hardware guide §2.3).
- **The relays:** the RESET margin is computed for the 5 V coil. The 4.5 V coil (C7402021) is the planned later change, and has 0 stock.

## How many to assemble

| Option | Cost (2026-11-10 prices) | Relays needed |
|---|---|---|
| Five boards made, five assembled | $397.96 + $32.74 hand fit = **$430.70** | 20 |
| Five boards made, **two** assembled | $265.56 + $17.36 hand fit = **$282.92** | 8 |

The package review recommends two (`../validation/rev-g100/package-review-2026-11-15/REVIEW.md` §9):
- no board of this line has been built;
- the Rev G firmware has never run;
- four respin items are already listed.

The cost of two is paying the setup and extended-part fees (about $115) again if three more are wanted later. **The owner decides.** The estimate's $12.30 X-ray line was not charged on Rev F's real quote, so expect slightly less. Against that, the estimate charges no extended-part fee on the two hand-fit lines (BNC, J4). If JLC does charge it, add about $6. Shipping and tax are extra.

## To order

Only the owner signs in, adds to the cart or pays.

1. **PCB.** At cart.jlcpcb.com/quote, upload `manufacturing/temper-lcr-gerbers.zip` (SHA-256 `ac6f45a6a8af1b21a5cd7a72e03637d6f95ca536834a5cd39923aa9f26498504`). It should detect "4 layer board of 100x100mm".
   - If it does not, delete `temper-lcr.d356` and `temper-lcr-User_Drawings.gbr` from a copy of the zip and upload that. JLC's uploader has not seen the netlist file, and the drawing layer extends past the board.
   - Settings:
     - FR-4, qty 5, 1.6 mm, green / white, TG135, ENIG 1 µ";
     - 1 oz outer, 0.5 oz inner;
     - via covering **Plugged** (Tented is greyed out);
     - 0.3 mm minimum via;
     - flying-probe test;
     - **Confirm production file: Yes**, if the form offers it, so you can see where the tooling holes go before production.

   Expect about $25.70.
2. **Tooling holes, not edge rails.** JLC's help pages say edge rails are for Standard assembly, while Economic needs two or three 1.152 mm tooling holes, which JLC adds. No corner of this board is free of copper. So:
   - stay on **Economic**, with "Tooling holes: Added by JLCPCB";
   - put the tooling-hole text below in the **PCB remark**.

   If the form only allows Standard with rails, Standard costs about $507 for five; prefer Economic with the remark.
3. **Assembly.**
   - PCB Assembly: Economic, top side, **Confirm Parts Placement: Yes**.
   - Quantity: 5, or 2 (see above).
   - Upload `manufacturing/bom-jlcpcb.csv` and `manufacturing/cpl-jlcpcb.csv`.
   - Expect 81 lines. The BNC line (C41416668) and J4's header (C7402729) are through-hole, so let JLC solder them by hand. If the Economic flow refuses through-hole parts, deselect those lines and solder them yourself: 22 joints per board (J4 can wait until a board needs SWD).
4. **Remarks.** Any remark sends the order to a manual review (about a day).
   - **PCB remark:**
     - *"Tooling holes: please place them only through GND copper pour, away from all tracks; suggested positions X 1.5 Y 98.5 mm, X 98.5 Y 95.0 mm and X 94.0 Y 8.0 mm from the lower-left corner. If you prefer edge rails instead, add them on the left and right edges only (the edges perpendicular to the BNC edge), never on the BNC edge or the opposite edge."*
     - *"IPC-D-356 netlist temper-lcr.d356 is in the Gerber zip; please test against it."*
   - **PCBA remark:**
     - *"SMT stencil 0.10–0.12 mm please (U1 is a 0.4 mm pitch QFN)."*
     - *"Y1: 0° and 180° are both correct."*
     - *"J1 USB-C: please align to its pads."*
     - *"BNC J3, J7, J8, J9: the barrel points off the front board edge (the edge with the four BNC footprints)."*
5. **Placement preview.** Check every row of `manufacturing/preview-checklist.csv`: 62 keyed parts, 40 marked "dead board if wrong". It says where pad 1 should sit with the BNC edge up and the USB-C connector on the left. An independent check found every CPL rotation correct against JLC's library, so expect it to pass.
   - Also check the BNC barrels and D4's lens toward the front edge.
   - **J1 is expected to show about 1.2 mm off its pads** (footprint anchor against library origin). The remark covers it.
   - Do not use the viewer's arrow buttons: they move the selected part. If the undo arrow goes active, undo.
6. **Exposed-pad vias.** If JLC asks about the 33 thermal vias in the exposed pads, answer **"follow the Gerber, proceed"**. Do not pay for filled-and-capped on this build: open 0.3 mm vias in QFN pads are routine.
7. **Record the result.** Put the quote and the preview outcome in `validation/rev-g100/fab-quote.json` and in the plan's status.

## When boards arrive

1. **Start with [bring-up-rev-g.md](bring-up-rev-g.md), "G100 first power", on board 1:** have a debug probe ready on J4 (JLC fits the header), scope C60 on the first blank power-up, and put nothing on the jacks until `INFO` says PASS. It also has the G100 test-pad table and the spares to buy now.
   - **Flash `firmware-rev-e/bin/temper-lcr-rev-g.uf2`.** Use it wherever the bring-up pages say `temper-lcr-rev-e.uf2`. The Rev E image never closes the jack switches, so `refcheck` / `relaycheck` cannot pass with it. Type `BUILD` to see which image is running: `INFO` says `E-codec` in all of them.
2. Follow [bring-up-rev-e.md](bring-up-rev-e.md), with the Rev F notes in [rev-f-handoff.md](rev-f-handoff.md) "When boards arrive". They all apply: start-up, hot-plug, relay coil identity, codec clock.
3. Then [bring-up-rev-g.md](bring-up-rev-g.md) Part B, G1–G9, including:
   - **G2 / G4:** `JACKS FORCE 1` turns the switches on for the measurement, and `JACKS FORCE 0` turns them off.
   - **G5:** read the jack senses with `JACKS` in a serial terminal, including LCUR's zero.
   - **G6a**, the relay state check at VBUS 4.40 V on a warm board. A FAIL means swapping R101 for a 0 Ω jumper first.
   - **The quiet-board step (§5):** the first measurement of the switcher pickup that G100's shrink increased by about 4 dB (relative).
4. Respin items are recorded in the plan and the third review's dispositions:
   - C9 / C15 closer;
   - EP paste windows off the vias;
   - the 0.4 mm 5V neck at U16;
   - 4.5 V-coil relays;
   - a host `jacks` command (the firmware's `BUILD` now names the image);
   - the pre-mortem's trades: the Schottky 3V3A → 3V3, UART and trigger pads, and snubber lands;
   - the optimization review's parts savings: C39 / C40 / C44 / C45 / C48 / C49 to the basic X5R (C377773) after a DC-bias check; R94 to 1 %; the ten 10 µF 1210 capacitors to a 1206 land with C13585. Together they save about $16 per five boards.
