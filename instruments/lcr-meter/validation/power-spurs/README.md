# Power-supply interference and regulator check (Rev C, before ordering)

**Rev D rerun (2026-10-20, after the [audit fixes](../../docs/rev-d-audit.md)).** `regulator_check.py` now reads every divider and feed-forward value from `cad/design.json`; before, it hard-coded the Rev C values, including R83 = 1.78 MΩ. With Rev D's R83 = 1.74 MΩ, VNEG is −13.347 / −14.071 / −14.805 V (min/nom/max), inside the −15 V recommendation. Finding 4 below is closed. U12 headroom is 1.028 V at the worst corner. Through the fitted 1 Ω R96 at 2× the estimated load it is 0.949 V: above the 0.6 V dropout, under the 1 V PSRR-curve condition (the "Option R5" row, which now describes fitted parts). The ripple chain now assumes 50 % DC-bias retention for C103 (22 µF 25 V X5R 1206). The other numbers below are Rev C text. They moved by under 1 % in the regenerated JSON.

This is a desk analysis of datasheets, `cad/design.json`, the CPL, the host fit and the firmware. No hardware exists. All numbers come from the scripts in this directory: `python3 run_all.py` reruns everything in about 3 minutes and needs numpy. Numbers read from datasheet curves are typical values. Values called "estimate" depend on the assumptions listed under **Limits**. Only the tolerance stacks in the regulator check use full-temperature datasheet limits.

## Verdict

**No PCB change and no BOM change is needed before ordering.** Every TI design rule passes at the worst-case corners. There is one 0.145 V excursion beyond a recommended operating range, caused by stacking every tolerance, and one capacitor sits exactly at its placement distance limit. The real problems are in software and have no hardware cost:

1. Every frequency in the Temper grid is a whole number of kHz, so a USB start-of-frame (SOF) harmonic falls on each one. The fit's rejection of that harmonic is 0 dB.
2. With the dividers that `divider_for` picks, AD9833 harmonics fold onto the measurement frequency. The worst case is harmonics 9 and 11 at 50 kHz.

Moving the grid up by 500 Hz fixes both. Switcher ripple only matters if one of its harmonics happens to alias into the fit main lobe. That is a chance event, roughly 2 % per frequency. The error estimates for that case are given below, along with an optional, cheap PCB provision.

## Findings, ranked

