# Bench heatsink r1: thermal mount for the first native-21 boards

Study, 2026-10-18. Branch `study/bench-sink-r1`, from `codex/power-stage-integration` @ f9d945326.

**Purpose.** A bench sink and mount that let the owner run COMMISSIONING steps 3–8 and 9a ("heat a pan"):
- on an isolation transformer, or on an isolated current-limited DC supply;
- on the native-21 stage-53 board;
- without the production M11 AlN stack.

**Status.** No hardware has been built or bought. No supplier was contacted, nothing was pushed, and no Rust or layout build was run.

**Rule for this file.** Every number below comes from a committed tool, named in its row, or is a parameter in `scripts/bench_params.py`. Parameters carry a source tag (`sources/SOURCES.md`) or are marked EST.

| tool (run from this folder) | output | runtime |
|---|---|---|
| `python3 -I scripts/bench_thermal.py` | `results/thermal.md`, `.json` | < 1 s |
| `python3 -I scripts/bench_insulation.py` (exits 1 on any fail) | `results/insulation.md`, `.json` | < 1 s |
| `python3 -I scripts/bench_cad.py` | `results/bench-sink-r1.dxf`, `.svg`, `results/drill-table.md` | < 1 s |

All three scripts use the standard library only. `bench_thermal.py` imports the device study's `thermal.py` loss models, and asserts on their constants.

## 0. Answer

**The mount, one line per part.**
- **Sink.** One **Wakefield-Vette 511-3M** bonded-fin sink:
  - fins vertical, base face 1.581 mm inside the board's rear edge (`insulation.md`, Geometry line);
  - lower edge 4.5 ± 0.3 mm above the board top, set with a gauge;
  - bonded to **PE**.
- **Insulator.** One continuous **SIL PAD 2000 (0.010 in) strip**, 114.5 × 30 mm, behind Q5, Q6, Q3, Q2 and BR1. It hangs 2.5 mm below the sink edge.
- **BR1.** Sits on a greased 0.508 mm aluminium shim under the strip, and is held by one M3 screw.
- **FET clamp: screwless.**
  - A 6061 3/8 × 1 in bar on two 10 mm spacers.
  - Four Lee LC 055E 03 S springs in 7 mm pockets in the bar.
  - FR-4 pads on the package fronts.
- **Sensors.** A Vishay NTCALUG01A NTC on M3. A real **Cantherm DF110S TCO** in the J3 loop, under 2 layers of Kapton and a loop clamp.
- **Fan.** 120 mm, used above 17.5 A or above a 30 °C ambient.

**Fixing chain (FAB-NOTE hole rules).** The sink and board both sit on a plywood baseplate:
- nylon M3 standoffs at H1 and H3–H8;
- H2, H9 and H10 empty;
- a window under the device row for soldering.

**Key numbers.** Ambient 30 °C, natural convection, ZVS loss basis D, worst FET, worst tab-area corner, 60 kHz:

| ceiling | sink | Tj FET | Tj BR1 | tool |
|---|---|---|---|---|
| **17.5 A** (ships) | **72.1 °C** | **79.7 °C** | 91.4 °C | `thermal.md` |
| 17.5 A at 40 °C ambient | 83.1 °C | 91.2 °C | 102.4 °C | `thermal.md` |
| **22 A** (headroom) | 83.1 °C, above the 80 °C TCO limit, **so the fan is needed** | 96.1 °C | 102.4 °C | `thermal.md` |
| 28 A | 114.2 °C, **fan needed** | 140.8 °C | 133.5 °C | `thermal.md` |

- **Fan requirement.** To keep the sink ≤ 80 °C at 30 °C ambient, R_SA must be ≤ 1.092 / 0.857 / 0.613 °C/W at 17.5 / 22 / 28 A. The 511-3M's natural 0.90 °C/W meets only the 17.5 A figure. Source: `thermal.md`, forced-air table.
- **D-36.** The interface Rcs is 0.954–1.155 °C/W per FET, so the bench mount **does not meet D-36 (≤ 0.7)**. No catalogue silicone pad does: K-10 gives 1.216–1.661 and 900S 1.739–2.166 (`thermal.md`). The bench accepts this because the junction stays below the 125 °C design target at 17.5 A and 22 A (rows above). D-36 stays an M11 (production) requirement.
- **Clamp force.** **68.4–85.4 N per TO-247** (nominal 76.9 N). That is inside the 45–102 N acceptance band and ≥ 60 N. Spring solid-height margin is ≥ 1.33 mm (`thermal.md`, Clamp).
- **Insulation and spacing.** All pass (`insulation.md`):
  - SIL PAD 2000 carries **9.1× the 622.4 V peak bound**, and its rating is 3.2× the 1250 V AC basic type-test level;
  - tightest creepage: **4.2 mm vs 4.0 mm**, sink edge to the edge pours across the hanging strip;
  - tightest clearance: **4.13 mm vs 1.3 mm**.
