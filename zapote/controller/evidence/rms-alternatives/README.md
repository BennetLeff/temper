# Tank-RMS channel: is there a much cheaper way?

Study only. No schematic, layout, BOM or firmware was edited. Date of price/stock snapshot: 2026-10-12 (read-only JLC public parts endpoint, `lcsc-snapshot-2026-10-12.json`).

Rerun (numpy only, about 2 s, no network):

```
python3 zapote/controller/evidence/rms-alternatives/rms_alternatives.py
```

It rewrites `results.json` and `cost.csv` next to itself and exits non-zero if either control assert fails.

## 1. Question

The tank-RMS channel is U14 AD8436BRQZ + U15 MCP3202 + 16 passives (controller.ato, signals `rms_*`). The BRQZ is $27.30 at LCSC with JLC stock 0, against a ~$200 PCB budget for a $1200-1500 cooker. Is there a much cheaper way to get a tank-current RMS good enough for its job?

## 2. Pass criterion (fixed before the results)

### What the RMS reading is used for (firmware `ps-integrate/firmware/components/power/`)

| Use | Where | Needs |
|---|---|---|
| RMS trip: latch `N21_FAULT_TANK_RMS` when half-cycle RMS > 1.05 x ceiling (23.1 A at 22 A, 29.4 A at 28 A); `config_ok` forbids a trip above 1.1 x ceiling | `n21_binding.c:81-84, 157`, `tank_freq.h:12, 81` | accuracy; one value per half line cycle |
| Frequency loop limit: step f down while half-cycle RMS <= effective ceiling; overrun latch after 12 halves (100 ms) | `tank_freq.c:168-184`, `tank_freq.h:21` | accuracy; ~100 ms latency is tolerated |
| No-pan clamp / pan evidence: needs RMS >= 4 A and p_inv/I^2 >= 0.8 ohm | `tank_freq.c:22, 162` | small-signal accuracy at 4 A |
| Power estimate: P_inv = mean(2sqrt2/pi x Vbus x I_rms x cos phi), inlet bound = I_ps x (1 + est_error) + I_aux, so each 1 % of RMS under-read must be absorbed by `est_error` (power given up 1:1) | `input_limits.h:13-17`, `input_limits.c:52-61` | accuracy; under-reading is the unsafe direction |
| Peak estimate and crest guard (1.5 x ceiling on each slot reading) | `n21_binding.c:164-165, 241`, `tank_freq.h:13, 83` | per-slot value must not be noisier than the 120 Hz envelope crest |

The firmware reads the converter on a 625 us acquisition slot (13 slots per half cycle, `n21_binding.h:9`) and forms the half-cycle RMS as sqrt(mean of slot readings squared).

### Which protections are hardware and which depend on the RMS reading

- **Hardware, independent of this channel:** CT peak comparator trip band 64.55-76.09 A (R43/R46 = 2.21 k) and the shunt OCP 66.30-118.74 A (stage-15 PLAN section 0, `power-stage-120v/validation-results/02-protection-timing/stage15-28A/PLAN.md`).
- **Firmware from raw CT_MON (ADC1, not this channel):** peak trip = min(2.17 x ceiling + 3, 62) A (`n21_binding.c:229`).
- **Depends on the RMS reading:** the 1.05 x ceiling RMS trip and everything above. It guards the sustained-current regime between the ceiling and the peak trips (coil, bank hot-spot, FET and R5 heating), which is thermal, not microsecond. Power-stage DECISIONS item 13 already notes the CT-fed firmware peak/RMS trips share the CT with each other.

### Accuracy the project assumes

- `COMMISSIONING.md` Step 6.1: telemetry `tank_rms_a` within **2 %** of a current probe after the Step 1 gain trim (`rms_gain_trim`, 40 kHz sine).
- Step 7 turns the remaining error into `est_error` (provisional 10 %; > 50 % is rejected by `input_limits_config_ok`).
- Stage 15 thermal basis: R5 dissipates 0.864 W at the 29.4 A trip against its 1 W rating (PLAN, line 203), i.e. the part is good to 31.6 A = 1.13 x 28 A. At -3 % read error the real current at the trip point is 1.05/0.97 = 1.0825 x ceiling = 30.3 A at 28 A, inside that.

