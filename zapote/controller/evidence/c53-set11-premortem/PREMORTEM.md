# Bring-up pre-mortem: controller C53 set-11 board (5d3ff39c2) with firmware fbd6f5ca9

> Archived copy (2026-11-28) of the independent report on the frozen export of commit 5d3ff39c2 (board `e82e6140…`). Paths in it are relative to that export. Its scripts are in `scripts/`. Dispositions: DECISIONS C53, set 11 review.

Date: 2026-11-28. Reviewer: fresh agent, frozen export only. Nothing was ordered, committed, pushed or sent.

## Verdict

**ORDER.** I found no reason in the netlist, copper, BOM, CPL or Gerbers for this board to come back dead, unsafe or unable
to run the firmware. No copper, BOM or CPL change is asked for.

Four things have to happen in the order flow and on the bench, and none of them is carried by a document that matches this
board today (M1). They are the MAJOR findings below:

1. Order with **epoxy-filled and capped vias**: 138 vias sit inside SMD pads (M3).
2. In JLC's placement preview, check the **key wall of J7 and J15** (and the other five JST headers) against the silk, and
   the **"+" pad of C1** (M2).
3. **Check each header's key on arrival** before plugging J7, J15 or J13 (M2, m5).
4. **Build the J11 USB lead before the boards arrive**; it is the only way to flash (M4).

## Scope: what I read

All paths are under `build/premortem-s11/`.

**Board**
- `controller/frozen/default.net`, `resolved-components.json`, `build-receipt.json` (sha256 of the netlist `8471186c…`,
  equal to the receipt and to `evidence/verify.json` `inputs`).
- `controller/pcb/controller.kicad_pcb` (sha256 `e82e6140…`, equal to `evidence/convergence.json` `board_sha256`), the
  vendored footprints `pcb/libs/Connector_Molex.pretty/*`, `Connector.pretty/Tag-Connect_TC2050-IDC-NL_*`.
- `controller/fab/bom-jlcpcb.csv`, `cpl-jlcpcb.csv`, `fab-notes.md`, `gerbers/*`, `controller-gerbers.zip`.
- `controller/elec/src/controller.ato` (MCU, debug, J4 sections), `controller_parts.ato` (pin tables and docstrings).
- `controller/README.md`, `ORDER.md`, `LAYOUT.md` (head, convergence rows), `DECISIONS.md` (C18, C41, C49–C53 in full,
  open items), `ENCLOSURE-HANDOFF.md` (connector rows).
- `controller/evidence/`: `land-patterns.json`, `fab-loose-ends/README.md`, `cpl-rotation/easyeda_pads.json`,
  `PREVIEW-2026-10-19.md`, `c51/jlc_pads.json`, `c52/jlc_pads.json`, `c53-order/stock-read.json`, `convergence.json`,
  `verify.json` (inputs and section counts), `layout-check.json`, `fab-review.json`, `jlc-dfm.json` (status fields).
- `controller/layout/fab.py` (rotation table, THT handling, export options).
- `controller/inputs/native-21/default.net`, `resolved-components.json`, `provenance.json` (power stage, branch
  `claude/native21-s55-unified` @ `f0c669a86`).

**Firmware**
- `components/hal/include/controller_pins.h`, `controller_board.h`, `temper_pins.h`, `emc2301.h`;
  `components/hal/controller_board.c`, `emc2301.c`, `esp32/controller_board_esp32.c`, `esp32/hal_init.c`,
  `esp32/hal_spi_esp32.c` (bus and device set-up).
- `components/power/include/n21_pins.h`, `n21_hw_esp32.c` (ADC pattern, MCP3202, GPIO set-up, reset pulse, captures),
  `Kconfig`, `CMakeLists.txt`.
- `components/sensors/rtd_service.c` (bootstrap), `include/rtd_service.h`, `rtd_food_service.h`, `max31865.h` (config words).
- `components/safety/safety.c` (watchdog, boot reason), `main/main.c`, `main/food_rtd_esp32.c`,
  `main/platform/ui_board_map.h`, `platform_esp32.c` (first 180 lines), `sdkconfig.defaults`, `partitions.csv`,
  `README.md` (pin map, BIAS_GOOD), `build-evidence/esp-idf/README.md`, `test/fixtures/controller-layout/`.

