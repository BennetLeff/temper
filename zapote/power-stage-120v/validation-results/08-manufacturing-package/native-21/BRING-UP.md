# Prototype bring-up procedure (2026-10-18; prepared, NOT run)

A plan for the first powered tests of the s53 power board with the C49 controller, for a home lab that has through-hole soldering only. Built from
what the repo records; nothing here has been run. Steps that depend on a fact I could not verify are marked **TBD**. The firmware ladder above the first
ceiling follows `firmware/components/power/COMMISSIONING.md` and is not repeated here.

## Ground rules
- **Never touch the board while it is powered from mains.** The heatsink and the HOT side are live until the real insulation stack is fitted (OPEN-ITEMS M11).
  Catalogue pads are for bench tests only: they are not reinforced insulation (IEC 60335-1 29.3.1).
- **Chain, in this order:** wall outlet, GFCI, isolation transformer (1:1, 120 V), Variac, dim-bulb tester (a 100-200 W incandescent lamp in series), board.
  Everything downstream floats, so it is the board that is isolated, not the Variac.
- **Measure HOT-side nodes only with a differential probe or a battery scope.** Do not clip a grounded probe to the bus.
- First-power ceiling is **17.5 A** (`TEMPER_POWER_TANK_CEILING_DA=175`, DECISIONS 61). Do not raise it without the COMMISSIONING gate.
- Stop at the first unexpected reading. Write it down. Do not "try once more".

## Equipment (owner's purchases; none ordered)
Isolation transformer, Variac, dim-bulb tester, GFCI outlet, differential probe (or battery scope), LCR meter (40 kHz), DMM, bench supply 15 V with current limit,
Tag-Connect TC2050-IDC-NL cable plus a USB breakout (3V3 not back-fed), hot-air gear for U41 / U42, IR thermometer or camera.

## Stage 0: before any power (unpowered)
1. Visual: solder bridges, part orientation (polarity: D9 on the controller, the electrolytics, U41 / U42 pin 1), consigned parts fitted (the 15 hand-fitted power-board parts,
   R39 on the controller).
2. Continuity and isolation with a DMM, board unpowered: no continuity between HOT (bus, switch nodes) and SELV (selv_gnd), nor between HOT and PE, other than the
   documented parts (R38 0 ohm PE-SELV link, the Y capacitors, the driver and optocoupler barriers).
3. Controller: no short on `v3v3`, `v15_selv`, `V15_BLW`; D9 forward-biased from J13 to the logic rail (diode test: about 0.3-0.5 V from J13.1 to the 3.3 V buck input).
4. Coil: measure L (40 kHz, free in air, then under the pan) and DCR. Spec: 88 uH +/-10 %, loaded at least 53.4 uH, DCR at most 0.12 ohm
   (`docs/hardware/TANK_COIL_SPECIFICATION.md`). A coil far outside this changes the resonance: re-run the tank tolerance sweep before using it.

## Stage 1: controller alone, no mains (SELV)
1. Bench 15 V, current limit 0.5 A, on J13 (V15_BLW). Expect: `v15_selv` about V15_BLW minus 0.3-0.5 V, `v3v3` = 3.30 V +/-3 %, quiescent current from the 15 V
   supply about 0.3 A (the logic budget is 4.83 W).
2. Flash through J11 (TC2050) with the 3V3 pin NOT driven by the programmer. First flash of the blank module should enumerate over USB in the ROM download mode;
   if not, hold IO0 low at reset.
3. Check: PERMIT low, all four PWM outputs low, `BLW_PG` high (V15_BLW present), `BIAS_GOOD_RB` (GPIO35) low with nothing on J4, RAIL_OK read through the expander.
4. Scope the logic rail (`v15_selv`) while a **bench-fed blower is started** (J10 connected to the real fan): the request's bench item 5. Record the dip, and whether the
   controller resets. Pass: no reset with the PS3-equivalent supply at its normal current limit (at least 5 A). The fan's start current is the number DECISIONS C49 lacks.

## Stage 2: power board SELV side and gate drive, no mains, no bus
- **TBD:** the HOT-side gate-drive bias (PS2, V24_RAW) is mains-fed. Whether a bench 24 V can be injected in its place without PS2 is not verified; trace it on the schematic
  first. If it cannot, skip this stage and do the gate-drive check in stage 3 with the bus held at zero by the Variac.
1. With bias present and no bus: drive the gates from the controller (firmware test mode, PERMIT granted). Check gate waveforms at U1 / U2 outputs with the differential
   probe: dead time about 499 ns, no overlap, turn-on slower than turn-off (68 ohm on, 1 ohm plus diode off), no ringing beyond the F6 study.
2. Verify the interlock: remove PERMIT (RUN_EN low) and confirm the gate outputs go low within the expected time; with BIAS_GOOD forced low, the drivers disable.

## Stage 3: mains, no coil, Variac at zero
1. Chain connected, Variac at 0 V, dim bulb in. Raise slowly: 30 V, 60 V, 90 V, 120 V, pausing at each step. The bulb should glow only briefly while the bus charges.
2. At 120 V, no switching: PS2 and PS3 outputs in range, `BIAS_GOOD` behaviour as the firmware README (low until PERMIT), bus voltage reading in the controller,
   no heating at the bridge or the filter.
3. **Touch-current measurement** (S1: 0.2412 mA against 0.25 mA, margin 8.8 uA) with the IEC 60990 network or an equivalent, at 120 V 60 Hz and with the inlet module fitted
   (it must have no Y capacitors, or the budget fails). Record, do not tune.

## Stage 4: tank, reduced power
1. Coil and bank fitted, a pan on a non-conductive spacer. Variac at 30-40 V, bulb in. Start the firmware's resonance search at reduced power.
2. Watch: tank current (the firmware ceiling and the CT/OCP trips), the switching frequency (35-60 kHz window), IR temperature of the FETs, the shunt, R10 and the bank.
3. Step the Variac up in 10-20 V steps only while all limits hold. Remove the bulb only after a clean run at full line voltage and low power.
4. Climb the ceiling per `COMMISSIONING.md` (never skip a step). Stop at 17.5 A until the B3 thermal gate passes at the next step.

## Stop conditions (any of these: power off, wait for the bus to discharge, investigate)
Bulb stays bright; a bus voltage above 290 V; any gate-drive overlap; a reset of the controller; smell, smoke or a part above 100 C on the IR camera; tank current above
the ceiling; any reading that disagrees with the model by more than the margin in the relevant study.

## Records to keep
Photos before power, the measured L, Q and DCR of the coil, the logic-rail dip at blower start, touch current, gate waveforms, first-power IR images. Put the numbers
in `DECISIONS.md` so the models can be corrected against them.