| # | Severity | Finding | Quantified basis | Fix |
|---|---|---|---|---|
| 1 | **Medium (amplitude not bounded)** | The host clock sets USB SOF at 1 kHz ±500 ppm. Each Temper grid frequency (1, 35, 40, 50, 60 kHz) is an exact SOF harmonic, and it falls inside the fit main lobe. | Fit rejection is 0.0 dB at all five points across ±560 ppm (SOF tolerance plus crystal tolerance). The supply-rail path estimate is ≤ 4.9×10⁻⁷ of \|Z\|. Ground and common-mode coupling through the USB cable cannot be bounded from datasheets. | Host change: use the grid 1.5, 35.5, 40.5, 50.5, 60.5 kHz, which gives −28 to −51 dB. A Hann-weighted fit would give −63 to −135 dB. Also add a NOISE gate (R2). |
| 2 | Low–medium | `divider_for` makes fs/f an integer or a simple ratio. AD9833 harmonics k then fold inside the main lobe: k = 9/11 at 50 kHz, 24/26 at 40 kHz, 49/51 at 1 and 60 kHz, 99/101 at 35 kHz. The error cancels for resistors but not for coils or capacitors. | 50 kHz with a 50 µH coil: 0.002 % using the exact digital DDS model, 0.018 % if the colliding harmonic is −80 dBc, 0.18 % at −60 dBc (the datasheet typical SFDR, a pessimistic level for this harmonic). 1 kHz with 9 µF: 0.002 %, 0.013 % and 0.13 % for the same three levels. | The same +500 Hz grid leaves no harmonic k ≤ 200 inside the main lobe. Re-choosing the divider fixes only 61 of the 175 affected frequencies, so frequency choice is the lever. |
| 3 | Low (chance event) | TPS65131 harmonics (fsw 1.25–1.50 MHz, free-running) can alias onto any grid point. Whether one does depends on the unit's actual fsw. | Probability per harmonic of a fit response > 0.1: 5.0×10⁻⁴, so 1.97 % that at least one of 40 harmonics collides. If a collision happens with a 15 Ω DUT: 0.055 % at the pessimistic corner, 0.0087 % typical. A 50 µH coil through the source-borne path: 0.11–0.19 % pessimistic, 0.017–0.029 % typical. | Bring-up check R4. Optional PCB provision R5: a 1 Ω or ferrite element before each LDO, which cuts the rail path ×17 (0.055 % → 0.0033 %). |
| 4 | Low | TPS65131 VNEG at the full tolerance stack (VREF max, VFBN min, R83/R84 at 1 %) is −15.145 V. The recommended minimum is −15 V; absolute max is −17 V. | Nominal −14.394 V; range −13.655 to −15.145 V. | Optional BOM change: R83 1.78 MΩ → 1.74 MΩ gives −13.347 to −14.805 V, and U12 headroom stays ≥ 1.028 V. |
| 5 | Info | The centre of C99 (U12 input, 10 µF) is 10.0 mm from U12. The datasheet guidance is ≤ 10 mm. C102 (100 nF) is 5.4 mm away. | CPL centre distance | Move C99 closer only if R5 reopens the layout. |

Everything else in the regulator check passes (table below). That covers the inductor value and saturation current, duty cycle, CP/CN/VREF and feed-forward capacitors, the forced-PWM pins, the output and input capacitance at break-even DC-bias retention, diode and pin stress, LDO COUT, CNR/CFF, divider limits, EN and headroom.

Both acquisition versions in this worktree were analysed: HEAD, which undersamples with the PIO clock divider, and the uncommitted in-progress boxcar decimation (`firmware/src/boxcar.c`, 2026-10-20 16:50). They use the same divider rule. Boxcar decimation does not change any conclusion. It reduces the 50 kHz coil DDS error from 0.018 % to 0.0078 % (−80 dBc case). It does nothing for the worst switcher case: m = 8 at 1.25 MHz is 10 MHz, a multiple of the 1 MSPS conversion rate, which the boxcar passes.

## 1. Spur source inventory

| Source | Frequency and tolerance | Relation to the ADC sample clock | Result |
|---|---|---|---|
| TPS65131 switcher | 1250 / 1380 / 1500 kHz (min/typ/max, SLVS493E §6.6); PSP = PSN = GND, so forced PWM. Boost runs forced CCM; inverter runs DCM at about 40 mA. | Free-running, with no sync pin | Any harmonic m ≥ 1 (m ≥ 2 at 60 kHz) can alias onto any grid point somewhere in the band. Content is edge-limited above about m = 25 (assumption A4). |
| RP2040 XOSC 12 MHz (±30 ppm tolerance, ±30 ppm stability), sys 120 MHz, USB PLL 48 MHz, CLK_GPOUT0 24 MHz, PIO SCLK 30 MHz/N, CONVST 1 MHz/N | Locked to the crystal | Every one is an integer multiple of every fs = 1 MHz/N (checked for N = 1–20) | Each aliases to exactly DC, which the fit's DC term absorbs. Zero error. |
| RP2040 ROSC | 1.8–12 MHz guaranteed (RP2040 datasheet §2.15). The SDK leaves it running. | Not locked | It drives no clock, so its amplitude is unknown but small. The NOISE gate catches it. |
| AD9833 DAC images | k·24 MHz ± f | Fold exactly onto f | −125 to −167 dBc at the source buffer input (zero-order hold, reconstruction filter and OPA810 roll-off). Negligible. |
| AD9833 harmonics and spurs | k·f. Datasheet THD −66 dBc typ / −56 dBc max at f = MCLK/4096; wideband SFDR −60 dBc typ; narrowband −78 dBc typ. The exact digital model (12-bit phase, 10-bit DAC) gives k = 3: −87, k = 9: −108, k = 11: −109, k = 49: −99, k = 51: −96, k = 99: −92 dBc. | Locked to the crystal, so the alias position is exact | Folds into the main lobe at low order for whole-kHz frequencies (finding 2). |
| USB SOF and host NAK polling | 1 kHz ±500 ppm on the host clock (USB 2.0 full speed), plus the microframe structure | Not locked; relative offset ≤ ±560 ppm | Inside the main lobe at every whole-kHz frequency (finding 1). |
| pico-sdk stdio_usb background task | Would be 1 ms on the board clock, but **this build is event-driven**: TinyUSB installs a shared USBCTRL handler, so `stdio_usb.c` skips the periodic timer (SDK 2.2.0, lines 223–231) | — | Not present. Kept in the scripts as a hypothetical board-clock 1 kHz comb, which would also fall inside the main lobe. |
| External 5 V adapter and mains ground loop through USB | Unknown | Not locked | Cannot be bounded. The NOISE gate catches it. |