**Not in the export, so not read:** the earlier pre-mortem and layout-review reports that DECISIONS C53 cites
(`evidence/c53-premortem/`, `evidence/c53-layout-review/`), the sibling units `verify_controller.py` needs
(`zapote/rtd`, `interlock`, `thermal-sense`), and the power stage beyond its netlist snapshot.

**What I ran** (scripts in `_scratch/`; outputs there are small):

| Script | What it does | Result |
|---|---|---|
| `nl.py` | Parses the frozen netlist with resolved MPNs into `comps.txt` / `nets.txt` | 343 components, 243 nets |
| `dump_pcb.py`, `parity.py` | Every pad's net on the board against the netlist; BOM and CPL against both | 0 mismatches; BOM 342 refs = CPL 342 = netlist minus J11 |
| `rotcheck.py` | My own rotation check: JLC's numbered pads placed at the CPL position and rotation, against our pads | Every SMD code fits (worst 0.35 mm RMS); 6 THT codes (8 headers) fit only at +180 (M2) |
| KiCad `kicad-cli pcb drc --schematic-parity` | Independent DRC on the board file | 0 errors, 0 unconnected, parity 0, 27 warnings |
| Gerber re-plot from a scratch copy of the board | Diff against `fab/gerbers` ignoring date lines | 13 layers and both drill files identical |
| `holes.py`, `pwr.py`, `vip.py` | Drill counts, power-net widths, via-in-pad count | PTH 1379 / NPTH 5 = the drill files; 138 vias in SMD pads |
| `tools/check_controller_pinmap.py --ato controller/elec/src/controller.ato` | The firmware's own pin-map gate, pointed at this board's source | PASSED (36 GPIOs, 14 expander bits) |
| `idf_build.sh` | ESP-IDF v5.3.6 build of a scratch copy of the firmware with `CONFIG_TEMPER_POWER_HW_BINDING=y` | exit 0, `induction_cooker.bin` 453,392 bytes, 7 warnings |

**One slip to report:** my first DRC run wrote KiCad's local-settings file `controller/pcb/controller.kicad_prl` into the
export (git-ignored, 2 kB). I deleted it; the directory listing is back to the seven original entries and the board file's
sha256 is unchanged. Later KiCad runs used a scratch copy.

`tools/verify_controller.py` could not be re-run: it needs sibling units that are not in the export. Its committed result
is for this netlist hash, and I did not rely on it.

## Findings

### DEAD / UNSAFE

None found.

### MAJOR

**M1. There is no order document for this board. `ORDER.md` describes the C49 board.**
- Evidence: `controller/ORDER.md:3-5` says "The C51 order package is written after layout". Its upload table
  (`ORDER.md:43-48`) gives zip `53f5addd…`, BOM `259acf19…` (89 lines), CPL `2327ec70…` (288 placements, 9 THT). The files in
  `fab/` are zip `978ef705…`, BOM `bd689c1d…` (96 lines), CPL `d74fcbbb…` (342 placements, 11 THT). §2 still consigns R39;
  this board has eleven THT headers and consigns nothing.
- DECISIONS C53 F2 (`DECISIONS.md:967`) says "ORDER gets three steps" for the THT headers. `ORDER.md` has none of them.
- The record is also open-ended: `DECISIONS.md:1241` ends at "Set 11 runs 3 fresh runs on this code". The set-11 result is
  only in `LAYOUT.md:201-211` and `evidence/convergence.json`.
- How checked: sha256 of the three fab files; grep of `ORDER.md` for the THT, via and PS3 items.
- Consequence: the owner has no checklist that matches what is uploaded. M2 and M3 are exactly the steps that would be
  missed.
- Fix (document only): write the set-11 order section from `fab/fab-notes.md`: the three hashes above, 6 layers
  JLC06161H-3313, ENIG, epoxy-filled and capped vias, Standard PCBA, 96 lines / 342 placements / 11 THT, nothing
  consigned, the preview list, PS3 = MPM-90-15ST.

