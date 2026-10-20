# Exact coupled circuit: solver and transient checks

Generated data checks; official vendor models unchanged. DC/AC/transient all required, every numeric field finite.

| Case | I HIGH buffer mA | I LOW buffer mA | I TIA mA | max DC output KCL residual pA | AC rows | transient rows | ADC pin min/max V |
|---|---:|---:|---:|---:|---:|---:|---|
| 100r_cap100n | -1.0221769 | -2.0451423 | -1.0226135 | 1.05946 | 561 | 12116 | 1.189176 / 2.906951 |
| 100r_cap500n | -1.0221769 | -2.0451423 | -1.0226135 | 1.05946 | 561 | 12117 | 1.174315 / 2.921828 |
| 100r_cap9u | -1.0221769 | -2.0451423 | -1.0226135 | 1.05946 | 561 | 12122 | 1.211822 / 2.884282 |
| 100r_coil50u | -1.0225157 | -2.0449158 | -1.0274729 | 1.01846 | 561 | 12086 | 1.225579 / 2.868858 |
| 5k_resistor | -1.0223472 | -2.0450285 | -1.0228292 | 1.03883 | 561 | 12153 | 1.629589 / 2.465617 |
| 100k_resistor | -1.0223473 | -2.0450286 | -1.0227857 | 1.03894 | 561 | 12069 | 1.630278 / 2.465398 |

DC output current is taken from the existing manufacturer model output-current sensor, with negative sign for current delivered externally. Residuals include omitted follower input bias and ESD off leakage (~pA), not an unconstrained op-amp output. Negative currents are real FDA common-mode sink loading.

## Five-kilohm fast-disturbance transient

1µA current pulse from DUT_HI to DUT_LO;1ns edge; both RG/RF=5kΩ and DUT=5kΩ. This is a diagnostic disturbance, not the normal DDS waveform. FDA CM/load retained. Nominal27°C.

| Case | TIA increment mV | TIA overshoot % | last outside1% ns afteredge |
|---|---:|---:|---:|
| pulse5k_cf0 | -2.499993 | 93.698 | 322.09 |
| pulse5k_cf2p2 | -2.499994 | 8.639 | 54.73 |
| pulse5k_cf4p7 | -2.499994 | 0.000 | 95.96 |
| pulse5k_cf10 | -2.499994 | 0.000 | 226.12 |
| pulse5k_cf0_fixture100 | -2.499968 | 0.000 | 1162.13 |
| pulse5k_cf2p2_fixture100 | -2.499966 | 0.000 | 1173.50 |
| pulse5k_cf4p7_fixture100 | -2.499965 | 0.000 | 1186.62 |
| pulse5k_cf10_fixture100 | -2.499961 | 0.000 | 1217.59 |

Structural-shunt sensitivity is recorded separately; do not infer robustness from one converged circuit.
