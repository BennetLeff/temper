# Rev E acquisition survey: codec (Option C) vs keep-SAR with a coherent DAC (Option S)

Survey date 2026-10-20. Nothing here has been built or simulated. This is a parts survey only.

**Citation convention.** `[PART pN]` means `sources/rev-e/PART.txt`, PDF page N. Each file holds `pdftotext -layout` text of the listed pages, with a header giving the source URL and the PDF's SHA-256. `[JLC]` means `sources/rev-e/JLC-stock-2026-10-20.txt`, a snapshot of the JLCPCB parts API. Every part in this survey is an **Extended** part with `preferredComponentFlag = false`. None is Basic or Preferred. **UNVERIFIED** marks a claim not found in a primary source. **Derived** marks arithmetic on cited numbers. Prices are JLC 1–9 pcs USD.

**Clock arithmetic used throughout (derived).** The RP2040 system clock is 120 MHz.
- 375 kHz = 120 MHz / 320, with BCLK = 64·fs = 24 MHz = 120 MHz / 5.
- 187.5 kHz = 120 MHz / 640, with BCLK = 64·fs = 12 MHz = 120 MHz / 10, and SCK/MCLK = 128·fs = 24 MHz.
- 750 kHz = 120 MHz / 160 would need BCLK = 32·fs = 24 MHz. That leaves only 16-bit slots for two channels.

The RP2040 clock-output dividers have duty-cycle correction (DC50) for odd divisors such as ÷5 (`sources/new/RP2040-datasheet.txt` §2.15.3.4). Running PIO full-duplex I2S/TDM at BCLK = 24 MHz takes 5 system cycles per bit; this is **UNVERIFIED**. At 12 MHz it takes 10 cycles per bit.

**What matters for this instrument.** The host forms Z = feedback · V_phasor / I_phasor (`host/src/lib.rs:543`). Both channels are fitted from one capture, so DAC amplitude, DAC latency and DAC phase drop out. Only the following survive calibration:
- channel-to-channel skew and gain that drift between calibration and measurement;
- nonlinearity, including any data-dependent gain such as DRE or AGC;
- noise;
- components that land exactly on the measured bin.

Decimation-filter ripple, phase non-linearity and group delay are linear and time-invariant, so the bilinear calibration absorbs them. **Passband edge therefore matters only for signal level and alias rejection, not flatness.**

---

## 1. Option C: one ADC (≥2 ch) plus DAC, or one codec

