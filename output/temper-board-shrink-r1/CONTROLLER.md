# Controller board shrink study (r1)

Read-only study, 2026-10-27. Question: how small can the C49 controller board be?
No build, router or autorouter was run. Nothing in the controller or enclosure was changed.

**Short answer.**
- The board is 206 × 76 mm. Its parts' courtyards cover only **25.6 %** of it.
- The outline came from an enclosure allocation made before the circuit existed. Circuit density did not set it.
- The same circuit fits in about **131 × 76 mm** on one side. Keep today's left part of the outline, X−38…93 (option A-cut below). That needs 41 % courtyard utilisation.
- Double-sided assembly would allow about 84–102 × 76 mm.
- **80 × 60 mm is not credible.** It needs 87 % utilisation on one side or 54–57 % per side double-sided. A packed layout of this mixed-signal board reaches 35–45 %.
- A smaller board saves at most about USD 7 per board, the whole bare-PCB price today. Parts cost USD 65 per board.
- The real cost is a full re-layout and re-routing, plus an enclosure re-landing of 4 harnesses.

## Sources and how to re-run

Short names used below:
- `C/` = `/Users/bennet/Desktop/temper/worktrees/ctrl-j13/zapote/controller` (branch `controller-j13-merge`, C49).
- `E/` = `/Users/bennet/Desktop/temper/output/temper-manufacturing-r43/design`.
- `PS/` = `/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v`.

| Script (in `scripts/`) | Reads | Writes (in `results/`) |
|---|---|---|
| `kicad_courtyard.py` | library: S-expression reader, courtyard polygons, outline, zones | — |
| `measure_controller.py` | `C/pcb/controller.kicad_pcb`. Its sha256 `b3af25b8…` equals the C49 board in `C/ORDER.md` | `controller-area.json` |
| `measure_native21_selv.py` | s53 board `worktrees/runs-native21/s53/c53int/section.kicad_pcb`. Its sha256 `82af7bd9…` equals the s53 packet. Also reads `PS/audit.rs` SELV_NETS | `native21-selv.json` |
| `shrink_options.py` | the two JSONs, the C49 board, KiCad 10 library courtyards | `shrink-options.json` (**estimates**) |

Run from this folder, standard-library Python only, in this order:

```
python3 -I scripts/measure_controller.py
python3 -I scripts/measure_native21_selv.py
python3 -I scripts/shrink_options.py
```

How courtyards are counted:
- **Courtyard area** is the closed F.CrtYd/B.CrtYd outline of each footprint. Every footprint had one, so no bounding-box fallback was used.
- The THT connectors' courtyards cover the body only. J4's plug overhangs the left edge and is not counted.

## 1. Measured: how full is the board?

`results/controller-area.json`:

| Quantity | Value |
|---|---|
| Outline | 206.0 × 76.0 mm = 15 656 mm², 4 layers |
| Placements | 289 footprints. CPL: 288 placed, 279 SMD / 9 THT; J11 is a copper-only land. All on the top side |
| Support holes | 6 × Ø4.0 mm, each with a Ø8 keep-out (301.6 mm² in total) |
| Sum of courtyards | **4 006 mm²** |
| Utilisation | **25.6 %** of the board; 26.1 % of the board less the Ø8 keep-outs |
| Package mix | 202 × 0603 (873 mm²), 5 × 0805 (33), 12 × 1206 (126), 70 others (2 973) |

### By functional block

- Blocks are assigned by atopile instance path; the rules are in `measure_controller.py` `BLOCKS`.
- **Hull density** is the block's courtyard area divided by the convex hull of its placed parts.
- Hull density is meaningful only for blocks placed as one cluster. Blocks marked *spread* sit beside the connector or pin they serve, all over the board.

