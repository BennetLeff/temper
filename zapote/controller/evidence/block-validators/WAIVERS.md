# Block-validator waivers on the controller layout (DECISIONS C34)

Every finding that is not `pass` in the three verdict runs (`results/controller-interlock.json`,
`results/controller-thermal.json`, `results/controller-rtd.json`) is listed here with its reason. Nothing
else is waived. The validators, their contracts and the unit profiles are unchanged; the only profile
differences are the ones C30 already used (`profile-controller.json`: no host connector, CS GPIO 10, DRDY
on the expander).

Counts: `summary.json` (this rerun) against `summary-before-C34.json` (the C30 run on commit `0207a6974`).

| Validator | Before (pass / fail / indet) | After | Fails left | All of them waived below as |
|---|---|---|---|---|
| Interlock | 69 / 6 / 5 | 70 / 5 / 5 | 5 | W1 (5) |
| Thermal-sense | 86 / 14 / 7 | 88 / 9 / 7 | 9 | W1 (4), W2 (5) |
| RTD | 5 / 165 / 6 | 5 / 18 / 5 | 18 | W1 (16), W3 (2) |

**C44 rerun, repeated on the C45 board and the three C47 convergence boards (current `results/`, `summary.json`: convergence run 3, sha256 `77ed3751…`; identical counts on all, and on the C44 board `969936fb…`):** interlock **69 / 6 / 5**
(+1: `aggregate` exact MPN, W6), thermal-sense **88 / 9 / 7** (unchanged), RTD **5 / 33 / 5** (+15: the C37
sense filter and J3 protection, W7). Fails: interlock W1 (5) + W6 (1); thermal W1 (4) + W2 (5); RTD W1 (16) +
W3 (2) + W7 (15). Indeterminates unchanged. The RTD binder now takes `--deviations rtd-deviations-c37.json`
(W7); without it, it aborts on the census, as it would already have done on C36's `r_avdd_top` swap.

**C53 rerun (current `results/`, `summary.json`): the C51 six-layer board, convergence set "placement fix" run 1
(`pcb/controller.kicad_pcb` sha256 `11265a33…`).** Interlock **68 / 7 / 5** (+1 fail), thermal-sense **87 / 10 / 7**
(+1 fail), RTD **5 / 40 / 5** (+7 fails). Every added fail is W8. Indeterminates are unchanged. Two tool changes, both
DECISIONS C53:
- The validators now read a six-layer export (`Board.copper_layer_count`). Before the fix, the RTD run stopped at
  INPUT_SCHEMA on In4.Cu, and its lower fail count was checks that never ran.
- The binder's deviations file declares the C51/C52 MPNs.

The informative layer-roles run has 71 clock-return findings (W4).

The indeterminate findings left are those of each unit's own standalone control (W5), plus for the RTD
`unit_io` pending (W1) and the two layer-role gaps (W4). The standalone controls themselves exit 1 with zero
FAIL and only these INDETERMINATE findings, so exit 0 is not reachable for any of the three (README).

Fixed by C34 (no longer reported): `DRC.BOARD.STACKUP` (interlock and thermal), the four thermal
`DRC.NATIVE.CLEARANCE` findings below 0.20 mm, `DRC.RTD.LOCAL_DECOUPLING` for `c_rtd_input`, the 146
`DRC.RTD.NATIVE_GEOMETRY` analog-return corridor failures, and the "filled-zone evidence lacks RTD_AVDD on
F.Cu" indeterminate.

## W1. Host connectors absent: census, connector parts, topology, connectivity, unit interface (25 findings)

The controller embeds each unit without its host connector; the controller's copper replaces it (DECISIONS
C1). `mappings/*.json` shows every remaining pad on exactly its unit net (0 pads on another net, 0 extra
pads), so these rules fail on the missing connector pads alone (an inference from the pad-level mapping;
the Rust findings are boolean).

