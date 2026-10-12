# Fascia UI board (schematic capture), revision 2: owned controls

The UI board of the induction cooktop: one PCB parallel to the fascia, 170 x 81 x 1.6 mm, plus a small separate **sensor tab** behind the fascia at the knob axis. Revision 2 (2026-10-12) follows the owner's decision: the Grayhill encoder and the APEM buttons are gone; the controls are PCB tact switches under owned metal caps and a removable magnetic knob read through the 3 mm 5052 fascia by a TMAG5170 3D Hall sensor. It carries
- the Newhaven NHD-3.12-25664UCW2 OLED on a 1 x 20 socket (it makes its own 12 V panel supply from 3V3: DECISIONS U3);
- three C&K KSC223G LFG tact switches (START, STOP, BACK/RESET; U27);
- the TMAG5170A1QDGKR on the sensor tab, with a 10-way harness (U23, U26);
- a **CS qualification** (one NAND and two OR gates) so that the sensor's and the TMP122's selects are honoured only while the expander and the OLED are idle (U20-U22);
- an MCP23S08 SPI expander (buttons, sensor select and ALERT, buzzer, TMP122 select), a TMP122 temperature sensor and a self-oscillating 85 C buzzer (U28);
- one 12-way JST XH jumper (J7, 120 mm) to controller J7 (`../controller`, DECISIONS C26), **pin map unchanged**.

**Status:** schematic source, frozen netlist, BOM with LCSC numbers, calcs, an automated verifier with mutation tests, a mechanical floorplan against enclosure R41 and a reply to the owned-controls requirements ([REPLY-TO-OWNED-CONTROLS.md](REPLY-TO-OWNED-CONTROLS.md)). **No layout.** Not fabricated, no physical test. Open items are U32 in [DECISIONS.md](DECISIONS.md).

## Results (2026-10-12, revision 2)

| | |
|---|---|
| Verification | **190 / 190 checks pass** (`evidence/verify.json`) |
| Mutation tests | **38 / 38 caught**, each fails the check that owns it (`evidence/mutations.json`) |
| CS qualification | `CS_dev# = GPx OR NAND(CS_EXP#, CS_OLED#)`: selected only for GPx = 0, CS_EXP# = 1, CS_OLED# = 1 (8-row table per device from the netlist); deselected at reset; MISO high-Z unless qualified-selected |
| Select / release timing | CS_dev# moves within 18.8 ns of CS_EXP#; margins 936 ns (tsu_cs 45 ns) and 31 ns before the first expander clock |
| Sensor | TMAG5170A1, +/-100 mT, 16x averaging, XYZ continuous, 200 Hz reads at 1 to 2.5 MHz (5 MHz margin 13 ns) |
| Stray-field angle error | at most 0.173 degree (bare, no pan, 60 kHz, unfiltered, hot magnet); 0.027 degree assembled; p-p jitter 0.35 to 0.45 degree in pan or assembled cases, **0.69 degree in the bare no-pan transient (over the 0.5 target)** |
| 3V3 (J7.2) | 385.3 mA at maxima: 340 OLED + 45.3 board; headroom 74.7 mA of the 120 mA non-OLED allocation |
| 5 V (J7.1) | 0.51 mA of 30 mA: unused |
| Buzzer | GSD9605YB-5V2800 (85 C) at (u, v) = (-95.0, 24.0); predicted body 69.9 to 83.9 C |
| Sensor datum | Hall centre (110.000, 53.000, w -4.00); tab front face w -4.78; steel keep-out R 25 |
| BOM | 22 lines, 51 placements: 11 basic + 10 extended with LCSC, 1 consigned (tact, 0 stock at JLC) |

## Layout of the unit

| Path | What |
|---|---|
| `elec/src/ui_board.ato` | Top module `UiBoard`: J7 and power, expander, TMP122, OLED socket, tact switches, ESD, buzzer, CS qualification gates, sensor-tab harness and the tab's parts |
| `elec/src/ui_parts.ato` | Part definitions. Each docstring cites the datasheet table or page its pin numbers were checked against |
| `frozen/` | Reviewed build outputs (`default.net`, `default.csv`, `resolved-components.json`), unit path normalised to `UNIT`, plus `build-receipt.json` |
| `bom/ui-parts.json`, `bom/ui-parts.csv` | Every MPN with LCSC code, JLC library type, stock and price on 2026-10-12, role and datasheet basis; the CSV is in the JLCPCB BOM layout |
| `inputs/firmware/` | Read-only copy of `ui_board_map.h` at 780eaab89, with its hash (its ENC_A/B/SW bits are repurposed here) |
| `tools/ui_calcs.py` | Every numeric claim: power, harness drop, pull-ups, buzzer drive and temperature, ESD, SPI timing, CS timing and sequence, magnet field, stray-field angle error, sensor configuration and schedule, sensor-tab temperature. Writes `evidence/ui_calcs.json` |
| `tools/verify_ui.py` | The verification, 190 checks in 16 sections. Writes `evidence/verify.json` |
| `tools/mutate_ui.py` | 38 mutation tests on the netlist, resolved export, BOM and firmware map. Writes `evidence/mutations.json` |
| `tools/floorplan.py` | Board outline, holes, OLED, tact switches, J7 and J8, sensor tab, keep-outs, buzzer and Hall datums from the enclosure source; 47 checks; writes `evidence/floorplan.svg` and `.json` |
| `tools/make_bom.py` | Builds the BOM JSON and CSV from the netlist and a part table; `--refresh` re-reads JLC stock and price (read-only) |
| `tools/freeze.py`, `circuit_export.py`, `netlist.py` | Same as the controller unit's (build with pinned atopile 0.2.69, export, read the netlist) |
| `REPLY-TO-OWNED-CONTROLS.md` | The answers to the five items requested in `UI-BOARD-REQUIREMENTS.md` |

