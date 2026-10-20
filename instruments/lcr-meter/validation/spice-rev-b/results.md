# Nominal simulations — generated numerical results

These results describe specified SPICE cases, not hardware measurements. AFE cases use incremental ideal-FDA loading with zero DC common-mode bias; full-chain model fails convergence.

## Passive source path

200Ω DDS Thevenin resistance; 330Ω/1nF twice; 1µF/100kΩ coupling; ideal readout gain 6.

| Actual frequency (Hz) | Gain V/V | Phase ° |
|---:|---:|---:|
| 100.00 | 5.948097 | 0.854 |
| 1000.00 | 5.948649 | -0.406 |
| 34673.68 | 5.740293 | -16.860 |
| 50118.72 | 5.535968 | -23.850 |
| 60255.96 | 5.377390 | -28.178 |
| 100000.00 | 4.674619 | -42.944 |
| 23988329.20 | 0.001508 | -176.977 |

0→0.3V DDS DC step at 1ms; output values below are elapsed since that step.

- 0.200s: 245.581204mV residual.
- 0.500s: 12.543564mV residual.
- 1.000s: 0.088199mV residual.

## AFE complex ratio sanity

Zest=(RF || CF)×(HIGH_BUF−LOW_BUF)/(LOW_BUF−TIA_OUT). Errors relative to the nominal DUT at the actual sweep frequency. These omit coupled FDA DC bias and finite-bandwidth input loading.

| Case | f Hz | Re Z Ω | Im Z Ω | Complex relative error % |
|---|---:|---:|---:|---:|
| cap100n | 34807.01 | -0.018469 | -45.725084 | 0.04039 |
| cap100n | 59566.21 | -0.018473 | -26.719015 | 0.06914 |
| cap100n | 100000.00 | -0.018475 | -15.915431 | 0.11609 |
| cap500n | 34807.01 | -0.003673 | -9.144993 | 0.04016 |
| cap500n | 59566.21 | -0.003674 | -5.343761 | 0.06875 |
| cap500n | 100000.00 | -0.003675 | -3.183014 | 0.11547 |
| cap9u | 1000.00 | -0.000177 | -17.683942 | 0.00106 |
| coil50u | 34807.01 | 0.504454 | 10.934808 | 0.04071 |
| coil50u | 59566.21 | 0.512987 | 18.713041 | 0.06939 |
| coil50u | 100000.00 | 0.536550 | 31.415503 | 0.11634 |
| mid5k | 34807.01 | 5000.001500 | -2.023096 | 0.04046 |
| mid5k | 59566.21 | 4999.971385 | -3.462159 | 0.06925 |
| mid5k | 100000.00 | 4999.888235 | -5.812179 | 0.11627 |
| high100k | 34807.01 | 99994.415062 | -39.794793 | 0.04018 |
| high100k | 59566.21 | 99983.371783 | -66.028072 | 0.06809 |
| high100k | 100000.00 | 99955.294864 | -101.993603 | 0.11136 |

## TIA return-ratio diagnostic

Series AC voltage at TIA inverting input, DC zero; T=−V(DUT_LO)/V(IN−). Other loops closed. Figures are nominal single-loop diagnostics with approximate incremental FDA loading and zero FDA-induced DC bias. They are **not full-board phase-margin guarantees**.

| Case | Crossing MHz | Nominal phase margin ° |
|---|---:|---:|
| cap100n | 30.7213 | 69.11 |
| cap500n | 30.7212 | 69.12 |
| cap9u | 30.7212 | 69.13 |
| coil50u | 56.2810 | 52.04 |
| mid5k | 17.5724 | 30.32 |
| high100k | 42.2178 | 91.88 |

## Standalone FDA

Official THS4551 model at 5V, VOCM 2.048V, 1k input and 1003.3Ω total feedback per side,4.02Ω output isolation,330pF toground and 3.3nF differential,16pF static ADC input eachside. Ideal zero-ohm input source; ADC sampling switches omitted.

- Low-frequency differential gain: 1.0032970 V/V.
- Maximum ACgain: 1.0288721V/V at 22387211.40Hz.
- First sweep point below −3dB: 6.945MHz.
- 10mV input step: output increment 10.032970mV; overshoot 1.5465%; last >0.1% error 295.81ns after end of 10 ns input edge (1ns requested timestep).
