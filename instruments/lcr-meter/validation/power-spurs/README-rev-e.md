# Power-supply interference, Rev E (codec) rerun

This reruns the [Rev C/D study](README.md) for the Rev E acquisition chain: TAC5112 codec ADC and DAC on one 187.5 kHz frame clock, one exact DFT line per tone over a coherent record (`host/src/rev_e.rs`), and the board at `af615c841` (SHA256 `80d44838…`). It is a desk analysis. No hardware exists.

```sh
python3 regulator_check.py   # design rules and tolerance stacks on the Rev E cad/design.json
python3 rev_e_spurs.py       # -> rev_e_spurs.json, about 1 s; log in rev_e_spurs.log
```

`regulator_check.py` needed one change: its nearest-analog-IC distance looked for the removed ADS9224R (U4). It now uses the parts that exist, and includes U14, the codec. 44 of its 45 rows pass on Rev E: the regulators, their dividers and their capacitors are the Rev D parts. **USB-C power (2026-10-21):** the DC jack and Q1 are gone and U16 (TPS2553, 1.0–1.16 A limit) feeds 5V from USB_VBUS. The input corners are now 4.40 V (USB 2.0 device minimum) and 5.5 V (Type-C vSafe5V maximum); after U16's 135 mΩ maximum and 45 mΩ of entry copper at 0.45 A the converter sees 4.32 V. The same 44 rows pass: duty 0.612–0.779 (limit 0.875), inductor current 0.38/0.55 A at 2× load (limit 1.8 A), VIN abs-max margin 0.50 V. The one FLAG row is the R5 option, which Rev D fitted as R95/R96. **Divider consolidation (2026-10-29):** U11's divider is now 82k/9.1k 1 % (basic) and U12's 100k over 5k + 1k + 5k (0.1 % lines already on the BOM), ±11.86 V nominal, removing the 91k and 10k lines; `ldo_divider_options.py` lists every option tried (no 1 % pair keeps U12 at ≥ 1 V). R83 is built as R83 240k + R111 1.5M (1.740 MΩ); C88 4.7 pF spans the whole string. `regulator_check.py` now reads divider legs as resistor strings from the netlist. The R95/R96 headroom row passes at 1.083 V (was the FLAG, 0.951 V); a new row adds divider TCR over 25 ± 35 °C and flags 0.970 V against the 1 V PSRR-curve condition (0.838 V on the old dividers); dropout holds. 45 of 46 rows pass. **Host rail window (2026-10-29):** `rail_monitor_window.py` carries the rail range (with TCR) through the monitors as the host reads them. Worst healthy readings: +12 V 10.42–13.18 V, −12 V 10.71–13.87 V. The −12 V reading is about 16× as sensitive to its pin voltage as the rail, so 3V3 error and the RP2040's ±1 µA pin leakage dominate it, and the RP2040's 100 kΩ minimum ADC input impedance, as a load over a 257-conversion burst on the 100 nF hold capacitors, can pull a reading 2.1 % low. The old 10.8–13.2 V window could refuse a healthy board on either rail; the host now uses 10.2–13.4 V (+12) and 10.5–14.1 V (−12), and refuses a calibrated measurement when a rail moved more than 8.6 % / 9.7 % since calibration (temperature, leakage and ADC terms only; part tolerances cancel on one board). The ADC error (±8 LSB) is an estimate: RP2040 publishes no gain or offset limit. The switcher is 64.6 mm from the codec (D3 to U14). The Rev D loads include the removed FDAs' bias current, so the rail loads are conservative for Rev E.

## Verdict

**No change to the board or BOM before ordering.** Two of the four Rev D findings are much smaller on Rev E. One is unchanged and is a host-software item. One mechanism is new: images of the DAC output near the codec's modulator clock. It cannot be settled from the published data. If it were real, the first board would show it plainly in one bench test, and there is a BOM-only fallback.