| Validator | Finding | n |
|---|---|---|
| Interlock | `ERC.INTERLOCK.NATIVE_COMPONENTS` exact 25-component census (23 present: `faults`, `host` absent) | 1 |
| Interlock | `ERC.INTERLOCK.PARTS` exact MPN `faults`, `host` (B8B-XH-A) | 2 |
| Interlock | `ERC.INTERLOCK.TOPOLOGY`, `ERC.INTERLOCK.CONNECTIVITY` | 2 |
| Thermal | `ERC.THERMAL.NATIVE_COMPONENTS` exact 27-component census (26 present: `host` absent) | 1 |
| Thermal | `ERC.THERMAL.PARTS` exact MPN `host` (B6B-XH-A) | 1 |
| Thermal | `ERC.THERMAL.TOPOLOGY`, `ERC.THERMAL.CONNECTIVITY` | 2 |
| RTD | `ERC.RTD.UNIT_INTERFACE`: `unit_io` absent, and its pads 1-10 not on their source nets | 11 |
| RTD | `ERC.RTD.SPI_SERIES_PLACEMENT` `unit_io.4`-`.8` have no SPI source connection | 5 |
| RTD | INDETERMINATE `ERC.RTD.UNIT_INTERFACE` connector MPN and pin map pending (profile `pending_qualified_source`) | 1 (indet) |

**Justification:** a structural difference of the integration, not a layout defect. No stand-in connector
is synthesised, so the validators report it.

## W2. Thermal trip resistors changed by C32 (5 findings)

`ERC.THERMAL.PARTS` exact MPN for `hs_top`, `hs_bottom`, `coil_top`, `coil_bottom`, `coil_hyst`. The
validator's constants are the standalone unit's 85 / 120 °C trips; the controller trips at 101.4 / 175.7 °C
(DECISIONS C32, the thermal trip ladder) with 11.5 k / 8.06 k and 90.9 k / 7.06 k / 140 k. The controller's
64-corner trip analysis for these values is `tools/controller_calcs.py thermal_trips()`, checked by
`verify_controller.py` section `thermal` (11/11, with a mutation test). Updating the unit contract is a
change request to `zapote/thermal-sense` (C32).

*C36 note:* `hs_bottom` (R31) is now RT0603BRD078K06L (Yageo RT 8.06 k 0.1 %, 25 ppm, LCSC C861587) instead of
RC0603FR-078K06L; same value, 0603 footprint and net, so the 64-corner trip bands are unchanged (the 1 % tolerance
in `thermal_trips()` bounds the tighter part). The exact-MPN finding for `hs_bottom` stays waived under W2.

## W3. RTD_DRDY is on the TCA9555 expander, not a GPIO (2 findings)

`ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE` ("RTD_DRDY uses GPIO 65535; GPIO 9 is source-defined") and
`ERC.RTD.SPI_SERIES_PLACEMENT` ("RTD_DRDY lacks the source-derived GPIO/ADC pin/series resistor binding").
The controller reads DRDY on expander P07 (DECISIONS C23, LAYOUT.md open item 12), so no ESP32 GPIO carries
it; `profile-controller.json` says so with `drdy_gpio = 65535`. The validator also hard-codes SCK / SDI /
SDO as GPIO 8 / 11 / 12 (the controller uses 11 / 13 / 12) in `zapote-harness`, so it cannot check those
three against the controller; only CS (GPIO 10) is checked, and passes.

## W4. RTD return-plane layer roles: gnd on In2.Cu and +3V3 on B.Cu (2 indeterminate)

`DRC.RTD.NATIVE_GEOMETRY` INDETERMINATE "native filled-zone evidence lacks gnd on In2.Cu" (the unit's
`clock_return` role) and "... lacks +3V3 on B.Cu" (`upstream_supply`). These are the unit board's layer
roles (`rtd/unit/profile.json` `return_planes`). The controller's are: one solid selv_gnd plane on In1.Cu
that is the return for both the analog and the SPI nets, and the v3v3 plane on In2.Cu as the upstream
supply. Turning In2 into ground under the RTD block would cut the v3v3 plane that feeds ~100 decoupling
capacitors through one via each; a B.Cu +3V3 pour would add copper for a role the In2 plane already fills.

What the controller does instead (C34), and what the validator does check now:
- **Analog return (the `analog_return` role, gnd In1.Cu):** checked, and passes for all RTD analog traces.
  The router keeps the eight analog nets on F.Cu / In2.Cu over In1, off In1 antipads, and lets them change
  layer only within 2.5 mm of a selv_gnd plane via (a stitching grid over the RTD region supplies them).
- **Filtered supply (`filtered_analog_supply`, RTD_AVDD F.Cu):** a local RTD_AVDD pour at the MAX31865 VDD
  pin and its bypass: checked, passes (this indeterminate is gone).

