# C51/C53 controller bring-up pre-mortem (2026-11-26)

Scope: frozen export `build/premortem-c53/` (netlist, BOM, CPL, `controller/` at b77bb230a, `firmware/` at fbd6f5ca9).
Layout copper was out of scope. I read the board file `pcb/controller-routed.kicad_pcb` in the worktree, read-only, only to get
each footprint's KiCad rotation (the export's `placement.json` is stale and has no C51 parts).

**Verdict: do not order with this CPL.** The netlist, the IC pinouts and the firmware pin map agree; I found no
firmware-vs-netlist error. The package fails on assembly data: five LCSC codes introduced by C51/C52 have no entry in
`CPL_ROTATION_OFFSET`, so 12 polarized or multi-pin parts go to JLC at the wrong rotation, including both 100 uF
electrolytics (reversed) and all four gates of the interlock chain.

## Findings

### F1. UNSAFE / DEAD: 12 parts have the wrong CPL rotation (C1, C9, U11, U25, U33, U37, U52, Q2, D10-D13)

`layout/fab.py:137` applies `CPL_ROTATION_OFFSET.get(lcsc, 0)`. The table (`fab.py:45-80`) is keyed by LCSC code and was
last extended at C49. Codes added since then silently get offset 0. I re-ran the audit's own geometry method
(`evidence/fab-loose-ends/cpl-rotation/audit.py` `geometry()`: rotate JLC's numbered pads onto the KiCad numbered pads)
for every non-passive BOM line, using the JLC pad records already committed (`easyeda_pads.json`, `evidence/c51/jlc_pads.json`,
`evidence/c52/jlc_pads.json`). It reproduces the applied offset on all 33 previously audited codes (the ones JLC's
preview confirmed on 2026-10-19) and disagrees on exactly the new ones:

| Parts | MPN, LCSC | JLC package | Needed offset | Applied | KiCad rot | CPL now | CPL should be |
|---|---|---|---|---|---|---|---|
| C1, C9 | UCD1E101MCL6GS, C445471 | CAP-SMD_BD8.0-L8.3-W8.3-RD | 180 | 0 | 180 | 180 | **0** |
| U11, U25, U33 | SN74LVC1G08QDBVRQ1, C840098 | SOT-23-5 ...-BL | 270 | 0 | 0 | 0 | **270** |
| U37 | same | same | 270 | 0 | 90 | 90 | **0** |
| U52 | EMC2301-1-ACZL-TR, C148036 | MSOP-8 ...-BL | 270 | 0 | 90 | 90 | **0** |
| Q2 | BSS138LT1G, C82045 | SOT-23-3 ...-BR | 180 | 0 | 0 | 0 | **180** |
| D10-D13 | BAV199-7-F, C155248 | SOT-23 ...-BR | 180 | 0 | 90 | 90 | **270** |

Fit RMS at the needed offset is 0.03-0.28 mm against 1.8-6.3 mm at the applied one, so none is ambiguous. The result is
also consistent by family: every "-BL" JLC package on this board needs 270 and every "-BR" needs 180.

Why each matters:
- **C1, C9 (UNSAFE).** JLC's footprint for the Nichicon part has pad 1 at +X on the chamfered (positive) side; KiCad's
  `CP_Elec_8x6.2` has pad 1 (+, nets `v15_selv` / `V15_BLW`) at -X. The Panasonic part it replaced (C178539) had offset 0, and
  that is the one the 2026-10-19 preview checked. As written, both 25 V aluminium electrolytics are mounted reversed
  across 15 V. DECISIONS C52 says "polarity stays a JLC-preview item"; the land gate reported its 0.245 mm fit at the
  180 degree rotation and nothing carried that rotation into the CPL.
- **U11, U25, U33, U37 (DEAD).** The C52 stock swap changed the code from C7666 (offset 180, in the table) to C840098
  (a different JLC footprint, needs 270, not in the table). These are SENSOR_LIVE, common_good, the RTD window AND and
  the PERMIT gate. Placed 90 degrees off they cannot sit on the lands; if JLC "corrects" by eye it has a 50 % chance of
  180, which swaps VCC and GND on a SOT-23-5. Either way PERMIT never rises, and four parts may load v3v3.
- **U52 (FEATURE-DEAD, possibly worse).** Face fan controller 90 degrees off. It sits on the I2C bus, whose SCL is the
  GPIO0 boot strap, so a bridged part could also stop the expander or the boot; I cannot predict which pads bridge.
- **Q2, D10-D13 (FEATURE-DEAD).** Fan PWM cascode and the four food-probe clamp pairs 180 degrees off on 3-pin lands;
  D10-D13 pads 1/2 are selv_gnd / RTD2_AVDD.

The stale `fab/fab-notes.md` supports this: its "43 lines corrected" list has no U11, U25, U33, U37, U52, Q2 or D10-D13,
and its NEEDS-PREVIEW list still names C7666 and C178539, which are no longer on the BOM.

**Fix (fab data only, no copper or netlist change):**
1. Add to `CPL_ROTATION_OFFSET`: C445471 180, C840098 270, C148036 270, C82045 180, C155248 180. Regenerate the CPL.
2. Make `fab.py` fail when a polarized or more-than-two-pad BOM code has neither a table entry nor an explicit
   "audited, offset 0" record, and make `check_land_patterns.py` compare its best-fit rotation with the offset the CPL
   uses. Rerun `audit.py` on the C53 board so `audit.csv` and `fab-notes.md` describe this BOM.
3. In JLC's preview check one designator per new code (C1, U11, U52, Q2, D10) before paying.

### F2. DEGRADED to DEAD, not established from files: orientation of the hand-soldered XH/PH headers (J1, J2, J3, J9, J7, J14, J15)

JLC's footprints for these codes number their pads in the opposite direction from KiCad's (geometry offset 180), while
J10, J12 (C144394) and J13 are offset 0. The CPL carries KiCad's rotation for all of them (deliberate, see
`PREVIEW-2026-10-19.md` Result 2, which also records that the connectors were never re-checked after the revert). If JLC's
operators follow JLC's own placement render, the seven headers are fitted turned 180 degrees and their harnesses mate
mirrored. J1, J2, J14 (2-pin NTC) and J3, J9 (4-wire RTD) still work mirrored. **J7 does not:** controller 3V3 (pin 2)
lands on the UI board's GND (pin 11), a short of v3v3. **J15 does not:** 12 V lands on the fan's PWM input.
J9, J14 and J15 are new and have never been through a preview.

