# Rev G100 order package review (2026-11-15)

Reviewed at commit 7c7b8a479, board SHA-256 `49ba0a39…d716` (matches the handoff). Everything here was run from `instruments/lcr-meter`; scripts and outputs are in this folder. Nothing outside this folder was changed, nothing was uploaded, and JLC was only queried through its public part search and help pages.

## Verdict: ORDER AFTER SMALL FIXES

The files to upload are right. The fixes are all to the instructions (handoff, bring-up) plus one stock action. No board, BOM or CPL change is needed.

"Verified" below means I ran it or read it at the cited place. "Believed" means my experience of JLC orders, not something I could check signed out.

## Findings, by severity

### 1. HIGH: the edge-rail step does not fit an Economic order, and JLC will drill tooling holes where it chooses

- **Verified.** The handoff asks for both "Edge rails added by JLCPCB" (step 2, `docs/rev-g100-handoff.md:79`) and "Economic … tooling holes by JLCPCB" (step 3, line 81). JLC's own help pages (both "Last updated on Sep 09, 2026", fetched today) say:
  - "Edge rails and fiducials are required for **standard** PCB assembly" (`/help/article/How-to-add-edge-rails-fiducials-for-PCB-assembly-order`);
  - "For **Economic** PCBA type, tooling holes are a must … Two or three tooling holes … in opposite corners … 1.152 mm round non-plated … If there is no enough room, you can add them to the copper area … JLC will help to add the tooling holes by default" (`/help/article/How-to-add-tooling-holes-for-PCB-assembly-order`);
  - "for Economic assembly, please panelize your boards with mouse-bites; for Standard assembly … mouse-bites or V-cut" (`/help/article/pcb-assembly-faqs`, item 11).