**M2. Seven JST headers can be soldered in backwards, and the CPL cannot prevent it. J7 or J15 reversed does damage.**
- Evidence: JLC's footprints for C158012 (J1, J2), C144395 (J3, J9), C158027 (J7), C131337 (J14) and C157991 (J15) number
  their pins 180° from ours. In `rotcheck.py` they miss by 2.0–17.4 mm RMS at the CPL rotation and fit at 0.0–0.14 mm at
  +180. `fab/fab-notes.md:17-24` lists them; `layout/fab.py:92-104` keeps KiCad's rotation on purpose.
- An XH or PH header fits its row of holes either way round. The key wall is the only thing that tells the operator.
- What a reversed header does (netlist pin order, `_scratch/comps.txt`):
  - **J7** (UI bus): pin 2 `v3v3` and pin 11 `selv_gnd` swap, and pin 1 `V5_UI` lands on `J7_CS_EXP_N`. The UI harness then
    shorts the 3.3 V rail to ground through the UI board.
  - **J15** (face fan): pins become GND, PWM, FG, 12 V, GND. The fan's PWM lead gets 12 V and its supply lead gets the PWM
    line.
  - J1, J2, J14 (two-pin NTCs) and J3, J9 (four-wire RTD: 1↔4 and 2↔3 swap force with force and sense with sense) work
    either way.
- J10, J12 and J13 agree with JLC's numbering (0.0 mm), so the render is right for them. A hand-insertion error is still
  possible; see m5 for J13.
- Could not establish: whether JLC's body outline for these XH parts follows its own pin numbering. The 2026-10-19 preview
  only settled J4 (its body hung off the board at +180).
- Fix: three order steps. (1) In the placement preview, compare each header's key wall with our silk and rotate it there
  if it is 180° off. (2) Add an assembly remark naming J7 and J15. (3) On arrival, check the key wall of J7, J15 and J13
  against the silk before anything is plugged in.
- **C1 and C9 belong to the same preview pass.** They are 100 µF electrolytics across 15 V, and their code C445471 has
  never been seen in a JLC preview (`fab-notes.md:24`). My check agrees with the CPL: JLC pad 1 is at +X at rotation 0 and
  our "+" pad is at the larger X (C1 "+" at X 89.05, C9 "+" at X 133.65, board frame). What I cannot check is that JLC's
  pad 1 is the positive terminal. One look at the "+" marker settles it.
- Also on the never-previewed list, one part per code: U11 (C840098), U52 (C148036), Q2 (C82045), D10 (C155248). All four
  fit by pad number in my check (0.04, 0.03, 0.30, 0.21 mm).

**M3. 138 vias are inside SMD pads. The order must be epoxy-filled and capped.**
- Evidence: `_scratch/vip.py` counts 138 vias whose centre is inside an SMD pad: 57 in resistor pads, 54 in IC pads
  (16 of them under the module U4), 18 capacitor, 6 diode, 3 transistor. All are 0.3 mm drill, 0.6 mm pad.
- DECISIONS C53 m8 (`DECISIONS.md:1044`) accepts via-in-pad "with JLC's epoxy fill and cap, which becomes an order-form
  item". `fab-notes.md:8` says it is JLC's default for six layers and up.
- Consequence if the order goes in with tented or plugged vias: solder wicks down open barrels in about 120 small pads.
  Expect tombstoned 0603s and starved IC joints on a board with 342 placements.
- Could not establish: what the JLC form defaults to today, and whether it adds cost. It is read on the quote page.
- Fix: on the order form, confirm "Via covering: epoxy filled and capped" before paying, and put it in the order section
  of M1.

**M4. The board can only be flashed over USB on the J11 pads, with a lead that has to be made.**
- Evidence: J11 is a copper-only TC2050 land: 1 `v3v3`, 2 `MCU_EN`, 3 `I2C_SCL_BOOT` (GPIO0), 4 `UART0_TX`, 5 GND,
  6 `USB_DN` (GPIO19), 7 `USB_DP` (GPIO20), 8 GND, 9/10 open (`_scratch/comps.txt`, J11). The module's RXD0 (GPIO44) is
  `UI_MISO` and reaches J7 only (`controller_pins.h:87`), so there is no UART download path.
- J11 has no USB VBUS pad. USB alone does not power the board; it needs 15 V on J13.
- The pad numbers follow Tag-Connect's layout (1–5 in one row, 10–6 in the other, pad 1 opposite pad 10), which is 1:1 with
  the pins of the cable's 2×5 ribbon socket.