- **The sink-sensed trips do not protect the junction when ZVS is lost.** At 17.5 A, basis A (the D-18 hard-switching proxy), Tj is (`thermal.md`, trip table):
  - **139.3 °C** with the sink held at the 95 °C firmware trip;
  - **149.3 °C** at the 104.6 °C top of the hardware band;
  - **155.0 °C** at the TCO's 110 °C.

  Lost ZVS is caught by step 4's ZVS check and by the loop's lag latch, not by the sink. The sink-sensed chain is the backstop for the ZVS (D) case only: Tj 103.6 / 113.7 / 119.4 °C at the same three sink temperatures.

**Commits on this branch:**
- c5a448069: parameters, thermal and clamp;
- 21aa9ed23: insulation;
- 878ffc59d: drawing and drill tables;
- this README, the BOM and the sources: the final commit (see the git log).

## 1. Geometry and the board-side constraints

Frame (the M11 frame, from `bench_params.py`):
- x runs along the rear edge;
- y runs into the board, with y = 0 at the edge;
- z runs up from the board top.

| item | value | source |
|---|---|---|
| Device centres x | Q5 9.95, Q6 27.95, Q3 50.05, Q2 68.05; BR1 94.2 (body 79.6–109.2) | `[CPL]` |
| Tab nets | Q5, Q2 bus_p (HS); Q6 sw_b, Q3 sw_a (LS, switching) | params |
| FET tab plane / BR1 back | y 1.835 / 2.30 | `[M11]` |
| HOT pour edge (all layers) / nearest FET pad edge | y 0.6 / 1.965 | `[M11]` |
| Tab metal (IPW p.12 corners) | z 5.55–25.49 | `insulation.md` |
| Sink face | y 1.581 = tab plane − 0.254 strip | `insulation.md` |

**Why the sink sits only 1.581 mm inside the edge.** The TO-247s are not formed. They stand on their lead shoulders, with the tab plane where the footprint puts it. The sink face therefore sits exactly one strip thickness behind the tabs. No lead forming means no lead stress and no height uncertainty from bends.

**BR1.** Its back sits 0.465 mm behind the tab plane, and the 0.508 mm shim plus grease fills that. The remaining interference is taken up by BR1's lead play in its 1.6 mm holes.

**Why the strip hangs below the sink.** The sink edge is 4.5 mm over the board top and only 0.98 mm in from the HOT edge pours. Without the strip, the edge would face pour copper with less than the 4.0 mm creepage floor.

The 2.5 mm overhang does three things:
- it makes the creepage path run round the strip's free edge;
- it closes the narrow gap below the sink, so it counts as bridged under the X = 1.5 mm rule;
- it keeps every path ≥ 4.2 mm at the worst corner of sink height (±0.3) and overhang (±0.3) (`insulation.md`, rows C1–C3).

The gauge tolerance (Z_SINK_TOL 0.3) was tightened from 0.5 because C3 sat at exactly 4.0 mm with ±0.5.

## 2. Decisions

Each decision gives what was chosen, the data behind it, and what would reverse it.

### D1. Sink: Wakefield-Vette 511-3M, fins vertical, bolted to the baseplate by two angle brackets

- **Data.**
  - The 511-3M's 132.33 mm width covers the whole row: −12.0 to 120.33 against devices spanning x ≈ 2 to 109.2 `[WAK]`.
  - The 76.2 mm cut length points up, so the fins are vertical and the 0.90 °C/W natural rating applies.
  - A milled base (0.15 mm/mm flatness class) suits the 0.254 mm pad.
  - DigiKey had 25 in stock at $40.69 (read 2026-10-18).
  - It meets the 17.5 A ceiling without a fan (`thermal.md`).
- **Rejected.**
  - The production M11 extrusion: not available, and needs the AlN stack.
  - One small sink per device: the 18 mm FET pitch leaves no room.
  - The 511-6M (152.4 mm, 0.65 °C/W): worth it only if the bench must run 22 A without a fan.
- **Reverses if:**
  - stock runs out: take the 511-6M, same profile, nothing else changes;
  - the measured natural R_SA (§6, T0) is above 1.092 °C/W: run the fan at 17.5 A too.

### D2. Insulator: SIL PAD 2000, 0.010 in, one continuous strip

