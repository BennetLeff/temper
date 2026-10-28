# How small can the power board be? (native-21, board of record s53)

Study date 2026-10-27. Read-only. Nothing was built, placed, routed or solved. No workspace build, chain, router or
B3 solve was run. Every number below comes from a script in `scripts/` (output in `results/`) or from a cited file.
Path prefixes: **PS** = `zapote/power-stage-120v`, **RUN** = `worktrees/runs-native21/s53/c53int` (outside git),
**OUT** = this folder. Estimates are labelled **[EST]**. "Bound" is used only where a number bounds something.

## 1. Answer in brief

- **The board is 39.7 % parts by area.** The s53 outline is 45,150 mm². Part courtyards cover 17,947 mm².
- **The rest is mostly copper, not air.** 19,406 mm² (43 %) carries pours and planes with no part on them. The 8 mm
  HOT↔SELV moat takes 4,106 mm² (9.1 %). Only 4,699 mm² (10.4 %) is truly empty.
- **The copper is the heatsink.** In still air the board sheds 13.3 W from its faces. That is a mean rise of 14.8 K.
  The release margin is only +1.3 K. So area cannot be cut freely: most cuts need more airflow or a cooler R_on.
- **What sets the outline:** the enclosure band (a ceiling of 290 × 140, not a floor), the J4 tongue (an owner
  harness choice), and the still-air thermal basis. The power loop and the barrier set the *core*, not the outline.
- **Best option [EST]: move EMI, fuse, MOV, PS2 and the blower tap into the existing inlet module, and drop the
  tongue.** That gives about **30,500 mm², roughly 218 × 140 mm** (68 % of s53). It needs h ≈ 12 W/m²K (not 10) at
  17.5 A, or a 2 W-class R_on plus about the same airflow. At 28 A it needs h ≈ 19 instead of 16.
- **Recommendation: build s53 as it is. Shrink in the production re-layout**, together with the board-face airflow
  that 28 A needs anyway.

## 2. What was measured, and how

`scripts/power_board_area.py` reads the s53 board of record and its copper dump. It checks the board's SHA-256
(`82af7bd9…`, the hash in `PS/validation-results/08-manufacturing-package/native-21/review-packet-s53/README.md` §2).

- **Courtyards:** F.CrtYd / B.CrtYd shapes of all 444 footprints, posed by each footprint's position. No footprint
  needed the pad-box fallback.
- **Union area:** rasterised at 0.25 mm. Overlaps are counted once.
- **Blocks:** assigned from each footprint's atopile `SourceInstance` name (rules in the script, `BLOCK_RULES`).
- **Barrier moat:** copper on every layer is split into a HOT side (HOT, MAINS, SW_A, SW_B) and a LOW side (SELV, PE),
  using the unit's own `PS/native-21/layout/domains.py`. Exact distance transforms then mark the copper-free cells
  closer than 8.0 mm to both sides.
  - Check: the smallest HOT-to-LOW copper distance on the raster is 8.13 mm. The D5 audit gives 8.047 mm. The
    difference is within the 0.25 mm raster.
- **Territory:** each board cell goes to the moat, or else to the nearest part courtyard. A block's territory is its
  parts plus the copper and empty board nearest to them. Holes, fiducials and test pads claim no territory.
  Territories plus moat add up to the board area exactly.

`scripts/power_layout_map.py` draws a 5 mm block map (`results/power_layout_map.json`).
`scripts/power_shrink_options.py` builds the option budgets (`results/power_shrink_options.json`).

## 3. Area census (s53)

Source: `results/power_area.json`.

| Quantity | mm² | % of board |
|---|---|---|
| Board (290 × 140 + 91 × 50 tongue) | 45,150 | 100 |
| Part courtyards, union (F side 17,856, B side 147) | 17,947 | **39.7** |
| Copper only, no part (pours, planes, lanes) | 19,406 | 43.0 |
| Barrier moat, copper-free (1,007 of it under straddling parts) | 4,106 | 9.1 |
| Empty: no part, no copper, not moat | 4,699 | 10.4 |
| HOT-side region / LOW-side region (cells nearer HOT / LOW copper) | 33,017 / 12,133 | 73 / 27 |

**By block.** "Duty" is each territory's share of the board's convective cooling in the s53 release solve (section 5).

