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

Cheap, same respin:
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
