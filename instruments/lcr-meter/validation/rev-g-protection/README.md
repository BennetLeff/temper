# Rev G jack protection study (started 2026-11-08)

Rev F has no protection on its four BNC jacks (audit AFE-01 to AFE-04). `../charged-dut/` measured the gap: 7 V with Kelvin clips when powered and 0.5–1 V when unpowered, against 1 J for a Keysight E4980A.

This study designs the Rev G protection while Rev F is built. The final values wait for Rev F bring-up: the real ESD knee, 3V3A rise, stability with leads, and accuracy margins.

**Target** (charged-dut README, "Rev G requirements"):
- **Minimum:** within every datasheet rating (class A) for 1 µF at 30 V, powered and unpowered, on every connection pattern.
- **Stretch:** 1 J.
- **Constraints:** no loss of accuracy, stability or low-impedance signal that the later phases cannot accept.

## Phases

| Phase | What | Status |
|---|---|---|
| 1 | Surge screen of candidate topologies with parametric clamps, in the charged-DUT model | **done** (below) |
| 2 | Pick real parts (TVS, Schottky, pulse-rated resistors, isolation switch) whose ratings cover the phase 1 stresses, and rerun the screen with their datasheet models | next |
| 3 | Normal-operation impact: signal loss on the 100 Ω range for low-Z parts, phase and drift added to the HPOT/LPOT and TIA paths, leakage at DUT_LO, noise | next |
| 4 | Stability: the full-chain matrix (`../stability-full-chain/`) with the network's capacitances on DUT_HI, DUT_LO, HPOT and LPOT | after 3 |
| 5 | Accuracy map and noise rows (`../rev-e-accuracy-map/`, `../rev-e-codec/`) | after 4 |
| 6 | Isolation switch drive, residual-voltage sense, power budget, firmware sequencing; schematic and layout | after Rev F bring-up |

## Phase 1: surge screen

```sh
python3 validation/rev-g-protection/protection_screen.py --jobs 10   # ~6 min for all candidates -> protection-screen.json
python3 validation/rev-g-protection/protection_screen.py --check-readme
```

**Method.** `../charged-dut/charged_dut_spice.py` `deck()` takes a protection network (`prot=`). The leads then land on jack nodes, and the network connects those to the Rev F board nodes DUT_HI, HPOT, LPOT and DUT_LO. Every case is judged by the same `judge()`: all the OPA2810, LDO (including OUT beyond IN), TAC5112, BAT54S and passive ratings of Rev F. The screen runs:
- every connection pattern;
- all six meter states;
- 1 µF, at 0.5 V to 1000 V in both polarities.

**Harness checks.**
- Without a network, `deck()` writes byte-identical circuits; 720 sample circuits were compared by hash.
- The `links` candidate (zero-ohm links) reproduces all 30 baseline rows of `charged-dut.json` exactly.

**Clamp models are parametric, not parts:**
- **TVS5:** BV 6.4 V, 0.06 Ω, 2 nF (a 5 V-standoff 400 W-class TVS).
- **TVS3:** BV 4 V, 0.1 Ω, 0.5 nF, a second stage that still passes the 1.7 V source.
- **Schottky pair:** 0.31 V at 10 mA, 0.5 V at 1 A.
- **Isolation relay:** open (1 pF) when unpowered, 0.1 Ω when powered.

Phase 2 replaces all of these with datasheet parts.

<!-- generated:screen -->
| Candidate | Lowest class-A voltage, 1 µF, any pattern and state | Powered | Unpowered | 30 V target | What ends it |
|---|---|---|---|---|---|
| `links` | 0.5 V | 3 V | 0.5 V | no | h_to_gnd unpowered/100R: u6b input 72.6 mA > 10 |
| `tvs_all` | 0 V | 3 V | 0 V | no | h_to_gnd unpowered/100R: u6b input 21.1 mA > 10 |
| `tvs_all_r1k_pot` | 0.5 V | 3 V | 0.5 V | no | l_to_gnd unpowered/100R: u7a input 31.9 mA > 10 |
| `iso_tvs` | 3 V | 3 V | 1000 V | no | l_to_gnd powered/5k: u7a Vdiff 7.16 V > 7 |
| `two_stage` | 1 V | 1000 V | 1 V | no | kelvin unpowered/100R: u6b input 10.6 mA > 10 |
| `iso_two_stage` | 1000 V | 1000 V | 1000 V | met | nothing up to 1000 V |
<!-- /generated -->

Candidates (full definitions in `CANDIDATES`):
- **`tvs_all`:** a TVS5 at each jack.
- **`tvs_all_r1k_pot`:** the same, plus 1 kΩ at HPOT and LPOT.
- **`iso_tvs`:** the jack TVSs plus a normally-open isolation relay on all four jacks.
- **`two_stage`:**
  - jack TVSs;
  - 10 Ω on HCUR and LCUR, 100 Ω + 1 nF C0G on HPOT and LPOT;
  - a TVS3 second stage on HCUR, HPOT and LPOT, and a Schottky pair at DUT_LO (a virtual ground, so the pair never conducts in use).
- **`iso_two_stage`:** both.

### What the screen shows

