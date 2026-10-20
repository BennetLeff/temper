# Final-network fast-disturbance checks

Every case retains the final 22 Ω / 100 pF / 4.32 Ω FDA network and the actual bias currents. A 1 µA DUT HI→LO disturbance has 1 ns edges and 10 µs width; simulation ends at 20 µs with a 1 ns maximum step. Supply rails are ±12 V and 5 V. The 100 kΩ range coil cases deliberately mismatch the range to expose coupled-loop behavior; they are not a recommended measurement configuration.

|Case|HI/LO ground capacitance pF|Rows|Peak TIA change mV|Peak HIGH/LOW change mV|ADC min/max V|HIGH late-envelope µV(12–15/16–20µs)|
|---|---|---:|---:|---|---|---|
|c100_cap100n|0/0|20050|0.063189|0.063213/0.000023|2.025115/2.025652|57.237558/38.361609|
|c100_cap500n|0/0|20054|0.018121|0.018126/0.000019|2.025115/2.025652|17.772122/16.405507|
|c100_cap9u|0/0|20058|0.001105|0.001105/0.000019|2.025115/2.025652|1.103851/1.098956|
|c100_coil50u|0/0|20114|0.092091|0.114260/0.021131|2.025035/2.025710|13.458624/0.004495|
|c100_open|0/0|20146|0.120769|0.115034/0.021255|2.025124/2.025632|0.000021/0.000012|
|c100_short10m|0/0|20020|0.000012|0.000010/0.000002|2.025068/2.025676|0.000000/0.000009|
|c100k_coil_hi0_lo0|0/0|102098|1.886212|4.877788/0.414216|2.024949/2.025773|73.501165/0.050774|
|c100k_coil_hi0_lo100|0/100|79529|0.747866|6.275764/0.120909|2.024992/2.025740|5750.766572/4002.859278|
|c100k_coil_hi100_lo0|100/0|64221|8.623371|0.471492/0.459007|2.022173/2.028171|3.426716/0.000248|
|c100k_coil_hi100_lo100|100/100|25118|8.600731|0.551599/0.248481|2.022144/2.028209|14.340070/2.367666|

These finite traces test bounded response over the stated window. They do not establish asymptotic stability, complete settling, arbitrary fixture tolerance or all internal-loop pole counts. Loop analysis and hardware qualification remain separate.
