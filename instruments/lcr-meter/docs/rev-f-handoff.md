# Rev F handoff (2026-11-03)

The Rev F LCR meter board is design-complete and ready to order. Nothing has been ordered, and no board exists yet. This page tells you what to do next and where everything is. The reasons behind each decision are in [rev-f-plan.md](rev-f-plan.md) §5, and the evidence is in [validation/README.md](../validation/README.md).

## State

- **Branch:** `study/lcr-in-box`, worktree `worktrees/lcr-in-box`. Pushed; HEAD `a44d910c2`.
- **Board:** `cad/temper-lcr.kicad_pcb`, SHA256 `490892127c7f1713881aaff3e4493406874ff5b9f9b311f81d124b095d4a76ca`. 100 × 100 mm, 4 layers, hand-routed.
- **Gerber zip:** `manufacturing/temper-lcr-gerbers.zip`, SHA256 `136174bec23403516eb5eb845dabfd5e772a32eeb032b4c81d62a2a6c2b5f4ae`. It is gitignored; `cad/rebuild.sh` regenerates it.
- **Gates on that board:** ERC 0, DRC 0/0/0, schematic parity 0, JLC fab pass PASS, independent check 674 pins / 0 findings, current check 0 FAIL, regulators 51 PASS / 2 FLAG (accepted), start-up model 128/128, hot-plug 96/96 under 6.5 V. The analog copper is identical to `6ae693082`, the board the parasitic extraction and stability sweep ran on.
- **Parts:** 223 components, 220 fitted, 216 SMT placements, 69 JLC lines (27 extended). Estimate for 5 boards: $357.43 economic (`manufacturing/order-estimate-5.json`).
- **Firmware:** `firmware-rev-e/`, commit `f13087113`. It covers the datasheet-audit items: bus-powered 500 mA, a rail start gate, codec quick-charge, the clock fallback with a `STATUS` command, and range "unknown" until the first RANGE command. Host tests pass and the UF2s are rebuilt. It has never run on a board.

## Changes since the 2026-10-29 board

All are recorded in rev-f-plan §5 and the audit README `validation/datasheet-audit-rev-f/README.md`.

- **U17 LM3880 sequencer and C117 330 µF.** Without them the TPS65131 converters started together against the TPS2553 limit and the board hiccupped. Model: `validation/power-spurs/startup_surge.py`.
- **R121 1.5 Ω in C113's ground leg.** A USB-A plug-in rang U16 IN to 10.4 V against its 7 V abs max; it now peaks at 6.24 V worst case. Model: `validation/power-spurs/hotplug_spice.py` (ngspice).
- **Value changes:** C113 4.7 µF, R101 1 Ω, C62 2.2 µF.
- **Test pads TP15–TP21:** I2S and USB_VBUS.
- **TI SBAA634A (codec):** common-mode tolerance mode 1 is characterized now. At 40 kΩ it gives 101 dB SNR and CMRR is 47 dB (`codec.md` addendum).

## To order

The JLC quote of 2026-10-30 in `manufacturing/fab-quote.json` was on the board *before* R121, so upload again. Only the owner signs in, adds to the cart or pays.

1. **PCB.** At cart.jlcpcb.com/quote, upload `manufacturing/temper-lcr-gerbers.zip`. It should detect "4 layer board of 100x100mm". Settings:
   - FR-4, qty 5, 1.6 mm, green/white, TG135, ENIG 1 µ".
   - 1 oz outer, 0.5 oz inner copper.
   - Via covering **Plugged** (Tented is greyed out), 0.3 mm minimum via, flying-probe test.
   - Expect $25.70.
2. **Edge rails.** Select "Edge rails added by JLCPCB" and paste this remark: *"V-cut edge rails on the left and right edges only (the edges perpendicular to the BNC edge); no rail on the BNC edge or the opposite edge; ship depanelized or with rails, either is fine"* (`manufacturing/FABRICATION.md`). Not yet priced; the 2026-10-30 quote had no rails.
3. **Assembly.**
   - PCB Assembly: Economic, top side, qty 5, tooling holes by JLCPCB, **Confirm Parts Placement: Yes**.
   - Upload `manufacturing/bom-jlcpcb.csv` and `cpl-jlcpcb.csv`.
   - Expect 69 lines, with C22769 (R121) new.
4. **Y1 (ABM8-272-T3, C20625731).** JLC stock was 0 on 2026-10-30 and is **8,071 on 2026-11-03**, so it should just match. If it shows a shortfall again, pre-order it from LCSC into the JLC parts inventory. Do not substitute: the RP2040 hardware guide §2.3 tunes R10/C12/C13 to this crystal, and no JLC 10 pF part meets its 50 Ω / 200 µW (decision 2026-10-30).
5. **Order remark, Y1.** Add "Y1: orient by pad geometry; the chamfer mark is unreliable".
6. **Placement preview.**
   - **Already passed on 2026-10-30:** C117 + on the south land, U17 pin 1 north-west, U1, K1–K4 stripe at pin 1, and the +/− markers of D5–D8 and D15–D20.
   - **Still to check:** Y1 by pad geometry (pins 1/3 are the crystal, 2/4 the lid; 90° off means no USB), R121 present, and D4's lens toward the front (BNC) edge.
   - Do not use the viewer's arrow buttons: they move the selected part. If the undo arrow goes active, undo.
