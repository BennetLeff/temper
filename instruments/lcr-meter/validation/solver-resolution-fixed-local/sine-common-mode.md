# Final-network sine and common-mode verification

The sine cases apply DDS SIN(0.3 V DC,0.3 V peak,100 kHz), run 120 µs with maximum 5 ns steps and strict Newton/LTE tolerances. A three-coefficient least-squares DC/cos/sin fit uses the final 40 µs at the actual nonuniform solver timestamps. The outputs are static ADC RC nodes, not simulated digitized codes.

|Case|A peak(V)|B peak(V)|B/A|A / B fit RMS relative to peak|ADC range(V)|
|---|---:|---:|---:|---:|---:|
|sine100|0.699313022|0.699301565|0.999983617|4.621e-7 / 4.641e-7|1.658686–2.392005|
|sine5k|0.699179615|0.667053066|0.954051079|1.191e-8 / 1.005e-8|1.666683–2.391950|
|sine100k|0.697881325|0.109687565|0.157172232|3.604e-8 / 1.250e-4|1.667288–2.391341|

The matched5k common-mode case applies a 10 mV VOCM step with 1 ns edges at 1 µs, 10 µs width, 20 µs window, 1 ns maximum step. ADC common-mode metrics include the 22 Ω internal-feedback isolation drop.

|Channel|CM final change(mV)|CM rising overshoot|CM 1% settling(ns)|Differential peak glitch(µV)|
|---|---:|---:|---:|---:|
|A|9.876415872|45.719465%|1495.151|0.395757|
|B|9.876415863|45.719573%|1495.151|0.328663|

All CM ADC nodes stayed 2.020668–2.039956V. External DC KCL residual≤1.039e-12A.