## 2. Alias map (`alias_map.py`, `alias_map.json`, `mitigation.py`)

The script reproduces `divider_for`, the 28-bit DDS quantisation and the exact least-squares DC + cos + sin fit over 16 384 samples. Each spur is folded over its full tolerance band. "Response" is the worst-phase fitted phasor relative to a signal of equal amplitude: 1 means no rejection.

| Grid | f_DDS (Hz) | N | fs | Bin (main-lobe half-width) | SOF harmonics in main lobe | Worst SOF response, ±560 ppm | DDS harmonics in main lobe | Switcher harmonics that can reach it |
|---|---|---|---|---|---|---|---|---|
| **1 kHz** | 1000.0169 | 20 | 50 kHz | 3.05 Hz | 1, 49, 51, 99, 101… | 0 dB | 49, 51, 99, 101… | 40 of 40 |
| **35 kHz** | 34999.9666 | 2 | 500 kHz | 30.5 Hz | 35 | 0 dB | 99, 101, 199 | 40 |
| **40 kHz** | 39999.9619 | 2 | 500 kHz | 30.5 Hz | 40 | 0 dB | 24, 26, 49, 51… | 40 |
| **50 kHz** | 50000.0417 | 2 | 500 kHz | 30.5 Hz | 50 | 0 dB | 9, 11, 19, 21… | 40 |
| **60 kHz** | 60000.0322 | 1 | 1 MHz | 61.0 Hz | 60 | 0 dB | 49, 51, 99… | 39 (m = 1 cannot reach) |

Proposed grid, with SOF worst response over ±560 ppm:

| Proposed | N | Rectangular fit (current host) | 16 000-sample record | Hann-weighted fit | Lowest DDS k in main lobe |
|---|---|---|---|---|---|
| 1.5 kHz | 20 | −50.6 dB | −49.8 dB | −134.6 dB | 99 (response 0.46; 9 µF error 0.0008 %) |
| 35.5 kHz | 2 | −34.3 dB | −33.7 dB | −82.9 dB | none ≤ 200 |
| 40.5 kHz | 2 | −34.2 dB | −33.7 dB | −82.3 dB | none ≤ 200 |
| 50.5 kHz | 1 | −28.5 dB | −27.5 dB | −65.4 dB | none ≤ 200 |
| 60.5 kHz | 1 | −28.4 dB | −27.4 dB | −63.5 dB | none ≤ 200 |

A 16 000-sample record makes every record a whole number of milliseconds. It would null a board-clock comb to −87 to −102 dB, but no such comb exists in this build. It does not help against SOF, because the SOF lines drift with the host's ppm error.