| Block (designators) | Parts | Courtyard mm² | Territory mm² | % board | Copper only | Empty | Duty % |
|---|---|---|---|---|---|---|---|
| Sensing, protection, isolators (OCP/OVP, CT chain, AMC1311, CA-IS3720, LINE_ZC, heartbeat, SELV transfer caps) | 114 | 1,149 | 7,633 | 16.9 | 5,932 | 638 | 8.2 |
| Tank: bank C21–23/C151/C152, studs J2/J5, CT T1, bleed R22–R25 | 12 | 3,424 | 6,630 | 14.7 | 2,870 | 606 | 16.1 |
| PS2 + isolated bias (RECOM U41/U42, LS LDO U26, rail monitors) | 118 | 2,815 | 6,595 | 14.6 | 3,049 | 635 | 24.1 |
| Mains / EMI / fuse / MOV (J1, F1, RV1, C1–C4, L1, R1, R2, J6) | 11 | 3,634 | 6,434 | 14.3 | 1,588 | 1,254 | 12.8 |
| Bridge FETs + gate drive (Q2/Q3/Q5/Q6, U1/U2, leg networks, C38–C41, R5) | 105 | 2,329 | 5,416 | 12.0 | 2,852 | 374 | 26.4 |
| Rectifier + bus (BR1, C5, C6, D3, D17, R3, R4) | 7 | 3,329 | 5,226 | 11.6 | 1,782 | 239 | 11.6 |
| Connectors J4 (tongue), J3 | 2 | 411 | 1,863 | 4.1 | 1,295 | 109 | 0.3 |
| Blower AC tap (F2, R130, J11) | 3 | 318 | 1,247 | 2.8 | 39 | 842 | 0.5 |
| Holes, fiducials, 59 test pads | 72 | 594 | 0 | 0 | — | — | — |
| Barrier moat | — | — | 4,106 | 9.1 | — | — | — |

The largest single parts: PS2 1,465 mm², C5 and C6 1,424 each, L1 1,380, T1 766, F1 clips 610, each bank cap 492,
RV1 449. These twelve parts hold 9,977 mm², 56 % of all courtyard area.

**Where the space is (5 mm tiles, board frame, y down; `results/power_area.json` `tile_map_5mm`).**
C = parts, `=` = copper only, `~` = barrier moat, `.` = empty.

```
  y  x: 0 ......................... 145 ......................... 290
  0 .CCCCCC==CCCCCC=CCCCCC=====.C===CCCCCCCCCCCCCCCCCCCCCCCCCC
 20 ================================CCCCCCCCCCC...=CCCCCCCCCC=
 40 C.=CCC.==C==CC=CC=CC=======================CCCCCCCCC......
 60 =CC=~~=~~CCCC~~C=~~.C==C....====CCCCCCC==CCCCCCCC=========
 80 ====~~=~~=====~~=~~.CCCC==C.====CCCCCCC==CCCCCCCCCCCCCCCCC
100 ====~~=~~===C~~==C~~C====CCCC.==CCCCCCC=~~=CC.====CCCCCCCC
120 ~~~~~~=~~~~~~~~=.~CCCCCC~CCCCCC=.........==.........CCC...
135 ==============================CCCC=========.C.............
140 ===================      (tongue: SELV pour)
175 =C====CCCCCC=====C=      (J4)
```

(Every fourth row shown; the full map is in the JSON.)
- The left half (x 0–115) is the power core and the two high-side bias islands. Its "copper only" area is the In1
  HV_RET and In2 BUS_P planes and the switch-node lanes.
- The vertical `~` strips are the moats round the SELV island and its fingers.
- The empty patch at the bottom right (x ≈ 205–290, y ≈ 115–140) is where PS1 used to be. DECISIONS 50 kept it clear
  on purpose (`PS/DECISIONS.md:1678`).
- The tongue (y 140–190) is 4,550 mm² of SELV ground pour that carries only J4, R146 and five 0603 caps.

## 4. What sets the outline