**Fix (order process):** check body and key against the silk for these seven in the preview, add a JLC assembly remark
("THT headers: orient to silkscreen outline, key wall as drawn"), and on arrival check each key against
ENCLOSURE-HANDOFF before plugging J7 or J15.

### F3. NOTE, unverified: J4 circuit numbering has only one source

JLC's C277731 footprint is KiCad's `Molex_Micro-Fit_3.0_43045-1600 ... Horizontal` rotated 180 degrees (pads and
numbering), yet the 2026-10-19 preview found JLC's body correct at offset 0 and hanging off the board at +180. So the two
libraries disagree on where circuit 1 is relative to the body, or JLC's 3D model is mis-rotated. The part only fits one way,
so assembly is safe; the question is whether KiCad's numbering matches Molex's. The Molex drawing is still unread
(`evidence/fab-loose-ends/README.md` task 3). A wrong numbering maps pin n to 17-n on a harness that carries PERMIT and
the PWM lines. **Fix:** read Molex 430450201_sd.pdf once; at bring-up, buzz J4.3 (3V3) and J4.9 (PERMIT) against the
power board before mating.

### F4. NOTE (board, optional): U30 CS# has no pull-up

`RTD_CS_N` = U4.18 (GPIO10) -> R44 33 R -> U30.16, nothing else. U15 has R108 and U50 has R136. While the MCU is in
reset, in the bootloader or unprogrammed, U30's CS# floats. Nothing shares the bus then and firmware rewrites the
configuration at boot, so no failure follows; a 10 k to v3v3 would make it defined.