| strip | Rcs °C/W | Tj at 17.5 A, 30 °C | breakdown | tool |
|---|---|---|---|---|
| **SIL PAD 2000 0.254** | 0.954–1.155 | **79.7** | 4000 V AC | `thermal.md`, `[HNK]` |
| K-10 0.152 | 1.216–1.661 | 82.5 | 6000 V AC | `thermal.md`, `[HNK]` |
| 900S 0.229 | 1.739–2.166 | 85.5 | 5500 V AC | `thermal.md`, `[HNK]` |

- **Why SIL PAD 2000.** It has the lowest Rcs at the clamp's 82 psi. Its rating to peak stress is 9.1×, and its rating is 3.2× the 1250 V AC basic test level (`insulation.md`). The fibreglass carrier tolerates the bar's spring loading and hand placement.
- **Why one strip rather than one pad per device.**
  - Catalogue TO-247 ceramic or pad cut-outs (Fischer AOS 247 at 20 × 23 mm, Boyd 4180G at 23.24 × 18.8 mm) are wider than the 18 mm pitch.
  - A strip has no gaps between devices, so there is no creepage path between pads.
  - A strip is one part to place.
- **Why not ceramic (AlN or Al₂O₃) on the bench.** It is not catalogue-available at this pitch. It needs grease on both faces and a flat, controlled clamp. Its Rcs advantage is not needed to meet the bench Tj.
- **Cost.** One 12 × 12 in sheet ($171.85; DigiKey had 28) cuts 2 × 10 = 20 strips of 114.5 × 30 mm.
- **Reverses if:**
  - the SP2000 sheet is gone: use K-10 2165804 (+2.8 K Tj at 17.5 A; it has an adhesive side, so place it adhesive-to-sink);
  - the 500 V DC IR test (§5 step 10) fails: re-cut, inspect for burrs on the sink face.

### D3. Screwless spring clamp: bar, four springs, FR-4 pads

- **Why no screw through the tab.** A screw through the TO-247 tab hole would leave only about 0.25 mm of pad between the tab and the sink at the hole edge. It would also put a PE screw head against a HOT package front. It would need a shoulder washer and a second insulator at each device. Four such stacks multiply the creepage paths.
- **What the springs give** (`thermal.md`, Clamp):
  - force independent of the operator: 68.4–85.4 N, set by the spacer length and pocket depth, not by torque;
  - end-screw loads of 192.1 and 115.5 N on two M4 screws;
  - 0.072 mm bar deflection, costing 1.34 N at the middle.
- **Clearance to the board.** The bar's back face is 2.299 mm from the C38–C41 film-cap courtyard (`thermal.md`). The bar underside clears the tallest HOT SMD part under it by 4.9 mm (`insulation.md`).
- **Bar potential.** The bar is PE: it is screwed to the sink. All its paths to HOT pass (`insulation.md`):
  - spring to tab metal: clearance 4.419 mm, creepage 7.495 mm;
  - spacer to edge pours: 15.63 mm.

  The FR-4 pads are credited for nothing (`insulation.md`). They only spread the spring load over the package front.
- **Reverses if:**
  - the springs cannot be bought (Lee sells direct): any spring that fits the 9.53 mm pocket and gives 60–102 N at the installed length `bench_thermal.py` computes. Rerun `bench_thermal.py` with the new `SPRING`.
  - §6 measures a per-device ΔT spread suggesting uneven pressure: shim the pad.

### D4. Sink potential: bonded to PE

Options considered:

| option | single-fault result | verdict |
|---|---|---|
| **PE-bonded** (chosen) | A strip fault takes the faulted HOT net to PE. On the isolated secondary this earths one point, and the power-on DMM check (§5 step 12) finds it. The touchable sink stays at PE. The NTC's 1500 V AC insulation `[NTC]` sees no HOT stress. | chosen: same potential as production M11, so the measured common-mode and the NTC stress are representative |
| Floating | A strip fault puts a touchable, unlabelled sink at HOT with no indication. The NTC lug then carries HOT against SELV across one basic layer. | rejected |
| Tied to a HOT net | The tabs are on three different nets (bus_p, sw_a, sw_b), so the strip is still needed under two of them. The sink is then HOT and touchable. | rejected |

- **Bond.** 14 AWG green/yellow from the sink's M4 bond hole to the bench PE stud, star-connected with the board's J6 PE lead. Verify the bond resistance (§5 step 9).
- **Isolation transformer.** It remains the second measure for the operator. The PE bond protects against a strip fault; the transformer protects against a touch on board HOT.
- **Cost of bonding.** It adds 21.1–33.5 pF from each tab to PE (`insulation.md`; production AlN: 5.8–9.1 pF). The two switching tabs (Q3, Q6) inject C·dv/dt into the bench PE. Common-mode and EMI readings taken on this bench are therefore pessimistic for production.
- **Reverses if:** never on this bench without a second insulation layer.