| # | Mechanism | Rev D | Rev E | Action |
|---|---|---|---|---|
| 1 | USB SOF lines (host clock, 1 kHz ±560 ppm) on the tone | 0 dB rejection at every whole kHz | Unchanged: 0 dB at every whole kHz. 221 of the 3 627 integer frequencies the host can play exactly have response > 0.1, all within 50 Hz of a whole kHz. The half-kHz grid gives −51 to −54 dB | Host: use 1500, 27500, 35500, 40500, 50500, 60500 Hz (all exact tones). Source-off check ported (R-E2, done) |
| 2 | Switcher harmonic lands on the tone | 2 % chance per frequency (any of 40 harmonics, SAR folds everything) | 0.010–0.091 % chance per frequency (only harmonics within the decimation passband of a modulator multiple reach the line). Every other alias is ≥ 90.5 dB down | None. Bring-up R4 unchanged |
| 3 | Source spurs fold onto the tone | AD9833 harmonics k = 9/11 at 50 kHz etc. | DAC harmonics fold onto the line only through the ≥ 90.5 dB stop band (lowest folding order k = 14 at 50 kHz, k = 24 at 60 kHz). Crystal-locked clocks are all multiples of fs and alias to DC | None |
| 4 | **DAC images at N·f_mod ± f (new)** | AD9833 images at 24 MHz: −125 to −167 dBc | Fold exactly onto f. Pessimistic estimate up to 0.75 % on a coil (table below); the datasheet says both converters reject these bands, by an amount not published | No board change. Bring-up gate B-E1; BOM fallback C34/C35 |
| 5 | **USB VBUS as the only supply (new, USB-C power)** | External regulated adapter; the adapter–USB ground loop was not modelled | A host VBUS line must sit inside the tone's DFT line response (16 Hz of offsets with response > 0.1, 0.25 s record) and be at least 25 mV (9 µF at 60.5 kHz, 12 mV at 85 kHz) or 0.44 V (the other reference parts at 60.5 kHz) to reach 10⁻⁴. The adapter ground loop is gone | None. Source-off check (R-E2) sees such a line; bring-up §5 step 3 on the real host |

## 1. USB start-of-frame lines

A coherent capture rejects anything off its line by the Dirichlet response of the record (0.25 s: 4 Hz bins). A SOF line within ±560 ppm of the tone is not rejected at all. Results at the 0.25 s default length:

| Tone | CYCLES/PERIOD | Worst SOF response | | Tone | CYCLES/PERIOD | Worst SOF response |
|---|---|---|---|---|---|---|
| 45.776 Hz | 1/4096 | −59.9 dB | | 1500 Hz | 1/125 | −54.1 dB |
| 1000 Hz | 2/375 | **0 dB** | | 27500 Hz | 11/75 | −51.6 dB |
| 27000 Hz | 18/125 | **0 dB** | | 35500 Hz | 71/375 | −51.6 dB |
| 35000, 40000, 50000 Hz | | **0 dB** | | 40500 Hz | 27/125 | −51.5 dB |
| 60000, 80000, 85000 Hz | | **0 dB** | | 50500 / 60500 Hz | 101/375, 121/375 | −51.4 / −51.3 dB |

The host already warns (`sof_response`) but captures anyway, and its Rev E examples used 27 and 60 kHz. The SOF amplitude reaching the analog chain cannot be bounded from datasheets (Rev D estimate through the rails: ≤ 4.9×10⁻⁷ of |Z|; the cable and ground paths are unbounded).

## 2. Switcher harmonics

TPS65131 fsw is 1.25–1.50 MHz, free-running and unknown per unit. For a harmonic x = m·fsw to reach the tone at full amplitude, x must sit within the decimation passband of a modulator multiple: x = k·f_mod ± f. Elsewhere the codec's low-latency decimation filter takes ≥ 90.5 dB (SLASF24A Table 7-38). The modulator rate at 187.5 kHz is unpublished, so 8, 16, 32 and 64 fs (1.5–12 MHz) are all evaluated.