**Informative run with the controller's own roles** (`results/informative-controller-rtd-layer-roles.json`,
`profile-controller-roles.json`: clock return gnd In1.Cu, upstream +3V3 In2.Cu; not the verdict). It turns
both gaps into checks: the upstream-supply role passes, and the clock-return role **fails** for the RTD SPI
nets (RTD_SCK, SDI, SDO, CS_N, DRDY) where they run on B.Cu (their nearest plane there is the In2 v3v3
plane, which this validator does not accept as a return) and at some of their F.Cu vias that have no
selv_gnd via within 3 mm: 74 clock-return trace findings on the committed board (60 on B.Cu, 12 on F.Cu,
2 on In2.Cu, of 128 RTD SPI trace pieces; 83 / 91 on the other two convergence boards, the routing
differs per run).

**Justification and what remains open:** the SPI lines are slow (MAX31865 SCLK ≤ 5 MHz, 33 Ω series at the
ADC), their return over the decoupled v3v3 plane is a defined image, and they do not share a corridor with
the analog nets, which C34 keeps over solid ground. Bringing the SPI nets under the same rule as the analog
nets (F/In2 only, return vias) is a routing change across the board (the RTD SPI nets run ~200 mm from the
module), so it is recorded as a follow-up rather than done here. To make the validator's verdict
board-specific, the RTD profile's `return_planes` should be given per board (a controller profile with
the roles above); that is a validator/profile change for the RTD unit's owner, not made here, and it
would make the SPI finding above part of the verdict.

## W5. Standalone-control indeterminates (unchanged by layout)

Identical to each unit's own standalone control (`results/control-standalone-*.json`): interlock 5
(physical fault tests NOT RUN; SENSOR_LIVE / AUX producers; watchdog timing; HC30 applicability), thermal 7
(device applicability across the monitor rail, beta extrapolation, connector / mounting / harness,
power-off), RTD 2 (`ERC.RTD.FAULT_CORNERS` brownout timing not measured; `ERC.RTD.MODEL_DEVICE_APPLICABILITY`).
They are open by the validators' design (physical tests and device qualification), not layout findings.

## W6. Prototype-lot sourcing swaps (C35/C36): exact-MPN findings on 74HC30PW,118 and the RTD resistors

Validators were **not re-run** for C36 (no Rust workspace build in that session). Expected new findings, waived
here in advance and to be confirmed on the next validator run:

- `ERC.INTERLOCK.PARTS` exact MPN for `aggregate` (U22): the unit contract names CD74HC30PWR (TI); the
  controller fits **74HC30PW,118** (Nexperia, LCSC C546857) because CD74HC30PWR had 2 in stock at JLC on
  2026-10-12. Same 8-input NAND, same TSSOP-14 pinout and 2-6 V HC family; the footprint, the net list and
  `verify_controller.py`'s HC30 model (pin table identical, 20 uA budget kept) are unchanged. 
- Any RTD `PARTS`-type exact-MPN finding for `r_avdd_top` (R53: ERA-3AEB1652V -> RT0603BRD0716K5L, same
  16.5 k 0.1 % 25 ppm 0603) and `r_ref` (R39: RG2012V-431-W-T1 0.05 % -> RT0805BRD07430RL 0.1 % 25 ppm, 0805;
  about 0.13-0.26 C more PT100 error over 0-250 C, DECISIONS C35). The 10 / 300 ohm fault thresholds are unaffected.
- No validator, contract or unit profile was edited.

*Confirmed by the C44 rerun:* the interlock reports exactly the `aggregate` MPN finding (69 / 6 / 5). The RTD
validator reports no MPN finding for `r_avdd_top` (it checks the MPN of `c_rtd_input` only, see W7), and `r_ref`
is the unit's RG2012V-431-W-T1 again (C37 reverted the swap; consigned). The swap does show in the RTD binder's
census gate, which `rtd-deviations-c37.json` declares (W7).

## W7. RTD sense filter and J3 protection (DECISIONS C37; 15 findings)

C37 applies sensor-r3 CR-1 / CR-2: a two-stage 1.00 k / 100 nF C0G differential filter per sense line, 1 nF
C0G to ground at each RTDIN pin, 220 nF and an ESD5Z3.3T1G on every J3 pin, the 499 k open-input pull-ups,
the window branch and the low-window return on the connector side of the filter (`rtd_sense_*_ext`), and
10 nF on the window node. That is 16 parts the unit does not have, 4 changed MPNs and 6 pads on a
connector-side net. All of them are declared in `rtd-deviations-c37.json`, which only lets them past the
binder's abort gates; the export and the unit bindings reach Rust unchanged, and Rust reports:

