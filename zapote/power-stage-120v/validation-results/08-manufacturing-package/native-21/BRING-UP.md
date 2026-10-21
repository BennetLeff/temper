# Prototype bring-up: home-lab overview (2026-10-18; prepared, NOT run)

The order of work for the first native-21 boards, **stage 55** (the board of record, `fab/FAB-NOTE.md`; DECISIONS 82 lists what changed from the previous board), with the C49
(J13-merge) controller, on a home bench that solders through-hole only. It is an overview. The procedure, its numbers
and its pass levels are in `firmware/components/power/COMMISSIONING.md` ("COMMISSIONING" below), and this file only points
to its steps. Where the two disagree, COMMISSIONING wins and this file is wrong. `firmware/tools/commissioning_board_table.py
--check` runs the prose checks on this file too (board-stage claims, power-board resistor values against the frozen BOM,
firmware and Kconfig symbol names, and every COMMISSIONING step named here exists).

## Ground rules (summary; COMMISSIONING "Ground rules" is the full list)
- **BR1 stays out until step 4 passes** (owner decision 2026-10-18; COMMISSIONING bring-up power plan). It is the only part
  that joins mains to the bus. In steps 2–4 PS2 runs from its own input at 120 V, and the bus comes from an isolated,
  current-limited DC supply soldered to the B19 leads. Mains is on the inlet, the filter, F2 / J11, the J3 loop and PS2's
  input from step 2: treat those as live. hv_ret is tied to PE at one point in steps 2–4 only, and the tie comes off
  before BR1 is fitted.
- **Mains chain:**
  - Steps 2–4: wall outlet → GFCI → isolation transformer (1:1, 120 V) → power analyser → inlet. No variac (PS2 needs its
    input range; COMMISSIONING step 2 setup).
  - Step 5, the first time mains reaches the bus: wall outlet → GFCI → isolation transformer → variac → dim-bulb tester (a
    100–200 W incandescent lamp in series) → power analyser → inlet. The bulb stays in for the first raise of the variac and
    step 5 items 1–2 with the bridge idle. Take it out before the first bench session (step 5 item 3): a series lamp moves
    the line the firmware measures and hides the inlet current the estimator is checked against.
  - Behind the isolation transformer the GFCI sees no fault current from the board. It protects the bench wiring only.
- **Never touch the board while it is fed from mains**, at any step. The bench sink and the HOT side are live, and the bench
  insulation is catalogue pad, not the production M11 stack (OPEN-ITEMS M11).
