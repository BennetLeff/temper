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
- **Gerber zip:** `manufacturing/temper-lcr-gerbers.zip`. It is gitignored; `sh validation/rev-g100/gates.sh` regenerates it, and the board above produces it. It carries the IPC-D-356 netlist `temper-lcr.d356`.
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

  The last review found the board orderable, and its fixes were re-checked clean.
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

## Stock (JLC, 2026-11-10, `validation/rev-g/prices/jlc-parts-2026-11-10.json`)

Every line is in stock for five boards. The tightest, as multiples of what the order needs:

| Part | Need | Stock | |
|---|---|---|---|
| BNC-KYWE-295-W4-N (C41416668), J3 J7 J8 J9 | 20 | 267 | 13× |
| TAC5112IRGER (C44853692), U14 | 5 | 83 | 17× |
| OPA2810IDGKR (C2864204), U6 U7 | 10 | 170 | 17× |
| TQ2SA-L2-5V-Z (C2684450), K1–K4 | 20 | 1,269 | slowly falling |
| ABM8-272-T3 (C20625731), Y1 | 5 | 850 | was 9,312 on 2026-11-09 |

If the order shows a shortfall, pre-order the part from LCSC into the JLC parts inventory. Do not substitute:
- **Y1:** R10 / C12 / C13 are tuned to this crystal (RP2040 hardware guide §2.3).
- **The relays:** the RESET margin is computed for the 5 V coil. The 4.5 V coil (C7402021) is the planned later change, and has 0 stock.

## To order

Only the owner signs in, adds to the cart or pays.

1. **PCB.** At cart.jlcpcb.com/quote, upload `manufacturing/temper-lcr-gerbers.zip`. It should detect "4 layer board of 100x100mm". Settings:
   - FR-4, qty 5, 1.6 mm, green / white, TG135, ENIG 1 µ";
   - 1 oz outer, 0.5 oz inner;
   - via covering **Plugged** (Tented is greyed out);
   - 0.3 mm minimum via;
   - flying-probe test.

   Expect about $25.70.
2. **Edge rails.** Select "Edge rails added by JLCPCB" and paste this remark: *"V-cut edge rails on the left and right edges only (the edges perpendicular to the BNC edge); no rail on the BNC edge or the opposite edge; ship depanelized or with rails, either is fine"*.
3. **Assembly.**
   - PCB Assembly: Economic, top side, qty 5, tooling holes by JLCPCB, **Confirm Parts Placement: Yes**.
   - Upload `manufacturing/bom-jlcpcb.csv` and `manufacturing/cpl-jlcpcb.csv`.
   - Expect 80 lines. The BNC line (C41416668) is through-hole, so let JLC solder it by hand. If the Economic flow refuses through-hole parts, deselect that line and solder the four BNCs yourself: 20 joints per board.
4. **Order remarks.** Add all four:
   - "Y1: orient by pad geometry; the chamfer mark is unreliable."
   - "SMT stencil 0.10–0.12 mm please (U1 is a 0.4 mm pitch QFN)."
   - "IPC-D-356 netlist temper-lcr.d356 is in the Gerber zip; please test against it."
   - "BNC J3, J7, J8, J9: the barrel points off the front board edge (the edge with the four BNC footprints)."
5. **Placement preview.** Work through the list in `manufacturing/FABRICATION.md` ("Placement-preview checks"):
   - Y1 by pad geometry;
   - C117 polarity;
   - U17, U16, U3, U15, U5, D1 rotations;
   - K1–K4 stripe;
   - D4's lens;
   - the TLP172AMs U18–U21;
   - D28, D29;
   - the BNC barrels.

   Do not use the viewer's arrow buttons: they move the selected part. If the undo arrow goes active, undo.
6. **DFM at order.** Accept JLC's review of the 33 exposed-pad thermal vias (Plugged). Filled-and-capped is an acceptable paid answer if asked.
7. **Record the result.** Put the quote and the preview outcome in `validation/rev-g100/fab-quote.json` and in the plan's status.

## When boards arrive

1. Follow [bring-up-rev-e.md](bring-up-rev-e.md), with the Rev F notes in [rev-f-handoff.md](rev-f-handoff.md) "When boards arrive". They all apply: start-up, hot-plug, relay coil identity, codec clock.
2. Flash `temper-lcr-rev-g.uf2`.
3. Then [bring-up-rev-g.md](bring-up-rev-g.md) Part B, G1–G9, including:
   - **G6a**, the relay state check at VBUS 4.40 V on a warm board. A FAIL means swapping R101 for a 0 Ω jumper first.
   - **The quiet-board step (§5):** the first measurement of the switcher pickup that G100's shrink increased by about 4 dB (relative).
4. Respin items are recorded in the plan and the third review's dispositions:
   - C9 / C15 closer;
   - EP paste windows off the vias;
   - the 0.4 mm 5V neck at U16;
   - 4.5 V-coil relays.