| Finding | n | What it is |
|---|---|---|
| `ERC.RTD.UNIT_COMPONENT_MPN` `c_rtd_input` GRM31C5C1H104JA01L, unit C0603C102J5GACTU | 1 | the RTDIN differential cap is the second filter stage, 100 nF C0G 1206 |
| `ERC.RTD.UNIT_COMPONENT_MPN` source binding on `rtd_sense_*_ext` (J3.2, J3.3, `r_window_sense_p.1`, `r_low_bottom.2`, `r_rtdin_p_bias.1`, `r_rtdin_n_bias.1`) | 6 | the declared pad-net moves |
| `DRC.RTD.UNIT_PAD_GEOMETRY` component census, pad census | 2 | the 16 added parts and their pads |
| `ERC.RTD.FOUR_WIRE_PINOUT` J3.2 / J3.3 not on `rtd_sense_p` / `rtd_sense_n` | 2 | the probe reaches RTDIN through 2 x 1.00 k |
| `ERC.RTD.BOARD_COMPONENT_BINDING` no J3.2 / J3.3 -> `rtd_sense_*` | 2 | same |
| `ERC.RTD.NATIVE_CONNECTIVITY` `rtd_sense_p`, `rtd_sense_n` lack the J3 endpoint | 2 | same |

**Justification:** the unit validator's model is the unit's direct probe-to-RTDIN topology, so it cannot accept
a filter in the sense path. The filter is checked where it was specified: `evidence/sensor-r3-checks/`
(`run_as_built.py` on the frozen netlist, the unmodified sensor-r3 `checks.py`: 11/11 gates PASS, no
difference from the change request: pickup 0.105 LSB worst DM at 20 kHz, runaway shift 0.03 K, open lead
detected, protection and ratings), and `verify_controller.py` (`sensor_io`, `sources`: the block is
generated from the byte-identical library plus listed edits). Accepting the filter in the RTD unit's own
contract is a change request to `zapote/rtd`, not made here.

What still holds: no new FAIL or INDETERMINATE in any other RTD rule; the analog-return corridor check
(`DRC.RTD.NATIVE_GEOMETRY`) passes on every trace of the unit's analog nets. The four new `_ext` / `_mid`
nets are not unit nets, so the validator does not check them; the router applies the same rule to them
(`RTD_ANALOG_NETS` in `layout/floorplan.py`: F.Cu / In2.Cu only, a ground via within 2.5 mm of each via).
Informative layer-roles run: 61 clock-return trace findings on the RTD SPI nets of the committed board (69 / 91 / 61 on the three C47 convergence boards, 87 on the C44 board, 74 on C34's; W4,
routing differs per run), no analog finding.

## W8. C51/C52 parts and the six-layer stack (DECISIONS C51, C52, C53; 9 findings)

| Validator | Finding | Part | Reason |
|---|---|---|---|
| Interlock | `ERC.INTERLOCK.PARTS` exact MPN `common: SN74LVC1G08DBVR` | U11-class AND gates | C52 stock swap to SN74LVC1G08QDBVRQ1 (C840098), the automotive grade of the same gate in the same DBV package |
| Thermal | `ERC.THERMAL.PARTS` exact MPN `hs_hyst: RC0603FR-0734K8L` | R32 | C52 stock swap to AF0603FR-0734K8L (C2098331), the same 34.8 k 1 % 0603 in Yageo's anti-sulfur line |
| RTD | `DRC.RTD.UNIT_PAD_GEOMETRY` ×2, `ERC.RTD.BOARD_COMPONENT_BINDING` ×2, `ERC.RTD.UNIT_COMPONENT_MPN` ×2 | U30, R39 | U30: MAX31865AAP+T is the tape-and-reel code of the unit's MAX31865AAP+ (C51), on the correct 5.3 mm SSOP land. R39: PTFR0805B430RN9 is the stocked 0.1 % 10 ppm/K Rref (C52; CR-2 gate 1b at 0.45 K) |
| RTD | `ERC.RTD.UNIT_COMPONENT_MPN` "unit manufacturing contract does not match the standalone profile" | board | The unit's standalone contract is four layers. The controller is six (C53): 1 oz outer, 0.5 oz inner, the same 0.20 mm rules |

**Justification:** each finding names a part that DECISIONS changed on purpose, and the validator still reports it,
because the native export goes to Rust unchanged. The binder declarations (`rtd-deviations-c37.json`) only stop its
census and MPN gates from aborting. The thermal and AND-gate swaps keep value, tolerance and package. The Rref change
carries its own accuracy budget (C52). The RTD layer-role and reference-plane checks run on the six-layer stack itself:
F/In2 against In1, In3/B against In4.