| Constraint | What it fixes | Where |
|---|---|---|
| Enclosure band (D-36) | A **ceiling**: at most 290 × 140 in the front-middle band, between the front-panel module, the centre-sensor corridor and the coil legs. A 240 × 160 board fit nowhere | `PS/DECISIONS.md:135-141`; `PS/RELAYOUT-REQUIREMENTS.md:39` (L11) |
| Smaller boards fit *more* easily | The R4 rectangle scan: 290 × 140 fits 15 positions, 250 × 140 fits 150, 220 × 140 fits 303 (board box only, no sink or duct) | `PS/validation-plan/enclosure-fit/rect-scan.json` (R4, pre-R43) |
| FET row and edge sink | BR1 + 4 × TO-247 in one 106 mm row on the rear edge; sink keep-out 114 × 50 × 73 behind it | `RELAYOUT-REQUIREMENTS.md:41-42` (L13, L14); `PS/native-21/FLOORPLAN.md:20` |
| Connectors | Mains and coil studs on or near the rear edge, outside the sink span | `RELAYOUT-REQUIREMENTS.md:43` (L15) |
| **The L-shape** | The 91 × 50 tongue exists only to put J4 on a front edge: a 74 mm lead to the front controller that stays in front of the Nomex barrier. A J4 elsewhere was estimated to need ≥ 140 mm of SELV lead across the HOT core | `PS/DECISIONS.md:260-265`; `PS/native-21/FLOORPLAN.md:3-4` ("the tongue … grew during routing") |
| 8 mm HOT↔SELV / PE (reinforced, PD3, group IIIa) | 4,106 mm² of moat (9.1 %). It scales with the SELV island's perimeter, not with board area | `PS/D5-BASIS.md:5,30-32`; `results/power_area.json` `barrier` |
| RES_A 12.6 mm outer-layer rule | Keeps the tank copper far from SELV/PE (F.Cu minimum 18.99 mm, B.Cu 13.38 mm on s53) | `RUN/barrier.txt`; review-packet README §4 gate 5 |
| Power loop | The HF film row C38–C41 sits under the FETs, 6 mm lower than native-19 to fit the F6 gate network. Its loop was re-extracted in FEM and kept | `PS/DECISIONS.md:144,146`; `RELAYOUT-REQUIREMENTS.md:23-25` (L5–L7) |
| Tank copper | The tank lanes ride on one 2 oz layer each; SW_A at 7.0 mm set the 22 A copper screen | `PS/DECISIONS.md:150,154` |
| **Board-copper heat path** | Still air, h 10 W/m²K, bay 61 °C. The board is the heat spreader for R_on, the RECOMs, U26, PS2 and the tank copper. Release margin +1.3 K (R10) | `PS/DECISIONS.md:2193-2210` (item 61); `margins.json` |

**So:** the band sets a maximum. The FET row and the barrier set the core. The tongue is a harness choice. The
binding limit on *shrinking* is thermal.

## 5. Thermal: how much the margin depends on area

Source: the s53 release solve `PS/validation-results/04-board-current-thermal/round5-native21/b3-ratings/runs/c17.5_h10_p0p25.json`
(board SHA matches s53) and `margins.json`.

- Heat into the board model: 16.63 W (8.88 W parts, 7.75 W hot tank/bus/line copper).
- It leaves as 13.32 W by face convection, 2.26 W from part bodies to air, 1.05 W down the FET leads to the sink.
- Face convection at h 10 over 45,150 mm² × 2 faces gives a **board-mean rise of 14.8 K** (13.32 / (2 × 10 × 0.04515)).
- The binding release row is R10 (68 Ω 2512 R_on at 0.217 W, terminal derating): **+1.3 K**. Next: laminate 1 mm
  block +3.8 K, R20 +4.2 K, PS2 local air +4.2 K, U26 +4.4 K.
- In an older (s43) attribution, R10's rise was 47.0 K of board heat, of which 19.3 K was R_on itself and about
  27.7 K came from everything else (`…/heat-attribution-2026-10-15/README.md:174`). The far part is what shrinking
  makes worse.