| Part (LCSC, stock, $) | Max fs; passband at the useful rate | Filters; HPF | Inputs, full scale, Z_in | Dynamic performance (datasheet conditions: 1 kHz, 20 kHz BW) | Matching / crosstalk | Clocking, non-standard rates | Control; supply; package |
|---|---|---|---|---|---|---|---|
| **TI TAC5212** codec, 2 ADC + 2 diff. DAC (C44853694, **stock 1**, $10.55) [JLC] | 768 kHz for ADC and DAC [p1, p11]. **Analog input bandwidth is 90 kHz for fs > 192 kHz** [p11]; DAC output also 90 kHz [p14]. Wideband needs `ADC_CHx_BW_MODE` = 1, the 40 kΩ input setting, and not high-swing mode [p48, p134]; the default analog bandwidth is "24 kHz mode" [p134]. ADC linear-phase: 0.227·fs at 384k, stop 0.391·fs, 80 dB [p59 T7-32]; 0.121·fs ±0.05 dB at 768k [p60 T7-33]; only 0.223·fs at 192k [p59 T7-31]. ADC low-latency at 192k: 0.456·fs, stop 0.571·fs, 90.5 dB [p63 T7-38]. DAC linear-phase at 384k: 0.258·fs, stop 77.7 dB [p78 T7-58]; DAC low-latency at 192k: 0.452·fs, 86.9 dB [p83 T7-64]. *Derived:* at 187.5 kHz with low-latency filters, ADC passband 85.5 kHz and DAC 84.8 kHz; at 375 kHz with linear-phase filters, ADC 85.1 kHz and DAC 96.8 kHz. | Linear-phase, low-latency, ultra-low-latency, low-power [p55 T7-24]. HPF: 1st-order IIR, default 0.00002·fs. Setting `HPF_SEL` = 00 with default coefficients gives an all-pass, i.e. HPF off [p51–52]. | Differential 2 Vrms full scale (4 Vrms in DC-coupled high-swing mode); single-ended 1 Vrms [p8]. AC- or DC-coupled [p1]. Z_in 5.5 / 11 / 44 kΩ [p11]. Pin range 0–5.6 V [p7]. | ADC DR 119 dB (AC-coupled); 112 dB DC-coupled; THD+N −98 dB [p10]. **Wideband mode: SNR 89 dB integrated to 85 kHz, DC-coupled** [p9, note 4 p16]. DAC differential 2 Vrms full scale, DR 120 dB, THD+N −104 dB [p12–14]. All THD-vs-frequency plots stop at 20 kHz [p23–26]. **THD at 27–100 kHz: UNVERIFIED.** | Interchannel isolation −134 dB; gain mismatch ±0.1 dB; phase mismatch ±0.01° at 1 kHz; CMRR 80 dB (DC-coupled high-CMRR mode) [p11]. No drift spec found (**UNVERIFIED**). | Target mode with PLL locked to BCLK/FSYNC [p38–39]. Auto-detect buckets: 349.27–387.84 kHz and 174.64–193.92 kHz at default 1 % tolerance [SLAAEG9 p2 T1-1], or ±5 % [T1-2]. **375 kHz and 187.5 kHz both fall inside a bucket.** Semi-automatic and manual modes cover other non-audio rates [SLAAEG9 p3; SLAAEG6 p9; SLAAEP0 p1]. Controller mode from CCLK ≤ 36.864 MHz [p8]. ADC and DAC share the ASI clocks, so they are coherent by construction. | I2C or SPI [p1]. AVDD 3.3 or 1.8 V single supply, IOVDD 1.2/1.8/3.3 V [p7]. VQFN-24 4×4 mm, 0.5 mm pitch [p1]. |
| **TI TAC5112** (C44853692, stock 181, $5.93) [JLC] | Same family: 768 kHz, 90 kHz input bandwidth above 192k [TAC5112 p10]. | Same as TAC5212 [TAC5112 p1]. | Same full scale (2 Vrms differential) [TAC5112 p1]. | ADC DR 105 dB, THD+N −97 dB [TAC5112 p1]. Wideband SNR 91 dB to 85 kHz, AC-coupled [TAC5112 p9]. DAC DR 114 dB [p1]. | Gain/phase mismatch ±0.1 dB / ±0.01°; ADC isolation −134 dB; CMRR **60 dB** [TAC5112 p11]; DAC isolation −120 dB [p14]. | Same as TAC5212 (covered by SLAAEG6/9). | **Pin-, package- and register-compatible drop-in for TAC5212** [TAC5212 p4]. |
| TI TAA5212 ADC (C44525604, 188, $10.01) + TAD5212 DAC (C45068920, **1**, $6.37) or TAD5112 (C45335600, 16, $5.06) [JLC] | TAA5212: 768 kHz, 90 kHz input bandwidth above 192k, wideband SNR 89 dB to 85 kHz [TAA5212 p7, p9]. TAD5212: 90 kHz wideband DAC [TAD5212 p37]. | Same family as TAC5212. | 2 Vrms differential [TAA5212 p1]. | ADC DR 119 dB [TAA5212 p1]; DAC 120 dB, THD+N −104 dB [TAD5212 p1]. | Isolation −134 dB; ±0.1 dB / ±0.01° [TAA5212 p9; TAD5212 p9]. | Same family. | Two VQFN-24 parts. No advantage over one TAC5x12. |
| **TI TLV320ADC5140** 4-ch ADC (C2876368, 256, $4.00) [JLC]. Siblings: ADC3140 (C882863 / C1852021, 46 / 279) and ADC6140 (C1852023, 87, $12.49) [JLC] | 768 kHz [p1]. **Input bandwidth up to 80 kHz** at fs ≥ 176.4k [p30]. Linear-phase 384k: 0.212·fs, stop 0.58·fs, 70 dB [p40 T29]; 768k: 0.113·fs [p40 T30]. Low-latency 192k: 0.463·fs, stop 0.6·fs, 85.6 dB [p45 T36]. *Derived:* 79.5 kHz at 375k (linear-phase); 86.8 kHz at 187.5k (low-latency), capped by the 80 kHz analog bandwidth. | Linear-phase, low-latency, ultra-low-latency. Programmable HPF (default 12 Hz) [p8]. **DRE (data-dependent gain) and AGC must be off** [p1, p50]. | Differential 2 Vrms AC-coupled full scale [p7]. DC coupling per channel, not with the 2.5 kΩ setting [p27–28]. Z_in 2.5 / 10 / 20 kΩ [p7, p28]. | DR 108 dB with DRE off; THD+N −98 dB [p1, p8]. ADC3140: DR 106 dB; ADC6140: 113 dB with DRE off [p3]. | Isolation −124 dB [p8]. Gain mismatch 0.1 dB, gain drift −4.4 ppm/°C, phase mismatch 0.02°, **phase drift 0.0005 °/°C** (1 kHz), CMRR 60 dB [p9]. | Auto-detect tables (384k at BCLK/FSYNC = 64 → 24.576 MHz) [p26]. Auto-detect and clock-error check can be turned off for custom clocks [p27]. Tolerance of the auto-detect buckets: **UNVERIFIED**. | I2C/SPI; 3.3 or 1.8 V; WQFN-24 4×4 [p1]. ADC only, so it needs a separate DAC (§2). |
| AKM AK5572 2-ch ADC (C5451857, 30, $12.01) [JLC] | 768 kHz. At 384k, −0.1 dB at 81.75 kHz, stop 277.4 kHz, 85 dB [AK5572 p16]. At 192k sharp roll-off, passband 83.7 kHz, stop 122.9 kHz [p14]. Bands scale with fs [p16 note 13]. | Four decimation filters; digital HPF disabled with pin HPFE = L [p1, p6]. | Full differential; **full scale only 2.8 Vpp differential; R_in 3.6 kΩ** [p9]. | S/(N+D) 112 dB; DR 121 dB [p9]. | Gain mismatch 0–0.5 dB; isolation 120 dB [p9]. | **Needs MCLK (no PLL).** Fixed ratio modes: 64·fs = 24 MHz → "fs = 384 kHz" mode; 128·fs = 24 MHz → quad speed, **108 kHz ≤ fs ≤ 216 kHz**, so 187.5 kHz is inside a documented range [p33 T5]. | 3-wire / I2C or pin control; AVDD **5 V** [p1]; QFN-48 7×7. Sibling AK5552 (C2651617, stock 2): DR 115 dB, R_in 10.4 kΩ [AK5552 p9]. |
| TI PCM1865 4-ch ADC (C181312, 788, $6.80) [JLC] | **192 kHz max** [p1]. Classic FIR: passband 0.454·fs, stop 0.583·fs, **only −65 dB** [p16]. *Derived:* 85.1 kHz passband at 187.5k. The datasheet describes the main ADC SNR "with 40-kHz bandwidth" [p47]. **Analog front-end bandwidth at 60 kHz: UNVERIFIED.** | FIR or low-latency IIR; HPF on by default (DSP_CTRL) [p53]. A disable option exists in DSP_CTRL but is not in the excerpt (**UNVERIFIED**). Automatic clipping suppression and energysense must be off [p1]. | Single-ended 2.1 Vrms; differential 4.2 Vrms [p1]. Z_in 10 kΩ [p13]. | SNR 110 dB; differential THD+N −93 dB [p1, p13]. | Not found (**UNVERIFIED**). | At 176.4/192 kHz, SCK must be 128 or 256·fs [p47 T16]. Tolerance for 187.5 kHz is **UNVERIFIED**; the auto clock detector can be disabled for non-audio clocks [p47]. | I2C/SPI; 3.3 V; TSSOP-30 [p1]. Needs a separate DAC. |
| TI PCM1820/1821/1822 (C5215004 33; C5214995 509) [JLC] | **192 kHz max**; linear-phase passband at 192k is 0.3·fs = 57.6 kHz [PCM1820 p1, p22 T8-14]. **Rejected:** below the 60 kHz minimum. | Pin control only; DC-removal HPF integrated [p1]. | 2 Vrms differential; Z_in 2.5 kΩ (PCM1820) [p6]. | DR 113 dB with DRE off [p6]. | Phase drift 0.0005 °/°C; CMRR 45 dB [p7]. | — | Hardware pins, so less agent-drivable. |