## Build, freeze, verify

From `zapote/ui-board`. Offline apart from `make_bom.py --refresh`; no Rust, no workspace build.

```sh
python3 tools/freeze.py            # ato build + export + normalise into frozen/ + receipt
python3 tools/freeze.py --check    # rebuild; fail if frozen/ is stale
python3 tools/ui_calcs.py          # evidence/ui_calcs.json
python3 tools/verify_ui.py         # evidence/verify.json; exit 1 on any failure
python3 tools/mutate_ui.py         # evidence/mutations.json; exit 1 if a defect is not caught
python3 tools/floorplan.py         # evidence/floorplan.svg
python3 tools/make_bom.py --refresh  # re-read JLC stock and price and rewrite bom/ (read-only query)
```

The raw build is `uv tool run --offline --from atopile==0.2.69 ato --non-interactive build elec/src/ui_board.ato:UiBoard`. It emits only atopile's "Implicit Declaration" deprecation warnings for `override_net_name`, the same as the controller.

## What the verifier checks

- **J7** pin map equal to four independent copies of the controller's (C26 table, ENCLOSURE-HANDOFF row, frozen netlist, `verify_controller.py`) and a literal, a GND beside every signal, SRV05-4 on every signal, MISO source termination, no pull on D/C or the chip selects.
- **GP map:** GP0 Start, GP1 Stop, GP2 Back, GP6 buzzer, GP7 TMP122 equal to the firmware header (the copy's hash and `git show`); GP3 the sensor select (only through the gate), GP4 ALERT, GP5 spare; the select not on a fixed GP.
- **CS qualification (`cs`):** the exhaustive 8-row truth table of each gated device and the 16-row MISO driver table, both evaluated from the netlist; both devices deselected at reset (the pull level on the GP net); CS# pull-ups; TMAG5170 pin map with TEST grounded; the 390 ohm SDO resistor against the 10 mA limit; the timing and sequence checks of the calcs.
- **Tact, removed, tab:** three Y31B13136FPLFG on GP0-GP2 with pull-up, series resistor and clamp; no Grayhill, APEM, comparator, J2, encoder net or 70 C buzzer anywhere (netlist and BOM); the J8-J9 harness pin map.
- **Buzzer:** default off at reset, low-side N-FET, flyback, current in the allocation, rating at least 1 K above the predicted worst body temperature.
- **Power:** budgets recomputed from the netlist (5 V at most 30 mA; 3V3 inside the controller allocation with at least 70 mA of headroom) and the calcs they come from.
- **ESD:** the buttons and the tab inputs are clamped; no chassis, PE or fascia net exists on the board (the discharge path is mechanical). **OLED:** pin map, unused jumper pins open, RC reset.
- **Decoupling:** each IC has its own 100 nF (`c_<name>` for `u_<name>`). **BOM:** every MPN has an LCSC code (the tact is the one named exception), stock and date recorded, CSV equal to JSON, designators equal to the netlist. **Floorplan** and **frozen freshness**.

## Mutation tests

Each mutation edits a copy of the netlist (or BOM, firmware map, resolved export) and must fail the named check, while the unmutated design passes everything. Carried over (swapped J7 pins, dropped pull-ups, inverted buzzer default, buzzer on 5 V, removed decoupling, swapped GP map, changed firmware map, missing LCSC, zero stock, pull-up on D/C, removed ESD channel, shorted MISO termination, grounded clamp Vcc, removed OLED reset capacitor, floating BS0). New: gate bypassed (sensor, TMP122), wrong gate polarity, either NAND input tied high, missing CS pull-up (sensor, TMP122), sensor select on the wrong GP, sensor selected at reset, TMP122 always selected (MISO contention), SDO resistor too small, TEST floating, harness pins swapped, the 70 C buzzer back, the APEM button or the encoder socket back, the wrong tact, a fascia net on ground, a tab clamp channel removed, missing gate decoupling, zero TMAG stock. The list and results are in `evidence/mutations.json`.

## Not verified here

Marked in DECISIONS and the calcs: the SRV05-4 clamp voltage, the AWG28 and XH contact resistances, the ESP32 GPIO-matrix input delay, the sensor noise values (read from a plot), the buzzer's sound pressure at 3.3 V and its rating (listing only), the KSC2 drawing, footprint pad pairing and bounce time, the JST SH envelope, the 55 kHz stray field, the tab's temperature model, and the text of IEC 60335-1 and 60335-2-6 (not read; the STOP analysis is an engineering reading to confirm with the test lab).
