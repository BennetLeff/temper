# Rev C bounded fast-disturbance transients

Official unmodified 2021 GWL THS4551 model; 22Ω inside feedback, 100pF feedback caps, 4.32Ω ADC isolation; real FDA bias/loading. 1µA DUT HI→LO current pulse,1ns edges,10µs width;20µs total,1ns maximum step. DDS at0.3V DC with source AC coupling retained. Open means1TΩ and short means10mΩ. These are bounded finite waveform checks, not proof of all loop margins or long-time settling.

| Case | HI/LO to ground pF | Peak TIA change mV | Peak HIGH buffer change mV | Peak LOW buffer change mV | Final TIA offset µV | ADC min/max V |
|---|---|---:|---:|---:|---:|---|
| c100_cap100n | 0/0 | 0.063189 | 0.063213 | 0.000023 | -25.740915 | 2.025115/2.025652 |
| c100_cap500n | 0/0 | 0.018121 | 0.018126 | 0.000019 | -15.147137 | 2.025115/2.025652 |
| c100_cap9u | 0/0 | 0.001105 | 0.001105 | 0.000019 | -1.094048 | 2.025115/2.025652 |
| c100_coil50u | 0/0 | 0.092091 | 0.114260 | 0.021131 | 0.000015 | 2.025035/2.025710 |
| c100_open | 0/0 | 0.120769 | 0.115034 | 0.021255 | 0.000008 | 2.025124/2.025632 |
| c100_short10m | 0/0 | 0.000012 | 0.000010 | 0.000002 | 0.000009 | 2.025068/2.025676 |