| Block | Parts | Courtyard mm² | Share | Hull density |
|---|---|---|---|---|
| Connectors J1–J13 (J4 383, J7 225, J3 90, J13 84, J9/J10/J12 74 each, J1/J2 57 each, J11 land 45) | 10 | 1 162 | 29.0 % | *spread* |
| MCU: ESP32-S3-WROOM-1U (368) + decoupling, EN RC, pull-ups | 8 | 401 | 10.0 % | 38 % |
| Blower buck U2/L2, PS3 bulk, speed, FAN_OFF, BLW_PG, tach, D9 | 27 | 424 | 10.6 % | 21 % |
| RTD front end (MAX31865, REF2025, windows, TPS389001, CR-1 filter) | 50 | 328 | 8.2 % | 25 % |
| Interlock (latch, watchdog, aggregate) + PERMIT gate | 27 | 308 | 7.7 % | 17 % |
| 3.3 V buck U1/L1 | 14 | 193 | 4.8 % | **57 %** |
| Tank RMS: AD8436 + MCP3202 | 18 | 192 | 4.8 % | **49 %** |
| Trip glue: rail window, read-back buffer, runaway / rim trips | 23 | 189 | 4.7 % | *spread* |
| Thermal-sense trip comparators | 24 | 152 | 3.8 % | 25 % |
| NTC / M12 / rim front ends | 25 | 149 | 3.7 % | *spread* |
| D-11 bus receiver + ct_mon buffer | 17 | 147 | 3.7 % | *spread* |
| C39 capacitive-mode detector | 14 | 129 | 3.2 % | **45 %** |
| UI bus support (2 × SRV05-4, 6 × 100 Ω, +5 V LDO) | 15 | 100 | 2.5 % | 20 % |
| Expander TCA9555 | 4 | 76 | 1.9 % | (4 parts) |
| J4 interface (PWM series / pull-downs, ZC, BIAS_GOOD) | 13 | 56 | 1.4 % | *spread* |

What the table shows:
- Connectors plus the module are 39 % of all courtyard area. The circuit itself is small.
- The tightly placed clusters (3.3 V buck, AD8436, C39 detector) reach 45–57 % hull density.
- The blocks given room on purpose sit at 17–25 %. They are the interlock, RTD and thermal-sense blocks, where `C/ENCLOSURE-HANDOFF.md:63-75` asks for their own region and short traces.

## 2. What sets today's outline

| Constraint | Effect on the outline | Source |
|---|---|---|
| **Enclosure allocation made before the design existed.** R18/R19 reserved a 210 × 80 mm envelope (X−170…40, Y12…92) for the controller **plus** the standalone interlock (100 × 65) and thermal-sense (100 × 45) boards. R20 merged the three into one board and kept the space as 206 × 76 | Sets both dimensions | `E/r19/CONTROLLER-SPEC.md:5-7`; `E/r20/DECISIONS.md:49-63` ("Board: 206 × 76 × 1.6 mm") |
| R31 restates it: "R20 fixes its outline … so the board can be laid out to fit" | The layout fills the outline; nothing tried to shrink it | `E/r31/CONTROLLER-SPEC.md:3`; `C/LAYOUT.md:123` ("Fixed by the enclosure") |
| Fixed connector landings span the board. J4 sits on the left edge (body X−38…−24.3). J9 −33, J2 −20, J7 box X29.8–62.2, J1 55, J13 88, J12 126, J10 139, J3 152 (rear row Y≈86) | The landing courtyards alone span 197 mm in X (J4 body X−38 to J3 body X158.7) | `C/layout/world.py:60-85`; checked by `C/layout/check_layout.py` (`C/LAYOUT.md:224-231`) |
| WROOM-1U fixed on the R33 box X141–159, Y50–69.5 | Holds the right end | `C/layout/world.py:87-97`; DECISIONS C26 (`C/DECISIONS.md:187`) |
| Six snap-in holes at the R31 positions, X−34…164, Y18…86 | Holds all four corners. Each Ø8 keep-out is 50 mm² of dead area | `C/layout/world.py:51-56`; C24/C25 (`C/DECISIONS.md:172, 178`) |
| Height: 15.4 mm above the board (Z40); J13 has a local Z54 allowance within ±6 mm of (88, 86) | Not an outline driver. It pins J13 to its spot | `C/layout/world.py:44-49`; `C/DECISIONS.md:376` |
| R43 J13 barrier: a panel in the 6.4 mm strip between the controller's rear edge (Y90) and native-21, 2.20 mm from J13 | Pins the rear edge and J13 | `E/r43/DECISIONS.md:24-31` |
| Analog partition: L2 (blower buck) at least 10 mm from the RTD front end; a keep-apart band; one ground plane, so the partition is by placement | Needs about 10 mm of space, not board length | `C/ENCLOSURE-HANDOFF.md:74-75`; `C/layout/floorplan.py:251-257`; `C/LAYOUT.md:90, 148` |
| Interlock box is a router keep-out for MCU nets; RUN_EN runs 208.6 mm because the module is at the far right and J4 at the far left | A cost of the long outline, not a cause of it | `C/LAYOUT.md:161, 165-169` |
| **ESP32 antenna keep-out: none since R33.** U.FL to an off-board chip antenna on 150 mm coax; only a 3 mm clear circle round the U.FL. The module was behind the lens window only in R31 (C25), with Espressif's keep-out | Not a driver now | `C/DECISIONS.md:180, 187`; `C/layout/world.py:91-97` |
| **Creepage: none.** SELV 15 V max. Clearance is 0.15 mm (0.20 mm thermal class and selv_gnd–v3v3) | Not a driver | `C/LAYOUT.md:98-99`; `C/layout/floorplan.py:160` |
| Blower-buck heat: IC up to 0.91 W. Tj at 60 °C ambient is 96.6 °C (typ, JEDEC 112.2 °C/W) and 115.1 °C (max, TI EVM 60.2 °C/W) | Needs EVM-like copper round U2 (keep the cluster). Not a length driver | `C/tools/controller_calcs.py:453, 489-490, 507-510`; `C/evidence/controller_calcs.json` `blower_supply` |

