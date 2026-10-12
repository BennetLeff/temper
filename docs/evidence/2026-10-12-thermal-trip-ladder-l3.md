# Thermal trip ladder for the integrated controller and IPW65R018CFD7 (2026-10-12)

This supersedes the IGBT-era reasoning in `2026-08-15-thermal-threshold-decision.md` for the integrated SELV controller (`zapote/controller`, layout L3). Decision record: `zapote/controller/DECISIONS.md` C32. Numbers: `zapote/controller/tools/controller_calcs.py thermal_trips()`, checked from the frozen netlist by `zapote/controller/tools/verify_controller.py` (section "thermal").

## Why the 2026-08-15 ladder no longer applies

That ladder was 75 °C warn → **80 °C firmware trip** → **85 °C hardware latch** → 125 °C fault-state backstop. Its basis no longer holds:
- **Wrong device.** It was argued for the IGBT IKW40N120H3 (Tvj max 175 °C). The power stage now uses 4× **IPW65R018CFD7** (Tj max 150 °C; design target 125 °C, power-stage `requirement.py:17,37`).
- **Below the operating point.** The R32 air path holds the sink base at **88.6 °C** at full power (R_SA 0.29 °C/W, `output/temper-manufacturing-r32/evidence/airflow-r32/REPORT.md`). The firmware fan law regulates to that point (`thermal_mgmt.h` `FAN_SINK_SETPOINT_C 88.6f`). An 80 °C firmware trip and an 85 °C hardware latch would therefore trip in normal operation.
- **Coil out of step too.** The coil hardware trip (120 °C) also sat below the coil fan setpoint (140 °C) and the 150–160 °C derate band.

## FET junction budget (IPW65R018CFD7)

Per FET, junction to sink: **θjc 0.28 °C/W** (datasheet RθJC max; power-stage task 03 round 3 README:51) plus **θcs 0.634 °C/W** (2 mm AlN plus 2× grease, the conservative end of 0.399–0.634; `requirement.py:7`), 0.914 °C/W in total.

At 28 A on basis A (power-stage task 05 round 6, `board_side.py`, commit 18318042c), per-FET loss gives **Tj ≈ T_sink + 27.8 K**.

| Sink | Tj | Against |
|---|---|---|
| 88.6 °C (fan setpoint) | ≈ 116 °C | |
| 95 °C (firmware trip) | ≈ 123 °C | 125 °C design target |
| 104.6 °C (hardware trip, high corner) | ≈ 132.4 °C | ≥ 15 K below the 150 °C maximum |

## The ladder (coordinator decision 2026-10-12)

| | Fan law | Firmware derate | Firmware trip | Hardware trip, nominal (64-corner band) |
|---|---|---|---|---|
| Heatsink | 88.6 °C | — | 95 °C | 101.4 °C (98.3–104.6) |
| Coil | 140 °C | 150–160 °C | 165 °C | 175.7 °C (169.7–182.0) |

The coil sensor changes to a 100 k / 300 °C glass NTC (Semitec 104GT-2 class), because the Vishay NTCALUG01A104GA lug is rated to 150 °C only.

## Change request to the firmware session (not made on the controller branch)

- **`firmware/config.yaml` `OVER_TEMP_THRESHOLD`:** 80.0 → **95.0** °C, with its doc text pointing here; then regenerate `config.h` with `firmware/tools/gen_config.py`.
- **Tests pinning 80 °C:** `firmware/test/test_safety.c:41`, `firmware/test/test_state_machine.c:922` and `firmware/test/test_sil_fault_injection.c:588` (`INV_MAX_HEATSINK_TEMP`).
- **Legacy `fan_guard.c`:** `T_MAX 80.0f` is superseded by the `thermal_mgmt` fan law.
- **Recovery:** `state_machine.c:518`, heatsink < 70 °C, may stay; it is below the hardware release band (83.0–88.2 °C).
- **Coil sensor curve:** `THERMAL_NTC_COIL` changes from Vishay curve 11 to the Semitec 104GT-2 table. The coil trip 165 °C stays.