### D5. TCO: a real Cantherm DF110S in the J3 loop, not a jumper

- **Why a real part.** J3's loop (l_filt–tco_l) feeds PS2's mains input, so opening it removes all gate drive. It is the one cut-out that works without the firmware, the controller or the NTC. It still works if the NTC lug comes loose. A jumper removes the only sink protection that survives a controller fault during the first powered runs.
- **Rating.** DF110S (`[CAN]`, `bench_params.py`):
  - Tf 110 °C, tolerance +0/−5, so 105–110 °C. That is above the 104.6 °C top of the hardware comparator band, so the ladder stays ordered: firmware 95 → hardware 98.3–104.6 → TCO 105–110.
  - Th 86 °C. A TCO held above Th drifts toward opening, so the bench keeps the sink ≤ 80 °C (6 K under Th). That is the source of the fan rule in D6.
- **Insulation.** The TCO case is live (TCO_L, line side). It gets 2 layers of 3M 5413 (106× peak stress, `insulation.md`) and a cushioned loop clamp. Bends ≥ 3 mm from the body; crimp, don't solder, near the body `[CAN]`.
- **DigiKey read.** 1,377 in stock, $0.87.
- **Reverses if:**
  - production picks the Microtemp G4A from the R43 BOM: match its Tf/Th. The one G4A rating seen (G4A01121C, Tf 121 / Th 106) was a search snippet and is not used. A 121 °C part would leave a gap above the hardware band.
  - the owner decides the bench TCO belongs on the glass rather than the sink (open question Q4).

### D6. Fan: 120 mm Cooltron, never credited

- **Rule.** Run the fan for any run above 17.5 A, or with ambient above 30 °C.
  - At 22 A the natural sink reaches 83.1 °C, above the 80 °C TCO limit (`thermal.md`).
  - At 17.5 A and 40 °C ambient it also reaches 83.1 °C.
- **What it needs to achieve.** R_SA ≤ 0.857 °C/W at 22 A and ≤ 0.613 at 28 A (30 °C ambient). Wakefield's shrouded 100 CFM figure (0.120) is far below that, but an unshrouded 120 mm fan at the fin tips is not that case. No pass claim uses the fan. §6's T0 run measures R_SA with it.
- **Reverses if:** the T0 measurement shows R_SA with the fan > 0.613 °C/W. Then 28 A needs a shroud or the 511-6M.

### D7. NTC on the sink face

- **Where.** M3 tapped at x 77.8, z 40.0, between Q2 and BR1 above the strip. That is where production's controller would read the hottest sink region. It is next to the TCO.
- **Why this NTC.** The NTCALUG01A lug is rated 1500 V AC terminal-to-lug `[NTC]`, but with the sink at PE it carries no HOT stress (`insulation.md`).

### D8. Baseplate, standoffs, brackets, window

- **Baseplate and standoffs.** 18 mm plywood, 400 × 300 mm. Nylon M3 × 15 male-female standoffs at H1 and H3–H8. H1 may take metal, but nylon is used for uniformity. **H2, H9 and H10 are left empty** (FAB-NOTE).
- **Brackets.** Two 1-1/2 × 1-1/2 × 1/8 in aluminium angles, bolted through the sink's outermost fins and slotted for y/z adjustment. They stay ≥ 5 mm behind the board edge: clearance 5.6 mm to edge copper (`insulation.md`).
- **Window.** Cut in the baseplate under board x −2 to 112, y −2 to 22. It gives iron and preheat access to the device leads, so the devices can be **seated on the sink and clamped before they are soldered**, as PROTOTYPE-LOT plans.
- **Reverses if:** JLC solders the TO-247 row (open question Q1). Then the devices arrive fixed. The sink is brought to the tab plane with a feeler stack, and the bracket slots absorb the difference.

## 3. Thermal results (abridged; full tables in `results/thermal.md`)

**Inputs.**
- Loss basis D: ZVS, from the device study's energy grid. Loss basis A: the D-18 hard-switching proxy, i.e. the lost-ZVS fault.
- I_t = 1.05 × ceiling.
- Bus at 132 V × √2.
- BR1 loss 25.52 W at 13.5 A line.
- RthJC 0.28 °C/W `[IPW]`.
- Spreading per device from the Lee et al. average form.

**The sink-temperature model.** It is one lumped sink temperature. It does not resolve the gradient along the row; for example, Q2 sits next to BR1. §6 measures that gradient.

