# Rev C strict full-chain final-capacitor regression

Feedback capacitance: 100Ω→100pF;5kΩ→10pF;100kΩ→5pF. All other circuit elements, vendor models and strict numerical tolerances are unchanged. Each case requires true internal-MID DC bias, DC KCL,561ACrows and complete120µs transient.

| Case | Feedback pF | DC KCL max pA | AC rows | Transient rows | ADC min/max V |
|---|---:|---:|---:|---:|---|
| revc_100r_cap100n | 100 | 1.0595 | 561 | 12114 | 1.189182/2.906945 |
| revc_100r_cap500n | 100 | 1.0595 | 561 | 12112 | 1.174320/2.921822 |
| revc_100r_cap9u | 100 | 1.0595 | 561 | 12121 | 1.211828/2.884277 |
| revc_100r_coil50u | 100 | 1.0185 | 561 | 12092 | 1.225585/2.868851 |
| revc_5k_resistor | 10 | 1.0388 | 561 | 12110 | 1.629642/2.465615 |
| revc_100k_resistor | 5 | 1.0389 | 561 | 12069 | 1.630278/2.465398 |