Across the whole host range, a 1 Hz sweep of 99 901 frequencies finds:

- 60 frequencies with a DDS harmonic k ≤ 10 inside the main lobe, 175 with k ≤ 20 and 390 with k ≤ 50. All are round numbers, such as 5, 10 and 100 kHz, where k = 9/11.
- 8 411 frequencies with a board-clock 1 kHz comb line (h ≤ 300) inside the main lobe.

Choosing the divider differently fixes only 61 of the 175 frequencies with k ≤ 20. At 100 kHz no allowed divider avoids k = 9, so frequency choice is the reliable fix.

Switcher harmonics are a matter of chance because fsw is not known to better than 1.25–1.50 MHz. Each harmonic has a 4.97×10⁻⁴ chance of a fit response > 0.1, which is a 1/16 384-wide window at each fold. Bring-up: measure fsw on SW_P and run `python3 alias_map.py --fsw <Hz> [f1,f2,…]`. For example, at exactly 1.380 MHz, 40 kHz collides with m = 8, 17 and 33, and 60 kHz with m = 13 and 37. The proposed grid is clear at that fsw, and at 1.30 MHz.

## 3. Ripple chain (`ripple_chain.py`, `ripple_chain.json`)

**Operating point.** The estimated loads are +35.4 mA and −39.5 mA. Each assumes the IQ maximum of five amplifier channels at 4.5 mA, an 18 mA-peak source and TIA current, and the FDA input-resistor currents. The pessimistic corner uses 2× those loads, fsw = 1.25 MHz, VIN = 4.71 V after Q1, and L at −20 %.

| Stage | Pessimistic corner | Typical corner |
|---|---|---|
| RAW_P / RAW_N capacitive ripple, peak-to-peak (3 × 10 µF; retention 0.40 or 0.70, −10 % tolerance, −15 % temperature) | 4.27 / 5.38 mV | 1.06 / 1.45 mV |
| RAW fundamental, adding capacitance, ESR and an ESL spike term (A2–A4) | 9.8 / 9.9 mV | 3.3 / 2.7 mV |
| LDO PSRR at fsw: TPS7A49/TPS7A30 Figure 14 (COUT 10 µF, CNR = CFF = 10 nF; curves at 5 V / 6.2 V / 150 mA and −5 V / −6.2 V / 200 mA). The board runs at 12 V, 35–40 mA and ≥ 1.3 V headroom, so 6 dB is subtracted for the pessimistic corner. | 28.4 / 29.7 dB (34.4 / 35.7 dB read at 1.25 MHz, minus 6 dB) | 33.3 / 34.7 dB at 1.38 MHz |
| ±12 V ripple at fsw | 371 / 321 µV | 71 / 49 µV |
| OPA2810/OPA810 PSRR (Figure 55 / Figure 6-52, simulated at 24 V; 47 dB at 1 MHz, falling 20 dB/decade) | 45.1 dB at 1.25 MHz | 44.2 dB at 1.38 MHz |
| ADC input, worst harmonic, after the FDA filter (1.59 MHz and 5.3 MHz poles). Channel A has two followers; channel B has a follower plus the TIA at noise gain ≤ 2. | A 81 µV, B 121 µV (0.65 / 0.97 LSB) | A 12.7 µV, B 19.1 µV (0.10 / 0.15 LSB) |
| \|ΔZ/Z\| if one harmonic hits the main lobe, 15 Ω DUT (A = 0.18 V, B = 1.2 V): ±12 V path | **0.055 %** (m = 8) | **0.0087 %** (m = 7) |
| Same, with a matched 100 Ω load (A = B = 0.699 V) | 0.029 % | 0.0046 % |
| 5 V → FDA and ADC AVDD path, with no credit for FB1 and an assumed 30 dB ADC PSRR above 100 kHz | 0.065 % | 0.028 % |
| Same, crediting FB1 at ≥ 1 Ω into C103 and the local capacitors | 0.0007 % | 0.0005 % |
| Source-borne ripple (OPA810 gain 6 plus the source buffer) through a 50 µH coil, 35–60 kHz. Resistors are 0.011 %; capacitors are ≤ 0.019 %. | 0.11–0.19 % | 0.017–0.029 % |
| ±12 V path with R5 (≥ 1 Ω into the existing 10 µF LDO input capacitor) | 0.0033 % | 0.0006 % |
| USB/digital current through the supply rails (A9: 20 mA × 20 µs every 1 ms on 0.3 Ω), at 1–60 kHz | ≤ 4.9×10⁻⁷ | — |