**Verdict on the hypothesis:**
- **Confirmed:** the enclosure sets the outline, not circuit density. The outline is a space allocation; the fixed landings and holes then spread over it.
- **Two corrections:**
  - The ESP32 is no longer behind the lens. It is at the right since R33, with an off-board antenna and no keep-out.
  - 80 × 60 mm is too small for this circuit (section 3).

**Parts that exist because of the enclosure split.** They stay in every option below unless the architecture changes:
- J4 right-angle Micro-Fit (383 mm²), because the controller and power board are separate.
- J7 plus the UI-bus ESD, series parts and +5 V LDO (325 mm²), because the UI is a fascia board on a 120 mm jumper (C26).
- J13, D9 and the BLW_PG divider (J13 84 + D9 24.5 mm², plus two 0603), because PS3 is chassis-mounted (C33, C49).
- The six Ø8 support keep-outs (302 mm²).

## 3. Shrink options (ESTIMATES)

**How the area is estimated** (`results/shrink-options.json`; method in the `shrink_options.py` docstring):
- Required area = courtyard area ÷ u + support-hole keep-outs. A small board keeps 4 holes.
- **u** is the board-level courtyard utilisation a packed layout reaches. I bracket it at **0.35 / 0.40 / 0.45**, not the 40–60 % sometimes quoted. Three reasons:
  - **The router.** This board is 25.6 %, and its in-house router closes the C49 netlist on only 1 of 3 clean runs (`C/DECISIONS.md:726`). Density is already at the router's edge.
  - **Local packing.** This board's tightest clusters reach 45–57 % *locally*, with no routing between blocks (section 1). A whole board, with its inter-block buses, lands below that.
  - **Fixed spacing.** Four analog front ends, a 10 mm L2–RTD gap, the interlock keep-out box and the module's escape channels (`C/layout/floorplan.py:251-257`) all need space a pure digital board would not.
- Outlines are areas shown as shapes, not layouts.

| Option | Area mm² (u = .35 / .40 / .45) | Outline at 76 mm depth (u = .35 / .40 / .45) | 4:3 at u = .40 |
|---|---|---|---|
| Today | 15 656 (u = 0.256) | 206 × 76 | — |
| **A** single-sided, 4-layer, same parts, landings moved to suit | 11 646 / 10 215 / 9 103 | 153 / 134 / 120 × 76 | 117 × 88 |
| **A+D** as A with the part swaps of D | 10 331 / 9 065 / 8 080 | 136 / 119 / 106 × 76 | 110 × 83 |
| **B** double-sided (top 2 638 / bottom 1 367 mm²) | 7 739 / 6 797 / 6 064 | 102 / 89 / 80 × 76 | 95 × 71 |
| **B+D** double-sided with swaps (top 2 468 / bottom 1 078) | 7 251 / 6 370 / 5 684 | 95 / 84 / 75 × 76 | 92 × 69 |
| 80 × 60 (the hypothesis) | 4 800 | needs u = 0.87 (A), 0.77 (A+D), 0.57 (B), 0.54 (B+D) | — |