- **Verified.** The only real pass through this flow agrees: the Rev F quote of 2026-10-30 records "Economic … tooling holes added by JLCPCB", a "Panel 0.00" line and no rails (`manufacturing/fab-quote.json`, `assembly_quote.options`), and the Rev F handoff says "Not yet priced; the 2026-10-30 quote had no rails" (`docs/rev-f-handoff.md:34`). The G100 handoff dropped that caveat.
- **Verified.** `FABRICATION.md:63` ("Every edge has SMT copper within 2 mm, so JLC's line needs rails") is stated as fact, with no JLC source for the Economic line.
- **Verified** (`tooling_spots.py` → `tooling-spots.txt`). No corner has a bare-laminate spot for a 1.152 mm hole. Three corners have a spot through GND fill only: near (51.5, 46.5), (148.5, 50.0) and (144.0, 137.0) in board coordinates. The back-left corner (USB-C side) has none within 22 mm.
- **What goes wrong.** Either the owner cannot find the option and stalls; or switches to Standard to get it (the package's own estimate: $507.29 against $397.96); or stays Economic and JLC's CAM engineer picks the hole positions on a board with no empty corner.
- **Fix (10 minutes, no board change).** Rewrite step 2:
  1. Stay on Economic, "Tooling holes: Added by JLCPCB".
  2. PCB remark: *"Tooling holes: please place them only through GND copper pour, away from all tracks; suggested positions X 1.5 Y 98.5 mm, X 98.5 Y 95.0 mm and X 94.0 Y 8.0 mm from the lower-left corner. If you prefer edge rails instead, add them on the left and right edges only (the edges perpendicular to the BNC edge), never on the BNC edge or the opposite edge."*
  3. Select "Confirm production file: Yes" on the PCB form, and look at the holes before approving (believed: the option exists on the PCB quote form and costs time, not money).
- **Cleaner alternative, if a board edit is acceptable:** put three 1.152 mm NPTH holes (0.148 mm mask expansion) at those spots and order "Added by Customer". It needs the gates rerun and a look from a reviewer, so I would not do it for this order.

### 2. HIGH, time-sensitive: relay stock fell 84 % in five days

- **Verified** (`live_stock.py` → `live-stock.txt`, JLC part search today against the 2026-11-10 snapshot):

  | Part | Need | 2026-11-10 | 2026-11-15 | × need |
  |---|---|---|---|---|
  | TQ2SA-L2-5V-Z (C2684450), K1–K4 | 20 | 1,269 | **209** | 10 |
  | TAC5112IRGER (C44853692) | 5 | 83 | 73 | 15 |
  | OPA2810IDGKR (C2864204) | 10 | 170 | 168 | 17 |
  | TPS65131RGER (C87663) | 5 | 755 | **187** | 37 |
  | LM3880MF-1AA (C486059) | 5 | 388 | 245 | 49 |
  | ABM8-272-T3 (C20625731) | 5 | 850 | 368 | 74 |
  | BNC (C41416668) | 20 | 267 | 639 | 32 |

- The handoff's table still says the relay is "slowly falling" (`rev-g100-handoff.md:60`). The relay is the part the handoff forbids substituting, and its planned replacement has 0 stock.
- All 81 codes still resolve, all are in stock for five boards, the library class of every line is unchanged (34 extended, 45 basic or preferred), and the SMT parts total moved from $239.62 to $245.38.
- **Fix.** Order within a day or two. If the order will wait longer, buy 22 relays into the JLC parts inventory now (about $45; an owner purchase). On order day rerun `manufacturing/prices/fetch_jlc_parts.py` and update the stock table.

### 3. MEDIUM: the bring-up path names the wrong firmware image, and nothing on the board says which image is running

- **Verified.** `docs/bring-up-rev-e.md` names `temper-lcr-rev-e.uf2` in the equipment list (line 11) and in §3 step 1 (line 107), and steps 6–7 reflash "the UF2" (120–121). The handoff's arrival steps run in the order "follow bring-up-rev-e.md" (step 1), then "flash `temper-lcr-rev-g.uf2`" (step 2) (`rev-g100-handoff.md:105–106`). `bring-up-rev-g.md` Part B says to flash the Rev G image "after §1–§3 pass, and before §6".
- **Verified.** §4 of bring-up-rev-e (lines 127–130) runs `refcheck` and `relaycheck` before §6. On G100 the reference sits behind the jack switches (`bring-up-rev-g.md`, Part A row "§7"). With the Rev E image the switches never close, so these checks cannot give a valid answer.
- **Verified.** Both images answer `INFO 3 E-codec`: `HARDWARE_REVISION` is one constant (`firmware-rev-e/src/pins.h:4`, printed at `src/main.c:447`). The host has no jack command: `strings host/bin/temper-lcr-macos-arm64` lists 18 subcommands and none reads `JACKS`; `grep -ri jack host/src` returns nothing. Step G5 asks for `JACK_HC` / `JACK_LC` readings and does not say how to get them.
- **What goes wrong.** A person following the pages in order flashes the Rev E image, gets a relaycheck FAIL, and the G6a ladder then tells them to replace R101 and after that the relays. That is rework on a healthy board.
- **Fix (15 minutes of text).**
  1. Handoff "When boards arrive": make step 1 "flash `temper-lcr-rev-g.uf2`; wherever bring-up-rev-e.md says `temper-lcr-rev-e.uf2`, use it instead".
  2. Put the same sentence at the top of bring-up-rev-e.md §3.
  3. In G5, say how to read the jacks: open the serial port in a terminal and type `JACKS` (reply `JACKS <state> <HCUR mV> <LCUR mV>`, firmware README line 81).
  4. Better, later: report `G-codec` from the `LCR_REV_G` build and add `temper-lcr jacks PORT`. That is a firmware and host change, so it does not have to precede the order.

### 4. MEDIUM: the placement-preview list leaves out most parts that kill a board

- **Verified.** The handoff's list (`rev-g100-handoff.md:89–97`) is Y1, C117, U17, U16, U3, U15, U5, D1, K1–K4, D4, U18–U21, D28, D29 and the BNCs. Missing: U1 (RP2040), U13 (TPS65131), U14 (TAC5112), U11 / U12 (LDOs), U6 / U7, U2 (flash), D2 / D3 (the switcher diodes; reversed is a shorted converter), D5–D9 (the coil flyback diodes), Q2–Q7 and J1. It is also shorter than `FABRICATION.md:93–110`, which adds D18 and Q7. Only four parts have their expected answer written down.
- A new upload is a new preview, so the Rev F pass of 2026-10-30 does not carry over.
- **Verified, independently of the package's own audit** (`rot_check.py` → `rot-check.txt`). I took the EasyEDA / JLCEDA official-library footprint of each LCSC code (source: https://lceda.cn/, https://easyeda.com), rotated it by 0 / 90 / 180 / 270° and found the angle that puts each numbered pad on the board's pad. For all 64 keyed parts the CPL rotation is the best-fit angle, with the next angle at least 1.09 mm worse. 58 match by pad number. The six red LEDs D15–D20 (C2286) match by function: the library numbers its pads 1 = A, 2 = K, the KiCad footprint 1 = K, and the CPL puts A on the anode pad (D18 reversed on purpose, as documented). So I expect the preview to pass.
- **Verified** (`origin_check.py` → `origin-check.txt`). If JLC puts the library origin at the CPL point, every part lands within 0.30 mm except **J1, which lands 1.2 mm off** (the KiCad anchor is not the library centre). The handoff forbids the viewer's arrow buttons, so the owner needs to know this one is expected. Believed: JLC's engineers centre connectors on their pads during review.
- **Fix.** Use `preview-checklist.csv` in this folder (`preview_table.py`): 62 keyed parts, 40 marked "dead board if wrong", each with where pad 1 sits in the preview (BNC edge up, USB-C left). It agrees with the four answers FABRICATION.md gives (C117 down, U17 up-left, D4 left, U1 down-right). Add a PCBA remark: "J1 USB-C: please align to the pads".

### 5. LOW: remarks

- **Believed.** JLC has two remark fields, one read by the bare-board CAM engineer and one by assembly. The handoff does not say which remark goes where (`rev-g100-handoff.md:84–88`). Tooling holes / rails and the IPC-D-356 request belong in the PCB remark; stencil, BNC direction and J1 in the PCBA remark.
- **Verified.** The Y1 remark ("orient by pad geometry; the chamfer mark is unreliable") guards against something that cannot happen silently: the footprint is 3.2 × 2.5 mm with pads 1 / 3 crystal and 2 / 4 lid, so 0° and 180° are electrically the same, and 90° misses the pads by 1.97 mm (`rot-check.txt`, Y1). The remark is hard for an operator to act on and may cost a query. Replace it with "Y1: 0° and 180° are both correct".
- Any remark sends the order to manual review. Expect about a day.

### 6. LOW: the exposed-pad via note claims something JLC has not confirmed

- **Verified.** Fab note 4 on the drawing layer and `FABRICATION.md:39` say "JLC's plugging fills them". The package's own record says "thermal vias in the five exposed pads stay open on top under paste" and "vendor_dfm_approval: NOT PERFORMED" (`validation/rev-g100/via-in-pad-process.json`). `FABRICATION.md:37` says "Do not order POFV", while handoff step 6 calls filled-and-capped "an acceptable paid answer".
- **Believed.** The 33 vias have a mask opening on top (they are inside the pad), so JLC will leave them open or plug them from the bottom. Open 0.3 mm vias in QFN pads are routine on JLC boards: some solder comes through, the parts work. This is not a reason to hold the order.
- **Fix.** Decide the answer before JLC asks: "follow the Gerber, proceed". Do not pay for filled-and-capped on this build.

### 7. LOW: untested zip contents

- **Verified.** `temper-lcr.d356` entered the zip on 2026-11-03 (commit 797cb7678), after the last real upload on 2026-10-30, so JLC's uploader has never seen it. `temper-lcr-User_Drawings.gbr` carries the fab notes out to x = 251.9 mm, 102 mm past the board (`notes.py` → `fab-notes.txt`); it dates from 2026-10-29 (commit a89c3b974), so it was probably in the uploads that detected "100x100mm" (believed, the record does not list the zip's files).
- **Fix.** Add to step 1: if the page does not detect a 4-layer 100 × 100 mm board, delete those two files from the zip and upload again. Also record the zip hash in the handoff: `3c649f60e59c3d5d2751ef0fb89d8d7ac2e9279f3f2fec60a5b6476eef7ae19d`.