These figures apply only when a harmonic lands within about one bin of f. Elsewhere the fit attenuates the ripple by its sidelobes. The pessimistic corner stacks every assumption at once, and the ESL spike term (A3, A4) dominates the high harmonics, so treat the 0.055 % as an upper estimate, not a bound.

## 4. Regulator stability and design rules (`regulator_check.py`, `regulator_check.json`)

The worst corners are 5 V ±5 % input, Q1 drop, full-temperature datasheet limits, 1 % or 0.1 % resistor tolerances, and 2× the estimated rail loads. There are no vendor DC-bias curves in the repository. Each capacitance check therefore reports the **break-even retention**: the fraction of nominal capacitance the part must keep at its bias, after −10 % tolerance and −15 % temperature drift. That is compared with an assumed conservative retention: 0.75 at ≤ 12 % of rated voltage, 0.40 at ≤ 35 %.

| Check | Value | Limit | Status |
|---|---|---|---|
| VPOS, R81/R82 at 1 %, VFBP limits | 13.776 / 14.313 / 14.866 V | ≤ 15 V recommended | Pass, 0.134 V margin |
| VNEG, VREF and VFBN limits, R83/R84 at 1 % | −13.655 / −14.394 / −15.145 V | ≥ −15 V recommended; −17 V abs max | **Flag**, see finding 4 |
| Inductor 4.7 µH ±20 % | 3.76–5.64 µH | 3.3–6.8 µH | Pass |
| Peak inductor current at the worst corner, 2× load | 0.724 A | < 1.8 A ILIM min; < 3.8 A Isat | Pass |
| Isat compared with ILIM max (start-up and short circuit) | 3.8 A | > 2.2 A | Pass |
| Duty cycle, all corners | 0.648–0.768 | 0.125–0.875 | Pass |
| Input capacitors C80 + C82 ≥ 2 × 4.7 µF at 5 V | Break-even retention 0.61 | ≤ 0.75 | Pass |
| RAW_P / RAW_N capacitance for 10 mV (datasheet Eq. 7/8) | Need 3.87 / 4.82 µF; break-even 0.17 / 0.21 | ≤ 0.40 | Pass |
| CP, CN, VREF capacitors; feed-forward C87/C88 = 4.3 pF | 10 nF, 4.7 nF, 220 nF; rule gives 4.20 / 4.21 pF | Datasheet §8.2.2.6 | Pass |
| PSP/PSN = GND (forced PWM); BSW floating; VIN RC 100 Ω / 100 nF; ENP/ENN = 3V3 (≥ 1.4 V) | — | Datasheet | Pass. ENP/ENN have an abs max of VIN + 0.3 V; check at power-down during bring-up. |
| SS14 reverse voltage | 14.87 V / 20.39 V | 40 V, derated 80 % | Pass |
| OUTN–INN differential / INP node | 20.94 V / 15.42 V | 24 V / 17 V abs max | Pass, with 3.06 V and 1.58 V of static margin before ringing |
| TPS7A49 / TPS7A30 output | 11.646–12.292 V / 11.672–12.320 V | ±2.5 % + 0.2 % | Pass |
| LDO headroom: minimum RAW minus maximum output | 1.484 V / 1.335 V | ≥ 0.6 V dropout; ≥ 1 V curve condition | Pass |
| COUT (C95 or C100 alone, 10 µF 50 V 1210) ≥ 2.2 µF | Break-even 0.288 | ≤ 0.40 | Pass, before counting 3 × 1 µF and 100 nF at the amplifiers |
| COUT / CIN placement (centres) | 7.8 / 9.4 mm (U11); 7.1 / **10.0** mm (U12) | ≤ 10 mm | Pass / marginal |
| CNR = CFF = 10 nF; R2 = 10 kΩ; Ifb 118 µA; EN tied to IN | — | ≤ 10 nF; ≤ 237 kΩ; ≥ 5 µA; allowed | Pass |
| LDO dissipation, 2× load | 0.23 W / 0.27 W | — | Pass |
| Switch node or magnetics to the nearest analog IC | 63.5 mm (D3 to U10) | Information only | — |