Other parts were looked up but not taken further:
- **Cirrus CS5381 / CS5361 / CS4272**, **AK4458**, **ADAU1979**, and **PCM4220 / PCM4202 / PCM1804**: available at JLC [JLC]. Their maximum rates and passbands were not checked against primary sources (**UNVERIFIED**). AKM and Cirrus parts outside the AK5572/AK5552 above also have low stock.
- **ESS ES9822 and ES9038Q2M**: out of stock [JLC].
- **PCM1808 / PCM1802**: 96 kHz-class audio ADCs, below what this needs (**UNVERIFIED**; datasheets downloaded but not cited).

### Derived noise check for Option C
- The TAC5212 in wideband mode has 89 dB SNR in 85 kHz, relative to full scale [TAC5212 p9].
- The ADS9224R has 93 dB SNR [`sources/ti/ADS9224R.txt` line 519]. Assuming that noise spreads over the 500 kHz Nyquist band at 1 MSPS, it is about 100.7 dB in 85 kHz.

So the codec ADC is about **12 dB (≈4×) noisier relative to full scale** (derived, assumption stated). The ADC is 36–89 % of the fitted-Z noise budget (`validation/virtual-instrument/README.md` §2.4), and the worst noise-only error today is 2.9 % of a tolerance. The codec would therefore raise it to roughly ≤11 % of tolerance. This is an estimate to confirm in the virtual instrument.

