# High-range coil fixture: long-tail check

100kΩ/5pF feedback;0.5Ω+50µH DUT;100pF from DUT_LOW to ground, no added HIGH-to-ground capacitance. This deliberately poor range/load pairing is outside the intended coil measurement setup. A single1µA10µs current pulse starts at1µs. True-DC guard passed; complete100µs finite transient at2ns maximum step. Envelope values are peak absolute deviations from the pre-pulse DC state, including numerical offset.

| Window after simulation start | TIA envelope µV | HIGH buffer envelope µV | LOW buffer envelope µV |
|---|---:|---:|---:|
| 12–20µs | 449.323326 | 5770.615542 | 106.578360 |
| 20–30µs | 226.699825 | 2960.416048 | 54.696118 |
| 30–40µs | 98.319037 | 1278.974848 | 23.629160 |
| 40–60µs | 42.455933 | 553.254291 | 10.222253 |
| 60–80µs | 7.989603 | 103.282559 | 1.901889 |
| 80–100µs | 1.520419 | 18.901549 | 0.349335 |