### A-cut (recommended form of A): keep the left 131 mm of today's board

The new outline is X−38…93, Y14…90. That is **131 × 76 mm**, 9 956 mm² (`shrink-options.json` `recommended_left_cut`).

What stays where it is:
- **Landings:** J4, J9, J2, J1, J7 and J13.
- **Support holes:** four of today's six, (−34, 18), (−26, 74), (65, 18) and (75, 86).
- **Edges:** the left, front and rear edges.
- **Enclosure items that depend on these:** the J4 harness and native-21's J4, the J7 UI jumper, the coil and sink NTC drops, the M12 lead, and R43's J13 barrier and tie.

What moves into the board:
- J3 and J12 (the cartridge cable);
- J10 (blower);
- the module and its U.FL;
- the J11 land.

The two right-hand holes (164, 18) and (164, 80) go.

Utilisation needed:
- 41.1 % as-is;
- 38.1 % with 0402 for the controller's own passives;
- 36.3 % with every D swap.

That is inside the band, about 1.6 × today's density.

### Option A / A-cut: single-sided, re-landed connectors

- **Pigtails are not needed.** The moved connectors are rear-edge or top-entry cable landings. Their cables re-route in the enclosure to the new spots. A pigtail would add a hand-made harness and two contacts per line. The owner wants JLC to assemble everything possible.
- **Breaks (enclosure):**
  - a new enclosure revision moves the J3, J12 and J10 landings and the U.FL. Check that the 150 mm coax still reaches the antenna carrier;
  - two support holes and their spot-faced base holes go;
  - the R28 rule "every SELV cable ends on its plug" (`E/r43/HANDOFF.md:36`) must be re-run for the three moved cables.
- **Breaks (controller):**
  - `world.py` and `floorplan.py` are rewritten;
  - `check_layout.py`'s 14 checks are re-pointed;
  - `controller_calcs.py landings()` is re-run;
  - the RTD stitching region (`floorplan.py` RTD_STITCH) moves;
  - the block validators are re-run;
  - all 288 CPL placements move, so the rotation audit and JLC preview are redone (C50 took two preview passes).
- **Unchanged:** `verify_controller.py` (233 checks), the frozen netlist and the 50 mutation tests. The schematic does not change.
- **Main risk: routing.** The in-house router already closes 1 in 3 runs at 25.6 %. At 41 % expect hand routing in the layout source, or tscircuit. Not Freerouting.

### Option B: double-sided

The split:
- **Top:** THT connectors, module, inductors, electrolytics, ICs with more than 8 pins, and the whole RTD block. C34 keeps the RTD analog nets on F.Cu/In2.Cu over the In1 ground plane, so its parts stay on top.
- **Bottom:** 217 parts (passives and SOT-23/SOD).

Result: about 84–102 × 76 mm.

Costs:
- **JLC:** a bottom side adds JLC's second-side setup and a second stencil. The amount is not in the repo; read it off the quote. Standard PCBA is already required (`C/DECISIONS.md:727`).
- **Bring-up:** probing and rework get harder, because about 200 parts are under the board.
- **Height:** the bottom faces the snap-in supports, with about 12 mm under the board (R30 supports, `C/DECISIONS.md:172`). Check the bottom against the support heads.
- **Breaks:** the same items as A, plus bottom-side CPL, bottom F.Fab and assembly drawings.

### Option C: put the controller on native-21's SELV island

Measured on s53 (`results/native21-selv.json`):
- native-21 is 45 150 mm² (290 × 190 L-shape) at 39.6 % utilisation.
- Its SELV island plane outline is 8 800 mm²:
  - 91 SELV-only parts take 774 mm²;
  - 8 parts straddle the moat (1 399 mm² of courtyard, part of it inside the island).