| strip | ceiling | basis | amb | sink | P_FET | P_sink | Tj FET | Tcase | Tj BR1 |
|---|---|---|---|---|---|---|---|---|---|
| SP2000 | 17.5 | D | 30 | 72.1 | 4.83 | 44.8 | 79.7 | 78.3 | 91.4 |
| SP2000 | 17.5 | D | 40 | 83.1 | 5.16 | 46.2 | 91.2 | 89.7 | 102.4 |
| SP2000 | 22 | D | 30 | 83.1 | 8.36 | 59.0 | 96.1 | 93.8 | 102.4 |
| SP2000 | 22 | D | 40 | 95.3 | 8.98 | 61.4 | 109.3 | 106.8 | 114.6 |
| SP2000 | 28 | D | 30 | 114.2 | 17.03 | 93.5 | 140.8 | 136.1 | 133.5 |
| SP2000 | 17.5 | A | 30 | 160.8 | 30.31 | 145.4 | 208.2 | 199.7 | 180.2 |

**Tj with the sink held at each trip** (SP2000, worst FET; `thermal.md`):

| ceiling | basis | sink 86 (Th) | 95 (firmware) | 104.6 (hardware top) | 110 (TCO Tf) |
|---|---|---|---|---|---|
| 17.5 | D | 94.2 | 103.6 | 113.7 | 119.4 |
| 17.5 | A | 129.8 | 139.3 | 149.3 | 155.0 |
| 22 | D | 99.3 | 109.0 | 119.4 | 125.2 |
| 28 | D | 108.8 | 119.0 | 129.9 | 136.1 |

**Reading the tables.**
- **Normal operation.** At 17.5 A and 22 A (ZVS) the FETs stay well inside 150 °C and under the 125 °C target, at any sink temperature up to the TCO.
- **28 A.** It needs the fan, which holds the sink at or below 86 °C (Tj 108.8 °C there).
- **Lost ZVS.** At steady state it would overheat everything (row A). The sink trips bound Tj at 139–155 °C only if the sink actually reaches them. They are not the protection for this case.

**BR1 stack.** 0.457 °C/W in total: strip 0.364, shim 0.0064, grease 0.087, at 50 psi (`thermal.md`).

## 4. Insulation and spacing (abridged; full table in `results/insulation.md`)

**Stress bound.** Tab to PE sink: 435.7 V worst die VDS (OPEN-ITEMS S3) + 186.7 V line peak (132 V RMS) = **622.4 V peak**. This is above the 190 V line-only peak and the step-3 300 V DC test.

**Floors.** Basic: creepage 4.0 mm, clearance 1.3 mm, type test 1250 V AC (M11 RECOMMENDATION §2, basic reference).

| insulator | rating / peak stress | rating / 1250 V AC | field |
|---|---|---|---|
| SP2000 strip, FET tab → sink | 9.1 | 3.20 | 2.45 kV/mm peak |
| SP2000 + GBJ case behind BR1 | 49.2 | 5.20 | 0.73 kV/mm |
| GBJ case alone at the M3 screw | 18.9 | 2.00 | – |
| 2 × 3M 5413 on the TCO | 106.1 | 11.20 | 1.35 kV/mm |

**Spacing.**

| path | value | floor |
|---|---|---|
| Tightest creepage: sink edge → strip → board over the edge pours | 4.2 mm | 4.0 mm |
| Tab bottom edge → strip bottom → sink | 5.404 mm | 4.0 mm |
| Q5's left tab edge → strip end → sink | 5.479 mm | 4.0 mm |
| Tightest clearance: sink edge → F.Cu edge pour | 4.13 mm | 1.3 mm |

**Not assessed.** Partial discharge in the 0.254 mm strip under the low-side tabs' 33–60 kHz swing. The bench runs are short, and the 500 V DC IR test before power plus the monitoring in §6 are the checks. M11's thick AlN is the production answer.

## 5. Assembly procedure

Drill and cut dimensions are in `results/drill-table.md`; views are in `results/bench-sink-r1.dxf` (and `.svg`). Hand tools and a drill press only.

1. **Machine the sink** (drill-table, front face):
   - M4 bar-screw holes at u 5.0 and 127.5, v 14.2;
   - M3 NTC and TCO-clamp holes;
   - M4 PE-bond hole.

   Deburr the face and stone it flat where the strip lies. A burr is the likeliest way to puncture 0.254 mm.
2. **Machine the bar.** Cut to 130.5 mm. Pockets: 3/8 in flat-bottom, 7.0 mm deep, at u 20.95 / 38.95 / 61.05 / 79.05, v 9.0. Ends: Ø4.5 through at u 4.0 and 126.5. Break all edges.
3. **Cut the parts.**
   - Strip, 114.5 × 30.0. Scribe a line 2.5 mm above one long edge; that edge hangs below the sink.
   - Shim, 28 × 17 × 0.508.
   - Four FR-4 pads, 14 × 16.
   - Baseplate: window and standoff holes.
   - Brackets, 70 mm tall, slotted.
