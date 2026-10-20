# Feedback lead inductance: full-chain pulse stress

All 18 cases retain the final FDA network: 22 Ω inside the feedback loop, 1 kΩ || 100 pF feedback, 4.32 Ω ADC isolation, and the real FDA input bias currents. RF = 100 Ω and CF = 100 pF connect in parallel from DUT LOW to `rf_end`; the tested 10/20/50 nH connects from `rf_end` to the TIA output. Each DUT terminal has 100 pF to ground. Corners pair C104 ±5%, analog ±12 V rails ±5%, and FDA 5 V ±5%; other filter components remain nominal. This study selects no new component values.

The disturbance is 1 µA from HI to LOW, with 1 ns edges and 10 µs width. The simulation lasts 20 µs with a 1 ns maximum step. Tolerances remain `reltol=1e-5`, `abstol=1e-12`, `vntol=1e-7`, with Gear integration. Accepted initialization uses Newton iteration only and exact-network declaration-order conditioning. Every full operating point passes the internal MID and source-DC guards; every trace is complete and finite.

The peak columns cover both pulse edges. The open-load overshoot column describes the rising disturbance only. A brief inverse excursion at the falling edge can make the overall peak larger than the rising-step overshoot suggests; the saved waveform retains it.

| Case | TIA plateau change µV | TIA peak change µV | Open: rising-step overshoot % | Rise/fall 1%-of-peak settling ns | HIGH/LOW peak change µV | ADC pin min/max V |
|---|---:|---:|---:|---|---|---|
