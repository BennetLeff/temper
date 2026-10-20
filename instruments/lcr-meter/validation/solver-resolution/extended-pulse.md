# Rev C bounded fast-disturbance transients

Official unmodified 2021 GWL THS4551 model; Riso=4.02Ω; real FDA bias/loading. 1µA DUT HI→LO current pulse,1ns edges,10µs width;20µs total,1ns maximum step. DDS at0.3V DC with source AC coupling retained. Open means1TΩ and short means10mΩ. These are bounded finite waveform checks, not proof of all loop margins or long-time settling.

| Case | HI/LO to ground pF | Peak TIA change mV | Peak HIGH buffer change mV | Peak LOW buffer change mV | Final TIA offset µV | ADC min/max V |
|---|---|---:|---:|---:|---:|---|
| c100_cap100n | 0/0 | 0.063189 | 0.063214 | 0.000023 | -25.740900 | 2.047378/2.047885 |
| c100_cap500n | 0/0 | 0.018121 | 0.018126 | 0.000005 | -15.147119 | 2.047378/2.047885 |
| c100_cap9u | 0/0 | 0.001105 | 0.001105 | 0.000001 | -1.094028 | 2.047378/2.047885 |
| c100_coil50u | 0/0 | 0.092097 | 0.113923 | 0.021203 | 0.000046 | 2.047280/2.047976 |
| c100_open | 0/0 | 0.120902 | 0.114927 | 0.021350 | -0.000084 | 2.047376/2.047891 |
| c100_short10m | 0/0 | 0.000012 | 0.000010 | 0.000003 | 0.000060 | 2.047327/2.047937 |
| c100k_coil_hi0_lo0 | 0/0 | 1.883106 | 4.871148 | 0.407718 | -0.017145 | 2.045969/2.049345 |
| c100k_coil_hi0_lo100 | 0/100 | 0.748123 | 6.265048 | 0.118909 | 150.996456 | 2.045455/2.049914 |
| c100k_coil_hi100_lo0 | 100/0 | 8.624243 | 0.471430 | 0.455477 | -0.015750 | 2.042959/2.051695 |
| c100k_coil_hi100_lo100 | 100/100 | 8.600221 | 0.551635 | 0.248430 | -0.012715 | 2.042938/2.051715 |