- What to have on the bench before the boards arrive:
  - Tag-Connect **TC2050-IDC-NL** (no-legs, 10-pin, 0.1 in ribbon socket), and a retaining clip (TC2050-CLIP) if the
    console is to stay connected. The back of the board is clear under J11.
  - A cut USB cable or USB breakout wired to the ribbon socket: **D− to pin 6, D+ to pin 7, GND to pin 5 or 8. Leave
    VBUS unconnected.** Keep the wires short.
  - Two jumpers or push-buttons: pin 3 (IO0) to GND and pin 2 (EN) to GND. A blank or crash-looping module can keep
    re-enumerating; holding IO0 low while pulsing EN puts the ROM in USB download mode. GPIO46 reads low there (100 k
    pull-down), which the ROM requires.
- Could not establish: whether the TC2050 plug body clears C91, whose pads are 3.5 mm from the land's centre line against a
  3.37 mm courtyard half-width. It is 0.17 mm outside the courtyard.
- Fix: none on the board. Make and test the lead first.

### MINOR

**m1. The firmware builds for this board, but the committed build evidence is older than the C49 and C51 code.**
- `build-evidence/esp-idf/README.md` is dated 2026-10-12; `components/power/Kconfig:5-9` says the binding "compiled clean
  against ESP-IDF only before the J13 edits of 2026-10-18".
- I built a scratch copy of fbd6f5ca9 with ESP-IDF v5.3.6 and `CONFIG_TEMPER_POWER_HW_BINDING=y`: exit 0, 453,392 bytes
  (78 % of the 2 MB app partition free), 7 warnings of the kinds the old evidence lists. Console is USB-Serial-JTAG,
  flash 4 MB / 80 MHz on the 8 MB module.
- The default Kconfig leaves the power binding off, and with it on the default mode is INHIBITED (pads low). That is the
  right state for first power-up. The firmware has not run on hardware.

**m2. U30's chip select has no pull-up.** `RTD_CS_N` (GPIO10) goes to U30 pin 16 through R44 only; U15 (R108) and U50
(R136) have 10 k. From reset until `rtd_service_bootstrap()`, and for the whole of a flash session, the pan MAX31865's CS#
floats. No bus contention follows (the other two devices are deselected), and the bootstrap rewrites the configuration.
Already accepted as F4 in DECISIONS C53; I agree. Do not read meaning into U30's registers before the firmware has
initialised it.

**m3. "SAFE MODE" can appear in the boot log for a reason that is not a fault.** `check_boot_reason()` (`safety.c:196-218`,
called at `main.c:273`) reads SUP_RUN_OK once. The TPS3823 holds its output low for about 200 ms after power-up and pulses
it low again every 1.6 s or so while WDI is not toggled, which is the case during a flash (timing from memory of the
datasheet, not re-read). A boot that lands in a pulse logs "Rebooted due to EXTERNAL Hardware Watchdog". Nothing outside
`safety.c` reads the safe-mode flag, so the effect is the log line and one `pwm_disable_all()`.

**m4. BIAS_GOOD reaches GPIO35 at 0.813 × VDD.** The power board drives it from an SN74LVC1G17 on `v3v3` through R146
220 k; the controller adds R124 10 k in series and R123 1 M to ground. That is 2.68 V on a 3.30 V rail against the
ESP32-S3's VIH minimum of 0.75 × VDD (2.48 V; value from memory of the datasheet's DC table, not re-read). It works and is
ratiometric, with 6 % of VDD in hand, as long as the pin stays high-impedance. The firmware configures it with no pull
(`n21_hw_esp32.c:672-677`). Measure it at bring-up.

**m5. J13 has no reverse-polarity protection on the fan branch.** D9 protects the logic rail only. A reversed PS3 harness
puts −15 V across C9 (electrolytic) and the VIN pins of U2 and U51. Check the harness with a meter before the first plug.
PS3 must be the MPM-90-15ST (`DECISIONS.md:745`); `README.md:135` and `LAYOUT.md:26` still name the IRM-60.