---

## 2. Option S: keep ADS9224R + THS4551; replace AD9833 + OPA810 with a coherently clocked DAC

| Part (LCSC, stock, $) | fs; filter at the useful rate | Output | Dynamic | Clocking at 375 kHz / 187.5 kHz | Control; package |
|---|---|---|---|---|---|
| **TI PCM5102A** (C107671, 2613, $1.45) [JLC] | 8–384 kHz [p7]. Filters: "x8/x4/x2/x1 (bypass)" from 8 to 384 kHz [p17]. Normal x2 filter: passband 0.45·fs, stop 0.55·fs, −60 dB [p20 T6]. Low-latency: −52 dB [p21–23]. **At 384 kHz the sibling PCM512x runs OSR = 1 (bypass)** [PCM5122 p21 T8]. The PCM5102A datasheet does not map rate to OSR, but it lists the same x1 bypass, so **at 375 kHz expect no digital image rejection** (inference, UNVERIFIED). *Derived:* at 187.5 kHz (quad rate, x2), passband 84.4 kHz and stop band from 103 kHz at −60 dB. | 2.1 Vrms ground-centred single-ended; load ≥ 1 kΩ [p4, p9]. Gain error ±6 %, which calibration removes [p9]. | THD+N −93 dB at 48/96/192 kHz; DR 112 dB; channel separation 109 dB [p8]. All with a 20 kHz measurement bandwidth. **THD at 27–100 kHz output: UNVERIFIED.** "Up to 20 dB lower out-of-band noise … 100 kHz to 3 MHz", no absolute figure [p14]. | Detects rate bands "(176.4–192 kHz) and 384 kHz with **±4 % tolerance**" [p24]. 375 kHz is −2.3 % and 187.5 kHz is −2.3 % (derived), so both are inside the band. At 384 kHz, SCK 64 or 128·fs and BCK 32/48/64·fs [p15 T2]; SCK = 24 MHz is 64·fs at 375k and 128·fs at 187.5k. BCK-PLL mode (no SCK) expects BCK 64·fs [p25 T11]. The negative charge pump clock is set by the sampling-rate detector [p24], so it follows SCK; its **frequency is not stated (UNVERIFIED)**. LRCK/SCK drift of more than ±5 SCK forces a resync [p15]. | Pin control (FLT, FMT, XSMT) [p5]; 3.3 V AVDD/CPVDD; TSSOP-20. |
| TI PCM5122 (C962071 47, $3.25; C1540085 177, $4.11) [JLC] | Same OSR map: 384k → bypass, 192k → x2 [PCM5122 p21 T8]. Adds a high-attenuation filter (−100 dB, x8/x4/x2 only) and an asymmetric FIR [p9, p21 T7]. | 2.1 Vrms SE; load ≥ 5 kΩ; channel gain mismatch ±0.5 % [p9]. | THD+N −93 dB [p8]. | Non-audio SCK rates "between 1 MHz and 50 MHz" are supported in software mode through PLL and dividers [PCM5102A p24]. | I2C/SPI; TSSOP-28. |
| TI PCM5242 (C471871, 841, $2.93) [JLC] | Same family; 384k = octal rate, bypass [PCM5242 p44]. | **4.2 Vrms differential** (2.1 Vrms per pin) [p1, p23]. | THD+N −94 dB [p7]. | Software PLL (family) [p1]. | I2C/SPI; VQFN-32 5×5. |
| TAD5212 / TAD5112 | See §1. DAC linear-phase at 384k: 0.258·fs, 77.7 dB stop band (the TAC5212 table applies to the family) [TAC5212 p78]. Wideband 90 kHz [TAD5212 p37]. | 2 Vrms differential. | DR 120 / 114 dB. | Same as TAC5212. | Low JLC stock (1 / 16) [JLC]. |

