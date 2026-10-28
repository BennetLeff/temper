# Lab mill plan: lean PrintNC build, then bootstrap

Owner decision 2026-10-28. A home-lab CNC mill for Temper prototype parts, built for about
$1,560 in materials, then upgraded with parts it machines itself. Agents do the CAD, PCB,
CAM and analysis; the owner assembles. Decisions and their reasons are in
[DECISIONS.md](DECISIONS.md); progress is in [STATUS.md](STATUS.md).

## 1. Scope

**Jobs the machine must do** (each is a Part B item below):

| Job | Material | Source of the requirement |
|---|---|---|
| Fascia bench coupon: eight blind D10.4 × 1.5 magnet pockets, M2 taps | 5052 3.0 mm | `output/temper-knob-contract/wp2/parts.csv` (`fascia_coupon_5052`) |
| Knob shell secondary ops: three key pockets at 120°, radial M1.6 holes | 6061 | `wp2/parts.csv` (`puck_shell`); the turned blank stays a JLC part |
| Stand-in puck springs for rate and feel tests | phosphor bronze C51000, 0.7 mm | `wp2/REPORT.md` arm resize; C17200 itself is never machined here (D6) |
| Heatsink spreader bar: face, drill, tap | 6061-T6 | R43 BOM `electronics_sink_spreader_bar` |
| Brackets, fixtures, small PEEK / acetal parts | 6061, PEEK, acetal | general prototyping |

**Not this machine's job:** sheet-metal enclosure parts (SendCutSend), the glass sensor bore
(drill press + diamond core bit + water dam), turned parts (JLC), stainless or steel parts,
anything in C17200.

## 2. Requirements