- **Chance of a collision** (fit response > 0.1, fsw uniform): 9.1×10⁻⁴ (8 fs) down to 9.6×10⁻⁵ (64 fs) per frequency at 0.25 s, doubled at 85 kHz where the fs − f image falls in the unspecified transition band (E4). Rev D: 2 %.
- **Error if one does collide** (ripple from `ripple_chain.py`, the same rails, LDOs and op-amps as Rev D; codec divider 0.5 and the 568 kHz input pole replace the FDA):

| Target | ±12 V path, pessimistic / typical | 5 V → AVDD path, no FB1 credit / FB1 ≥ 1 Ω | Source-borne, pessimistic |
|---|---|---|---|
| 15 Ω resistor | 0.050 % / 0.008 % | 0.16 % / 0.002 % | 0.003 % |
| Coil 50 µH, 27.5 kHz | 0.074 % / 0.012 % | 0.24 % / 0.003 % | 0.098 % |
| 100 nF, 35.5–60.5 kHz | 0.021–0.029 % / ≤ 0.005 % | 0.06–0.09 % / 0.001 % | 0.004 % |
| 500 nF, 35.5–60.5 kHz | 0.072–0.117 % / ≤ 0.020 % | 0.23–0.38 % / 0.004 % | 0.004 % |
| 9 µF, 1.5 kHz | 0.056 % / 0.009 % | 0.18 % / 0.002 % | 0.004 % |

These are at the USB input corners (4.32 V worst, after U16). The adapter-era values were up to 16 % higher.

The AVDD column with no FB1 credit also takes 0 dB from the AP2112K at MHz (E6) and 30 dB from the codec's AVDD (E5; 107 dB is specified only at 1 kHz). These are the Rev D-style upper estimates, now multiplied by a collision chance 20–200 times smaller.

## 3. Source spurs and locked clocks

- The DAC plays an exact digital sine; harmonics come from the analog DAC and amplifiers (DAC THD+N −94 dB at −1 dBFS, the firmware cap is −3.6 dBFS). Harmonic k folds onto the tone bin when (k ∓ 1)·CYCLES ≡ 0 mod PERIOD. On the grid the lowest such k is 14 (50 kHz), 24 (60 kHz), 74 or 124 elsewhere, 374 on the half-kHz points. All of them sit in the decimation stop band: ≥ 90.5 dB below an already −94 dBc harmonic.
- XOSC 12 MHz, clk_sys 120 MHz, USB PLL 48 MHz, BCLK 12 MHz and flash SCK 60 MHz are all integer multiples of fs. They alias exactly to DC, which the DFT line ignores.
- **Activity periodic in the waveform period** (the TX DMA re-trigger every PERIOD frames) has lines at multiples of fs/PERIOD, i.e. on every bin including the tone's. Its coupling is unknown and tiny, and only a source-off capture **at the same PERIOD** sees it (R-E2).

## 4. DAC images at the modulator rate (new)

The DAC's delta-sigma modulator holds its output at f_mod, so the tone has images at N·f_mod ± f. The ADC modulator samples at a crystal-locked multiple of fs, so an image within its decimation passband of a multiple of f_mod folds **exactly** onto f. The image passes through the DUT like the tone, so A/B cancels it except for the DUT's frequency dependence: the same formula as Rev D's `dds_spurs.py`, with the Rev E source (R104 + RG), R_iso, R_F‖C104 and the 568 kHz input pole. A resistor-only calibration absorbs the resistor part. A reactive DUT keeps the rest. **Calibrated error, coil 50 µH, any tone 27–85 kHz**:

| Modulator rate | No credit (E2 + E3) | Credit for 20 dB total rejection | Credit for 40 dB |
|---|---|---|---|
| 8 fs, 1.5 MHz | 5.2–5.5 % | 0.53 % | 0.053 % |
| 16 fs, 3.0 MHz | 0.73–0.78 % | 0.075 % | 0.0075 % |
| 32 fs, 6.0 MHz | 0.095–0.10 % | 0.010 % | 0.001 % |
| 64 fs, 12 MHz | 0.012–0.013 % | 0.001 % | — |