4. **Board onto the baseplate.** Nylon M3 standoffs and nylon screws at H1 and H3–H8. Nothing in H2, H9, H10.
5. **Sink onto the brackets.** Bolt the brackets through the outer fins (match-drill). Set the lower edge with a 4.5 mm gauge (drill shank) at both ends, then lock the brackets.
6. **BR1 hole (first build only).** Stand BR1 in its holes, hold its back against the bare sink at its natural seated height, and transfer-punch through its hole. Remove BR1. Drill 2.5 and tap M3.
7. **Stack the sink face.**
   - Thin film of 120-SA grease, then the shim, centred on BR1 (u 106.2).
   - Then the strip, with its scribed line on the sink's lower edge, left end at u 9.0, held by two Kapton tabs above z 32.
   - Punch a Ø4 hole in the strip at the BR1 screw.
8. **Devices and clamp.**
   - Insert Q5, Q6, Q3, Q2 with their tabs toward the sink, leads straight, seated on the lead shoulders. Insert BR1.
   - Fit BR1's M3 screw with a flat washer, at ≤ 0.56 N·m (`[GBJ]` 5 in-lb).
   - Place the FR-4 pads on the four package fronts, springs in the pockets, bar onto the two 10 mm spacers. Tighten the M4 × 25 screws until each spacer is clamped.
   - Spring force is now set by geometry: 68.4–85.4 N. Check each pad gap by eye, and check that all four devices stand square with a square from the board.
9. **Solder.** Stand the fixture on its left end so the window faces you. Preheat the board through the window: power pins are solid, rework at ≥ 100 °C board temperature (PROTOTYPE-LOT). Solder the TO-247 and BR1 leads and trim to ≤ 2.5 mm.
10. **IR test before any bond.** With the PE lead off the sink, short together every lead of Q2, Q3, Q5, Q6 and BR1 on the unpowered board. These are nets bus_p, sw_a, sw_b, leg_ret, l_filt, n_filt and hv_ret (`native-21/layout/pads.json`). Apply **500 V DC** from an insulation tester between that short and the sink, then between it and the bar.
    - Pass: ≥ 100 MΩ. This is the NTC datasheet's own IR criterion, used here as the bench criterion. It is not a computed value.
    - Do not hipot at 1250 V AC on the board: the board's Y-caps and suppressors are on these nets.
11. **TCO.**
    - Bend the leads ≥ 3 mm from the body. Wrap the body in 2 layers of 3M 5413 with ≥ 50 % overlap.
    - Lay it along x above BR1 (x 94.2, z 40). Hold it with a nylon-cushioned loop clamp on the M3 hole at z 47.
    - Crimp the leads to 18 AWG 200 °C wire with butt splices; never solder near the body.
    - Terminate in a JST VHR-3N with SVH-21T-P1.1 contacts in positions 1 and 3 for J3. Repeat the IR test of step 10 with J3 plugged.
12. **NTC.** M3 screw with a star washer into the tapped hole at (77.8, 40). Route its leads to the controller's sink-NTC input away from the HOT leads.
13. **PE bond.** 14 AWG green/yellow ring lug with a star washer on the M4 bond hole, to the bench PE stud, star-connected with the J6 PE lead.
    - Measure sink → PE stud and bar → PE stud with a 4-wire ohmmeter.
    - Pass: ≤ 0.1 Ω. This is the IEC 60335-1 cl. 27.5 limit, quoted from memory (EST).
14. **Power-on check, every session, on the isolated secondary.** With the board idle, measure the AC voltage from each secondary line to PE with a DMM. A collapsed reading on one line means a HOT-to-PE fault (strip, BR1 case or TCO wrap): stop.
15. **Fan.** 12 V bench supply, on a stand behind the fins, blowing into them. Switch it on for any run above 17.5 A, or with ambient above 30 °C.
16. **Touch.** The sink, bar and brackets are PE and may be touched. Everything on the board is HOT. Above 50 V, put the clear cover (polycarbonate on the baseplate, standoff-mounted) over the board, and fix the probes before energising (COMMISSIONING ground rules).

## 6. What the bench run measures

The aim is to turn the models above into measured numbers for M11.

