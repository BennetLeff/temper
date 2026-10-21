# Rev E option C: codec noise check

`noise_codec.py` (Python 3 + numpy, reuses `../virtual-instrument`) compares the 1σ fitted-impedance noise of the Rev D SAR chain with a TAC5112 or TAC5212 codec chain at equal capture time, for every Temper target. The codec chain is the [Rev E front end](../../docs/rev-e-front-end.md). It uses the `riso22_lo100` transfer: Rev D plus the fixed 100 pF from DUT_LO to ground that the relay stability campaign added. Output: `results/noise_codec.json`.

| Target | Tolerance | 2σ/tolerance, Rev D SAR | TAC5112 | TAC5212 |
|---|---:|---:|---:|---:|
| Coil R, no pan | 20 mΩ | 0.77 % | 1.31 % | 1.65 % |
| 100 nF tan δ | 1×10⁻³ | 0.44 % | 1.01 % | 1.27 % |
| 0.5 µF bank tan δ | 1×10⁻³ | 2.06 % | 4.11 % | 5.17 % |
| Tank Q, no pan | 10 % | 0.51 % | 0.72 % | 0.91 % |
| Every other target | | ≤ 0.25 % | ≤ 0.41 % | ≤ 0.52 % |

The codec ADC is essentially all of the noise; the analog core's own noise is negligible. The 100 pF at DUT_LO doubles the TIA op-amp's noise gain at high frequency, but it changes no row at the precision shown. Noise therefore does not decide between the options: the worst case is 5.2 % of a tolerance.

Assumptions (in the script header):
- Source: limited to 1.7 V peak at SOURCE_BUF. DAC noise above 20 kHz is twice the datasheet's 20 kHz figure (no figure is published above 20 kHz).
- Codec inputs: both channels pass through a 1k/1k divider (K = 0.5), so the common-mode swing of the unbalanced drive stays within the 1 Vpp of CM_TOL = 01. That setting is assumed to cost 3 dB ("a few dB" in the datasheet).
- Firmware gain: 12 dB channel gain whenever the peak stays under 0.8 of full scale; it costs 2 dB of SNR.
- Sampling: modulator rate 6.144 MHz (not published), with a 500 kHz anti-alias pole.

Bench-only questions stay open: wideband-mode response to 85 kHz, gain compression at Temper frequencies, clock acceptance at 187.5 kHz, and whether CM_TOL = 01 is allowed in wideband mode.