### F5. NOTE (firmware): food-probe CS# latch is written once

`ctrl_board_food_cs_prepare()` writes OUTPUT0 bit 6 = 0 once, in `food_rtd_esp32.c` `create()`. `ctrl_board_food_cs()`
only toggles CONFIG0. If the TCA9555 alone resets, OUTPUT0 returns to FFh and "select" then drives P06 high: the food
probe reads "no reading" until the MCU reboots. Fail-silent, not unsafe. **Fix:** rewrite OUTPUT0 in the select path or
on any expander re-init.

### F6. NOTE: first flash needs a home-made cable, and has no UART fallback

J11 is copper only: 1 3V3, 2 EN, 3 IO0, 4 TXD0, 5 GND, 6 D-, 7 D+, 8 GND. Flashing is USB-Serial-JTAG over a
TC2050-IDC-NL wired to a USB plug (D-, D+, GND; no VBUS needed). U0RXD (GPIO44) is UI_MISO, so a UART bootloader is not
available at J11. This works on a blank module, and EN and IO0 are there for a forced download. Have the cable and a
retaining clip made before the boards arrive.

### F7. NOTE: export hygiene
- `controller/README.md` still says J4.1 is the 15 V input (lines 12, 70, 125); the netlist has `bias_good_j4` there and
  power from J13 through D9. `ORDER.md` is for C48/C49. `pcb/placement.json` has no C51 parts.
- `tools/verify_controller.py` cannot run from the export (it needs `zapote/rtd/circuit/rtd_contract.json`), so I did
  not run it. Its PASS is the designer's claim.
- `inputs/native-21` is the stage-56 snapshot; the board of record is s57. J4 matches s56 pin for pin.
- `controller_board_esp32.c` header: "NOT YET COMPILED against ESP-IDF or run on hardware". `build-evidence/esp-idf`
  suggests it has since been compiled; this lot is still its first run on hardware.
- Pan Rref is now 0.1 % and firmware has no gain calibration (`rtd_convert.c`, fixed 430.0): 0.54 K at 250 C, as
  DECISIONS C52 already states.

## Checked and found correct

**MCU pin map (every GPIO, netlist U4 pad -> module pin -> firmware define).** Module table from the Espressif
ESP32-S3-WROOM-1/1U datasheet, Table 3-1 (downloaded): 4=IO4, 5=IO5, 6=IO6, 7=IO7, 8=IO15, 9=IO16, 10=IO17, 11=IO18,
12=IO8, 13=IO19, 14=IO20, 15=IO3, 16=IO46, 17=IO9, 18=IO10, 19=IO11, 20=IO12, 21=IO13, 22=IO14, 23=IO21, 24=IO47,
25=IO48, 26=IO45, 27=IO0, 28=IO35, 29=IO36, 30=IO37, 31=IO38, 32=IO39, 33=IO40, 34=IO41, 35=IO42, 36=RXD0, 37=TXD0,
38=IO2, 39=IO1. All 36 signals in `controller_pins.h` land on the intended net: PWM HA/LA/HB/LB 4/5/15/16; IL_RESET_N 17;
IL_WDI 18; RUN_EN 14; BUS_FAULT_RB 21; BIAS_GOOD_RB 35; PERMIT_RB 36; RTD CS/SCK/SDO/SDI 10/11/12/13; EXT_ADC_CS_N 42;
CT_ZC 38; LINE_ZC 39; ADC1 CH0/1/5/6/7/8 on GPIO1/2/6/7/8/9; SDA 37; SCL 0; UI SCK/MOSI/MISO/CS_OLED/CS_EXP/DC
40/41/44/47/48/45; FAN_PWM 46; FAN_TACH 3; USB 19/20; TXD0 43. IO35-37 are free on the N8 (datasheet note: taken only on
octal-PSRAM variants). No legacy `temper_pins.h` use in the controller code. Direction, level and pulls in
`controller_board.c` match the netlist (R5-R8 10 k down, R102 4.7 k down, R68/R108/R119/R120 10 k up, R111/R112 4.7 k,
R110/R20 100 k down, R123 1 M down with R124 10 k and C97 1 nF).