Sequencing: 3V3 enables the TPS65131, so the ±raw rails start after 3V3 and the 5VA rail. The TPS65131 soft-starts in about 1 ms. Each LDO tracks its input and soft-starts through its 10 nF NR capacitor. No datasheet sequencing requirement is violated.

## 5. Recommendations

| ID | Change | Basis | Effort |
|---|---|---|---|
| **R1** | **Host: change the default grid to 1500, 35500, 40500, 50500, 60500 Hz.** Warn when a requested f is within about 10 bins of a whole kHz (allowing ±560 ppm). | SOF rejection goes from 0 dB to −28 to −51 dB. DDS collisions with k ≤ 200 disappear (finding 2). Stage53 coil and capacitor impedances barely change over 500 Hz. | About 1 h: update the README and the default grid. Fresh calibration is needed anyway. |
| **R2** | **Host: pair each CAPTURE with a NOISE capture at the same f, N and DUT.** Reject the point if the source-off fitted tone exceeds 10⁻⁴ × the signal amplitude. | For a 15 Ω DUT, channel A is 1440 codes, so the threshold is 0.144 codes for 0.01 %. The fit's amplitude standard deviation is 0.011 codes per 1 LSB rms of white noise, so the gate can resolve that. This is the only check that covers SOF, ground loops, the adapter and switcher collisions, which this analysis cannot bound. | About half a day, host only; the firmware already has NOISE. It doubles capture time. |
| R3 | Host, optional: Hann-weighted least-squares fit. | SOF lines at ±500 Hz drop to −63 to −83 dB. The cost is a main lobe twice as wide, which roughly doubles the switcher collision chance, and higher noise bandwidth (a standard window property, not computed here). | About half a day plus recalibration. |
| R4 | Bring-up gates: measure fsw on SW_P and run `alias_map.py --fsw`. Scope RAW_P/N, ±12 V and 5VA for spikes. Sweep NOISE with USB attached and the real adapter. Scope 5 V during an adapter hot-plug, because there is no TVS and VIN/INN have a 6 V abs max. | Covers assumptions A3, A4 and A7, and the unbounded paths. | Bench time |
| R5 | PCB, optional: put a series element between RAW_P and U11 IN, and between RAW_N and U12 IN, with C94/C99 on the LDO side. A 1 Ω 0603 resistor gives exactly the credited ≥ 1 Ω, with no LC peaking (RC corner 52 kHz into the derated 10 µF). It drops 35–40 mV at the estimated load; LDO headroom stays ≥ 1.26 V even at 2× load. A ferrite such as the FB1 part works too, but its L with 10 µF would resonate near the measurement band. | ±12 V-path collision error drops ×17: 0.055 % → 0.0033 % (pessimistic), 0.0087 % → 0.0006 % (typical). Not required by the evidence; it is insurance against an unlucky fsw. | 2 BOM lines, re-route 2 nets, rerun rebuild/DRC/parity: about 2–3 h |
| R6 | BOM, optional: R83 1.78 MΩ → 1.74 MΩ (E96, 1 %). | VNEG stays within −13.35 to −14.81 V; U12 headroom ≥ 1.03 V. | One BOM line plus re-export |