**Lumped area model [EST, not B3].** Each kept territory's share of the convective duty is taken from the solve's own
pad temperatures × area (the apportionment overshoots the solve's total by 10.5 %, so it is used for shares only).
If an option removes board heat q and duty share c, the rest of the board must run hotter by a factor
F = ((Q − q)/Q) / (1 − c). The hit on the release row is estimated two ways:

- low = (F − 1) × 14.8 K, the board-mean rise;
- high = (F − 1) × 27.7 K, R10's far-field heat.

Neither is a bound. A B3 solve on a real re-layout is the only real check.

Two facts drive the results:
- **The tongue and the SELV island do almost no cooling.** They sit across the moat from the heat. The tongue's
  territory carries 0.4 % of the duty. Cutting it costs about 0.1 K.
- **The PS2 / L1 / mains corner does real cooling.** Moving it off removes 1.28 W of board heat but 23 % of the duty.
  F = 1.17–1.18.

## 6. Shrink options

All areas are **[EST]** from `results/power_shrink_options.json`.

- *Repacked* = cut-only area minus half the empty area left in the kept territories (range shown for 30–70 %).
- *Width at 140* is an indicative rectangle at the band's 140 mm depth. It is not a placement.

| Option | Area mm² (range) | % of s53 | Indicative outline | Release margin at h 10, low / high est | h to keep today's margin | h for 28 A (lumped; s53 needs 16) |
|---|---|---|---|---|---|---|
| O0 Same circuit, re-laid tighter | 42,800 (41,860–43,740) | 95 | keeps the L | +1.3 / +1.3 K | 10 | 16 |
| **O1 Drop the tongue** (J4 + 6 small parts move into the main body) | 38,920 (38,000–39,850) | 86 | **290 × 140 rectangle** | +1.2 / +1.2 K | 10 | 16.1 |
| O2 Inlet module takes EMI, fuse, MOV, PE branch, blower tap, PS2 + J3 (adds a 2-pole input terminal and a 2-pin gate-supply input) | 34,380 (33,930–34,840) | 76 | L, ≈ 245 wide | −1.3 / −3.5 K | 11.7 | 18.8 |
| **O1 + O2** | **30,500 (30,060–30,940)** | **68** | **≈ 218 × 140** | −1.4 / −3.7 K | 11.8 | 18.9 |
| O1 + O2 + O6 (R_on 2 W class) | as O1 + O2 | 68 | ≈ 218 × 140 | R10 no longer binds; next row (laminate block) +1.1 / −1.2 K | ≈ 11.8 | ≈ 18.9 |
| O3 Controller merged into the SELV zone | +8,180 to +12,270 on the board | — | on O1 + O2: 38,680–42,770 mm², about 290 × 140 | SELV area adds little heat | — | — |
| O4 QDPAK top-side-cooled FETs | +1,215 mm² of courtyard | +2.7 | no direct gain | changes the heat path (below) | — | — |
| O5 Denser resonant bank | at most the bank's 3,856 mm² territory | −8.5 at most | small | bank ratings re-open | — | — |

### O1: drop the tongue

- **Gain:** 4,550 mm² of outline comes off. J4 and its parts need about 630 mm² in the main body's SELV island. The
  result is a plain 290 × 140 rectangle, about 14 % smaller.
- **Cost:** the J4 harness. It runs from the main body's front edge (y 140) instead of the tongue's (y 190), about
  50 mm further back [EST]. The owner's reason for the tongue was a 74 mm lead kept in front of the Nomex barrier.
  Whether a lead from y 140 stays in front of that barrier is not checked here.
- **Thermal:** neutral (the tongue cools almost nothing).
- **Breaks:** a full re-route of the SELV island edge; every gate; R43 fit (the board shrinks, but the J4 landing
  moves); a new order package.

### O2: an inlet-side module takes the mains corner

- **Gain:** 10,380 mm² of territory leaves. The board keeps BR1 onward.
- **Fits a module that already exists.** The D-22 inlet module already carries the CM choke, X caps and DM inductors
  (`PS/validation-results/11-candidates/c23-supply-topology/MODULE-REQUEST.md:6-17`). Moving L1, C1–C4, RV1 and F1
  into it consolidates one filter that is now split across two parts of the system.
- **What it costs:**
  - EMI must be re-modelled. The s19b desk margin depends on the board's L1 and on the module's DM inductance
    (review packet §4).
  - The touch-current budget (0.2412 mA against 0.25, margin 8.8 µA, DECISIONS 50) moves with the Y caps.
  - PS2's 24 V output is referenced to N_LS (HOT). Off-board, it becomes a HOT harness, and the TCO loop J3 goes with it.
  - The F1 copper-I²t check (0.993 today) moves to the module's wiring.
  - **Thermal: −2.6 to −4.8 K on the release row at h 10.** The board loses its warmest spreading area.
- **Breaks:** the EMI and leakage evidence; the certifier packet items on F1, J1 and the Y caps; R43 fit and the
  rear-wall connector plan.

### O3: merge the controller (seen from the power board)

- **Area:** the controller has 289 footprints and 4,071 mm² of courtyard on a 206 × 76 board (26 % packing). Merged
  at 30–45 % packing, it adds 8,180–12,270 mm². J4 and the harness go on both sides.
- **System total:** on top of O1 + O2, one board of about 38,700–42,800 mm² would replace two boards totalling
  60,806 mm² today.
- **Barrier:** the controller is all SELV. If it sits against the existing SELV island, the 8 mm moat grows only where
  the new SELV area faces HOT copper. The island already crosses the board through the isolators.
- **Heat:** the SELV island sits across the moat and runs near bay air (its parts read the lowest pad temperatures in
  the solve). That suits an ESP32 module better than the HOT side would.
- **What it breaks:** the enclosure. The controller sits behind the front panel and the R43 band was chosen to clear
  that front module. A merged board must reach the front panel, so the fit study starts again. Coil-field pickup on
  the controller's sensor front ends would also need a new study (the coil plate covers board y ≤ 79,
  `FLOORPLAN.md`).
