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
- **Board:** `cad/temper-lcr.kicad_pcb`, SHA-256 `49ba0a39913cd1ed725b996fd5b46332ebe61ce2b02178523349e9d932ebd716`. 100 × 100 mm, 4 layers, hand-routed.
- **Gerber zip:** `manufacturing/temper-lcr-gerbers.zip`, SHA-256 `3c649f60e59c3d5d2751ef0fb89d8d7ac2e9279f3f2fec60a5b6476eef7ae19d`. It is gitignored; `sh validation/rev-g100/gates.sh` regenerates it, and the board above produces it. It carries the IPC-D-356 netlist `temper-lcr.d356`.
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
  - 253 components, 252 fitted (J4 DNP);
  - 248 SMT placements plus the four BNCs, which JLC fits by hand;
  - 80 JLC BOM lines.
- **Estimate for five boards** (`validation/rev-g100/order-estimate-5.json`, JLC prices of 2026-11-10), excluding shipping and tax:

  | Item | USD |
  |---|---|
  | Economic PCBA, including the $25.70 bare boards | 397.96 |
  | JLC hand fit of the BNCs (parts, joints, labour) | 31.07 |
  | **Total** | **429.03** |

- **Firmware:** `firmware-rev-e/bin/temper-lcr-rev-g.uf2`, the jack-guard build (`LCR_REV_G=1`). The default `temper-lcr-rev-e.uf2` never closes the jack switches, so a G100 board measures nothing with it. It has never run on a board.
- **Host:** `host/bin/temper-lcr-macos-arm64`.

## Stock (JLC, live check 2026-11-15, `../validation/rev-g100/package-review-2026-11-15/live-stock.txt`)

Every line is still in stock for five boards, but several have been falling fast. **Order soon.** If the order slips more than a day or two, buy 22 relays (C2684450) into the JLC parts inventory first, about $45.

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
| Five boards made, five assembled | $397.96 + $31.07 BNC fit = **$429.03** | 20 |
| Five boards made, **two** assembled | $265.56 + $16.70 BNC fit = **$282.26** | 8 |

The package review recommends two (`../validation/rev-g100/package-review-2026-11-15/REVIEW.md` §9):
- no board of this line has been built;
- the Rev G firmware has never run;
- four respin items are already listed.

The cost of two is paying the setup and extended-part fees (about $115) again if three more are wanted later. **The owner decides.** The estimate's $12.30 X-ray line was not charged on Rev F's real quote, so expect slightly less. Shipping and tax are extra.

## To order

Only the owner signs in, adds to the cart or pays.

1. **PCB.** At cart.jlcpcb.com/quote, upload `manufacturing/temper-lcr-gerbers.zip` (SHA-256 `3c649f60e59c3d5d2751ef0fb89d8d7ac2e9279f3f2fec60a5b6476eef7ae19d`). It should detect "4 layer board of 100x100mm".
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
   - Expect 80 lines. The BNC line (C41416668) is through-hole, so let JLC solder it by hand. If the Economic flow refuses through-hole parts, deselect that line and solder the four BNCs yourself: 20 joints per board.
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

1. **Flash `firmware-rev-e/bin/temper-lcr-rev-g.uf2` first.** Use it wherever the bring-up pages say `temper-lcr-rev-e.uf2`. The Rev E image never closes the jack switches, so `refcheck` / `relaycheck` cannot pass with it. Both images answer `INFO 3 E-codec`, so nothing on the board says which one is running.
2. Follow [bring-up-rev-e.md](bring-up-rev-e.md), with the Rev F notes in [rev-f-handoff.md](rev-f-handoff.md) "When boards arrive". They all apply: start-up, hot-plug, relay coil identity, codec clock.
3. Then [bring-up-rev-g.md](bring-up-rev-g.md) Part B, G1–G9, including:
   - **G5:** read the jack senses with `JACKS` in a serial terminal.
   - **G6a**, the relay state check at VBUS 4.40 V on a warm board. A FAIL means swapping R101 for a 0 Ω jumper first.
   - **The quiet-board step (§5):** the first measurement of the switcher pickup that G100's shrink increased by about 4 dB (relative).
4. Respin items are recorded in the plan and the third review's dispositions:
   - C9 / C15 closer;
   - EP paste windows off the vias;
   - the 0.4 mm 5V neck at U16;
   - 4.5 V-coil relays;
   - a `G-codec` identity for the Rev G image, and a host `jacks` command.