### Criteria

1. **Accuracy.** Worst-case error of the half-cycle RMS against the true half-cycle RMS, over the waveform set (31-55 kHz, ZVS-side, near-resonance, pan removal, burst, 4-28 A), after the one-point trim, **plus** the tolerance stack, within **+/-3 %** (2 % trimmed commissioning gate + 1 % allowance). A negative error (reads low) is the unsafe sign and must meet the same bound.
2. **Response.** The estimate must be valid per closed half cycle (8.33 ms) including burst edges (no more than 3 % error in the first and last ON half cycle), and the converter should settle to 1 % within half a half cycle (4 ms). The 100 ms overrun latch sets the outer limit.
3. **Failure.** A single failure of the chain must not leave a silent low reading, or must be catchable by a cheap firmware check.
4. **Cost.** "Much cheaper" is taken as at least half of today's chain at 4 boards, without failing 1-3.

## 3. Method

`rms_alternatives.py` synthesises the series-resonant current as the harmonic sum of a square-wave-driven series RLC (L = 70 uH, C = 0.5 uF, f_res 26.9 kHz, harmonics 1-15), multiplied by the unsmoothed |sin| line envelope, and normalised so the true half-cycle RMS equals the stated current. Cases (17 windows): nominal pan at 31, 35, 40, 45, 50, 55 kHz and 22 A; low-R pan at 35 and 55 kHz and 28 A; f = 1.05 f_res with R = 0.15 ohm (empty coil / pan removal) at 22 A and 4 A; a pan at 1.05 f_res; far above resonance (L = 35 uH); a stress waveform with 12 % third and 6 % fifth harmonic; the 40 kHz sine trim signal flat and under the line envelope; and a 4-on/4-off half-cycle burst (first and last ON window). I did not reuse the 05-resonant-tank-envelope waveforms; this synthesis is simpler and covers the same current shapes, but it has no ZVS commutation ringing.

Each option is run through its signal chain and the firmware estimator on a 2 MS/s grid, with five slot phases against LINE_ZC, then one-point trimmed on the 40 kHz 22 A sine (as COMMISSIONING Step 1). Reported: the **systematic** error (min..max) and, for the converters, the **converter-only** error from the exact half-cycle window (isolates the part from the 13-slot estimator).