- The separate controller study (CONTROLLER.md in this folder) owns the controller side.

### O4: top-side-cooled SMD FETs

- **Part:** Infineon **IPDQ65R017CFD7A**, 650 V CoolMOS CFD7A, R_DS(on),max 17 mΩ (the TO-247 IPW65R018CFD7 is 18 mΩ).
  - Package Q-DPAK PG-HDSOP-22, 15.1 × 21.06 mm maximum.
  - R_thJC 0.18 °C/W. Reverse-diode dv/dt 70 V/ns, the same as today.
  - Drain on the top tab, so the tab is live.
  - Automotive (AEC-Q101) grade.
  - Source: Infineon datasheet Rev. 2.2, 2026-03-01, pp. 1, 3, 4, 12
    (https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipdq65r017cfd7a-datasheet-en.pdf).
  - Siblings in the same package: 40, 80, 99 and 125 mΩ (distributor listing, not re-read). IPQC65R…CFD7A is the
    bottom-cooled version.
- **No CoolMOS CFD7 in TOLT was found.** Infineon's TOLT parts in the search were CoolSiC. The IPT65R…CFD7 parts are
  TOLL, which is bottom-cooled.
- **Area:** four Q-DPAKs take about 1,215 mm² *more* courtyard than four vertical TO-247s.
- **What it buys:** freedom from the rear-edge row (L13) and from the edge-sink keep-out (L14). The power loop can be
  planar SMD.
- **Insulation:** the live top tab still needs a reinforced insulator to a PE sink. The repo's M11 study already rated
  it about 0.77 °C/W (conservative), which fails the 0.7 budget (`…/m11/stack-options/COST-BENEFIT.md:18,32`). It
  called this "production option only".
- **Breaks:** FEM leg evidence, F6 decks, M11 stack, sink and duct.

### O5: denser resonant bank

- **Today:** the bank is 5 × 100 nF / 2000 V film, 2,459 mm² of courtyard and 3,856 mm² of territory (8.5 %). It sets
  the 24 A ceiling (review packet §5).
- **Fewer, larger caps:** they would need the same current and voltage rating. Film volume scales with C·V², so area
  falls only if the parts get taller (L12 allows 50 mm). A realistic gain is a fraction of the 8.5 %.
- **Cost:** the bank's whole evidence chain (DECISIONS 68, 70, 73, 74). **Not worth it on its own.**

### O6: what replaces board copper as the heat path

- **The binding row is a choice of part.** R10's limit follows the gate's own line,
  155 − 85·P / (0.8·P_rated) (`b3_ratings_gate.py:404`; UniRoyal 25121WF 1 W at 70 °C, lines 108–112).
- A 2 W-rated part, or two 1 W parts in parallel, lifts the limit from 131.9 to 143.5 °C, worth +11.5 K. Two parts
  also halve each part's heat, which is not credited here.
- **Then the laminate block at R12 binds (+3.8 K), then U26 (+4.4 K).** Both also take R_on heat.
  - The R_on change goes through the gate network (DECISIONS 54) and its gate-loop checks.
  - The 2 W part has not been chosen; no datasheet was read.
- **Airflow is the big lever.** Board-face airflow is already the plan for 28 A: DECISIONS 66 needs h ≥ 16 W/m²K
  (review packet README:113).
  - In the lumped model, a shrunk board needs h scaled by F: about 12 at 17.5 A and about 19 at 28 A for O1 + O2.
  - Shrinking and 28 A therefore draw on the same airflow budget. Neither has a bench h measurement yet
    (DECISIONS 69 sets the method).