**m6. J4 circuit numbering is still unread from Molex, but the two footprints agree with each other.**
- Both ends use KiCad's Micro-Fit footprints: right-angle 43045-1600 here, vertical 43045-1612 on the power board. I
  compared their geometry in KiCad's library. In both, pins 9–16 are the latch-side row and pin 1 is bottom-right looking
  into the mating face with the latch up. For the right-angle part that assumes the latch is on top, away from the board.
  A harness wired 1:1 between two 43025-1600 receptacles therefore joins pad n to pad n.
- JLC's library numbers the right-angle part the other way round relative to its body (the 2026-10-19 preview plus the pad
  record). That does not affect assembly, since the part fits one way, and it is not evidence about Molex's numbering.
- All 16 nets match the power-stage snapshot by name, pin for pin (`_scratch` dump of both netlists). The snapshot is
  stage 55/56; I could not check it against the s57 board of record.
- Fix: bring-up step. Buzz J4.3 to the power board's 3.3 V net and J4.9 to its PERMIT net through the harness before
  powering the pair. Do the same for any bought cable assembly, whose wiring pattern I could not establish.

**m7. PERMIT cannot be seen high on a bare board, by design.** The latch needs every source healthy: J4.10 low (open reads
fault through R61), NTCs on J1 and J2, a PT100 on J3 with the MAX31865 bias on, the heartbeat running, and `v3v3` inside
the TPS3703 window. The checklist below gives the stand-ins.

**m8. The 3.3 V window is tight by design.** README gives 21 mV between the regulator's low corner and the supervisor's
release threshold. If RAIL_OK_RB never reads high, measure `v3v3` at C20 before suspecting the latch: below about 3.22 V
the supervisor is entitled to hold RAIL_OK low. The fix would be R13/R14, not copper.

**m9. Stale text that will mislead at bring-up.** `README.md:65` quotes netlist `c0808194…`, 285 components and 233 checks
(now `8471186c…`, 343 components); `LAYOUT.md:3` says 284 parts. The BOM's last column, "JLC stock (latest check)", is not
the latest read: it shows 59 for C14663 and blanks for 18 lines, where `evidence/c53-order/stock-read.json` (2026-11-27)
has every line in stock. Thin lines in that read: AD8436 28, MCP3202 31, TPS3703-Q1 52, RT0603BRD078K06L 68, TPS389001 96,
TLV9031 222. Re-read them on order day.

## Checked and fine

**Firmware against the netlist, pin by pin**
- All 36 module pins: the net on each pad of U4 (module pin table in `controller_parts.ato:21-61`, datasheet v1.8 Table
  3-1) equals the `CTRL_GPIO_*` number for that net. PWM 4/5/15/16, IL_RESET_N 17, IL_WDI 18, RUN_EN 14, BUS_FAULT_RB 21,
  BIAS_GOOD_RB 35, PERMIT_RB 36, RTD bus 10/11/12/13 with SDO = MISO on 12 and SDI = MOSI on 13, EXT_ADC_CS 42, CT_ZC 38,
  LINE_ZC 39, ADC1 on 1/2/6/7/8/9 with channel = GPIO − 1, I2C SDA 37 / SCL 0, UI 40/41/44/47/48/45, FAN_PWM 46,
  FAN_TACH 3, USB 19 (D−) / 20 (D+), TXD0 43.
- The firmware's fixture copy of `controller.ato` differs from this board's only in the five C52 MPN swaps (13 diff lines).
- TCA9555 U8: A0/A1/A2 (pins 21/2/3) on ground gives 0x20. P00/P01 CM read-backs, P02 RAIL_OK_RB, P05 RTD2_DRDY, P06
  RTD2_CS_N, P07 RTD_DRDY, P10–P13 fault read-backs, P14 SUP_RUN_OK_RB, P15 FAN_OFF, P16 BLW_PG, P17 FAN2_ALERT: all equal
  `CTRL_EXP_*`. INT is unconnected and unused. P03/P04 are open (internal pull-ups).
- EMC2301 U52 at its fixed 0x2F on the same bus; no address clash.
- Sense of every read-back through U9 (SN74LVC244A, both enables grounded): LATCHED_FAULT_RB is the latch's Q̄ (high =
  fault), RTD_FAULT_RB follows the open-drain NAND (high = fault), SUP_RUN_OK and RAIL_OK high = good, CM_x_OK high =
  healthy. All as `ctrl_exp_decode()` reads them.
