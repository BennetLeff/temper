# Rev C bounded fast-disturbance transients

Official unmodified 2021 GWL THS4551 model; 22Ω inside feedback, 100pF feedback caps, 4.32Ω ADC isolation; real FDA bias/loading. 1µA DUT HI→LO current pulse,1ns edges,10µs width;20µs total,1ns maximum step. DDS at0.3V DC with source AC coupling retained. Open means1TΩ and short means10mΩ. These are bounded finite waveform checks, not proof of all loop margins or long-time settling.

| Case | HI/LO to ground pF | Peak TIA change mV | Peak HIGH buffer change mV | Peak LOW buffer change mV | Final TIA offset µV | ADC min/max V |
|---|---|---:|---:|---:|---:|---|
| c100k_coil_hi0_lo100 | 0/100 | 0.747866 | 6.275764 | 0.120909 | 137.642820 | 2.024992/2.025740 |
| c100k_coil_hi100_lo0 | 100/0 | 8.623371 | 0.471492 | 0.459007 | 0.030936 | 2.022173/2.028171 |
| c100k_coil_hi100_lo100 | 100/100 | 8.600731 | 0.551599 | 0.248481 | 0.022187 | 2.022144/2.028209 |