- **Other levers** from the heat-attribution study: thicker tank copper (+1.75 A for −20 % copper loss), a lower
  sink setpoint (+0.92 A per −10 K), cooler bay air (0.27 A per K). These buy current, not area. Any one of them can
  be spent on area instead.

### Why not 150 × 120 like a commercial cooktop?

The brief's comparison board is 18,000 mm², single-sided, with one or two IGBTs and a non-isolated MCU. The best
estimate here (30,500 mm²) is about 1.7× that. The gap is structural:

- a full bridge with two reinforced isolated drivers, two isolated bias modules and their monitors (6,595 mm² of
  territory);
- an 8 mm reinforced moat (4,106 mm²);
- the OCP, CT and heartbeat protection chain (7,633 mm², mostly SELV ground plane);
- a 5-cap 2000 V bank;
- a heat path through board copper in still air.

A commercial board puts its devices on a fan-cooled sink and has no SELV barrier on the board.

## 7. Before or after the first prototype order?

The s53 order is prepared, not placed (`…/native-21/PROTOTYPE-LOT.md:1`). It carries:
- 19 passing gates;
- the R43 real-pose fit;
- FEM-backed loops;
- a certifier packet refreshed to s53;
- a stock-gated BOM.

Every shrink option breaks at least one of these:

| Option | Breaks | Sensible when |
|---|---|---|
| O1 tongue | re-route, all gates, R43 fit, order package, J4 harness length | production re-layout (it is cheap and thermally neutral, but not cheap enough to re-open a frozen order) |
| O2 inlet module | EMI and leakage evidence, certifier items (F1, J1, Y caps), module design, R43 connectors, thermal margin | production, with airflow, after bench EMI and leakage data on s53 |
| O3 controller merge | enclosure band and front module, both boards' evidence, controller firmware pin map | production, only if the enclosure is re-planned; decide after the bench |
| O4 Q-DPAK | FEM legs, F6 decks, M11 stack, sink, duct | production at the earliest |
| O5 bank | bank ratings evidence | no |
| O6 R_on 2 W class | gate network checks; BOM | production (or as a BOM-only candidate if a same-footprint part exists) |

**Recommendation: prototype s53 as it is. Shrink in the production re-layout.** Target O1 + O2 + O6, about
**218 × 140 mm (≈ 30,500 mm², 68 % of s53)**, together with the board-face airflow that 28 A already needs.

Why wait:
- The thermal basis is a desk model with +1.3 K of margin. There is no bench measurement anywhere in the project
  (CHECKLIST G-01).
- The prototype will measure exactly the things a shrink depends on: board-face h (DECISIONS 69), the hot spots, EMI
  with the real module, and touch current.
- Shrinking first would trade a fully gated board for an unverified one, to save area that the enclosure does not
  need today (the band allows 290 × 140).

**Main risk:** heat. The board's copper is its heatsink in still air. A shrunk board leans on airflow nobody has
measured. If bench h comes in under about 12 W/m²K, a 218 × 140 board would not hold 17.5 A without a cooler R_on.

## 8. Limits of this study

- Areas are budgets, not placements. The 218 × 140 figure assumes C5/C6, D3/D17 and the bank can be re-packed into
  the space PS2 and the filter leave. That was not tried.
- The thermal numbers are a lumped first-order model built on one B3 solve. They are not B3 results. The
  low/high spread is the honest uncertainty.
- R10's far-field term (27.7 K) comes from the s43 attribution, an older stage than s53.
- "Territory" uses nearest-courtyard assignment (chessboard metric). It is a fair share-out, not a layout rule.
- The rect-scan is the R4 scan (board box only). R43 fit was not re-run.
- Q-DPAK data is from the Infineon datasheet (read). Sibling parts and the absence of a TOLT CoolMOS come from web
  search only.
- Side note (not a defect): B3 run files are solved on a 50 °C base. `b3_ratings_gate.py` `est()` re-bases them to
  the bay. Raw probe values below the 61 °C bay are expected.

## 9. Reproduce

From `OUT/scripts` (standard-library Python, about 10 s in total; the s53 run folder must exist outside git):

```
python3 power_board_area.py        # -> results/power_area.json (checks the s53 SHA-256)
python3 power_layout_map.py        # -> results/power_layout_map.json
python3 power_shrink_options.py    # -> results/power_shrink_options.json
```