**Models**
- AD8436 (A0, A1) and LTC1968 (D): single pole that gives 1 % additional error at 65 kHz at 300 mV (the datasheet bound cited in DECISIONS C19; I could not re-read the datasheet, see Risks), averaging tau = 0.49 ms (DECISIONS C19's 3.4 ms to 0.1 %), 16 k / 10 nF output filter, x4 buffer, 12-bit MCP3202. LTC1968 uses 500 kHz (ADI product page, as quoted in DECISIONS C19; UNVERIFIED).
- B (precision full-wave rectifier, mean-|x| x 1.1107, 0.2 ms RC): TLV9062 (10 MHz GBW, 6.5 V/us from the LCSC listing), Schottky Vd = 0.30 V. Dead zone per zero crossing: open-loop slew through Vd, lost area = s t^2 with t = sqrt(2 Vd / (pi GBW 0.5 s)) + 2 Vd / SR. First-order, not SPICE.
- C (ESP32-S3 ADC1 continuous mode on the existing CT_MON path): 80 kS/s, the README's 9-slot pattern with CT_MON in slots 1 and 3, 12-bit over 2.9 V, noise 2 LSB, cubic INL 15 mV, 1 MHz sample/hold bandwidth. C1 is the pattern as built; C2 picks the sample clock per half cycle from 64 candidates (72.0-80.0 kS/s) minimising the exact figure of merit |mean exp(j 2 pi k f t_k)| (k = 2, 4, 6), which the firmware can compute from its commanded f.
- Tolerance stack (percent, worst case, added to the systematic error): LM4040A25 ratio reference 100 ppm/K x 45 K = 0.45; AD8436 gain 50 ppm/K ASSUMED = 0.23; trim residual 0.10; for C the ESP32 ADC gain drift 1.0 and INL residual 0.5 (both ASSUMED, no datasheet figure found).

**Controls (asserted by the script, both pass)**
1. Pure sine form factor rms/mean-abs = 1.11072 (= pi / (2 sqrt2), prints as 1.1107).
2. 300 mV rms sine at 65 kHz through the whole A pipeline: additional error -0.93 % against the 1 % datasheet figure, inside the model tolerance of 0.1 %. This is a one-parameter fit to the guaranteed point, so it checks the plumbing, not the datasheet; the model deliberately stays pessimistic against the typical 1 MHz -3 dB.

## 4. Results

### Accuracy and response

| Option | Systematic error, whole chain with today's 13-slot estimator | Converter-only (exact window) | + tolerance | Worst case | Step to 99 % | Pass +/-3 % |
|---|---|---|---|---|---|---|
| A0 AD8436BRQZ (as built) | -2.95 .. +1.14 % | -0.69 .. +0.01 % | +/-0.78 % | -1.46 .. +0.79 % converter; -3.73 .. +1.92 % whole chain | 2.1 ms (90 %: 1.0 ms; 99.9 %: 3.2 ms) | converter yes; whole chain no (see finding below) |
| A1 AD8436ARQZ-R7 | same | same | same stack (grade not re-read) | same | same | same |
| B precision FW rectifier (TLV9062) | -7.27 .. +3.51 % | -4.81 .. +2.44 % | +/-0.98 % | -5.78 .. +3.41 % converter | 0.8 ms | **no** (reads low, 3.6 % at 55 kHz, 4.8 % at 4 A) |
| C1 ESP32 ADC, pattern as built | -98.3 .. +41.7 % | n/a | | | | **no** (phase lock) |
| C2 ESP32 ADC, sample clock chosen per half cycle | -1.54 .. +1.39 % | n/a | +/-1.60 % (ASSUMED) | -3.14 .. +2.99 % | 0.6 ms (one slot) | marginal: 0.14 % outside on the low side, entirely from the assumed ADC drift |
| D LTC1968 | -2.94 .. +1.12 % | -0.68 .. 0.00 % | +/-0.78 % | -1.46 .. +0.78 % converter | not modelled (CAVG unknown) | converter yes |

Key findings

1. **The AD8436 itself is not the accuracy problem.** Its converter-only error is -0.7 .. 0 % across 31-55 kHz and every waveform; burst edges leak under 0.7 %. The 55 kHz droop (-0.5 %) is trimmed out at 40 kHz.
2. **Today's estimator is.** Because `n21_half` pools only 13-14 slot readings and the window starts and ends at the line zero crossings, the half-cycle RMS scatters between -2.95 % and +1.14 % with slot phase, for A, B and D alike. A one-point trim cannot remove it. It is a modelling result from reading `input_limits.c:52-61` and `n21_signal.c:107-120`, not from running the firmware tests; it should be confirmed on the bench (COMMISSIONING Step 6.3 is the right place) and is cheap to fix (time-weight the slots or add a trapezoid end).
3. **B fails on physics, not on parts.** A rectifier's dead zone is a fixed area per zero crossing, so relative loss grows with frequency and falls with amplitude: it reads low (the unsafe sign) by 2-3.6 % at 40-55 kHz and 4.8 % at 4 A, even with a 10 MHz op-amp. A 100 MHz part (OPA2354, $12.31) would fix it and cost as much as an AD8436ARQZ. The form factor itself is not the issue: the sine factor is exactly 1.1107 and the real tank waveforms deviate from it by under 0.2 % (`stress` case +2.4 % only with the 12 %/6 % distortion).
4. **C works only with sampling retime.** With the 9-slot pattern, CT_MON samples fall 25 us apart every 112.5 us. At f = 40.00 kHz (one carrier period = the 25 us pair spacing) and at k x 8.889 kHz (35.56, 44.44, 53.33 kHz; the pattern repeat is 112.5 us), with neighbours (8.9 % of 50 Hz bins over 2 %, 4.0 % over 5 %), the samples sit on two phases and the RMS reads **-98 % .. +42 %**, which is a silent low reading in the unsafe direction. The 250 Hz frequency loop and a 40 kHz bench trim both land on those bins. Choosing the sample clock per half cycle brings the worst bin on a 22 A sine to 1.2 % and 0 % of bins over 2 % (scan in `results.json`). That costs VBUS sample rate (24.0 .. 26.7 kS/s against the 20 kS/s requirement; worst gap 69 us against 150 us).
5. **C's per-slot estimates are noisier than the crest guard allows.** A 625 us slot holds ~11 samples; the largest per-slot RMS at 22 A comes out 34.5 A against the 33 A guard (1.5 x ceiling), so the guard would nuisance-trip. It would have to be rewritten on the peak instead.

### Cost per board (USD, LCSC tier price, `cost.csv`)

| Option | Parts removed / added | Qty 4 boards | Qty 1000 boards | JLC stock (2026-10-12) |
|---|---|---|---|---|
| A0 AD8436BRQZ (as built) | 18 parts (U14, U15, 16 passives, BAT54S) | **$30.24** | $27.74 | U14: **0** |
| A1 AD8436ARQZ-R7 (C495329) | swap U14 only | **$15.04** (saves $15.20) | $13.25 | U14: 106 |
| B FW rectifier + MCP3202 | -U14 and 6 passives, +2 TLV9062, 2 BAT54S, 6 x 0.1 % R, caps; 26 parts | $3.08 chain, but U15 kept (included); saves $27.2 vs A0, $12.0 vs A1 | $1.87 | all in stock |
| C ESP32 ADC (no converter) | -U14, -U15, 16 passives, BAT54S; frees GPIO42 and the RTD-bus device; nothing added | **$0** (saves $30.24 vs A0, $15.04 vs A1) | $0 (saves $27.74) | n/a |
| D LTC1968IMS8 (C679077) | -U14, -gain resistors, +5 V supply for U14 | $13.98 (saves $16.3 vs A0, $1.1 vs A1) | $12.50 | **17** |

Other candidates (stock/price, `cost.csv`): LTC1967CMS8 $9.04 / 910 in stock (4.5-5.5 V, bandwidth not verified); LTC1966CMS8 $8.28 / 3041 (micropower, bandwidth not verified, believed far below 55 kHz); AD637ARZ $73.37 / 193, AD637JRZ $20.07 / 78 (8 MHz but +/-3-18 V and large); AD736 family: **0** in stock on every variant; AD8361 is an RF detector (100 MHz+ class, wrong band). None of these is "much cheaper" than the ARQZ once the 5 V rail, stock and unverified bandwidth are counted.

### Failure behaviour

| Option | Failure | Reads | Detected today |
|---|---|---|---|
| A | AD8436 or output buffer stuck at 0 V, CAVG open | low (0 A) | Not by `n21_binding.c`: it only checks the ADC and the LM4040 reference channel (`N21_FAULT_RMS_CHANNEL`) and the 3.3 V window. The firmware peak trip from raw CT_MON and the hardware comparator still protect. |
| A | MCP3202 SPI failure or wrong CS | stale/zero | yes: ref-channel check, freshness |
| B | op-amp or diode open | low | no; same as A |
| C | CT_MON buffer (TLV9062) dead | 0 A and the firmware peak trip is blind too (common cause), hardware comparator remains | `N21_CT_MON_MIN_MV` < 50 mV catches an unplugged J4 only |
| C | DMA stall | stale | yes: freshness checks |
| C | Sample/tank phase lock | low, silently | only with the figure-of-merit guard added in C2 |
| all | cheap fix: plausibility check RMS >= max|CT_MON| / (1.05 x 2.17) per half cycle (uses `TANK_PEAK_PER_RMS` and `ct_abs_max_a` that already exist) | | would catch every stuck-low case above |

## 5. Recommendation

1. **Now, prototypes: fit the AD8436ARQZ-R7 (C495329, 106 in stock).** It saves $15.20 per board at 4 boards ($14.5 at 1000), removes the zero-stock/consignment dependency, and the model gives -1.46 .. +0.79 % converter worst case, inside the +/-3 % criterion. The 0.5 % vs 0.25 % grade difference is an initial gain error that the Step 1 trim removes. This is the same call DECISIONS C19 already offered, with its "RMS-trip error-budget check" now done.
2. **Production candidate: delete the whole chain and compute the RMS from the existing raw CT_MON ADC1 path (option C).** Saves 18 parts and $30.24 (BRQZ) / $15.04 (ARQZ) per board, frees GPIO42 and the RTD-bus device, and shortens the analog route in the front-left corner (LAYOUT.md line 110). CPU is negligible: the DMA already runs, and the firmware only accumulates about 142 squares per half cycle. It meets the criterion only if (a) the sample clock is retimed per half cycle as in C2, (b) the crest guard is rewritten on the peak (finding 5), (c) the plausibility check above is added, and (d) the ESP32-S3 ADC gain drift over temperature and its INL at 55 kHz stay within what I assumed (1 % and 0.5 %). None of these is measured, so the prototype must carry **both**: leave U14/U15 populated on the prototypes, add a shadow RMS from CT_MON in bench firmware, and compare against the AD8436 and a current probe over 0-70 C and 31-55 kHz. Delete the chain at production if C2 stays inside 3 %.
3. **Reject B** (reads low by up to 5.8 %, 3.6 % even at 55 kHz/22 A; the fix costs as much as the ARQZ) and **D** (a $11 part with 17 in stock and a 5 V rail, saving $1 against the ARQZ).
4. **Fix the estimator whatever is chosen:** time-weight the slot readings at the window edges (finding 2).

## 6. Risks and what is not verified

- **No datasheet could be read from this network.** `datasheet.lcsc.com` returns HTML and `analog.com` did not respond (WebFetch timed out). Nothing was downloaded or committed. The AD8436 figures (1 % at 65 kHz at 300 mV, 3.4 ms settling scaled from 10 uF) are the repo's own citations (DECISIONS C19, "Rev. B Table 1"); the A1 grade stack, LTC1966/1967/1968 bandwidth and AD8436 gain tempco are not re-read. The tempco (50 ppm/K) is ASSUMED.
- **ESP32-S3 ADC:** S/H aperture, sampling-capacitor kick from the TLV9062 + 100 ohm/1 nF source, gain drift and INL near 55 kHz are not specified anywhere I could read; 1 MHz S/H bandwidth, 2 LSB noise, 15 mV INL, 1 % drift are ASSUMED. The 83.3 kS/s limit is the README's `SOC_ADC_SAMPLE_FREQ_THRES_HIGH` for ESP-IDF v5.2.3. ADC1 itself is Wi-Fi safe (it is ADC2 that is not).
- **Waveforms are synthesised** (series RLC + square drive), without ZVS commutation ringing or measured pan data. B and C are the options most sensitive to that; A is the least.
- **B's dead zone is a first-order formula**, not SPICE. A real circuit with a faster amplifier would do better, but the cost argument above holds.
- **Estimator finding (2)** comes from reading the code, not from running `test/test_input_limits.c`.
- **Layout impact is not worked:** removing the chain edits the frozen netlist and the BOM/CPL regeneration (C34 flow), and the 4-layer plane under U14 would be left empty. I did not touch any of it.
- The LM4040A25 (U13) stays in every option: it is the D-11 bus-receiver reference, not part of the RMS chain.

## Files

- `rms_alternatives.py`: the simulation and cost script.
- `results.json`: every case, option, scan and control.
- `cost.csv`: parts, LCSC numbers, stock and tier prices with fetch times.
- `lcsc-snapshot-2026-10-12.json`: raw price/stock tiers the cost script reads.