Capacitors are 9–15× smaller (16 fs: 0.05–0.08 % for 100 nF and 500 nF at 35.5–60.5 kHz, 0.12 % at 85 kHz). Resistors are 0.

**Why "no credit" is pessimistic.** It assumes a plain zero-order hold on the DAC (image ≈ f/f_mod of the tone, then the U5 pole at 284 kHz) and a sampling ADC with no alias rejection. The TAC5212 datasheet (SLASF23, the TAC5112's register-compatible sibling) says the opposite for both:
- ADC: "inherent antialias filtering with a high rejection of out-of-band frequency noise around multiple modulator frequency components".
- DAC: the same sentence for the playback path.

Neither number is published. TI's note for the sibling ADC family, [SBAA377](https://www.ti.com/lit/pdf/sbaa377) §2, quantifies it: notches in the modulator's signal transfer function attenuate N·FMOD ± 20 kHz by more than 100 dB, at FMOD 6.144 MHz for the 48 kHz family. With that credit, tones up to 20 kHz are clear (`calibrated_sbaa377_notch_credit` in the JSON). The 27–85 kHz tones lie outside the ±20 kHz the note covers, and wideband mode is not in it.

**Decision: no board change.** The mechanism needs two pessimistic assumptions that the datasheet contradicts. On the first board, the range screen below shows it at 5–20 times its size on the Temper targets.
- **Bring-up gate B-E1 (range screen)** (`range_screen` in the JSON). The image error grows with the range resistor in series with the source. Read one inductor on the 100 Ω range and on the 5 kΩ range at the same frequency and level, each with its own calibration. Pessimistic disagreement:

| Inductor | 8 fs | 16 fs | 32 fs | 64 fs |
|---|---|---|---|---|
| Cal kit L1, 47 µH at 60.5 kHz: 100 Ω vs 5 kΩ range | 5.6 vs 17.1 % | 0.79 vs 4.5 % | 0.10 vs 1.08 % | 0.013 vs 0.23 % |
| 1 mH at 27.5 kHz | 0.41 vs 7.4 % | 0.056 vs 1.07 % | 0.007 vs 0.14 % | 0.001 vs 0.018 % |

  The accuracy map puts both ranges at ≤ 0.2 % (corner) for 10–316 Ω at these frequencies. **Pass:** L and R agree within 0.3 %. That bounds the Temper coil's image error to about 0.06 % at 16 fs (0.03 % at 32 fs, 0.14 % at 8 fs). **Fail:** apply the fallback, then repeat.
- **Fallback, BOM only:** C34/C35 (U5 feedback and ground-leg capacitors, now each two 560 pF in series with C114/C115) → 1 nF C0G with 0 Ω at C114/C115. The pole moves to 80 kHz, which cancels in A/B. It cuts the image error 3.6× (16 fs, 27 kHz coil: 0.73 → 0.21 %) for −0.5 / −2.0 / −3.3 dB of tone at 27 / 60 / 85 kHz (`source_cap_options`). A full fix past that would need a second source pole (a layout change for a later revision).
- The reference-meter measurement of the cal kit's L and C (CHARACTERIZE.md §1) also bounds this directly, to the reference meter's accuracy.

**85 kHz.** Above 0.429 fs = 80.4 kHz, the DAC interpolation image at fs − f lands in the ADC's unspecified 0.456–0.571 fs transition band and folds onto f. Neither attenuation is published. Treat 80–85 kHz as unverified until the bench sweep in the firmware README (step 9) also checks a reactive DUT there.

## 5. USB VBUS, the only supply (new with USB-C power)

Since 2026-10-21 the board runs from USB-C VBUS through U16 (TPS2553). A host's VBUS noise has no fixed spectrum, so `vbus_tolerance` reports the reverse: the coherent VBUS ripple at the tone frequency that makes a 10⁻⁴ |Z| error, through two paths (E10):

- **5V → FB1 → U15 (AP2112K) → codec AVDD.** AP2112K PSRR from its datasheet curve (DS39724 p.11: 67 dB to 3 kHz, 45 dB at 60 kHz, 41 dB at 85 kHz). Codec AVDD PSRR counted as 60 dB across the tone band (121 dB is specified at 1 kHz). FB1 credited 0 dB.
- **5V → TPS65131 (0 dB) → TPS7A49/TPS7A30 → op-amps.** Rev D's digitized PSRR curves.

Ripple riding on the source tone is ratiometric and cancels. The AVDD path dominates everywhere. Worst DUT and path, from `rev_e_spurs.json`:

| Tone | 45.8 Hz | 1.5 kHz | 27.5 kHz | 35.5 kHz | 40.5 kHz | 50.5 kHz | 60.5 kHz | 85 kHz |
|---|---|---|---|---|---|---|---|---|
| VBUS line for 10⁻⁴ | 498 mV | 737 mV | 230 mV | 112 mV | 75 mV | 39 mV | 25 mV | 12 mV |

The worst DUT is the 9 µF capacitor, whose impedance is small at high frequency; the stage53 plan measures it at 1.5 kHz. The 15 Ω resistor, the coil and the 100/500 nF capacitors need 0.44 V or more at 60.5 kHz. A line also has to fall within the line response, 16 Hz of offsets around the tone with response > 0.1 (`line_response_width_hz`, 0.25 s record), to count at full weight. The source-off capture (R-E2) measures exactly that bin on every point, so a host that does have such a line fails the check rather than biasing the result.

## Recommendations

| ID | Change | Basis | Cost |
|---|---|---|---|
| **R-E1** | Host: recommend the half-kHz grid 1500, 27500, 35500, 40500, 50500, 60500 Hz in the Rev E docs and examples | §1: 0 dB → −51 to −54 dB SOF rejection; every point is an exact tone | Docs (done with this rerun) |
| **R-E2** (done: commit "host: Rev E source-off check (zero WAVE, same SKIP and PERIODS) and 80-85 kHz advisory") | Host: port Rev D's source-off check to Rev E. Upload a zero waveform of the same PERIOD (`WAVE`), capture with the same SKIP and PERIODS, require the tone bin below 10⁻⁴ of the source-on amplitude on each channel | The only check that sees SOF coupling, ground loops, the adapter, switcher collisions and PERIOD-locked board activity. `OFF` alone uses PERIOD 16 and cannot see the tone bin | Host only, about half a day; doubles capture time |
| B-E1 | Bring-up range screen (§4) | Settles the DAC-image question on the first board | 20 min bench |
| R4 | Bring-up: measure fsw on SW_P; scope the rails (Rev D R4) | Unchanged | Bench |

## Method and limits

- **Exact:** the host's tone rule and capture length, the coherent DFT line response, crystal-locked aliasing, the harmonic folding rule, and the circuit values from `cad/design.json` (R30/R31 2.2 kΩ, C34/C35 270 pF, divider 1 kΩ/1 kΩ, C69/C70/C72/C73 560 pF, R104 47 Ω, R94 22 Ω, C104 100 pF).
- **Assumptions E1–E10:** listed in the script header and in `rev_e_spurs.json`. The ripple chain keeps Rev D's A1–A9.
- **Not modelled:** magnetic and capacitive pickup from the switcher (64.6 mm to the codec); ground-return and USB-cable currents; the spectrum of any particular host's VBUS (§5 gives the tolerance instead); amplifier loop gain at 1.5–12 MHz (ideal followers, TIA and driver; OPA2810/OPA810 GBW 70 MHz). DUT self-resonance above the tone is also excluded: the coil and capacitors are ideal up to the images.
- **DUTs:** the Rev D stage53 set on the 100 Ω range, at the frequencies each is measured at.
