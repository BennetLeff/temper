# Rev G protection: phase 2 part candidates (2026-11-08)

These are the parts for the `iso_two_stage` network in `../README.md`. Every number below comes from a datasheet: the URL, SHA256 and quoted rows are in `parts.json`. Curve values marked "read from figure" are about ±10–20 %. Stock and price come from the JLC parts API on 2026-11-08. The SPICE fits are ngspice DC solves against the datasheet points; `parts.json` lists the fit points and the error at each.

## Recommended set

| Role | Part | LCSC / library | Key numbers | Margin at the 30 V target |
|---|---|---|---|---|
| Jack TVS (×4) | HJC **H4V5HD3B**, SOD-323 | C20615803, preferred | VRWM 4.5 V; VBR 4.8–7 V @ 1 mA; VC ≤ 6.5 V @ 1 A, ≤ 10 V @ 40 A (8/20); IR ≤ 0.2 µA @ 4.5 V; 100 pF typ | 24 A vs 40 A (8/20). Model gives 8.6 V at 24 A |
| Second-stage TVS (HCUR, HPOT, LPOT) | HJC **H3V3LD5B**, SOD-523 | C20615817, preferred | VRWM 3.3 V; VBR 3.5–6.5 V; VC ≤ 6 V @ 1 A, ≤ 12 V @ 8 A; IR ≤ 0.2 µA @ 3.3 V; 12.5 pF typ / 25 pF max | 0.53 A vs 8 A. Model gives 5.7 V at 0.53 A |
| DUT_LO pair | Nexperia **BAV99** (common pin to DUT_LO, both ends to GND) | C2500, **basic** | VF ≤ 0.715 / 0.855 / 1.0 / 1.25 V @ 1 / 10 / 50 / 150 mA; IFSM 4 A @ 1 µs, 1 A @ 1 ms; Cd ≤ 1.5 pF; IR ≤ 30 nA @ 25 V | 0.97 A for ~1.7 µs vs 4 A @ 1 µs |
| 10 Ω (HCUR, LCUR) | Vishay **CRCW080510R0FKEAHP** | C844598, extended | 1 %, ±100 ppm/K; single pulse ~450 W @ 1 µs; ~500 V pulse | 9.3 W, 31 µJ: about 30× |
| 100 Ω (HPOT, LPOT) | Vishay **CRCW0603100RFKEAHP** | C844725, extended | 1 %, ±100 ppm/K; ~250 W @ 1 µs; ~250 V pulse | 1.2 W: about 200×, and it covers the stretch rows too |
| 1 nF C0G | Yageo **CC0603JRNPO9BN102** | C106246, extended | NP0, ±30 ppm/°C, 50 V, ±5 % | n/a |
| Isolation switch (×4) | Toshiba **TLP172AM(TPL,E)** photoMOS, 1 Form A | C2152276, extended | VOFF 60 V; RON 1 Ω typ / 2 Ω max; COFF 20 pF typ @ 0 V; IOFF ≤ 1 µA @ 60 V; IFT ≤ 3 mA; tON ≤ 2 ms, tOFF ≤ 0.5 ms; 3750 Vrms | Off-state sees ~8–10 V vs 60 V. On-state surge 0.97 A vs IONP 1.5 A |

**Cost.** The set adds 4 extended lines, about $12 per order in setup fees. The jack TVS and second-stage TVS are preferred parts and the BAV99 is basic, so those three add no fee. To drop the capacitor line, two of the 560 pF C0G already on Rev F (C107054) in parallel give 1.12 nF; this works if the screen accepts that value.

**Isolation drive** (superseded by `../drive_budget.py`: 300 Ω, because 400 Ω gives 3.8 mA at the lowest rail, below the 5 mA RON is specified at). Two strings of two LEDs run from VBUS through about 400 Ω each, switched by one AO3400A. That is about 10–11 mA (55 mW) for all four poles. The non-latching relay alternative (2 × Omron G6K-2F-Y DC5, C47190) needs 42 mA, which is nearly all of the ~40 mA left in the 0.5 A budget. The Rev F TQ2SA-L2 relays latch, so they cannot be the normally-open switch.

