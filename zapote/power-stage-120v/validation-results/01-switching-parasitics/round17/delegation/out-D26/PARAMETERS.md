# Catalog UCC21550BDWKR parameter ledger

Source: Texas Instruments **SLUSE89C**, May2023, revised August2024,
[original catalog datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf).
Printed pages are used below. The B suffix selects the8V output-UVLO option.
No automotive model was incorporated. All table limits are conditional on
the table's stated operating/test conditions; blank cells remain unknown.

| Quantity | Min / typical / max | Source and use |
|---|---|---|
| Each A/B rising and falling propagation |26 /33 /45ns|p10 §5.9,100ns input,500kHz,unloaded; high input threshold→output10%, low threshold→output90%. CORNER−1/0/+1 selects these.|
| Same-channel pulse-width distortion |— /0 /5ns|p10 §5.9, absolute difference between rise/fall delays. PWD independently shifts rise by+PWD/2 and fall by−PWD/2.|
| Same-edge channel matching |— /0 /6.5ns cold;5ns otherwise|p10 §5.9,−40…−10°C versus−10…150°C. SKEW independently shifts B.|
| Input pulse passing unloaded |4 /12 /30ns|p10 §5.9 and p24 §7.3.4; both ON and OFF must exceed30ns to guarantee passage. Inertial filter selects these values; finite ramp and event resolution affect boundary tests.|
| Input and DIS high threshold |— /2 /2.3V|p9 §5.8. Nominal hysteretic switch uses2V.|
| Input and DIS low threshold |0.8 /1 /—V|p9 §5.8. Nominal switch uses1V.|
| Input/DIS hysteresis |— /1 /—V|p9 §5.8. Not a guaranteed1V window.|
| Input pull-down; DIS pull-up |50 /90 /185kΩ|p9 §5.8 at3.3V; model90kΩ.|
| Programmed dead time10kΩ |86 /99 /112ns|p10 §5.8.|
| Programmed dead time20kΩ |167 /185 /203ns|p10 §5.8.|
| Programmed dead time50kΩ |399 /443 /487ns|p10 §5.8.|
| Typical programming equation |8.6×R(kΩ)+13ns|p25 §7.4.2.2,1.7…100kΩ. Equation is approximate; max/min interpolation is a model assumption, not an extra TI guarantee.|
| R9/R17 |49.9kΩ ±0.1%|D12 resistor selection and DECISIONS2026-10-03; native19 and frozen BOM identifyRT0603BRD0749K9L. CORNER applies−0.1%,0,+0.1% along with timing scenario.|
| Combination rule |Longer programmed/input gap|pp25–26 §7.4.2; overlapping inputs force both outputs low. Model delays expiration of opposite-active state, cancelling expiration if reasserted. DTEN=0 represents floating DT and permits overlap.|
| Controller gap |200ns|DECISIONS2026-10-03 O07; independently applied both directions.|
| DC source/sink resistance |— /5Ω and0.55Ω /—|p10 §5.8 at±50mA; typical only.|
| Transient pull-up assistance |about1.47Ω NMOS parallel to PMOS|p24 §7.3.4/Fig7-2. Model assumes20ns duration; the datasheet supplies no duration, process range, or nonlinear trajectory.|
| Peak source/sink current |— /4A and6A /—|p9 §5.8,CL0.22µF,CVDD10µF,1kHz; **not hard clipping limits**. No clipping is imposed.|
| Rise and fall,1.8nF |— /8ns each /—|p10 §5.9,12/25V, rise20–80%,fall90–10%. Model uses5ns control ramp and reports a fixture miss rather than fitting its gate behavior.|
| VCCI UVLO on |2.55 /2.7 /2.85V|p9 §5.8. Model nominal threshold.|
| VCCI UVLO off |2.35 /2.5 /2.65V|p9 §5.8; hysteresis typical0.2V.|
| VCCI UVLO on/off delay |18 /42 /80µs;0.5 /1.2 /7µs|p9 §5.8. CORNER selects delays. Deglitch0.4/0.9/3.1µs is not added again.|
| B-output UVLO on |7.7 /8.5 /8.9V|p9 §5.8; model nominal.|
| B-output UVLO off |7.2 /7.9 /8.4V|p9 §5.8; typical hysteresis0.6V.|
| Output UVLO on/off delay |— /— /10µs;0.1 /0.5 /2µs|p9 §5.8. On delay fixed10µs is an explicit choice, not a typical. Filter0.1/0.17/—µs is not added again.|
| DIS assertion/release propagation |27 /48 /80ns|p10 §5.9;20ns typical filter. The behavioral DIS buffer uses total propagation as its inertial interval: deglitch response is simplified.|
| Unpowered active pull-down |— /1.6 /2V at200mA|p10 §5.8; NOT represented by the powered0.55Ω sink.|

The no-load logical delay guarantees and the separate output-stage typicals
do not supply a physical bound on die-VGS crossing times. Same-edge skew and
same-channel distortion constrain differences; independently choosing26ns
for one edge and45ns for its partner would violate those constraints.

The stress scenarios therefore use center35.5ns, B skew±6.5ns and same-channel
PWD±5ns independently, producing edge delays within26.5…44.5ns, while DT is
independently min/max. This samples allowed combinations; it is not a proof
that every physically correlated corner is covered. The pulse filter is held
at12ns in these scenarios because its correlation with propagation is unknown.

At49.9kΩ the table has no explicit guaranteed row. The model linearly
interpolates the stated DT spread between20 and50kΩ and applies resistor
tolerance. At50.0kΩ/zero tolerance its fixtures directly test the table.