1. **Unpowered, clamps alone cannot do it.** With the rails at 0 V, any current that reaches an op-amp pin charges the ±12 V rails past the LDOs' 0.3 V OUT-to-IN limit, or exceeds 10 mA in an ESD cell. HCUR and LCUR carry the measurement current, so they cannot take the kilohms that would stop it without losing signal on low-impedance parts, which are the Temper targets. `two_stage` holds 1000 V powered but only 1 V unpowered.
2. **Powered, a jack clamp alone is not enough at the TIA.** Any jack clamp at ~7 V or more leaves LCUR high enough to exceed U7A's 7 V differential input on the 5 kΩ and 100 kΩ ranges, where RF is too large for the TIA to hold its input. `iso_tvs` stops at 3 V for this reason. The fix is a low-voltage second stage at DUT_LO. DUT_LO is a virtual ground, so a Schottky pair there never conducts in normal use.
3. **The follower differential limit needs the step slowed, not just clamped.** On HPOT and LPOT, 100 Ω + 1 nF slows the contact step enough for the followers to follow. This is why option A (1 kΩ into a few pF) did nothing powered.
4. **`iso_two_stage` meets the target with margin.** In the parametric model it is class A to 1000 V on every pattern and state. The isolation switch handles the unpowered meter; the two stages handle the powered one.
5. **The isolation switch only sees the jack clamp's voltage,** not the DUT's. That opens up a solid-state photoMOS switch instead of a relay: normally open with no drive, a few mA of LED current instead of a coil, and no contact wear. That matters for the USB budget, because the board already draws about 0.46 A of the 0.5 A it declares. Phase 2 has to check its on-resistance and capacitance.

### Part stress in `iso_two_stage` (sizes phase 2)

<!-- generated:stress -->
| Part | At 1 µF, 30 V (the target) | Worst case in the screen (up to 1000 V) |
|---|---|---|
| `tvs1_hcur` | 24.1 A peak, 204 µJ | 1.06e+03 A peak, 186 mJ |
| `tvs2_hcur` | 0.527 A peak, 20.2 µJ | 12.5 A peak, 2.3 mJ |
| `tvs1_hpot` | 24.1 A peak, 207 µJ | 1.06e+03 A peak, 189 mJ |
| `tvs2_hpot` | 0.056 A peak, 11.3 µJ | 1.3 A peak, 0.271 mJ |
| `tvs1_lpot` | 24.1 A peak, 207 µJ | 1.06e+03 A peak, 189 mJ |
| `tvs2_lpot` | 0.0516 A peak, 0.73 µJ | 1.29 A peak, 0.24 mJ |
| `tvs1_lcur` | 24.1 A peak, 204 µJ | 1.06e+03 A peak, 186 mJ |
| `sch2_lcur` | 0.97 A peak, 34.9 µJ | 13.1 A peak, 2.49 mJ |
| `r_hcur` | 5.29 V, 2.8 W peak, 5.17 µJ | 125 V, 1.55e+03 W peak, 2.04 mJ |
| `r_hpot` | 9.97 V, 0.993 W peak, 1.47 µJ | 129 V, 167 W peak, 0.222 mJ |
| `r_lpot` | 11 V, 1.21 W peak, 1.47 µJ | 129 V, 167 W peak, 0.222 mJ |
| `r_lcur` | 9.66 V, 9.34 W peak, 31 µJ | 131 V, 1.72e+03 W peak, 2.43 mJ |
<!-- /generated -->

- **At the 30 V target,** a 400 W-class SMA TVS and pulse-rated resistors cover these with margin.
- **The 1000 V rows** are a 1 µF tank cap at 1000 V. They put about 1 kA through each jack TVS, past any single SMA part, and kilowatt peaks into the series resistors. That is the 1 J stretch goal. It needs SMC-class TVSs or a series element ahead of them, and phase 2 decides whether it is worth it.
- **The clamp voltages at kiloamps** depend on the parametric dynamic resistance. Phase 2 reruns them with datasheet clamping curves.

## Open questions for phases 2–6

- **Second-stage capacitance on HPOT/LPOT.** It adds phase in the voltage channel, and a TVS's capacitance moves with temperature and bias. C0G for the slowing capacitor and a low-capacitance clamp keep it calibratable. Phase 3 measures the drift.
- **Signal loss and noise on the 100 Ω range.** The 10 Ω on HCUR and LCUR (plus the switch's on-resistance) adds to the 147 Ω source path, which costs signal for low-Z parts. Phase 3 quantifies it, and the values can shrink if the stability and surge margins allow.
- **The Schottky pair at DUT_LO.** It adds capacitance and a temperature-dependent conductance at the TIA's virtual ground, like C78. Phases 3–5 check the error term and stability.
- **The isolation switch.**
  - **Drive and power budget:** 4 poles, which drive, and how much current it takes from USB.
  - **Residual-voltage sense:** read the jacks through a high-impedance divider before closing, and refuse to close while a DUT is charged.
  - **Sequencing:** open it before any range change and on any fault.

  RP2040 ADC2/ADC3 (GPIO 28/29, the optional UART header) are free for the sense.
- **Human ESD on the centre pins** (IEC 61000-4-2): add it as a test case once the parts are chosen.
