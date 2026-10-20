# Feedback lead inductance: full-chain pulse stress

All 18 cases retain the final FDA network: 22 Ω inside the feedback loop, 1 kΩ || 100 pF feedback, 4.32 Ω ADC isolation, and the real FDA input bias currents. RF = 100 Ω and CF = 100 pF connect in parallel from DUT LOW to `rf_end`; the tested 10/20/50 nH connects from `rf_end` to the TIA output. Each DUT terminal has 100 pF to ground. Corners pair C104 ±5%, analog ±12 V rails ±5%, and FDA 5 V ±5%; other filter components remain nominal. This study selects no new component values.

The disturbance is 1 µA from HI to LOW, with 1 ns edges and 10 µs width. The simulation lasts 20 µs with a 1 ns maximum step. Tolerances remain `reltol=1e-5`, `abstol=1e-12`, `vntol=1e-7`, with Gear integration. Accepted initialization uses Newton iteration only and exact-network declaration-order conditioning. Every full operating point passes the internal MID and source-DC guards; every trace is complete and finite.

The peak columns cover both pulse edges. The open-load overshoot column describes the rising disturbance only. A brief inverse excursion at the falling edge can make the overall peak larger than the rising-step overshoot suggests; the saved waveform retains it.

| Case | TIA plateau change µV | TIA peak change µV | Open: rising-step overshoot % | Rise/fall 1%-of-peak settling ns | HIGH/LOW peak change µV | ADC pin min/max V |
|---|---:|---:|---:|---|---|---|
|open_lead10_corner0|-99.998716|107.423847|0.001|35.07/35.28|100.001535/20.877748|2.025124/2.025632|
|open_lead10_corner-1|-99.998716|107.304288|0.017|30.94/30.91|100.001537/21.309086|2.024999/2.025508|
|open_lead10_corner1|-99.998716|107.537610|0.000|37.67/38.51|100.001536/20.484041|2.025248/2.025755|
|open_lead20_corner0|-99.998716|106.521111|0.003|35.17/35.56|100.001540/21.985027|2.025124/2.025632|
|open_lead20_corner-1|-99.998716|106.434366|0.019|32.34/32.45|100.001540/22.343558|2.024999/2.025508|
|open_lead20_corner1|-99.998716|106.610600|0.000|37.96/37.73|100.001536/21.666752|2.025248/2.025755|
|open_lead50_corner0|-99.998716|104.958665|4.960|98.06/97.62|100.001553/26.560910|2.025124/2.025632|
|open_lead50_corner-1|-99.998716|103.738604|3.740|74.80/74.34|100.002554/26.779450|2.024999/2.025508|
|open_lead50_corner1|-99.998716|106.377651|6.379|129.38/135.75|100.001781/26.363913|2.025248/2.025755|
|coil_lead10_corner0|-0.497491|95.566033|n/a*|2293.74/2293.29|93.572328/20.848154|2.025034/2.025710|
|coil_lead10_corner-1|-0.497492|96.163029|n/a*|2290.38/2290.16|93.568036/21.271963|2.024913/2.025584|
|coil_lead10_corner1|-0.497490|95.075816|n/a*|2296.60/2296.32|93.575269/20.454394|2.025156/2.025836|
|coil_lead20_corner0|-0.497493|95.454235|n/a*|2294.29/2294.45|93.570110/21.941694|2.025034/2.025710|
|coil_lead20_corner-1|-0.497485|95.987284|n/a*|2291.23/2290.50|93.567876/22.298222|2.024913/2.025584|
|coil_lead20_corner1|-0.497488|95.133765|n/a*|2296.50/2295.92|93.574737/21.618141|2.025156/2.025836|
|coil_lead50_corner0|-0.497489|101.619456|n/a*|2262.78/2263.55|93.563578/26.459722|2.025034/2.025710|
|coil_lead50_corner-1|-0.497495|101.371048|n/a*|2263.39/2263.56|93.561171/26.681853|2.024913/2.025584|
|coil_lead50_corner1|-0.497483|101.892015|n/a*|2262.49/2262.72|93.566645/26.257586|2.025156/2.025836|

*The coil's large initial response relative to its small final DC response includes its physical L/R behavior. Calling that ratio feedback-loop overshoot would be misleading, so no coil overshoot percentage is assigned. Settling uses a ±1% band of the measured peak TIA change around the final plateau or initial baseline. It is not 1% of the coil's small DC step.

`current-windows.csv` reports actual RG, feedback-inductor and DUT currents, together with HIGH-buffer, LOW-buffer and TIA macro-model output currents. Negative output current indicates current sunk by the amplifier. ADC windows use actual pin voltages, not only differential signals. The export includes `rf_end`, so the physical placement of the inductance can be audited from the deck and trace.

A bounded 20 µs transient does not establish every loop's stability or phase margin. The 50 nH negative control can remain bounded while failing the separate 45° margin criterion. These are imposed lumped inductances, not extracted PCB measurements; routing qualification remains separate. No physical-board accuracy or noise claim follows.
