# Rev E option C: codec noise check

`noise_codec.py` (Python 3 + numpy, reuses `../virtual-instrument`) compares the 1σ fitted-impedance noise of the Rev D SAR chain with a TAC5112 or TAC5212 codec chain at equal capture time, for every Temper target. The codec chain is the [Rev E front end](../../docs/rev-e-front-end.md). It uses the `riso22_lo100` transfer: Rev D plus the fixed 100 pF from DUT_LO to ground that the relay stability campaign added. Output: `results/noise_codec.json`.

| Target | Tolerance | 2σ/tolerance, Rev D SAR | TAC5112 | TAC5212 |
|---|---:|---:|---:|---:|
| Coil R, no pan | 20 mΩ | 0.77 % | 3.57 % | 4.49 % |
| 100 nF tan δ | 1×10⁻³ | 0.44 % | 2.70 % | 3.40 % |
| 0.5 µF bank tan δ | 1×10⁻³ | 2.06 % | **12.9 %** | 16.3 % |
| Tank Q, no pan | 10 % | 0.51 % | 2.29 % | 2.88 % |
| Every other target | | ≤ 0.25 % | ≤ 1.29 % | ≤ 1.63 % |

**Correction (2026-10-20).** An earlier version credited a 12 dB firmware channel gain, which gave a 4.1 % worst case. That figure came from the "12dB channel gain" rows of the TAC5112 SNR table. While writing the Rev E firmware I found that the register map (SLASF24A §8.1.1) has no analog gain field, only digital volume, and digital volume does not lower input-referred noise. The table above has no gain.

**Where the noise comes from.**
- The codec ADC is essentially all of it. The 100 pF at DUT_LO and the analog core add nothing at the precision shown.
- The worst case is the 0.5 µF bank at 35–60 kHz. There, channel A (the voltage across about 5 Ω on the 100 Ω range) uses only 1.2–2.1 % of full scale.

**Capture time.**
- The comparison uses Rev D's capture times, 16–33 ms at those points.
- Rev E averages on the device over any number of waveform periods ([firmware](../../firmware-rev-e/README.md)), so capture length is no longer limited by RAM.
- Noise falls as 1/√T. A 10× longer capture (0.16–0.33 s) brings the bank to about 4 %, and every other target well below that.
- Noise stays well inside every tolerance either way.

**Assumptions** (in the script header):
- **Source:** limited to 1.7 V peak at SOURCE_BUF. DAC noise above 20 kHz is twice the datasheet's 20 kHz figure (no figure is published above 20 kHz).
- **Codec inputs:** both channels pass through a 1k/1k divider (K = 0.5). This keeps the common-mode swing of the unbalanced drive within the 1 Vpp of CM_TOL = 01, which is assumed to cost 3 dB ("a few dB" in the datasheet).
- **Sampling:** modulator rate 6.144 MHz (not published), with a 500 kHz anti-alias pole.

**Bench-only questions** stay open:
- wideband-mode response to 85 kHz;
- gain compression at Temper frequencies;
- clock acceptance at 187.5 kHz;
- whether CM_TOL = 01 is allowed in wideband mode.