| ID | Requirement | Verified by |
|---|---|---|
| R1 | Working area about 450 × 350 mm (X × Y), Z travel ≥ 100 mm | measured travel at commissioning |
| R2 | Spindle nose to table ≥ 150 mm at Z top. The Z plate has a second spindle position 40 mm higher, for a rotary later (D8) | measured |
| R3 | Positioning within ±0.05 mm over 100 mm on every axis after calibration; backlash ≤ 0.02 mm | dial indicator, P5 |
| R4 | Tram ≤ 0.02 mm across a 100 mm sweep | tram plate and indicator, P5 |
| R5 | Test coupon holds ISO 2768-m (the knob contract's P04 class for machined parts) | measured coupon, P5 |
| R6 | Agent-drivable: an agent streams G-code, reads machine state and runs probe cycles over the network without a GUI | scripted job, P6 |
| R7 | Every program is simulated with the vise, fixtures and stock modelled, collision-free, before it cuts. Every new program also runs once in the air. | sim log kept beside the program |
| R8 | E-stop opens a contactor that cuts motor power and the router. Tested before the first powered move. | P4 test record |
| R9 | No C17200 (beryllium copper) machining, no glass, no unattended runs until P6 passes | rule |

## 3. Part A: the $1,560 build

### 3.1 Bill of materials

Prices are estimates from listings checked 2026-10-28 (sources at the end), before shipping
and tax. Re-price before ordering.

| # | Item | Spec | Est. USD |
|---|---|---|---|
| A1 | Frame steel | PrintNC V4 Desktop preset: 75 × 50 × 3 tube frame, 75 × 75 × 4 gantry, cut to the configurator's cut list by the supplier | 150 |
| A2 | Linear motion | HGR20 rail × 4 (X, Y) with HGW20CC × 8; HGR15 × 2 (Z) with HGH15CA × 4; SFU1610 × 3 (X, Y1, Y2), SFU1204 × 1 (Z); BK12/BF12 × 3, BK10/BF10 × 1; couplers 3 × D30 L40, 1 × D25 L30 | 350 |
| A3 | Plates and hardware | Z plate, spindle plate (two positions, R2), tram plate as agent-drawn DXFs cut by SendCutSend; fasteners; leveling epoxy; two drag chains | 150 |
| A4 | Motors and drivers | 4 × NEMA23 about 3 Nm, 4 × DM542T, 48 V 350 W supply set to about 45 V | 230 |
| A5 | Control | grblHAL controller board (agent-designed, JLC-assembled, 5 step/dir outputs: X, Y1, Y2, Z, spare A), 24 V supply, E-stop and contactor, 4 × M8 NPN NC homing sensors (X, Y1, Y2, Z), cabinet about 400 × 600 × 200, cable | 200 |
| A6 | Router | Makita RT0701C with a 65 mm clamp, precision collets for 1/8″ and 1/4″; switched by a controller relay; speed set on the dial | 150 |
| A7 | Workholding and probing | 4″ vise; agent-designed touch probe and tool-length setter | 120 |
| A8 | Starter cutters | single-flute carbide for aluminum (1/4″, 1/8″, 1 mm, 0.5 mm), spot drill, drills, M2/M3/M4 taps | 150 |
| A9 | Chips | plywood splash guard, shop-vac port, air blast or IPA mist | 60 |
| | **Total** | | **≈ 1,560** |

Not included: bench tools you may already own (drill, taps, square, dial indicator with
magnetic base, calipers), about $100 if bought. A bought grblHAL board is the fallback for A5
if the custom board slips (it costs more; price it at P0).

### 3.2 Phases

| Phase | Work | Who | Gate to leave the phase |
|---|---|---|---|
| P0 Design | Configure the V4 model at the Desktop preset and export the cut list. Check R1/R2 clearances in the model. Draw the plates (A3). Design the grblHAL board in KiCad, **hand-routed, no autorouter**, with the E-stop chain, homing inputs, probe input and router relay. Draw the cabinet wiring diagram. Design the probe and tool setter. | agents | A second agent reviews the board and the E-stop chain. BOM re-priced from live listings and still ≤ $1,600. |
| P1 Procure | Order A1–A9. On arrival: every block slides smoothly with no notchy spots and no missing balls; clean and regrease every block; check screws for straightness and nut play. | owner | Inspection notes in STATUS.md; reject bad blocks before mounting |
| P2 Frame | Drill with the guides, bolt up, epoxy-level the rail surfaces | owner | Rail surfaces flat ≤ 0.05 mm over their length; X ⟂ Y within 0.05 mm over 300 mm |
| P3 Motion | Mount rails parallel within 0.02 mm, align screws (each turns freely by hand over full travel), fit motors | owner | Hand-turn check passes on all axes |
| P4 Electronics | Build the cabinet, test the E-stop chain with motor power off and then on, set up homing and Y auto-squaring | owner, agents on config | R8 test recorded; homing repeats within 0.02 mm over 10 cycles |
| P5 Commission | Calibrate steps per mm against the indicator over 100 mm; measure backlash; tram the router; cut MDF, then the aluminum test coupon | owner, agents on analysis | R3, R4, R5 measured and recorded |
| P6 Agent loop | CAM pipeline (scripted FreeCAD CAM, or G-code generators for 2.5D work) → collision simulation (CAMotics) with fixtures modelled → network streaming → job log | agents | R6 and R7 shown on the B1 job |

## 4. Part B: bootstrap

The machine's first jobs are its own workholding, then Temper parts. Each item is material
cost only, because agents do the design and CAM.

| Step | Make | Replaces | Material | Acceptance |
|---|---|---|---|---|
| B1 | Surface the MDF spoilboard | — | MDF, about $20 | flat within 0.05 mm |
| B2 | Fixture plate: 6061, about 300 × 200 × 12 mm, M6 tapped grid with dowel holes | a bought fixture plate | about $60 | faced flat within 0.03 mm; dowel holes on grid within 0.05 mm |
| B3 | Aluminum soft jaws for the vise | bought jaws | about $15 | jaw step parallel to X within 0.02 mm |
| B4 | Machined 65 mm router clamp (replaces the sheet clamp) | — | about $15 | tram holds R4 after a router remove-and-refit |
| B5 | **Knob shell indexing fixture**: block holding the shell horizontal on a turned plug, index plate with three dowel positions at 120° | a rotary 4th axis ($240–450) | about $20 plus dowels | probe one feature at each index; returning to the same index 10 times repeats within 0.02 mm |
| B6 | Temper parts: fascia coupon, spreader bar, brackets | JLC or SendCutSend one-offs | per part | drawing tolerance; ISO 2768-m where none given |
| B7 | Stand-in springs: 0.7 mm C51000 glued to the faced spoilboard, cut with 1 mm and 0.5 mm end mills | etched prototypes for rate and feel tests only | about $10 per sheet | arm width and thickness measured; spring rate measured on the bench. Not used for fatigue claims |

**Later upgrades (buy only the commodity part; the machine makes the mounts):**

| Upgrade | Buy | Machine makes | Trigger |
|---|---|---|---|
| Spindle | 80 mm 2.2 kW water-cooled with VFD, about $300 (needs 240 V; else 1.5 kW 120 V) | 80 mm clamp plate | router runout or noise limits small-tool work |
| 4th axis | 100 mm rotary, belt about $240 or harmonic about $450 | mounting keys and plate; uses the R2 high spindle position and the spare A output | a part needs continuous rotation, not three indexes |
| Coolant / enclosure | mist kit, panels | brackets | chip control or noise becomes a problem |

## 5. Risks

| Risk | Mitigation |
|---|---|
| Clone rail or screw quality varies | P1 inspection; buy from one seller with returns; never buy used rails or screws |
| Custom controller board slips or has a fault | Bought grblHAL board as fallback; E-stop is hardware (contactor), not firmware |
| Agent CAM crashes the tool | R7 simulation with fixtures plus an air run for every new program |
| Router runout limits 0.5 mm tools | Precision collets; measure runout at P5; spindle upgrade is the fallback |
| Desktop frame is too small for a future part | Send it out; the machine is sized to Temper's small parts on purpose |

## Sources

- PrintNC V4 build guide: https://cncrouterinfo.com/guides/printnc-guide/
- HGR20 + RM1610 kit listing: https://www.ebay.de/itm/256531248970
- NEMA23 / DM542T kit listing: https://ebay.com/itm/334533596538
- Mesa 7i96S (reference price for the LinuxCNC route not taken): https://store.mesanet.com/index.php?route=product/product&product_id=374
- 4th-axis listings: harmonic https://www.ebay.de/itm/404776187148, belt https://www.ebay.de/itm/116571082639
- Spindle kits: https://ratrig.com/products/spindle-kit-80mm-2-2kw-spindle-with-huanyang-vfd-collet-set-water-cooled
- Harmonic gearbox component pricing (why the rotary is bought, not built): https://www.accio.ai/find-product/csf-17-100-2uh
