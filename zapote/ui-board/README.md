# Fascia UI board (schematic capture)

The UI board of the induction cooktop: one PCB parallel to the fascia, 170 x 81 x 1.6 mm, carrying
- the Newhaven NHD-3.12-25664UCW2 OLED on a 1 x 20 socket (it makes its own 12 V panel supply from 3V3: DECISIONS U3);
- three APEM IPR3PAD2 IP67 buttons (START, STOP, BACK/RESET);
- the socket for the Grayhill 62VG15-H9S-030C encoder's lead, with a comparator that restores its levels (U7);
- an MCP23S08 SPI expander (buttons, encoder, buzzer, TMP122 chip select), a TMP122 temperature sensor and a self-oscillating buzzer;
- one 12-way JST XH jumper (J7, 120 mm) to controller J7 (`../controller`, DECISIONS C26).

**Status:** schematic source, frozen netlist, BOM with LCSC numbers, calcs, an automated verifier with mutation tests, and a mechanical floorplan against enclosure R41. **No layout.** Not fabricated, no physical test. Open items and the questions for the enclosure, firmware and owner are at the end of [DECISIONS.md](DECISIONS.md).

## Results (2026-10-12)

| | |
|---|---|
| Verification | **128 / 128 checks pass** (`evidence/verify.json`) |
| Mutation tests | **21 / 21 caught**, each fails the check that owns it (`evidence/mutations.json`) |
| 5 V (J7.1) | 0.51 mA of 30 mA: unused (OLED boost needs 170 mA at 5 V) |
| 3V3 (J7.2) | 411.9 mA at maxima: 340 OLED + 71.9 board; controller allocation 460 / 120 |
| Rail at the UI | 3.202 to 3.367 V; encoder low-side margin 26 mV (tightest) |
| BOM | 23 lines, 56 placements: 14 basic + 8 extended with LCSC, 1 hand-fitted (IPR3PAD2) |
| Expander map | unchanged from firmware `ui_board_map.h`; GP7 resolved as TMP122 CS# |
| STOP | software, with a "UI lost = stop" rule; hardware option designed, not built (DECISIONS U15) |

## Layout of the unit

| Path | What |
|---|---|
| `elec/src/ui_board.ato` | Top module `UiBoard`: J7 and power, expander, TMP122, OLED socket, buttons, encoder and comparator, ESD, buzzer |
| `elec/src/ui_parts.ato` | Part definitions. Each docstring cites the datasheet table or page its pin numbers were checked against |
| `frozen/` | Reviewed build outputs (`default.net`, `default.csv`, `resolved-components.json`), unit path normalised to `UNIT`, plus `build-receipt.json` |
| `bom/ui-parts.json`, `bom/ui-parts.csv` | Every MPN with LCSC code, JLC library type, stock on 2026-10-12, role and datasheet basis; the CSV is in the JLCPCB BOM layout |
| `inputs/firmware/` | Read-only copy of `ui_board_map.h` at 780eaab89, with its hash |
| `tools/ui_calcs.py` | Every numeric claim: power budget, harness drop, pull-ups, comparator, buzzer drive, ESD, SPI timing, OLED reset. Writes `evidence/ui_calcs.json` |
| `tools/verify_ui.py` | The verification, 128 checks in 13 sections. Writes `evidence/verify.json` |
| `tools/mutate_ui.py` | 21 mutation tests on the netlist, resolved export, BOM and firmware map. Writes `evidence/mutations.json` |
| `tools/floorplan.py` | Board outline, holes, OLED, buttons, encoder, J7 and J2 from the enclosure source; 24 checks; writes `evidence/floorplan.svg` and `.json` |
| `tools/make_bom.py` | Builds the BOM JSON and CSV from the netlist and a part table; `--refresh` re-reads JLC stock (read-only) |
| `tools/freeze.py`, `circuit_export.py`, `netlist.py` | Same as the controller unit's (build with pinned atopile 0.2.69, export, read the netlist) |

## Build, freeze, verify

From `zapote/ui-board`. Offline apart from `make_bom.py --refresh`; no Rust, no workspace build.

```sh
python3 tools/freeze.py            # ato build + export + normalise into frozen/ + receipt
python3 tools/freeze.py --check    # rebuild; fail if frozen/ is stale
python3 tools/ui_calcs.py          # evidence/ui_calcs.json
python3 tools/verify_ui.py         # evidence/verify.json; exit 1 on any failure
python3 tools/mutate_ui.py         # evidence/mutations.json; exit 1 if a defect is not caught
python3 tools/floorplan.py         # evidence/floorplan.svg
python3 tools/make_bom.py --refresh  # re-read JLC stock and rewrite bom/ (read-only query)
```

The raw build is `uv tool run --offline --from atopile==0.2.69 ato --non-interactive build elec/src/ui_board.ato:UiBoard`. It emits only atopile's "Implicit Declaration" deprecation warnings for `override_net_name`, the same as the controller.

## What the verifier checks

- **J7** pin map equal to four independent copies of the controller's (C26 table, ENCLOSURE-HANDOFF row, frozen netlist, `verify_controller.py`), a GND beside every signal, SRV05-4 on every signal, MISO source termination, no pull on D/C or the chip selects.
- **GP map** equal to the firmware header (the copy's hash and `git show` of the commit), each role traced from its GP pin to the physical part, opcode 0x40, the buzzer the only output.
- **Pull-ups:** every expander input has an external pull-up of at most 47 kohm; the encoder levels pass the comparator.
- **Buzzer** default off at reset, low-side N-FET, flyback, current inside the allocation.
- **Power** budgets recomputed from the netlist (5 V at most 30 mA; 3V3 inside the controller's allocation) and the calcs they come from.
- **ESD** on every external-facing line; **OLED** pin map, unused jumper pins open, RC reset; **encoder** map per the Grayhill drawing and comparator thresholds recomputed from the netlist values.
- **Decoupling:** each IC has its own 100 nF (`c_<name>` for `u_<name>`), bulk at J7 and at the OLED socket.
- **BOM:** every MPN has an LCSC code (one named exception), stock recorded and at least one board's worth, CSV equal to JSON, designators equal to the netlist.
- **Floorplan** and **frozen freshness** (sources and outputs equal the receipt).

## Mutation tests

Each mutation edits a copy of the netlist (or BOM, firmware map, resolved export) and must fail the named check, while the unmutated design passes everything: swapped J7 pins (two), a dropped pull-up (three), an inverted buzzer default, the buzzer on the 5 V pin, removed decoupling (two), a swapped GP map, a changed firmware map, a missing LCSC code, zero stock, a pull-up on D/C, swapped encoder A/B, a removed ESD channel, a shorted MISO termination, a grounded clamp Vcc, a removed OLED reset capacitor, a floating BS0 and a bad comparator reference. The list and results are in `evidence/mutations.json`.

## Not verified here

Marked in DECISIONS and the calcs: the SRV05-4 clamp voltage, the AWG28 and XH contact resistances, the ESP32 GPIO-matrix input delay, the encoder's "30 ms" rise time, the buzzer's sound pressure at 3.3 V, the J2 mating orientation, the IPR5PAD2 code, and the text of IEC 60335-1 and 60335-2-6 (not read; the STOP analysis is an engineering reading to confirm with the test lab).