## Why these over the alternatives

- **Jack TVS: H4V5HD3B over an SMAJ5.0CA.**
  - Capacitance is ~100 pF against ~1.15 nF (ST Fig. 7). That matters most on LCUR and LPOT, which sit at the TIA virtual ground.
  - Leakage is lower: 0.2 µA max, against the HJC SMAJ5.0CA's 800 µA, doubled for bidirectional parts.
  - The ST SMAJ5.0CA-TR (C123776) is the documented fallback. It has 8/20 ratings, RD, a C–V curve and IR against temperature.
- **DUT_LO: silicon BAV99 over a Schottky.**
  - At a virtual ground, what matters is the pair's zero-bias conductance, not its clamp voltage. That conductance is set by the saturation current, which grows with temperature.
  - From the typical IR curves (an estimate, for phase 3 to measure):
    - BAT42 pair: about 190 kΩ at 25 °C and about 3 kΩ at 75 °C. On the 100 k range that is a noise gain of about 30, plus a current-sharing error that moves with temperature.
    - BAV99 pair: about 1.5–3 MΩ at 25 °C and about 60 kΩ at 85 °C.
  - The BAV99 clamps higher: 1.13 V at 0.1 A, and 2.9 V at 1 A extrapolated from the max-VF fit. Both are far inside U7A's 7 V differential limit. The phase-2 screen rerun has to confirm this.
  - The Schottky candidate is BAT42WS (C22466360, preferred, IFSM 4 A, 10 pF), fitted to the Vishay BAT42W tables.
- **Second stage: H3V3LD5B over Nexperia PESD3V3L1BSL (C3715319).**
  - At 0.5 A it clamps about 2.4 V lower, and it is a preferred part.
  - Its datasheet has no C(V) curve. If phase 3 needs a bounded phase drift on HPOT and LPOT, use the Nexperia part there: 15.6 → ~13 pF over ±1.7 V (Fig. 4), about 0.3 % of the 1 nF.

## Risks and gaps

1. **The new clamps sit above the phase-1 parametric values.**
   - The second stage clamps at 5.7–8 V at 0.5 A, against TVS3's BV of 4 V.
   - The jack clamp is 8.1–8.6 V at 24 A.
   - The photoMOS off capacitance is 20 pF, not 1 pF.

   The phase-2 rerun of `protection_screen.py` with these models decides whether class A still holds at the op-amp pins.
2. **The HJC datasheets are thin.** They give typical capacitance only at 0 V, wide VBR windows (the fits use the midpoints) and no C(V) or IR(T) curves. Bench-check C and leakage on a few parts.
3. **BAV99 at 1 A is outside its VF table.** The model is extrapolated from max values, so it overstates the clamp, which is the safe direction for this check.
4. **The resistor pulse ratings come from the CRCW-HP single-pulse curve** (n < 1000 pulses), read off the plot. Panasonic ERJ-P06 is cheaper, but its datasheet gives only a 150 pF / 3 kV ESD figure, with no pulse-power curve.
5. **Nothing in the set survives the 1 J stretch.**
   - Jack TVS: about 1 kA is needed, and ST SMCJ5.0CA (C133644) is listed at 746 A 8/20 (not checked against its datasheet).
   - 10 Ω resistors: 1.7 kW is needed; CRCW2512-HP would cover it.
   - Second stage on HCUR: 12.5 A against 8 A.
   - DUT_LO pair: 13 A.
   - photoMOS: 13 A on-state.

   Only the 100 Ω parts and the HPOT/LPOT second stage cover the stretch rows.
6. **No basic-library part exists for the photoMOS, the pulse-rated resistors or the 1 nF C0G.** Preferred parts exist only for the TVSs and the Schottky.