Adding the controller:
- The controller less its J4 is 3 623 mm².
- Merged into the island, that is 50–66 % island utilisation, above the band.
- At u = 0.40 the island must grow by 2 190–5 690 mm², i.e. native-21 grows by 4.9–12.6 %.

Saves: both J4 headers, the J4 harness and the BIAS_GOOD wiring. Costs:
- **2 oz copper:** native-21 is 2 oz on every layer. JLC asks for at least 8 mil (0.2 mm) track and space on 2 oz (`PS/tools/jlc_dfm_check.py:15-17`). The controller uses 0.15 mm.
- **Plane roles are inverted:** the island's In1 is v3v3 and In2 selv_gnd. The controller's C34 RTD rule needs ground under F.Cu.
- **Location:** the analog front ends would sit beside a 17.5 A tank. The sensor, UI-jumper and antenna-coax landings would all move behind Y96, away from the fascia.
- **Re-spin:** native-21's s53 board of record and its barrier, D5 and DFM gates are re-run.
- **Not recommended.**

### Option D: part-level savings

These apply to the controller's own parts only. The ported thermal-sense, interlock and RTD blocks are byte-locked (`port_blocks.py --check`, C37), and their 71 × 0603 stay.

| Swap | Saving | What it costs |
|---|---|---|
| 0603 → 0402 for 111 own parts. 20 thin-film 0.1 %/0.05 % parts (RT0603B…, ERA-, RG2012) are kept | 289.5 mm² | New MPNs, stock reads, `bom/controller-parts.json` and the verify `bom` section |
| WROOM-1U (368 mm² courtyard) → ESP32-S3-MINI-1U-N8 (15.4 × 15.4 mm, Espressif MINI-1/1U datasheet v1.7 Table 1-1) | 115.5 mm² | New module pin table (`controller_parts.ato`, the MCU model in `verify_controller.py`). GPIO numbers are the SoC's, so `pins.h` can stay only if every used GPIO is bonded out on the MINI [to check]. Fresh JLC preview |
| 2 × 8 × 6.2 mm electrolytics → 6.3 × 5.8 mm | 55.2 mm² | Needs a 100 µF / 25 V part with the same ripple rating [UNVERIFIED] |
| **Total** | **460 mm² (11.5 %)** | Worth it only with B, or to buy routing margin in A-cut |

## 4. Cost

Board area is a small cost driver here:
- **Bare PCBs:** JLC quoted 5 bare 206 × 76 mm 4-layer boards at about USD 34.70 (`C/DECISIONS.md:724`). That is USD 6.94 per board **in total**, so no shrink saves more than that per board at prototype quantity.
- **Parts:** USD 65.35 per board (`C/ORDER.md:154`).
- **Extended parts:** 83 of the 89 BOM lines are extended types, and Standard PCBA is required (`C/DECISIONS.md:727`). These fees do not depend on area.
- **Bigger cost items than area:** B adds the second-side setup; D adds MPN churn; C adds a native-21 re-spin.
- **What a shrink buys:** enclosure volume, not money. A-cut frees the X93…168 strip under the fascia, 75 × 76 mm. That is only worth it if the enclosure has a use for it.

## 5. Recommendation

1. **Do not change the board for the first prototype order.** The C49 package is DRC-clean and already through the JLC preview (C50). A shrink re-opens routing, the CPL audit and the enclosure landings.
2. **For the next spin, if the enclosure wants the space: A-cut.**
   - The board is **131 × 76 mm at X−38…93**, top side only, 4 layers, same schematic.
   - Add 0402 for the controller's own passives to bring utilisation to 38 %.
   - It keeps J4, J7, J1, J2, J9, J13, four holes, the J4 harness and R43's J13 barrier. Only the cartridge cable, the blower lead and the antenna coax re-land.
   - Plan to hand-route it.
3. Go double-sided (B, about 84–102 × 76 mm) only if the enclosure needs the controller under about 100 mm long. Do not pursue 80 × 60 mm or the native-21 merge.