- SPI2: mode 3 at 500 kHz (MAX31865) and 800 kHz (MCP3202); U30 SDO, U50 SDO and U15 DOUT share `RTD_SDO` through 33 Ω,
  1 k and 33 Ω and are all tri-state when deselected. U50's CS# is driven only through the expander, with the output latch
  written before the pin is made an output.
- MAX31865 wiring matches the firmware's configuration: BIAS tied to REFIN+, REFIN− to ISENSOR, FORCE2 grounded (4-wire),
  Rref 430 Ω (pan, `MAX31865_RREF_OHM`) and 4.30 k (food, Pt1000). DRDY is push-pull into the expander.
- ADC: the n21 pattern's six channels are the six ADC1 pads above.
- Pins the firmware drives that the board does not connect: none. Board signals the firmware does not use: P00, P01, P05,
  P17 (diagnostic), UART0_TX (ROM log).
- No controller source includes the legacy `temper_pins.h`; `hal_init()` configures no pins.

**Straps, boot and reset**
- GPIO0: R111 4.7 k to `v3v3`; the only other loads are the SCL pins of U8 and U52 and J11.3. Reads 1 at reset.
- GPIO45: R110 100 k to ground, 100 Ω to J7. Reads 0 (3.3 V flash).
- GPIO46: R20 100 k to ground, plus 68.3 k to the blower buck's 0.8 V feedback node. That is 0.48 V worst case without
  the pad's own pull-down, against a 0.25 × VDD = 0.83 V limit.
- GPIO3: pulled up through the tach network; ignored unless an eFuse is burnt.
- EN: R109 10 k and C91 1 µF. Nothing else drives it but J11.2.
- Module is the N8 (JLC's record for C2980297 is titled ESP32-S3-WROOM-1U-N8), so GPIO35/36/37 are free.
- Wi-Fi is disabled in `sdkconfig.defaults`, so the missing antenna on the U.FL does no harm.

**Interlock and PERMIT**
- PERMIT (J4.9) has one driver, U37 = PERMIT_LATCH AND RUN_EN. R103 10 k pulls it down here; R71 pulls the latch output
  down; R102 4.7 k pulls RUN_EN down.
- Latch U20 (SN74LVC1G74): D and PRE# on `v3v3`, CLR# = `all_good`, CLK = inverted IL_RESET_N. At power-up RAIL_OK and
  the watchdog output are both low, so CLR# is held and the latch starts cleared.
- The ESP32-S3's power-up glitch on GPIO17 would clock the latch, but CLR# is low then, and RUN_EN (GPIO14, glitch
  direction low) still gates PERMIT. The PWM pads' glitches are low-going, and the lines have 10 k pull-downs.
- Firmware hang: WDI stops, the TPS3823 output drops within about 1.6 s, `common_good` falls, the latch clears and stays
  cleared. The watchdog output does not reset the MCU.
- Brown-out: TPS3703 trips RAIL_OK, which clears the latch through two paths (RAIL_FAULT and SENSOR_LIVE).
- Capacitive-mode flip-flops U42: with RUN_EN low, one is preset and the other cleared, so CAP_FAULT is low (healthy)
  until the first PWM edge.
- Pull directions: `bus_fault` up (open wire = fault), IL_RESET_N up (idle), WDI down (watchdog armed, not floating),
  SENSOR_LIVE down, all four PWM down. No floating CMOS input in the netlist (single-node nets are all outputs, NC or
  documented float pins).
- Power side: PERMIT feeds two NAND gates with BIAS_GOOD that drive the drivers' DIS pins, so PERMIT high = run.

**Power**
- J13 → `V15_BLW` → D9 (cathode on `v15_selv`) → logic. Nothing joins the two rails but D9.
- U1 3.3 V: 0.8 V × (1 + 22.1 k / 7.06 k) = 3.304 V. EN divider 100 k / 12.1 k turns on near 11.2 V.
- U2 blower: 12.2 V with GPIO46 driven low, 11.2 V with GPIO46 floating at reset, 5.4 V at full duty; about 12.5 V for a
  moment at start while C10 charges.