No change is recommended to the TPS65131 inductor, its capacitors, the diodes, the LDO capacitors, or the enable and sequencing scheme. Firmware: none is required. The capture runs with no periodic board-clock task.

## Method and limits

- **Exact:** `divider_for`; DDS word quantisation; the least-squares fit response (`common.Fit`, the same estimator as `host/src/lib.rs::fit`); the crystal-locked aliasing; and the AD9833 digital model (ideal DAC levels, so DAC INL/DNL are excluded).
- **Typical curves, digitised by eye from the PDF figures** (about ±3 dB reading error): LDO PSRR (TPS7A49/TPS7A30 Figure 14/18), op-amp PSRR (simulated curves), THS4551 PSRR. Above 10 MHz the LDO PSRR is held flat at the last digitised value. No credit is taken for amplifier-local decoupling or for the TPS65131's own line rejection.
- **Assumptions:**
  - A1: output capacitor retention 0.40 / 0.70 at 14 V.
  - A2: ESR 10 / 4 mΩ per 10 µF capacitor.
  - A3: output loop ESL 3 / 1.5 nH.
  - A4: 10 ns current edges.
  - A5: 6 dB LDO PSRR derating at the pessimistic corner.
  - A6: 2× / 1× load.
  - A7: ADC AVDD PSRR 30 dB above 100 kHz. The datasheet specifies 70 dB only below 100 kHz.
  - A8: FB1 either uncredited or ≥ 1 Ω.
  - A9: USB/digital current pulse of 20 mA × 20 µs on 0.3 Ω.
  - AO3401A Rds(on) of 85 mΩ. Its datasheet is not in `sources/`.
- **Not modelled:**
  - Magnetic or capacitive pickup from L1/L2 and the switch nodes (≥ 63.5 mm from analog ICs).
  - Ground-return and USB-cable common-mode currents.
  - The adapter's noise and its hot-plug overshoot.
  - fsw drift with temperature.
  - Extracted PCB parasitics.
  - AD9833 INL-driven high-order harmonics, which are bracketed by the −80 and −60 dBc cases.
- **DUT error model:** a source-borne spur at fk changes Z by W·s·\|(Rg+Z(f))/(Rg+Z(fk))\|·\|Z(fk)/Z(f) − Zf(fk)/Zf(f)\|, with ideal amplifiers on the 100 Ω range. Injection after the DUT (followers, TIA, FDA, ADC) adds directly, relative to each channel's signal.
- **Signal levels:** 0.18 V (channel A, 15 Ω) and 0.699 V (matched) come from the brief and `docs/analog-validation-rev-c.md`. Channel B for 15 Ω is scaled by RF/Z.

## Files

| File | Contents |
|---|---|
| `common.py` | Acquisition rule, exact fit response, boxcar and filter models, cited datasheet constants and digitised curves |
| `alias_map.py` → `alias_map.json` | Spur folding for the grid, the proposed grid and test points; 1 Hz sweep; `--fsw` bring-up helper |
| `dds_spurs.py` → `dds_spurs.json` | AD9833 digital model, DUT-dependent error, both acquisition modes |
| `ripple_chain.py` → `ripple_chain.json` | Converter ripple → LDO → amplifiers → ADC; 5 V path; source-borne path; USB estimate; collision probability |
| `regulator_check.py` → `regulator_check.json` | Design-rule and tolerance-stack checks; R83 option |
| `mitigation.py` → `mitigation.json` | Grid, record-length and window options; divider study |
| `run_all.py` → `results.json`, `*.log` | Runs everything and writes the summary |
| `netdump.py` | Prints part and net connectivity from `cad/design.json` |
