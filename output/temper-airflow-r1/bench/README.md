# temper-airflow-r1 bench: measure the R45 jet box's board-face h

2026-10-15. This is a ready-to-build kit that measures the area-averaged heat-transfer coefficient h that the R45 jet
box (HANDOFF.md item 1) delivers to native-21's strip (model x 0–90, y 7–23.5 mm). It covers still air, the blower
drive floor (5.5 V), drive 0.55 (6.6 V) and full drive.

**Why it matters:**
- The power stage will not raise the tank ceiling above 18 A until jet h is measured.
- 28 A at a 61 °C bay needs h_top ≥ 97.2 W/m²K (`../board-h-sweep.json`).
- The design basis at drive 0.55 is Martin × 0.6 = 100 W/m²K, with Martin used at Re 520–1150, below its validated
  Re ≥ 2000 (`setpoints.json`).

Every number below is written by a script in this folder and reruns in seconds. Prices are estimates.

## The rig in one paragraph

- **Plate:** a 90 × 16.5 × 3 mm 6061 plate that *is* the strip, heated by two TO-220 resistors underneath.
- **Guard:** the plate sits in a 6061 guard tray (1 mm gap, RTV-sealed) that a PWM loop holds at plate temperature,
  so back and edge losses go to the guard instead of the plate's heat balance.
- **Channel replica:** the jet box and F3 feed legs are printed to HANDOFF's envelope, with jets Ø3.0 at x 5.5 + 11k,
  y 14.0, and the floor 6.0 mm above the plate. The channel is bounded as on s42: the TO-247/BR1 fronts at y 6.9
  under the FR-4 pressure-strip face at y 9.5, and the C38–C41 film-cap blocks at y 23.7. The spent jets therefore
  leave by the same slits, cap gaps and ends.
- **Air supply:** a stand-in for the push hood, fed by the product blower with a taped bleed. The set variable is the
  manifold pressure (SDP810), not blower volts.
- **Logger:** the sensor-r3 ESP32-S3 logger, with more MAX31856 channels, an INA226 for heater power, and the
  guard's PWM output.

## Answer to "how well will it decide?"

From `selftest.json`: four synthetic rig days run through the whole pipeline (zero → gap calibration → runs →
transfer → verdict), with known truth.

| Truth h at drive 0.55 | Fit (95 %) | U95 | Verdict for c28 at a 61 °C bay (needs 97.2) |
|---|---|---|---|
| 125.0 | 123.9 (120.9–126.8) | 2.4 % | PASS |
| 100.0 | 99.1 (97.0–101.1) | 2.1 % | MARGINAL |
| 88.0 | 87.2 (85.4–89.0) | 2.1 % | FAIL |
| 100.0, no flow meter | 100.1 (96.7–103.6) | 3.4 % | MARGINAL |

- **Measurement uncertainty:** about ±2 % (95 %) with the optional flow meter and about ±3.4 % without it. To PASS
  28 A at a 61 °C bay, the measured h must therefore be ≥ 99.2–100.7 W/m²K
  (`c28_bay61_pass_needs_h_ge` in `selftest.json`).
- **What that means for the Martin estimate:** that pass line is Martin × 0.60, which is exactly the design basis.
  If the jets deliver the design value, the bench reads MARGINAL. A clear PASS needs the jets to beat the design
  basis by a few percent. If they don't, `fit.py` reports the lowest swept drive whose lower bound clears 97.2.
- **Not in U95:** replica fidelity. The plate is smooth (no SMD bumps ≤ 1 mm), the surroundings are unheated and the
  rig jets run at room temperature (transferred by Reynolds-number matching). The optional height and bump runs
  bound the first two. See DECISIONS J9.

## Files

| File | What |
|---|---|
| `RIG.md` | Build: parts, machining, printing, wiring, assembly, checks |
| `PROCEDURE.md` | Bench day: zero, calibration, runs, settling, safety |
| `DECISIONS.md` | Why each choice (J1–J12) |
| `plate_design.py` → `plate-design.json` | Plate choice (Al vs Cu vs FR-4 coupon), losses (unguarded vs guarded), heater sizing, time constants, radiation, air heating |
| `setpoints.py` → `setpoints.json` | Manifold pressure in the rig for each product drive (imports `../delivery.py` read-only) |
| `cad/rig_cad.py` → `cad/rig-cad.json`, `cad/*.step`, `cad/*.stl` | Rig CAD, plus geometry checks against HANDOFF (floor 6.0, gaps 1.0 / 1.2, jets open, no overlaps) |
| `logger_fw/jet_logger_fw.ino` | ESP32-S3 firmware (raw records; guard duty commanded from the host) |
| `jet_logger.py` | Host logger and guard loop; `--selftest` → `logger-selftest.json` |
| `fit.py` | zero / gap / run / report / transient; `--selftest` → `selftest.json` |
| `bench.example.json` | Channel map and 1σ uncertainties; copied to `bench.json` on first use |
| `bom.py` → `bom.json` | Lean BOM with estimates |
| `air.py` | Air properties (Sutherland) |
| `demo/` | Interactive walkthrough page `jet-bench-demo.html` (3D rig, air path, simulated bench day). `export_mesh.py` (build123d venv) → `rig-mesh.json`, then `python3 build_demo.py` fills `page.html` from the kit's JSON |

## Rerun

```
python3 plate_design.py          # numpy + scipy (system python3 here: numpy 2.4.6, scipy 1.18.0)
python3 setpoints.py
python3 bom.py
python3 jet_logger.py --selftest
python3 fit.py --selftest        # ~5 s
cd cad && ../../.venv/bin/python rig_cad.py     # build123d 0.11.1
```

CAD venv recipe, from the airflow folder: `uv venv -p 3.12 .venv && VIRTUAL_ENV=.venv uv pip install build123d==0.11.1`.

## Cost (estimates, `bom.json`)

| | USD |
|---|---|
| **Must buy** | **315** (plate and guard 125, sensing 153, drive 21, tools 16) |
| Already on the sensor-r3 lean order (logger) | 48 |
| Shared with the enclosure A1/A3 bench (BFB1012VH-F00 blower) | 25 |
| Optional (flow meter 60, exit-air channel 8) | 68 |

## What the owner must do

1. **Order.** The JLCCNC plate and guard tray (from `cad/plate.step` and `cad/guard_tray.step`), plus the `bom.json`
   must-buy rows. Put them on the same order day as the sensor-r3 kit.
2. **Print and build** per RIG.md. Allow about one day, plus epoxy cure.
3. **Flash and check.** Flash `logger_fw/jet_logger_fw.ino`; it was not compiled here. Run PROCEDURE A–B, then the
   overnight zero.
4. **Bench day:** PROCEDURE C–F, about 7 h. It can share the day with the sensor survey, since one logger serves both,
   one bench at a time.
5. **Report.** Run `python3 fit.py report runs/` and send `results.json` plus the printed verdict to the power-stage
   session.