**Straps and boot.** GPIO0: 4.7 k up (R111), I2C slaves on the same rail, J11.3 can pull it low. GPIO45: 100 k down (R110),
only the 100 R to J7.10 beyond it. GPIO46: 100 k down plus the FB network, about 0.25 V at reset. GPIO3: tach input,
strap unused. EN: 10 k / 1 uF (R109, C91), on J11.2. Console is USB-Serial-JTAG in `sdkconfig.defaults`; flash settings
suit the N8.

**Reset and unprogrammed defaults.** RUN_EN low by R102 so PERMIT = latch AND RUN_EN is low; `permit` also has R103
10 k down; latch Q has R71 down and is cleared by the TPS3823 reset at power-up. PWM lines low by 10 k. bus_fault reads
"fault" unplugged (R61 up). Blower runs at about 11.2 V (FAN_OFF gate held low by R19 against the expander's 100 k
pull-up). Face fan: EMC2301 power-up watchdog gives 100 % after 4 s. Firmware presets RUN_EN, IL_WDI and UI_DC low
before enabling the drivers and IL_RESET_N high before it.

**Interlock logic, gate by gate from the netlist:** U23/U24 LVC14, U22 74HC30 (inputs 1-6, 11, 12; output 8), U20
LVC1G74 (CLK 1, D 2 high, Q# 3, Q 5, CLR# 6, PRE# 7), U37, U25, U11, U35 open drain with pull-ups, U9 LVC244 read-backs
to the right GPIO and expander bits, U42-U46 capacitive-mode detector, U21 TPS3823 (RESET 1, GND 2, MR 3, WDI 4, VDD 5;
WDI has R69 1 k to ground so a silent MCU times out).

**I2C / SPI.** TCA9555 A0-A2 grounded = 0x20; EMC2301 fixed 0x2F ("The EMC2301 SMBus address is set at 0101_111(r/w)b",
DS20006532A p. 21); 4.7 k pull-ups; 400 kHz. Expander bits: P00/P01 CM OK, P02 RAIL_OK_RB, P05 RTD2_DRDY, P06 RTD2_CS_N
(R136 10 k up, R135 1 k series), P07 RTD_DRDY, P10-P14 read-backs, P15 FAN_OFF, P16 BLW_PG (20 k / 4.7 k), P17
FAN2_ALERT (R155 up): all equal `CTRL_EXP_*`. Register numbers 0-7 correct. SPI2 mode 3 for all three devices (MAX31865
"supports SPI modes 1 and 3"; MCP3202 0,0 / 1,1); SDO lines are high-Z when deselected; init order is rtd_service first,
then the MCP3202 which tolerates the existing bus. UI on SPI3.

**MAX31865 SSOP-20 (U30, U50), every pad.** Datasheet Pin Description table (Maxim 19-6478, SSOP column): 1 DRDY, 2 DVDD,
3 VDD, 4 BIAS, 5 REFIN+, 6 REFIN-, 7 ISENSOR, 8 FORCE+, 9 FORCE2, 10 RTDIN+, 11 RTDIN-, 12 FORCE-, 13 GND2, 14 SDI,
15 SCLK, 16 CS, 17 SDO, 18 DGND, 19 GND1, 20 N.C. Netlist for both parts: 1 DRDY net, 2 v3v3, 3 AVDD (bead + caps), 4+5
tied (BIAS = REFIN+), 6+7 tied (REFIN- = ISENSOR), Rref between them, 8 to connector pin 1, **9 to selv_gnd** (FORCE2:
"When in the 2-wire or 4-wire connection configuration, connect to ground"), 10/11 through the filters to pins 2/3,
12 to pin 4, 13/18/19 ground, 14-17 SPI, 20 open. Footprint is the 5.3 mm SSOP and fits JLC's land to 0.01 mm at the
applied 270.

**Other pinouts against datasheets I downloaded:** EMC2301 MSOP-8 (Table 3-1: SMDATA 1, SMCLK 2, VDD 3, GND 4, PWM 5,
TACH 6, CLK 7, ALERT 8); TCA9555 PW; TPS62933 DRL (RT 1, EN 2, VIN 3, GND 4, SW 5, BST 6, SS 7, FB 8; RT floating =
500 kHz); TLV9031 DBV (OUT 1, V- 2, IN+ 3, IN- 4, V+ 5; the TLV9030 pinout differs and is not used); TLV760 DBZ (OUT 1,
IN 2, GND 3); TPS3890 DSE; TPS3703-Q1 DSE; TPS3823 DBV; SN74LVC1G74 DCU. Buck outputs from the FB dividers: 3.304 V,
12.18 V blower (11.2 V at reset), 12.0 V face fan; EN dividers 1.6 V.

**Polarity in the netlist:** D9 anode V15_BLW, cathode v15_selv; C1/C9 pin 1 positive; ESD diodes cathode on the signal;
BAT54S / BAV199 pin 1 ground, pin 2 rail, pin 3 signal; Q1, Q2 gate 1, source 2, drain 3. CPL offsets of all other ICs and
diodes equal the geometry offset (table in F1 lists the exceptions). BOM, CPL and netlist hold the same 342 designators
with equal MPNs (J11 is copper only).

**Connectors:** J4 all 16 pins equal the frozen s56 power-board netlist; J3, J9 F+ / S+ / S- / F-; J7 equals DECISIONS
C26; J10, J12, J13, J14, J15 and J11 equal ENCLOSURE-HANDOFF.

**Firmware constants against parts:** pan Rref 430 = R39 PTFR0805B430RN9, Pt100, threshold words 35544 / 12844
recomputed; food Rref 4300 = R130 RT0805BRD074K3L, Pt1000, 1 M pull-ups R137/R138 as modelled; 4-wire bit 0, 60 Hz
filter; HS 10 k pull-up and 1.00 k / 5.90 k gain 0.855072; coil 10 k; bay 47 k; rim 1.00 k; VBUS receiver 20 k / 10 k
with 90.9 k / 10 k bias from the 2.5 V reference; RMS gain 1 + 30 k / 10 k; MCP3202 CH1 on the LM4040; EMC2301 register
addresses and IDs (37h / 5Dh).

## Not verified
- AD8436 QSOP-20 pinout (U14): analog.com timed out; the map matches my memory of the datasheet only. Unchanged since C48.
- MAX31865: read from a mirror of the Maxim PDF (makerguides.com copy), not from analog.com.
- SN74LVC1G08-Q1, LVC1G14/32/38/86, LVC74A, LVC244A, LVC14A, 74HC30, MCP3202, SRV05-4, BAT54S, BAV199, 2N7002, BSS138,
  LM4040, REF2025, OPA2388, TLV9062/9061, TLV3201: standard pinouts checked from memory, datasheets not re-read.
- The UI board (not in the export): whether anything on it pulls J7.10 (GPIO45 strap) up.
- The s57 power board against J4 (only s56 is in the export), and the Molex numbering (F3).
- What JLC actually does with a part whose CPL rotation does not fit its lands (F1), and how it orients THT headers (F2).
- Layout, routing, DRC: out of scope.