7. **DFM at order.** JLC shows no DFM before an order. Accept its review of the 33 exposed-pad thermal vias (Plugged). Filled-and-capped is an acceptable paid answer if asked.
8. **Record the result.** Update `manufacturing/fab-quote.json` (gerber_quote, assembly_quote) and the receipt in `validation/README.md`. Never add to the cart or pay; the owner does that.

## When boards arrive

Follow [bring-up-rev-e.md](bring-up-rev-e.md) in order. Rev F-specific steps:

- **§1a Indicator LEDs:** check them first.
- **§2a Start-up:** scope 5 V, ENP and ENN from attach. Expect ENP at about 46 ms and ENN about 8.5 ms after it, with 5 V ≥ 3.86 V.
- **§2a step 3 Hot-plug:** at the VB pad (TP20), test 1 m and 2 m cables and one **USB-A to C** cable. The model predicts ≤ 6.24 V. If it reads higher, record the cable and rerun `hotplug_spice.py` with it.
- **§3 step 3 Codec clock:** run `temper-lcr codec PORT` and the new `STATUS` at 187.5 kHz; CLK_DET_STS0 must show bin 10. On a clock error the firmware falls back automatically. Also confirm all three channels (2 ADC + 1 DAC) run above 48 kHz; TI's "Sampling Rates and Programmable Processing Blocks" report could not be found.
- **§3 step 4 I2S edges:** probe TP15–TP18 with GND at TP19. the codec needs ≤ 10 ns; the estimate is about 5.7 ns at the default 4 mA drive. If edges are slow or ringing, set drive and slew in firmware.
- **§6 step 4 Codec passband / CM_TOL:** this only confirms that SBAA634A's 1 kHz numbers hold at 27–85 kHz.
- **§10 Relay capacitances (optional):** measure a loose TQ2SA's contact-to-coil and pole-to-pole capacitance (unpublished; the stability stress set brackets it), then rerun the stability case the step names.

## Not established (bench only)

- Calibrated accuracy and noise.
- Codec behaviour at 187.5 kHz in wideband mode.
- Real hot-plug peaks.
- Relay-internal capacitances.
- The DAC image level.
- Cal-standard self-capacitance.
- **DUT jacks have no protection.** Discharge DUTs to under 5 V and verify with a DMM. A clamp design is a Rev G study (audit AFE-01 to AFE-04).
- **Accepted FLAG:** about 0.46 A from USB at attach, before enumeration. USB 2.0 allows 100 mA; most hosts tolerate it.

## How to rebuild and check

Run from `instruments/lcr-meter`. KiCad Python is `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.

- **Routes are hand-specified** in `cad/tools/rev_f_routes.py`. Placement and parts are in `cad/tools/rev_f.py`. Never use Freerouting or any autorouter.
- **Rebuild:**
  1. Run `python3 cad/tools/rev_f.py --check` (pre-DRC). When it asks, first run `<kicad-python> cad/tools/silk_library.py`.
  2. Then run `RENDER_PYTHON=~/.local/share/temper/renderenv/bin/python sh cad/rebuild.sh`. The renderenv holds pygerber 2.4.3 and cairosvg 2.9.1.
- **Gates after a change:**
  - `<kicad-python> validation/independent_check.py f`
  - `python3 validation/power-spurs/current_check.py`
  - `python3 validation/power-spurs/regulator_check.py`
  - `python3 validation/power-spurs/startup_surge.py`
  - `sh validation/layout-parasitics/copper_delta.sh 6ae693082`: the analog copper must stay identical, or the extraction and stability sweep must be rerun.
  - `<kicad-python> cad/tools/pour_report.py -o validation/pour-report-rev-f.json`
  - `<kicad-python> manufacturing/order_estimate.py [2]`
- **Prices:** `python3 manufacturing/prices/fetch_jlc_parts.py` writes `manufacturing/prices/jlc-parts-<today>.json`. `order_estimate.py` reads a fixed dated file, so change it to the new file.
- **SPICE on the tailscale box:** `ssh bennet@100.121.239.87`. Tailscale SSH sometimes asks for a browser check that the owner must approve. Run `conda activate temper-spice` (ngspice 41); the run directory is `~/lcr-spice/` (mirror `validation/...` and `cad/design.json`). Before a heavy job, check `free -g` and `~/temper-fem/HEAVY-RUN.txt`.
- **Firmware:** the host tests are `cc -std=c11 -DLCR_FS_375K={0,1} -Isrc test/test_host.c src/*.c` minus `main.c` and `usb_descriptors.c` (see `firmware-rev-e/README.md`). The SDK 2.2.0 and Arm GNU 14.2.rel1 toolchain are under `~/.local/share/temper/`.

## House rules that apply here

- Never `git stash`.
- Stage explicit paths, and run `git diff --cached` before each commit.
- Never order, add to cart, or enter credentials.
- Numeric claims need a committed script that reproduces them.
- Record decisions in rev-f-plan §5.
- Vendor PDFs are not committed; cite them by URL and hash.
- JLC assembles everything SMT; the home bench does through-hole only.