---

## 3. Recommendations

**Option C: TAC5212, with TAC5112 as the stocked drop-in.** One VQFN-24 replaces the ADS9224R, both THS4551s, the AD9833 and the OPA810 gain stage. ADC and DAC share one FSYNC, so the chain is coherent by construction.

Decisive numbers:
- 90 kHz analog bandwidth in wideband mode [p11, p48].
- At fs = 187.5 kHz (12 MHz BCLK) with low-latency filters, 85.5 kHz ADC and 84.8 kHz DAC passband. The ADC stop band starts at 0.571·fs = 107 kHz, 90.5 dB down [p63, p83].
- 187.5 kHz sits in the default auto-detect bucket [SLAAEG9 p2].
- Isolation −134 dB [p11].

The decimation stop band also removes the AD9833-style harmonic-alias problem. A component can land on f ≤ 0.456·fs only from at or above 0.544·fs, which is inside the ≥ 90 dB stop band (derived). The equivalent mechanism set the 21 mΩ coil-R spur bound in Rev C/D (virtual-instrument README §2.3).

Costs:
- About 4× more ADC noise relative to full scale (derived; still far inside target).
- A 100 kHz ceiling. 100 kHz itself falls in the transition band, with attenuation **UNVERIFIED**.
- The TAC5212 has only 1 unit at JLC [JLC]. The TAC5112 (181 units) is register- and pin-compatible [TAC5212 p4]. It costs 14 dB of audio-band dynamic range but has a similar wideband SNR (91 vs 89 dB, measured under different coupling conditions) [TAC5112 p9; TAC5212 p9].

Interfacing implications (design notes, not sourced):
- Channel A can take the HIGH and LOW follower outputs differentially through AC coupling (the differential stage disappears).
- Channel B, the single-ended TIA output of up to 3.6 Vpp, exceeds the 1 Vrms (2.83 Vpp) single-ended full scale. It needs a resistive attenuator or an inverter.
- The DAC's 2 Vrms differential output needs a differential-to-single-ended stage in front of the OPA2810 source buffer.

Runner-up: **TLV320ADC5140 + PCM5102A/PCM5122**. Both are in stock. But the ADC's analog bandwidth is 80 kHz, there are two chips, and the DAC has a −60 dB image stop band.