### 8. LOW: numbers that disagree

- `docs/rev-g100-plan.md` §2 gives the cost as "$400.38 economic"; the handoff and `order-estimate-5.json` give $397.96 plus $31.07.
- `bring-up-rev-g.md` G1 asks for "D21–D24 cathode on the jack centre pin"; `FABRICATION.md:108` says those TVS diodes are bidirectional, and JLC's description of C20615803 agrees ("Bidirectional", `live-describe.txt`).

### 9. Opinion: assemble two, not five

No board of this design line has ever been built (Rev A–F were never ordered), the Rev G firmware has never run, and the handoff already lists four respin items. Five identical first articles is three more than bring-up needs. The package's own estimator, run into this folder, gives $265.56 + $16.70 = **$282** for two assembled boards (five bare boards are still made) against $429 for five. It also takes the pressure off the relay stock (8 instead of 20). The cost of being wrong is paying the setup and extended-part fees (about $115) again for a second batch. I would assemble two.

## The most likely way to get five boards that don't work

A keyed part placed in the wrong rotation, because JLC's placement library disagrees with the CPL. It is the one fault that hits all five boards identically and cannot be reworked on the QFNs. Coverage is good after finding 4: the package's own EasyEDA audit, my independent check of all 64 keyed parts, and the preview with a full list.

