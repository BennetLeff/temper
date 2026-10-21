# Rev D decision (2026-10-20)

**Decision: respin before ordering.** One change is required for stability with real leads. The other changes are cheap to fold into the same respin. Nothing found argues for changing the analog architecture, the ranges or the gain staging.

## Evidence summary

| Study | Result | Board change? |
|---|---|---|
| Fixture/lead stability (`validation/stability-full-chain/fixture-envelope.md`) | The 100 Ω range fails 45° above ~300 pF of cable per DUT terminal (470 pF: 39.9°; 2 m RG-174: 41.0°) | **Yes**: R_iso |
| Extracted parasitics (`validation/layout-parasitics/`) | Assumed inductances were conservative. Board copper costs ~6°, mostly 10.5 pF on the TIA-output trace. With R_iso the floor is 51.7° | R_iso placement; optionally shorten the TIA-out copper |
| Virtual instrument (`validation/virtual-instrument/`) | Every proposed Temper target meets. Coil R_ac (no pan) and tan δ are marginal at corners; the limits are standards, contacts and DDS spurs, not board noise (≤2.9% of any tolerance) | No |
| Supply spurs/regulators (`validation/power-spurs/`) | No required change. VNEG tolerance stack reaches −15.145 V (−15 V recommended). Switcher error ≤0.97 LSB at the ADC | Optional R83, LDO input resistors |
| Firmware/host (commits e4e41c31a, 8a4726397) | 1 MSPS boxcar capture; hazard-frequency refusal; source-off check; grid 1.5/35.5/40.5/50.5/60.5 kHz | No |

## Rev D change list

Required:
1. **R_iso = 22 Ω, 0.1%, low TC, 0603**, between J3 LO and the U7A summing node. The LOW follower taps the J3 side. Placement is above U7 per `validation/layout-parasitics/README.md`: about 6 changed segments, one via, one plane keepout, a new net in `design.json`, and the part shifted up 0.1 mm for courtyard clearance. Route by hand in `cad/routing.json`; no autorouter. The host nominal feedback model becomes `R_iso + RF‖CF`. After the edit, re-extract parasitics and rerun `final_fixedextracted`.

Cheap, same respin (status: see **Implemented** below):
2. **R83 1.78 MΩ → 1.74 MΩ** (E96, 1%): VNEG −13.35 to −14.81 V, U12 headroom ≥ 1.03 V.
3. **1 Ω before each LDO input**: residual switcher error on the ±12 V path drops ×17; headroom stays ≥ 1.26 V at twice the estimated load.
4. **Agent hooks on unused RP2040 GPIO:** range-jumper sense lines, a temperature sensor next to RF/C104, and ±12 V / 5 V rail dividers into the RP2040 ADC (GPIO26/27). These let an agent confirm the range and run the rail bring-up check itself.
5. **Shorten the TIA-output copper** where the reroute allows. Dropping its 10.5 pF entirely recovers ~4.6°.

Rejected (studied, no verdict changes): a 20–33 Ω range with BUF634A, extra FDA or channel-A gain, extra source drive.

## Bench and process rules (no board change)
- Know the ratio of the 20 Ω and 100 Ω calibration standards to ≤0.03% (measure them once against a reference); marked ±0.1% values leave about −16 mΩ on coil R.
- With R_iso fitted, fix the LO lead in place after calibration, or recalibrate after moving it (±20% lead C at 200 pF adds about 8 mΩ to coil R at 60 kHz).
- Use the host's clean grid and keep the paired source-off check on.
- Without Rev D (if Rev C were built): keep each DUT terminal under about 220 pF, and no relay multiplexer.

## Implemented (2026-10-20, branch `study/lcr-in-box`)

All edits are hand-routed segments in `cad/routing.json`; no autorouter was used. `cad/rebuild.sh`: ERC 0, DRC 0, 0 unconnected, parity 0. `validation/independent_check.py D`: 0 findings.

| Item | Status | Detail |
|---|---|---|
| 1. R_iso | Done | R94 22 Ω 0.1 % RT0603BRD0722RL (C861239) at (167.0, 105.3); new net TIA_SUM = U7.2, C104.1, R43–R45.1, R94.2. LOW follower stays on J3. Re-extracted as built: within 1 % of the proposal. `final_fixedextracted` as built: **minimum 51.3°**, \|1+T\| ≥ 0.573 over 0–1000 pF cable (Rev C 29.5°). |
| 2. R83 | Done | 1.74 MΩ 0603WAF1744T5E (C422975). |
| 3. LDO input resistors | Done | R95/R96 1 Ω (C22936, basic) into new nets LDOIN_P/LDOIN_N. |
| 4a. Rail monitors | Done, ±12 V only | R97 100k/R98 10k/C110 → GPIO26 (≈1.09 V at +12 V); R100 150k from −12 V, R99 10k to 3V3, C111 → GPIO27 (≈2.34 V at −12 V, never negative while 3V3 is up). The divider tops sit at the rails, so the long runs carry only a resistor-limited node. Firmware `RAILS`; host `rails`, and `info`/`capture`/`noise` refuse out-of-window rails (10.8–13.2 V). 5 V is not monitored: no free ADC input (GPIO28/29 are the UART header). |
| 4b. Range-jumper sense | Dropped | Sensing a jumper means a GPIO net reaching the RG/RF jumpers, which are on the source and summing-node nets. A digital line there is a coupling path into the most sensitive node for a convenience feature. The host already records the range explicitly in every capture and calibration, and a range mismatch fails calibration matching. Relay ranging, if it is ever added, brings its own state readback. |
| 4c. Temperature near RF/C104 | Dropped; RP2040 die sensor instead | No free ADC input remains, and an I2C sensor would bring a digital bus into the AFE. `RAILS` reports the RP2040 die temperature (ADC4) with every rail check. It is only a coarse board-temperature proxy, but enough to log drift context. |
| 5. Shorten TIA_OUT copper | Not done | The 10.5 pF is spread over about 47 mm on three branches: JP4/RF100 (local), the JP5/JP6 5 k/100 k branch (~20 mm) and the FDA input branch to R67 (~17 mm, mostly on In2). Removing most of it means moving JP5/JP6 and their RF resistors next to U7, or moving R67 so that the long run lands on the FDA's own summing node instead. Either is a larger AFE re-layout with its own stability risk, for at most ~4.6°. The as-built floor is 51.3°, above the 45° criterion. Revisit only if the first board's ringing check shows less margin than modelled. |

Firmware/host: identity `D-riso22`, host 0.6.0, feedback = 22 Ω + RF‖100 pF on every range, calibration schema 5 (refuses Rev C files), 29 tests and Clippy pass, firmware hot loop still 88/120 cycles.

Cost: +$0.068 per board, 173 SMT placements (+9), 55 lines (one new extended line: R94).

Still open before ordering:
- LCSC stock for C861239, C422975 and C22936 is unconfirmed (jlcsearch gives no stock); check at BOM upload. Alternates for R94: any 22 Ω 0.1 % ≤25 ppm/°C 0603 thin-film part.
- Full package build without `LCR_SKIP_ARCHIVE` (`temper-lcr-rev-d-package.zip`, manifest refresh).
- JLC placement preview and DFM, as for Rev C.
- The virtual-instrument study (`validation/virtual-instrument/`) remains pinned to the Rev C host (protocol 1) and models R_iso analytically; it was not rerun against host 0.6.0.
- All evidence is simulation on typical vendor models. Bench rules above still apply.