**Option S: PCM5102A (C107671), run at fs = 187.5 kHz, not 375 kHz.**
- SCK = 24 MHz (128·fs), BCK = 12 MHz.
- 187.5 kHz is inside the ±4 % 192 kHz detection band [p24].
- Quad rate uses the x2 interpolation filter (passband 84.4 kHz, −60 dB stop band from 103 kHz) [p20 T6; PCM5122 p21 T8].
- At 375 kHz the family bypasses the interpolation filter entirely (OSR = 1) [PCM5122 p21 T8]. Images at fs − f (e.g. 325 kHz for 50 kHz) would reach the DUT with only analog filtering.
- Choose PCM5122 instead if register control or non-audio PLL configuration is wanted; it has lower stock.
- If harmonics are at the −93 dB the datasheet gives at 1 kHz, the README's −60/−80 dBc spur bounds scale to about 0.5 mΩ coil R at 50 kHz. That figure is derived and holds only if HD stays that low at 50 kHz, which is **UNVERIFIED**.

---

## 4. Risks to check, and which simulation can settle

Settle in simulation (existing `validation/virtual-instrument` chain plus filter models built from the cited tables):
1. **Option S image and alias folding.** Model the DAC output as ZOH at fs_DAC with the x2 −60 dB filter (or bypass at 375 kHz), then the reconstruction RC and the TIDA core, then the 1 MSPS SAR. Search for k·fs_DAC ± f ≡ ±f (mod 1 MHz). Example (derived): with fs_DAC = 187.5 kHz, 16·fs_DAC = 3 MHz, so the images at 3 MHz ± f fold exactly onto f. Compute the Z error per target frequency, as `spur_alias.py` already does for AD9833 spurs.
2. **Option C decimation alias rejection.** Feed DAC harmonics through the tabulated decimation stop band and confirm that the on-bin contribution is negligible at 27–60 kHz and 1–1.5 kHz.
3. **Option C noise.** Replace the ADS9224R + FDA noise with 89 dB / 85 kHz at a 2 Vrms differential full scale, then rerun the noise-only E and the what-if table, including channel-B attenuation.
4. **Channel-B and DAC scaling.** Signal levels against codec full scale on every range (100 Ω / 5 kΩ / 100 kΩ), short and open fixtures, clipping margins.
5. **AC-coupling corners.** 40 kΩ input with the coupling capacitor at 100 Hz, and the DAC HPF bypassed. Linear, so it calibrates out, but confirm it is still above the noise at the lowest frequency.

Need the bench (no vendor models; datasheets specify only 20 Hz–20 kHz):
6. ADC and DAC **THD and gain compression at 27–100 kHz**. Do a DAC→ADC loopback with a passive divider and sweep amplitude, to see whether gain depends on amplitude between standards and DUT. This is the one nonlinearity calibration cannot remove.
7. **Wideband mode actually passing 60–90 kHz.** Measure the attenuation at 85–100 kHz (TAC) and 60–80 kHz (ADC5140, PCM1865 front end).
8. **Clock acceptance:**
   - TAC at 187.5 or 375 kHz in auto mode, reading `CLK_DET_STS` [TAC5212 p39];
   - PCM5102A at 187.5 or 375 kHz with SCK = 24 MHz;
   - RP2040 PIO full-duplex I2S at 12 MHz (and 24 MHz) BCLK.
9. **Inter-channel phase and gain drift** over temperature and time between calibration and measurement. Only the ADC5140 and PCM182x publish a figure (0.0005 °/°C at 1 kHz); the TAC has none at 50 kHz.
10. **PCM5102A charge-pump spur** frequency and level (frequency not published). Check with an idle-channel FFT to 3 MHz. Its frequency, once measured, can be put back into sim item 1.
11. **Data-dependent processing actually off:** DRE and AGC (ADC5140, PCM1820); AGC, limiter, foldback and VAD (TAC5212 [p1]); clipping suppression and energysense (PCM1865). Read back the registers and run an amplitude sweep.
12. **Input protection.** ±12 V op-amp faults reaching codec pins rated 0–5.6 V [TAC5212 p7] through AC coupling.
13. **Supply.** JLC stock for the TAC5212 (1 unit) and TAD5212 (1 unit); design for TAC5212/TAC5112 interchangeability.