**T0: thermal calibration, board unpowered, before step 3.** The FET's own body diode is the heater and the sensor (the JEDEC electrical-test method).
1. **Calibrate V_SD.** Bring the whole clamped assembly to two or three uniform temperatures in a warm room or under a cover, waiting for the sink thermocouples to agree. At each, record V_SD at a small sense current. This gives the V_SD(T) slope per device.
2. **Interface per device.** Drive a DC current through one FET's body diode from an isolated ≤ 2 V supply:
   - Q3: source+ at pin 3 (leg_ret), return at pin 2 (sw_a);
   - the other three analogously;
   - before connecting, check each net's other DC paths.

   Choose the current so that I × V_SD is close to that device's P_FET at the ceiling being prepared (4.83 W at 17.5 A, `thermal.md`). At steady state, interrupt for a few ms and read V_SD at the sense current to get Tj. Then:
   - Rcs = (Tj − Tsink)/P − RthJC;
   - Tsink comes from a thermocouple on the sink face directly above that device (z 33, x = device centre).

   Compare with the model's 0.954–1.155 °C/W. Expect Tcase − Tsink ≈ 6.2 K at 4.83 W (`thermal.md`: 78.3 − 72.1).
3. **R_SA.** Heat all four FETs, and BR1 from its − (hv_ret) to + (bus_p) terminals, together at a known total power near P_sink (44.8 W at 17.5 A). Record R_SA natural, and with the fan. Compare with 0.90 natural and with the 1.092 / 0.857 / 0.613 requirements.

**During steps 6 and 8.**
- Thermocouples: six type-K on the sink face above Q5, Q6, Q3, Q2, BR1 and beside the NTC, logged with the firmware's sink reading. **No thermocouple on any tab or lead.**
- An IR thermometer or camera on the plastic package fronts. This gives a case-side estimate. It is not a pass criterion.
- **Loss basis.** Total sink power = (T_sink,avg − T_amb) / R_SA(T0). If it is close to basis D's P_sink (44.8 W at 17.5 A), the ZVS loss model holds. A large excess means hard-switching edges (basis A).
- **Along-row gradient.** Is Q2, next to BR1, the hottest?
- **NTC versus the thermocouple beside it.** The offset feeds the trip ladder.

**After each session.** Repeat the 500 V DC IR test whenever the clamp has been opened.

**Record.** One CSV per session in the COMMISSIONING record, with columns: ceiling, f, ambient, per-device sink thermocouples, NTC, fan on/off, P_line. Plus T0's Rcs per device and R_SA.

## 7. Hand-off to M11

| bench output | used by M11 for |
|---|---|
| Measured Rcs per device for SP2000 at 82 psi | Calibrating the interface model (`interface_thermal.py`) against Henkel's D5470 numbers. If the measured value beats the catalogue, the D-36 thin-pad route (THIN-PAD-ROUTE) gains evidence; if it is worse, the AlN stack's grease/pressure assumptions need the same correction. |
| Spring clamp at 68.4–85.4 N, uniform across four devices | Confirms the 45–102 N comb acceptance band and the ≥ 60 N target with a real package front. The per-device ΔT spread tests uniformity. |
| Seated tab plane (no lead forming) and the 4.5 mm sink-edge gauge | Confirms M11's tab-plane datum y 1.835 on built boards. Measure the actual tab plane at Q5 and Q2 with a feeler before the strip goes on, and report it. |
| BR1's seated height and screw-hole position (measured at step 6) | M11's BR1 pocket and screw location: the GBJ drawing has no seating shoulder. |
| Total sink power at 17.5 A against basis D | The loss basis M11's sink is sized for. |
| NTC − thermocouple offset; sink gradient Q2 vs Q5 | The production NTC location and the trip ladder's sensor offset. |
| Whether the sink stays ≤ 80 °C at the run points (TCO Th margin) | The production TCO rating (Microtemp G4A choice). |

**Does not transfer:**
- R_SA (a different sink);
- the insulation: bench basic SP2000 at PE, versus the production AlN stack and its own basis;
- common-mode current: 21.1–33.5 pF versus AlN's 5.8–9.1 pF per tab (`insulation.md`).

## 8. BOM (reads 2026-10-18; raw reads and blocked sites in `sources/SOURCES.md`)