- **HOT-side nodes: isolated or differential probes only.** Never clip a grounded probe to the bus or a switch node.
- **First-power ceiling 17.5 A** until a ladder step passes its thermal gate (COMMISSIONING "Raising the commissioned tank
  ceiling", gate 0, and step 9a item 6).
- Stop at the first unexpected reading and write it down. Do not "try once more".

## What the owner fits, and what JLC does
- **Owner, through-hole:** BR1 (step 4b), RV1 and the two F1 clips. The owner also inserts the F1 cartridge (no
  soldering). This is consign-r1's list (`11-candidates/consign-r1/README.md`, answer 4).
- **JLC:** everything else, including U41 / U42 (SSOP-36, placed from Global Sourcing; consign-r1 answer 2) and the four
  FETs Q2, Q3, Q5 and Q6, consigned from one lot and soldered by JLC. No hot-air gear is needed.
- **Bench heatsink:** `11-candidates/bench-sink-r1/README.md`, revision 3. It is one common sink, with a shim selected per
  FET from feeler-gauge gaps (`scripts/shim_select.py`) and a clamp pad chosen per device. It is fitted to the JLC-soldered
  FETs (§6.2). BR1's fit and preheat are in §6.3, and the TCO is in the J3 loop (D5).

## Order of work
| Phase | What | Where |
|---|---|---|
| Before power | Visual inspection: bridges, polarity (the electrolytics, U41 / U42 pin 1, controller D9 by J13), the owner-fitted parts | this row |
| Before power | Continuity, unpowered: no HOT-to-SELV or HOT-to-PE path except the documented ones (R38, the PE–SELV link; the Y capacitors; the driver and optocoupler barriers). Controller: no short on `v3v3`, `v15_selv` or `V15_BLW`. Controller D9 conducts from J13 toward the logic rail in diode test and blocks the other way | this row |
| Before power | Confirm the fitted parts against the board table (B1, B2, B9, B13, B14) and enter them in the record | COMMISSIONING ground rules, "Board revision" |
| Before power | Build and measure the coil | "The coil" below; `output/temper-coil-r1/` |
| Desk | Host suite, ESP-IDF build, pin-map check | COMMISSIONING step 0 |
| SELV only | Controller alone, bench 15 V into J13 (current limit and checks in step 1). Flash over the Tag-Connect TC2050 with the programmer's 3V3 pin not driven | COMMISSIONING step 1 |
| Mains on PS2, bus dead | Logic and gate supplies, PWM, interlock, BIAS_GOOD (GPIO35) checks; gates disconnected | COMMISSIONING step 2 |
| Mains on PS2, bus from DC | CT, OCP and OVP trip calibration | COMMISSIONING step 3 |
| Mains on PS2, bus from DC | First switching, ZVS, resonance map, phase calibration, with gates and coil connected | COMMISSIONING step 4 |
| Unpowered | The owner fits BR1; hv_ret–PE tie removed | COMMISSIONING step 4b; bench-sink §6.3 |
| Mains to the bus | Variac with the dim bulb, LINE_ZC, VBUS against the line | COMMISSIONING step 5 |
| Heating | Tank ramp with a pan, estimator, thermal, blower and PS3 (including the logic-rail scope at blower start), frequency loop | COMMISSIONING steps 6, 7, 8, 8b, 8c, 9a |

## The coil
Build and measure it per the coil study: `output/temper-coil-r1/BUILD-AND-MEASURE.md` §1 (winding), §2 (measurements M1–M7
and their pass levels), §3 (tune) and §5 (first power), with the traveller of §4. The study's pass levels are:
- M2: free-air L 76–86 µH after tuning, flat ±3 % over 20–60 kHz;
- M3: R_dc ≤ 0.100 Ω;
- M4: loaded L ≥ 41.5 µH on the cast-iron reference pan, ratio L_loaded / L_free 0.47–0.77;
- M5: the ring-down R_ac.
The modelled values these are measured against are in the study's `model/results/TABLES.md`. At first power: no aluminium pan, and stop at 130 °C on any winding thermocouple with stock Litz (§5).

**Coil spec version (settled 2026-10-18).** `docs/hardware/TANK_COIL_SPECIFICATION.md` is now the native-21 reissue (70 µH,
alternate B 80 µH, loaded floor 41.5 µH), with the coil study's corrections to rows 1 and 7. The legacy 88 µH / 53.43 µH version came from
a 270 nF tank and the 44 kHz PLL floor of the half-bridge, not native-21's bank (B14); against it R1 would fail row 3
(`11-candidates/commission-s53/results/coil-floor.md`, from `scripts/coil_floor.py`). R1 is alternate B and passes the reissue.

## Stop conditions (any of these: power off at the mains cut, wait for the bus to discharge, investigate)
- The dim bulb stays bright after the bus has charged (step 5).
- The bus is above B6's release window top: OVP should already have tripped.
- Any gate-drive overlap, or an edge that hard-switches (step 4 item 2).
- An unexpected controller reset.
- Smell or smoke.
- On the IR camera, any part above 100 °C (**provisional**), the bench TCO opening, or a winding thermocouple at 130 °C.
- Tank current above the commissioned ceiling.
- Any reading outside the pass level of the step it belongs to.

## Records to keep
- Photos of both boards before first power, including the shim and pad selected for each FET (bench-sink §6.2).
- The coil traveller: M1–M5 per coil, plus M4 for every pan you will cook on. Send them back to the coil study for its model
  re-anchor (coil README §5, item 6).
- Every value the COMMISSIONING steps ask to record, in its commissioning record ("Commissioning record").
- The logic-rail and v3v3 minimum at blower start (COMMISSIONING step 8c item 7).
- Gate and switch-node waveforms from steps 2 and 4.
- First-power IR images.
- Touch current (OPEN-ITEMS S1, design value only). It is not a COMMISSIONING step and needs its own later setup: IEC 60990
  measures against an earthed supply, and behind a floating isolation transformer it reads near zero. Record it; do not tune
  against it.
