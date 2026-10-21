# Rev E option C: codec noise check

`noise_codec.py` (Python 3 + numpy, reuses `../virtual-instrument` unchanged) compares the 1σ fitted-impedance noise of the Rev D SAR chain with a TAC5112 or TAC5212 codec chain at equal capture time, for every Temper target. Output: `results/noise_codec.json`.

| Target | Tolerance | 2σ/tolerance, Rev D SAR | TAC5112 | TAC5212 |
|---|---:|---:|---:|---:|
| Coil R, no pan | 20 mΩ | 0.77 % | 1.22 % | 1.53 % |
| 100 nF tan δ | 1×10⁻³ | 0.44 % | 0.92 % | 1.16 % |
| 0.5 µF bank tan δ | 1×10⁻³ | 2.06 % | 4.33 % | 5.45 % |
| Tank Q, no pan | 10 % | 0.51 % | 0.77 % | 0.96 % |
| Every other target | | ≤ 0.25 % | ≤ 0.43 % | ≤ 0.54 % |

The codec ADC is essentially all of the noise. Channel A (voltage across a low-impedance DUT) is only 0.07–0.26 V peak against a 2.83 V peak full scale. The analog core's own noise is negligible. Noise therefore does not decide between the options: the worst case is 5.5 % of a tolerance. If it ever matters, the codec's channel gain can lift channel A in firmware.

Assumptions (in the script header): DAC noise above 20 kHz is twice the datasheet's 20 kHz figure (unpublished); channel B is attenuated to 0.7 so the 3.6 Vpp TIA output fits; the modulator rate is 6.144 MHz (unpublished) with a 500 kHz anti-alias pole; the source amplitude equals Rev D's. Bench-only questions stay open: wideband-mode response to 85 kHz, gain compression at Temper frequencies, and clock acceptance at 187.5 kHz.