| # | part | qty | source / PN | stock read | unit price |
|---|---|---|---|---|---|
| 1 | Heatsink, Wakefield-Vette 511-3M | 1 | DigiKey 345-1205-ND | 25 | $40.69 |
| 2 | SIL PAD 2000, 0.010 in, 12 × 12 in sheet | 1 | DigiKey, Bergquist SP2000-0.010-00-1212 | 28 | $171.85 |
| 3 | Compression spring, Lee LC 055E 03 S (stainless) | 6 (4 + 2 spare) | leespring.com, direct | not shown | $8.04 |
| 4 | 6061 flat bar 3/8 × 1 in, 6 in | 1 | DigiKey (marketplace), Remington 0.375X1.0FLT6061T6511-6 | 50 | $11.83 |
| 5 | G-10/FR-4 sheet 1/16 in, 6 × 6 in | 1 | DigiKey (marketplace), USA Industrials BULK-CS-GFR4-54 | 3 | $15.53 |
| 6 | Spacer, M4 × 10 mm aluminium round, RAF M0539-4-AL | 4 (2 + 2) | DigiKey | 223 | $1.29 |
| 7 | Thermal grease, Wakefield 120-SA | 1 | DigiKey 345-1006-ND | 4,984 | $5.55 |
| 8 | TCO, Cantherm SDF-DF110S | 3 (1 + 2) | DigiKey 317-1131-ND | 1,377 | $0.87 |
| 9 | NTC lug, Vishay NTCALUG01A104GA | 2 (1 + 1) | DigiKey 56-NTCALUG01A104GA-ND | 770 | $2.19 |
| 10 | Polyimide tape 3M 5413, 1/2 in × 5 yd | 1 | DigiKey, 5413-0.5-5 | 23 | $33.04 |
| 11 | JST VHR-3N housing | 2 | DigiKey | not shown | $0.10 |
| 12 | JST SVH-21T-P1.1 contact | 6 | DigiKey | not shown | $0.042 |
| 13 | Fan, Cooltron FD1225B12W2-61-2NC1, 120 mm 12 V | 1 | DigiKey (marketplace) | 36 | $22 (qty 2) |
| 14 | Aluminium angle 1-1/2 × 1-1/2 × 1/8 in, 6061, 2 × 70 mm | 1 length | McMaster, **PN not read** (site blocked) | – | – |
| 15 | Aluminium sheet 0.020 in (shim) | 1 | McMaster, **PN not read** | – | – |
| 16 | Nylon M3 × 15 male-female standoffs, nylon M3 screws and nuts | 7 each | McMaster, **PN not read** | – | – |
| 17 | Steel: M4 × 25 SHCS (2), M4 × 10 + star washer (bond), M3 × 10 + washer (BR1), M3 × 8 + star washer (NTC, loop clamp), M4 bracket bolts + nuts (4) | – | any; McMaster **PN not read** | – | – |
| 18 | Nylon-cushioned steel loop clamp, ~6 mm ID, M3 tab | 1 | McMaster, **PN not read** | – | – |
| 19 | 14 AWG green/yellow wire, M4 ring lugs; 18 AWG 200 °C silicone wire; crimp butt splices | – | stock / McMaster | – | – |
| 20 | 18 mm plywood 400 × 300; clear polycarbonate cover and standoffs | – | local | – | – |
| 21 | Type-K thermocouples × 6 with logger; insulation tester (500 V DC); 4-wire ohmmeter | – | owner's bench | – | – |

**Totals.** The DigiKey and Lee lines above total about $360 at these reads. Most of that is the SP2000 sheet. This is quoted from the rows, not from a tool. Re-price at order.

## 9. Owner's next steps

1. Answer **Q1**: who solders the TO-247 and BR1 row. This design assumes in-house, seated before soldering.
2. Order BOM lines 1–13; buy 14–20 locally or from McMaster.
3. Build per §5. Report:
   - the measured tab plane at Q5 and Q2;
   - BR1's seated height and hole position;
   - the measured bar-to-film-cap gap: 2.299 mm modelled, so check it on the built board.
4. Run T0 (§6) before COMMISSIONING step 3, and file the Rcs per device and R_SA.
5. Run steps 3–8 at 17.5 A without the fan at ≤ 30 °C ambient, with the fan otherwise. Check the IR test and the power-on line-to-PE check every session.

## 10. Open questions

- **Q1. TO-247 / BR1 assembly.** PROTOTYPE-LOT and the r2-dfm proposals say in-house, but `bom-jlcpcb.csv` lists these parts for JLC. This design works either way (D8), but seat-before-solder is only possible in-house.
- **Q2. TCO equivalence.** The bench Cantherm DF110S (Tf 110 / Th 86) against the R43 BOM's Microtemp G4A "rating to select". No G4A datasheet was read: the Farnell/Newark pages timed out.
- **Q3. GBJ seating.** The datasheet gives no seating shoulder, so BR1's height (EST z 2.2–22.2) and the shim position are set from the part.
- **Q4.** Does the bench also need the glass TCO (R43 enclosure) for the pan runs, or only the sink TCO?
- **Q5. Gap-bridging width.** X = 1.5 mm (PD3) was quoted from memory. C3 (4.2 mm) depends on the strip-to-board gap being treated as bridged.
- **Q6. Unverified fit.** The McMaster part numbers were not read (site blocked), and the 511-3M's outer-fin construction for the bracket bolts is unverified until the part arrives.
- **Q7. Stock.** SP2000 had only 28 sheets at DigiKey. K-10 is the fallback (D2).
- **Q8. Partial discharge.** Not assessed in the thin strip under the switching tabs (§4).