- U51 face fan: 0.8 V × (1 + 140 k / 10 k) = 12.0 V.
- All capacitors on the 15 V nets are 25 V or 50 V parts.
- With the power stage absent every rail is present; `bus_fault` reads fault. With only J11: no VBUS pad, so no power;
  feeding 3.3 V into J11.1 would back-feed the whole 3.3 V rail and is not a supported way to power the board.

**Assembly data**
- Board against netlist: every pad's net equal, footprints equal, 0 unconnected, parity 0.
- BOM against netlist: every designator's MPN and footprint equal; LCSC code equal to `bom/controller-parts.json`.
- LCSC code against part: JLC's own title for all 96 codes is our MPN (9 differ only in spacing or case), and JLC's
  package for each agrees with our footprint (`stock-read.json`, read 2026-11-27).
- Resistor values against Yageo, Panasonic and RESI MPN codes: all decode to the netlist value.
- CPL: positions equal the board (THT at the pad centroid, U4 at its pad box centre). Every SMD rotation puts JLC's pad
  numbers on ours, including the polarized and multi-pin parts: D9 0.04 mm, ESD5Z 0.01, BAT54S / BAV199 0.21, SOT-23-5
  codes ≤ 0.16, TPS62933 0.10, TPS3703 0.02, MAX31865 0.01, TCA9555 0.16, AD8436 0.08, EMC2301 0.03, module pads 1–40
  0.02 mm. R32's code has no JLC pad record; it is a two-pad resistor.
- DNP and board-only: J11 and FID1–3 are excluded from BOM and CPL by footprint attribute. Nothing is consigned.
- Gerbers and drill files are exactly what this board file plots; the zip holds the same 16 files (drill maps left out).
- Pinouts cited by the project that I checked from memory: MAX31865 SSOP-20, TCA9555 PW, SN74LVC244A, LVC1G74 DCU,
  LVC74A, 74HC30, LVC14, MCP3202, TPS3823, TPS62933 DRL, LM4040 DBZ, BAT54S, BAV199, 2N7002, BSS138, SRV05-4, REF2025.
  TPS3890 DSE (1 SENSE, 2 GND, 3 MR, 4 VDD, 5 CT, 6 RESET) and TLV9031 DBV (1 OUT, 2 V−, 3 IN+, 4 IN−, 5 V+) I confirmed
  by a web search of TI's datasheet pages on 2026-11-28, not by reading the PDFs. TPS3703 DSE, TLV760 DBZ, EMC2301 and
  AD8436 rest on the project's cited tables: not independently established.

**Connectors**
- J4: see m6. J10 blower: V_BLOWER, GND, FG. J15: GND, 12 V, FG, PWM, GND, the standard four-wire fan order plus a
  ground. J3 / J9: F+, S+, S−, F−. J12: rim NTC, return, drain. J14: bay NTC, PH so it cannot take an XH lead.
- Plugs that fit a wrong header (same XH size), and what happens: J10 / J12 (three-way: a rim cable in J10 puts
  V_BLOWER across the 100 k NTC, a blower in J12 gets 3.3 V through 1 k; no board damage). J3 / J9 (four-way: a Pt1000
  on the pan channel reads far too hot and trips, the safe direction). J1 / J2 (two-way: coil and heatsink NTCs swapped
  shift both hardware trip points; label the harness). J15 and J7 are the only five-way and twelve-way headers.

## What I could not establish

- Molex's own circuit numbering for 43045-1600 (drawing not read; m6 rests on KiCad's two footprints agreeing).
- That JLC's pad 1 on C445471 is the positive terminal (M2).
- JLC's body orientation for the XH and PH headers at the CPL rotation (M2).
- JLC's current default and price for via filling on six layers (M3).
- TC2050 plug clearance to C91 (M4).
- The power stage beyond the stage-55/56 netlist snapshot: whether the s57 board of record changed J4, and what its
  outputs do with mains off.
- Datasheet values quoted from memory are marked where they appear. I read no vendor PDF in this review.
- Layout quality beyond DRC, parity and power-net widths (V_BLOWER and V15_BLW are on 0.8 mm outer-layer tracks with
  feed pours; not re-derived for 2.7 A). That is the layout review's job, not this one.