The most likely way to *believe* the boards don't work is finding 3: the wrong image, then a relaycheck FAIL.

## Checked and found fine

- **Gerbers** (`gerber-compare.txt`). All 15 files in the zip match a fresh KiCad 10.0.4 export of the board with the commands in `cad/rebuild.sh` (dates aside), and are byte-identical to the tracked `manufacturing/gerbers/`.
- **BOM ↔ CPL ↔ board** (`consistency.py` → `consistency.txt`).
  - 282 footprints, all on top: 248 SMT, 4 through-hole BNCs, J4 DNP, 29 non-BOM (fiducials, holes, test pads).
  - 252 BOM designators = 252 CPL rows; 80 BOM lines; no duplicate designator.
  - Every CPL position equals the footprint position from the lower-left origin (0 mismatches); every LCSC code and footprint name equals the board's fields (0 mismatches); all 252 `orientation-audit.csv` rows are consistent with the board and the CPL.
  - The handoff's counts (253 / 252 / 248 + 4 / 80) are right.
- **Drill** (`manufacturing/drill-report.txt`): 461 PTH and 6 NPTH, as FABRICATION.md states.
- **JLC library today** (`live-describe.txt`): every code's manufacturer part number and package equal the BOM's.
- **Estimate.** `order_estimate.py` reproduces $397.96 and $31.07 from the committed inputs.
- **Firmware and host.** `shasum -c firmware-rev-e/verification/SHA256SUMS` passes for every source and binary; `temper-lcr-rev-g.uf2` is 416 blocks, RP2040 family (`verification/uf2.txt`); the host tests pass for the Rev G build (`verification/host-test.txt`, third line); the host binary carries `relaycheck` and is as new as the last `host/src` commit (286f4c05f).
- **Gate records** in `validation/rev-g100/` carry this board's hash: DRC 0 violations / 0 unconnected / 0 parity, fab-check pass, Gerber netlist 0 shorts / 0 opens. I read them; I did not rerun `gates.sh`, because it writes outside this folder.

## Expected cost, five boards

| Item | USD | Basis |
|---|---|---|
| Economic PCBA including bare boards | about 392 | Estimate $397.96, minus the $12.30 X-ray line that the real Rev F quote did not charge, plus $0.91 nitrogen reflow (`manufacturing/fab-quote.json`, `vs_estimate`), plus $5.76 of part price movement since 2026-11-10 |
| BNCs fitted by JLC | 31 | Estimate; this line has never been through JLC's flow |
| **Goods** | **about 423** | Range $415–440. If the order is forced to Standard: about $540 |
| Shipping, duties and tax to the US | 100–230 | Believed, not in any file: express shipping $30–50, and US import charges on Chinese assemblies that JLC collects at checkout |
| **Landed** | **about 520–650** | |

Two assembled boards instead: about $280 in goods.

## Not checked

- JLC's order form itself (signed out): the exact option names, the rail or tooling-hole price, whether the Economic flow accepts the through-hole BNC line.
- The layout copper, by instruction.
- Firmware behaviour: no board exists.