## Bring-up checklist: first power-up

Do the steps in order. Stop at the first one that fails.

**Before power**
1. Check the key wall of J7, J15 and J13 against the silk, then the other headers. Check the "+" stripe side of C1 and C9
   and the band on D9 (the band is at the lower-X end, away from J13).
2. Meter, unpowered: J13.1 to J13.2 not shorted; `v3v3` (J4.3) to ground (J4.2) not shorted; J7.2 to J7.3 not shorted.
3. Check the PS3 harness polarity with a meter: J13 pin 1 is +15 V (m5).

**First power: 15 V bench supply on J13, limit 0.3 A, nothing else connected**
4. Current settles well under the limit (logic only; no blower, no UI).
5. Rails: `v15_selv` about 14.5 V (C1); `v3v3` 3.24–3.37 V (C20 or J4.3); V_BLOWER about 11.2 V at J10.1;
   V12_FAN2 12.0 V at J15.2; V5_UI 5.0 V at J7.1; `ref2v5` 2.500 V (U13 pin 1).
6. Straps with the module in reset or blank: EN about 3.3 V, GPIO0 (J11.3) about 3.3 V, GPIO45 (J7.10) 0 V.
7. Safe state: J4.9 PERMIT 0 V; J4.5–8 PWM 0 V; J4.10 reads about 3.3 V (pulled up, no power board).
8. Watchdog alive: U21 pin 1 pulses low about 200 ms every 1.6 s or so while no firmware toggles WDI.

**First flash**
9. Connect the J11 lead (M4). The host should enumerate an Espressif USB JTAG/serial device. If it keeps reconnecting,
   hold pin 3 (IO0) to ground, tap pin 2 (EN) to ground, release IO0 after it enumerates.
10. Flash the default build (binding off, or on with INHIBITED). Expect the boot banner on the USB console. "SAFE MODE"
    once after a flash is m3, not a fault.
11. Expect in the log: TCA9555 answers; EMC2301 "programmed" within a second; MAX31865 faults if no PT100 is fitted.

**Interlock on the bare board (the binding built in, INHIBITED)**
12. Fit stand-ins: 10 k across J1 and across J2; a 100 Ω resistor on J3 wired four-wire (pins 1+2 one end, 3+4 the
    other); J4.10 jumpered to J4.15 (ground).
13. Expander read-backs: RAIL_OK_RB high, SUP_RUN_OK_RB high, RTD/HS/COIL fault bits low. LATCHED_FAULT_RB stays high
    until the firmware sends a reset request (a 20 µs low pulse on IL_RESET_N, GPIO17). I did not establish whether the
    INHIBITED mode sends one; if it does not, use a BENCH-mode build (COMMISSIONING.md) to send it.
14. With the latch set, remove one stand-in at a time (J4.10 jumper, a J1 resistor, the J3 resistor): LATCHED_FAULT_RB
    goes high each time and PERMIT stays 0 V. Hold EN low: U21 pin 1 drops within about 1.6 s and the latch clears.
15. PERMIT never rises while RUN_EN (GPIO14) is low. Confirm on a scope through a reset and a power cycle.

**Fans and sensors**
16. Raise the supply limit to 4 A. Blower on J10 runs near full speed at reset; tach edges at GPIO3; FAN_OFF (P15) stops
    it. Face fan on J15 starts at 100 % within 4 s of power or of a firmware stop.
17. Bay NTC on J14, rim NTC on J12, PT1000 on J9: plausible readings in the 10 s log line.

**With the power board (mains off first)**
18. Confirm the power board is stage 50 or later: J4.1 carries BIAS_GOOD, not 15 V.
19. Buzz the harness: J4.3 to the power board's 3.3 V, J4.9 to its PERMIT, J4.2 to ground (m6).
20. Mate. `v3v3` at the power board 3.24–3.39 V. J4.10 now low. BIAS_GOOD at GPIO35 is 0 V with PERMIT low, and at least
    2.6 V within 2 ms of PERMIT going high (m4).
21. From here follow `firmware/components/power/COMMISSIONING.md`. The first PWM edge can trip CAP_FAULT if the CT
    polarity is reversed: that is R72 (remove to flip), DECISIONS open item 15.
